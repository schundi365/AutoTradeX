# Apex Trader Health & Performance Monitoring

## Overview
Added comprehensive health and performance monitoring for the Apex Trader (Ollama) model in the AI & MLOPS tab. This helps track model performance, identify degradation, and determine when retraining is needed.

## Features Added

### 1. Health Status Dashboard
Located at the top of the AI & MLOPS tab, showing:

#### Main Metrics (4 KPI Cards)
- **Model Status**: 🟢 ONLINE / 🔴 OFFLINE indicator
- **Avg Latency**: Average response time in milliseconds
- **Total Calls (24h)**: Number of LLM calls in the last 24 hours
- **Success Rate**: Percentage of successful responses

#### Decision Quality Metrics
- **GO Decisions**: Count of approved trade signals
- **NOGO Decisions**: Count of rejected trade signals
- **GO Win Rate**: Win percentage of executed GO decisions (key metric for retraining)
- **Avg Confidence**: Average confidence score of decisions

#### Response Quality Metrics
- **P50 Latency**: Median response time (50th percentile)
- **P95 Latency**: 95th percentile response time (outlier detection)
- **Timeouts**: Number of timeout errors
- **Errors**: Number of failed requests

### 2. Retrain Recommendation Alert
Automatically shows when retraining is recommended based on:
- GO win rate drops below 65% threshold
- Latency increases significantly (P95 > 500ms)
- Error rate exceeds 5%
- Model age exceeds 14 days with significant market regime changes

The alert displays:
- ⚠️ Warning banner with amber background
- Specific reason for recommendation
- Quick "START RETRAIN" button linking to training pipeline

### 3. Latency Trend Chart
7-day performance visualization showing:
- **Avg Latency** (blue line, filled): Average response time trend
- **P95 Latency** (amber dashed line): Outlier detection trend
- Interactive Chart.js visualization with tooltips
- Helps identify performance degradation over time

### 4. Model Information
Displays:
- **Model Name**: e.g., "apex-trader"
- **Last Trained**: Date of last training run
- **Training Samples**: Number of examples used in last training

## API Endpoint

### GET `/api/ai/apex-health`

Returns comprehensive health metrics:

```json
{
  "status": "online",
  "avg_latency": 185.5,
  "calls_24h": 523,
  "success_rate": 0.97,
  "go_count": 182,
  "nogo_count": 341,
  "go_winrate": 0.68,
  "avg_confidence": 0.78,
  "p50_latency": 165.2,
  "p95_latency": 312.8,
  "timeouts": 2,
  "errors": 1,
  "model_name": "apex-trader",
  "last_trained": "2026-03-01T10:30:00Z",
  "training_samples": 1247,
  "needs_retrain": false,
  "retrain_reason": null,
  "latency_trend": [
    {
      "timestamp": "2026-02-28T00:00:00Z",
      "avg_latency": 175.3,
      "p95_latency": 298.5
    },
    // ... 7 days of data
  ]
}
```

## Backend Implementation Needed

To make this fully functional, add the endpoint in `api/server.py`:

```python
@app.get("/api/ai/apex-health")
async def get_apex_health():
    """
    Returns Apex Trader (Ollama) health and performance metrics.
    Tracks latency, decision quality, and determines if retraining is needed.
    """
    from memory.duckdb_store import DuckDBStore
    from datetime import datetime, timedelta
    
    store = DuckDBStore(settings.training.duckdb_path)
    await store.start()
    
    # Get metrics from last 24 hours
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    
    # Query LLM call logs
    llm_calls = await store.query("""
        SELECT 
            COUNT(*) as total_calls,
            AVG(latency_ms) as avg_latency,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms) as p50_latency,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95_latency,
            SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
            SUM(CASE WHEN timeout = 1 THEN 1 ELSE 0 END) as timeouts,
            SUM(CASE WHEN error = 1 THEN 1 ELSE 0 END) as errors
        FROM llm_calls
        WHERE timestamp >= ? AND agent = 'orchestrator'
    """, [day_ago])
    
    # Query decision outcomes
    decisions = await store.query("""
        SELECT 
            decision,
            COUNT(*) as count,
            AVG(confidence) as avg_confidence,
            SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins
        FROM bot_decisions
        WHERE timestamp >= ? AND decision IN ('GO', 'NOGO')
        GROUP BY decision
    """, [day_ago])
    
    # Calculate metrics
    go_stats = next((d for d in decisions if d['decision'] == 'GO'), None)
    nogo_stats = next((d for d in decisions if d['decision'] == 'NOGO'), None)
    
    go_count = go_stats['count'] if go_stats else 0
    go_wins = go_stats['wins'] if go_stats else 0
    go_winrate = go_wins / go_count if go_count > 0 else 0
    
    # Get 7-day latency trend
    latency_trend = await store.query("""
        SELECT 
            DATE(timestamp) as date,
            AVG(latency_ms) as avg_latency,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95_latency
        FROM llm_calls
        WHERE timestamp >= ? AND agent = 'orchestrator'
        GROUP BY DATE(timestamp)
        ORDER BY date
    """, [week_ago])
    
    # Get model info
    model_info = await store.query("""
        SELECT model_name, last_trained, training_samples
        FROM model_metadata
        WHERE model_type = 'ollama'
        ORDER BY last_trained DESC
        LIMIT 1
    """)
    
    # Determine if retraining is needed
    needs_retrain = False
    retrain_reason = None
    
    if go_winrate < 0.65:
        needs_retrain = True
        retrain_reason = f"GO win rate dropped to {go_winrate*100:.1f}% (threshold: 65%)"
    elif llm_calls[0]['p95_latency'] > 500:
        needs_retrain = True
        retrain_reason = f"P95 latency increased to {llm_calls[0]['p95_latency']:.0f}ms (threshold: 500ms)"
    elif llm_calls[0]['errors'] / llm_calls[0]['total_calls'] > 0.05:
        needs_retrain = True
        retrain_reason = "Error rate exceeds 5%"
    
    await store.stop()
    
    return {
        "status": "online" if llm_calls[0]['total_calls'] > 0 else "offline",
        "avg_latency": llm_calls[0]['avg_latency'],
        "calls_24h": llm_calls[0]['total_calls'],
        "success_rate": llm_calls[0]['successes'] / llm_calls[0]['total_calls'],
        "go_count": go_count,
        "nogo_count": nogo_stats['count'] if nogo_stats else 0,
        "go_winrate": go_winrate,
        "avg_confidence": go_stats['avg_confidence'] if go_stats else 0,
        "p50_latency": llm_calls[0]['p50_latency'],
        "p95_latency": llm_calls[0]['p95_latency'],
        "timeouts": llm_calls[0]['timeouts'],
        "errors": llm_calls[0]['errors'],
        "model_name": model_info[0]['model_name'] if model_info else "apex-trader",
        "last_trained": model_info[0]['last_trained'] if model_info else None,
        "training_samples": model_info[0]['training_samples'] if model_info else 0,
        "needs_retrain": needs_retrain,
        "retrain_reason": retrain_reason,
        "latency_trend": [
            {
                "timestamp": row['date'].isoformat(),
                "avg_latency": row['avg_latency'],
                "p95_latency": row['p95_latency']
            }
            for row in latency_trend
        ]
    }
```

## Database Schema Needed

Add these tables to DuckDB for tracking:

```sql
-- LLM call logs
CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY,
    timestamp TIMESTAMP,
    agent VARCHAR,
    model VARCHAR,
    latency_ms FLOAT,
    success BOOLEAN,
    timeout BOOLEAN,
    error BOOLEAN,
    error_message VARCHAR
);

-- Bot decision outcomes
CREATE TABLE IF NOT EXISTS bot_decisions (
    id INTEGER PRIMARY KEY,
    timestamp TIMESTAMP,
    symbol VARCHAR,
    decision VARCHAR,  -- 'GO' or 'NOGO'
    confidence FLOAT,
    outcome VARCHAR,   -- 'WIN', 'LOSS', 'PENDING', NULL
    pnl FLOAT
);

-- Model metadata
CREATE TABLE IF NOT EXISTS model_metadata (
    id INTEGER PRIMARY KEY,
    model_type VARCHAR,
    model_name VARCHAR,
    last_trained TIMESTAMP,
    training_samples INTEGER,
    accuracy FLOAT,
    notes VARCHAR
);
```

## Logging Integration

Update `llm/client.py` to log metrics:

```python
async def call_llm(...):
    start_time = time.time()
    success = False
    timeout = False
    error = False
    error_msg = None
    
    try:
        # ... existing LLM call logic ...
        success = True
        return result
    except asyncio.TimeoutError:
        timeout = True
        raise
    except Exception as e:
        error = True
        error_msg = str(e)
        raise
    finally:
        latency_ms = (time.time() - start_time) * 1000
        
        # Log to DuckDB
        store = DuckDBStore(settings.training.duckdb_path)
        await store.start()
        await store.execute("""
            INSERT INTO llm_calls (timestamp, agent, model, latency_ms, success, timeout, error, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [datetime.utcnow(), agent, "ollama", latency_ms, success, timeout, error, error_msg])
        await store.stop()
```

## Usage

1. **Open AI & MLOPS Tab**: Click "AI & MLOPS" in the navigation
2. **View Health Metrics**: Automatically loads on tab open
3. **Refresh Data**: Click "↻ REFRESH" button to update metrics
4. **Monitor Trends**: Check the 7-day latency chart for performance degradation
5. **Retrain When Needed**: If alert shows, click "START RETRAIN" to begin retraining pipeline

## Key Metrics to Watch

### Critical (Retrain Triggers)
- **GO Win Rate < 65%**: Model decisions are underperforming
- **P95 Latency > 500ms**: Response times degrading
- **Error Rate > 5%**: Model stability issues

### Warning Signs
- **Latency Trend Increasing**: Check chart for upward slope
- **Timeout Count > 10/day**: Model may be overloaded
- **Success Rate < 95%**: Infrastructure issues

### Healthy Indicators
- **GO Win Rate > 70%**: Model performing well
- **Avg Latency < 200ms**: Fast responses
- **Success Rate > 98%**: Stable operation

## Benefits

1. **Proactive Monitoring**: Catch performance issues before they impact trading
2. **Data-Driven Retraining**: Know exactly when and why to retrain
3. **Performance Trends**: Visualize model health over time
4. **Quick Diagnostics**: Identify latency, timeout, or error issues immediately
5. **Decision Quality Tracking**: Monitor if model decisions are profitable

## Files Modified
- `frontend/trading-bot-dashboard.html` - Added health monitoring UI and JavaScript
- `frontend/apex-api-client.js` - Added API endpoint and mock data generator

## Files to Create
- Backend endpoint in `api/server.py`
- Database schema updates in `memory/duckdb_store.py`
- Logging integration in `llm/client.py`

## Status
✅ Frontend UI complete with mock data
⏳ Backend API endpoint needed
⏳ Database schema updates needed
⏳ Logging integration needed
