"""
全市場每日行情存放區（資料表 daily_prices / daily_price_sync）。

原本個股歷史股價是逐支用 twstock 打證交所／櫃買中心（一支股票 9~18 次請求），
掃描 150 支股票一輪就是上千次，容易被證交所暫時封鎖。改成每個交易日只抓兩次
「全市場收盤行情」（上市 MI_INDEX + 上櫃 dailyQuotes）存進資料庫，個股歷史直接從
資料庫讀；資料庫還沒涵蓋到的期間或股票，fetcher.get_stock_history() 會退回原本的抓法。

做法跟 pipeline/sources.py 類似（那邊給 GitHub Pages 的選股 App 用），差別是這裡
也保留 ETF（今日訊號掃描的候選裡有 ETF），上櫃用不含盤後定價的行情。
"""
import logging
import threading
import time
from datetime import date, datetime, timedelta

import pandas as pd
import requests

from backend.db import portfolio_db as db
from backend.utils import TAIPEI, is_trading_day

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
PAUSE_SECONDS = 3          # 每抓完一天停一下：證交所對短時間大量請求會暫時封鎖
HISTORY_CALENDAR_DAYS = 430  # 回補多久：個股頁最長查 365 天，抓法會再往前推到該月 1 號（見 _window_start）
RECENT_DAYS = 3            # 掃描前先補最近幾個交易日，讓今天的收盤資料盡快進來

_sync_lock = threading.Lock()
_coverage: tuple[date | None, date | None] | None = None  # (連續涵蓋的最早日, 最新日)，同步後重算


# ── 抓資料 ────────────────────────────────────────────────────────────────────

def _get_json(url: str, tries: int = 5):
    """GET 並解析 JSON；失敗會重試（櫃買中心偶爾會傳到一半斷線）。"""
    for attempt in range(1, tries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=60)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError):
            if attempt == tries:
                raise
            time.sleep(5 * attempt)


def _num(value) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def _keep(code: str) -> bool:
    """一般股票（4 碼數字）與 ETF（00 開頭）；權證、特別股等不收。"""
    return (len(code) == 4 and code.isdigit()) or code.startswith("00")


def _rows(day: date, fields: list[str], data: list[list], names: tuple[str, ...]) -> list[tuple]:
    fields = [f.strip() for f in fields]  # 櫃買中心的欄位名稱有時帶前後空白
    idx = [fields.index(n) for n in names]
    out = []
    for r in data:
        code, o, h, l, c, vol = (r[i] for i in idx)
        code = code.strip()
        close = _num(c)
        if _keep(code) and close is not None:  # 收盤價 '--' 代表當天沒成交
            out.append((day, code, _num(o), _num(h), _num(l), close, int(_num(vol) or 0)))
    return out


def _fetch_twse(day: date) -> list[tuple] | None:
    """上市某一天的行情；休市或還沒公布回傳 None。"""
    data = _get_json("https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
                     f"?date={day:%Y%m%d}&type=ALLBUT0999&response=json")
    if data.get("stat") != "OK":
        return None
    table = next((t for t in data.get("tables", []) if "證券代號" in (t.get("fields") or [])), None)
    if not table or not table.get("data"):
        return None
    return _rows(day, table["fields"], table["data"],
                 ("證券代號", "開盤價", "最高價", "最低價", "收盤價", "成交股數"))


def _fetch_tpex(day: date) -> list[tuple]:
    """上櫃某一天的行情；沒有資料回傳空 list。

    用「不含定價」版本：成交股數只算一般交易時段，跟上市 MI_INDEX、原本 twstock 的口徑一致
    （dailyQuotes 會把 14:30 盤後定價交易也算進去，鎖漲停的日子成交量可能差好幾倍）。
    """
    data = _get_json("https://www.tpex.org.tw/www/zh-tw/afterTrading/otc"
                     f"?date={day:%Y/%m/%d}&type=EW&response=json")
    tables = data.get("tables") or []
    if not tables or not tables[0].get("data"):
        return []
    return _rows(day, tables[0]["fields"], tables[0]["data"],
                 ("代號", "開盤", "最高", "最低", "收盤", "成交股數"))


# ── 同步 ──────────────────────────────────────────────────────────────────────

def _today() -> date:
    return datetime.now(TAIPEI).date()


def _missing_days(limit: int | None) -> list[date]:
    """回補範圍內還沒同步過的平日，新的在前。

    刻意不用 is_trading_day() 過濾：內建的休市日清單可能有錯（例如曾把有開盤的日子列成連假），
    信任它會漏抓整天的資料。每個平日都問一次證交所，沒資料就記成休市，一年只多十幾次請求。
    """
    synced = db.get_synced_price_days()
    today = _today()
    days, d = [], today
    while d >= today - timedelta(days=HISTORY_CALENDAR_DAYS):
        if d.weekday() < 5 and d not in synced:
            days.append(d)
            if limit is not None and len(days) >= limit:
                break
        d -= timedelta(days=1)
    return days


def sync(limit: int | None = None, wait: bool = True) -> int:
    """抓還沒存的交易日（新的優先），回傳這次新存了幾天。

    limit=None 代表把整個回補範圍補齊（第一次約需 20~25 分鐘）。
    wait=False 時如果另一個同步正在跑就直接略過（那邊也是新的優先，今天的資料會先進來）。
    """
    global _coverage
    if not _sync_lock.acquire(blocking=wait):
        return 0
    stored = 0
    try:
        today = _today()
        for day in _missing_days(limit):
            twse = _fetch_twse(day)
            if twse is None:
                if day != today:
                    db.mark_price_day_synced(day, 0)  # 證交所沒有這天的資料：休市
                time.sleep(PAUSE_SECONDS)
                continue
            tpex = _fetch_tpex(day)
            if not tpex:
                # 上市有、上櫃還沒有：今天就等下一輪；過去的日子也先不標記，下次再試
                logger.warning("[price_store] %s 上櫃行情抓不到，稍後重試", day)
                time.sleep(PAUSE_SECONDS)
                continue
            db.save_daily_prices(twse + tpex)
            db.mark_price_day_synced(day, len(twse) + len(tpex))
            stored += 1
            time.sleep(PAUSE_SECONDS)
    finally:
        _coverage = None
        _sync_lock.release()
    if stored:
        logger.info("[price_store] 新存入 %d 個交易日的全市場行情", stored)
    return stored


def _get_coverage() -> tuple[date | None, date | None]:
    """(最早日, 最新日)：這段期間的每個平日都已經同步過（休市日也會記一筆 rows = 0）。"""
    global _coverage
    if _coverage is None:
        synced = db.get_synced_price_days()
        if not synced:
            _coverage = (None, None)
        else:
            latest = max(synced)
            earliest, d = latest, latest
            while d >= min(synced):
                if d.weekday() < 5:
                    if d not in synced:
                        break
                    earliest = d
                d -= timedelta(days=1)
            _coverage = (earliest, latest)
    return _coverage


def _previous_trading_day(d: date) -> date:
    d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def _window_start(days: int) -> date:
    """跟原本 twstock 抓法相同的起始日：往前 days+35 天，再推到該月 1 號。"""
    start = _today() - timedelta(days=days + 35)
    return start.replace(day=1)


# ── 讀資料 ────────────────────────────────────────────────────────────────────

def history(ticker: str, days: int) -> pd.DataFrame | None:
    """從資料庫讀個股最近 days 筆日 K（欄位同 fetcher.get_stock_history）。

    資料庫還沒涵蓋這段期間（例如剛開始回補、或排程停了好幾天），或資料庫裡沒有這支股票時
    回傳 None，讓呼叫端退回逐支抓取。
    """
    earliest, latest = _get_coverage()
    if earliest is None:
        return None
    start = _window_start(days)
    # 最新日最多只能落後一個交易日（今天收盤資料還沒公布時，最新的就是前一個交易日）
    if earliest > start or latest < _previous_trading_day(_today()):
        return None

    rows = db.get_daily_prices(ticker, start)
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").astype(float)
    return df.tail(days)
