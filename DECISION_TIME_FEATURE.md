# Bot Decision History - Decision Time Feature

## What Was Added

Added a "Decision Time" column to the Bot Decision History table showing how long each orchestrator decision took in seconds.

## Changes Made

### 1. Database Schema
Added `decision_time_ms` column to `bot_decisions` table:
```sql
CREATE TABLE bot_decisions (
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    symbol VARCHAR,
    decision VARCHAR,
    confidence FLOAT,
    outcome VARCHAR,
    decision_time_ms INTEGER  -- NEW: Time taken to make decision in milliseconds
)
```

### 2. Backend Logging (`agents/graph.py`)
- Added timing capture in `orchestrator_node()`:
  - Records start time before LLM evaluation
  - Calculates elapsed time after decision
  - Logs `decision_time_ms` to database

```python
# Track decision timing
decision_start_time = time.time()

# ... LLM decision logic ...

# Log with timing
decision_time_ms = int((time.time() - decision_start_time) * 1000)
await store.execute_write("""
    INSERT INTO bot_decisions 
    (timestamp, symbol, decision, confidence, outcome, decision_time_ms)
    VALUES (?, ?, ?, ?, ?, ?)
""", [timestamp, symbol, decision, confidence, outcome, decision_time_ms])
```

### 3. API Endpoint (`api/server.py`)
Updated `/api/decisions` endpoint to:
- Query `decision_time_ms` from database
- Format as human-readable string (e.g., "0.25s", "1.50s")
- Return in API response

```python
decisions.append({
    "timestamp": timestamp.isoformat(),
    "symbol": symbol,
    "decision": decision,
    "confidence": confidence,
    "outcome": outcome,
    "decision_time_ms": decision_time_ms,
    "decision_time_display": f"{decision_time_ms / 1000:.2f}s"
})
```

### 4. Dashboard UI (`frontend/trading-bot-dashboard.html`)
Updated table structure:
- Removed verbose columns (Agent, Signal Score, Indicators, Reasoning)
- Added clean columns: Timestamp, Symbol, Decision, Confidence, Decision Time, Outcome
- Simplified for better readability

### 5. JavaScript Rendering (`frontend/apex-api-client.js`)
Updated `loadDecisionHistory()` to:
- Display decision time with color coding:
  - **Green (fast)**: < 500ms
  - **Amber (medium)**: 500ms - 1000ms
  - **Red (slow)**: > 1000ms
- Show confidence as percentage
- Display GO/NOGO decisions clearly

### 6. CSS Styling (`frontend/trading-bot-dashboard.html`)
Added styles for time badges:
```css
.time-badge.fast { color: green; }
.time-badge.medium { color: amber; }
.time-badge.slow { color: red; }
```

## How It Works

1. **Decision Starts**: Orchestrator begins evaluating signals
2. **Timer Starts**: `decision_start_time = time.time()`
3. **LLM Evaluation**: Calls LLM to make GO/NOGO decision
4. **Timer Stops**: Calculates `decision_time_ms = (time.time() - start) * 1000`
5. **Database Log**: Stores decision with timing
6. **API Response**: Returns formatted time string
7. **Dashboard Display**: Shows color-coded time badge

## Example Output

### Dashboard Table
```
Timestamp           Symbol   Decision   Confidence  Decision Time  Outcome
2024-01-15 14:30:15 XAUUSD   APPROVED   85%        0.25s          Pending
2024-01-15 14:25:10 BTCUSD   REJECTED   45%        0.18s          --
2024-01-15 14:20:05 EURUSD   APPROVED   92%        0.32s          WIN
```

### Color Coding
- **0.25s** (green) - Fast decision
- **0.75s** (amber) - Medium decision
- **1.50s** (red) - Slow decision

## Benefits

1. **Performance Monitoring**: Track how long decisions take
2. **Bottleneck Detection**: Identify slow LLM calls
3. **Optimization**: See impact of model changes on speed
4. **Debugging**: Correlate slow decisions with errors
5. **User Experience**: Transparency on decision latency

## Migration Steps

If you already have data in `bot_decisions` table:

### Option 1: Reset Tables (Recommended)
```powershell
python scripts/reset_apex_health_tables.py
```
This drops and recreates all tables with correct schema.

### Option 2: Add Column Manually
```sql
ALTER TABLE bot_decisions ADD COLUMN decision_time_ms INTEGER;
```

## Files Modified

1. `agents/graph.py` - Added timing capture in orchestrator_node
2. `api/server.py` - Updated /api/decisions endpoint
3. `frontend/trading-bot-dashboard.html` - Updated table structure and CSS
4. `frontend/apex-api-client.js` - Updated rendering logic
5. `scripts/init_apex_health_tables.py` - Added decision_time_ms column
6. `scripts/reset_apex_health_tables.py` - Added decision_time_ms column
7. `scripts/test_apex_health_logging.py` - Updated test to include timing

## Testing

1. Reset tables:
```powershell
python scripts/reset_apex_health_tables.py
```

2. Test logging:
```powershell
python scripts/test_apex_health_logging.py
```

3. Run bot:
```powershell
python main.py
```

4. Check dashboard:
- Open http://localhost:8000
- Navigate to "Bot Decision History" section
- Verify "Decision Time" column shows values
- Verify color coding (green/amber/red)

## Expected Results

After bot runs for one cycle:
- Decision Time column populated with values like "0.25s", "0.50s"
- Fast decisions (<500ms) show in green
- Medium decisions (500-1000ms) show in amber
- Slow decisions (>1000ms) show in red
- Confidence shows as percentage (e.g., "85%")
- Outcome shows WIN/LOSS/Pending

## Performance Impact

- **Minimal**: Only adds one `time.time()` call per decision
- **Storage**: Adds 4 bytes per decision (INTEGER column)
- **Query**: No performance impact (indexed by timestamp)

## Future Enhancements

Potential additions:
1. Average decision time metric in Apex Health
2. Decision time trend chart
3. Alert if decision time exceeds threshold
4. Breakdown by LLM tier (Ollama vs Groq vs DeepSeek)
5. Correlation between decision time and accuracy
