"""
背景排程：容器啟動時立即檢查一次，之後每小時檢查資料是否有新交易日。
有新資料時自動執行「今日訊號掃描」並存入 DB，若自動交易已初始化則同時
執行「早盤掃描」（自動下單）。取代原本的手動「重新掃描」「早盤掃描」按鈕。
"""
import asyncio
import logging

from backend.config import load_config
from backend.data.fetcher import last_trading_day_str, get_stock_history
from backend.analysis.technical import calculate_indicators, get_indicator_summary
from backend.db import portfolio_db as db
from backend.strategy.ai_batch import run_batch_ai_analysis
from backend.strategy.auto_trade import morning_scan
from backend.strategy.scanner import scan_today

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 3600
SCAN_MAX_CANDIDATES = 150


def run_scan_cycle() -> None:
    """檢查是否有新交易日資料；有的話執行今日訊號掃描 + (若已啟用自動交易) 早盤掃描。"""
    current = last_trading_day_str()
    state = db.get_scan_state()

    if state.get("last_scan_date") == current:
        db.update_scan_state()
        return

    logger.info("[scheduler] 偵測到新交易日 %s，開始自動掃描", current)

    result = scan_today(max_candidates=SCAN_MAX_CANDIDATES)
    db.save_scan_result(current, result)

    cfg = load_config()
    if cfg.get("settings", {}).get("auto_scan_with_ai", True):
        try:
            all_candidates = list(result.get("all_candidates", []))
            scanned_tickers = {c["ticker"] for c in all_candidates}

            # 持倉中不在今日掃描名單的股票，補充技術資料後一併送 AI 分析
            portfolio = db.load_portfolio()
            if portfolio:
                for ticker, pos in portfolio.get("positions", {}).items():
                    if ticker in scanned_tickers:
                        continue
                    try:
                        df = get_stock_history(ticker, 90)
                        if df.empty or len(df) < 20:
                            continue
                        df = calculate_indicators(df)
                        all_candidates.append({
                            "ticker":    ticker,
                            "name":      pos.get("name", ticker),
                            "technical": get_indicator_summary(df),
                        })
                        logger.info("[scheduler] 補充持倉 %s 至 AI 分析名單", ticker)
                    except Exception:
                        logger.warning("[scheduler] 無法取得持倉 %s 技術資料，略過", ticker)

            run_batch_ai_analysis(all_candidates, current)
        except Exception:
            logger.exception("[scheduler] AI 批次分析失敗")

    if db.load_portfolio():
        try:
            morning_scan(max_candidates=SCAN_MAX_CANDIDATES)
        except Exception:
            logger.exception("[scheduler] 早盤掃描失敗")

    db.update_scan_state(current)
    logger.info("[scheduler] 自動掃描完成")


async def scan_loop() -> None:
    """容器啟動時立即跑一次，之後每小時檢查一次。"""
    loop = asyncio.get_running_loop()
    while True:
        try:
            await loop.run_in_executor(None, run_scan_cycle)
        except Exception:
            logger.exception("[scheduler] 自動掃描週期發生錯誤")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
