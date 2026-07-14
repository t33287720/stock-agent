"""
PostgreSQL persistence layer for the unified auto_trade portfolio.

Tables
──────
portfolio_config  — single row: cash, initial_capital, per_stock_budget, dates
positions         — one row per open position (ticker PK)
trades            — append-only log of all buy/sell executions
equity_history    — daily equity snapshots (date PK, upserted)

All public functions return/accept the same dict format that auto_trade.py
previously read from JSON files, so the caller needs no format changes.
"""

import json
import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")


# ── Connection ─────────────────────────────────────────────────────────────────

def _db_cfg() -> dict:
    # Environment variables take precedence (set by docker-compose or .env)
    if os.environ.get("DB_HOST"):
        return {
            "host": os.environ["DB_HOST"],
            "port": int(os.environ.get("DB_PORT", "5432")),
            "name": os.environ.get("DB_NAME", "stockdb"),
            "user": os.environ.get("DB_USER", "stockuser"),
            "password": os.environ["DB_PASSWORD"],
        }
    # Fall back to settings.json "database" key (local dev outside docker)
    cfg_path = Path(__file__).parent.parent.parent / "config" / "settings.json"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg["database"]


@contextmanager
def _conn():
    cfg = _db_cfg()
    c = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        dbname=cfg["name"], user=cfg["user"], password=cfg["password"],
    )
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


# ── Schema creation ────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create all tables (idempotent)."""
    ddl = """
    CREATE TABLE IF NOT EXISTS portfolio_config (
        id                INTEGER PRIMARY KEY DEFAULT 1,
        initial_capital   NUMERIC(15,2) NOT NULL,
        per_stock_budget  NUMERIC(15,2) NOT NULL DEFAULT 10000,
        cash              NUMERIC(15,2) NOT NULL,
        started_at        DATE NOT NULL,
        last_updated      TIMESTAMP NOT NULL,
        CONSTRAINT single_portfolio CHECK (id = 1)
    );

    CREATE TABLE IF NOT EXISTS positions (
        ticker       VARCHAR(10)  PRIMARY KEY,
        name         VARCHAR(100),
        shares       INTEGER      NOT NULL,
        avg_cost     NUMERIC(10,2) NOT NULL,
        bought_at    DATE,
        entry_reason TEXT,
        limit_sell   NUMERIC(10,2),
        stop_loss    NUMERIC(10,2),
        fee_paid     NUMERIC(10,2) DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS trades (
        id           SERIAL PRIMARY KEY,
        trade_date   DATE         NOT NULL,
        ticker       VARCHAR(10)  NOT NULL,
        name         VARCHAR(100),
        action       VARCHAR(10)  NOT NULL CHECK (action IN ('buy','sell')),
        shares       INTEGER      NOT NULL,
        price        NUMERIC(10,2) NOT NULL,
        amount       NUMERIC(15,2),
        fee          NUMERIC(10,2),
        reason       TEXT,
        pnl          NUMERIC(15,2),
        pnl_pct      NUMERIC(8,4),
        entry_price  NUMERIC(10,2),
        entry_reason TEXT,
        created_at   TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS equity_history (
        trade_date     DATE PRIMARY KEY,
        equity         NUMERIC(15,2),
        cash           NUMERIC(15,2),
        position_value NUMERIC(15,2)
    );

    CREATE TABLE IF NOT EXISTS scan_state (
        id              INTEGER PRIMARY KEY DEFAULT 1,
        last_scan_date  DATE,
        last_checked_at TIMESTAMPTZ,
        CONSTRAINT single_scan_state CHECK (id = 1)
    );

    CREATE TABLE IF NOT EXISTS scan_results (
        scan_date  DATE PRIMARY KEY,
        result     JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS stock_ai_results (
        ticker     VARCHAR(10) PRIMARY KEY,
        name       VARCHAR(100),
        scan_date  DATE NOT NULL,
        verdict    VARCHAR(10),
        confidence INTEGER,
        result     JSONB NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS daily_run_log (
        run_date         DATE PRIMARY KEY,
        data_status      VARCHAR(10),
        data_date        DATE,
        scan_status      VARCHAR(10),
        scan_started_at  TIMESTAMPTZ,
        scan_done_at     TIMESTAMPTZ,
        scan_error       TEXT,
        ai_status        VARCHAR(10),
        ai_started_at    TIMESTAMPTZ,
        ai_done_at       TIMESTAMPTZ,
        ai_done_count    INTEGER,
        ai_total_count   INTEGER,
        ai_error         TEXT,
        trade_status     VARCHAR(10),
        trade_started_at TIMESTAMPTZ,
        trade_done_at    TIMESTAMPTZ,
        trade_summary    JSONB,
        trade_error      TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_trades_ticker ON trades(ticker);
    CREATE INDEX IF NOT EXISTS idx_trades_date   ON trades(trade_date);
    CREATE INDEX IF NOT EXISTS idx_stock_ai_results_scan_date ON stock_ai_results(scan_date);
    """
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(ddl)
            # Migration: add per_stock_budget to existing DBs
            cur.execute("""
                ALTER TABLE portfolio_config
                ADD COLUMN IF NOT EXISTS per_stock_budget NUMERIC(15,2) NOT NULL DEFAULT 10000
            """)


# ── Portfolio ──────────────────────────────────────────────────────────────────

def load_portfolio() -> dict:
    """Return portfolio dict (same shape as old auto_portfolio.json)."""
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM portfolio_config WHERE id = 1")
            row = cur.fetchone()
            if not row:
                return {}

            portfolio = {
                "initial_capital":  float(row["initial_capital"]),
                "per_stock_budget": float(row.get("per_stock_budget") or 10000),
                "cash":             float(row["cash"]),
                "started_at":       str(row["started_at"]),
                "last_updated":     str(row["last_updated"]),
                "positions":        {},
            }

            cur.execute("SELECT * FROM positions")
            for pos in cur.fetchall():
                portfolio["positions"][pos["ticker"]] = {
                    "name":         pos["name"] or pos["ticker"],
                    "shares":       int(pos["shares"]),
                    "avg_cost":     float(pos["avg_cost"]),
                    "bought_at":    str(pos["bought_at"]) if pos["bought_at"] else "",
                    "entry_reason": pos["entry_reason"] or "",
                    "limit_sell":   float(pos["limit_sell"]) if pos["limit_sell"] else 0.0,
                    "stop_loss":    float(pos["stop_loss"])  if pos["stop_loss"]  else 0.0,
                    "fee_paid":     float(pos["fee_paid"])   if pos["fee_paid"]   else 0.0,
                }

            return portfolio


def save_portfolio(portfolio: dict) -> None:
    """Upsert portfolio config + replace all positions atomically."""
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("""
                INSERT INTO portfolio_config
                    (id, initial_capital, per_stock_budget, cash, started_at, last_updated)
                VALUES (1, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    initial_capital  = EXCLUDED.initial_capital,
                    per_stock_budget = EXCLUDED.per_stock_budget,
                    cash             = EXCLUDED.cash,
                    started_at       = EXCLUDED.started_at,
                    last_updated     = EXCLUDED.last_updated
            """, (
                portfolio.get("initial_capital", 100_000),
                portfolio.get("per_stock_budget", 10_000),
                portfolio.get("cash", 0),
                portfolio.get("started_at") or datetime.today().date(),
                portfolio.get("last_updated") or datetime.now(),
            ))

            cur.execute("DELETE FROM positions")
            for ticker, pos in portfolio.get("positions", {}).items():
                cur.execute("""
                    INSERT INTO positions
                        (ticker, name, shares, avg_cost, bought_at, entry_reason,
                         limit_sell, stop_loss, fee_paid)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    ticker,
                    pos.get("name", ticker),
                    pos.get("shares", 0),
                    pos.get("avg_cost", 0),
                    pos.get("bought_at") or None,
                    pos.get("entry_reason", ""),
                    pos.get("limit_sell")  or None,
                    pos.get("stop_loss")   or None,
                    pos.get("fee_paid", 0),
                ))


def reset_portfolio(capital: float, per_stock_budget: float = 10_000) -> dict:
    """Wipe everything and start fresh."""
    today = datetime.today().strftime("%Y-%m-%d")
    now   = datetime.today().strftime("%Y-%m-%d %H:%M")
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("TRUNCATE TABLE positions, trades, equity_history")
            cur.execute("""
                INSERT INTO portfolio_config
                    (id, initial_capital, per_stock_budget, cash, started_at, last_updated)
                VALUES (1, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    initial_capital  = EXCLUDED.initial_capital,
                    per_stock_budget = EXCLUDED.per_stock_budget,
                    cash             = EXCLUDED.cash,
                    started_at       = EXCLUDED.started_at,
                    last_updated     = EXCLUDED.last_updated
            """, (capital, per_stock_budget, capital, today, now))

    return {
        "initial_capital":  capital,
        "per_stock_budget": per_stock_budget,
        "cash":             capital,
        "positions":        {},
        "started_at":       today,
        "last_updated":    now,
    }


# ── Trades ─────────────────────────────────────────────────────────────────────

def delete_buy_today(ticker: str) -> int:
    """Delete today's buy record for ticker. Returns number of rows deleted."""
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "DELETE FROM trades WHERE ticker=%s AND action='buy' AND trade_date=CURRENT_DATE",
                (ticker,),
            )
            return cur.rowcount


def sold_today(ticker: str) -> bool:
    """Return True if a sell trade for this ticker was already logged today."""
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM trades WHERE ticker=%s AND action='sell' AND trade_date=CURRENT_DATE LIMIT 1",
                (ticker,),
            )
            return cur.fetchone() is not None


def append_trade(trade: dict) -> None:
    """Insert one trade record (buy or sell)."""
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("""
                INSERT INTO trades
                    (trade_date, ticker, name, action, shares, price, amount,
                     fee, reason, pnl, pnl_pct, entry_price, entry_reason)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                trade.get("date"),
                trade.get("ticker"),
                trade.get("name", trade.get("ticker")),
                trade.get("action"),
                trade.get("shares", 0),
                trade.get("price",  0),
                trade.get("amount"),
                trade.get("fee"),
                trade.get("reason", ""),
                trade.get("pnl"),
                trade.get("pnl_pct"),
                trade.get("entry_price"),
                trade.get("entry_reason", ""),
            ))


def load_orders() -> dict:
    """Return {'pending_buy': [], 'filled': [list of all trades]}."""
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT trade_date AS date, ticker, name, action, shares,
                       price, amount, fee, reason, pnl, pnl_pct,
                       entry_price, entry_reason
                FROM   trades
                ORDER  BY trade_date DESC, id DESC
            """)
            filled = []
            for row in cur.fetchall():
                t = dict(row)
                t["date"] = str(t["date"])
                for key in ("price", "amount", "fee", "pnl", "pnl_pct", "entry_price"):
                    if t[key] is not None:
                        t[key] = float(t[key])
                filled.append(t)
            return {"pending_buy": [], "filled": filled}


# ── Equity history ─────────────────────────────────────────────────────────────

def append_equity(entry: dict) -> None:
    """Upsert a daily equity snapshot."""
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("""
                INSERT INTO equity_history (trade_date, equity, cash, position_value)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (trade_date) DO UPDATE SET
                    equity         = EXCLUDED.equity,
                    cash           = EXCLUDED.cash,
                    position_value = EXCLUDED.position_value
            """, (
                entry.get("date"),
                entry.get("equity"),
                entry.get("cash"),
                entry.get("position_value"),
            ))


def load_history() -> list:
    """Return list of daily equity entries, oldest first."""
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT trade_date AS date, equity, cash, position_value
                FROM   equity_history
                ORDER  BY trade_date ASC
            """)
            return [
                {
                    "date":           str(r["date"]),
                    "equity":         float(r["equity"])         if r["equity"]         else 0.0,
                    "cash":           float(r["cash"])           if r["cash"]           else 0.0,
                    "position_value": float(r["position_value"]) if r["position_value"] else 0.0,
                }
                for r in cur.fetchall()
            ]


# ── Scan state / results ───────────────────────────────────────────────────────

def get_scan_state() -> dict:
    """Return {'last_scan_date': str|None, 'last_checked_at': str|None}.

    last_scan_date holds the data_date (from scan_today()'s actual fetched data)
    of the last cycle that ran AI analysis / auto-trade to completion — NOT a
    calendar date. Comparing against the newly-fetched data_date is what lets
    the scheduler detect "new closing data appeared" regardless of what wall-clock
    time it happens to check.
    """
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT last_scan_date, last_checked_at FROM scan_state WHERE id = 1")
            row = cur.fetchone()
            if not row:
                return {"last_scan_date": None, "last_checked_at": None}
            return {
                "last_scan_date":  str(row["last_scan_date"]) if row["last_scan_date"] else None,
                "last_checked_at": row["last_checked_at"].isoformat() if row["last_checked_at"] else None,
            }


def update_scan_state(last_scan_date: str | None = None) -> None:
    """Upsert scan_state. last_checked_at is always set to now(); last_scan_date
    is only updated when provided."""
    with _conn() as c:
        with c.cursor() as cur:
            if last_scan_date is not None:
                cur.execute("""
                    INSERT INTO scan_state (id, last_scan_date, last_checked_at)
                    VALUES (1, %s, NOW())
                    ON CONFLICT (id) DO UPDATE SET
                        last_scan_date  = EXCLUDED.last_scan_date,
                        last_checked_at = EXCLUDED.last_checked_at
                """, (last_scan_date,))
            else:
                cur.execute("""
                    INSERT INTO scan_state (id, last_checked_at)
                    VALUES (1, NOW())
                    ON CONFLICT (id) DO UPDATE SET
                        last_checked_at = EXCLUDED.last_checked_at
                """)


def save_scan_result(scan_date: str, result: dict) -> None:
    """Upsert today's scan result (JSONB) for the given trading day."""
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("""
                INSERT INTO scan_results (scan_date, result)
                VALUES (%s, %s)
                ON CONFLICT (scan_date) DO UPDATE SET
                    result     = EXCLUDED.result,
                    created_at = NOW()
            """, (scan_date, json.dumps(result, ensure_ascii=False)))


def get_latest_scan_result() -> dict | None:
    """Return the most recent scan_results row's `result` JSON, or None."""
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT scan_date, result, created_at
                FROM   scan_results
                ORDER  BY scan_date DESC
                LIMIT  1
            """)
            row = cur.fetchone()
            if not row:
                return None
            result = dict(row["result"])
            result["scan_date"] = str(row["scan_date"])
            result["created_at"] = row["created_at"].isoformat()
            return result


# ── Daily run log (首頁執行狀況列表：資料新鮮度／掃描／AI／自動交易) ────────────

_RUN_LOG_PHASES = ("scan", "ai", "trade")


def start_phase(run_date: str, phase: str) -> None:
    """Mark a phase ('scan'|'ai'|'trade') as running for run_date (upsert)."""
    if phase not in _RUN_LOG_PHASES:
        raise ValueError(f"unknown phase {phase!r}")
    status_col, started_col = f"{phase}_status", f"{phase}_started_at"
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(f"""
                INSERT INTO daily_run_log (run_date, {status_col}, {started_col})
                VALUES (%s, 'running', NOW())
                ON CONFLICT (run_date) DO UPDATE SET
                    {status_col}  = 'running',
                    {started_col} = NOW()
            """, (run_date,))


def complete_scan(run_date: str, status: str, error: str | None = None) -> None:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("""
                INSERT INTO daily_run_log (run_date, scan_status, scan_done_at, scan_error)
                VALUES (%s, %s, NOW(), %s)
                ON CONFLICT (run_date) DO UPDATE SET
                    scan_status  = EXCLUDED.scan_status,
                    scan_done_at = NOW(),
                    scan_error   = EXCLUDED.scan_error
            """, (run_date, status, error))


def complete_ai(run_date: str, status: str, done_count: int | None = None,
                 total_count: int | None = None, error: str | None = None) -> None:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("""
                INSERT INTO daily_run_log
                    (run_date, ai_status, ai_done_at, ai_done_count, ai_total_count, ai_error)
                VALUES (%s, %s, NOW(), %s, %s, %s)
                ON CONFLICT (run_date) DO UPDATE SET
                    ai_status      = EXCLUDED.ai_status,
                    ai_done_at     = NOW(),
                    ai_done_count  = EXCLUDED.ai_done_count,
                    ai_total_count = EXCLUDED.ai_total_count,
                    ai_error       = EXCLUDED.ai_error
            """, (run_date, status, done_count, total_count, error))


def complete_trade(run_date: str, status: str, summary: dict | None = None,
                    error: str | None = None) -> None:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("""
                INSERT INTO daily_run_log (run_date, trade_status, trade_done_at, trade_summary, trade_error)
                VALUES (%s, %s, NOW(), %s, %s)
                ON CONFLICT (run_date) DO UPDATE SET
                    trade_status  = EXCLUDED.trade_status,
                    trade_done_at = NOW(),
                    trade_summary = EXCLUDED.trade_summary,
                    trade_error   = EXCLUDED.trade_error
            """, (run_date, status, json.dumps(summary, ensure_ascii=False) if summary is not None else None, error))


def set_data_status(run_date: str, data_date: str | None, status: str) -> None:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("""
                INSERT INTO daily_run_log (run_date, data_status, data_date)
                VALUES (%s, %s, %s)
                ON CONFLICT (run_date) DO UPDATE SET
                    data_status = EXCLUDED.data_status,
                    data_date   = EXCLUDED.data_date
            """, (run_date, status, data_date))


def get_run_log(days: int = 30) -> list[dict]:
    """Return daily_run_log rows for the last `days` calendar days, newest first."""
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM daily_run_log
                WHERE run_date >= CURRENT_DATE - %s::int
                ORDER BY run_date DESC
            """, (days,))
            rows = cur.fetchall()

    out = []
    for r in rows:
        d = dict(r)
        for key in ("run_date", "data_date"):
            if d.get(key) is not None:
                d[key] = str(d[key])
        for key in ("scan_started_at", "scan_done_at", "ai_started_at", "ai_done_at",
                    "trade_started_at", "trade_done_at"):
            if d.get(key) is not None:
                d[key] = d[key].isoformat()
        out.append(d)
    return out


# ── Stock AI results (批次 ReAct 分析) ─────────────────────────────────────────

def save_stock_ai_result(ticker: str, name: str, scan_date: str, result: dict) -> None:
    """Upsert a stock's AI analysis result (one row per ticker, overwritten daily)."""
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("""
                INSERT INTO stock_ai_results (ticker, name, scan_date, verdict, confidence, result, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (ticker) DO UPDATE SET
                    name       = EXCLUDED.name,
                    scan_date  = EXCLUDED.scan_date,
                    verdict    = EXCLUDED.verdict,
                    confidence = EXCLUDED.confidence,
                    result     = EXCLUDED.result,
                    updated_at = NOW()
            """, (
                ticker, name, scan_date,
                result.get("verdict"), result.get("confidence"),
                json.dumps(result, ensure_ascii=False),
            ))


def get_stock_ai_results_for_date(scan_date: str) -> dict:
    """Return {ticker: {**result, 'name': ...}} for all AI results matching scan_date."""
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT ticker, name, result
                FROM   stock_ai_results
                WHERE  scan_date = %s
            """, (scan_date,))
            out = {}
            for row in cur.fetchall():
                entry = dict(row["result"])
                entry["name"] = row["name"]
                out[row["ticker"]] = entry
            return out


def get_stock_ai_result(ticker: str) -> dict | None:
    """Return a single ticker's latest AI analysis result, or None."""
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT ticker, name, scan_date, result
                FROM   stock_ai_results
                WHERE  ticker = %s
            """, (ticker,))
            row = cur.fetchone()
            if not row:
                return None
            entry = dict(row["result"])
            entry["name"] = row["name"]
            entry["scan_date"] = str(row["scan_date"])
            return entry


# ── Migration from JSON ────────────────────────────────────────────────────────

def migrate_from_json(portfolio_path, orders_path, history_path) -> bool:
    """
    One-time import of existing JSON cache files into PostgreSQL.
    Returns True if migration happened, False if DB already has data.
    """
    # Don't migrate if DB already has a portfolio
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM portfolio_config")
            if cur.fetchone()[0] > 0:
                return False

    import json
    from pathlib import Path

    pf = Path(portfolio_path)
    if not pf.exists():
        return False

    with open(pf, encoding="utf-8") as f:
        portfolio = json.load(f)

    save_portfolio(portfolio)

    of = Path(orders_path)
    if of.exists():
        with open(of, encoding="utf-8") as f:
            orders = json.load(f)
        for trade in orders.get("filled", []):
            try:
                append_trade(trade)
            except Exception:
                pass

    hf = Path(history_path)
    if hf.exists():
        with open(hf, encoding="utf-8") as f:
            history = json.load(f)
        for entry in history:
            try:
                append_equity(entry)
            except Exception:
                pass

    return True
