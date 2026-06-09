"""
FastAPI backend for Taiwan Stock AI Analyzer.
Run: uvicorn backend.main:app --host 0.0.0.0 --port 8000
"""
import asyncio
import math
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import load_config, save_config
from backend.data.fetcher import get_fundamental, get_stock_history, get_top100_stocks
from backend.analysis.technical import calculate_indicators, get_indicator_summary
from backend.strategy.signals import generate_signals, run_backtest
from backend.strategy.auto_trade import (
    init_auto_portfolio, morning_scan, execute_trade,
    auto_portfolio_summary, get_equity_history, load_auto_orders,
    cancel_position as cancel_auto_position,
)
from backend.strategy.full_backtest import run_full_portfolio_backtest
from backend.strategy.scanner import scan_today, save_scan, load_scan

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


# ── Request models ──────────────────────────────────────────────────────────────

class ConfigUpdate(BaseModel):
    api_keys: dict | None = None
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
        "fetched_at": datetime.now().strftime("%H:%M"),
    }


# ── 個股分析 ─────────────────────────────────────────────────────────────────────

@app.get("/api/stock/{ticker}")
async def stock_analysis(ticker: str, days: int = 365):
    df = get_stock_history(ticker, days)
    if df.empty:
        raise HTTPException(404, f"找不到 {ticker} 的歷史資料")
    df = calculate_indicators(df)
    df = generate_signals(df)
    fund = get_fundamental(ticker)
    return {
        "ticker":      ticker,
        "name":        fund.get("name", ticker),
        "technical":   get_indicator_summary(df),
        "fundamental": fund,
        "history":     _build_history(df),
    }


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


@app.post("/api/auto/scan")
async def auto_scan(max_candidates: int = 100):
    result = await asyncio.to_thread(morning_scan, max_candidates)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


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
    result = load_scan()
    if result is None:
        return {"cached": False, "buy_candidates": [], "sell_candidates": [],
                "scanned": 0, "scan_time": None}
    return result


@app.post("/api/scan/today")
async def scan_today_signals(max_candidates: int = 150):
    result = await asyncio.to_thread(scan_today, max_candidates)
    await asyncio.to_thread(save_scan, result)
    return result


# ── AI Agent（佔位符，保留 UI 接口）────────────────────────────────────────────────

@app.post("/api/agent/{ticker}")
async def agent_analyze(ticker: str):
    return {
        "ticker":     ticker,
        "verdict":    "中性觀望",
        "confidence": 0,
        "steps":      [],
        "key_reasons": ["AI Agent 功能建置中"],
        "risks":      [],
        "summary":    "AI Agent 分析功能尚未啟用，請使用技術面指標與訊號作為參考。",
        "provider":   "—",
        "iterations": 0,
    }


# ── 設定 ─────────────────────────────────────────────────────────────────────────

@app.get("/api/config")
async def get_config():
    cfg = load_config()
    masked = {k: ("*" * (len(v) - 4) + v[-4:]) if len(v) > 4 else "*" * len(v)
              for k, v in cfg.get("api_keys", {}).items()}
    return {
        "api_keys_masked": masked,
        "settings":        cfg.get("settings", {}),
        "strategy":        cfg.get("strategy", {}),
    }


@app.put("/api/config")
async def update_config(update: ConfigUpdate):
    cfg = load_config()
    if update.api_keys:
        for k, v in update.api_keys.items():
            if v:
                cfg["api_keys"][k] = v
    if update.settings:
        cfg["settings"].update(update.settings)
    if update.strategy:
        cfg["strategy"].update(update.strategy)
    save_config(cfg)
    return {"status": "ok", "message": "設定已儲存"}


@app.get("/api/health")
async def health():
    cfg = load_config()
    return {"status": "ok", "llm_provider": cfg["settings"].get("llm_provider")}
