"""
Taiwan stock data fetcher.
Sources:
  - twstock        → historical OHLCV (primary, direct TWSE/TPEX API)
  - yfinance       → historical OHLCV fallback + fundamental info (EPS, ROE, sector)
  - TWSE Open API  → stock list, P/E, P/B, dividend yield
  - Cache          → JSON files under /cache/ (TTL = cache_hours)
"""
import difflib
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
import yfinance as yf
import twstock

from backend.config import load_config
from backend.utils import TAIPEI, is_trading_day

CACHE_DIR = Path(__file__).parent.parent.parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

TWSE_BASE = "https://openapi.twse.com.tw/v1"
TWSE_BWIBBU = "https://www.twse.com.tw/exchangeReport/BWIBBU_d"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


# ── cache helpers ──────────────────────────────────────────────────────────────

def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def _read_cache(key: str) -> Optional[dict | list]:
    path = _cache_path(key)
    if not path.exists():
        return None
    cfg = load_config()
    ttl = cfg["settings"].get("cache_hours", 6) * 3600
    if time.time() - path.stat().st_mtime > ttl:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        path.unlink(missing_ok=True)
        return None


class _DateEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return super().default(obj)


def _write_cache(key: str, data) -> None:
    with open(_cache_path(key), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, cls=_DateEncoder)


# ── stock list ─────────────────────────────────────────────────────────────────

def last_trading_day_str() -> str:
    """Return the most recent trading day as YYYY-MM-DD (skips weekends + TW market holidays)."""
    d = datetime.now(TAIPEI).date()
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def get_latest_close(ticker: str) -> tuple[float, str]:
    """
    Single source of truth for the latest close price.

    Used by BOTH execute_trade (buy price) and auto_portfolio_summary
    (current price), so buy price == display price at the moment of purchase.

    Cache key includes the trading day → auto-invalidates each new day.
    Falls back to yesterday when today's close isn't published yet.
    """
    ltd = last_trading_day_str()
    cache_key = f"close_{ticker}_{ltd}"
    cached = _read_cache(cache_key)
    if cached:
        # Discard if the price date is more than 5 calendar days old —
        # means the cache was populated before the data source had today's data.
        gap = (datetime.today().date() - datetime.strptime(cached["date"], "%Y-%m-%d").date())
        if gap.days <= 5:
            return cached["price"], cached["date"]

    df = get_stock_history(ticker, 10)
    if df.empty:
        raise ValueError(f"無法取得 {ticker} 的收盤價")

    price    = float(df["Close"].iloc[-1])
    date_str = str(df.index[-1])[:10]
    _write_cache(cache_key, {"price": price, "date": date_str})
    return price, date_str


def get_top100_stocks() -> list[dict]:
    """Return top-300 Taiwan stocks sorted by daily 張數 (lots traded)."""
    # Use date-keyed cache so it auto-invalidates on each new trading day
    cache_key = f"top100_{last_trading_day_str()}"
    cached = _read_cache(cache_key)
    if cached:
        return cached

    try:
        url = f"{TWSE_BASE}/exchangeReport/STOCK_DAY_ALL"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        raw = resp.json()

        stocks = []
        for item in raw:
            try:
                shares = float(str(item.get("TradeVolume", "0")).replace(",", ""))
                lots = shares / 1000  # 張數 = 股數 / 1000
                close_str = str(item.get("ClosingPrice", "0")).replace(",", "")
                close = float(close_str) if close_str not in ("", "--") else 0.0
                stocks.append({
                    "ticker": item["Code"],
                    "name": item["Name"],
                    "close": close,
                    "volume": shares,
                    "lots": round(lots, 0),           # 張數
                    "trade_value": float(str(item.get("TradeValue", "0")).replace(",", "")),
                })
            except (ValueError, KeyError):
                continue

        # Sort by 張數 (lots traded) descending → top 300
        stocks.sort(key=lambda x: x["lots"], reverse=True)
        top300 = stocks[:300]
        _write_cache(cache_key, top300)
        return top300

    except Exception as e:
        print(f"[fetcher] top300 error: {e}")
        return _fallback_stock_list()


def _load_company_name_map() -> dict[str, str]:
    """抓取台股（上市＋上櫃）公司簡稱對照表，例如 2330 → 台積電。

    用公司簡稱（而非 yfinance 的英文 longName）才能讓 SearXNG 搜尋到較多中文新聞結果。
    """
    cache_key = f"company_names_{datetime.today().strftime('%Y-%m')}"
    cached = _read_cache(cache_key)
    if cached:
        return cached

    name_map = {}
    sources = [
        (f"{TWSE_BASE}/opendata/t187ap03_L", "公司代號", "公司簡稱"),
        ("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O", "SecuritiesCompanyCode", "CompanyAbbreviation"),
    ]
    for url, code_key, name_key in sources:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            for item in resp.json():
                code, name = item.get(code_key), item.get(name_key)
                if code and name:
                    name_map[code] = name
        except Exception as e:
            print(f"[fetcher] company name list error ({url}): {e}")

    # 補上 ETF 等不在公司基本資料裡的代號（來自每日成交資料，含中文名稱）
    try:
        resp = requests.get(f"{TWSE_BASE}/exchangeReport/STOCK_DAY_ALL", headers=HEADERS, timeout=15)
        resp.raise_for_status()
        for item in resp.json():
            code, name = item.get("Code"), item.get("Name")
            if code and name and code not in name_map:
                name_map[code] = name
    except Exception as e:
        print(f"[fetcher] STOCK_DAY_ALL name list error: {e}")

    if name_map:
        _write_cache(cache_key, name_map)
    return name_map


def get_company_name(ticker: str) -> Optional[str]:
    """回傳台股中文公司簡稱（例：2330 → 台積電），查無資料則回傳 None。"""
    return _load_company_name_map().get(ticker)


def search_tickers(query: str, limit: int = 5) -> list[dict]:
    """依公司名稱片段或股票代號，從代號對照表中找出候選 {ticker, name}（供聊天功能解析使用者提到的股票）。"""
    query = query.strip()
    if not query:
        return []
    name_map = _load_company_name_map()

    if query.upper() in name_map:
        return [{"ticker": query.upper(), "name": name_map[query.upper()]}]

    matches = [
        {"ticker": t, "name": n}
        for t, n in name_map.items()
        if query in n or n in query
    ]

    if not matches:
        # 找不到完全子字串匹配時的容錯：LLM 解析問題時偶爾會把繁體字打成簡體或形近字
        # （例如「英業達」→「英業达」），改用模糊比對抓回最相似的公司名稱。
        close = difflib.get_close_matches(query, name_map.values(), n=limit, cutoff=0.6)
        matches = [{"ticker": t, "name": n} for t, n in name_map.items() if n in close]

    # 完全相同或名稱較短（較精確）的排前面
    matches.sort(key=lambda m: (m["name"] != query, len(m["name"])))
    return matches[:limit]


def _fallback_stock_list() -> list[dict]:
    """Hardcoded fallback list of major Taiwan stocks."""
    major = [
        ("2330", "台積電"), ("2317", "鴻海"), ("2454", "聯發科"),
        ("2882", "國泰金"), ("6505", "台塑化"), ("2412", "中華電"),
        ("2308", "台達電"), ("2881", "富邦金"), ("2886", "兆豐金"),
        ("1301", "台塑"), ("1303", "南亞"), ("2002", "中鋼"),
        ("2303", "聯電"), ("3711", "日月光投控"), ("2891", "中信金"),
        ("2892", "第一金"), ("2884", "玉山金"), ("2880", "華南金"),
        ("5871", "中租-KY"), ("2885", "元大金"), ("2883", "開發金"),
        ("2887", "台新金"), ("2888", "新光金"), ("1326", "台化"),
        ("2379", "瑞昱"), ("3008", "大立光"), ("2395", "研華"),
        ("2382", "廣達"), ("2357", "華碩"), ("2376", "技嘉"),
        ("2327", "國巨"), ("4904", "遠傳"), ("4938", "和碩"),
        ("2408", "南亞科"), ("2301", "光寶科"), ("2345", "智邦"),
        ("2356", "英業達"), ("2371", "大同"), ("2449", "京元電子"),
        ("2360", "致茂"), ("3034", "聯詠"), ("2385", "群光"),
        ("3037", "欣興"), ("2353", "宏碁"), ("2352", "佳世達"),
        ("2344", "華邦電"), ("3045", "台灣大"), ("4958", "臻鼎-KY"),
        ("2337", "旺宏"), ("2439", "美律"),
    ]
    return [{"ticker": t, "name": n, "close": 0, "volume": 0, "trade_value": 0}
            for t, n in major]


# ── historical price ───────────────────────────────────────────────────────────

def get_stock_history(ticker: str, days: int = 365) -> pd.DataFrame:
    """Fetch OHLCV history. Primary: twstock (direct TWSE/TPEX). Fallback: yfinance."""
    # Cache key includes trading day so it auto-invalidates each new trading day.
    cache_key = f"hist_{ticker}_{days}_{last_trading_day_str()}"
    cached = _read_cache(cache_key)
    if cached:
        df = pd.DataFrame(cached)
        df["Date"] = pd.to_datetime(df["Date"])
        df.set_index("Date", inplace=True)
        # Discard cache if the newest data is more than 5 calendar days old —
        # means the cache was populated before the source had today's data.
        if not df.empty:
            gap = (datetime.today().date() - df.index[-1].date())
            if gap.days >= 5:
                cached = None
        if cached is not None:
            return df

    df = _twstock_history(ticker, days)
    if df.empty:
        df = _yf_history(ticker + ".TW", days)
    if df.empty:
        df = _yf_history(ticker + ".TWO", days)
    if df.empty:
        return pd.DataFrame()

    _write_cache(cache_key, df.reset_index().to_dict(orient="records"))
    return df


def _twstock_history(ticker: str, days: int) -> pd.DataFrame:
    """Download OHLCV via twstock (official TWSE/TPEX API). Auto-selects exchange."""
    try:
        start = datetime.today() - timedelta(days=days + 35)  # extra buffer for weekends
        s = twstock.Stock(ticker)
        s.fetch_from(start.year, start.month)

        if not s.date or not s.close:
            return pd.DataFrame()

        df = pd.DataFrame({
            "Open":   s.open,
            "High":   s.high,
            "Low":    s.low,
            "Close":  s.close,
            "Volume": s.capacity,
        }, index=pd.DatetimeIndex(s.date, name="Date"))

        df.index = df.index.tz_localize(None)
        df = df.apply(pd.to_numeric, errors="coerce")
        df.dropna(subset=["Close"], inplace=True)
        df = df.tail(days)

        # Reject stale data: if last date is more than 10 calendar days old,
        # fall through to yfinance which has more up-to-date data
        if not df.empty:
            last_date = df.index[-1].to_pydatetime().replace(tzinfo=None)
            if (datetime.today() - last_date).days > 10:
                print(f"[fetcher] twstock data for {ticker} is stale (last: {last_date.date()}), trying yfinance")
                return pd.DataFrame()

        return df
    except Exception as e:
        print(f"[fetcher] twstock error for {ticker}: {e}")
        return pd.DataFrame()


def _yf_history(yf_ticker: str, days: int) -> pd.DataFrame:
    """Download history via yfinance Ticker.history() — works with v1.x."""
    try:
        t = yf.Ticker(yf_ticker)
        period = f"{days + 60}d"
        df = t.history(period=period)

        if df.empty:
            return pd.DataFrame()

        # Flatten MultiIndex columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Drop dividend / split columns; keep OHLCV
        keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        df = df[keep].copy()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df.index.name = "Date"
        df.dropna(subset=["Close"], inplace=True)
        return df.tail(days)

    except Exception as e:
        print(f"[fetcher] history error for {yf_ticker}: {e}")
        return pd.DataFrame()


# ── fundamental data ───────────────────────────────────────────────────────────

def get_fundamental(ticker: str) -> dict:
    """Fetch P/E, P/B, dividend yield from TWSE BWIBBU endpoint."""
    # 以週為 TTL：同一週內不重抓（基本面每週更新一次已足夠）
    week_str  = datetime.today().strftime("%Y-W%W")
    cache_key = f"fund_{ticker}_{week_str}"
    cached = _read_cache(cache_key)
    if cached:
        return cached

    data = {"ticker": ticker, "pe": None, "pb": None, "div_yield": None,
            "eps": None, "roe": None, "name": get_company_name(ticker)}

    try:
        date_str = datetime.today().strftime("%Y%m%d")
        url = (f"{TWSE_BWIBBU}?response=json"
               f"&date={date_str}&stockNo={ticker}&selectType=ALL")
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        raw = resp.json()

        rows = raw.get("data", [])
        if rows:
            row = rows[-1]
            # TWSE columns: 0=date, 1=yield, 2=dividend, 3=PE, 4=PB
            data["div_yield"] = _safe_float(row[1])
            data["pe"] = _safe_float(row[3])
            data["pb"] = _safe_float(row[4])

    except Exception as e:
        print(f"[fetcher] fundamental error for {ticker}: {e}")

    # Supplement with yfinance info
    try:
        info = yf.Ticker(ticker + ".TW").info
        if not data["eps"]:
            data["eps"] = info.get("trailingEps")
        if not data["roe"]:
            roe_raw = info.get("returnOnEquity")
            data["roe"] = round(roe_raw * 100, 2) if roe_raw else None
        if not data["pe"]:
            data["pe"] = info.get("trailingPE")
        data["market_cap"] = info.get("marketCap")
        if not data["name"]:
            data["name"] = info.get("longName", ticker)
        data["sector"] = info.get("sector", "")
        data["industry"] = info.get("industry", "")
        data["description"] = info.get("longBusinessSummary", "")[:500]
    except Exception:
        pass

    if not data["name"]:
        data["name"] = ticker

    _write_cache(cache_key, data)
    return data


def _safe_float(val) -> Optional[float]:
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return None
