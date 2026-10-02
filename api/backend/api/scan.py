"""API 區：今日訊號掃描（結果由控制區背景排程 backend.control.scheduler 產生並存入 DB，
這裡只負責讀取／觸發重新分析，不做任何抓資料或計算）。"""
import asyncio
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException

from backend.db import portfolio_db as db
from backend.control.strategy.ai_batch import is_batch_running, run_batch_ai_analysis
from backend.control.strategy.scanner import ai_targets
from backend.utils import TAIPEI, is_trading_day

router = APIRouter()

# 掃描候選清單要附上的 AI 分析欄位（前端讀 ai_<欄位名>）
_AI_FIELDS = ("verdict", "confidence", "summary", "key_reasons", "risks", "trace_steps", "news")


@router.get("/api/scan/today")
async def get_scan_cache():
    result = await asyncio.to_thread(db.get_latest_scan_result, False)
    if result is None:
        return {"cached": False, "buy_candidates": [], "sell_candidates": [],
                "scanned": 0, "scan_time": None}
    result["cached"] = True

    scan_date = result.get("scan_date")
    ai_results = await asyncio.to_thread(db.get_stock_ai_results_for_date, scan_date) if scan_date else {}
    for c in result.get("buy_candidates", []) + result.get("sell_candidates", []):
        ai = ai_results.get(c["ticker"], {})
        for field in _AI_FIELDS:
            c[f"ai_{field}"] = ai.get(field)
    result["ai_enriched"] = bool(ai_results)
    return result


@router.get("/api/scan/ai-trace/{ticker}")
async def get_scan_ai_trace(ticker: str, scan_date: str | None = None):
    """單一股票批次 AI 分析的完整流程；列表不帶 trace（太大），前端展開時才呼叫。"""
    if scan_date is None:
        latest = await asyncio.to_thread(db.get_latest_scan_tickers)
        if latest is None:
            raise HTTPException(404, "尚無掃描結果")
        scan_date = latest[0]
    trace = await asyncio.to_thread(db.get_stock_ai_trace, ticker, scan_date)
    if trace is None:
        raise HTTPException(404, f"查無 {ticker} 的 AI 分析流程")
    return {"ticker": ticker, "scan_date": scan_date, "trace": trace}


@router.get("/api/scan/calendar")
async def get_scan_calendar(days: int = 30):
    """首頁執行狀況列表：每天的資料新鮮度／今日訊號掃描／AI批次分析 狀態。"""
    rows = await asyncio.to_thread(db.get_run_log, days)
    row_map = {r["run_date"]: r for r in rows}
    today = datetime.now(TAIPEI).date()
    out = []
    for i in range(days):
        d = today - timedelta(days=i)
        ds = d.strftime("%Y-%m-%d")
        r = row_map.get(ds, {})
        out.append({
            "date":           ds,
            "weekday":        "一二三四五六日"[d.weekday()],
            "is_trading_day": is_trading_day(d),
            "data":  {"status": r.get("data_status"), "data_date": r.get("data_date")},
            "scan":  {"status": r.get("scan_status"), "started_at": r.get("scan_started_at"),
                      "done_at": r.get("scan_done_at"), "error": r.get("scan_error")},
            "ai":    {"status": r.get("ai_status"), "started_at": r.get("ai_started_at"),
                      "done_at": r.get("ai_done_at"), "done_count": r.get("ai_done_count"),
                      "total_count": r.get("ai_total_count"), "error": r.get("ai_error")},
        })
    return {"days": out}


@router.get("/api/scan/ai-progress")
async def get_scan_ai_progress():
    latest = await asyncio.to_thread(db.get_latest_scan_tickers)
    if latest is None:
        return {"scan_date": None, "total": 0, "done": 0, "running": is_batch_running()}
    scan_date, tickers = latest
    tickers = list(set(tickers))
    done = await asyncio.to_thread(db.count_stock_ai_done, scan_date, tickers)
    return {"scan_date": scan_date, "total": len(tickers), "done": done, "running": is_batch_running()}


@router.post("/api/scan/ai-retry")
async def retry_scan_ai_analysis():
    """手動重新執行今日買入／賣出候選的 AI 分析（跳過已成功項目，重試先前因 LLM 無回應等失敗的項目）。"""
    if is_batch_running():
        return {"status": "running"}

    result = await asyncio.to_thread(db.get_latest_scan_result)
    if result is None:
        raise HTTPException(400, "尚無掃描結果")

    scan_date = result.get("scan_date")
    targets = ai_targets(result)

    async def _run():
        try:
            await asyncio.to_thread(run_batch_ai_analysis, targets, scan_date)
        except Exception:
            logging.getLogger(__name__).exception("[ai-retry] 重新分析失敗")

    asyncio.create_task(_run())
    return {"status": "started", "total": len(targets)}
