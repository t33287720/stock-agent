"""API 區：單股回測。"""
from fastapi import APIRouter, HTTPException

from backend.control.data.fetcher import get_stock_history
from backend.control.analysis.technical import calculate_indicators
from backend.control.strategy.signals import run_backtest

router = APIRouter()


# ── 個股回測 ─────────────────────────────────────────────────────────────────────

@router.post("/api/backtest/{ticker}")
async def backtest(ticker: str, days: int = 365, with_fee: bool = True):
    df = get_stock_history(ticker, days)
    if df.empty:
        raise HTTPException(404, f"找不到 {ticker} 的歷史資料")
    df = calculate_indicators(df)
    result = run_backtest(ticker, df, with_fee=with_fee)
    return vars(result)

