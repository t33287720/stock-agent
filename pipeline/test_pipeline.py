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


def _history(code, n_days):
    days = pd.bdate_range("2026-06-01", periods=n_days).strftime("%Y-%m-%d")
    return [{"date": day, "code": code, "name": code, "market": "上市", "open": 10 + i, "high": 11 + i,
             "low": 9 + i, "close": 10 + i + 0.123, "volume": 1000 * (i + 1)}
            for i, day in enumerate(days)]


def test_spark_is_last_60_closes_rounded():
    out = indicators.latest_indicators(pd.DataFrame(_history("2330", 80)))
    spark = out.iloc[0]["spark"]
    assert len(spark) == 60
    assert spark[-1] == round(out.iloc[0]["close"], 2)
    assert spark[0] == round(10 + 20 + 0.123, 2)


def test_spark_shorter_when_history_is_short():
    out = indicators.latest_indicators(pd.DataFrame(_history("2330", 12)))
    assert len(out.iloc[0]["spark"]) == 12


def test_vols_align_with_spark_in_lots():
    """回測用的成交量序列要和 spark 同長度、單位為張（股數 ÷ 1000）。"""
    out = indicators.latest_indicators(pd.DataFrame(_history("2330", 80)))
    row = out.iloc[0]
    assert len(row["vols"]) == len(row["spark"]) == 60
    assert row["vols"][-1] == 80          # 最後一天成交 80,000 股 = 80 張
    assert row["vols"][-1] == round(row["lots"])


def test_vols_shorter_when_history_is_short():
    out = indicators.latest_indicators(pd.DataFrame(_history("2330", 12)))
    assert len(out.iloc[0]["vols"]) == 12
