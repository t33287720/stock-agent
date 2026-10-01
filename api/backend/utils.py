"""
Shared utilities: Taiwan trading calendar, timezone helpers, number parsing.

休市日優先採用證交所 OpenAPI 公告（每天最多抓一次、存成本機快取），
抓不到時才退回下方手動維護的 TW_HOLIDAYS。
"""
import json
import logging
import math
import threading
import time
from datetime import date, datetime

import pytz
import requests

from backend.cache import CACHE_DIR

TAIPEI = pytz.timezone("Asia/Taipei")

logger = logging.getLogger(__name__)

# Fallback：證交所 API 無法連線、且本機快取沒有該年度資料時才使用。
# Source: https://www.twse.com.tw/zh/trading/holiday.html
# 只列出「平日但不開盤」的日子（週末本來就不交易）。
TW_HOLIDAYS: set[str] = {
    # ── 2025 ──────────────────────────────────────────────────
    "2025-01-01",                                           # New Year
    "2025-01-27", "2025-01-28", "2025-01-29",              # Lunar New Year
    "2025-01-30", "2025-01-31", "2025-02-03",
    "2025-02-28",                                           # 228 Memorial
    "2025-04-03", "2025-04-04",                             # Children's / Tomb-Sweeping
    "2025-05-01",                                           # Labor Day
    "2025-05-30", "2025-05-31",                             # Dragon Boat
    "2025-10-06", "2025-10-07",                             # Mid-Autumn
    "2025-10-10",                                           # National Day
    # ── 2026（依證交所 115 年市場開休市日期表）────────────────
    "2026-01-01",                                           # 開國紀念日
    "2026-02-12", "2026-02-13",                             # 春節前無交易（僅結算交割）
    "2026-02-16", "2026-02-17", "2026-02-18",              # 農曆除夕及春節
    "2026-02-19", "2026-02-20",
    "2026-02-27",                                           # 228 補假
    "2026-04-03", "2026-04-06",                             # 兒童節 / 清明補假
    "2026-05-01",                                           # 勞動節
    "2026-06-19",                                           # 端午節
    "2026-09-25",                                           # 中秋節
    "2026-09-28",                                           # 教師節
    "2026-10-09",                                           # 國慶補假
    "2026-10-26",                                           # 光復節補假
    "2026-12-25",                                           # 行憲紀念日
}

_TWSE_HOLIDAY_URL = "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule"
_HOLIDAY_CACHE = CACHE_DIR / "twse_holidays.json"
_HOLIDAY_REFRESH_SECONDS = 86400      # 成功抓到後一天內不重抓
_HOLIDAY_RETRY_SECONDS = 3600         # 抓失敗後一小時內不重試，避免每次判斷都卡在逾時

_holiday_lock = threading.Lock()
_holidays_by_year: dict[str, list[str]] | None = None
_holidays_next_refresh = 0.0


def _fetch_twse_holidays() -> dict[str, list[str]]:
    """抓證交所公告的當年度開休市日期表，回傳 {"2026": ["2026-01-01", ...]}。

    表裡同時列了「開始交易日」「最後交易日」這類提醒，名稱含「交易日」者是有開盤的，
    其餘（含「市場無交易，僅辦理結算交割作業」）都視為休市。
    """
    resp = requests.get(_TWSE_HOLIDAY_URL, timeout=10)
    resp.raise_for_status()
    out: dict[str, list[str]] = {}
    for row in resp.json():
        name, roc = row.get("Name", ""), str(row.get("Date", ""))
        if "交易日" in name or len(roc) != 7:
            continue
        ds = f"{int(roc[:3]) + 1911}-{roc[3:5]}-{roc[5:7]}"
        out.setdefault(ds[:4], []).append(ds)
    return out


def _twse_holidays() -> dict[str, list[str]]:
    global _holidays_by_year, _holidays_next_refresh
    with _holiday_lock:
        if _holidays_by_year is None:
            try:
                _holidays_by_year = json.loads(_HOLIDAY_CACHE.read_text(encoding="utf-8"))
                if time.time() - _HOLIDAY_CACHE.stat().st_mtime < _HOLIDAY_REFRESH_SECONDS:
                    _holidays_next_refresh = _HOLIDAY_CACHE.stat().st_mtime + _HOLIDAY_REFRESH_SECONDS
            except (OSError, ValueError):
                _holidays_by_year = {}

        if time.time() >= _holidays_next_refresh:
            try:
                fetched = _fetch_twse_holidays()
                if fetched:
                    _holidays_by_year = {**_holidays_by_year, **fetched}
                    _HOLIDAY_CACHE.parent.mkdir(parents=True, exist_ok=True)
                    _HOLIDAY_CACHE.write_text(json.dumps(_holidays_by_year), encoding="utf-8")
                _holidays_next_refresh = time.time() + _HOLIDAY_REFRESH_SECONDS
            except Exception as e:
                logger.warning("[utils] 抓證交所休市日失敗，改用快取/內建清單: %s", e)
                _holidays_next_refresh = time.time() + _HOLIDAY_RETRY_SECONDS

        return _holidays_by_year


def is_trading_day(d: date | datetime | None = None) -> bool:
    """Return True if d is a Taiwan stock exchange trading day."""
    if d is None:
        d = datetime.now(TAIPEI).date()
    if isinstance(d, datetime):
        d = d.date()
    if d.weekday() >= 5:           # Sat / Sun
        return False
    ds = d.strftime("%Y-%m-%d")
    official = _twse_holidays().get(ds[:4])
    if official:
        return ds not in official
    return ds not in TW_HOLIDAYS


def to_float(val, default: float | None = None) -> float | None:
    """'1,234.5' / 1234.5 / numpy 數值 → float；None、NaN、'--'、'N/A' 等無法轉換的值回傳 default。"""
    if val is None:
        return default
    try:
        f = float(str(val).replace(",", "")) if isinstance(val, str) else float(val)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(f) else f
