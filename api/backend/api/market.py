"""API 區：全市場篩選（TWSE 上市 + TPEX 上櫃，不限於今日訊號掃描的成交量前 300 大候選池）。"""
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.control.data.fetcher import get_market_screener
from backend.control.strategy.market_screener import compute_technical_for_tickers, MAX_TICKERS
from backend.utils import TAIPEI

router = APIRouter()


class TechnicalBody(BaseModel):
    tickers: list[str]


@router.get("/api/market/screener")
async def market_screener():
    stocks = get_market_screener()
    return {
        "stocks":     stocks,
        "count":      len(stocks),
        "fetched_at": datetime.now(TAIPEI).strftime("%H:%M"),
    }


@router.post("/api/market/technical")
async def market_technical(body: TechnicalBody):
    if len(body.tickers) > MAX_TICKERS:
        raise HTTPException(400, f"最多一次計算 {MAX_TICKERS} 支股票，請先縮小篩選範圍（目前 {len(body.tickers)} 支）")
    results = compute_technical_for_tickers(body.tickers)
    return {"results": results}
