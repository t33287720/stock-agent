"""API 區：今日訊號掃描（結果由控制區背景排程 backend.control.scheduler 產生並存入 DB，
這裡只負責讀取／觸發重新分析，不做任何抓資料或計算）。"""
import asyncio
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException

from backend.db import portfolio_db as db
from backend.control.strategy.ai_batch import run_batch_ai_analysis, build_candidates_with_portfolio
from backend.utils import TAIPEI, is_trading_day

router = APIRouter()

_ai_retry_running = False


@router.get("/api/scan/today")
async def get_scan_cache():
    result = await asyncio.to_thread(db.get_latest_scan_result)
    if result is None:
        return {"cached": False, "buy_candidates": [], "sell_candidates": [],
                "scanned": 0, "scan_time": None}
    result["cached"] = True

    scan_date = result.get("scan_date")
    ai_results = await asyncio.to_thread(db.get_stock_ai_results_for_date, scan_date) if scan_date else {}
    for c in result.get("buy_candidates", []) + result.get("sell_candidates", []):
        ai = ai_results.get(c["ticker"])
        c["ai_verdict"] = ai.get("verdict") if ai else None
        c["ai_confidence"] = ai.get("confidence") if ai else None
        c["ai_summary"] = ai.get("summary") if ai else None
        c["ai_key_reasons"] = ai.get("key_reasons") if ai else None
        c["ai_risks"] = ai.get("risks") if ai else None
        c["ai_trace"] = ai.get("trace") if ai else None
        c["ai_news"] = ai.get("news") if ai else None
    result["ai_enriched"] = bool(ai_results)

    result.pop("all_candidates", None)
    return result


@router.get("/api/scan/calendar")
async def get_scan_calendar(days: int = 30):
    """首頁執行狀況列表：每天的資料新鮮度／今日訊號掃描／AI批次分析／自動交易 狀態。"""
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
            "trade": {"status": r.get("trade_status"), "started_at": r.get("trade_started_at"),
                      "done_at": r.get("trade_done_at"), "summary": r.get("trade_summary"),
                      "error": r.get("trade_error")},
        })
    return {"days": out}


@router.get("/api/scan/ai-progress")
async def get_scan_ai_progress():
    result = await asyncio.to_thread(db.get_latest_scan_result)
    if result is None:
        return {"scan_date": None, "total": 0, "done": 0}
    scan_date = result.get("scan_date")
    total = len(result.get("all_candidates", []))
    ai_results = await asyncio.to_thread(db.get_stock_ai_results_for_date, scan_date)
    done = sum(1 for r in ai_results.values() if not r.get("error"))
    return {"scan_date": scan_date, "total": total, "done": done, "running": _ai_retry_running}


@router.post("/api/scan/ai-retry")
async def retry_scan_ai_analysis():
    """手動重新執行今日掃描候選股的 AI 分析（跳過已成功項目，重試先前因 LLM 無回應等失敗的項目）。"""
    global _ai_retry_running
    if _ai_retry_running:
        return {"status": "running"}

    result = await asyncio.to_thread(db.get_latest_scan_result)
    if result is None:
        raise HTTPException(400, "尚無掃描結果")

    scan_date = result.get("scan_date")
    all_candidates = await asyncio.to_thread(build_candidates_with_portfolio, result.get("all_candidates", []))

    async def _run():
        global _ai_retry_running
        _ai_retry_running = True
        try:
            await asyncio.to_thread(run_batch_ai_analysis, all_candidates, scan_date)
        except Exception:
            logging.getLogger(__name__).exception("[ai-retry] 重新分析失敗")
        finally:
            _ai_retry_running = False

    asyncio.create_task(_run())
    return {"status": "started", "total": len(all_candidates)}
