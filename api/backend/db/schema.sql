-- 台股 AI 分析系統 — PostgreSQL Schema
-- API 啟動時 portfolio_db.init_db() 會直接執行這份檔案（唯一的 DDL 來源）；也可手動執行
-- 執行方式: psql -U stockuser -d stockdb -f schema.sql

-- 自動掃描狀態（永遠只有一列，id = 1）
CREATE TABLE IF NOT EXISTS scan_state (
    id              INTEGER PRIMARY KEY DEFAULT 1,
    last_scan_date  DATE,                            -- 上次完整處理過的資料日期
    last_checked_at TIMESTAMPTZ,                     -- 上次檢查時間
    CONSTRAINT single_scan_state CHECK (id = 1)
);

-- 每日今日訊號掃描結果（背景排程寫入）
CREATE TABLE IF NOT EXISTS scan_results (
    scan_date  DATE PRIMARY KEY,                     -- 掃描對應的交易日
    result     JSONB NOT NULL,                       -- scan_today() 回傳的完整結果
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 批次 AI 分析結果（每支股票一列，每日覆寫）
CREATE TABLE IF NOT EXISTS stock_ai_results (
    ticker     VARCHAR(10) PRIMARY KEY,
    name       VARCHAR(100),
    scan_date  DATE NOT NULL,                        -- 分析對應的交易日
    verdict    VARCHAR(10),                          -- 偏多 / 中性 / 偏空
    confidence INTEGER,                              -- 信心度 0-100
    result     JSONB NOT NULL,                       -- 完整分析結果
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 首頁執行狀況列表：每天各階段（資料／訊號掃描／AI 分析）的執行狀態
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
    ai_error         TEXT
);

CREATE INDEX IF NOT EXISTS idx_stock_ai_results_scan_date ON stock_ai_results(scan_date);

-- 全市場每日收盤行情（上市＋上櫃，一般股票與 ETF）。每個交易日只打兩次 API 就有全部股票，
-- 個股歷史股價直接從這裡讀，不用逐支股票打證交所（見 control/data/price_store.py）
CREATE TABLE IF NOT EXISTS daily_prices (
    ticker     VARCHAR(10) NOT NULL,
    trade_date DATE NOT NULL,
    open       DOUBLE PRECISION,
    high       DOUBLE PRECISION,
    low        DOUBLE PRECISION,
    close      DOUBLE PRECISION NOT NULL,
    volume     BIGINT,                               -- 成交股數
    PRIMARY KEY (ticker, trade_date)
);

-- 哪些交易日已經完整抓過（上市＋上櫃都有）；rows = 0 代表那天其實休市
CREATE TABLE IF NOT EXISTS daily_price_sync (
    trade_date DATE PRIMARY KEY,
    rows       INTEGER NOT NULL,
    synced_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 常用查詢範例 ──────────────────────────────────────────────────────────────

-- 查看最近 10 天的執行狀況
-- SELECT run_date, data_status, scan_status, ai_status FROM daily_run_log ORDER BY run_date DESC LIMIT 10;

-- 查看最新一次掃描的買入候選
-- SELECT scan_date, jsonb_array_length(result->'buy_candidates') AS buys FROM scan_results ORDER BY scan_date DESC LIMIT 1;
