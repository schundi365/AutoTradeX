"""
APEX Bot — Logger
Structured logging with loguru. Broadcasts log events to
connected WebSocket clients so the frontend Log panel updates live.
"""
from __future__ import annotations
import sys
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from loguru import logger
import duckdb

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ── WebSocket broadcast registry ────────────────────────
_ws_clients: set = set()
# Cached reference to the main asyncio event loop so background threads
# (e.g. FastAPI BackgroundTasks / APScheduler) can broadcast log lines.
_main_loop: asyncio.AbstractEventLoop | None = None

# DuckDB log storage
DB_PATH = Path(__file__).parent.parent / "data" / "system_logs.duckdb"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def _init_db():
    con = duckdb.connect(str(DB_PATH))
    con.execute("""
        CREATE TABLE IF NOT EXISTS system_logs (
            timestamp TIMESTAMP,
            level TEXT,
            agent TEXT,
            module TEXT,
            message TEXT
        )
    """)
    con.close()

_init_db()

def _db_sink(message):
    record = message.record
    try:
        con = duckdb.connect(str(DB_PATH))
        con.execute(
            "INSERT INTO system_logs VALUES (?, ?, ?, ?, ?)",
            (
                record["time"].replace(tzinfo=None),
                record["level"].name,
                record["extra"].get("agent", "SYSTEM"),
                record["name"],
                record["message"]
            )
        )
        con.close()
    except Exception:
        pass # Don't let log storage failure crash the app

def register_ws_client(ws):
    _ws_clients.add(ws)

def unregister_ws_client(ws):
    _ws_clients.discard(ws)


# ── Custom log sink → broadcasts to frontend ────────────
def _ws_sink(message):
    global _ws_clients, _main_loop
    record = message.record
    level_map = {
        "INFO":    "INFO",
        "WARNING": "WARN",
        "ERROR":   "WARN",
        "SUCCESS": "TRADE",
        "DEBUG":   "INFO",
    }
    level = level_map.get(record["level"].name, "INFO")

    # Enhanced categorization for dashboard filters
    msg = record["message"]
    msg_upper = msg.upper()
    
    # Priority 1: Errors (Map ERROR/CRITICAL/FAILED to WARN for the frontend)
    if record["level"].name in ["ERROR", "CRITICAL"] or "FAILED" in msg_upper or "ERROR" in msg_upper:
        level = "WARN"
    # Priority 2: Trade Execution
    elif any(k in msg_upper for k in ["TRADE", "APPROVED", "ORDER", "EXECUTION", "TICKET="]):
        level = "TRADE"
    # Priority 3: Signals & Analysis
    elif any(k in msg_upper for k in ["SIGNAL", "REJECTED", "MARKET ANALYST", "SENTIMENT"]):
        level = "SIGNAL"
    # Priority 4: AI & ML Operations
    elif any(k in msg_upper for k in ["AI", "OLLAMA", "GROQ", "DEEPSEEK", "CLAUDE", "REPLAY", "TRAINING", "🤖", "🧠", "🔮"]):
        level = "AI"

    payload = json.dumps({
        "type":    "log",
        "time":    datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "level":   level,
        "msg":     msg,
        "agent":   record["extra"].get("agent", "SYSTEM"),
        "module":  record["name"],
    })

    # Determine which event loop to use:
    #   - Called from async context → get_running_loop() succeeds; cache it.
    #   - Called from a background thread → use the cached _main_loop with
    #     run_coroutine_threadsafe (the only safe cross-thread API).
    try:
        loop = asyncio.get_running_loop()
        if _main_loop is None:
            _main_loop = loop
        in_async = True
    except RuntimeError:
        loop = _main_loop
        in_async = False

    if loop is None or not loop.is_running():
        return  # No live event loop available — log goes to file/stdout only

    async def _safe_send(ws, data: str):
        try:
            await ws.send_text(data)
        except Exception:
            _ws_clients.discard(ws)

    for ws in list(_ws_clients):
        try:
            if in_async:
                asyncio.ensure_future(_safe_send(ws, payload))
            else:
                asyncio.run_coroutine_threadsafe(_safe_send(ws, payload), loop)
        except Exception:
            _ws_clients.discard(ws)


def setup_logging(log_level: str = "INFO"):
    logger.remove()

    # Ensure stdout can handle Unicode on Windows (cp1252 → utf-8)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # Console — coloured
    logger.add(
        sys.stdout,
        level=log_level,
        colorize=True,
        format=(
            "<green>{time:HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan> | "
            "<level>{message}</level>"
        ),
    )

    # File — daily rotation, keep 30 days
    logger.add(
        LOG_DIR / "apex_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="00:00",
        retention="30 days",
        compression="gz",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name} | {message}",
    )

    # WebSocket sink
    logger.add(_ws_sink, level="INFO", format="{message}")

    # DuckDB sink
    logger.add(_db_sink, level="DEBUG")

    logger.info("Logger initialised — level={}", log_level)


def get_agent_logger(agent_name: str):
    """Return a logger bound with agent context."""
    return logger.bind(agent=agent_name)
