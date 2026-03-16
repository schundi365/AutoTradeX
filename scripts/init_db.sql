-- APEX Bot — DuckDB Schema
-- Run once at startup via: memory/duckdb_store.py → init_schema()
-- Or manually: duckdb data/apex.db < scripts/init_db.sql

-- ─────────────────────────────────────────────────────────────────────────────
-- OHLCV market data
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ohlcv (
    symbol    VARCHAR,
    timeframe VARCHAR,
    timestamp TIMESTAMP,
    open      DOUBLE,
    high      DOUBLE,
    low       DOUBLE,
    close     DOUBLE,
    volume    DOUBLE,
    PRIMARY KEY (symbol, timeframe, timestamp)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- All trade executions (immutable audit log)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS executions (
    execution_id     VARCHAR PRIMARY KEY,
    signal_id        VARCHAR,
    symbol           VARCHAR,
    direction        VARCHAR,
    strategy         VARCHAR,
    timeframe        VARCHAR,
    signal_price     DOUBLE,
    execution_price  DOUBLE,
    slippage         DOUBLE,
    stop_loss        DOUBLE,
    take_profit      DOUBLE,
    lot_size         DOUBLE,
    account_balance  DOUBLE,
    risk_amount      DOUBLE,
    risk_pct         DOUBLE,
    market_regime    VARCHAR,
    atr              DOUBLE,
    adx              DOUBLE,
    rsi              DOUBLE,
    broker_order_id  VARCHAR,
    broker_name      VARCHAR,
    execution_time   TIMESTAMP,
    order_latency_ms INTEGER,
    status           VARCHAR,
    notes            VARCHAR
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Closed trade summary (training data + analytics)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS closed_trades (
    trade_id                VARCHAR PRIMARY KEY,
    symbol                  VARCHAR,
    direction               VARCHAR,
    strategy                VARCHAR,
    entry_price             DOUBLE,
    close_price             DOUBLE,
    final_pnl               DOUBLE,
    lot_size                DOUBLE,
    risk_pct                DOUBLE,
    open_time               TIMESTAMP,
    close_time              TIMESTAMP,
    duration_minutes        INTEGER,
    close_reason            VARCHAR,
    sl_tightened_count      INTEGER DEFAULT 0,
    tp_extended_count       INTEGER DEFAULT 0,
    trailing_active         BOOLEAN DEFAULT FALSE,
    max_adverse_excursion   DOUBLE  DEFAULT 0.0,
    max_favorable_excursion DOUBLE  DEFAULT 0.0
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Daily KPI snapshots for dashboard
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_kpis (
    date            DATE PRIMARY KEY,
    total_pnl       DOUBLE,
    daily_pnl       DOUBLE,
    win_rate        DOUBLE,
    total_trades    INTEGER,
    profit_factor   DOUBLE,
    sharpe_ratio    DOUBLE,
    max_drawdown    DOUBLE,
    account_balance DOUBLE
);

-- ─────────────────────────────────────────────────────────────────────────────
-- News items (deduplicated)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS news (
    id        VARCHAR PRIMARY KEY,
    title     VARCHAR,
    source    VARCHAR,
    published TIMESTAMP,
    sentiment DOUBLE,
    impact    VARCHAR,
    symbols   VARCHAR,
    processed BOOLEAN DEFAULT FALSE
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Decision log — EVERY orchestrator decision (approved AND rejected)
-- This is the primary source for fine-tuning training data.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS decision_log (
    timestamp    TIMESTAMP,
    symbol       VARCHAR,
    context_json VARCHAR,   -- full JSON blob of all features at decision time
    outcome      VARCHAR,   -- WIN | LOSS | NULL (filled when trade closes)
    final_pnl    DOUBLE,    -- filled when trade closes
    PRIMARY KEY (timestamp, symbol)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Bot decisions — Real-time decision tracking for dashboard
-- Tracks GO/NOGO decisions with timing metrics
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bot_decisions (
    id INTEGER PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    symbol VARCHAR,
    decision VARCHAR,
    confidence DOUBLE,
    outcome VARCHAR,
    decision_time_ms INTEGER
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Sentiment analysis cache for dashboard
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sentiment_analysis (
    timestamp        TIMESTAMP PRIMARY KEY,
    news_summary     VARCHAR,
    adjustments_json VARCHAR
);

-- ─────────────────────────────────────────────────────────────────────────────
-- View: only completed decisions ready for training export
-- ─────────────────────────────────────────────────────────────────────────────
CREATE VIEW IF NOT EXISTS training_ready AS
SELECT *
FROM decision_log
WHERE outcome IS NOT NULL                -- only completed trades
  AND timestamp < NOW() - INTERVAL 1 DAY; -- exclude very recent

-- ─────────────────────────────────────────────────────────────────────────────
-- View: win rate by symbol (last 30 days)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE VIEW IF NOT EXISTS win_rate_by_symbol AS
SELECT
    symbol,
    COUNT(*)                                                    AS total_decisions,
    SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END)           AS wins,
    ROUND(SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END)
          * 100.0 / COUNT(*), 2)                               AS win_rate_pct,
    ROUND(AVG(final_pnl), 2)                                    AS avg_pnl
FROM decision_log
WHERE outcome IS NOT NULL
  AND timestamp > NOW() - INTERVAL 30 DAY
GROUP BY symbol
ORDER BY win_rate_pct DESC;

-- ─────────────────────────────────────────────────────────────────────────────
-- Indices for common query patterns
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_tf    ON ohlcv (symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_executions_symbol  ON executions (symbol);
CREATE INDEX IF NOT EXISTS idx_executions_status  ON executions (status);
CREATE INDEX IF NOT EXISTS idx_closed_symbol      ON closed_trades (symbol);
CREATE INDEX IF NOT EXISTS idx_closed_time        ON closed_trades (close_time);
CREATE INDEX IF NOT EXISTS idx_decision_symbol    ON decision_log (symbol);
CREATE INDEX IF NOT EXISTS idx_decision_outcome   ON decision_log (outcome);
CREATE INDEX IF NOT EXISTS idx_bot_decisions_time ON bot_decisions (timestamp);
