"""
背景排程：容器啟動時立即檢查一次，之後每小時檢查資料是否有新交易日。
有新資料時自動執行「今日訊號掃描」並存入 DB，若自動交易已初始化則同時
執行「早盤掃描」（自動下單）。取代原本的手動「重新掃描」「早盤掃描」按鈕。
"""
import asyncio
import logging

from backend.config import load_config
from backend.control.data.fetcher import last_trading_day_str
from backend.db import portfolio_db as db
from backend.control.strategy.ai_batch import run_batch_ai_analysis, build_candidates_with_portfolio
from backend.control.strategy.auto_trade import morning_scan, auto_portfolio_summary
from backend.control.strategy.scanner import scan_today

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

    db.start_phase(current, "scan")
    try:
        result = scan_today(max_candidates=SCAN_MAX_CANDIDATES)
        db.save_scan_result(current, result)
        data_date = result.get("data_date")
        db.set_data_status(current, data_date, "ok" if data_date == current else "stale")
        db.complete_scan(current, "done")
    except Exception as e:
        db.complete_scan(current, "error", error=str(e)[:300])
        raise

    cfg = load_config()
    if cfg.get("settings", {}).get("auto_scan_with_ai", True):
        db.start_phase(current, "ai")
        try:
            all_candidates = build_candidates_with_portfolio(result.get("all_candidates", []))
            ai_result = run_batch_ai_analysis(all_candidates, current)
            db.complete_ai(current, "done",
                            done_count=ai_result["analyzed"] + ai_result["skipped"],
                            total_count=len(all_candidates))
        except Exception:
            logger.exception("[scheduler] AI 批次分析失敗")
            db.complete_ai(current, "error", error="AI批次分析失敗")

    if db.load_portfolio():
        db.start_phase(current, "trade")
        try:
            trade_result = morning_scan(max_candidates=SCAN_MAX_CANDIDATES)
            summary = auto_portfolio_summary()
            db.append_equity({
                "date":           current,
                "equity":         summary["total_value"],
                "cash":           summary["cash"],
                "position_value": summary["position_value"],
            })
            db.complete_trade(current, "done", summary={
                "buy_count":  trade_result.get("buy_count"),
                "sell_count": trade_result.get("sell_count"),
                "errors":     trade_result.get("errors", []),
            })
        except Exception:
            logger.exception("[scheduler] 早盤掃描失敗")
            db.complete_trade(current, "error", error="早盤掃描失敗")

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
