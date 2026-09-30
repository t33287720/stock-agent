"""
背景排程：容器啟動時立即檢查一次，之後每小時檢查資料是否有新交易日。
有新資料時自動執行「今日訊號掃描」並存入 DB，視設定對候選股做批次 AI 分析。
"""
import asyncio
import logging

from backend.config import load_config
from backend.control.data.fetcher import last_trading_day_str
from backend.db import portfolio_db as db
from backend.control.strategy.ai_batch import run_batch_ai_analysis
from backend.control.strategy.scanner import scan_today

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 3600
SCAN_MAX_CANDIDATES = 150


def run_scan_cycle() -> None:
    """每小時都實際執行一次今日訊號掃描（股價多半命中本地快取，成本低），
    直接以「抓到的資料日期（data_date）」跟上次已完整處理過的資料日期比對，
    不同才代表出現新的收盤資料，才觸發 AI 批次分析。

    不能用日曆（last_trading_day_str()）判斷「今天掃過了沒」：凌晨（開盤前）
    執行時，日曆上的今天已經算「run_date」，但抓到的其實還是前一個交易日的
    資料；若只記錄「今天已經掃過」，同一天內即使資料後來更新了，也會被誤判
    成「已完成」而永遠不再重新掃描。改成比對資料本身的日期，不管什麼時間點
    執行、抓到的是哪一天的資料，只要跟上次處理過的不同就會重新觸發。

    scan／data 這兩個狀態記在 run_date（執行當下的日曆日）底下，回答的是
    「今天有沒有檢查、检查結果新不新鮮」；但 AI 的完成狀態記在
    data_date（這批資料真正代表的交易日）底下，回答的是「這個交易日的資料
    有沒有分析完」。兩者一旦混用（例如凌晨掃到舊資料時，把 AI 結果標記在
    還沒有資料的「今天」），系統執行狀況列表就會出現資料=stale（紅）但
    AI=done（綠）的矛盾畫面。
    """
    run_date = last_trading_day_str()
    state = db.get_scan_state()

    db.start_phase(run_date, "scan")
    try:
        result = scan_today(max_candidates=SCAN_MAX_CANDIDATES)
        data_date = result.get("data_date")
        db.set_data_status(run_date, data_date, "ok" if data_date == run_date else "stale")
        db.complete_scan(run_date, "done")
    except Exception as e:
        db.complete_scan(run_date, "error", error=str(e)[:300])
        raise

    if not data_date or state.get("last_scan_date") == data_date:
        db.update_scan_state()
        return

    logger.info("[scheduler] 偵測到新資料 %s（先前已處理到 %s），開始 AI 分析",
                data_date, state.get("last_scan_date"))

    # 以下都用 data_date 當 key，代表「這是哪一天的收盤資料」，而不是
    # run_date（我們在哪一天執行了這段程式碼），這樣「今日訊號掃描」頁與
    # 「系統執行狀況」列表才會把 AI 結果正確歸在它真正對應的交易日。
    db.save_scan_result(data_date, result)

    cfg = load_config()
    if cfg.get("settings", {}).get("auto_scan_with_ai", True):
        db.start_phase(data_date, "ai")
        try:
            all_candidates = result.get("all_candidates", [])
            ai_result = run_batch_ai_analysis(all_candidates, data_date)
            db.complete_ai(data_date, "done",
                            done_count=ai_result["analyzed"] + ai_result["skipped"],
                            total_count=len(all_candidates))
        except Exception:
            logger.exception("[scheduler] AI 批次分析失敗")
            db.complete_ai(data_date, "error", error="AI批次分析失敗")

    db.update_scan_state(data_date)
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
