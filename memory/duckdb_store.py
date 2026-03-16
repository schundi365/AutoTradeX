"""
APEX Bot — DuckDB Store
Single-writer pattern: all writes go through an asyncio.Queue.
Reads use read-only connections (concurrent-safe).

Critical: DuckDB does not support concurrent writers. All mutations must
flow through the single write connection owned by _writer_loop().
"""
from __future__ import annotations
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import duckdb
from loguru import logger as log


class DuckDBStore:
    """
    Thread-safe DuckDB wrapper for the APEX bot.

    Usage (inside an async context):
        store = DuckDBStore("data/apex.db")
        await store.start()
        await store.execute_write("INSERT INTO ...", [...])
        rows = store.execute_read("SELECT * FROM executions")
        await store.stop()
    """

    def __init__(self, db_path: str = "data/apex.db"):
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # Dedicated write connection — never share this
        self._write_conn: Optional[duckdb.DuckDBPyConnection] = None
        self._write_queue: asyncio.Queue = asyncio.Queue()
        self._writer_task: Optional[asyncio.Task] = None
        self._running = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self):
        """Open write connection and start the writer loop."""
        self._write_conn = duckdb.connect(self._db_path)
        self._running = True
        self._writer_task = asyncio.create_task(self._writer_loop(), name="duckdb-writer")
        log.info("DuckDB store started: {}", self._db_path)

    async def stop(self):
        """Drain the write queue, close the connection."""
        self._running = False
        if self._write_queue:
            await self._write_queue.join()
        if self._writer_task:
            self._writer_task.cancel()
        if self._write_conn:
            self._write_conn.close()
        log.info("DuckDB store stopped")

    # ── Internal writer loop ───────────────────────────────────────────────────

    async def _writer_loop(self):
        while self._running or not self._write_queue.empty():
            try:
                sql, params, future = await asyncio.wait_for(
                    self._write_queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue
            try:
                result = self._write_conn.execute(sql, params)
                self._write_conn.commit()
                if not future.done():
                    future.set_result(result)
            except Exception as e:
                log.error("DuckDB write error: {}\nSQL: {}", e, sql[:200])
                if not future.done():
                    future.set_exception(e)
            finally:
                self._write_queue.task_done()

    # ── Public API ────────────────────────────────────────────────────────────

    async def execute_write(self, sql: str, params: list = []) -> Any:
        """
        Enqueue a write operation and await its completion.
        Safe to call from multiple coroutines concurrently.
        """
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        await self._write_queue.put((sql, params, future))
        return await future

    def execute_read(self, sql: str, params: list = []) -> list[tuple]:
        """
        Execute a read query.
        Uses the write connection when available (avoids DuckDB multi-connection
        conflicts), otherwise opens a fresh connection with read_only flag.
        """
        try:
            if self._write_conn:
                return self._write_conn.execute(sql, params).fetchall()
            con = duckdb.connect(self._db_path, read_only=True)
            result = con.execute(sql, params).fetchall()
            con.close()
            return result
        except Exception as e:
            log.error("DuckDB read error: {}\nSQL: {}", e, sql[:200])
            return []

    def execute_read_df(self, sql: str, params: list = []):
        """Return results as a pandas DataFrame."""
        try:
            if self._write_conn:
                return self._write_conn.execute(sql, params).df()
            con = duckdb.connect(self._db_path, read_only=True)
            df = con.execute(sql, params).df()
            con.close()
            return df
        except Exception as e:
            log.error("DuckDB read_df error: {}", e)
            import pandas as pd
            return pd.DataFrame()

    # ── Schema initialisation ─────────────────────────────────────────────────

    async def init_schema(self):
        """Create all APEX tables if they don't exist."""
        schema_path = Path(__file__).parent.parent / "scripts" / "init_db.sql"
        if schema_path.exists():
            sql = schema_path.read_text()
            # Execute each statement separately
            for statement in sql.split(";"):
                stmt = statement.strip()
                if stmt:
                    await self.execute_write(stmt)
            log.info("DuckDB schema initialised from init_db.sql")
        else:
            await self._create_schema_inline()

    async def _create_schema_inline(self):
        """Fallback: create schema without SQL file."""
        statements = [
            """CREATE TABLE IF NOT EXISTS ohlcv (
                symbol VARCHAR, timeframe VARCHAR, timestamp TIMESTAMP,
                open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE,
                PRIMARY KEY (symbol, timeframe, timestamp)
            )""",
            """CREATE TABLE IF NOT EXISTS executions (
                execution_id VARCHAR PRIMARY KEY,
                signal_id VARCHAR, symbol VARCHAR, direction VARCHAR,
                strategy VARCHAR, timeframe VARCHAR,
                signal_price DOUBLE, execution_price DOUBLE, slippage DOUBLE,
                stop_loss DOUBLE, take_profit DOUBLE,
                lot_size DOUBLE, account_balance DOUBLE,
                risk_amount DOUBLE, risk_pct DOUBLE,
                market_regime VARCHAR, atr DOUBLE, adx DOUBLE, rsi DOUBLE,
                broker_order_id VARCHAR, broker_name VARCHAR,
                execution_time TIMESTAMP, order_latency_ms INTEGER,
                status VARCHAR, notes VARCHAR
            )""",
            """CREATE TABLE IF NOT EXISTS closed_trades (
                trade_id VARCHAR PRIMARY KEY,
                symbol VARCHAR, direction VARCHAR, strategy VARCHAR,
                entry_price DOUBLE, close_price DOUBLE, final_pnl DOUBLE,
                lot_size DOUBLE, risk_pct DOUBLE,
                open_time TIMESTAMP, close_time TIMESTAMP,
                duration_minutes INTEGER, close_reason VARCHAR,
                sl_tightened_count INTEGER DEFAULT 0,
                tp_extended_count INTEGER DEFAULT 0,
                trailing_active BOOLEAN DEFAULT FALSE,
                max_adverse_excursion DOUBLE DEFAULT 0.0,
                max_favorable_excursion DOUBLE DEFAULT 0.0
            )""",
            """CREATE TABLE IF NOT EXISTS daily_kpis (
                date DATE PRIMARY KEY,
                total_pnl DOUBLE, daily_pnl DOUBLE, win_rate DOUBLE,
                total_trades INTEGER, profit_factor DOUBLE,
                sharpe_ratio DOUBLE, max_drawdown DOUBLE,
                account_balance DOUBLE
            )""",
            """CREATE TABLE IF NOT EXISTS news (
                id VARCHAR PRIMARY KEY, title VARCHAR, source VARCHAR,
                published TIMESTAMP, sentiment DOUBLE, impact VARCHAR,
                symbols VARCHAR, processed BOOLEAN DEFAULT FALSE
            )""",
            """CREATE TABLE IF NOT EXISTS decision_log (
                timestamp TIMESTAMP,
                symbol VARCHAR,
                context_json VARCHAR,
                outcome VARCHAR,
                final_pnl DOUBLE,
                PRIMARY KEY (timestamp, symbol)
            )""",
            """CREATE TABLE IF NOT EXISTS sentiment_analysis (
                timestamp TIMESTAMP PRIMARY KEY,
                news_summary VARCHAR,
                adjustments_json VARCHAR
            )""",
        ]
        for sql in statements:
            await self.execute_write(sql)
        log.info("DuckDB schema initialised (inline)")

    # ── Domain helpers ────────────────────────────────────────────────────────

    async def log_sentiment_analysis(self, news_summary: str, adjustments: list):
        """Persist the latest sentiment agent findings."""
        await self.execute_write(
            """INSERT INTO sentiment_analysis (timestamp, news_summary, adjustments_json)
               VALUES (?, ?, ?)""",
            [datetime.utcnow(), news_summary, json.dumps(adjustments)],
        )

    async def log_decision(
        self,
        timestamp: datetime,
        symbol: str,
        context: dict,
        outcome: Optional[str] = None,
        final_pnl: Optional[float] = None,
    ):
        """
        Write an orchestrator decision to decision_log.
        Call this for EVERY decision — approvals AND rejections.
        outcome = "WIN" | "LOSS" | None (filled when trade closes)
        """
        await self.execute_write(
            """INSERT INTO decision_log (timestamp, symbol, context_json, outcome, final_pnl)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (timestamp, symbol) DO UPDATE
               SET outcome = excluded.outcome,
                   final_pnl = excluded.final_pnl
            """,
            [timestamp, symbol, json.dumps(context), outcome, final_pnl],
        )

    async def update_decision_outcome(
        self, symbol: str, entry_timestamp: datetime, outcome: str, final_pnl: float
    ):
        """Fill in the WIN/LOSS outcome once a trade closes."""
        await self.execute_write(
            """UPDATE decision_log
               SET outcome = ?, final_pnl = ?
               WHERE symbol = ? AND timestamp = ?
            """,
            [outcome, final_pnl, symbol, entry_timestamp],
        )

    def get_win_rate(self, symbol: Optional[str] = None, lookback_days: int = 30) -> float:
        """Compute win rate from decision_log for Kelly Criterion sizing."""
        where = "WHERE outcome IS NOT NULL AND timestamp > NOW() - INTERVAL 30 DAY"
        if symbol:
            where += f" AND symbol = '{symbol}'"
        rows = self.execute_read(
            f"SELECT outcome FROM decision_log {where}"
        )
        if not rows:
            return 0.5  # default assumption
        wins = sum(1 for (o,) in rows if o == "WIN")
        return wins / len(rows)

    def get_avg_rr(self, symbol: Optional[str] = None, lookback_days: int = 30) -> float:
        """Compute average risk/reward from closed_trades."""
        where = "WHERE final_pnl IS NOT NULL"
        if symbol:
            where += f" AND symbol = '{symbol}'"
        rows = self.execute_read(
            f"""SELECT entry_price, close_price, direction
                FROM closed_trades {where}
                ORDER BY close_time DESC LIMIT 100"""
        )
        if not rows:
            return 2.0  # default assumption
        rrs = []
        for entry, close, direction in rows:
            if entry and close:
                move = abs(close - entry)
                # Approximate RR from price move vs typical SL (1 ATR ~ 0.5% of price)
                approx_sl = entry * 0.005
                if approx_sl > 0:
                    rrs.append(move / approx_sl)
        return sum(rrs) / len(rrs) if rrs else 2.0

    def get_daily_pnl(self) -> float:
        """Current day's realised P&L."""
        rows = self.execute_read(
            """SELECT COALESCE(SUM(final_pnl), 0.0)
               FROM closed_trades
               WHERE close_time >= CURRENT_DATE"""
        )
        return rows[0][0] if rows else 0.0

    def get_open_trade_count(self) -> int:
        """Count of currently open executions (status = OPEN)."""
        rows = self.execute_read(
            "SELECT COUNT(*) FROM executions WHERE status = 'OPEN'"
        )
        return rows[0][0] if rows else 0

    async def write_ohlcv_batch(self, rows: list[tuple]):
        """
        Bulk insert OHLCV rows. Each tuple: (symbol, tf, ts, o, h, l, c, v).
        Uses INSERT OR IGNORE to avoid duplicates.
        """
        if not rows:
            return
        await self.execute_write(
            """INSERT OR IGNORE INTO ohlcv
               (symbol, timeframe, timestamp, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )

    async def write_execution(self, record: dict):
        """Insert a full ExecutionRecord into the executions table."""
        await self.execute_write(
            """INSERT INTO executions VALUES (
               ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )""",
            [
                record.get("execution_id"),
                record.get("signal_id"),
                record.get("symbol"),
                record.get("direction"),
                record.get("strategy"),
                record.get("timeframe"),
                record.get("signal_price"),
                record.get("execution_price"),
                record.get("slippage"),
                record.get("stop_loss"),
                record.get("take_profit"),
                record.get("lot_size"),
                record.get("account_balance"),
                record.get("risk_amount"),
                record.get("risk_pct"),
                record.get("market_regime"),
                record.get("atr"),
                record.get("adx"),
                record.get("rsi"),
                record.get("broker_order_id"),
                record.get("broker_name"),
                record.get("execution_time"),
                record.get("order_latency_ms"),
                record.get("status", "OPEN"),
                record.get("notes", ""),
            ],
        )
