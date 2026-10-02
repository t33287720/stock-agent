"""針對實際出過錯的地方寫的回歸測試，每個測試的說明寫了當初是什麼問題。"""
from datetime import date

import pandas as pd
import pytest

from conftest import fake_http


# ── 估值（本益比／淨值比／殖利率）────────────────────────────────────────────

BWIBBU_FIELDS = ["證券代號", "證券名稱", "收盤價", "殖利率(%)", "股利年度", "本益比", "股價淨值比", "財報年/季"]
BWIBBU_ROWS = [
    ["2330", "台積電", "2,510.00", "0.88", 114, "29.09", "10.12", "115/2"],
    ["9958", "世紀鋼", "92.00", "4.89", 114, "13.07", "1.93", "115/2"],
]


def test_valuation_reads_by_field_name_not_last_row(monkeypatch):
    """BWIBBU 帶 selectType=ALL 會回傳全市場，舊程式取最後一列（世紀鋼）又把欄位對錯，
    每支股票的本益比都變成 4.89、淨值比 114。"""
    from backend.control.data import fetcher
    monkeypatch.setattr(fetcher.requests, "get", fake_http({
        "BWIBBU_d": {"stat": "OK", "fields": BWIBBU_FIELDS, "data": BWIBBU_ROWS},
        "peratio_analysis": [{"SecuritiesCompanyCode": "6488", "PriceEarningRatio": "52.67",
                              "PriceBookRatio": "5.36", "YieldRatio": "0.71"}],
    }))
    v = fetcher.get_market_valuation()
    assert v["2330"] == {"pe": 29.09, "pb": 10.12, "div_yield": 0.88}
    assert v["9958"] == {"pe": 13.07, "pb": 1.93, "div_yield": 4.89}
    assert v["6488"] == {"pe": 52.67, "pb": 5.36, "div_yield": 0.71}  # 上櫃也要有


def test_valuation_falls_back_to_last_published_day(monkeypatch):
    """當天資料下午才公布：原本固定查今天，上午與假日全市場篩選都沒有本益比。"""
    from backend.control.data import fetcher
    asked = []

    def get(url, *a, **k):
        from conftest import FakeResponse
        if "BWIBBU_d" in url:
            asked.append(url.split("date=")[1][:8])
            if len(asked) == 1:  # 最新交易日還沒公布
                return FakeResponse({"stat": "很抱歉，沒有符合條件的資料!"})
            return FakeResponse({"stat": "OK", "fields": BWIBBU_FIELDS, "data": BWIBBU_ROWS})
        return FakeResponse([])

    monkeypatch.setattr(fetcher.requests, "get", get)
    monkeypatch.setattr(fetcher, "last_trading_day_str", lambda: "2026-10-02")
    v = fetcher.get_market_valuation()
    assert asked[:2] == ["20261002", "20261001"]
    assert v["2330"]["pe"] == 29.09
    assert fetcher._valuation_memo["is_latest"] is False  # 用的是前一天 → 30 分鐘後會再查


# ── 休市日 ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("day, trading", [
    ("2025-10-07", True),    # 內建清單曾把有開盤的 10/7 列成中秋連假
    ("2025-02-03", True),    # 春節後開始交易日，曾被誤列為休市
    ("2025-10-06", False),
    ("2025-12-25", False),   # 行憲紀念日（2025 年起放假）
    ("2026-02-17", False),   # 2026 春節（內建清單曾沿用 2025 的日期）
    ("2026-10-01", True),    # 曾被誤列為中秋
    ("2026-09-25", False),
    ("2026-10-03", False),   # 星期六
])
def test_builtin_holiday_calendar(day, trading):
    from backend.utils import is_trading_day
    assert is_trading_day(date.fromisoformat(day)) is trading


def test_official_holiday_api_is_parsed(monkeypatch):
    """證交所 API 的「開始交易日／最後交易日」是有開盤的，不能當休市。"""
    from backend import utils
    monkeypatch.setattr(utils, "_holidays_next_refresh", 0)
    monkeypatch.setattr(utils.requests, "get", fake_http({"holidaySchedule": [
        {"Name": "國曆新年開始交易日", "Date": "1150102"},
        {"Name": "市場無交易，僅辦理結算交割作業", "Date": "1150212"},
        {"Name": "中秋節", "Date": "1150925"},
    ]}))
    assert utils.is_trading_day(date(2026, 1, 2)) is True
    assert utils.is_trading_day(date(2026, 2, 12)) is False
    assert utils.is_trading_day(date(2026, 9, 25)) is False
    assert utils.is_trading_day(date(2026, 10, 1)) is True   # 官方表有該年資料時以官方為準


# ── 全市場每日行情（price_store）──────────────────────────────────────────────

def test_tpex_fields_are_stripped_and_warrants_dropped():
    """櫃買中心欄位名稱有時帶空白；權證等不需要的代號要濾掉。"""
    from backend.control.data import price_store
    fields = ["代號", "名稱", "收盤 ", "漲跌", "開盤 ", "最高 ", "最低", "成交股數  "]
    rows = [
        ["6488", "環球晶", "866.00", "+78", "866.00", "866.00", "866.00", "2,738,000"],
        ["00679B", "元大美債20年", "28.10", "0", "28.0", "28.2", "27.9", "1,000"],
        ["700001", "某權證", "1.00", "0", "1", "1", "1", "10"],
        ["1234", "沒成交", "--", "0", "--", "--", "--", "0"],
    ]
    out = price_store._rows(date(2026, 5, 26), fields, rows, ("代號", "開盤", "最高", "最低", "收盤", "成交股數"))
    assert [r[1] for r in out] == ["6488", "00679B"]
    assert out[0] == (date(2026, 5, 26), "6488", 866.0, 866.0, 866.0, 866.0, 2738000)


def _trading_days(start, end):
    from datetime import timedelta
    d, out = start, set()
    while d <= end:
        if d.weekday() < 5:
            out.add(d)
        d += timedelta(days=1)
    return out


@pytest.mark.parametrize("name, synced, days, has_prices, use_db", [
    ("完整涵蓋", (date(2025, 7, 1), date(2026, 10, 1)), 90, True, True),
    ("今天收盤還沒公布", (date(2025, 7, 1), date(2026, 9, 30)), 90, True, True),
    ("排程停了好幾天", (date(2025, 7, 1), date(2026, 9, 25)), 90, True, False),
    ("回補還沒到視窗起點", (date(2026, 6, 15), date(2026, 10, 1)), 90, True, False),
    ("365 天還不夠", (date(2026, 4, 1), date(2026, 10, 1)), 365, True, False),
    ("資料庫沒有這支股票", (date(2025, 7, 1), date(2026, 10, 1)), 90, False, False),
])
def test_price_store_coverage(monkeypatch, name, synced, days, has_prices, use_db):
    """資料庫沒涵蓋到的期間要退回逐支抓取，不能回傳不完整的歷史。"""
    from backend.control.data import price_store
    monkeypatch.setattr(price_store, "_today", lambda: date(2026, 10, 1))
    monkeypatch.setattr(price_store, "_coverage", None)
    monkeypatch.setattr(price_store.db, "get_synced_price_days", lambda: _trading_days(*synced))
    rows = [(date(2026, 9, 30), 1.0, 2.0, 0.5, 1.5, 1000)] if has_prices else []
    monkeypatch.setattr(price_store.db, "get_daily_prices", lambda t, start: rows)
    assert (price_store.history("2330", days) is not None) is use_db, name


def test_price_store_window_matches_twstock_fetch(monkeypatch):
    """起始日要跟原本 twstock 的抓法一樣（往前 days+35 天再推到月初），筆數才會相同。"""
    from backend.control.data import price_store
    monkeypatch.setattr(price_store, "_today", lambda: date(2026, 10, 1))
    assert price_store._window_start(90) == date(2026, 5, 1)
    assert price_store._window_start(365) == date(2025, 8, 1)


def test_get_stock_history_falls_back_when_db_errors(monkeypatch):
    from backend.control.data import fetcher

    def boom(*a):
        raise RuntimeError("db down")

    monkeypatch.setattr(fetcher.price_store, "history", boom)
    df = pd.DataFrame({"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0], "Volume": [1.0]},
                      index=pd.DatetimeIndex([pd.Timestamp("2026-09-30")], name="Date"))
    monkeypatch.setattr(fetcher, "_twstock_history", lambda t, d: df)
    assert fetcher.get_stock_history("2330", 90).equals(df)


# ── 其他 ────────────────────────────────────────────────────────────────────

def test_ai_batch_only_targets_buy_and_sell_candidates():
    """畫面只顯示買賣候選的 AI 結果，其他候選分析了也沒人看。"""
    from backend.control.strategy.scanner import ai_targets
    result = {
        "buy_candidates": [{"ticker": "T5"}],
        "sell_candidates": [{"ticker": "T7"}, {"ticker": "T99"}],
        "all_candidates": [{"ticker": f"T{i}", "technical": {"close": i}} for i in range(150)],
    }
    targets = ai_targets(result)
    assert [c["ticker"] for c in targets] == ["T5", "T7", "T99"]
    assert all("technical" in c for c in targets)


def test_config_cache_returns_independent_copies():
    from backend import config
    a = config.load_config()
    a["settings"]["llm_model"] = "改掉"
    assert config.load_config()["settings"]["llm_model"] != "改掉"
    a["settings"]["llm_model"] = "m2"
    config.save_config(a)
    assert config.load_config()["settings"]["llm_model"] == "m2"


@pytest.mark.parametrize("raw, expected", [
    ("1,234.5", 1234.5), (12, 12.0), ("--", None), ("N/A", None), (None, None), (float("nan"), None),
])
def test_to_float(raw, expected):
    from backend.utils import to_float
    assert to_float(raw) == expected
