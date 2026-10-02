"""
批次 ReAct AI 分析 — 對今日訊號掃描的買入／賣出候選逐一執行完整的個股 AI 分析流程
（與 `/api/stock/{ticker}/ai-analysis` 相同：最多 10 輪延伸搜尋 + 二次驗證），
結果存入 stock_ai_results，供今日訊號掃描頁面使用。

Ollama 為單一 GPU，無法平行處理多個 LLM 請求，因此序列執行。
已有當日結果的股票會跳過，容器重啟後可從中斷處繼續。
"""
import logging
import threading

from backend.control.data.fetcher import get_fundamental
from backend.control.data.news import get_stock_news
from backend.control.llm.analysis import analyze_stock_stream
import backend.db.portfolio_db as db

logger = logging.getLogger(__name__)

# 背景排程與手動「重新分析」共用同一把鎖：同一時間只會有一批在跑，
# 避免兩批同時把請求丟給單一 GPU 的 Ollama、互相拖慢甚至重複分析同一支股票。
_batch_lock = threading.Lock()


def is_batch_running() -> bool:
    return _batch_lock.locked()


def run_batch_ai_analysis(candidates: list[dict], scan_date: str) -> dict:
    """對 candidates（scanner.ai_targets() 挑出的買賣候選）逐一執行完整 ReAct AI 分析，存入 stock_ai_results。

    已有當日成功結果者跳過 → 容器重啟後可從中斷處繼續；
    先前因本機 LLM 無回應等錯誤而失敗的項目會重新分析。
    若已有另一批正在執行，會等它跑完再開始（屆時已完成的會直接跳過）。
    """
    with _batch_lock:
        return _run_batch(candidates, scan_date)


def _run_batch(candidates: list[dict], scan_date: str) -> dict:
    done = db.get_stock_ai_results_for_date(scan_date)
    skipped = sum(1 for c in candidates if c["ticker"] in done and not done[c["ticker"]].get("error"))
    analyzed = failed = 0

    for c in candidates:
        ticker = c["ticker"]
        if ticker in done and not done[ticker].get("error"):
            continue
        try:
            fund = get_fundamental(ticker)
            name = fund.get("name") or c.get("name") or ticker
            news = get_stock_news(ticker, name)

            result = None
            for event in analyze_stock_stream(ticker, name, c["technical"], fund, news):
                if event["type"] == "result":
                    result = event["result"]

            if result is None:
                raise RuntimeError("無回應")

            result["news"] = news
            db.save_stock_ai_result(ticker, name, scan_date, result)
            analyzed += 1
        except Exception:
            logger.exception("[ai_batch] %s 分析失敗", ticker)
            failed += 1

    logger.info("[ai_batch] 完成：新增 %d、失敗 %d、跳過(已完成) %d", analyzed, failed, skipped)
    return {"analyzed": analyzed, "failed": failed, "skipped": skipped}
