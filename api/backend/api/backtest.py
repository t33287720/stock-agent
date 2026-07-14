"""API 區：單股回測 / 策略歷史驗證（全組合回測）。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.control.data.fetcher import get_stock_history
from backend.control.analysis.technical import calculate_indicators
from backend.control.strategy.signals import run_backtest
from backend.control.strategy.full_backtest import run_full_portfolio_backtest

router = APIRouter()


class FullBacktestBody(BaseModel):
    months: int = 12
    initial_capital: float = 100_000
    per_stock_budget: float = 10_000
    max_candidates: int = 40


# ── 個股回測 ─────────────────────────────────────────────────────────────────────

@router.post("/api/backtest/{ticker}")
async def backtest(ticker: str, days: int = 365, with_fee: bool = True):
    df = get_stock_history(ticker, days)
    if df.empty:
        raise HTTPException(404, f"找不到 {ticker} 的歷史資料")
    df = calculate_indicators(df)
    result = run_backtest(ticker, df, with_fee=with_fee)
    return vars(result)


# ── 策略歷史驗證 ─────────────────────────────────────────────────────────────────

@router.post("/api/full-backtest")
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
