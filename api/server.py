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
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.config import settings
from core.logger import setup_logging, register_ws_client, unregister_ws_client, get_agent_logger
from core.models import BotState, Trade, AccountInfo, TradeStatus
from utils.orchestrator import orchestrator

log = get_agent_logger("API")

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


# ── Stdout bridge for background training scripts ─────
import io as _io
import sys as _sys

class _LogBridge(_io.TextIOBase):
    """Pipe print() output from training scripts into loguru so it reaches the WebSocket dashboard."""
    def __init__(self, prefix: str = "[TRAINING]"):
        self._prefix = prefix
        self._buf = ""

    def write(self, text: str) -> int:
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.rstrip()
            if line:
                log.info("{} {}", self._prefix, line)
        return len(text)

    def flush(self):
        if self._buf.strip():
            log.info("{} {}", self._prefix, self._buf.strip())
            self._buf = ""

# ── App ──────────────────────────────────────────────
app = FastAPI(title="APEX Trading Bot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Include dashboard routes ──────────────────────────
from api.dashboard_routes import dashboard_router
app.include_router(dashboard_router)

# ── Include APEX Health API routes ────────────────────
from api.apex_health_api import router as apex_health_router
app.include_router(apex_health_router)

# ── Include ML API routes ──────────────────────────────
from api.ml_endpoints import router as ml_router
app.include_router(ml_router)

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

@app.get("/apex-health-interactive.js", include_in_schema=False)
async def serve_apex_health_interactive():
    """Serve the APEX Health interactive JS module."""
    js_file = FRONTEND_DIR / "apex-health-interactive.js"
    if js_file.exists():
        return FileResponse(str(js_file), media_type="application/javascript")
    return FileResponse("/dev/null", media_type="application/javascript")

# ── Global state ─────────────────────────────────────
_bot_running = False
_bot_task: asyncio.Task | None = None
_bot_state = BotState()
_scheduler = AsyncIOScheduler()


# ═══════════════════════════════════════════════════════
#  BOT LOOP (runs in background)
# ═══════════════════════════════════════════════════════

async def _bot_main_loop():
    """Main bot cycle — runs agent pipeline every N minutes."""
    global _bot_state, _bot_running

    from agents.graph import run_agent_pipeline, build_agent_graph
    from core.bot_lifecycle import bot_manager

    # Try LangGraph compiled graph first, fall back to sequential
    graph = build_agent_graph()

    cycle = 0
    log.info("🚀 APEX Bot started — env={} | cycle={}min", settings.env, settings.bot_cycle_minutes)

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

            # Sync with Broker (Check if trades were closed by SL/TP on broker side)
            await _sync_trades_with_broker()

            log.info("✅ Cycle #{} complete — {} open trades", cycle, len(_bot_state.open_trades))

            # Update bot lifecycle state
            bot_manager.update_positions(
                active=len(_bot_state.open_trades),
                pending=len(_bot_state.pending_signals)
            )

            # Broadcast state update to WebSocket clients
            await _broadcast_state_update()

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error("Bot cycle #{} error: {}", cycle, e)
            bot_manager.set_error(str(e))

        # Wait before next cycle (configurable via BOT_CYCLE_MINUTES env var)
        try:
            await asyncio.sleep(settings.bot_cycle_minutes * 60)
        except asyncio.CancelledError:
            break

    log.info("🛑 Bot stopped after {} cycles", cycle)


async def _sync_trades_with_broker():
    """Detect trades closed by the broker (SL/TP) and move to history."""
    from brokers.base import BrokerFactory
    from data.storage import storage
    
    factory = BrokerFactory(settings)
    mt5 = factory.get("MT5")
    
    # Skip sync if MT5 not connected and don't try to reconnect (prevents blocking)
    if not mt5.connected:
        log.debug("[SYNC] MT5 not connected, skipping trade sync")
        return
        
    try:
        # Wrap entire sync operation in timeout to prevent blocking
        real_open = await asyncio.wait_for(mt5.get_open_trades(), timeout=5.0)
        real_ids = {str(t.broker_order_id) for t in real_open if t.broker_order_id}
        
        still_open = []
        for trade in _bot_state.open_trades:
            ticket = str(trade.broker_order_id or "")
            if ticket and ticket in real_ids:
                # Still open, update current price + pnl
                matching = next(t for t in real_open if str(t.broker_order_id) == ticket)
                trade.current_price = matching.current_price
                trade.pnl           = matching.pnl
                trade.stop_loss     = matching.stop_loss
                trade.take_profit   = matching.take_profit
                still_open.append(trade)
            else:
                # CLOSED externally (SL/TP/Manual)
                log.info("🎯 [SYNC] Trade {} {} detected as CLOSED by broker. Syncing to history.", trade.symbol, ticket)
                trade.status = TradeStatus.CLOSED
                trade.close_time = datetime.utcnow()
                storage.store_trade(trade)
                
        _bot_state.open_trades = still_open
        
    except asyncio.TimeoutError:
        log.warning("[SYNC] Trade sync timed out after 5 seconds, skipping")
    except Exception as e:
        log.error("Error syncing trades: {}", e)

def _clean_val(val, default=0.0):
    """Recursively ensure value is JSON compliant (not nan/inf)."""
    if val is None:
        return default
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return default
        return val
    if isinstance(val, dict):
        return {k: _clean_val(v, default) for k, v in val.items()}
    if isinstance(val, list):
        return [_clean_val(v, default) for v in val]
    return val

async def _broadcast_state_update():
    """Push portfolio snapshot to all connected WebSocket clients."""
    global _ws_connections
    if not _ws_connections:
        return
    try:
        # Calculate some quick stats for the UI
        balance = _bot_state.account_info.balance if _bot_state.account_info else 50000.0
        equity = _bot_state.account_info.equity if _bot_state.account_info else balance + sum(t.pnl for t in _bot_state.open_trades)
        
        payload = json.dumps({
            "type": "state_update",
            "open_trades": len(_bot_state.open_trades),
            "pending_signals": len(_bot_state.pending_signals),
            "is_news_blackout": _bot_state.is_news_blackout,
            "market_regime": _bot_state.market_regime,
            "equity": round(_clean_val(equity), 2),
            "pnl": round(_clean_val(equity - balance), 2),
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

# ── Ticker strip live prices ─────────────────────────────────────────────────
_ticker_cache: dict = {"data": [], "ts": 0.0, "refreshing": False}

# Display symbol → yfinance ticker
_TICKER_SYMBOLS: dict[str, str] = {
    "XAUUSD": "GC=F",
    "BTCUSD": "BTC-USD",
    "EURUSD": "EURUSD=X",
    "USOIL":  "CL=F",
    "XAGUSD": "SI=F",
    "ETHUSD": "ETH-USD",
    "GBPUSD": "GBPUSD=X",
    "NVDA":   "NVDA",
    "AAPL":   "AAPL",
    "NATGAS": "NG=F",
    "USDJPY": "USDJPY=X",
    "SPX500": "^GSPC",
}


def _refresh_ticker_cache() -> None:
    """Fetch latest daily prices from yfinance and update _ticker_cache."""
    _ticker_cache["refreshing"] = True
    try:
        import yfinance as yf
        yf_syms = list(_TICKER_SYMBOLS.values())
        # Single batched request — period=5d gives enough history for prev-close
        raw = yf.download(
            yf_syms, period="5d", interval="1d",
            progress=False, group_by="ticker", auto_adjust=True,
        )
        result = []
        for sym, yf_sym in _TICKER_SYMBOLS.items():
            try:
                closes = raw[yf_sym]["Close"].dropna()
                if len(closes) >= 2:
                    price = float(closes.iloc[-1])
                    prev  = float(closes.iloc[-2])
                    chg   = (price - prev) / prev * 100 if prev > 0 else 0.0
                    result.append({
                        "sym":   sym,
                        "price": round(price, 6),
                        "chg":   round(chg, 2),
                        "dir":   "up" if chg >= 0 else "dn",
                    })
            except Exception:
                pass
        if result:
            _ticker_cache["data"] = result
            _ticker_cache["ts"]   = __import__("time").time()
    except Exception as e:
        log.warning("Ticker refresh failed: {}", e)
    finally:
        _ticker_cache["refreshing"] = False


@app.get("/api/ticker")
async def get_ticker():
    """Return live ticker prices (yfinance, cached 60 s).

    Uses stale-while-revalidate: always responds immediately, triggers a
    background refresh when cache is older than 60 seconds.
    """
    import time, threading
    if time.time() - _ticker_cache["ts"] >= 60 and not _ticker_cache["refreshing"]:
        threading.Thread(target=_refresh_ticker_cache, daemon=True).start()
    return {"items": _ticker_cache["data"], "stale": _ticker_cache["ts"] == 0.0}


@app.get("/api/status")
async def get_status():
    from brokers.base import BrokerFactory, BrokerName
    from data.storage import storage
    
    factory = BrokerFactory(settings)
    account = None
    broker_connected = False
    
    try:
        broker = factory.get(BrokerName.MT5)
        if not broker.connected:
            # Don't try to reconnect in status endpoint - it blocks everything
            # Just report disconnected status
            log.debug("MT5 not connected in get_status (skipping reconnect attempt)")
        
        if broker.connected:
            # Wrap in timeout to prevent blocking
            try:
                account = await asyncio.wait_for(broker.get_account(), timeout=2.0)
                broker_connected = True
                log.debug("MT5 account fetched: balance=${:.2f}", account.balance if account else 0)
            except asyncio.TimeoutError:
                log.warning("MT5 get_account() timed out after 2 seconds")
                broker_connected = False
        else:
            log.debug("MT5 not connected in get_status")
    except Exception as e:
        log.error("Error fetching MT5 account in get_status: {}", e)
        account = None

    # Get performance stats
    perf = await _get_comprehensive_analytics()

    return _clean_val({
        "bot_running": _bot_running,
        "env": settings.env,
        "account": {
            "balance": account.balance if account else 10000.0,
            "equity": account.equity if account else 10000.0,
            "margin_pct": account.margin_pct if account else 0.0,
            "currency": account.currency if account else "USD"
        },
        "performance": perf,
        "open_trades": len(_bot_state.open_trades),
        "is_news_blackout": _bot_state.is_news_blackout,
        "market_regime": _bot_state.market_regime,
        "uptime": datetime.now(timezone.utc).isoformat(),
        "brokers": {
            "mt5": {"connected": broker_connected, "latency_ms": 12},
            "ccxt": {"connected": True, "exchange": settings.exchange_id},
        }
    })


@app.get("/api/trades/open")
async def get_open_trades():
    # Always fetch live from the broker for accuracy — _bot_state may be stale or empty.
    from brokers.base import BrokerFactory
    from data.storage import storage
    
    live_trades = []
    try:
        global _posmgr_broker
        if _posmgr_broker is None:
            _posmgr_broker = BrokerFactory(settings).get("MT5")
        
        # Skip MT5 connection if not already connected (prevents blocking)
        if not _posmgr_broker.connected:
            log.debug("[API] MT5 not connected, using bot state for open trades")
            live_trades = _bot_state.open_trades
        else:
            # Wrap in timeout to prevent blocking
            live_trades = await asyncio.wait_for(_posmgr_broker.get_open_trades(), timeout=3.0)
            live_ids = {str(t.broker_order_id) for t in live_trades if t.broker_order_id}

            # 1. Reconcile known bot state with live MT5 state
            still_open = []
            for bt in _bot_state.open_trades:
                ticket = str(bt.broker_order_id or "")
                if ticket and ticket in live_ids:
                    # Match found, update from live data
                    lt = next(t for t in live_trades if str(t.broker_order_id) == ticket)
                    bt.pnl = lt.pnl
                    bt.current_price = lt.current_price
                    bt.stop_loss = lt.stop_loss
                    bt.take_profit = lt.take_profit
                    still_open.append(bt)
                else:
                    # Trade in bot state but NOT in live MT5 -> It was closed
                    log.info("🎯 [API] Detected external closure of {} {} during fetch.", bt.symbol, ticket)
                    bt.status = TradeStatus.CLOSED
                    bt.close_time = datetime.utcnow()
                    storage.store_trade(bt)

            # 2. Add any live trades MT5 has that our _bot_state DID NOT know about (e.g. manually opened or from previous session)
            known_ids = {str(t.broker_order_id) for t in still_open if t.broker_order_id}
            for lt in live_trades:
                if str(lt.broker_order_id) not in known_ids:
                    still_open.append(lt)

            _bot_state.open_trades = still_open
            live_trades = still_open # return reconciled list

    except asyncio.TimeoutError:
        log.warning("[API] get_open_trades timed out after 3 seconds, using bot state")
        live_trades = _bot_state.open_trades
    except Exception as e:
        log.warning("[API] get_open_trades sync failed ({}), using bot state", e)
        live_trades = _bot_state.open_trades

    return _clean_val({
        "trades": [t.dict() for t in live_trades],
        "count": len(live_trades),
        "total_pnl": sum(t.pnl for t in live_trades),
    })


@app.get("/api/trades/history")
async def get_trade_history(limit: int = 100, offset: int = 0):
    from data.storage import storage
    df = storage.get_trade_history(limit)
    return _clean_val({
        "trades": df.to_dict('records'),
        "total": len(df),
        "limit": limit,
        "offset": offset,
    })


@app.post("/api/trades/sync-mt5")
async def sync_mt5_trades_endpoint(background_tasks: BackgroundTasks):
    """
    Sync closed trades from MT5 to trade journal.
    Runs in background to avoid blocking other requests.
    """
    # Start sync in background
    background_tasks.add_task(run_mt5_sync)
    
    return _clean_val({
        "status": "started",
        "message": "MT5 sync started in background. Check logs for progress."
    })


def run_mt5_sync():
    """Background task to sync MT5 trades"""
    try:
        import MetaTrader5 as mt5
        import pandas as pd
    except ImportError as e:
        log.error(f"Required package not installed: {e}")
        return
    
    # Initialize MT5
    if not mt5.initialize(
        login=settings.mt5_login,
        password=settings.mt5_password,
        server=settings.mt5_server
    ):
        log.error(f"MT5 initialization failed: {mt5.last_error()}")
        return
    
    try:
        from datetime import timedelta
        from core.decision_tracer import DecisionType
        from data.trade_journal import trade_journal, TradeJournalEntry, DecisionMaker
        
        log.info("Starting MT5 sync...")
        
        # Get closed trades from last 7 days (reduced for performance)
        from_date = datetime.now() - timedelta(days=7)
        to_date = datetime.now()
        
        deals = mt5.history_deals_get(from_date, to_date)
        
        if deals is None or len(deals) == 0:
            log.info("No deals found in MT5 history")
            return
        
        log.info(f"Found {len(deals)} deals in MT5 history")
        
        # Get existing entries in batch
        existing_ids = set()
        try:
            # Use get_decision_history to get recent decisions
            recent_decisions = trade_journal.get_decision_history(limit=1000)
            if not recent_decisions.empty:
                existing_ids = {
                    f"mt5_{row['trade_id']}" 
                    for _, row in recent_decisions.iterrows() 
                    if pd.notna(row.get('trade_id'))
                }
                log.info(f"Found {len(existing_ids)} existing MT5 entries")
        except Exception as e:
            log.warning(f"Could not load existing entries: {e}")
        
        # Group deals by position ticket
        positions = {}
        for deal in deals:
            if deal.type not in [mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL]:
                continue
            
            position_id = deal.position_id
            if position_id not in positions:
                positions[position_id] = []
            positions[position_id].append(deal)
        
        log.info(f"Grouped into {len(positions)} positions")
        
        synced_count = 0
        skipped_count = 0
        
        for position_id, deals_list in positions.items():
            deals_list.sort(key=lambda d: d.time)
            
            if len(deals_list) < 2:
                continue
            
            entry_deal = deals_list[0]
            exit_deal = deals_list[-1]
            
            # Fast set lookup
            entry_id = f"mt5_{position_id}"
            if entry_id in existing_ids:
                skipped_count += 1
                continue
            
            pnl = exit_deal.profit
            direction = "BUY" if entry_deal.type == mt5.DEAL_TYPE_BUY else "SELL"
            
            entry_time = datetime.fromtimestamp(entry_deal.time)
            exit_time = datetime.fromtimestamp(exit_deal.time)
            holding_time_seconds = int((exit_time - entry_time).total_seconds())
            
            # Create journal entry
            entry = TradeJournalEntry(
                entry_id=entry_id,
                timestamp=exit_time,
                decision_type=DecisionType.TRADE_CLOSED,
                symbol=entry_deal.symbol,
                direction=direction,
                market_regime="UNKNOWN",
                risk_appetite="UNKNOWN",
                liquidity_conditions="UNKNOWN",
                is_news_blackout=False,
                signal_score=0.0,
                confidence=1.0,
                risk_reward=0.0,
                indicators={},
                decision="GO",
                reasoning=f"Synced from MT5 position {position_id}",
                decision_maker=DecisionMaker.SYSTEM,
                trade_id=str(position_id),
                entry_price=entry_deal.price,
                exit_price=exit_deal.price,
                pnl=pnl,
                holding_time_seconds=holding_time_seconds,
                exit_reason="MT5_CLOSE"
            )
            
            # Record to journal
            trade_journal.record_decision(entry)
            synced_count += 1
        
        log.success(f"✓ MT5 sync complete: {synced_count} trades synced, {skipped_count} skipped")
        
    except Exception as e:
        log.error(f"Error syncing MT5 trades: {e}")
        import traceback
        log.debug(traceback.format_exc())
    finally:
        mt5.shutdown()


@app.get("/api/decisions")
async def get_decision_history(limit: int = 50):
    """
    Get bot decision history (GO/NOGO decisions from orchestrator).
    Returns decisions from bot_decisions table in DuckDB.
    """
    from memory.duckdb_store import DuckDBStore
    
    try:
        store = DuckDBStore(settings.training.duckdb_path)
        await store.start()
        
        # Try bot_decisions table first (new format with timing)
        try:
            rows = store.execute_read("""
                SELECT 
                    timestamp,
                    symbol,
                    decision,
                    confidence,
                    outcome,
                    decision_time_ms
                FROM bot_decisions
                ORDER BY timestamp DESC
                LIMIT ?
            """, [limit])
            
            # If bot_decisions has data, use it
            if rows and len(rows) > 0:
                decisions = []
                for row in rows:
                    timestamp, symbol, decision, confidence, outcome, decision_time_ms = row
                    
                    decisions.append({
                        "timestamp": timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp),
                        "symbol": symbol,
                        "decision": decision,
                        "confidence": confidence or 0.0,
                        "outcome": outcome or "PENDING",
                        "decision_time_ms": decision_time_ms or 0,
                        "decision_time_display": f"{decision_time_ms / 1000:.2f}s" if decision_time_ms else "N/A"
                    })
                
                await store.stop()
                
                return _clean_val({
                    "decisions": decisions,
                    "total": len(decisions),
                    "limit": limit,
                })
            else:
                # bot_decisions is empty, fall back to decision_log
                raise Exception("bot_decisions empty, using fallback")
            
        except Exception as e:
            # Fall back to decision_log table (old format)
            log.debug("Using decision_log fallback: {}", e)
            rows = store.execute_read("""
                SELECT 
                    timestamp,
                    symbol,
                    context_json,
                    outcome,
                    final_pnl
                FROM decision_log
                ORDER BY timestamp DESC
                LIMIT ?
            """, [limit])
            
            await store.stop()
            
            decisions = []
            for row in rows:
                timestamp, symbol, context_json, outcome, final_pnl = row
                context = json.loads(context_json) if context_json else {}
                
                decisions.append({
                    "timestamp": timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp),
                    "symbol": symbol,
                    "decision": context.get("decision", "UNKNOWN"),
                    "confidence": context.get("confidence", 0.0),
                    "indicators": {
                        "rsi": context.get("rsi", 0),
                        "adx": context.get("adx", 0),
                        "atr_pct": context.get("atr_pct", 0.0),
                    },
                    "reasoning": context.get("reasoning", ""),
                    "outcome": outcome or "PENDING",
                    "decision_time_ms": 0,
                    "decision_time_display": "N/A"
                })
            
            return _clean_val({
                "decisions": decisions,
                "total": len(decisions),
                "limit": limit,
            })
        
    except Exception as e:
        log.warning("Failed to fetch decision history: {}", e)
        # Return empty list if table doesn't exist yet
        return {
            "decisions": [],
            "total": 0,
            "limit": limit,
        }


async def _get_comprehensive_analytics() -> dict:
    """Consolidates logic for merging DB, MT5 history, and open P&L for a complete picture."""
    from data.storage import storage
    from brokers.base import BrokerFactory
    import math as _math
    from datetime import date as _date

    # 1. Local DB closed trades
    db_stats = storage.get_analytics()
    trades = db_stats.get("trades", [])

    # 2. Supplement with MT5 deal history if DB is sparse (< 5 closed trades)
    if len(trades) < 5:
        try:
            global _posmgr_broker
            if _posmgr_broker is None:
                _posmgr_broker = BrokerFactory(settings).get("MT5")
            
            # Skip MT5 if not connected (prevents blocking)
            if _posmgr_broker.connected:
                # Wrap in timeout to prevent blocking
                mt5_trades = await asyncio.wait_for(_posmgr_broker.get_deal_history(days=90), timeout=3.0)
                if mt5_trades:
                    # Merge: deduplicate by id, prefer db trades
                    existing_ids = {str(t.get("id", "")) for t in trades}
                    for t in mt5_trades:
                        if str(t.get("id", "")) not in existing_ids:
                            trades.append(t)
            else:
                log.debug("[ANALYTICS] MT5 not connected, skipping deal history fetch")
        except asyncio.TimeoutError:
            log.warning("[ANALYTICS] MT5 deal history fetch timed out after 3 seconds")
        except Exception as e:
            log.warning("[ANALYTICS] MT5 deal history fetch failed: {}", e)

    # 3. Also include unrealized P&L from current open positions
    open_pnl = sum(t.pnl for t in _bot_state.open_trades)

    if not trades:
        return {
            "total_pnl":    open_pnl,
            "today_pnl":    open_pnl,
            "win_rate":     0.0,
            "total_trades": 0,
            "profit_factor":0.0,
            "max_drawdown": 0.0,
            "current_drawdown": 0.0,
            "sharpe_ratio": 0.0,
            "equity_curve": [],
            "by_asset_class": {},
            "by_strategy":  {},
            "open_pnl":      open_pnl,
        }

    # 4. Compute analytics from merged trade list
    def _c(v):
        return v if not (_math.isnan(v) or _math.isinf(v)) else 0.0

    pnls = [float(t.get("pnl", 0.0)) for t in trades]
    won  = [p for p in pnls if p > 0]
    lost = [p for p in pnls if p <= 0]
    total_pnl    = sum(pnls) + open_pnl
    win_rate     = len(won) / len(pnls) if pnls else 0.0
    gross_profit = sum(won)
    gross_loss   = abs(sum(lost))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0.0

    # Max drawdown
    cum, peak, max_dd = 0.0, 0.0, 0.0
    for p in pnls:
        cum  += p
        peak  = max(peak, cum)
        max_dd = max(max_dd, peak - cum)

    # Sharpe
    if len(pnls) > 1:
        mean_p = sum(pnls) / len(pnls)
        variance = sum((p - mean_p) ** 2 for p in pnls) / len(pnls)
        std_p = variance ** 0.5
        sharpe = (mean_p / std_p * (252 ** 0.5)) if std_p > 0 else 0.0
    else:
        sharpe = 0.0

    # Today's P&L
    today_str = _date.today().isoformat()
    today_pnl = sum(
        float(t.get("pnl", 0.0)) for t in trades
        if str(t.get("close_time", "")).startswith(today_str)
    ) + open_pnl

    # Equity curve
    equity_curve = []
    eq = 0.0
    for t in sorted(trades, key=lambda x: x.get("close_time", "")):
        eq += float(t.get("pnl", 0.0))
        equity_curve.append({"date": str(t.get("close_time", ""))[:16], "equity": round(eq, 2)})

    # By asset class
    by_ac: dict = {}
    for t in trades:
        ac = str(t.get("asset_class", "FOREX")).upper()
        if ac not in by_ac:
            by_ac[ac] = {"total": 0, "won": 0, "pnl": 0.0}
        by_ac[ac]["total"] += 1
        by_ac[ac]["pnl"]   += float(t.get("pnl", 0.0))
        if float(t.get("pnl", 0.0)) > 0:
            by_ac[ac]["won"] += 1
    by_asset_class = {
        ac: {"win_rate": s["won"] / s["total"] if s["total"] else 0.0,
             "pnl": s["pnl"], "count": s["total"]}
        for ac, s in by_ac.items()
    }

    # By strategy
    by_strat: dict = {}
    for t in trades:
        st = str(t.get("strategy", "unknown") or "unknown").lower()
        if st not in by_strat:
            by_strat[st] = {"total": 0, "won": 0, "pnl": 0.0}
        by_strat[st]["total"] += 1
        by_strat[st]["pnl"]   += float(t.get("pnl", 0.0))
        if float(t.get("pnl", 0.0)) > 0:
            by_strat[st]["won"] += 1
    by_strategy = {
        st: {"win_rate": s["won"] / s["total"] if s["total"] else 0.0,
             "pnl": s["pnl"], "count": s["total"]}
        for st, s in by_strat.items()
    }

    return {
        "total_pnl":     _c(total_pnl),
        "today_pnl":     _c(today_pnl),
        "win_rate":      _c(win_rate),
        "total_trades":  len(trades),
        "profit_factor": _c(profit_factor),
        "max_drawdown":  _c(max_dd),
        "current_drawdown": _c(max(0.0, peak - (cum + open_pnl))),
        "sharpe_ratio":  _c(sharpe),
        "equity_curve":  equity_curve,
        "by_asset_class": by_asset_class,
        "by_strategy":   by_strategy,
        "open_pnl":      _c(open_pnl),
    }


@app.get("/api/analytics")
async def get_analytics():
    stats = await _get_comprehensive_analytics()
    return _clean_val(stats)

def _get_live_equity_curve(trades: list) -> list[dict]:
    """Generates equity points from closed trades."""
    equity = 40000.0 # starting base
    points = [{"date": "Initial", "equity": equity}]
    for t in sorted(trades, key=lambda x: x['close_time']):
        equity += t['pnl']
        points.append({
            "date": t['close_time'].strftime("%H:%M") if hasattr(t['close_time'], 'strftime') else str(t['close_time']),
            "equity": round(equity, 2)
        })
    return points


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


@app.get("/api/sentiment/latest")
async def get_latest_sentiment():
    """Fetch the absolute latest structured sentiment analysis from DuckDB."""
    from memory.duckdb_store import DuckDBStore
    store = DuckDBStore(settings.training.duckdb_path)
    try:
        rows = store.execute_read(
            "SELECT timestamp, news_summary, adjustments_json FROM sentiment_analysis ORDER BY timestamp DESC LIMIT 1"
        )
        if not rows:
            return {"status": "empty", "message": "No sentiment analysis found yet."}
        
        ts, summary, adj_json = rows[0]
        return {
            "status": "success",
            "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            "news_summary": summary,
            "adjustments": json.loads(adj_json) if adj_json else []
        }
    except Exception as e:
        log.error("Failed to fetch latest sentiment: {}", e)
        return {"status": "error", "message": str(e)}


# ── Config endpoints ──────────────────────────────────

class ConfigUpdate(BaseModel):
    risk: dict | None = None
    strategy: dict | None = None
    assets: dict | None = None
    broker: dict | None = None
    groq_api_key: str | None = None
    deepseek_api_key: str | None = None
    anthropic_api_key: str | None = None
    ollama_model: str | None = None

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
                # Special handling for timeframes to ensure it's a list
                if k == "timeframes" and isinstance(v, list):
                    settings.strategy.timeframes = v
                    log.info("Updated analysis timeframes: {}", v)
    if update.ollama_model:
        settings.ollama_model = update.ollama_model
        os.environ["OLLAMA_MODEL"] = update.ollama_model
    if update.groq_api_key:
        settings.groq_api_key = update.groq_api_key
        os.environ["GROQ_API_KEY"] = update.groq_api_key
    if update.deepseek_api_key:
        settings.deepseek_api_key = update.deepseek_api_key
        os.environ["DEEPSEEK_API_KEY"] = update.deepseek_api_key
    if update.anthropic_api_key:
        settings.anthropic_api_key = update.anthropic_api_key
        os.environ["ANTHROPIC_API_KEY"] = update.anthropic_api_key
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
            "ollama_model": settings.ollama_model,
        }
    }


# ── AI Analytics endpoints ────────────────────────────

@app.get("/api/ai/metrics")
async def get_ai_metrics():
    """Get latest model performance metrics."""
    from utils.trainer import trainer
    return _clean_val(trainer.get_latest_metrics())

@app.get("/api/ai/history")
async def get_ai_history():
    """Get AI training run history."""
    from utils.trainer import trainer
    return _clean_val({"history": trainer.get_history()})

@app.get("/api/ai/apex-health")
async def get_apex_health():
    """
    Returns Apex Trader (Ollama) health and performance metrics.
    Tracks latency, decision quality, and determines if retraining is needed.
    """
    from memory.duckdb_store import DuckDBStore
    from datetime import datetime, timedelta
    import statistics
    
    # First check if Ollama is actually running
    ollama_running = False
    ollama_check_error = None
    try:
        import requests
        resp = requests.get(f"{settings.ollama_base_url}/api/tags", timeout=2.0)
        ollama_running = resp.status_code == 200
        log.debug(f"[APEX-HEALTH] Ollama check: status={resp.status_code}, running={ollama_running}")
    except Exception as e:
        ollama_running = False
        ollama_check_error = str(e)
        log.warning(f"[APEX-HEALTH] Ollama check failed: {e}")
    
    try:
        store = DuckDBStore(settings.training.duckdb_path)
        await store.start()
        
        # Get metrics from last 24 hours
        now = datetime.utcnow()
        day_ago = now - timedelta(days=1)
        week_ago = now - timedelta(days=7)
        
        # Query LLM call logs (if table exists)
        try:
            llm_calls = store.execute_read("""
                SELECT 
                    COUNT(*) as total_calls,
                    AVG(latency_ms) as avg_latency,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
                    SUM(CASE WHEN timeout = 1 THEN 1 ELSE 0 END) as timeouts,
                    SUM(CASE WHEN error = 1 THEN 1 ELSE 0 END) as errors
                FROM llm_calls
                WHERE timestamp >= ? AND tier = 'ollama'
            """, [day_ago])
            
            if llm_calls and llm_calls[0][0] > 0:
                total_calls, avg_latency, successes, timeouts, errors = llm_calls[0]
                
                # Get percentile latencies
                latencies = store.execute_read("""
                    SELECT latency_ms FROM llm_calls
                    WHERE timestamp >= ? AND tier = 'ollama' AND success = 1
                    ORDER BY latency_ms
                """, [day_ago])
                
                latency_values = [row[0] for row in latencies if row[0]]
                p50_latency = statistics.median(latency_values) if latency_values else avg_latency
                p95_latency = statistics.quantiles(latency_values, n=20)[18] if len(latency_values) > 20 else avg_latency * 1.5
            else:
                # No data, use defaults
                total_calls = 0
                avg_latency = 0
                successes = 0
                timeouts = 0
                errors = 0
                p50_latency = 0
                p95_latency = 0
                
        except Exception as e:
            # Table doesn't exist yet, use defaults
            log.warning("[APEX-HEALTH] LLM calls query failed: {}", e)
            total_calls = 0
            avg_latency = 0
            successes = 0
            timeouts = 0
            errors = 0
            p50_latency = 0
            p95_latency = 0
        
        # Query decision outcomes (if table exists)
        try:
            decisions = store.execute_read("""
                SELECT 
                    decision,
                    COUNT(*) as count,
                    AVG(confidence) as avg_confidence,
                    SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins
                FROM bot_decisions
                WHERE timestamp >= ? AND decision IN ('GO', 'NOGO')
                GROUP BY decision
            """, [day_ago])
            
            go_stats = next((d for d in decisions if d[0] == 'GO'), None)
            nogo_stats = next((d for d in decisions if d[0] == 'NOGO'), None)
            
            go_count = go_stats[1] if go_stats else 0
            go_wins = go_stats[3] if go_stats else 0
            go_winrate = go_wins / go_count if go_count > 0 else 0
            avg_confidence = go_stats[2] if go_stats else 0
            nogo_count = nogo_stats[1] if nogo_stats else 0
            
        except Exception as e:
            # Table doesn't exist yet, use defaults
            log.warning("[APEX-HEALTH] Bot decisions query failed: {}", e)
            go_count = 0
            go_wins = 0
            go_winrate = 0
            avg_confidence = 0
            nogo_count = 0
        
        # Get 7-day latency trend (if data exists)
        try:
            latency_trend = store.execute_read("""
                SELECT 
                    DATE(timestamp) as date,
                    AVG(latency_ms) as avg_latency
                FROM llm_calls
                WHERE timestamp >= ? AND tier = 'ollama' AND success = 1
                GROUP BY DATE(timestamp)
                ORDER BY date
            """, [week_ago])
            
            trend_data = [
                {
                    "timestamp": row[0].isoformat() if hasattr(row[0], 'isoformat') else str(row[0]),
                    "avg_latency": float(row[1]),
                    "p95_latency": float(row[1]) * 1.5  # Estimate
                }
                for row in latency_trend
            ]
        except Exception:
            trend_data = []
        
        # Get model info (if table exists)
        try:
            model_info = await store.execute_read("""
                SELECT model_name, last_trained, training_samples
                FROM model_metadata
                WHERE model_type = 'ollama'
                ORDER BY last_trained DESC
                LIMIT 1
            """)
            
            if model_info:
                model_name = model_info[0][0]
                last_trained = model_info[0][1]
                training_samples = model_info[0][2]
            else:
                model_name = settings.ollama_model or "apex-trader"
                last_trained = None
                training_samples = 0
        except Exception:
            model_name = settings.ollama_model or "apex-trader"
            last_trained = None
            training_samples = 0
        
        # Determine if retraining is needed
        needs_retrain = False
        retrain_reason = None
        
        # Check if model was recently trained (within last 7 days)
        recently_trained = False
        if last_trained:
            try:
                if isinstance(last_trained, str):
                    last_trained_dt = datetime.fromisoformat(last_trained.replace('Z', '+00:00'))
                else:
                    last_trained_dt = last_trained
                days_since_training = (now - last_trained_dt).days
                recently_trained = days_since_training < 7
            except Exception:
                recently_trained = False
        
        # Only check for retraining if model wasn't recently trained
        # and we have sufficient data (at least 50 decisions)
        if not recently_trained and go_count >= 50:
            if go_winrate > 0 and go_winrate < 0.65:
                needs_retrain = True
                retrain_reason = f"GO win rate dropped to {go_winrate*100:.1f}% (threshold: 65%)"
            elif p95_latency > 500:
                needs_retrain = True
                retrain_reason = f"P95 latency increased to {p95_latency:.0f}ms (threshold: 500ms)"
            elif total_calls > 0 and errors / total_calls > 0.05:
                needs_retrain = True
                retrain_reason = "Error rate exceeds 5%"
        elif recently_trained:
            # Model was recently trained, give it time to collect new performance data
            pass
        elif go_count < 50:
            # Not enough data to make a retraining decision
            pass
        
        await store.stop()
        
        # Calculate success rate
        success_rate = successes / total_calls if total_calls > 0 else 1.0
        
        # Determine actual status
        if not ollama_running:
            status = "offline"
        elif total_calls == 0:
            status = "idle"
        else:
            status = "online"
        
        return _clean_val({
            "status": status,
            "ollama_running": ollama_running,
            "avg_latency": avg_latency,
            "calls_24h": total_calls,
            "success_rate": success_rate,
            "go_count": go_count,
            "nogo_count": nogo_count,
            "go_winrate": go_winrate,
            "avg_confidence": avg_confidence,
            "p50_latency": p50_latency,
            "p95_latency": p95_latency,
            "timeouts": timeouts,
            "errors": errors,
            "model_name": model_name,
            "last_trained": last_trained.isoformat() if last_trained and hasattr(last_trained, 'isoformat') else None,
            "training_samples": training_samples,
            "needs_retrain": needs_retrain,
            "retrain_reason": retrain_reason,
            "latency_trend": trend_data
        })
        
    except Exception as e:
        log.error("Failed to fetch apex health: {}", e)
        import traceback
        log.debug("Apex health error details: {}", traceback.format_exc())
        
        # Return empty/offline state instead of mock data
        return _clean_val({
            "status": "no_data",
            "error": "Database tables not initialized or no data logged yet",
            "avg_latency": 0,
            "calls_24h": 0,
            "success_rate": 0,
            "go_count": 0,
            "nogo_count": 0,
            "go_winrate": 0,
            "avg_confidence": 0,
            "p50_latency": 0,
            "p95_latency": 0,
            "timeouts": 0,
            "errors": 0,
            "model_name": settings.ollama_model or "apex-trader",
            "last_trained": None,
            "training_samples": 0,
            "needs_retrain": False,
            "retrain_reason": "No data available - run bot to collect metrics",
            "latency_trend": []
        })


@app.get("/api/autonomous/stats")
async def get_autonomous_stats():
    """
    Get autonomous orchestrator performance statistics.
    Shows fast path usage, decision times, and adaptive learning metrics.
    """
    try:
        # Get autonomous orchestrator instance if it exists
        from agents.graph import orchestrator_node
        
        if not hasattr(orchestrator_node, "_autonomous"):
            return {
                "enabled": False,
                "message": "Autonomous orchestrator not initialized yet"
            }
        
        autonomous = orchestrator_node._autonomous
        stats = autonomous.get_performance_stats()
        
        return {
            "enabled": True,
            "performance": {
                "total_decisions": stats["total_decisions"],
                "fast_path_percentage": round(stats["fast_path_pct"], 1),
                "llm_decisions": stats["llm_decisions"],
                "avg_decision_time_ms": round(stats["avg_decision_time_ms"], 0)
            },
            "recent_performance": stats["recent_performance"],
            "regime_performance": stats["regime_performance"],
            "adaptive_thresholds": stats["adaptive_thresholds"],
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        log.error(f"Error getting autonomous stats: {e}")
        return {
            "enabled": False,
            "error": str(e)
        }


# ── Bot control ───────────────────────────────────────

@app.post("/api/bot/start")
async def start_bot():
    global _bot_running, _bot_task
    from core.bot_lifecycle import bot_manager
    
    if _bot_running:
        return {"status": "already_running"}
    
    _bot_running = True
    _bot_task = asyncio.create_task(_bot_main_loop())
    bot_manager.start()
    log.info("Bot START command received")
    return {"status": "started"}

@app.post("/api/bot/stop")
async def stop_bot():
    global _bot_running, _bot_task
    from core.bot_lifecycle import bot_manager
    
    _bot_running = False
    if _bot_task:
        _bot_task.cancel()
    bot_manager.stop()
    log.info("Bot STOP command received")
    return {"status": "stopped"}

@app.post("/api/bot/train")
async def trigger_training(
    model_type: str = "random_forest",
    symbol: str = "EURUSD"
):
    """
    Manually trigger AI model training.
    Delegates to ML endpoints for actual training logic.
    """
    try:
        # Import here to avoid circular dependency
        from api.ml_endpoints import train_model, TrainModelRequest
        
        # Create request
        request = TrainModelRequest(
            model_type=model_type,
            symbol=symbol,
            training_months=6
        )
        
        # Delegate to ML endpoint (thin wrapper)
        result = await train_model(request)
        
        return {
            "status": "success",
            "message": f"{model_type} training completed",
            "metrics": result.get("metrics", {}),
            "model_path": result.get("model_path", "")
        }
    
    except Exception as e:
        log.error(f"Training failed: {e}")
        return {
            "status": "error",
            "message": str(e)
        }

@app.post("/api/bot/restart")
async def restart_bot():
    await stop_bot()
    await asyncio.sleep(2)
    return await start_bot()


# ═══════════════════════════════════════════════════════
#  TRAINING PIPELINE ENDPOINTS
# ═══════════════════════════════════════════════════════

# Track running training jobs so the frontend can poll status
_training_jobs: dict[str, dict] = {}


class TrainingConfigUpdate(BaseModel):
    model_config = {"protected_namespaces": ()}
    
    fred_api_key: str | None = None
    historical_start_date: str | None = None
    ccxt_start_date: str | None = None
    yfinance_timeframe: str | None = None
    ccxt_timeframe: str | None = None
    raw_data_dir: str | None = None
    macro_data_dir: str | None = None
    duckdb_path: str | None = None
    yfinance_symbols: dict | None = None
    ccxt_symbols: list | None = None
    fred_series: dict | None = None
    sentiment_keywords: list | None = None
    min_training_examples: int | None = None
    training_data_dir: str | None = None
    include_synthetic: bool | None = None
    base_model: str | None = None
    lora_rank: int | None = None
    lora_alpha: int | None = None
    num_epochs: int | None = None
    batch_size: int | None = None
    gradient_accumulation: int | None = None
    learning_rate: float | None = None
    max_seq_length: int | None = None
    eval_split: float | None = None
    model_output_dir: str | None = None
    checkpoint_dir: str | None = None
    gguf_output: str | None = None
    quant_type: str | None = None
    ollama_model_name: str | None = None
    kaggle_username: str | None = None
    kaggle_api_key: str | None = None
    kaggle_dataset_name: str | None = None
    kaggle_kernel_name: str | None = None
    kaggle_gpu_type: str | None = None
    runpod_api_key: str | None = None
    runpod_endpoint_id: str | None = None
    docker_hub_username: str | None = None
    docker_image_name: str | None = None


@app.get("/api/training/config")
async def get_training_config():
    """Return current training pipeline configuration."""
    t = settings.training
    return {
        "collection": {
            "fred_api_key_set": bool(t.fred_api_key),
            "historical_start_date": t.historical_start_date,
            "ccxt_start_date": t.ccxt_start_date,
            "yfinance_timeframe": t.yfinance_timeframe,
            "ccxt_timeframe": t.ccxt_timeframe,
            "raw_data_dir": t.raw_data_dir,
            "macro_data_dir": t.macro_data_dir,
            "duckdb_path": t.duckdb_path,
            "yfinance_symbols": t.yfinance_symbols,
            "ccxt_symbols": t.ccxt_symbols,
            "fred_series": t.fred_series,
            "sentiment_keywords": t.sentiment_keywords,
        },
        "export": {
            "min_training_examples": t.min_training_examples,
            "training_data_dir": t.training_data_dir,
            "include_synthetic": t.include_synthetic,
        },
        "finetune": {
            "base_model": t.base_model,
            "lora_rank": t.lora_rank,
            "lora_alpha": t.lora_alpha,
            "num_epochs": t.num_epochs,
            "batch_size": t.batch_size,
            "gradient_accumulation": t.gradient_accumulation,
            "learning_rate": t.learning_rate,
            "max_seq_length": t.max_seq_length,
            "eval_split": t.eval_split,
            "model_output_dir": t.model_output_dir,
            "checkpoint_dir": t.checkpoint_dir,
        },
        "conversion": {
            "gguf_output": t.gguf_output,
            "quant_type": t.quant_type,
            "ollama_model_name": t.ollama_model_name,
        },
        "kaggle": {
            "kaggle_username_set": bool(t.kaggle_username),
            "kaggle_api_key_set":  bool(t.kaggle_api_key),
            "kaggle_dataset_name": t.kaggle_dataset_name,
            "kaggle_kernel_name":  t.kaggle_kernel_name,
            "kaggle_gpu_type":     t.kaggle_gpu_type,
        },
        "runpod": {
            "runpod_api_key_set":     bool(t.runpod_api_key),
            "runpod_endpoint_id_set": bool(t.runpod_endpoint_id),
            "runpod_endpoint_id":     t.runpod_endpoint_id,
            "docker_hub_username":    t.docker_hub_username,
            "docker_image_name":      t.docker_image_name,
        },
    }


_ENV_PATH         = Path(__file__).parent.parent / ".env"
_TRAINING_CFG_PATH = Path(__file__).parent.parent / "data" / "training_config.json"

# TrainingConfig fields that must survive server restarts → their .env key names
# (API keys go to .env for security; all other fields go to training_config.json)
_PERSIST_FIELDS = {
    "fred_api_key":       "FRED_API_KEY",
    "kaggle_username":    "KAGGLE_USERNAME",
    "kaggle_api_key":     "KAGGLE_KEY",
    "runpod_api_key":     "RUNPOD_API_KEY",
    "runpod_endpoint_id": "RUNPOD_ENDPOINT_ID",
    "docker_hub_username":"DOCKER_HUB_USERNAME",
    "docker_image_name":  "DOCKER_IMAGE_NAME",
}

# Fields that are secrets — excluded from the JSON config file
_SECRET_FIELDS = set(_PERSIST_FIELDS.keys())


def _save_training_config_json() -> None:
    """Save all non-secret TrainingConfig fields to data/training_config.json."""
    import dataclasses, json as _json
    try:
        _TRAINING_CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        for f in dataclasses.fields(settings.training):
            if f.name in _SECRET_FIELDS:
                continue  # secrets stay in .env only
            val = getattr(settings.training, f.name)
            # Only store JSON-serialisable primitives
            if isinstance(val, (str, int, float, bool, list)):
                data[f.name] = val
        _TRAINING_CFG_PATH.write_text(_json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning("Could not save training config JSON: {}", e)


def _load_training_config_json() -> None:
    """Load persisted non-secret TrainingConfig fields from data/training_config.json."""
    import json as _json
    if not _TRAINING_CFG_PATH.exists():
        return
    try:
        data = _json.loads(_TRAINING_CFG_PATH.read_text(encoding="utf-8"))
        for key, value in data.items():
            if hasattr(settings.training, key) and key not in _SECRET_FIELDS:
                setattr(settings.training, key, value)
        log.info("Training config loaded from {}: {} fields", _TRAINING_CFG_PATH.name, len(data))
    except Exception as e:
        log.warning("Could not load training config JSON: {}", e)


def _persist_to_env(env_key: str, value: str) -> None:
    """Write or update a key=value line in .env so the value survives server restarts."""
    if not _ENV_PATH.exists():
        return
    lines = _ENV_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    prefix = f"{env_key}="
    updated = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith(prefix):
            # Preserve any inline comment after the old value
            comment = ("  " + line[line.index("#"):].rstrip()) if "#" in line else ""
            lines[i] = f"{prefix}{value}{comment}\n"
            updated = True
            break
    if not updated:
        lines.append(f"{prefix}{value}\n")
    _ENV_PATH.write_text("".join(lines), encoding="utf-8")


@app.post("/api/training/config")
async def update_training_config(update: TrainingConfigUpdate):
    """Update training pipeline configuration at runtime."""
    persisted_env = []
    for field_name, value in update.dict(exclude_none=True).items():
        if hasattr(settings.training, field_name):
            setattr(settings.training, field_name, value)
            log.info("Training config updated: {}={}", field_name,
                     "***" if "key" in field_name.lower() else value)
            # API keys → .env
            if field_name in _PERSIST_FIELDS and value:
                _persist_to_env(_PERSIST_FIELDS[field_name], value)
                persisted_env.append(_PERSIST_FIELDS[field_name])
    # All other fields → data/training_config.json
    _save_training_config_json()
    msg = "Training configuration updated and saved"
    if persisted_env:
        msg += f" — API keys persisted to .env: {', '.join(persisted_env)}"
    return {"status": "ok", "message": msg}


def _run_collect_historical(job_id: str, source: str):
    """Run collect_historical_data in a background thread."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    _training_jobs[job_id]["status"] = "running"
    bridge = _LogBridge("[HIST]")
    _real_stdout, _real_stderr = _sys.stdout, _sys.stderr
    _sys.stdout = _sys.stderr = bridge
    try:
        from scripts.collect_historical_data import collect_yfinance, collect_ccxt
        t = settings.training
        total = 0
        if source in ("yfinance", "all"):
            total += collect_yfinance(
                start=t.historical_start_date,
                interval=t.yfinance_timeframe,
                out_dir=t.raw_data_dir,
                symbols=t.yfinance_symbols,
            )
        if source in ("ccxt", "all"):
            total += collect_ccxt(
                timeframe=t.ccxt_timeframe,
                start=t.ccxt_start_date,
                out_dir=t.raw_data_dir,
            )
        _training_jobs[job_id].update({"status": "done", "bars_collected": total})
        log.info("[HIST] Job {} complete — {:,} bars collected", job_id, total)
    except Exception as e:
        _training_jobs[job_id].update({"status": "error", "error": str(e)})
        log.error("[HIST] Job {} failed: {}", job_id, e)
    finally:
        bridge.flush()
        _sys.stdout, _sys.stderr = _real_stdout, _real_stderr


def _run_collect_extended(job_id: str, symbol: str, years: int, timeframe: str, all_symbols: bool):
    """Run collect_extended_historical_data in a background thread."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    _training_jobs[job_id]["status"] = "running"
    bridge = _LogBridge("[EXT]")
    _real_stdout, _real_stderr = _sys.stdout, _sys.stderr
    _sys.stdout = _sys.stderr = bridge
    try:
        from scripts.collect_extended_historical_data import collect_extended_data
        t = settings.training
        
        if all_symbols:
            # Collect for all configured symbols
            symbols = t.yfinance_symbols if hasattr(t, 'yfinance_symbols') else ["XAUUSD"]
            total = 0
            output_dir = str(Path(t.duckdb_path).parent / "raw")
            for sym in symbols:
                bars = collect_extended_data(
                    symbol=sym,
                    years=years,
                    target_timeframe=timeframe,
                    output_dir=output_dir
                )
                total += bars
                # Load to DuckDB
                csv_path = Path(output_dir) / f"{sym}_{timeframe}.csv"
                if csv_path.exists():
                    from scripts.collect_extended_historical_data import load_to_duckdb
                    load_to_duckdb(str(csv_path), t.duckdb_path)
            _training_jobs[job_id].update({"status": "done", "bars_collected": total, "symbols": len(symbols)})
            log.info("[EXT] Job {} complete — {:,} bars collected for {} symbols", job_id, total, len(symbols))
        else:
            # Collect for single symbol
            output_dir = str(Path(t.duckdb_path).parent / "raw")
            bars = collect_extended_data(
                symbol=symbol,
                years=years,
                target_timeframe=timeframe,
                output_dir=output_dir
            )
            # Load to DuckDB
            csv_path = Path(output_dir) / f"{symbol}_{timeframe}.csv"
            if csv_path.exists():
                from scripts.collect_extended_historical_data import load_to_duckdb
                load_to_duckdb(str(csv_path), t.duckdb_path)
            _training_jobs[job_id].update({"status": "done", "bars_collected": bars})
            log.info("[EXT] Job {} complete — {:,} bars collected for {}", job_id, bars, symbol)
    except Exception as e:
        _training_jobs[job_id].update({"status": "error", "error": str(e)})
        log.error("[EXT] Job {} failed: {}", job_id, e)
    finally:
        bridge.flush()
        _sys.stdout, _sys.stderr = _real_stdout, _real_stderr


def _run_collect_macro(job_id: str):
    """Run collect_macro_data in a background thread."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    _training_jobs[job_id]["status"] = "running"
    bridge = _LogBridge("[MACRO]")
    _real_stdout, _real_stderr = _sys.stdout, _sys.stderr
    _sys.stdout = _sys.stderr = bridge
    try:
        from scripts.collect_macro_data import collect_fred, collect_cot, load_macro_to_duckdb
        t = settings.training
        total = 0
        if t.fred_api_key:
            total += collect_fred(
                api_key=t.fred_api_key,
                start=t.historical_start_date,
                series=t.fred_series,
                out_dir=t.macro_data_dir,
            )
        total += collect_cot(out_dir=t.macro_data_dir)
        load_macro_to_duckdb(db_path=t.duckdb_path, macro_dir=t.macro_data_dir)
        _training_jobs[job_id].update({"status": "done", "records": total})
        log.info("[MACRO] Job {} complete — {:,} records collected", job_id, total)
    except Exception as e:
        _training_jobs[job_id].update({"status": "error", "error": str(e)})
        log.error("[MACRO] Job {} failed: {}", job_id, e)
    finally:
        bridge.flush()
        _sys.stdout = _real_stdout


def _run_export(job_id: str):
    """Run prepare_training_data in a background thread."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    _training_jobs[job_id]["status"] = "running"
    try:
        from scripts.prepare_training_data import export_training_data
        t = settings.training
        out_path = export_training_data(
            db_path=t.duckdb_path,
            min_examples=t.min_training_examples,
            include_synthetic=t.include_synthetic,
            out_dir=t.training_data_dir,
        )
        _training_jobs[job_id].update({"status": "done", "output_file": out_path})
        log.info("Training export job {} complete → {}", job_id, out_path)
    except Exception as e:
        _training_jobs[job_id].update({"status": "error", "error": str(e)})
        log.error("Training export job {} failed: {}", job_id, e)


def _run_finetune(job_id: str):
    """Run fine_tune.py in a background thread."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    _training_jobs[job_id]["status"] = "running"
    try:
        from scripts.fine_tune import run_finetuning
        t = settings.training
        data_path = str(Path(t.training_data_dir) / "apex_training_latest.jsonl")
        run_finetuning(
            data_path=data_path,
            output_dir=t.model_output_dir,
            base_model=t.base_model,
            max_seq_length=t.max_seq_length,
            lora_rank=t.lora_rank,
            lora_alpha=t.lora_alpha,
            num_epochs=t.num_epochs,
            batch_size=t.batch_size,
            gradient_accumulation=t.gradient_accumulation,
            learning_rate=t.learning_rate,
            eval_split=t.eval_split,
            checkpoint_dir=t.checkpoint_dir,
        )
        _training_jobs[job_id].update({"status": "done", "model_dir": t.model_output_dir})
        log.info("Fine-tuning job {} complete → {}", job_id, t.model_output_dir)
    except Exception as e:
        _training_jobs[job_id].update({"status": "error", "error": str(e)})
        log.error("Fine-tuning job {} failed: {}", job_id, e)


def _run_convert(job_id: str):
    """Run conversion.py in a background thread.

    Searches multiple paths for merged model or LoRA adapters (handles both
    local fine_tune.py output and Kaggle-downloaded nested layout).
    If only adapters are found, merges them locally first.
    """
    import sys as _sys2
    from pathlib import Path
    _sys2.path.insert(0, str(Path(__file__).parent.parent))

    _training_jobs[job_id]["status"] = "running"
    _real_stdout_cv, _real_stderr_cv = _sys.stdout, _sys.stderr
    bridge_cv = _LogBridge("[CONVERT]")
    _sys.stdout = _sys.stderr = bridge_cv
    try:
        from scripts.conversion import (
            convert_to_gguf, write_modelfile, load_into_ollama,
            find_model_paths, merge_adapters_locally, clone_llama_cpp,
        )
        t = settings.training

        # Check if a GGUF was already downloaded from Kaggle (skip merge + convert)
        _existing_ggufs = list(Path(t.model_output_dir).rglob("*.gguf"))
        if not _existing_ggufs:
            # Also search the models/ parent directory (e.g. models/apex-trader-q4_k_m.gguf)
            _existing_ggufs = list(Path(t.model_output_dir).parent.glob("*.gguf"))
        if not _existing_ggufs:
            _existing_ggufs = list(Path(".").glob("*.gguf"))
        if not _existing_ggufs and Path(t.gguf_output).exists():
            _existing_ggufs = [Path(t.gguf_output)]

        if _existing_ggufs:
            # Prefer q4_k_m quantized, then largest file (best quality available)
            _existing_ggufs.sort(key=lambda p: (
                0 if "q4_k_m" in p.name else (1 if "q8" in p.name else 2),
                -p.stat().st_size
            ))
            kaggle_gguf = _existing_ggufs[0]
            print(f"GGUF already present: {kaggle_gguf} ({kaggle_gguf.stat().st_size / 1e9:.2f} GB)")
            # Use the found GGUF directly — avoid large file copy
            mf = write_modelfile(kaggle_gguf)
            load_into_ollama(mf, model_name=t.ollama_model_name)
            _training_jobs[job_id].update({
                "status": "done",
                "gguf": str(kaggle_gguf),
                "ollama_model": t.ollama_model_name,
            })
            log.info("Conversion job {} — used pre-built GGUF: {}", job_id, kaggle_gguf)
            return

        merged_path, adapter_path = find_model_paths(t.model_output_dir)
        print(f"Convert: merged={merged_path} adapter={adapter_path}")

        if merged_path is None and adapter_path is not None:
            # Merge LoRA adapters into the base model locally.
            # torch may not be installed in the server venv — check first.
            try:
                import torch as _torch_cv
                _has_gpu = _torch_cv.cuda.is_available()
            except ImportError:
                _training_jobs[job_id].update({
                    "status": "error",
                    "error": (
                        "torch is not installed in the server environment — cannot merge locally. "
                        "Install it with: pip install torch --index-url https://download.pytorch.org/whl/cpu  "
                        "OR re-run Kaggle training (the next run will produce a GGUF directly)."
                    ),
                })
                print("[CONVERT] ERROR: torch not found. Install torch or re-run Kaggle to get a GGUF.")
                return

            merged_path = Path(t.model_output_dir + "_merged")
            print(f"No merged model found — starting local adapter merge")
            print(f"  Adapters : {adapter_path}")
            print(f"  Output   : {merged_path}")
            print(f"  GPU      : {'YES (fast)' if _has_gpu else 'NO — CPU mode (~30 GB RAM, may take 10-30 min)'}")
            if not _has_gpu:
                print("  TIP: Re-run Kaggle training — next run produces GGUF on GPU automatically.")
            _training_jobs[job_id]["status_detail"] = (
                f"Merging adapters ({'GPU' if _has_gpu else 'CPU — may take 10-30 min'})..."
            )
            ok = merge_adapters_locally(adapter_path, merged_path)
            if not ok:
                _training_jobs[job_id].update({
                    "status": "error",
                    "error": "Local adapter merge failed — check BOT LOGS for [CONVERT] error detail",
                })
                return

        if merged_path is None:
            _training_jobs[job_id].update({
                "status": "error",
                "error": f"No model or adapters found under {t.model_output_dir}. Run fine-tuning first.",
            })
            return

        # Ensure llama.cpp is available before conversion
        print("[CONVERT] Preparing llama.cpp...")
        clone_llama_cpp(skip_if_exists=True)

        success = convert_to_gguf(
            model_dir=merged_path,
            output_path=Path(t.gguf_output),
            quant_type=t.quant_type,
        )
        if success:
            mf = write_modelfile(Path(t.gguf_output))
            load_into_ollama(mf, model_name=t.ollama_model_name)
        _training_jobs[job_id].update({
            "status": "done" if success else "error",
            "gguf": t.gguf_output,
            "ollama_model": t.ollama_model_name,
        })
        log.info("Conversion job {} complete — ollama model: {}", job_id, t.ollama_model_name)
    except Exception as e:
        _training_jobs[job_id].update({"status": "error", "error": str(e)})
        log.error("Conversion job {} failed: {}", job_id, e)
    finally:
        bridge_cv.flush()
        _sys.stdout, _sys.stderr = _real_stdout_cv, _real_stderr_cv


def _run_remote_kaggle(job_id: str):
    """Run the full Kaggle remote fine-tuning pipeline in a background thread."""
    import sys as _sys2
    from pathlib import Path
    _sys2.path.insert(0, str(Path(__file__).parent.parent))

    _training_jobs[job_id]["status"] = "running"
    bridge = _LogBridge("[KAGGLE]")
    _real_stdout, _real_stderr = _sys.stdout, _sys.stderr
    _sys.stdout = _sys.stderr = bridge
    try:
        from scripts.run_remote_training import run_on_kaggle
        t = settings.training
        result = run_on_kaggle({
            "username":              t.kaggle_username,
            "api_key":               t.kaggle_api_key,
            "dataset_name":          t.kaggle_dataset_name,
            "kernel_name":           t.kaggle_kernel_name,
            "gpu_type":              t.kaggle_gpu_type,
            "training_data_dir":     t.training_data_dir,
            "model_output_dir":      t.model_output_dir,
            "base_model":            t.base_model,
            "max_seq_length":        t.max_seq_length,
            "lora_rank":             t.lora_rank,
            "lora_alpha":            t.lora_alpha,
            "num_epochs":            t.num_epochs,
            "batch_size":            t.batch_size,
            "gradient_accumulation": t.gradient_accumulation,
            "learning_rate":         t.learning_rate,
            "quant_type":            t.quant_type,
        })
        _training_jobs[job_id].update({
            "status":           result.get("status", "done"),
            "model_dir":        result.get("model_dir"),
            "duration_seconds": result.get("duration_seconds"),
            "kaggle_url":       result.get("url"),
            "gguf_path":        result.get("gguf_path"),
            "error":            result.get("error"),
        })
        if result.get("status") == "done":
            log.info("[KAGGLE] Job {} complete — model at {}", job_id, result.get("model_dir"))
        else:
            log.error("[KAGGLE] Job {} failed: {}", job_id, result.get("error"))
    except Exception as e:
        _training_jobs[job_id].update({"status": "error", "error": str(e)})
        log.error("[KAGGLE] Job {} failed: {}", job_id, e)
    finally:
        bridge.flush()
        _sys.stdout, _sys.stderr = _real_stdout, _real_stderr


@app.post("/api/training/remote/kaggle")
async def trigger_kaggle_training():
    """Start fine-tuning on Kaggle GPU (uploads data, pushes kernel, polls, downloads).

    Uses a daemon threading.Thread instead of FastAPI BackgroundTasks so the
    long-running poll loop (time.sleep * hours) does NOT block server shutdown.
    anyio cancels BackgroundTasks workers on shutdown, causing CancelledError;
    daemon threads are simply abandoned when the process exits.
    """
    import uuid, threading
    from pathlib import Path
    t = settings.training
    if not t.kaggle_username or not t.kaggle_api_key:
        return {
            "status": "error",
            "message": "Kaggle credentials not configured. Set username + API key in Training Config.",
        }
    latest = Path(t.training_data_dir) / "apex_training_latest.jsonl"
    if not latest.exists():
        return {
            "status": "error",
            "message": "Training data not found. Run Export (Step 3) first.",
        }
    job_id = f"kaggle_{uuid.uuid4().hex[:8]}"
    _training_jobs[job_id] = {
        "type":       "kaggle_finetune",
        "status":     "queued",
        "started_at": datetime.utcnow().isoformat(),
        "kaggle_url": f"https://www.kaggle.com/code/{t.kaggle_username}/{t.kaggle_kernel_name}",
    }
    # daemon=True: thread is silently abandoned on server exit (no CancelledError)
    t_thread = threading.Thread(target=_run_remote_kaggle, args=(job_id,), daemon=True)
    t_thread.start()
    log.info("Training job queued: kaggle_finetune (kernel={})", t.kaggle_kernel_name)
    return {"status": "queued", "job_id": job_id,
            "kaggle_url": _training_jobs[job_id]["kaggle_url"]}


@app.post("/api/training/remote/kaggle/download")
async def retry_kaggle_download(kernel_ref: str | None = None):
    """Re-download the last Kaggle kernel output without re-running training.

    Use this when the download step failed (e.g. charmap encoding error) but
    the kernel already completed successfully.
    kernel_ref: 'username/kernel-slug' — defaults to settings values.
    """
    import uuid, threading
    t = settings.training
    if not t.kaggle_username or not t.kaggle_api_key:
        return {"status": "error", "message": "Kaggle credentials not configured."}

    effective_ref = kernel_ref or f"{t.kaggle_username}/{t.kaggle_kernel_name}"

    def _do_download(job_id: str):
        _training_jobs[job_id]["status"] = "running"
        _real_out, _real_err = _sys.stdout, _sys.stderr
        bridge = _LogBridge("[KAGGLE-DL]")
        _sys.stdout = _sys.stderr = bridge
        try:
            from scripts.run_remote_training import _get_api, download_output
            api = _get_api(t.kaggle_username, t.kaggle_api_key)
            print(f"Re-downloading output of kernel: {effective_ref}")
            downloaded = download_output(api, effective_ref, t.model_output_dir)
            gguf_files = list(Path(t.model_output_dir).rglob("*.gguf"))
            gguf_path = str(gguf_files[0]) if gguf_files else None
            if gguf_path:
                print(f"GGUF found: {gguf_path} — ready for Convert step")
            _training_jobs[job_id].update({
                "status":           "done",
                "files_downloaded": len(downloaded),
                "gguf_path":        gguf_path,
            })
            log.info("[KAGGLE-DL] Re-download complete — {} file(s), gguf={}", len(downloaded), gguf_path)
        except Exception as e:
            _training_jobs[job_id].update({"status": "error", "error": str(e)})
            log.error("[KAGGLE-DL] Re-download failed: {}", e)
        finally:
            bridge.flush()
            _sys.stdout, _sys.stderr = _real_out, _real_err

    job_id = f"kaggle_dl_{uuid.uuid4().hex[:8]}"
    _training_jobs[job_id] = {
        "type":       "kaggle_download",
        "status":     "queued",
        "started_at": datetime.utcnow().isoformat(),
        "kernel_ref": effective_ref,
    }
    threading.Thread(target=_do_download, args=(job_id,), daemon=True).start()
    log.info("Re-download job queued: {}", effective_ref)
    return {"status": "queued", "job_id": job_id, "kernel_ref": effective_ref}


def _run_remote_runpod(job_id: str):
    """Run the full RunPod Serverless fine-tuning pipeline in a background thread."""
    import sys as _sys2
    from pathlib import Path
    _sys2.path.insert(0, str(Path(__file__).parent.parent))

    _training_jobs[job_id]["status"] = "running"
    bridge = _LogBridge("[RUNPOD]")
    _real_stdout, _real_stderr = _sys.stdout, _sys.stderr
    _sys.stdout = _sys.stderr = bridge
    try:
        from scripts.run_remote_runpod import run_on_runpod
        t = settings.training
        result = run_on_runpod({
            "api_key":               t.runpod_api_key,
            "endpoint_id":           t.runpod_endpoint_id,
            "training_data_dir":     t.training_data_dir,
            "model_output_dir":      t.model_output_dir,
            "base_model":            t.base_model,
            "max_seq_length":        t.max_seq_length,
            "lora_rank":             t.lora_rank,
            "lora_alpha":            t.lora_alpha,
            "num_epochs":            t.num_epochs,
            "batch_size":            t.batch_size,
            "gradient_accumulation": t.gradient_accumulation,
            "learning_rate":         t.learning_rate,
            "quant_type":            t.quant_type,
        })
        _training_jobs[job_id].update({
            "status":           result.get("status", "done"),
            "model_dir":        result.get("model_dir"),
            "gguf_path":        result.get("gguf_path"),
            "duration_seconds": result.get("duration_seconds"),
            "job_id_remote":    result.get("job_id"),
            "train_loss":       result.get("train_loss"),
            "error":            result.get("error"),
        })
        if result.get("status") == "done":
            log.info("[RUNPOD] Job {} complete — gguf: {}", job_id, result.get("gguf_path"))
        else:
            log.error("[RUNPOD] Job {} failed: {}", job_id, result.get("error"))
    except Exception as e:
        _training_jobs[job_id].update({"status": "error", "error": str(e)})
        log.error("[RUNPOD] Job {} failed: {}", job_id, e)
    finally:
        bridge.flush()
        _sys.stdout, _sys.stderr = _real_stdout, _real_stderr


def _run_docker_build(job_id: str):
    """Build + push the RunPod Docker image in a background thread.

    Streams docker build and docker push output to BOT LOGS via [DOCKER] prefix.
    Requires Docker Desktop (or Docker Engine) to be installed and logged in.
    """
    import subprocess as _sp
    from pathlib import Path

    bridge = _LogBridge("[DOCKER]")
    _real_stdout, _real_stderr = _sys.stdout, _sys.stderr
    _sys.stdout = _sys.stderr = bridge
    try:
        t = settings.training
        image = f"{t.docker_hub_username}/{t.docker_image_name}:latest"
        root = str(Path(__file__).parent.parent)

        def _stream(cmd: list[str], phase: str) -> int:
            print(f"\n[Docker] {phase}: {' '.join(cmd)}")
            proc = _sp.Popen(
                cmd, cwd=root,
                stdout=_sp.PIPE, stderr=_sp.STDOUT,
                text=True, bufsize=1,
            )
            for line in proc.stdout:
                print(line.rstrip())
            proc.wait()
            return proc.returncode

        _training_jobs[job_id]["status"] = "building"
        rc = _stream(
            ["docker", "build", "-f", "Dockerfile.runpod", "-t", image, "."],
            f"Building {image}",
        )
        if rc != 0:
            raise RuntimeError(f"docker build exited with code {rc}")

        _training_jobs[job_id]["status"] = "pushing"
        rc = _stream(["docker", "push", image], f"Pushing {image}")
        if rc != 0:
            raise RuntimeError(f"docker push exited with code {rc}")

        _training_jobs[job_id].update({"status": "done", "image": image})
        print(f"\n[Docker] Done — image available at: {image}")
        print(f"[Docker] Set this as your RunPod endpoint container image and re-deploy.")
    except FileNotFoundError:
        msg = "Docker not found — install Docker Desktop and ensure it is running."
        _training_jobs[job_id].update({"status": "error", "error": msg})
        print(f"[Docker] ERROR: {msg}")
    except Exception as e:
        _training_jobs[job_id].update({"status": "error", "error": str(e)})
        print(f"[Docker] ERROR: {e}")
    finally:
        bridge.flush()
        _sys.stdout, _sys.stderr = _real_stdout, _real_stderr


@app.post("/api/training/runpod/build")
async def trigger_docker_build():
    """Build and push the RunPod Docker image (apex-runpod) to Docker Hub.

    Requires Docker Desktop to be installed and running, and the user to be
    logged in via `docker login`. Streams output to BOT LOGS ([DOCKER] prefix).
    """
    import uuid, threading
    t = settings.training
    if not t.docker_hub_username:
        return {"status": "error", "message": "Docker Hub username not set — configure in RunPod config panel."}
    image = f"{t.docker_hub_username}/{t.docker_image_name}:latest"
    job_id = f"docker_{uuid.uuid4().hex[:8]}"
    _training_jobs[job_id] = {
        "type":       "docker_build",
        "status":     "queued",
        "started_at": datetime.utcnow().isoformat(),
        "image":      image,
    }
    threading.Thread(target=_run_docker_build, args=(job_id,), daemon=True).start()
    log.info("Docker build job queued: {} → {}", job_id, image)
    return {"status": "queued", "job_id": job_id, "image": image}


@app.post("/api/training/remote/runpod")
async def trigger_runpod_training():
    """Start fine-tuning on RunPod Serverless GPU.

    Submits a job to the configured RunPod endpoint, polls until complete,
    then downloads the GGUF directly — no encoding issues, no browser needed.
    """
    import uuid, threading
    from pathlib import Path
    t = settings.training
    if not t.runpod_api_key:
        return {"status": "error", "message": "RunPod API key not configured. Set in Training Config."}
    if not t.runpod_endpoint_id:
        return {"status": "error", "message": "RunPod Endpoint ID not configured. Set in Training Config."}
    latest = Path(t.training_data_dir) / "apex_training_latest.jsonl"
    if not latest.exists():
        return {"status": "error", "message": "Training data not found. Run Export (Step 3) first."}
    job_id = f"runpod_{uuid.uuid4().hex[:8]}"
    _training_jobs[job_id] = {
        "type":        "runpod_finetune",
        "status":      "queued",
        "started_at":  datetime.utcnow().isoformat(),
        "endpoint_id": t.runpod_endpoint_id,
    }
    threading.Thread(target=_run_remote_runpod, args=(job_id,), daemon=True).start()
    log.info("Training job queued: runpod_finetune (endpoint={})", t.runpod_endpoint_id)
    return {"status": "queued", "job_id": job_id}


@app.post("/api/training/collect/historical")
async def collect_historical(source: str = "all"):
    """Start historical OHLCV data collection (yfinance + CCXT)."""
    import uuid, threading
    job_id = f"hist_{uuid.uuid4().hex[:8]}"
    _training_jobs[job_id] = {"type": "collect_historical", "status": "queued", "source": source,
                               "started_at": datetime.utcnow().isoformat()}
    threading.Thread(target=_run_collect_historical, args=(job_id, source), daemon=True).start()
    log.info("Training job queued: collect_historical (source={})", source)
    return {"status": "queued", "job_id": job_id}


@app.post("/api/training/collect/extended")
async def collect_extended_historical(
    symbol: str = "XAUUSD",
    years: int = 2,
    timeframe: str = "1h",
    all_symbols: bool = False
):
    """Start extended historical data collection (2+ years via resampling)."""
    import uuid, threading
    job_id = f"ext_{uuid.uuid4().hex[:8]}"
    _training_jobs[job_id] = {
        "type": "collect_extended",
        "status": "queued",
        "symbol": symbol,
        "years": years,
        "timeframe": timeframe,
        "all_symbols": all_symbols,
        "started_at": datetime.utcnow().isoformat()
    }
    threading.Thread(
        target=_run_collect_extended,
        args=(job_id, symbol, years, timeframe, all_symbols),
        daemon=True
    ).start()
    log.info("Training job queued: collect_extended (symbol={}, years={}, tf={})", symbol, years, timeframe)
    return {"status": "queued", "job_id": job_id}


@app.get("/api/training/data/coverage")
async def get_data_coverage(symbol: str = None):
    """Get historical data coverage statistics."""
    import asyncio
    
    def _get_coverage():
        try:
            import duckdb
            from pathlib import Path
            
            db_path = settings.training.duckdb_path
            if not Path(db_path).exists():
                return {"status": "error", "message": "Database not found. Collect data first."}
            
            # Try read-only first, fall back to read-write if connection conflict
            try:
                con = duckdb.connect(db_path, read_only=True)
            except duckdb.IOException as e:
                if "different configuration" in str(e):
                    con = duckdb.connect(db_path, read_only=False)
                else:
                    raise
            
            # Check if table exists
            tables = con.execute("SHOW TABLES").fetchall()
            if not any('ohlcv' in str(t) for t in tables):
                con.close()
                return {"status": "error", "message": "No OHLCV data found. Collect data first."}
            
            # Get coverage by symbol
            query = """
                SELECT 
                    symbol,
                    timeframe,
                    COUNT(*) as bars,
                    MIN(timestamp) as start_date,
                    MAX(timestamp) as end_date,
                    DATEDIFF('day', MIN(timestamp), MAX(timestamp)) as days_covered
                FROM ohlcv
            """
            
            if symbol:
                query += f" WHERE symbol = '{symbol}'"
            
            query += " GROUP BY symbol, timeframe ORDER BY symbol, timeframe"
            
            results = con.execute(query).fetchall()
            con.close()
            
            coverage = []
            for row in results:
                sym, tf, bars, start, end, days = row
                coverage.append({
                    "symbol": sym,
                    "timeframe": tf,
                    "bars": bars,
                    "start_date": start.isoformat() if start else None,
                    "end_date": end.isoformat() if end else None,
                    "days_covered": days,
                    "years_covered": round(days / 365, 1) if days else 0,
                    "sufficient": bars >= 10000
                })
            
            return {"status": "success", "coverage": coverage}
            
        except Exception as e:
            log.error("Error getting data coverage: {}", e)
            return {"status": "error", "message": str(e)}
    
    # Run in thread pool to avoid blocking
    return await asyncio.to_thread(_get_coverage)


@app.post("/api/training/collect/macro")
async def collect_macro():
    """Start macro data collection (FRED + CFTC COT)."""
    import uuid, threading
    job_id = f"macro_{uuid.uuid4().hex[:8]}"
    if not settings.training.fred_api_key:
        return {"status": "error", "message": "FRED API key not configured. Set it in /api/training/config"}
    _training_jobs[job_id] = {"type": "collect_macro", "status": "queued",
                               "started_at": datetime.utcnow().isoformat()}
    threading.Thread(target=_run_collect_macro, args=(job_id,), daemon=True).start()
    log.info("Training job queued: collect_macro")
    return {"status": "queued", "job_id": job_id}


@app.post("/api/training/export")
async def export_training_data():
    """Export decision_log → JSONL training file."""
    import uuid, threading
    job_id = f"export_{uuid.uuid4().hex[:8]}"
    _training_jobs[job_id] = {"type": "export", "status": "queued",
                               "started_at": datetime.utcnow().isoformat()}
    threading.Thread(target=_run_export, args=(job_id,), daemon=True).start()
    log.info("Training job queued: export")
    return {"status": "queued", "job_id": job_id}


def _run_replay(job_id: str, assets: list, samples: int):
    """Run generate_replay_training in a background thread."""
    import sys as _sys2
    from pathlib import Path
    _sys2.path.insert(0, str(Path(__file__).parent.parent))

    _training_jobs[job_id]["status"] = "running"
    _real_stdout, _real_stderr = _sys.stdout, _sys.stderr
    bridge = _LogBridge("[REPLAY]")
    _sys.stdout = _sys.stderr = bridge
    try:
        from scripts.generate_replay_training import generate_replay_data
        t = settings.training
        out_path = generate_replay_data(
            assets=assets,
            samples_per_asset=samples,
            append=True,          # merge with any existing decision_log examples
            out_dir=t.training_data_dir,
        )
        _training_jobs[job_id].update({"status": "done", "output_file": out_path})
        log.info("Replay job {} complete → {}", job_id, out_path)
    except Exception as e:
        _training_jobs[job_id].update({"status": "error", "error": str(e)})
        log.error("Replay job {} failed: {}", job_id, e)
    finally:
        bridge.flush()
        _sys.stdout, _sys.stderr = _real_stdout, _real_stderr


@app.post("/api/training/replay")
async def generate_replay(assets: str = "XAUUSD", samples: int = 200):
    """Generate historical replay training data from OHLCV + macro CSVs."""
    import uuid, threading
    from pathlib import Path
    # Require at least raw CSVs *or* the DuckDB with live data
    _raw_ok = Path("data/raw").exists() and any(Path("data/raw").glob("*.csv"))
    _db_ok  = Path("data/market_data.duckdb").exists()
    if not _raw_ok and not _db_ok:
        return {"status": "error",
                "message": "No data found. Run Collect Historical Data (Step 1) first, or ensure the bot has logged market data to DuckDB."}
    asset_list = [a.strip().upper() for a in assets.split(",") if a.strip()]
    job_id = f"replay_{uuid.uuid4().hex[:8]}"
    _training_jobs[job_id] = {
        "type": "replay", "status": "queued",
        "assets": asset_list, "samples": samples,
        "started_at": datetime.utcnow().isoformat(),
    }
    threading.Thread(target=_run_replay, args=(job_id, asset_list, samples), daemon=True).start()
    log.info("Training job queued: replay (assets={}, samples={})", asset_list, samples)
    return {"status": "queued", "job_id": job_id}


@app.post("/api/training/finetune")
async def finetune_model():
    """Start QLoRA fine-tuning (GPU required)."""
    import uuid, threading
    from pathlib import Path
    latest = Path(settings.training.training_data_dir) / "apex_training_latest.jsonl"
    if not latest.exists():
        return {"status": "error",
                "message": "No training data found. Run /api/training/export first."}
    job_id = f"ft_{uuid.uuid4().hex[:8]}"
    _training_jobs[job_id] = {"type": "finetune", "status": "queued",
                               "started_at": datetime.utcnow().isoformat()}
    threading.Thread(target=_run_finetune, args=(job_id,), daemon=True).start()
    log.info("Training job queued: finetune")
    return {"status": "queued", "job_id": job_id}


@app.post("/api/training/convert")
async def convert_model():
    """Convert fine-tuned model to GGUF and register with Ollama.

    Accepts either a merged model directory or LoRA adapter directory —
    searches multiple paths to handle local and Kaggle-downloaded layouts.
    """
    import uuid, threading, sys as _sys2
    from pathlib import Path
    _sys2.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.conversion import find_model_paths

    merged_path, adapter_path = find_model_paths(settings.training.model_output_dir)
    if merged_path is None and adapter_path is None:
        return {
            "status": "error",
            "message": (
                f"No model or adapter files found under '{settings.training.model_output_dir}'. "
                "Run Fine-Tune (Step 4) first."
            ),
        }
    job_id = f"conv_{uuid.uuid4().hex[:8]}"
    _training_jobs[job_id] = {
        "type": "convert", "status": "queued",
        "started_at": datetime.utcnow().isoformat(),
        "merged_path": str(merged_path or ""),
        "adapter_path": str(adapter_path or ""),
    }
    threading.Thread(target=_run_convert, args=(job_id,), daemon=True).start()
    log.info("Training job queued: convert (merged={}, adapter={})", merged_path, adapter_path)
    return {"status": "queued", "job_id": job_id}


@app.get("/api/training/status")
async def get_training_status():
    """Return all training job statuses + decision_log row count."""
    row_count = 0
    latest_file = None
    try:
        import duckdb
        from pathlib import Path
        db = settings.training.duckdb_path
        if Path(db).exists():
            con = duckdb.connect(db, read_only=True)
            tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
            if "decision_log" in tables:
                row_count = con.execute(
                    "SELECT COUNT(*) FROM decision_log WHERE outcome IS NOT NULL"
                ).fetchone()[0]
            con.close()
        latest = Path(settings.training.training_data_dir) / "apex_training_latest.jsonl"
        if latest.exists():
            latest_file = str(latest)
            with open(latest) as f:
                latest_file_lines = sum(1 for _ in f)
        else:
            latest_file_lines = 0
    except Exception:
        latest_file_lines = 0

    return {
        "decision_log_count": row_count,
        "min_required": settings.training.min_training_examples,
        "ready_for_export": row_count >= settings.training.min_training_examples,
        "latest_training_file": latest_file,
        "latest_training_examples": latest_file_lines,
        "jobs": list(_training_jobs.values())[-20:],   # last 20 jobs
        "ollama_model": settings.training.ollama_model_name,
        "base_model": settings.training.base_model,
    }


@app.post("/api/training/pipeline/run")
async def run_full_pipeline():
    """Trigger the full automated pipeline: Collect → Prepare → Fine-Tune → Convert → Reload."""
    if orchestrator._is_running:
        raise HTTPException(409, "Pipeline already running")
    orchestrator.run_full_llm_pipeline()
    return {
        "status": "started",
        "schedule": settings.training.llm_training_schedule,
        "message": "Full LLM pipeline started — watch BOT LOGS for [TRAINING] progress",
    }


@app.get("/api/training/pipeline/status")
async def get_pipeline_status():
    """Return pipeline running state and next scheduled run."""
    next_run = None
    try:
        job = _scheduler.get_job("weekly_llm_refresh")
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()
    except Exception:
        pass
    return {
        "is_running": orchestrator._is_running,
        "current_job_id": orchestrator._current_job_id,
        "schedule": settings.training.llm_training_schedule,
        "next_run": next_run,
    }


@app.get("/api/training/job/{job_id}")
async def get_job_status(job_id: str):
    """Get status of a specific training job."""
    job = _training_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


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
            try:
                # Wait up to 30 s for a client message; send heartbeat on timeout
                data = await asyncio.wait_for(ws.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                # No message in 30 s → send heartbeat to keep TCP alive
                try:
                    await ws.send_text(json.dumps({"type": "heartbeat", "ts": datetime.utcnow().isoformat()}))
                except Exception:
                    # Socket is dead (stale TCP) — exit cleanly
                    break
                continue
            except WebSocketDisconnect:
                # Client closed cleanly — exit loop
                break
            except Exception:
                # Any other receive error (RuntimeError, ConnectionError, etc.) — exit cleanly
                break

            # Parse and handle the command
            try:
                cmd = json.loads(data)
            except Exception:
                # Ignore malformed frames — do NOT crash the handler
                continue

            if cmd.get("type") == "ping":
                try:
                    await ws.send_text(json.dumps({"type": "pong"}))
                except Exception:
                    break
            elif cmd.get("type") == "subscribe":
                log.debug("WS client subscribed to: {}", cmd.get("channels"))

    except WebSocketDisconnect:
        log.info("WebSocket client disconnected")
    except Exception as e:
        log.debug("WebSocket handler exited: {}", e)
    finally:
        _ws_connections.discard(ws)
        unregister_ws_client(ws)


@app.post("/api/logs/truncate")
async def truncate_logs():
    """Clear DuckDB system logs and delete physical .log files."""
    try:
        import duckdb
        from core.logger import DB_PATH, LOG_DIR
        
        # 1. Truncate DuckDB table
        con = duckdb.connect(str(DB_PATH))
        con.execute("DELETE FROM system_logs")
        con.close()
        
        # 2. Delete physical log files (except today's active one to avoid locking issues)
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        count = 0
        for f in LOG_DIR.glob("*.log"):
            if today_str not in f.name:
                try:
                    f.unlink()
                    count += 1
                except Exception:
                    pass
                    
        log.info("Logs truncated (DB cleared, {} archived files deleted)", count)
        return {"status": "ok", "message": f"Logs cleared. Deleted {count} archived files."}
    except Exception as e:
        log.error("Failed to truncate logs: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════
#  SOP POSITION MANAGEMENT CYCLE (every 15 seconds)
# ═══════════════════════════════════════════════════════

_posmgr_broker = None  # reused across cycles — avoids MT5 reconnect every 15s

async def _run_position_management_cycle():
    """
    SOP Section 10 — 10-step management cycle.
    Runs every 15 seconds for all open positions.
    Always syncs live MT5 positions so manual/pre-existing trades are managed too.
    """
    global _bot_state, _posmgr_broker
    try:
        from utils.position_manager import position_manager
        from brokers.base import BrokerFactory
        if _posmgr_broker is None:
            _posmgr_broker = BrokerFactory(settings).get("MT5")
        if not _posmgr_broker.connected:
            await _posmgr_broker.connect()

        # Sync live MT5 positions into _bot_state.open_trades so that:
        # (a) trades placed before this session are managed, and
        # (b) trades closed externally are removed
        live_trades = await _posmgr_broker.get_open_trades()
        if live_trades:
            known_tickets = {str(t.broker_order_id) for t in _bot_state.open_trades if t.broker_order_id}
            for lt in live_trades:
                ticket = str(lt.broker_order_id or lt.id)
                if ticket not in known_tickets:
                    log.info("[POSMGR] Discovered untracked position {} {} ticket={} — adding to tracker",
                             lt.direction, lt.symbol, ticket)
                    _bot_state.open_trades.append(lt)

        if not _bot_state.open_trades:
            return

        await position_manager.run_cycle(_posmgr_broker, _bot_state.open_trades, _bot_state)
    except asyncio.CancelledError:
        # Scheduler is being shut down, exit gracefully
        log.debug("[POSMGR] Position management cycle cancelled (bot stopping)")
        raise
    except Exception as e:
        log.error("[POSMGR] Cycle exception: {}", e)
        _posmgr_broker = None  # force reconnect next cycle on error


# ═══════════════════════════════════════════════════════
#  STARTUP / SHUTDOWN
# ═══════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    log.info("=" * 60)
    # Restore persisted training config (kernel names, hyperparams, etc.)
    _load_training_config_json()
    from apscheduler.triggers.cron import CronTrigger

    # Start Scheduler
    from utils.trainer import trainer
    _scheduler.add_job(
        trainer.train_daily_model,
        trigger=CronTrigger(hour=0, minute=0), # Daily at midnight
        id="daily_retraining",
        replace_existing=True
    )

    # Schedule Full LLM Training Pipeline (Collection -> FT -> GGUF)
    try:
        _scheduler.add_job(
            orchestrator.run_full_llm_pipeline,
            trigger=CronTrigger.from_crontab(settings.training.llm_training_schedule),
            id="weekly_llm_refresh",
            replace_existing=True
        )
        log.info("📅 Scheduler: Full LLM pipeline scheduled ({})", settings.training.llm_training_schedule)
    except Exception as e:
        log.warning("⚠️ Failed to schedule full LLM pipeline: {}", e)

    # Schedule SOP position management cycle (every 15 seconds)
    _scheduler.add_job(
        _run_position_management_cycle,
        trigger="interval",
        seconds=settings.risk.position_mgmt_interval_sec,
        id="position_management",
        replace_existing=True,
        max_instances=1,
    )
    log.info("📐 SOP position manager scheduled every {}s", settings.risk.position_mgmt_interval_sec)

    _scheduler.start()

    # --- AUTOSTART BOT ---
    if settings.autostart:
        global _bot_running, _bot_task
        from core.bot_lifecycle import bot_manager
        
        if not _bot_running:
            _bot_running = True
            _bot_task = asyncio.create_task(_bot_main_loop())
            bot_manager.start()
            log.info("🚀 Bot AUTOSTART enabled — loop initiated")

@app.on_event("shutdown")
async def shutdown():
    global _bot_running
    _bot_running = False
    if _bot_task:
        _bot_task.cancel()
    # Stop APScheduler — without this it holds the event loop open
    try:
        if _scheduler.running:
            _scheduler.shutdown(wait=False)
    except Exception:
        pass
    # Close all open WebSocket connections so uvicorn exits immediately
    for ws in list(_ws_connections):
        try:
            await ws.close(code=1001)  # 1001 = Going Away
        except Exception:
            pass
    _ws_connections.clear()
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
