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


def test_vol_ratio_is_today_over_prev_5_day_mean():
    """量比 = 今日量 ÷ 前 5 日平均量；歷史不足 6 天時為缺值。"""
    row = indicators.latest_indicators(pd.DataFrame(_history("2330", 80))).iloc[0]
    assert abs(row["vol_ratio"] - 80 / 77) < 1e-9   # 前 5 日 75..79 張，平均 77
    short = indicators.latest_indicators(pd.DataFrame(_history("2330", 5))).iloc[0]
    assert pd.isna(short["vol_ratio"])


def test_twse_institutional_parses_by_field_name(monkeypatch):
    payload = {"stat": "OK",
               "fields": ["證券代號", "證券名稱", "外陸資買賣超股數(不含外資自營商)", "投信買賣超股數", "自營商買賣超股數", "三大法人買賣超股數"],
               "data": [["2330", "台積電", "1,234,000", "-5,000", "10,000", "1,239,000"],
                        ["0050", "ETF", "1", "1", "1", "3"]]}
    monkeypatch.setattr(sources, "_get_json", lambda url: payload)
    assert sources.twse_institutional(date(2026, 10, 19)) == {"2330": [1234000.0, -5000.0, 10000.0]}


def test_institutional_5d_converts_to_lots_and_keeps_gaps():
    import build
    cache = {"2026-10-16": {"2330": [2000, -1000, 0]}, "2026-10-19": {"2330": [5000, 0, 1000]}}
    out = build.institutional_5d(cache, ["2026-10-16", "2026-10-17", "2026-10-19"])
    assert out == {"2330": [[2, -1, 0], None, [5, 0, 1]]}
