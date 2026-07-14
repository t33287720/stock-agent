"""API 區：自動交易（模擬）。"""
import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.control.data.fetcher import get_fundamental, get_stock_history
from backend.control.analysis.technical import calculate_indicators
from backend.control.strategy.auto_trade import (
    init_auto_portfolio, execute_trade,
    auto_portfolio_summary, get_equity_history, load_auto_orders,
    cancel_position as cancel_auto_position,
)

router = APIRouter()


class AutoInitBody(BaseModel):
    capital: float = 100_000
    per_stock_budget: float = 10_000


class AutoTradeBody(BaseModel):
    ticker: str
    action: str   # "auto" | "buy" | "sell"


@router.get("/api/auto/status")
async def auto_status():
    return auto_portfolio_summary()


@router.post("/api/auto/init")
async def auto_init(body: AutoInitBody):
    init_auto_portfolio(body.capital, body.per_stock_budget)
    return {"status": "ok", "message": f"已初始化：資金 NT${body.capital:,.0f}，每股上限 NT${body.per_stock_budget:,.0f}"}


@router.post("/api/auto/trade")
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


@router.post("/api/auto/cancel/{ticker}")
async def cancel_position_endpoint(ticker: str):
    """撤銷持倉：退回原始買入金額（股款 + 手續費），並刪除今日買入紀錄。"""
    result = await asyncio.to_thread(cancel_auto_position, ticker)
    if "error" in result:
        raise HTTPException(404 if "未持有" in result["error"] else 400, result["error"])
    return result


@router.get("/api/auto/orders")
async def auto_orders():
    return load_auto_orders()


@router.get("/api/auto/history")
async def auto_history():
    return {"history": get_equity_history()}
