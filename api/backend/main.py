"""
FastAPI 入口 — API 區的組裝點。
本檔案只做三件事：建立 app、掛載 backend/api/*.py 底下的路由、啟動背景排程。
每個功能實際的路由邏輯請見 backend/api/（API 區），
撈外部資料／寫 DB 的商業邏輯請見 backend/control/（控制區）。
Run: uvicorn backend.main:app --host 0.0.0.0 --port 8000
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.control.scheduler import scan_loop
from backend.api import stocks, chat, backtest, auto_trade, scan, settings, market

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


@app.get("/")
async def root():
    return {"status": "ok"}


# ── API 區路由掛載：每支檔案對應一個功能，詳見 backend/api/ 底下的檔案 ──────────────
app.include_router(stocks.router)       # 股票列表 / 個股技術+基本面分析 / 新聞 / AI 分析
app.include_router(chat.router)         # 問股票聊天
app.include_router(backtest.router)     # 單股回測 / 策略歷史驗證
app.include_router(auto_trade.router)   # 自動交易（模擬）
app.include_router(scan.router)         # 今日訊號掃描
app.include_router(settings.router)     # 策略/系統設定
app.include_router(market.router)       # 全市場篩選
