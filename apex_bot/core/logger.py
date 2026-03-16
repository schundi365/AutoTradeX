"""
APEX Bot — Logger
Structured logging with loguru. Broadcasts log events to
connected WebSocket clients so the frontend Log panel updates live.
"""
from __future__ import annotations
import sys
import asyncio
import json
from datetime import datetime
from pathlib import Path
from loguru import logger

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ── WebSocket broadcast registry ────────────────────────
_ws_clients: set = set()

def register_ws_client(ws):
    _ws_clients.add(ws)

def unregister_ws_client(ws):
    _ws_clients.discard(ws)


# ── Custom log sink → broadcasts to frontend ────────────
def _ws_sink(message):
    record = message.record
    level_map = {
        "INFO":    "INFO",
        "WARNING": "WARN",
        "ERROR":   "WARN",
        "SUCCESS": "TRADE",
        "DEBUG":   "INFO",
    }
    level = level_map.get(record["level"].name, "INFO")

    # Detect special prefixes set by agents
    msg = record["message"]
    if msg.startswith("SIGNAL"):     level = "SIGNAL"
    elif msg.startswith("TRADE"):    level = "TRADE"
    elif msg.startswith("🤖") or msg.startswith("🧠") or msg.startswith("🔮"): level = "AI"

    payload = json.dumps({
        "type":    "log",
        "time":    datetime.utcnow().strftime("%H:%M:%S"),
        "level":   level,
        "msg":     msg,
        "agent":   record["extra"].get("agent", "SYSTEM"),
        "module":  record["name"],
    })

    dead = set()
    for ws in _ws_clients:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(ws.send_text(payload))
        except Exception:
            dead.add(ws)
    _ws_clients -= dead


def setup_logging(log_level: str = "INFO"):
    logger.remove()

    # Console — coloured
    logger.add(
        sys.stdout,
        level=log_level,
        colorize=True,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
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
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}",
    )

    # WebSocket sink
    logger.add(_ws_sink, level="INFO", format="{message}")

    logger.info("Logger initialised — level={}", log_level)


def get_agent_logger(agent_name: str):
    """Return a logger bound with agent context."""
    return logger.bind(agent=agent_name)
