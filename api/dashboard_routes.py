"""
Dashboard-specific API routes
These routes are added to the main trading bot API server
to provide a unified service on port 8000.
"""
from fastapi import APIRouter, Request, HTTPException, WebSocket, WebSocketDisconnect
from typing import Optional
import duckdb
from pathlib import Path
from datetime import datetime, timezone
from core.logger import get_agent_logger
from core.bot_lifecycle import bot_manager

log = get_agent_logger("DASHBOARD_API")

# Create router with /api/v1 prefix
dashboard_router = APIRouter(prefix="/api/v1", tags=["dashboard"])

# WebSocket connections
active_ws_connections = set()


def utcnow():
    """Helper to get current UTC time with timezone"""
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════
#  LOGS ENDPOINT
# ═══════════════════════════════════════════════════════

@dashboard_router.get("/logs")
async def get_logs(
    limit: int = 500,
    level: Optional[str] = None,
    source: Optional[str] = None,
    order: str = "desc"
):
    """Get system logs from DuckDB"""
    try:
        db_path = Path("data/system_logs.duckdb")
        
        if not db_path.exists():
            return {"logs": [], "count": 0}
        
        con = duckdb.connect(str(db_path), read_only=True)
        
        query = "SELECT timestamp, level, agent, module, message FROM system_logs"
        conditions = []
        params = []
        
        if level and level != "ALL":
            conditions.append("level = ?")
            params.append(level)
        
        if source and source != "ALL":
            conditions.append("agent = ?")
            params.append(source)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        order_direction = "DESC" if order.lower() == "desc" else "ASC"
        query += f" ORDER BY timestamp {order_direction} LIMIT ?"
        params.append(limit)
        
        result = con.execute(query, params).fetchall()
        con.close()
        
        logs = []
        for row in result:
            logs.append({
                "timestamp": row[0].isoformat() if hasattr(row[0], 'isoformat') else str(row[0]),
                "level": row[1],
                "logger": row[2],
                "message": row[4],
                "context": None
            })
        
        return {"logs": logs, "count": len(logs)}
    
    except Exception as e:
        log.error(f"Failed to fetch logs: {e}")
        return {"logs": [], "count": 0}


# ═══════════════════════════════════════════════════════
#  BOT CONTROL ENDPOINTS
# ═══════════════════════════════════════════════════════

@dashboard_router.get("/bot/status")
async def get_bot_status():
    """Get current bot status from lifecycle manager"""
    status = bot_manager.get_status()
    return status.to_dict()


@dashboard_router.post("/bot/start")
async def start_bot_endpoint():
    """Start the trading bot"""
    if bot_manager.is_running():
        raise HTTPException(status_code=400, detail="Bot is already running")
    
    bot_manager.start()
    log.info("Bot started via dashboard")
    return {"message": "Bot started", "status": "running"}


@dashboard_router.post("/bot/stop")
async def stop_bot_endpoint():
    """Stop the trading bot"""
    if bot_manager.is_stopped():
        raise HTTPException(status_code=400, detail="Bot is already stopped")
    
    bot_manager.stop()
    log.info("Bot stopped via dashboard")
    return {"message": "Bot stopped", "status": "stopped"}


@dashboard_router.post("/bot/pause")
async def pause_bot_endpoint():
    """Pause the trading bot"""
    bot_manager.pause()
    log.info("Bot paused via dashboard")
    return {"message": "Bot paused", "status": "paused"}


@dashboard_router.post("/bot/restart")
async def restart_bot_endpoint():
    """Restart the trading bot"""
    bot_manager.restart()
    log.info("Bot restarted via dashboard")
    return {"message": "Bot restarted", "status": "running"}


@dashboard_router.get("/bot/activity")
async def get_bot_activity(limit: int = 100):
    """Get bot activity log from system logs"""
    try:
        db_path = Path("data/system_logs.duckdb")
        
        if not db_path.exists():
            return {"activities": [], "count": 0}
        
        con = duckdb.connect(str(db_path), read_only=True)
        
        query = """
            SELECT timestamp, level, agent, message 
            FROM system_logs 
            WHERE agent IN ('API', 'FAST_DECISION', 'ORCHESTRATOR', 'EXECUTION', 'BOT_LIFECYCLE')
            ORDER BY timestamp DESC 
            LIMIT ?
        """
        
        result = con.execute(query, [limit]).fetchall()
        con.close()
        
        activities = []
        for row in result:
            activities.append({
                "id": f"act_{hash(str(row))}",
                "timestamp": row[0].isoformat() if hasattr(row[0], 'isoformat') else str(row[0]),
                "activity_type": "BOT_ACTIVITY",
                "component": row[2],
                "description": row[3],
                "status": "success" if row[1] == "INFO" else "error"
            })
        
        return {"activities": activities, "count": len(activities)}
    
    except Exception as e:
        log.error(f"Failed to fetch activity log: {e}")
        return {"activities": [], "count": 0}


# ═══════════════════════════════════════════════════════
#  WEBSOCKET ENDPOINT
# ═══════════════════════════════════════════════════════

@dashboard_router.websocket("/ws/dashboard")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time dashboard updates"""
    await websocket.accept()
    active_ws_connections.add(websocket)
    log.info(f"WebSocket client connected. Total: {len(active_ws_connections)}")
    
    try:
        await websocket.send_json({
            "type": "connection_established",
            "timestamp": utcnow().isoformat(),
            "message": "Connected to APEX Dashboard"
        })
        
        while True:
            try:
                data = await websocket.receive_text()
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": utcnow().isoformat()
                })
            except Exception:
                break
    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.error(f"WebSocket error: {e}")
    finally:
        active_ws_connections.discard(websocket)
        log.info(f"WebSocket client disconnected. Total: {len(active_ws_connections)}")


async def broadcast_to_dashboard(message: dict):
    """Broadcast message to all connected WebSocket clients"""
    if not active_ws_connections:
        return
    
    message["timestamp"] = utcnow().isoformat()
    dead_connections = set()
    
    for connection in active_ws_connections:
        try:
            await connection.send_json(message)
        except Exception:
            dead_connections.add(connection)
    
    active_ws_connections.difference_update(dead_connections)


# ═══════════════════════════════════════════════════════
#  BOT DECISIONS HISTORY
# ═══════════════════════════════════════════════════════

@dashboard_router.get("/decisions")
async def get_decision_history(limit: int = 50):
    """
    Get bot decision history (GO/NOGO decisions from orchestrator).
    Returns decisions from bot_decisions table in DuckDB with timing info.
    """
    from memory.duckdb_store import DuckDBStore
    from core.config import settings
    import json
    
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
                
                return {
                    "decisions": decisions,
                    "total": len(decisions),
                    "limit": limit,
                }
            else:
                # bot_decisions is empty, fall back to decision_log
                raise Exception("bot_decisions empty, using fallback")
            
        except Exception as e:
            # Fall back to decision_log table (old format)
            log.debug(f"Using decision_log fallback: {e}")
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
            
            return {
                "decisions": decisions,
                "total": len(decisions),
                "limit": limit,
            }
        
    except Exception as e:
        log.warning(f"Failed to fetch decision history: {e}")
        # Return empty list if table doesn't exist yet
        return {
            "decisions": [],
            "total": 0,
            "limit": limit,
            "error": str(e)
        }
