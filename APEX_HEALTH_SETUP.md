# APEX Health Monitoring - Quick Setup

## The Issue
Your Apex Trader Health section shows blank fields because the database tables need to be created/reset with the correct schema.

## The Fix (3 Commands)

### 1. Reset Tables
```powershell
python scripts/reset_apex_health_tables.py
```
This drops and recreates the tables with correct schema.

### 2. Test Logging
```powershell
python scripts/test_apex_health_logging.py
```
This verifies the tables work correctly.

### 3. Run Bot
```powershell
python main.py
```
Let it run for 5 minutes (one cycle), then check the dashboard.

## What to Expect

After running the bot for one cycle, open http://localhost:8000 → AI & MLOPS tab.

The Apex Trader Health section will show:
- ✅ Status: online
- ✅ Avg Latency: ~150-300ms
- ✅ Calls (24h): number of LLM calls
- ✅ Success Rate: >95%
- ✅ GO/NOGO counts
- ✅ Latency metrics (P50, P95)
- ✅ Model info

## Logs to Watch For

When the bot runs, you should see:
```
[market_analyst] 🤖 LLM Tier 1 (Ollama/apex-trader) ✓
[ORCHESTRATOR] APPROVED BUY XAUUSD — High conviction setup
```

These confirm that:
1. LLM calls are being made
2. Decisions are being logged
3. Data is flowing to the database

## Troubleshooting

### Tables don't exist
```powershell
python scripts/reset_apex_health_tables.py
```

### Test fails
Check that:
- DuckDB file exists: `data/apex.db`
- No other process is locking the database
- Python has write permissions to `data/` folder

### Dashboard still blank after bot runs
1. Check browser console (F12) for errors
2. Test API endpoint: http://localhost:8000/api/ai/apex-health
3. Verify data in database:
```powershell
python scripts/test_apex_health_logging.py
```

## Files Created/Modified

### New Files
- `scripts/reset_apex_health_tables.py` - Resets tables with correct schema
- `scripts/test_apex_health_logging.py` - Tests logging functionality
- `APEX_HEALTH_LOGGING_FIX.md` - Detailed documentation
- `APEX_HEALTH_SETUP.md` - This quick setup guide

### Modified Files
- `scripts/init_apex_health_tables.py` - Fixed schema to match logging code

### Existing Files (Already Implemented)
- `llm/client.py` - Logs all LLM calls to `llm_calls` table
- `agents/graph.py` - Logs bot decisions to `bot_decisions` table
- `api/server.py` - Serves `/api/ai/apex-health` endpoint

## Database Schema

### llm_calls
Logs every LLM call across all 4 tiers:
- timestamp, agent, tier, model
- latency_ms, success, timeout, error

### bot_decisions
Logs every orchestrator decision:
- timestamp, symbol, decision (GO/NOGO)
- confidence, outcome (WIN/LOSS/NULL)

### model_metadata
Tracks model training history:
- model_type, model_name, last_trained
- training_samples, accuracy, notes

## Next Steps

1. Run the 3 commands above
2. Check the dashboard
3. If you see data, you're done! ✅
4. If not, check the troubleshooting section

For detailed information, see `APEX_HEALTH_LOGGING_FIX.md`.
