"""
批次 ReAct AI 分析 — 對今日訊號掃描抓到的股票逐一執行完整的個股 AI 分析流程
（與 `/api/stock/{ticker}/ai-analysis` 相同：最多 10 輪延伸搜尋 + 二次驗證），
結果存入 stock_ai_results，供今日訊號掃描頁面與自動交易系統使用。

Ollama 為單一 GPU，無法平行處理多個 LLM 請求，因此序列執行。
已有當日結果的股票會跳過，容器重啟後可從中斷處繼續。
"""
import logging

from backend.data.fetcher import get_fundamental
from backend.data.news import get_stock_news
from backend.llm.analysis import analyze_stock_stream
import backend.db.portfolio_db as db

logger = logging.getLogger(__name__)


def run_batch_ai_analysis(all_candidates: list[dict], scan_date: str) -> dict:
    """對 all_candidates 逐一執行完整 ReAct AI 分析，存入 stock_ai_results。

    已有當日結果者跳過 → 容器重啟後可從中斷處繼續。
    """
    done = db.get_stock_ai_results_for_date(scan_date)
    analyzed = failed = 0

    for c in all_candidates:
        ticker = c["ticker"]
        if ticker in done:
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

    logger.info("[ai_batch] 完成：新增 %d、失敗 %d、跳過(已完成) %d", analyzed, failed, len(done))
    return {"analyzed": analyzed, "failed": failed, "skipped": len(done)}
