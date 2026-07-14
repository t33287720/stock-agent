"""API 區：個股清單 / 個股技術+基本面分析 / 個股新聞 / 個股 AI 分析。
只做 request 解析 → 呼叫控制區 (backend.control.*) → 組回應，不放商業邏輯。
"""
import asyncio
import json
import math
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from starlette.concurrency import iterate_in_threadpool

from backend.control.data.fetcher import get_fundamental, get_stock_history, get_top100_stocks
from backend.control.data.news import get_stock_news
from backend.control.analysis.technical import calculate_indicators, get_indicator_summary
from backend.control.strategy.signals import generate_signals
from backend.control.llm.analysis import (
    analyze_stock_stream,
    get_cached_analysis, save_analysis_cache,
)
from backend.utils import TAIPEI

router = APIRouter()


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


# ── 股票列表 ─────────────────────────────────────────────────────────────────────

@router.get("/api/top100")
async def top100():
    stocks = get_top100_stocks()
    return {
        "stocks":     stocks,
        "count":      len(stocks),
        "fetched_at": datetime.now(TAIPEI).strftime("%H:%M"),
    }


# ── 個股分析 ─────────────────────────────────────────────────────────────────────

@router.get("/api/stock/{ticker}")
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


@router.get("/api/stock/{ticker}/news")
async def stock_news(ticker: str):
    fund = get_fundamental(ticker)
    news = await asyncio.to_thread(get_stock_news, ticker, fund.get("name", ticker))
    return {"news": news}


@router.post("/api/stock/{ticker}/ai-analysis")
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
