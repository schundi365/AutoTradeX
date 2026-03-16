"""
APEX Bot — Dashboard Backend (FastAPI)
Real-time WebSocket server and REST API for dashboard visualization.

Requirements: 17.3, 18.1, 18.2, 18.3, 19.5, 20.3, 21.5, 22.1, 22.2, 22.3, 22.4, 22.5
"""
import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set
from collections import defaultdict
from functools import lru_cache
import hashlib

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json

from core.logger import get_agent_logger
from data.trade_journal import trade_journal, DecisionType
from ml.model_registry import ModelRegistry
from core.outcome_tracker import OutcomeTracker
from data.historical_data_warehouse import HistoricalDataWarehouse
from core.bot_lifecycle import bot_lifecycle

log = get_agent_logger("DASHBOARD_BACKEND")

# Helper function for timezone-aware UTC datetime
def utcnow() -> datetime:
    """Get current UTC time as timezone-aware datetime"""
    return datetime.now(timezone.utc)

# Initialize components
model_registry = ModelRegistry()
outcome_tracker = OutcomeTracker()
warehouse = HistoricalDataWarehouse()

# Response cache with TTL
response_cache: Dict[str, tuple[float, any]] = {}
CACHE_TTL = 5  # seconds


def get_cache_key(endpoint: str, **params) -> str:
    """Generate cache key from endpoint and parameters"""
    param_str = json.dumps(params, sort_keys=True)
    return hashlib.md5(f"{endpoint}:{param_str}".encode()).hexdigest()


def get_cached_response(cache_key: str) -> Optional[any]:
    """Get cached response if not expired"""
    if cache_key in response_cache:
        timestamp, data = response_cache[cache_key]
        if time.time() - timestamp < CACHE_TTL:
            return data
        else:
            del response_cache[cache_key]
    return None


def set_cached_response(cache_key: str, data: any) -> None:
    """Cache response with current timestamp"""
    response_cache[cache_key] = (time.time(), data)
    
    # Clean old cache entries (keep last 100)
    if len(response_cache) > 100:
        oldest_keys = sorted(response_cache.keys(), 
                           key=lambda k: response_cache[k][0])[:50]
        for key in oldest_keys:
            del response_cache[key]


# FastAPI app
dashboard_app = FastAPI(title="APEX Dashboard API", version="1.0.0")

dashboard_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket connections
active_connections: Set[WebSocket] = set()

# Rate limiting
rate_limit_store: Dict[str, List[float]] = defaultdict(list)
RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_WINDOW = 60  # seconds


# ═══════════════════════════════════════════════════════
#  RATE LIMITING MIDDLEWARE
# ═══════════════════════════════════════════════════════

async def check_rate_limit(request: Request) -> None:
    """
    Check rate limit for incoming requests.
    Requirements: 22.5 - 100 requests per minute per IP
    """
    client_ip = request.client.host
    current_time = time.time()
    
    # Clean old requests outside the window
    rate_limit_store[client_ip] = [
        req_time for req_time in rate_limit_store[client_ip]
        if current_time - req_time < RATE_LIMIT_WINDOW
    ]
    
    # Check if limit exceeded
    if len(rate_limit_store[client_ip]) >= RATE_LIMIT_REQUESTS:
        retry_after = int(RATE_LIMIT_WINDOW - (current_time - rate_limit_store[client_ip][0]))
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)}
        )
    
    # Add current request
    rate_limit_store[client_ip].append(current_time)


# ═══════════════════════════════════════════════════════
#  WEBSOCKET SERVER
# ═══════════════════════════════════════════════════════

@dashboard_app.websocket("/ws/dashboard")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time dashboard updates.
    
    Message Types:
    - market_update: Market data and indicators (1s frequency)
    - trade_update: Trade opened/closed (immediate)
    - decision_update: Trading decision made (immediate)
    - alert: System alert or warning (immediate)
    - performance_update: Performance metrics (5s frequency)
    - model_update: Model prediction or retraining (5min frequency)
    
    Requirements: 17.3, 18.2, 20.3, 21.5
    """
    await websocket.accept()
    active_connections.add(websocket)
    log.info(f"WebSocket client connected. Total connections: {len(active_connections)}")
    
    try:
        # Send initial state
        await websocket.send_json({
            "type": "connection_established",
            "timestamp": utcnow().isoformat(),
            "message": "Connected to APEX Dashboard"
        })
        
        # Keep connection alive - just wait for disconnect
        # The periodic_websocket_updates task will send heartbeats
        while True:
            try:
                # Wait for messages from client or disconnect
                data = await websocket.receive_text()
                # Echo back for now (can add subscription logic later)
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": utcnow().isoformat()
                })
            except Exception:
                # Connection closed or error
                break
    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.error(f"WebSocket error: {e}")
    finally:
        active_connections.discard(websocket)
        log.info(f"WebSocket client disconnected. Total connections: {len(active_connections)}")


async def broadcast_message(message: Dict) -> None:
    """
    Broadcast message to all connected WebSocket clients.
    
    Args:
        message: Message dictionary with 'type' and data
    """
    if not active_connections:
        return
    
    message["timestamp"] = utcnow().isoformat()
    dead_connections = set()
    
    for connection in active_connections:
        try:
            await connection.send_json(message)
        except Exception as e:
            log.debug(f"Failed to send to connection: {e}")
            dead_connections.add(connection)
    
    # Remove dead connections
    active_connections.difference_update(dead_connections)


# Helper functions for broadcasting specific message types
async def broadcast_market_update(symbol: str, data: Dict) -> None:
    """Broadcast market data update (1s frequency)"""
    await broadcast_message({
        "type": "market_update",
        "symbol": symbol,
        "data": data
    })


async def broadcast_trade_update(trade_data: Dict) -> None:
    """Broadcast trade update (immediate)"""
    await broadcast_message({
        "type": "trade_update",
        "data": trade_data
    })


async def broadcast_decision_update(decision_data: Dict) -> None:
    """Broadcast trading decision (immediate)"""
    await broadcast_message({
        "type": "decision_update",
        "data": decision_data
    })


async def broadcast_alert(alert_type: str, message: str, severity: str = "info") -> None:
    """Broadcast system alert (immediate)"""
    await broadcast_message({
        "type": "alert",
        "alert_type": alert_type,
        "message": message,
        "severity": severity
    })


async def broadcast_performance_update(metrics: Dict) -> None:
    """Broadcast performance metrics (5s frequency)"""
    await broadcast_message({
        "type": "performance_update",
        "data": metrics
    })


async def broadcast_model_update(model_data: Dict) -> None:
    """Broadcast model update (5min frequency)"""
    await broadcast_message({
        "type": "model_update",
        "data": model_data
    })


# ═══════════════════════════════════════════════════════
#  BACKGROUND TASKS FOR WEBSOCKET UPDATES
# ═══════════════════════════════════════════════════════

async def periodic_websocket_updates():
    """
    Background task to send periodic updates to WebSocket clients.
    This keeps the connection alive and provides real-time data.
    """
    while True:
        try:
            if active_connections:
                # Send market updates every 5 seconds
                await broadcast_message({
                    "type": "heartbeat",
                    "active_connections": len(active_connections),
                    "timestamp": utcnow().isoformat()
                })
            
            await asyncio.sleep(5)
        except Exception as e:
            log.error(f"Error in periodic WebSocket updates: {e}")
            await asyncio.sleep(5)


@dashboard_app.on_event("startup")
async def startup_event():
    """Start background tasks on application startup"""
    log.info("Starting background tasks...")
    asyncio.create_task(periodic_websocket_updates())


# ═══════════════════════════════════════════════════════
#  REST API ENDPOINTS - MARKET DATA
# ═══════════════════════════════════════════════════════

@dashboard_app.get("/api/v1/market/symbols")
async def get_symbols(request: Request):
    """
    List all configured trading symbols.
    Requirements: 22.1
    """
    await check_rate_limit(request)
    
    # Get symbols from config or database
    symbols = [
        {"symbol": "XAUUSD", "name": "Gold", "asset_class": "METALS"},
        {"symbol": "EURUSD", "name": "Euro/USD", "asset_class": "FOREX"},
        {"symbol": "BTCUSD", "name": "Bitcoin", "asset_class": "CRYPTO"},
        {"symbol": "USOIL", "name": "Crude Oil", "asset_class": "COMMODITIES"},
    ]
    
    return {"symbols": symbols, "count": len(symbols)}


@dashboard_app.get("/api/v1/market/ohlcv/{symbol}")
async def get_ohlcv(
    symbol: str,
    request: Request,
    timeframe: str = "H1",
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 100
):
    """
    Get historical OHLCV data for a symbol.
    Requirements: 22.1
    """
    await check_rate_limit(request)
    
    # Parse dates
    if end is None:
        end_date = utcnow()
    else:
        end_date = datetime.fromisoformat(end)
    
    if start is None:
        start_date = end_date - timedelta(days=7)
    else:
        start_date = datetime.fromisoformat(start)
    
    # Query warehouse
    try:
        df = warehouse.query_ohlcv(symbol, timeframe, start_date, end_date)
        
        # Limit results
        if len(df) > limit:
            df = df.tail(limit)
        
        # Convert to records
        records = df.to_dict('records')
        
        # Convert timestamps to ISO format
        for record in records:
            if 'timestamp' in record:
                record['timestamp'] = record['timestamp'].isoformat()
        
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "data": records,
            "count": len(records)
        }
    except Exception as e:
        log.error(f"Error querying OHLCV: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@dashboard_app.get("/api/v1/market/indicators/{symbol}")
async def get_indicators(symbol: str, request: Request):
    """
    Get current technical indicators for a symbol.
    Requirements: 22.2
    """
    await check_rate_limit(request)
    
    # Mock indicators (integrate with FeaturePipeline in production)
    indicators = {
        "symbol": symbol,
        "timestamp": utcnow().isoformat(),
        "rsi": 65.3,
        "adx": 28.5,
        "atr": 12.5,
        "atr_pct": 0.6,
        "ema_20": 2050.25,
        "ema_50": 2045.10,
        "ema_200": 2030.50,
        "macd": 5.2,
        "macd_signal": 4.8,
        "bb_upper": 2055.0,
        "bb_lower": 2045.0,
        "volume_ratio": 1.2
    }
    
    return indicators


@dashboard_app.get("/api/v1/market/orderbook/{symbol}")
async def get_orderbook(symbol: str, request: Request):
    """
    Get current order book for a symbol.
    Requirements: 22.2
    """
    await check_rate_limit(request)
    
    # Mock order book (integrate with OrderBookCollector in production)
    orderbook = {
        "symbol": symbol,
        "timestamp": utcnow().isoformat(),
        "bids": [
            {"price": 2050.20, "volume": 100, "num_orders": 5},
            {"price": 2050.15, "volume": 150, "num_orders": 8},
            {"price": 2050.10, "volume": 200, "num_orders": 12},
        ],
        "asks": [
            {"price": 2050.25, "volume": 120, "num_orders": 6},
            {"price": 2050.30, "volume": 180, "num_orders": 9},
            {"price": 2050.35, "volume": 220, "num_orders": 15},
        ],
        "bid_volume": 450,
        "ask_volume": 520,
        "imbalance": 0.464
    }
    
    return orderbook


# ═══════════════════════════════════════════════════════
#  REST API ENDPOINTS - PERFORMANCE
# ═══════════════════════════════════════════════════════

@dashboard_app.get("/api/v1/performance/metrics")
async def get_performance_metrics(request: Request):
    """
    Get current performance metrics (cached for 5s).
    Requirements: 18.1, 18.2
    """
    await check_rate_limit(request)
    
    # Check cache
    cache_key = get_cache_key("performance_metrics")
    cached = get_cached_response(cache_key)
    if cached is not None:
        return cached
    
    # Get performance from outcome tracker
    perf = outcome_tracker.get_recent_performance(lookback_trades=100)
    
    metrics = {
        "total_return": 0.0,
        "sharpe_ratio": 0.0,
        "sortino_ratio": 0.0,
        "max_drawdown": 0.0,
        "win_rate": perf.get("win_rate", 0.0),
        "total_trades": perf.get("total_trades", 0),
        "wins": perf.get("wins", 0),
        "losses": perf.get("losses", 0),
        "avg_pnl": perf.get("avg_pnl", 0.0),
        "profit_factor": 0.0,
        "timestamp": utcnow().isoformat()
    }
    
    # Cache result
    set_cached_response(cache_key, metrics)
    
    return metrics


@dashboard_app.get("/api/v1/performance/equity-curve")
async def get_equity_curve(
    request: Request,
    start: Optional[str] = None,
    end: Optional[str] = None
):
    """
    Get equity curve data.
    Requirements: 18.1
    """
    await check_rate_limit(request)
    
    # Parse dates
    if end is None:
        end_date = utcnow()
    else:
        end_date = datetime.fromisoformat(end)
    
    if start is None:
        start_date = end_date - timedelta(days=30)
    else:
        start_date = datetime.fromisoformat(start)
    
    # Get trade history from journal
    df = trade_journal.get_decision_history(
        decision_type=DecisionType.TRADE_CLOSED,
        start_date=start_date,
        end_date=end_date,
        limit=1000
    )
    
    # Calculate equity curve
    equity_curve = []
    equity = 10000.0  # Starting equity
    
    for _, row in df.iterrows():
        if row.get('pnl') is not None:
            equity += row['pnl']
            equity_curve.append({
                "timestamp": row['timestamp'].isoformat() if hasattr(row['timestamp'], 'isoformat') else str(row['timestamp']),
                "equity": round(equity, 2),
                "pnl": round(row['pnl'], 2)
            })
    
    return {
        "data": equity_curve,
        "count": len(equity_curve),
        "start_equity": 10000.0,
        "end_equity": equity if equity_curve else 10000.0
    }


@dashboard_app.get("/api/v1/performance/trades")
async def get_trade_history(
    request: Request,
    limit: int = 100,
    offset: int = 0
):
    """
    Get trade history.
    Requirements: 18.3
    """
    await check_rate_limit(request)
    
    # Get trades from journal
    df = trade_journal.get_decision_history(
        decision_type=DecisionType.TRADE_CLOSED,
        limit=limit
    )
    
    # Convert to records
    trades = []
    for _, row in df.iterrows():
        trade = {
            "entry_id": row.get('entry_id'),
            "timestamp": row['timestamp'].isoformat() if hasattr(row['timestamp'], 'isoformat') else str(row['timestamp']),
            "symbol": row.get('symbol'),
            "direction": row.get('direction'),
            "entry_price": row.get('entry_price'),
            "exit_price": row.get('exit_price'),
            "pnl": row.get('pnl'),
            "holding_time_seconds": row.get('holding_time_seconds'),
            "exit_reason": row.get('exit_reason')
        }
        trades.append(trade)
    
    return {
        "trades": trades,
        "count": len(trades),
        "limit": limit,
        "offset": offset
    }


# ═══════════════════════════════════════════════════════
#  REST API ENDPOINTS - TRADE JOURNAL
# ═══════════════════════════════════════════════════════

@dashboard_app.get("/api/v1/journal/decisions")
async def get_decisions(
    request: Request,
    symbol: Optional[str] = None,
    decision: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 20  # Reduced from 50 for faster response
):
    """
    Get decision history with search/filter (cached for 5s).
    Requirements: 19.5, 22.3
    """
    await check_rate_limit(request)
    
    # Check cache
    cache_key = get_cache_key("journal_decisions", symbol=symbol, decision=decision, 
                              start=start, end=end, limit=limit)
    cached = get_cached_response(cache_key)
    if cached is not None:
        return cached
    
    # Parse dates
    start_date = datetime.fromisoformat(start) if start else None
    end_date = datetime.fromisoformat(end) if end else None
    
    # Query journal
    df = trade_journal.get_decision_history(
        symbol=symbol,
        decision=decision,
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )
    
    # Convert to records
    decisions = []
    for _, row in df.iterrows():
        decision_entry = {
            "entry_id": row.get('entry_id'),
            "timestamp": row['timestamp'].isoformat() if hasattr(row['timestamp'], 'isoformat') else str(row['timestamp']),
            "decision_type": row.get('decision_type'),
            "symbol": row.get('symbol'),
            "direction": row.get('direction'),
            "decision": row.get('decision'),
            "confidence": row.get('confidence'),
            "signal_score": row.get('signal_score'),
            "reasoning": row.get('reasoning'),
            "decision_maker": row.get('decision_maker'),
            "pnl": row.get('pnl')
        }
        decisions.append(decision_entry)
    
    result = {
        "decisions": decisions,
        "count": len(decisions),
        "limit": limit
    }
    
    # Cache result
    set_cached_response(cache_key, result)
    
    return result


@dashboard_app.get("/api/v1/journal/decisions/{entry_id}")
async def get_decision_details(entry_id: str, request: Request):
    """
    Get detailed information for a specific decision.
    Requirements: 22.3
    """
    await check_rate_limit(request)
    
    # Get decision by ID
    decision = trade_journal.get_decision_by_id(entry_id)
    
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
    
    # Convert timestamp
    if 'timestamp' in decision and hasattr(decision['timestamp'], 'isoformat'):
        decision['timestamp'] = decision['timestamp'].isoformat()
    
    return decision


@dashboard_app.get("/api/v1/journal/export")
async def export_journal(
    request: Request,
    format: str = "json",
    start: Optional[str] = None,
    end: Optional[str] = None
):
    """
    Export trade journal as CSV or JSON.
    Requirements: 22.3
    """
    await check_rate_limit(request)
    
    # Parse dates
    start_date = datetime.fromisoformat(start) if start else None
    end_date = datetime.fromisoformat(end) if end else None
    
    # Get data
    df = trade_journal.get_decision_history(
        start_date=start_date,
        end_date=end_date,
        limit=10000
    )
    
    if format.lower() == "csv":
        # Convert to CSV
        csv_data = df.to_csv(index=False)
        return {
            "format": "csv",
            "data": csv_data,
            "count": len(df)
        }
    else:
        # Convert to JSON
        records = df.to_dict('records')
        # Convert timestamps
        for record in records:
            if 'timestamp' in record and hasattr(record['timestamp'], 'isoformat'):
                record['timestamp'] = record['timestamp'].isoformat()
        
        return {
            "format": "json",
            "data": records,
            "count": len(records)
        }


# ═══════════════════════════════════════════════════════
#  REST API ENDPOINTS - MODELS
# ═══════════════════════════════════════════════════════

@dashboard_app.get("/api/v1/models")
async def get_models(
    request: Request,
    model_type: Optional[str] = None,
    deployment_status: Optional[str] = None
):
    """
    List all models with optional filters.
    Requirements: 15.5, 22.4
    """
    await check_rate_limit(request)
    
    # Build filters
    filters = {}
    if model_type:
        filters['model_type'] = model_type
    if deployment_status:
        filters['deployment_status'] = deployment_status
    
    # Query registry
    models = model_registry.list_models(filters=filters if filters else None)
    
    # Convert to dict
    model_list = []
    for model in models:
        model_dict = {
            "model_id": model.model_id,
            "model_name": model.model_name,
            "model_type": model.model_type,
            "version": model.version,
            "created_at": model.created_at.isoformat(),
            "deployment_status": model.deployment_status,
            "deployment_environment": model.deployment_environment,
            "train_metrics": model.train_metrics,
            "validation_metrics": model.validation_metrics,
            "test_metrics": model.test_metrics
        }
        model_list.append(model_dict)
    
    return {
        "models": model_list,
        "count": len(model_list)
    }


@dashboard_app.get("/api/v1/models/{model_id}")
async def get_model_metadata(model_id: str, request: Request):
    """
    Get model metadata by ID.
    Requirements: 22.4
    """
    await check_rate_limit(request)
    
    try:
        metadata, _ = model_registry.get_model(model_id)
        
        return {
            "model_id": metadata.model_id,
            "model_name": metadata.model_name,
            "model_type": metadata.model_type,
            "version": metadata.version,
            "created_at": metadata.created_at.isoformat(),
            "training_start_date": metadata.training_start_date.isoformat() if hasattr(metadata.training_start_date, 'isoformat') else str(metadata.training_start_date),
            "training_end_date": metadata.training_end_date.isoformat() if hasattr(metadata.training_end_date, 'isoformat') else str(metadata.training_end_date),
            "num_training_samples": metadata.num_training_samples,
            "hyperparameters": metadata.hyperparameters,
            "feature_names": metadata.feature_names,
            "num_features": metadata.num_features,
            "train_metrics": metadata.train_metrics,
            "validation_metrics": metadata.validation_metrics,
            "test_metrics": metadata.test_metrics,
            "deployment_status": metadata.deployment_status,
            "deployment_timestamp": metadata.deployment_timestamp.isoformat() if metadata.deployment_timestamp else None,
            "deployment_environment": metadata.deployment_environment,
            "git_commit_hash": metadata.git_commit_hash,
            "training_script_path": metadata.training_script_path
        }
    except ValueError:
        raise HTTPException(status_code=404, detail="Model not found")


@dashboard_app.get("/api/v1/models/{model_id}/download")
async def download_model(model_id: str, request: Request):
    """
    Download model file.
    Requirements: 22.4
    """
    await check_rate_limit(request)
    
    try:
        metadata, model_file = model_registry.get_model(model_id)
        
        # Return model file as bytes
        from fastapi.responses import Response
        
        filename = f"{metadata.model_name}_v{metadata.version}.pkl"
        return Response(
            content=model_file,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Model not found")


@dashboard_app.get("/api/v1/models/current")
async def get_current_model(request: Request, model_type: str = "XGBOOST"):
    """
    Get currently deployed model.
    Requirements: 22.4
    """
    await check_rate_limit(request)
    
    metadata = model_registry.get_current_production_model(model_type)
    
    if not metadata:
        return {"message": f"No production model found for type {model_type}"}
    
    return {
        "model_id": metadata.model_id,
        "model_name": metadata.model_name,
        "model_type": metadata.model_type,
        "version": metadata.version,
        "deployment_timestamp": metadata.deployment_timestamp.isoformat() if metadata.deployment_timestamp else None,
        "deployment_environment": metadata.deployment_environment,
        "validation_metrics": metadata.validation_metrics,
        "test_metrics": metadata.test_metrics
    }


# ═══════════════════════════════════════════════════════
#  HEALTH CHECK
# ═══════════════════════════════════════════════════════

@dashboard_app.get("/api/v1/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": utcnow().isoformat(),
        "active_connections": len(active_connections)
    }


# ═══════════════════════════════════════════════════════
#  REST API ENDPOINTS - LOGS
# ═══════════════════════════════════════════════════════

@dashboard_app.get("/api/v1/logs")
async def get_logs(
    request: Request,
    limit: int = 500,
    level: Optional[str] = None,
    source: Optional[str] = None,
    order: str = "desc"  # "desc" for newest first, "asc" for oldest first
):
    """
    Get system logs with optional filtering from DuckDB.
    """
    await check_rate_limit(request)
    
    try:
        import duckdb
        from pathlib import Path
        
        # Connect to the logs database
        db_path = Path(__file__).parent.parent / "data" / "system_logs.duckdb"
        
        if not db_path.exists():
            log.warning(f"Logs database not found at {db_path}")
            return {"logs": [], "count": 0}
        
        con = duckdb.connect(str(db_path), read_only=True)
        
        # Build query with filters
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
        
        # Add order by clause (default DESC for newest first)
        order_direction = "DESC" if order.lower() == "desc" else "ASC"
        query += f" ORDER BY timestamp {order_direction} LIMIT ?"
        params.append(limit)
        
        # Execute query
        result = con.execute(query, params).fetchall()
        con.close()
        
        # Format results — field names MUST match the WebSocket log payload:
        # { type, time, level, msg, agent, module }
        # so injectLogLine / addLogLine work identically for REST and live logs.
        logs = []
        for row in result:
            ts = row[0]
            time_str = ts.strftime("%H:%M:%S") if hasattr(ts, "strftime") else str(ts)[11:19]
            logs.append({
                "time":   time_str,
                "level":  row[1],   # INFO | WARN | TRADE | SIGNAL | AI
                "agent":  row[2],   # agent tag stored by get_agent_logger()
                "module": row[3],
                "msg":    row[4],
            })

        return {"logs": logs, "count": len(logs)}
    
    except Exception as e:
        log.error(f"Failed to fetch logs from database: {e}")
        # Return empty logs instead of failing
        return {"logs": [], "count": 0}


@dashboard_app.post("/api/logs/truncate")
async def truncate_logs(request: Request):
    """
    Truncate the system_logs table in DuckDB.
    Called by the dashboard 'CLEAR' button.
    """
    await check_rate_limit(request)
    try:
        import duckdb
        from pathlib import Path
        db_path = Path(__file__).parent.parent / "data" / "system_logs.duckdb"
        if not db_path.exists():
            return {"ok": True, "message": "No log database found — nothing to truncate"}
        con = duckdb.connect(str(db_path))
        con.execute("DELETE FROM system_logs")
        con.close()
        log.info("[DASHBOARD] Log database truncated by user")
        return {"ok": True, "message": "Logs cleared successfully"}
    except Exception as e:
        log.error(f"Failed to truncate logs: {e}")
        return {"ok": False, "message": str(e)}


# ═══════════════════════════════════════════════════════
#  REST API ENDPOINTS - CONFIGURATION
# ═══════════════════════════════════════════════════════

@dashboard_app.get("/api/v1/config")
async def get_config(request: Request):
    """
    Get current bot configuration.
    """
    await check_rate_limit(request)
    
    from core.config import settings
    
    config = {
        "environment": settings.env.value,
        "risk": {
            "max_risk_per_trade_pct": settings.risk.max_risk_per_trade_pct,
            "max_combined_risk_pct": settings.risk.max_combined_risk_pct,
            "max_daily_drawdown_pct": settings.risk.max_daily_drawdown_pct,
            "max_consecutive_losses": settings.risk.max_consecutive_losses,
            "min_equity_pct": settings.risk.min_equity_pct,
            "max_open_trades": settings.risk.max_open_trades,
            "max_trades_per_symbol": settings.risk.max_trades_per_symbol,
            "max_lot_size": settings.risk.max_lot_size,
            "min_signal_score": settings.risk.min_signal_score,
        },
        "strategy": {
            "enabled_strategies": settings.strategy.enabled_strategies,
        },
        "assets": {
            "metals": settings.assets.metals,
            "commodities": settings.assets.commodities,
            "forex": settings.assets.forex,
            "crypto": settings.assets.crypto,
            "stocks": settings.assets.stocks,
        },
        "llm": {
            "provider": settings.llm_provider.value,
            "model": settings.llm_model,
            "timeout": settings.llm_timeout,
        }
    }
    
    return config


@dashboard_app.patch("/api/v1/config/{section}")
async def update_config(section: str, request: Request):
    """
    Update a configuration section.
    """
    await check_rate_limit(request)
    
    try:
        data = await request.json()
        
        # Validate section
        valid_sections = ["risk", "strategy", "assets", "llm"]
        if section not in valid_sections:
            raise HTTPException(status_code=400, detail=f"Invalid section: {section}")
        
        # Update configuration (in production, persist to database or config file)
        from core.config import settings
        
        if section == "risk":
            for key, value in data.items():
                if hasattr(settings.risk, key):
                    setattr(settings.risk, key, value)
        elif section == "strategy":
            for key, value in data.items():
                if hasattr(settings.strategy, key):
                    setattr(settings.strategy, key, value)
        elif section == "assets":
            for key, value in data.items():
                if hasattr(settings.assets, key):
                    setattr(settings.assets, key, value)
        elif section == "llm":
            # LLM settings are at root level
            if "provider" in data:
                settings.llm_provider = data["provider"]
            if "model" in data:
                settings.llm_model = data["model"]
            if "timeout" in data:
                settings.llm_timeout = data["timeout"]
        
        log.info(f"Configuration section '{section}' updated: {data}")
        
        return {"message": f"Configuration section '{section}' updated successfully"}
    
    except Exception as e:
        log.error(f"Failed to update configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════
#  REST API ENDPOINTS - MODEL TRAINING
# ═══════════════════════════════════════════════════════

@dashboard_app.get("/api/v1/training/jobs")
async def get_training_jobs(request: Request):
    """
    Get list of training jobs.
    """
    await check_rate_limit(request)
    
    # Mock training jobs (integrate with actual training pipeline in production)
    jobs = [
        {
            "job_id": "job_001",
            "model_type": "XGBOOST",
            "status": "completed",
            "progress": 100,
            "started_at": (utcnow() - timedelta(hours=2)).isoformat(),
            "completed_at": (utcnow() - timedelta(hours=1)).isoformat(),
            "metrics": {
                "accuracy": 0.58,
                "precision": 0.56,
                "recall": 0.60,
                "f1_score": 0.58,
                "roc_auc": 0.62
            }
        }
    ]
    
    return {"jobs": jobs, "count": len(jobs)}


@dashboard_app.get("/api/v1/training/deployments")
async def get_deployments(request: Request):
    """
    Get list of model deployments.
    """
    await check_rate_limit(request)
    
    # Get from model registry
    models = model_registry.list_models(filters={"deployment_status": "PRODUCTION"})
    
    deployments = []
    for model in models:
        deployments.append({
            "model_id": model.model_id,
            "model_name": model.model_name,
            "version": model.version,
            "status": model.deployment_status.lower(),
            "environment": model.deployment_environment.lower() if model.deployment_environment else "paper",
            "deployed_at": model.deployment_timestamp.isoformat() if model.deployment_timestamp else None
        })
    
    return {"deployments": deployments, "count": len(deployments)}


@dashboard_app.post("/api/v1/training/start")
async def start_training(request: Request):
    """
    Start a new model training job.
    """
    await check_rate_limit(request)
    
    try:
        data = await request.json()
        model_type = data.get("model_type", "XGBOOST")
        lookback_months = data.get("lookback_months", 6)
        validation_split = data.get("validation_split", 0.2)
        hyperparameter_tuning = data.get("hyperparameter_tuning", True)
        
        # Start training asynchronously (integrate with actual training pipeline)
        job_id = f"job_{int(time.time())}"
        
        log.info(f"Starting training job {job_id}: {model_type}, lookback={lookback_months}mo")
        
        # In production, trigger actual training pipeline here
        # For now, return mock response
        
        return {
            "job_id": job_id,
            "status": "pending",
            "message": "Training job started successfully"
        }
    
    except Exception as e:
        log.error(f"Failed to start training: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@dashboard_app.post("/api/v1/training/deploy/{model_id}")
async def deploy_model(model_id: str, request: Request):
    """
    Deploy a model to an environment.
    """
    await check_rate_limit(request)
    
    try:
        data = await request.json()
        environment = data.get("environment", "paper")
        
        # Update model registry
        metadata, _ = model_registry.get_model(model_id)
        metadata.deployment_status = "PRODUCTION"
        metadata.deployment_environment = environment.upper()
        metadata.deployment_timestamp = utcnow()
        
        # In production, update the registry database
        log.info(f"Model {model_id} deployed to {environment}")
        
        return {
            "message": f"Model deployed to {environment} successfully",
            "model_id": model_id,
            "environment": environment
        }
    
    except ValueError:
        raise HTTPException(status_code=404, detail="Model not found")
    except Exception as e:
        log.error(f"Failed to deploy model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@dashboard_app.post("/api/v1/training/retire/{model_id}")
async def retire_model(model_id: str, request: Request):
    """
    Retire a deployed model.
    """
    await check_rate_limit(request)
    
    try:
        # Update model registry
        metadata, _ = model_registry.get_model(model_id)
        metadata.deployment_status = "RETIRED"
        
        # In production, update the registry database
        log.info(f"Model {model_id} retired")
        
        return {
            "message": "Model retired successfully",
            "model_id": model_id
        }
    
    except ValueError:
        raise HTTPException(status_code=404, detail="Model not found")
    except Exception as e:
        log.error(f"Failed to retire model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════
#  REST API ENDPOINTS - BOT CONTROL & ACTIVITY
# ═══════════════════════════════════════════════════════

# Global bot state (in production, use database or Redis)
bot_state = {
    "status": "stopped",
    "uptime_seconds": 0,
    "last_started": utcnow().isoformat(),
    "last_stopped": utcnow().isoformat(),
    "active_positions": 0,
    "pending_orders": 0,
    "error_message": None
}

activity_log_store = []
scheduled_jobs_store = []
async_jobs_store = []


@dashboard_app.get("/api/v1/bot/status")
async def get_bot_status(request: Request):
    """
    Get current bot status and statistics.
    """
    await check_rate_limit(request)
    
    # Update uptime if running
    if bot_state["status"] == "running" and bot_state["last_started"]:
        start_time = datetime.fromisoformat(bot_state["last_started"])
        bot_state["uptime_seconds"] = int((utcnow() - start_time).total_seconds())
    
    return bot_state


@dashboard_app.post("/api/v1/bot/start")
async def start_bot(request: Request):
    """
    Start the trading bot.
    """
    await check_rate_limit(request)
    
    if bot_state["status"] == "running":
        raise HTTPException(status_code=400, detail="Bot is already running")
    
    try:
        # In production, trigger actual bot startup
        bot_state["status"] = "running"
        bot_state["last_started"] = utcnow().isoformat()
        bot_state["uptime_seconds"] = 0
        bot_state["error_message"] = None
        
        # Log activity
        activity_log_store.insert(0, {
            "id": f"act_{int(time.time())}",
            "timestamp": utcnow().isoformat(),
            "activity_type": "BOT_CONTROL",
            "component": "DASHBOARD",
            "description": "Bot started via dashboard",
            "status": "success"
        })
        
        log.info("Bot started via dashboard")
        
        # Broadcast to WebSocket clients
        await broadcast_alert("bot_control", "Bot started", "info")
        
        return {"message": "Bot started successfully", "status": bot_state["status"]}
    
    except Exception as e:
        log.error(f"Failed to start bot: {e}")
        bot_state["status"] = "error"
        bot_state["error_message"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))


@dashboard_app.post("/api/v1/bot/stop")
async def stop_bot(request: Request):
    """
    Stop the trading bot and close all positions.
    """
    await check_rate_limit(request)
    
    if bot_state["status"] == "stopped":
        raise HTTPException(status_code=400, detail="Bot is already stopped")
    
    try:
        # In production, trigger actual bot shutdown and close positions
        bot_state["status"] = "stopped"
        bot_state["last_stopped"] = utcnow().isoformat()
        bot_state["error_message"] = None
        
        # Log activity
        activity_log_store.insert(0, {
            "id": f"act_{int(time.time())}",
            "timestamp": utcnow().isoformat(),
            "activity_type": "BOT_CONTROL",
            "component": "DASHBOARD",
            "description": "Bot stopped via dashboard",
            "status": "success"
        })
        
        log.info("Bot stopped via dashboard")
        
        # Broadcast to WebSocket clients
        await broadcast_alert("bot_control", "Bot stopped", "warning")
        
        return {"message": "Bot stopped successfully", "status": bot_state["status"]}
    
    except Exception as e:
        log.error(f"Failed to stop bot: {e}")
        bot_state["error_message"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))


@dashboard_app.post("/api/v1/bot/pause")
async def pause_bot(request: Request):
    """
    Pause the trading bot (keep positions open, stop new trades).
    """
    await check_rate_limit(request)
    
    if bot_state["status"] != "running":
        raise HTTPException(status_code=400, detail="Bot is not running")
    
    try:
        # In production, pause trading logic
        bot_state["status"] = "paused"
        bot_state["error_message"] = None
        
        # Log activity
        activity_log_store.insert(0, {
            "id": f"act_{int(time.time())}",
            "timestamp": utcnow().isoformat(),
            "activity_type": "BOT_CONTROL",
            "component": "DASHBOARD",
            "description": "Bot paused via dashboard",
            "status": "success"
        })
        
        log.info("Bot paused via dashboard")
        
        # Broadcast to WebSocket clients
        await broadcast_alert("bot_control", "Bot paused", "warning")
        
        return {"message": "Bot paused successfully", "status": bot_state["status"]}
    
    except Exception as e:
        log.error(f"Failed to pause bot: {e}")
        bot_state["error_message"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))


@dashboard_app.post("/api/v1/bot/restart")
async def restart_bot(request: Request):
    """
    Restart the trading bot.
    """
    await check_rate_limit(request)
    
    try:
        # Stop first
        if bot_state["status"] in ["running", "paused"]:
            bot_state["status"] = "stopped"
            bot_state["last_stopped"] = utcnow().isoformat()
            await asyncio.sleep(2)  # Wait for graceful shutdown
        
        # Then start
        bot_state["status"] = "running"
        bot_state["last_started"] = utcnow().isoformat()
        bot_state["uptime_seconds"] = 0
        bot_state["error_message"] = None
        
        # Log activity
        activity_log_store.insert(0, {
            "id": f"act_{int(time.time())}",
            "timestamp": utcnow().isoformat(),
            "activity_type": "BOT_CONTROL",
            "component": "DASHBOARD",
            "description": "Bot restarted via dashboard",
            "status": "success"
        })
        
        log.info("Bot restarted via dashboard")
        
        # Broadcast to WebSocket clients
        await broadcast_alert("bot_control", "Bot restarted", "info")
        
        return {"message": "Bot restarted successfully", "status": bot_state["status"]}
    
    except Exception as e:
        log.error(f"Failed to restart bot: {e}")
        bot_state["status"] = "error"
        bot_state["error_message"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))


@dashboard_app.get("/api/v1/bot/activity")
async def get_activity_log(
    request: Request,
    limit: int = 100,
    activity_type: Optional[str] = None
):
    """
    Get bot activity log.
    """
    await check_rate_limit(request)
    
    # Mock activity logs (in production, query from database)
    if not activity_log_store:
        # Initialize with sample data
        activity_types = [
            ("TRADE_OPENED", "FAST_DECISION", "Opened LONG position on XAUUSD"),
            ("TRADE_CLOSED", "FAST_DECISION", "Closed position on XAUUSD with +2.5% profit"),
            ("MODEL_PREDICTION", "MODEL_INFERENCE", "Generated prediction for EURUSD"),
            ("DATA_COLLECTION", "TICK_COLLECTOR", "Collected 1000 ticks for XAUUSD"),
            ("FEATURE_UPDATE", "FEATURE_PIPELINE", "Updated features for 5 symbols"),
            ("HEALTH_CHECK", "SYSTEM_MONITOR", "All systems healthy"),
        ]
        
        for i in range(20):
            activity_type_data = activity_types[i % len(activity_types)]
            activity_log_store.append({
                "id": f"act_{i}",
                "timestamp": (utcnow() - timedelta(minutes=i * 5)).isoformat(),
                "activity_type": activity_type_data[0],
                "component": activity_type_data[1],
                "description": activity_type_data[2],
                "status": ["success", "running", "failed"][i % 3] if i % 7 == 0 else "success"
            })
    
    activities = activity_log_store[:limit]
    
    # Filter by type if specified
    if activity_type:
        activities = [a for a in activities if a["activity_type"] == activity_type]
    
    return {"activities": activities, "count": len(activities)}


@dashboard_app.get("/api/v1/bot/scheduled-jobs")
async def get_scheduled_jobs(request: Request):
    """
    Get list of scheduled jobs (cron jobs, periodic tasks).
    """
    await check_rate_limit(request)
    
    # Mock scheduled jobs (in production, query from scheduler)
    if not scheduled_jobs_store:
        scheduled_jobs_store.extend([
            {
                "job_id": "job_model_retrain",
                "job_name": "Weekly Model Retraining",
                "job_type": "model_training",
                "schedule": "Every Sunday at 02:00 UTC",
                "last_run": (utcnow() - timedelta(days=2)).isoformat(),
                "next_run": (utcnow() + timedelta(days=5)).isoformat(),
                "status": "active",
                "last_duration_seconds": 1800
            },
            {
                "job_id": "job_data_archive",
                "job_name": "Daily Data Archival",
                "job_type": "data_collection",
                "schedule": "Every day at 00:00 UTC",
                "last_run": (utcnow() - timedelta(hours=8)).isoformat(),
                "next_run": (utcnow() + timedelta(hours=16)).isoformat(),
                "status": "active",
                "last_duration_seconds": 120
            },
            {
                "job_id": "job_portfolio_rebalance",
                "job_name": "Weekly Portfolio Rebalancing",
                "job_type": "rebalancing",
                "schedule": "Every Monday at 09:00 UTC",
                "last_run": (utcnow() - timedelta(days=6)).isoformat(),
                "next_run": (utcnow() + timedelta(days=1)).isoformat(),
                "status": "active",
                "last_duration_seconds": 45
            },
            {
                "job_id": "job_health_check",
                "job_name": "System Health Check",
                "job_type": "health_check",
                "schedule": "Every 5 minutes",
                "last_run": (utcnow() - timedelta(minutes=5)).isoformat(),
                "next_run": (utcnow() + timedelta(minutes=5)).isoformat(),
                "status": "active",
                "last_duration_seconds": 2
            }
        ])
    
    return {"jobs": scheduled_jobs_store, "count": len(scheduled_jobs_store)}


@dashboard_app.post("/api/v1/bot/scheduled-jobs/{job_id}/pause")
async def pause_scheduled_job(job_id: str, request: Request):
    """
    Pause a scheduled job.
    """
    await check_rate_limit(request)
    
    # Find and update job
    for job in scheduled_jobs_store:
        if job["job_id"] == job_id:
            job["status"] = "paused"
            log.info(f"Scheduled job {job_id} paused")
            return {"message": "Job paused successfully"}
    
    raise HTTPException(status_code=404, detail="Job not found")


@dashboard_app.post("/api/v1/bot/scheduled-jobs/{job_id}/resume")
async def resume_scheduled_job(job_id: str, request: Request):
    """
    Resume a paused scheduled job.
    """
    await check_rate_limit(request)
    
    # Find and update job
    for job in scheduled_jobs_store:
        if job["job_id"] == job_id:
            job["status"] = "active"
            log.info(f"Scheduled job {job_id} resumed")
            return {"message": "Job resumed successfully"}
    
    raise HTTPException(status_code=404, detail="Job not found")


@dashboard_app.post("/api/v1/bot/scheduled-jobs/{job_id}/run-now")
async def run_scheduled_job_now(job_id: str, request: Request):
    """
    Trigger a scheduled job to run immediately.
    """
    await check_rate_limit(request)
    
    # Find job
    for job in scheduled_jobs_store:
        if job["job_id"] == job_id:
            # In production, trigger actual job execution
            log.info(f"Scheduled job {job_id} triggered manually")
            
            # Add to async jobs
            async_jobs_store.insert(0, {
                "job_id": f"async_{int(time.time())}",
                "job_type": job["job_type"],
                "status": "running",
                "progress": 0,
                "started_at": utcnow().isoformat()
            })
            
            return {"message": "Job triggered successfully"}
    
    raise HTTPException(status_code=404, detail="Job not found")


@dashboard_app.get("/api/v1/bot/async-jobs")
async def get_async_jobs(request: Request):
    """
    Get list of async/background jobs.
    """
    await check_rate_limit(request)
    
    # Mock async jobs (in production, query from job queue)
    if not async_jobs_store:
        async_jobs_store.extend([
            {
                "job_id": "async_001",
                "job_type": "model_training",
                "status": "running",
                "progress": 65,
                "started_at": (utcnow() - timedelta(minutes=15)).isoformat()
            },
            {
                "job_id": "async_002",
                "job_type": "data_backfill",
                "status": "completed",
                "progress": 100,
                "started_at": (utcnow() - timedelta(hours=2)).isoformat(),
                "completed_at": (utcnow() - timedelta(hours=1)).isoformat()
            }
        ])
    
    return {"jobs": async_jobs_store, "count": len(async_jobs_store)}


@dashboard_app.post("/api/v1/bot/async-jobs/{job_id}/cancel")
async def cancel_async_job(job_id: str, request: Request):
    """
    Cancel a running async job.
    """
    await check_rate_limit(request)
    
    # Find and cancel job
    for job in async_jobs_store:
        if job["job_id"] == job_id:
            if job["status"] in ["running", "pending"]:
                job["status"] = "failed"
                job["error"] = "Cancelled by user"
                job["completed_at"] = utcnow().isoformat()
                log.info(f"Async job {job_id} cancelled")
                return {"message": "Job cancelled successfully"}
            else:
                raise HTTPException(status_code=400, detail="Job is not running")
    
    raise HTTPException(status_code=404, detail="Job not found")


# ═══════════════════════════════════════════════════════
#  REST API ENDPOINTS - DECISION TRACES
# ═══════════════════════════════════════════════════════

from core.decision_tracer import get_trace, get_recent_traces, DecisionType as TraceDecisionType
from dataclasses import asdict


@dashboard_app.get("/api/v1/decisions/traces")
async def get_decision_traces(
    request: Request,
    limit: int = 50,
    decision_type: Optional[str] = None,
    symbol: Optional[str] = None
):
    """
    Get recent decision traces with optional filters.
    """
    await check_rate_limit(request)
    
    # Convert decision_type string to enum if provided
    dt_enum = None
    if decision_type:
        try:
            dt_enum = TraceDecisionType(decision_type)
        except ValueError:
            pass
    
    traces = get_recent_traces(
        limit=limit,
        decision_type=dt_enum,
        symbol=symbol
    )
    
    # Convert to dict for JSON serialization
    traces_dict = [asdict(trace) for trace in traces]
    
    return {"traces": traces_dict, "count": len(traces_dict)}


@dashboard_app.get("/api/v1/decisions/traces/{decision_id}")
async def get_decision_trace_details(decision_id: str, request: Request):
    """
    Get detailed trace for a specific decision.
    """
    await check_rate_limit(request)
    
    trace = get_trace(decision_id)
    
    if not trace:
        raise HTTPException(status_code=404, detail="Decision trace not found")
    
    return asdict(trace)


@dashboard_app.get("/api/v1/agents/logs")
async def get_agent_logs(
    request: Request,
    agent_name: Optional[str] = None,
    limit: int = 100
):
    """
    Get logs from specific agents.
    """
    await check_rate_limit(request)
    
    # Mock agent logs (in production, query from logging system)
    agents = [
        "FastDecisionEngine",
        "MacroAgent",
        "ParallelAnalyzer",
        "AutonomousOrchestrator",
        "MarketContext",
        "OutcomeTracker",
        "CORR",
        "STRATEGY_ADAPTER",
        "WATCHDOG",
    ]
    
    logs = []
    for i in range(min(limit, 50)):
        agent = agents[i % len(agents)] if not agent_name else agent_name
        logs.append({
            "timestamp": (utcnow() - timedelta(minutes=i)).isoformat(),
            "agent_name": agent,
            "log_level": ["INFO", "DEBUG", "WARNING"][i % 3],
            "message": f"Sample log message from {agent}",
            "context": {"sample_key": f"value_{i}"} if i % 5 == 0 else None
        })
    
    return {"logs": logs, "count": len(logs)}


# ═══════════════════════════════════════════════════════
#  REST API ENDPOINTS - BOT CONTROL
# ═══════════════════════════════════════════════════════

@dashboard_app.get("/api/v1/bot/status")
async def get_bot_status(request: Request):
    """
    Get current bot status and statistics.
    """
    await check_rate_limit(request)
    
    status = bot_lifecycle.get_status()
    
    # Update position counts from trade journal
    try:
        open_trades = trade_journal.get_decision_history(
            decision_type=DecisionType.TRADE_OPENED,
            limit=100
        )
        # Count trades that haven't been closed yet
        closed_trades = trade_journal.get_decision_history(
            decision_type=DecisionType.TRADE_CLOSED,
            limit=100
        )
        closed_ids = set(closed_trades['entry_id'].tolist() if not closed_trades.empty else [])
        active_count = len([t for t in open_trades['entry_id'].tolist() if t not in closed_ids]) if not open_trades.empty else 0
        
        bot_lifecycle.update_positions(active=active_count, pending=0)
    except Exception as e:
        log.error(f"Failed to update position counts: {e}")
    
    return status.to_dict()


@dashboard_app.post("/api/v1/bot/start")
async def start_bot(request: Request):
    """
    Start the trading bot.
    """
    await check_rate_limit(request)
    
    try:
        bot_lifecycle.start()
        await broadcast_alert("bot_control", "Trading bot started", "info")
        return {"message": "Bot started successfully", "status": bot_lifecycle.get_status().to_dict()}
    except Exception as e:
        log.error(f"Failed to start bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@dashboard_app.post("/api/v1/bot/stop")
async def stop_bot(request: Request):
    """
    Stop the trading bot.
    """
    await check_rate_limit(request)
    
    try:
        bot_lifecycle.stop()
        await broadcast_alert("bot_control", "Trading bot stopped", "warning")
        return {"message": "Bot stopped successfully", "status": bot_lifecycle.get_status().to_dict()}
    except Exception as e:
        log.error(f"Failed to stop bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@dashboard_app.post("/api/v1/bot/pause")
async def pause_bot(request: Request):
    """
    Pause the trading bot (keep positions open).
    """
    await check_rate_limit(request)
    
    try:
        bot_lifecycle.pause()
        await broadcast_alert("bot_control", "Trading bot paused", "info")
        return {"message": "Bot paused successfully", "status": bot_lifecycle.get_status().to_dict()}
    except Exception as e:
        log.error(f"Failed to pause bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@dashboard_app.post("/api/v1/bot/restart")
async def restart_bot(request: Request):
    """
    Restart the trading bot.
    """
    await check_rate_limit(request)
    
    try:
        bot_lifecycle.restart()
        await broadcast_alert("bot_control", "Trading bot restarted", "info")
        return {"message": "Bot restarted successfully", "status": bot_lifecycle.get_status().to_dict()}
    except Exception as e:
        log.error(f"Failed to restart bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@dashboard_app.get("/api/v1/bot/activity")
async def get_bot_activity(request: Request, limit: int = 100):
    """
    Get bot activity log from system logs with detailed information extraction.
    """
    await check_rate_limit(request)
    
    try:
        import duckdb
        import re
        from pathlib import Path
        
        db_path = Path(__file__).parent.parent / "data" / "system_logs.duckdb"
        
        if not db_path.exists():
            return {"activities": [], "count": 0}
        
        con = duckdb.connect(str(db_path), read_only=True)
        
        # Query logs for bot activities - broader search
        query = """
            SELECT timestamp, level, agent, message 
            FROM system_logs 
            WHERE message LIKE '%TRADE%' 
               OR message LIKE '%position%'
               OR message LIKE '%DECISION%'
               OR message LIKE '%Bot%'
               OR message LIKE '%STARTED%'
               OR message LIKE '%STOPPED%'
               OR message LIKE '%ANALYST%'
               OR message LIKE '%POSMGR%'
               OR message LIKE '%ticket=%'
               OR message LIKE '%Score:%'
            ORDER BY timestamp DESC 
            LIMIT ?
        """
        
        result = con.execute(query, [limit]).fetchall()
        con.close()
        
        activities = []
        for i, row in enumerate(result):
            timestamp = row[0]
            level = row[1]
            agent = row[2]
            msg = row[3]
            
            # Extract detailed information from message
            details = {}
            activity_type = 'system'
            status = 'success'
            description = msg
            
            # Parse trading signals from ANALYST
            if '[ANALYST]' in msg and 'Direction.' in msg:
                activity_type = 'signal'
                
                # Extract direction
                direction_match = re.search(r'Direction\.(BUY|SELL)', msg)
                if direction_match:
                    details['direction'] = direction_match.group(1)
                
                # Extract symbol
                symbol_match = re.search(r'Direction\.[A-Z]+\s+([A-Z]+)', msg)
                if symbol_match:
                    details['symbol'] = symbol_match.group(1)
                
                # Extract score
                score_match = re.search(r'Score:\s*([\d.]+)', msg)
                if score_match:
                    details['score'] = float(score_match.group(1))
                
                # Extract reason (first 150 chars)
                reason_match = re.search(r'Reason:\s*(.+)', msg)
                if reason_match:
                    reason = reason_match.group(1)
                    details['reason'] = reason[:150] + '...' if len(reason) > 150 else reason
                
                # Create readable description
                if details.get('symbol') and details.get('direction'):
                    description = f"Trading Signal: {details['direction']} {details['symbol']}"
                    if details.get('score'):
                        description += f" (Score: {details['score']})"
                
                status = 'success' if details.get('score', 0) >= 7.0 else 'pending'
            
            # Parse position manager activities
            elif '[POSMGR]' in msg:
                activity_type = 'position_management'
                
                # Extract symbol
                symbol_match = re.search(r'([A-Z]{3,6})\s+ticket=', msg)
                if symbol_match:
                    details['symbol'] = symbol_match.group(1)
                
                # Extract ticket
                ticket_match = re.search(r'ticket=(\d+)', msg)
                if ticket_match:
                    details['ticket'] = ticket_match.group(1)
                
                # Determine action
                if 'Discovered untracked position' in msg:
                    details['action'] = 'discovered'
                    description = f"Discovered position: {details.get('symbol', 'Unknown')}"
                elif 'not in live positions' in msg:
                    details['action'] = 'closed_detected'
                    description = f"Position closed: {details.get('symbol', 'Unknown')}"
                elif 'adding to tracker' in msg:
                    details['action'] = 'tracking'
                    description = f"Tracking position: {details.get('symbol', 'Unknown')}"
            
            # Parse bot control messages
            elif any(word in msg.upper() for word in ['STARTED', 'STOPPED', 'PAUSED', 'RESUMED']):
                activity_type = 'bot_control'
                
                if 'STARTED' in msg.upper() or '🚀' in msg:
                    details['action'] = 'started'
                    description = "Bot started"
                    status = 'running'
                elif 'STOPPED' in msg.upper() or '🛑' in msg:
                    details['action'] = 'stopped'
                    description = "Bot stopped"
                    status = 'success'
                elif 'PAUSED' in msg.upper() or '⏸️' in msg:
                    details['action'] = 'paused'
                    description = "Bot paused"
                    status = 'pending'
                elif 'RESUMED' in msg.upper() or '▶️' in msg:
                    details['action'] = 'resumed'
                    description = "Bot resumed"
                    status = 'running'
            
            # Parse config updates
            elif 'Config updated' in msg:
                activity_type = 'configuration'
                description = "Configuration updated"
                
                # Try to extract what was updated
                if 'risk' in msg.lower():
                    details['section'] = 'risk'
                elif 'strategy' in msg.lower():
                    details['section'] = 'strategy'
            
            # Parse scheduled tasks
            elif 'scheduled' in msg.lower():
                activity_type = 'scheduled_task'
                description = msg
                
                # Extract interval
                interval_match = re.search(r'every\s+(\d+[smh])', msg)
                if interval_match:
                    details['interval'] = interval_match.group(1)
            
            # Handle errors
            if level == 'ERROR' or 'ERROR' in msg.upper() or 'FAILED' in msg.upper():
                status = 'failed'
                activity_type = 'error'
            
            activities.append({
                "id": f"activity_{i}_{int(timestamp.timestamp()) if hasattr(timestamp, 'timestamp') else i}",
                "timestamp": timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp),
                "activity_type": activity_type,
                "component": agent,
                "description": description,
                "status": status,
                "details": details if details else None
            })
        
        return {"activities": activities, "count": len(activities)}
    
    except Exception as e:
        log.error(f"Failed to fetch activity log: {e}")
        return {"activities": [], "count": 0}


@dashboard_app.get("/api/v1/bot/scheduled-jobs")
async def get_scheduled_jobs(request: Request):
    """
    Get list of scheduled jobs.
    """
    await check_rate_limit(request)
    
    # Mock scheduled jobs (implement with APScheduler in production)
    jobs = [
        {
            "job_id": "job_model_retrain",
            "job_name": "Model Retraining",
            "job_type": "model_training",
            "schedule": "0 0 * * 0",  # Weekly on Sunday
            "last_run": (utcnow() - timedelta(days=7)).isoformat(),
            "next_run": (utcnow() + timedelta(days=7)).isoformat(),
            "status": "active",
            "last_duration_seconds": 3600
        },
        {
            "job_id": "job_data_collection",
            "job_name": "Market Data Collection",
            "job_type": "data_collection",
            "schedule": "*/5 * * * *",  # Every 5 minutes
            "last_run": (utcnow() - timedelta(minutes=5)).isoformat(),
            "next_run": (utcnow() + timedelta(minutes=5)).isoformat(),
            "status": "active",
            "last_duration_seconds": 30
        },
        {
            "job_id": "job_health_check",
            "job_name": "System Health Check",
            "job_type": "health_check",
            "schedule": "*/1 * * * *",  # Every minute
            "last_run": (utcnow() - timedelta(minutes=1)).isoformat(),
            "next_run": (utcnow() + timedelta(minutes=1)).isoformat(),
            "status": "active",
            "last_duration_seconds": 5
        }
    ]
    
    return {"jobs": jobs, "count": len(jobs)}


@dashboard_app.post("/api/v1/bot/scheduled-jobs/{job_id}/pause")
async def pause_scheduled_job(job_id: str, request: Request):
    """
    Pause a scheduled job.
    """
    await check_rate_limit(request)
    log.info(f"Pausing scheduled job: {job_id}")
    return {"message": f"Job {job_id} paused successfully"}


@dashboard_app.post("/api/v1/bot/scheduled-jobs/{job_id}/resume")
async def resume_scheduled_job(job_id: str, request: Request):
    """
    Resume a scheduled job.
    """
    await check_rate_limit(request)
    log.info(f"Resuming scheduled job: {job_id}")
    return {"message": f"Job {job_id} resumed successfully"}


@dashboard_app.post("/api/v1/bot/scheduled-jobs/{job_id}/run-now")
async def run_scheduled_job_now(job_id: str, request: Request):
    """
    Trigger a scheduled job immediately.
    """
    await check_rate_limit(request)
    log.info(f"Triggering scheduled job: {job_id}")
    return {"message": f"Job {job_id} triggered successfully"}


@dashboard_app.get("/api/v1/bot/async-jobs")
async def get_async_jobs(request: Request):
    """
    Get list of async jobs.
    """
    await check_rate_limit(request)
    
    # Mock async jobs (implement with Celery or similar in production)
    jobs = []
    
    return {"jobs": jobs, "count": len(jobs)}


@dashboard_app.post("/api/v1/bot/async-jobs/{job_id}/cancel")
async def cancel_async_job(job_id: str, request: Request):
    """
    Cancel an async job.
    """
    await check_rate_limit(request)
    log.info(f"Cancelling async job: {job_id}")
    return {"message": f"Job {job_id} cancelled successfully"}


if __name__ == "__main__":
    import uvicorn
    log.info("Starting APEX Dashboard Backend on http://0.0.0.0:8001")
    uvicorn.run(dashboard_app, host="0.0.0.0", port=8001)
