"""從證交所（上市）與櫃買中心（上櫃）抓每日全市場資料。

每個函式一次拿到「某一天、整個市場」的資料，所以每天只需要打幾次 API。
只保留一般股票（4 位數代號、不以 0 開頭），ETF、權證等不收。
"""
import time
from datetime import date

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _get_json(url: str, tries: int = 5):
    """GET 並解析 JSON；失敗會重試（櫃買中心從國外連線偶爾會傳到一半斷線）。"""
    for attempt in range(1, tries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=60)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as e:
            if attempt == tries:
                raise RuntimeError(f"連線失敗（已重試 {tries} 次）：{url}\n{e}") from e
            time.sleep(5 * attempt)


def _num(value) -> float | None:
    """'1,234.5' → 1234.5；'--'、'-'、'N/A'、空字串 → None。"""
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def is_stock(code: str) -> bool:
    return len(code) == 4 and code.isdigit() and code[0] != "0"


def _pick(fields: list[str], row: list, *names: str) -> list:
    return [row[fields.index(n)] for n in names]


def twse_prices(day: date) -> list[dict] | None:
    """上市股票某一天的開高低收量。休市或還沒公布時回傳 None。"""
    data = _get_json("https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
                     f"?date={day:%Y%m%d}&type=ALLBUT0999&response=json")
    if data.get("stat") != "OK":
        return None
    table = next((t for t in data.get("tables", []) if "證券代號" in (t.get("fields") or [])), None)
    if not table or not table.get("data"):
        return None

    rows = []
    for r in table["data"]:
        code, name, o, h, l, c, vol = _pick(table["fields"], r, "證券代號", "證券名稱",
                                            "開盤價", "最高價", "最低價", "收盤價", "成交股數")
        code = code.strip()
        if is_stock(code) and _num(c) is not None:  # 收盤價 '--' 代表當天沒成交
            rows.append({"date": day.isoformat(), "code": code, "name": name.strip(), "market": "上市",
                         "open": _num(o), "high": _num(h), "low": _num(l), "close": _num(c),
                         "volume": _num(vol)})
    return rows


def tpex_prices(day: date) -> list[dict]:
    """上櫃股票某一天的開高低收量。沒有資料時回傳空 list。"""
    data = _get_json("https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes"
                     f"?date={day:%Y/%m/%d}&type=EW&response=json")
    tables = data.get("tables") or []
    if not tables or not tables[0].get("data"):
        return []

    fields, rows = tables[0]["fields"], []
    for r in tables[0]["data"]:
        code, name, o, h, l, c, vol = _pick(fields, r, "代號", "名稱", "開盤", "最高", "最低", "收盤", "成交股數")
        code = code.strip()
        if is_stock(code) and _num(c) is not None:
            rows.append({"date": day.isoformat(), "code": code, "name": name.strip(), "market": "上櫃",
                         "open": _num(o), "high": _num(h), "low": _num(l), "close": _num(c),
                         "volume": _num(vol)})
    return rows


def twse_valuation(day: date) -> dict[str, dict]:
    """上市股票某一天的本益比、股價淨值比、殖利率。還沒公布時回傳空 dict。"""
    data = _get_json("https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d"
                     f"?date={day:%Y%m%d}&selectType=ALL&response=json")
    if data.get("stat") != "OK":
        return {}
    fields = data["fields"]
    out = {}
    for r in data.get("data", []):
        code, pe, pb, dy = _pick(fields, r, "證券代號", "本益比", "股價淨值比", "殖利率(%)")
        out[code.strip()] = {"pe": _num(pe), "pb": _num(pb), "yield": _num(dy)}
    return out


def tpex_valuation(day: date) -> dict[str, dict]:
    """上櫃股票最新一天的本益比、股價淨值比、殖利率；資料日期不是 day 時回傳空 dict。"""
    data = _get_json("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis")
    roc_day = f"{day.year - 1911}{day:%m%d}"
    out = {}
    for item in data:
        if item.get("Date") != roc_day:
            continue
        out[item["SecuritiesCompanyCode"].strip()] = {
            "pe": _num(item.get("PriceEarningRatio")),
            "pb": _num(item.get("PriceBookRatio")),
            "yield": _num(item.get("YieldRatio")),
        }
    return out
