-- 台股 AI 分析系統 — PostgreSQL Schema
-- 執行方式: psql -U stockuser -d stockdb -f schema.sql

-- 投資組合設定（永遠只有一列，id = 1）
CREATE TABLE IF NOT EXISTS portfolio_config (
    id               INTEGER PRIMARY KEY DEFAULT 1,
    initial_capital  NUMERIC(15,2) NOT NULL,               -- 初始資金
    per_stock_budget NUMERIC(15,2) NOT NULL DEFAULT 10000, -- 每檔預算上限
    cash             NUMERIC(15,2) NOT NULL,               -- 目前可用現金
    started_at       DATE          NOT NULL,               -- 開始日期
    last_updated     TIMESTAMP     NOT NULL,               -- 最後更新時間
    CONSTRAINT single_portfolio CHECK (id = 1)
);

-- 目前持倉（一股票一列，賣出後刪除）
CREATE TABLE IF NOT EXISTS positions (
    ticker       VARCHAR(10)   PRIMARY KEY,          -- 股票代號，例如 2330
    name         VARCHAR(100),                       -- 股票名稱
    shares       INTEGER       NOT NULL,             -- 持有股數
    avg_cost     NUMERIC(10,2) NOT NULL,             -- 平均成本（元/股）
    bought_at    DATE,                               -- 買入日期
    entry_reason TEXT,                               -- 買入原因（訊號說明）
    limit_sell   NUMERIC(10,2),                     -- 停利價
    stop_loss    NUMERIC(10,2),                     -- 停損價
    fee_paid     NUMERIC(10,2) DEFAULT 0            -- 已付手續費
);

-- 所有成交紀錄（只增不刪的日誌）
CREATE TABLE IF NOT EXISTS trades (
    id           SERIAL        PRIMARY KEY,
    trade_date   DATE          NOT NULL,             -- 成交日期
    ticker       VARCHAR(10)   NOT NULL,             -- 股票代號
    name         VARCHAR(100),                       -- 股票名稱
    action       VARCHAR(10)   NOT NULL              -- 'buy' 或 'sell'
                     CHECK (action IN ('buy','sell')),
    shares       INTEGER       NOT NULL,             -- 成交股數
    price        NUMERIC(10,2) NOT NULL,             -- 成交價
    amount       NUMERIC(15,2),                     -- 成交金額（不含費）
    fee          NUMERIC(10,2),                     -- 手續費（買：0.1425%，賣：0.4425%）
    reason       TEXT,                               -- 出入場原因
    pnl          NUMERIC(15,2),                     -- 損益（賣出才有）
    pnl_pct      NUMERIC(8,4),                      -- 損益率（%）
    entry_price  NUMERIC(10,2),                     -- 對應買入價（賣出時記錄）
    entry_reason TEXT,                               -- 買入原因（賣出時記錄）
    created_at   TIMESTAMP DEFAULT NOW()            -- 紀錄建立時間
);

-- 每日資產曲線快照
CREATE TABLE IF NOT EXISTS equity_history (
    trade_date     DATE PRIMARY KEY,                 -- 日期（唯一）
    equity         NUMERIC(15,2),                   -- 總資產（現金 + 持股市值）
    cash           NUMERIC(15,2),                   -- 現金
    position_value NUMERIC(15,2)                    -- 持股市值
);

-- 查詢用索引
CREATE INDEX IF NOT EXISTS idx_trades_ticker ON trades(ticker);
CREATE INDEX IF NOT EXISTS idx_trades_date   ON trades(trade_date);

-- ── 常用查詢範例 ──────────────────────────────────────────────────────────────

-- 查看目前投資組合狀態
-- SELECT * FROM portfolio_config;

-- 查看所有持倉
-- SELECT ticker, name, shares, avg_cost, limit_sell, stop_loss, bought_at FROM positions;

-- 查看最近10筆交易
-- SELECT trade_date, ticker, action, shares, price, pnl, pnl_pct, reason FROM trades ORDER BY id DESC LIMIT 10;

-- 統計勝率
-- SELECT
--     COUNT(*) FILTER (WHERE action='sell')                         AS total_trades,
--     COUNT(*) FILTER (WHERE action='sell' AND pnl > 0)            AS wins,
--     ROUND(AVG(pnl_pct) FILTER (WHERE action='sell'), 2)          AS avg_pnl_pct,
--     ROUND(SUM(pnl)     FILTER (WHERE action='sell'), 0)          AS total_pnl
-- FROM trades;

-- 查看資產曲線（最近30天）
-- SELECT trade_date, equity, cash, position_value FROM equity_history ORDER BY trade_date DESC LIMIT 30;
