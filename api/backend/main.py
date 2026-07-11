"""
FastAPI backend for Taiwan Stock AI Analyzer.
Run: uvicorn backend.main:app --host 0.0.0.0 --port 8000
"""
import asyncio
import json
import logging
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import iterate_in_threadpool

from backend.config import load_config, save_config
from backend.data.fetcher import get_fundamental, get_stock_history, get_top100_stocks
from backend.data.news import get_stock_news
from backend.db import portfolio_db as db
from backend.llm.analysis import (
    analyze_stock_stream,
    get_cached_analysis, save_analysis_cache,
)
from backend.analysis.technical import calculate_indicators, get_indicator_summary
from backend.scheduler import scan_loop
from backend.utils import TAIPEI, is_trading_day
from backend.strategy.signals import generate_signals, run_backtest
from backend.strategy.auto_trade import (
    init_auto_portfolio, execute_trade,
    auto_portfolio_summary, get_equity_history, load_auto_orders,
    cancel_position as cancel_auto_position,
)
from backend.strategy.full_backtest import run_full_portfolio_backtest
from backend.strategy.ai_batch import run_batch_ai_analysis

app = FastAPI(title="台股 AI 分析系統", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

static_path = Path(__file__).parent.parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


@app.on_event("startup")
async def _start_background_scanner():
    """容器啟動時立即執行一次資料更新檢查，之後每小時檢查一次。"""
    asyncio.create_task(scan_loop())


# ── Request models ──────────────────────────────────────────────────────────────

class ConfigUpdate(BaseModel):
    settings: dict | None = None
    strategy: dict | None = None

class AutoInitBody(BaseModel):
    capital: float = 100_000
    per_stock_budget: float = 10_000

class FullBacktestBody(BaseModel):
    months: int = 12
    initial_capital: float = 100_000
    per_stock_budget: float = 10_000
    max_candidates: int = 40

class AutoTradeBody(BaseModel):
    ticker: str
    action: str   # "auto" | "buy" | "sell"


# ── Helpers ──────────────────────────────────────────────────────────────────────

def _safe(val):
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) else round(f, 4)
    except (TypeError, ValueError):
        return None


def _build_history(df) -> list[dict]:
    records = []
    for date, row in df.iterrows():
        records.append({
            "date":        str(date)[:10],
            "open":        _safe(row.get("Open")),
            "high":        _safe(row.get("High")),
            "low":         _safe(row.get("Low")),
            "close":       _safe(row.get("Close")),
            "volume":      _safe(row.get("Volume")),
            "sma20":       _safe(row.get("SMA_20")),
            "sma60":       _safe(row.get("SMA_60")),
            "rsi":         _safe(row.get("RSI")),
            "macd":        _safe(row.get("MACD")),
            "macd_signal": _safe(row.get("MACD_signal")),
            "macd_hist":   _safe(row.get("MACD_hist")),
            "k":           _safe(row.get("K")),
            "d":           _safe(row.get("D")),
            "bb_upper":    _safe(row.get("BB_upper")),
            "bb_mid":      _safe(row.get("BB_mid")),
            "bb_lower":    _safe(row.get("BB_lower")),
            "signal":      int(row.get("signal", 0)),
            "signal_reason": str(row.get("signal_reason", "")),
        })
    return records


# ── Routes ──────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "ok"}


# ── 股票列表 ─────────────────────────────────────────────────────────────────────

@app.get("/api/top100")
async def top100():
    stocks = get_top100_stocks()
    return {
        "stocks":     stocks,
        "count":      len(stocks),
        "fetched_at": datetime.now(TAIPEI).strftime("%H:%M"),
    }


# ── 個股分析 ─────────────────────────────────────────────────────────────────────

@app.get("/api/stock/{ticker}")
async def stock_analysis(ticker: str, days: int = 365):
    # 並行抓 K 線和基本面，省去串行等待
    df_task   = asyncio.to_thread(get_stock_history, ticker, days)
    fund_task = asyncio.to_thread(get_fundamental, ticker)
    df, fund  = await asyncio.gather(df_task, fund_task)
    if df.empty:
        raise HTTPException(404, f"找不到 {ticker} 的歷史資料")
    df = calculate_indicators(df)
    df = generate_signals(df)
    return {
        "ticker":      ticker,
        "name":        fund.get("name", ticker),
        "technical":   get_indicator_summary(df),
        "fundamental": fund,
        "history":     _build_history(df),
    }


@app.get("/api/stock/{ticker}/news")
async def stock_news(ticker: str):
    fund = get_fundamental(ticker)
    news = await asyncio.to_thread(get_stock_news, ticker, fund.get("name", ticker))
    return {"news": news}


@app.post("/api/stock/{ticker}/ai-analysis")
async def stock_ai_analysis(ticker: str, force: bool = False):
    """以 NDJSON 串流回傳分析過程：每完成一步就送出一行 JSON，最後送出最終結果。"""
    if not force:
        cached = await asyncio.to_thread(get_cached_analysis, ticker)
        if cached is not None:
            async def cached_stream():
                yield json.dumps({"type": "result", "result": {**cached, "from_cache": True}}, ensure_ascii=False) + "\n"
            return StreamingResponse(cached_stream(), media_type="application/x-ndjson")

    df_task = asyncio.to_thread(get_stock_history, ticker, 365)
    fund_task = asyncio.to_thread(get_fundamental, ticker)
    df, fund = await asyncio.gather(df_task, fund_task)
    if df.empty:
        raise HTTPException(404, f"找不到 {ticker} 的歷史資料")

    df = calculate_indicators(df)
    df = generate_signals(df)
    technical = get_indicator_summary(df)
    name = fund.get("name", ticker)
    news = await asyncio.to_thread(get_stock_news, ticker, name)

    async def event_stream():
        gen = analyze_stock_stream(ticker, name, technical, fund, news)
        async for event in iterate_in_threadpool(gen):
            if event["type"] == "result":
                result = event["result"]
                result["news"] = news
                await asyncio.to_thread(save_analysis_cache, ticker, result)
                event = {"type": "result", "result": {**result, "from_cache": False}}
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


# ── 個股回測 ─────────────────────────────────────────────────────────────────────

@app.post("/api/backtest/{ticker}")
async def backtest(ticker: str, days: int = 365, with_fee: bool = True):
    df = get_stock_history(ticker, days)
    if df.empty:
        raise HTTPException(404, f"找不到 {ticker} 的歷史資料")
    df = calculate_indicators(df)
    result = run_backtest(ticker, df, with_fee=with_fee)
    return vars(result)


# ── 自動交易 ─────────────────────────────────────────────────────────────────────

@app.get("/api/auto/status")
async def auto_status():
    return auto_portfolio_summary()


@app.post("/api/auto/init")
async def auto_init(body: AutoInitBody):
    init_auto_portfolio(body.capital, body.per_stock_budget)
    return {"status": "ok", "message": f"已初始化：資金 NT${body.capital:,.0f}，每股上限 NT${body.per_stock_budget:,.0f}"}


@app.post("/api/auto/trade")
async def auto_trade_endpoint(body: AutoTradeBody):
    df = await asyncio.to_thread(get_stock_history, body.ticker, 365)
    if df.empty:
        raise HTTPException(404, f"找不到 {body.ticker} 的歷史資料")
    df = calculate_indicators(df)
    fund = get_fundamental(body.ticker)
    action_taken, msg = execute_trade(body.ticker, df, body.action, fund.get("name", body.ticker))
    if action_taken == "error":
        raise HTTPException(400, msg)
    return {"status": "ok", "action": action_taken, "message": msg}


@app.post("/api/auto/cancel/{ticker}")
async def cancel_position_endpoint(ticker: str):
    """撤銷持倉：退回原始買入金額（股款 + 手續費），並刪除今日買入紀錄。"""
    result = await asyncio.to_thread(cancel_auto_position, ticker)
    if "error" in result:
        raise HTTPException(404 if "未持有" in result["error"] else 400, result["error"])
    return result


@app.get("/api/auto/orders")
async def auto_orders():
    return load_auto_orders()


@app.get("/api/auto/history")
async def auto_history():
    return {"history": get_equity_history()}


# ── 策略歷史驗證 ─────────────────────────────────────────────────────────────────

@app.post("/api/full-backtest")
async def full_backtest(body: FullBacktestBody):
    result = await run_full_portfolio_backtest(
        months=body.months,
        initial_capital=body.initial_capital,
        per_stock_budget=body.per_stock_budget,
        max_candidates=body.max_candidates,
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


# ── 今日訊號掃描 ─────────────────────────────────────────────────────────────────

@app.get("/api/scan/today")
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


@app.get("/api/scan/calendar")
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


_ai_retry_running = False


@app.get("/api/scan/ai-progress")
async def get_scan_ai_progress():
    result = await asyncio.to_thread(db.get_latest_scan_result)
    if result is None:
        return {"scan_date": None, "total": 0, "done": 0}
    scan_date = result.get("scan_date")
    total = len(result.get("all_candidates", []))
    ai_results = await asyncio.to_thread(db.get_stock_ai_results_for_date, scan_date)
    done = sum(1 for r in ai_results.values() if not r.get("error"))
    return {"scan_date": scan_date, "total": total, "done": done, "running": _ai_retry_running}


@app.post("/api/scan/ai-retry")
async def retry_scan_ai_analysis():
    """手動重新執行今日掃描候選股的 AI 分析（跳過已成功項目，重試先前因 LLM 無回應等失敗的項目）。"""
    global _ai_retry_running
    if _ai_retry_running:
        return {"status": "running"}

    result = await asyncio.to_thread(db.get_latest_scan_result)
    if result is None:
        raise HTTPException(400, "尚無掃描結果")

    all_candidates = list(result.get("all_candidates", []))
    scan_date = result.get("scan_date")

    # 補充持倉中不在掃描名單的股票
    from backend.data.fetcher import get_stock_history
    from backend.analysis.technical import calculate_indicators, get_indicator_summary
    scanned_tickers = {c["ticker"] for c in all_candidates}
    portfolio = await asyncio.to_thread(db.load_portfolio)
    if portfolio:
        for ticker, pos in portfolio.get("positions", {}).items():
            if ticker in scanned_tickers:
                continue
            try:
                df = await asyncio.to_thread(get_stock_history, ticker, 90)
                if df.empty or len(df) < 20:
                    continue
                df = calculate_indicators(df)
                all_candidates.append({
                    "ticker":    ticker,
                    "name":      pos.get("name", ticker),
                    "technical": get_indicator_summary(df),
                })
            except Exception:
                pass

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


# ── 設定 ─────────────────────────────────────────────────────────────────────────

@app.get("/api/config")
async def get_config():
    cfg = load_config()
    return {
        "settings": cfg.get("settings", {}),
        "strategy": cfg.get("strategy", {}),
    }


@app.put("/api/config")
async def update_config(update: ConfigUpdate):
    cfg = load_config()
    if update.settings:
        cfg["settings"].update(update.settings)
    if update.strategy:
        cfg["strategy"].update(update.strategy)
    save_config(cfg)
    return {"status": "ok", "message": "設定已儲存"}
