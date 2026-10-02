"""資料庫層測試（需要 Postgres，沒有設定 DB_HOST 就略過）。用 2099 年的日期，跑完自己清掉。"""
from datetime import date

import pytest

from conftest import requires_db

pytestmark = requires_db

DAY = "2099-01-02"


@pytest.fixture
def db():
    from backend.db import portfolio_db
    portfolio_db.init_db()
    yield portfolio_db
    with portfolio_db._conn() as c, c.cursor() as cur:
        cur.execute("DELETE FROM scan_results WHERE scan_date >= '2099-01-01'")
        cur.execute("DELETE FROM stock_ai_results WHERE scan_date >= '2099-01-01'")
        cur.execute("DELETE FROM daily_prices WHERE trade_date >= '2099-01-01'")
        cur.execute("DELETE FROM daily_price_sync WHERE trade_date >= '2099-01-01'")


def test_init_db_is_idempotent(db):
    db.init_db()
    db.init_db()


def test_scan_results_exclude_all_candidates_on_request(db):
    db.save_scan_result(DAY, {"buy_candidates": [], "sell_candidates": [], "all_candidates": [{"ticker": "X"}]})
    assert "all_candidates" in db.get_latest_scan_result()
    light = db.get_latest_scan_result(include_all_candidates=False)
    assert "all_candidates" not in light and light["scan_date"] == DAY


def test_ai_progress_counts_only_successful_targets(db):
    """進度的分母是買賣候選；失敗的、不是對象的都不算完成。"""
    db.save_scan_result(DAY, {"buy_candidates": [{"ticker": "T5"}], "sell_candidates": [{"ticker": "T7"}, {"ticker": "T9"}],
                              "all_candidates": [{"ticker": f"T{i}"} for i in range(20)]})
    db.save_stock_ai_result("T5", "n", DAY, {"verdict": "偏多", "trace": [{"label": "a"}, {"label": "b"}]})
    db.save_stock_ai_result("T7", "n", DAY, {"verdict": "中性", "error": True, "trace": []})
    db.save_stock_ai_result("T0", "n", DAY, {"verdict": "偏空", "trace": []})
    scan_date, tickers = db.get_latest_scan_tickers()
    assert scan_date == DAY and sorted(tickers) == ["T5", "T7", "T9"]
    assert db.count_stock_ai_done(DAY, tickers) == 1


def test_ai_results_list_without_trace_and_trace_on_demand(db):
    """列表不帶 trace（每筆可能上百 KB），展開時才單獨抓。"""
    trace = [{"label": "延伸搜尋判斷", "prompt": "x" * 1000}]
    db.save_stock_ai_result("T5", "台積電", DAY, {"verdict": "偏多", "summary": "s", "trace": trace})
    row = db.get_stock_ai_results_for_date(DAY)["T5"]
    assert "trace" not in row and row["trace_steps"] == 1 and row["name"] == "台積電"
    assert db.get_stock_ai_trace("T5", DAY) == trace
    assert db.get_stock_ai_trace("NOPE", DAY) is None


def test_daily_prices_round_trip_and_upsert(db):
    rows = [(date(2099, 1, 2), "2330", 1.0, 2.0, 0.5, 1.5, 1000), (date(2099, 1, 5), "2330", 1.5, 2.5, 1.0, 2.0, 2000)]
    db.save_daily_prices(rows)
    db.save_daily_prices([(date(2099, 1, 5), "2330", 1.5, 2.5, 1.0, 2.2, 3000)])   # 同一天重抓會覆蓋
    db.mark_price_day_synced(date(2099, 1, 2), 2)
    db.mark_price_day_synced(date(2099, 1, 2), 3)
    got = db.get_daily_prices("2330", date(2099, 1, 1))
    assert [(r[0], r[4], r[5]) for r in got] == [(date(2099, 1, 2), 1.5, 1000), (date(2099, 1, 5), 2.2, 3000)]
    assert date(2099, 1, 2) in db.get_synced_price_days()


def test_connection_pool_recovers_from_failed_query(db):
    with pytest.raises(Exception):
        with db._conn() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM no_such_table")
    assert db.get_latest_scan_tickers() is None or isinstance(db.get_latest_scan_tickers(), tuple)
