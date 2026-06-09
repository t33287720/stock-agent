"""
Shared utilities: Taiwan trading calendar, timezone helpers.
Update TW_HOLIDAYS annually with TWSE holiday schedule.
"""
from datetime import date, datetime, timedelta
import pytz

TAIPEI = pytz.timezone("Asia/Taipei")

# Taiwan Stock Exchange public holidays + compensatory days
# Source: https://www.twse.com.tw/en/holidaySchedule/holidaySchedule
# Note: 補假（compensatory days）are included when holidays fall on weekends.
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
    # ── 2026 ──────────────────────────────────────────────────
    "2026-01-01",                                           # New Year
    "2026-01-28", "2026-01-29", "2026-01-30",              # Lunar New Year
    "2026-01-31", "2026-02-02",
    "2026-02-27",                                           # 228 補假 (Feb 28 is Sat → Fri 27 off)
    "2026-04-03",                                           # Children's Day
    "2026-04-06",                                           # 清明補假 (Apr 4 Sat → Mon 6 off)
    "2026-05-01",                                           # Labor Day
    "2026-06-19",                                           # Dragon Boat
    "2026-09-29", "2026-09-30", "2026-10-01",              # Mid-Autumn
    "2026-10-09",                                           # 國慶補假 (Oct 10 Sat → Fri 9 off)
}


def is_trading_day(d: date | datetime | None = None) -> bool:
    """Return True if d is a Taiwan stock exchange trading day."""
    if d is None:
        d = datetime.now(TAIPEI).date()
    if isinstance(d, datetime):
        d = d.date()
    if d.weekday() >= 5:           # Sat / Sun
        return False
    return d.strftime("%Y-%m-%d") not in TW_HOLIDAYS


def get_trading_days(start: date, end: date) -> list[date]:
    """Return all trading days from start to end (inclusive)."""
    days, d = [], start
    while d <= end:
        if is_trading_day(d):
            days.append(d)
        d += timedelta(days=1)
    return days


def row_for_date(df, d: date):
    """Return the DataFrame row for a given date, or None."""
    if df is None or df.empty:
        return None
    try:
        dates = [ts.date() if hasattr(ts, "date") else ts for ts in df.index]
        for i, rd in enumerate(dates):
            if rd == d:
                return df.iloc[i]
    except Exception:
        pass
    return None


