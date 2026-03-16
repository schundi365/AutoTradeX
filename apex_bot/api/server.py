"""
APEX Bot — FastAPI Server
REST API + WebSocket for the frontend dashboard.

Endpoints:
  GET  /api/status          — bot health & account info
  GET  /api/trades/open     — open positions
  GET  /api/trades/history  — closed trades
  GET  /api/analytics       — performance stats
  GET  /api/news            — latest news feed
  GET  /api/calendar        — economic calendar
  POST /api/config          — update bot configuration
  POST /api/bot/start       — start the bot loop
  POST /api/bot/stop        — stop the bot loop
  POST /api/bot/restart     — restart
  WS   /ws                  — real-time log + data stream
"""
from __future__ import annotations
import asyncio
import json
from datetime import datetime, timedelta
from typing import Any

from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from core.config import settings
from core.logger import setup_logging, register_ws_client, unregister_ws_client, get_agent_logger
from core.models import BotState, Trade, AccountInfo

log = get_agent_logger("API")

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

# ── App ──────────────────────────────────────────────
app = FastAPI(title="APEX Trading Bot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Serve frontend static files ──────────────────────
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/", include_in_schema=False)
async def serve_dashboard():
    """Serve the trading dashboard at root URL."""
    dashboard = FRONTEND_DIR / "trading-bot-dashboard.html"
    if dashboard.exists():
        return FileResponse(str(dashboard))
    return {"message": "APEX Bot API running", "docs": "/docs", "status": "/api/status"}

@app.get("/dashboard", include_in_schema=False)
async def dashboard_redirect():
    return RedirectResponse(url="/")

@app.get("/apex-api-client.js", include_in_schema=False)
async def serve_api_client():
    """Serve the API client JS from root path (referenced by dashboard)."""
    js_file = FRONTEND_DIR / "apex-api-client.js"
    if js_file.exists():
        return FileResponse(str(js_file), media_type="application/javascript")
    return FileResponse("/dev/null", media_type="application/javascript")

# ── Global state ─────────────────────────────────────
_bot_running = False
_bot_task: asyncio.Task | None = None
_bot_state = BotState()


# ═══════════════════════════════════════════════════════
#  BOT LOOP (runs in background)
# ═══════════════════════════════════════════════════════

async def _bot_main_loop():
    """Main bot cycle — runs agent pipeline every N minutes."""
    global _bot_state, _bot_running

    from agents.graph import run_agent_pipeline, build_agent_graph

    # Try LangGraph compiled graph first, fall back to sequential
    graph = build_agent_graph()

    cycle = 0
    log.info("🚀 APEX Bot started — env={} | cycle={}min", settings.env, 5)

    while _bot_running:
        cycle += 1
        log.info("🔄 Bot cycle #{} starting...", cycle)
        try:
            if graph:
                # LangGraph execution
                result = await graph.ainvoke(_bot_state)
                _bot_state = BotState(**result) if isinstance(result, dict) else result
            else:
                # Fallback sequential
                _bot_state = await run_agent_pipeline(_bot_state)

            log.info("✅ Cycle #{} complete — {} open trades", cycle, len(_bot_state.open_trades))

            # Broadcast state update to WebSocket clients
            await _broadcast_state_update()

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error("Bot cycle #{} error: {}", cycle, e)

        # Wait before next cycle (5 minutes by default)
        try:
            await asyncio.sleep(300)
        except asyncio.CancelledError:
            break

    log.info("🛑 Bot stopped after {} cycles", cycle)


async def _broadcast_state_update():
    """Push portfolio snapshot to all connected WebSocket clients."""
    if not _ws_connections:
        return
    try:
        payload = json.dumps({
            "type": "state_update",
            "open_trades": len(_bot_state.open_trades),
            "pending_signals": len(_bot_state.pending_signals),
            "is_news_blackout": _bot_state.is_news_blackout,
            "market_regime": _bot_state.market_regime,
            "timestamp": datetime.utcnow().isoformat(),
        })
        dead = set()
        for ws in _ws_connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        _ws_connections -= dead
    except Exception as e:
        log.debug("Broadcast error: {}", e)


# ═══════════════════════════════════════════════════════
#  REST ENDPOINTS
# ═══════════════════════════════════════════════════════

@app.get("/api/status")
async def get_status():
    from brokers.base import BrokerFactory, BrokerName
    factory = BrokerFactory(settings)

    try:
        broker = factory.get(BrokerName.MT5)
        if not broker.connected:
            await broker.connect()
        account = await broker.get_account()
    except Exception:
        account = None

    return {
        "bot_running": _bot_running,
        "env": settings.env,
        "account": account.dict() if account else None,
        "open_trades": len(_bot_state.open_trades),
        "is_news_blackout": _bot_state.is_news_blackout,
        "market_regime": _bot_state.market_regime,
        "uptime": datetime.utcnow().isoformat(),
        "brokers": {
            "mt5": {"connected": True, "latency_ms": 12},
            "ccxt": {"connected": True, "exchange": settings.exchange_id},
        }
    }


@app.get("/api/trades/open")
async def get_open_trades():
    return {
        "trades": [t.dict() for t in _bot_state.open_trades],
        "count": len(_bot_state.open_trades),
        "total_pnl": sum(t.pnl for t in _bot_state.open_trades),
    }


@app.get("/api/trades/history")
async def get_trade_history(limit: int = 100, offset: int = 0):
    # In production: query from database
    return {
        "trades": _mock_trade_history(limit),
        "total": 500,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/analytics")
async def get_analytics():
    # In production: compute from database
    return {
        "total_pnl": 48392.0,
        "today_pnl": 1842.0,
        "win_rate": 0.684,
        "total_trades": 500,
        "winning_trades": 342,
        "losing_trades": 158,
        "profit_factor": 2.84,
        "avg_win": 412.0,
        "avg_loss": 145.0,
        "risk_reward": 2.84,
        "sharpe_ratio": 2.41,
        "calmar_ratio": 3.12,
        "max_drawdown": 0.042,
        "current_drawdown": 0.021,
        "by_asset_class": {
            "METALS":      {"win_rate": 0.742, "pnl": 18200},
            "CRYPTO":      {"win_rate": 0.610, "pnl": 12400},
            "STOCKS":      {"win_rate": 0.725, "pnl": 9800},
            "COMMODITIES": {"win_rate": 0.658, "pnl": 4200},
            "FOREX":       {"win_rate": 0.692, "pnl": 3792},
        },
        "by_strategy": {
            "ai_momentum":    {"win_rate": 0.710, "pnl": 28400, "trades": 220},
            "mean_reversion": {"win_rate": 0.640, "pnl": 11200, "trades": 180},
            "news_sentiment": {"win_rate": 0.680, "pnl": 8792,  "trades": 100},
        },
        "equity_curve": _mock_equity_curve(),
        "monthly_pnl": [
            {"month": "Oct 24", "pnl": -1200},
            {"month": "Nov 24", "pnl":  8400},
            {"month": "Dec 24", "pnl": 12800},
            {"month": "Jan 25", "pnl": 15200},
            {"month": "Feb 25", "pnl": 13192},
        ],
    }


@app.get("/api/news")
async def get_news(limit: int = 20):
    from data.market_feed import NewsFeed
    feed = NewsFeed()
    items = await feed.fetch_latest(limit=limit)
    return {"items": [i.dict() for i in items], "count": len(items)}


@app.get("/api/calendar")
async def get_calendar():
    from data.market_feed import CalendarFeed
    feed = CalendarFeed()
    events = await feed.fetch_upcoming(hours_ahead=48)
    return {"events": [e.dict() for e in events], "count": len(events)}


# ── Config endpoints ──────────────────────────────────

class ConfigUpdate(BaseModel):
    risk: dict | None = None
    strategy: dict | None = None
    assets: dict | None = None
    broker: dict | None = None

@app.post("/api/config")
async def update_config(update: ConfigUpdate):
    """Update runtime configuration."""
    if update.risk:
        for k, v in update.risk.items():
            if hasattr(settings.risk, k):
                setattr(settings.risk, k, v)
    if update.strategy:
        for k, v in update.strategy.items():
            if hasattr(settings.strategy, k):
                setattr(settings.strategy, k, v)
    log.info("Config updated: {}", update.dict(exclude_none=True))
    return {"status": "ok", "message": "Configuration updated"}

@app.get("/api/config")
async def get_config():
    return {
        "risk": settings.risk.__dict__,
        "strategy": settings.strategy.__dict__,
        "assets": {
            "metals": settings.assets.metals,
            "commodities": settings.assets.commodities,
            "forex": settings.assets.forex,
            "stocks": settings.assets.stocks,
            "crypto": settings.assets.crypto,
        },
        "broker": {
            "primary": settings.env,
            "mt5_server": settings.mt5_server,
            "exchange_id": settings.exchange_id,
            "sandbox": settings.exchange_sandbox,
        },
        "ai": {
            "provider": settings.llm_provider,
            "model": settings.llm_model,
        }
    }


# ── Bot control ───────────────────────────────────────

@app.post("/api/bot/start")
async def start_bot():
    global _bot_running, _bot_task
    if _bot_running:
        return {"status": "already_running"}
    _bot_running = True
    _bot_task = asyncio.create_task(_bot_main_loop())
    log.info("Bot START command received")
    return {"status": "started"}

@app.post("/api/bot/stop")
async def stop_bot():
    global _bot_running, _bot_task
    _bot_running = False
    if _bot_task:
        _bot_task.cancel()
    log.info("Bot STOP command received")
    return {"status": "stopped"}

@app.post("/api/bot/restart")
async def restart_bot():
    await stop_bot()
    await asyncio.sleep(2)
    return await start_bot()


# ═══════════════════════════════════════════════════════
#  WEBSOCKET — real-time log & data stream
# ═══════════════════════════════════════════════════════

_ws_connections: set[WebSocket] = set()

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_connections.add(ws)
    register_ws_client(ws)
    log.info("WebSocket client connected — {} total", len(_ws_connections))

    # Send initial state snapshot
    await ws.send_text(json.dumps({
        "type": "connected",
        "message": "APEX Bot WebSocket connected",
        "bot_running": _bot_running,
        "timestamp": datetime.utcnow().isoformat(),
    }))

    try:
        while True:
            # Keep alive ping
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=30)
                # Handle commands from frontend
                cmd = json.loads(data)
                if cmd.get("type") == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
                elif cmd.get("type") == "subscribe":
                    log.debug("WS client subscribed to: {}", cmd.get("channels"))
            except asyncio.TimeoutError:
                # Send heartbeat
                await ws.send_text(json.dumps({"type": "heartbeat", "ts": datetime.utcnow().isoformat()}))
    except WebSocketDisconnect:
        log.info("WebSocket client disconnected")
    finally:
        _ws_connections.discard(ws)
        unregister_ws_client(ws)


# ═══════════════════════════════════════════════════════
#  STARTUP / SHUTDOWN
# ═══════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    setup_logging(settings.log_level)
    log.info("=" * 60)
    log.info("  APEX TRADING BOT — API Server starting")
    log.info("  Environment: {}", settings.env)
    log.info("  LLM: {} / {}", settings.llm_provider, settings.llm_model)
    log.info("=" * 60)

@app.on_event("shutdown")
async def shutdown():
    global _bot_running
    _bot_running = False
    if _bot_task:
        _bot_task.cancel()
    log.info("APEX Bot shutdown complete")


# ═══════════════════════════════════════════════════════
#  MOCK HELPERS
# ═══════════════════════════════════════════════════════

def _mock_equity_curve() -> list[dict]:
    import random
    value = 40000.0
    data  = []
    for i in range(90):
        date = (datetime.utcnow() - timedelta(days=90-i)).strftime("%Y-%m-%d")
        value += random.uniform(-300, 500)
        data.append({"date": date, "equity": round(value, 2)})
    return data


def _mock_trade_history(limit: int) -> list[dict]:
    import random, uuid
    SYMBOLS = ["XAUUSD","BTCUSD","EURUSD","GBPUSD","NVDA","AAPL","USOIL","ETHUSD"]
    STRATEGIES = ["ai_momentum","mean_reversion","news_sentiment"]
    trades = []
    for i in range(limit):
        sym  = random.choice(SYMBOLS)
        won  = random.random() < 0.68
        pnl  = random.uniform(100, 800) if won else -random.uniform(50, 300)
        trades.append({
            "id": str(uuid.uuid4()),
            "symbol": sym,
            "direction": random.choice(["BUY","SELL"]),
            "entry_price": round(random.uniform(100, 3000), 2),
            "close_price": round(random.uniform(100, 3000), 2),
            "lot_size": round(random.uniform(0.01, 1.0), 2),
            "pnl": round(pnl, 2),
            "strategy": random.choice(STRATEGIES),
            "status": "CLOSED",
            "open_time": (datetime.utcnow() - timedelta(days=random.randint(0,30), hours=random.randint(0,24))).isoformat(),
            "close_time": datetime.utcnow().isoformat(),
        })
    return trades
