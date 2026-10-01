"""
PostgreSQL persistence layer.

Tables
──────
scan_state        — single row: last processed data date
scan_results      — daily 今日訊號掃描 result (JSONB)
stock_ai_results  — latest batch AI analysis per ticker
daily_run_log     — 首頁執行狀況列表 (data / scan / ai phases per day)
"""

import json
import os
import threading
import psycopg2
import psycopg2.extras
import psycopg2.pool
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

from backend.utils import TAIPEI

load_dotenv(Path(__file__).parent.parent.parent / ".env")

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


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


# 前端每幾秒就會輪詢一次，每次查詢都重新 TCP 連線 + 認證很浪費，改用連線池重複使用。
_POOL_MAX = 20
_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                cfg = _db_cfg()
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    1, _POOL_MAX,
                    host=cfg["host"], port=cfg["port"],
                    dbname=cfg["name"], user=cfg["user"], password=cfg["password"],
                )
    return _pool


@contextmanager
def _conn():
    pool = _get_pool()
    c = pool.getconn()
    try:
        yield c
        c.commit()
    except Exception:
        try:
            c.rollback()
        except psycopg2.Error:
            pass  # 連線已斷（例如 DB 重啟），下面 putconn 會把它丟掉
        raise
    finally:
        # 斷掉的連線不放回池子，下次 getconn 會自動建新的
        pool.putconn(c, close=bool(c.closed))


# ── Schema creation ────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create all tables (idempotent). DDL 只維護在 schema.sql 一份。"""
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(SCHEMA_PATH.read_text(encoding="utf-8"))


# ── Scan state / results ───────────────────────────────────────────────────────

def get_scan_state() -> dict:
    """Return {'last_scan_date': str|None, 'last_checked_at': str|None}.

    last_scan_date holds the data_date (from scan_today()'s actual fetched data)
    of the last cycle that ran AI analysis to completion — NOT a
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
                "last_checked_at": row["last_checked_at"].astimezone(TAIPEI).isoformat() if row["last_checked_at"] else None,
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


def get_latest_scan_result(include_all_candidates: bool = True) -> dict | None:
    """Return the most recent scan_results row's `result` JSON, or None.

    all_candidates 含每支候選股的完整技術指標，只有重新跑 AI 分析時才需要；
    給前端顯示用時傳 include_all_candidates=False，直接在 DB 端去掉，少傳一大段 JSON。
    """
    result_expr = "result" if include_all_candidates else "result - 'all_candidates'"
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT scan_date, {result_expr} AS result, created_at
                FROM   scan_results
                ORDER  BY scan_date DESC
                LIMIT  1
            """)
            row = cur.fetchone()
            if not row:
                return None
            result = dict(row["result"])
            result["scan_date"] = str(row["scan_date"])
            result["created_at"] = row["created_at"].astimezone(TAIPEI).isoformat()
            return result


# ── Daily run log (首頁執行狀況列表：資料新鮮度／掃描／AI) ─────────────────────

_RUN_LOG_PHASES = ("scan", "ai")


def start_phase(run_date: str, phase: str) -> None:
    """Mark a phase ('scan'|'ai') as running for run_date (upsert)."""
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
    """Return daily_run_log rows for the last `days` calendar days (Taipei time), newest first."""
    # Postgres session runs in UTC (see `SHOW timezone`), so CURRENT_DATE would be
    # up to a day behind Taipei's actual today during Taipei's 00:00–08:00 window.
    # Compute the cutoff in Taipei time in Python instead of relying on the DB's clock.
    threshold = (datetime.now(TAIPEI) - timedelta(days=days)).date()
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM daily_run_log
                WHERE run_date >= %s
                ORDER BY run_date DESC
            """, (threshold,))
            rows = cur.fetchall()

    out = []
    for r in rows:
        d = dict(r)
        for key in ("run_date", "data_date"):
            if d.get(key) is not None:
                d[key] = str(d[key])
        for key in ("scan_started_at", "scan_done_at", "ai_started_at", "ai_done_at"):
            if d.get(key) is not None:
                # 存的是 TIMESTAMPTZ（UTC），轉成台北時間再序列化，前端才不會顯示成 UTC 時間（差 8 小時）。
                d[key] = d[key].astimezone(TAIPEI).isoformat()
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
    """Return {ticker: {**result, 'name': ..., 'trace_steps': int}} for all AI results matching scan_date.

    不含 trace：trace 存了每一輪送給 LLM 的完整 prompt，一筆可能就上百 KB，
    列表頁只需要步數，展開時再用 get_stock_ai_trace() 單獨抓。
    """
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT ticker, name,
                       result - 'trace' AS result,
                       COALESCE(jsonb_array_length(result->'trace'), 0) AS trace_steps
                FROM   stock_ai_results
                WHERE  scan_date = %s
            """, (scan_date,))
            out = {}
            for row in cur.fetchall():
                entry = dict(row["result"])
                entry["name"] = row["name"]
                entry["trace_steps"] = row["trace_steps"]
                out[row["ticker"]] = entry
            return out


def count_stock_ai_done(scan_date: str, tickers: list[str]) -> int:
    """scan_date 當天、tickers 之中已成功完成 AI 分析（沒有 error）的數量。"""
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM   stock_ai_results
                WHERE  scan_date = %s
                  AND  ticker = ANY(%s)
                  AND  NOT COALESCE((result->>'error')::boolean, FALSE)
            """, (scan_date, tickers))
            return cur.fetchone()[0]


def get_latest_scan_tickers() -> tuple[str, list[str]] | None:
    """回傳最新一次掃描的 (scan_date, all_candidates 的股票代號清單)，不載入整份 result。"""
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("""
                SELECT scan_date,
                       ARRAY(SELECT x->>'ticker'
                             FROM jsonb_array_elements(COALESCE(result->'all_candidates', '[]'::jsonb)) x)
                FROM   scan_results
                ORDER  BY scan_date DESC
                LIMIT  1
            """)
            row = cur.fetchone()
            if not row:
                return None
            return str(row[0]), list(row[1])


def get_stock_ai_trace(ticker: str, scan_date: str) -> list | None:
    """單一股票在 scan_date 的 AI 分析完整流程（trace），查無則回傳 None。"""
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("""
                SELECT result->'trace'
                FROM   stock_ai_results
                WHERE  ticker = %s AND scan_date = %s
            """, (ticker, scan_date))
            row = cur.fetchone()
            return row[0] if row else None

