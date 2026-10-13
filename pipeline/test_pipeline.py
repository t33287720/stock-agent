"""pipeline 的基本測試（不連外網）。執行：cd pipeline && python -m pytest test_pipeline.py"""
from datetime import date

import numpy as np
import pandas as pd

import indicators
import sources


def test_tpex_prices_strips_fields_and_keeps_only_stocks(monkeypatch):
    """櫃買中心欄位名稱有時帶空白；只收一般股票，ETF、權證、沒成交的不收。"""
    payload = {"tables": [{
        "fields": ["代號", "名稱", "收盤 ", "漲跌", "開盤 ", "最高 ", "最低", "成交股數  "],
        "data": [["6488", "環球晶 ", "866.00", "+78", "866.00", "866.00", "866.00", "2,738,000"],
                 ["00679B", "元大美債20年", "28.1", "0", "28", "28.2", "27.9", "1,000"],
                 ["1234", "沒成交", "--", "0", "--", "--", "--", "0"]],
    }]}
    monkeypatch.setattr(sources, "_get_json", lambda url: payload)
    rows = sources.tpex_prices(date(2026, 5, 26))
    assert rows == [{"date": "2026-05-26", "code": "6488", "name": "環球晶", "market": "上櫃",
                     "open": 866.0, "high": 866.0, "low": 866.0, "close": 866.0, "volume": 2738000.0}]


def test_tpex_uses_regular_session_quotes(monkeypatch):
    """要用「不含盤後定價」的行情，成交量口徑才跟上市一致。"""
    urls = []
    monkeypatch.setattr(sources, "_get_json", lambda url: urls.append(url) or {"tables": []})
    sources.tpex_prices(date(2026, 5, 26))
    assert "/afterTrading/otc?" in urls[0]


def test_kd_matches_taiwan_convention():
    """台股 KD：9 日 RSV，K = 2/3 前K + 1/3 RSV，D = 2/3 前D + 1/3 K，起始 50。"""
    rng = np.random.default_rng(0)
    close = pd.Series(100 + np.cumsum(rng.normal(0, 1, 30)))
    high, low = close + 1, close - 1
    k, d = indicators._kd(high, low, close)
    pk = pd_ = 50.0
    for i in range(len(close)):
        lo, hi = low[max(0, i - 8):i + 1].min(), high[max(0, i - 8):i + 1].max()
        rsv = min(100, max(0, (close[i] - lo) / (hi - lo + 1e-9) * 100))
        pk = pk * 2 / 3 + rsv / 3
        pd_ = pd_ * 2 / 3 + pk / 3
        assert abs(k[i] - pk) < 1e-9 and abs(d[i] - pd_) < 1e-9


def test_latest_indicators_skips_stocks_without_trade_today():
    days = [f"2026-09-{d:02d}" for d in range(1, 31) if date(2026, 9, d).weekday() < 5]
    rows = [{"date": day, "code": code, "name": code, "market": "上市", "open": 10 + i, "high": 11 + i,
             "low": 9 + i, "close": 10 + i, "volume": 1000 * (i + 1)}
            for code in ("1101", "2330") for i, day in enumerate(days)
            if not (code == "1101" and day == days[-1])]   # 1101 最後一天沒成交
    out = indicators.latest_indicators(pd.DataFrame(rows))
    assert list(out["code"]) == ["2330"]
    assert out.iloc[0]["close"] == 10 + len(days) - 1


def test_market_summary_counts_breadth_and_limits():
    def row(day, code, close, vol=1000):
        return {"date": day, "code": code, "name": code, "market": "上市", "open": close, "high": close,
                "low": close, "close": close, "volume": vol}
    rows = [row("2026-09-01", c, 100) for c in ("A", "B", "C", "D", "E")]
    rows += [row("2026-09-02", "A", 110), row("2026-09-02", "B", 90), row("2026-09-02", "C", 100),
             row("2026-09-02", "D", 101), row("2026-09-02", "N", 50)]   # N 新上市、E 停牌
    m = indicators.market_summary(pd.DataFrame(rows))
    assert (m["up"], m["down"], m["flat"]) == (2, 1, 1)
    assert (m["limit_up"], m["limit_down"]) == (1, 1)
    assert m["amount"] == 110000 + 90000 + 100000 + 101000 + 50000
    assert m["amount_ratio"] == round(451000 / 500000, 2)


def test_market_summary_needs_two_days():
    df = pd.DataFrame([{"date": "2026-09-01", "code": "A", "name": "A", "market": "上市",
                        "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}])
    assert indicators.market_summary(df) is None
