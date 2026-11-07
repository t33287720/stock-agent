"""從證交所（上市）與櫃買中心（上櫃）抓每日全市場資料。

每個函式一次拿到「某一天、整個市場」的資料，所以每天只需要打幾次 API。
只保留一般股票（4 位數代號、不以 0 開頭），ETF、權證等不收。
"""
import re
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
    fields = [f.strip() for f in fields]  # 櫃買中心的欄位名稱有時帶前後空白
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
    """上櫃股票某一天的開高低收量。沒有資料時回傳空 list。

    用「不含定價」版本：成交股數只算一般交易時段，跟上市 MI_INDEX 口徑一致。
    （dailyQuotes 會把 14:30 盤後定價交易也算進去，鎖漲停的日子成交量可能多好幾倍，量比會失真。）
    """
    data = _get_json("https://www.tpex.org.tw/www/zh-tw/afterTrading/otc"
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


def _find(fields: list[str], *keywords: str) -> int | None:
    """欄位名稱同時包含所有關鍵字的第一個欄位位置；找不到回傳 None。"""
    for i, f in enumerate(fields):
        if all(k in f for k in keywords):
            return i
    return None


def twse_institutional(day: date) -> dict[str, list[float]]:
    """上市股票某一天三大法人買賣超（股）：{代號: [外資, 投信, 自營商]}。沒資料或格式不符時回傳空 dict。"""
    data = _get_json("https://www.twse.com.tw/rwd/zh/fund/T86"
                     f"?date={day:%Y%m%d}&selectType=ALL&response=json")
    if data.get("stat") != "OK":
        return {}
    fields = [f.strip() for f in data.get("fields", [])]
    idx = [_find(fields, "證券代號"), _find(fields, "外", "買賣超"),
           _find(fields, "投信", "買賣超"), _find(fields, "自營商買賣超")]
    if None in idx:
        return {}
    out = {}
    for r in data.get("data", []):
        code = r[idx[0]].strip()
        vals = [_num(r[i]) for i in idx[1:]]
        if is_stock(code) and None not in vals:
            out[code] = vals
    return out


def tpex_institutional(day: date) -> dict[str, list[float]]:
    """上櫃股票某一天三大法人買賣超（股）。openapi 只提供最新一天，資料日期不是 day 時回傳空 dict。"""
    data = _get_json("https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading")
    roc_day = f"{day.year - 1911}{day:%m%d}"
    out = {}
    for item in data:
        if item.get("Date") != roc_day:
            continue
        keys = list(item)

        def pick(*kw):
            k = next((k for k in keys if all(w.lower() in k.lower() for w in kw)), None)
            return _num(item.get(k)) if k else None
        vals = [pick("foreign", "diff"), pick("investmenttrust", "diff"), pick("dealers", "diff")]
        code = str(item.get("SecuritiesCompanyCode", "")).strip()
        if is_stock(code) and None not in vals:
            out[code] = vals
    return out


def roc_to_iso(text) -> str | None:
    """民國日期 '115年10月28日'、'1151028'、'115/10/28' → '2026-10-28'；無法解析回傳 None。"""
    digits = re.findall(r"\d+", str(text))
    try:
        if len(digits) >= 3:
            y, m, d = (int(x) for x in digits[:3])
        elif len(digits) == 1 and len(digits[0]) in (6, 7):
            s = digits[0]
            y, m, d = int(s[:-4]), int(s[-4:-2]), int(s[-2:])
        else:
            return None
        return date(y + 1911 if y < 1911 else y, m, d).isoformat()
    except ValueError:
        return None


def _exdiv_kind(text) -> str | None:
    text = str(text)
    if "權" in text and "息" in text:
        return "權息"
    return "息" if "息" in text else "權" if "權" in text else None


def twse_exdiv() -> dict[str, dict]:
    """上市除權息預告：{代號: {date, kind, amount}}；amount 為「權值+息值」（元／股）。沒資料或格式不符時回傳空 dict。"""
    data = _get_json("https://www.twse.com.tw/rwd/zh/exRight/TWT48U?response=json")
    fields = [f.strip() for f in data.get("fields", [])]
    idx = [_find(fields, "資料日期"), _find(fields, "股票代號"), _find(fields, "權/息"), _find(fields, "權值")]
    if None in idx[:3]:
        return {}
    out = {}
    for r in data.get("data", []):
        code, iso, kind = str(r[idx[1]]).strip(), roc_to_iso(r[idx[0]]), _exdiv_kind(r[idx[2]])
        if is_stock(code) and iso and kind:
            out[code] = {"date": iso, "kind": kind, "amount": _num(r[idx[3]]) if idx[3] is not None else None}
    return out


def tpex_exdiv() -> dict[str, dict]:
    """上櫃除權息預告：以欄位名稱關鍵字比對，格式不符時回傳空 dict。"""
    data = _get_json("https://www.tpex.org.tw/openapi/v1/tpex_exright_prepost")
    out = {}
    for item in data if isinstance(data, list) else []:
        def key(*kw):
            return next((k for k in item if all(w.lower() in k.lower() for w in kw)), None)
        k_code, k_date = key("code"), key("date")
        k_kind = next((k for k in item if _exdiv_kind(item[k])), None)
        k_amt = key("dividend") or key("value")
        if not (k_code and k_date and k_kind):
            continue
        code, iso, kind = str(item[k_code]).strip(), roc_to_iso(item[k_date]), _exdiv_kind(item[k_kind])
        if is_stock(code) and iso and kind:
            out[code] = {"date": iso, "kind": kind, "amount": _num(item.get(k_amt)) if k_amt else None}
    return out
