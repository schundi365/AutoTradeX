# Real Trading Bot Setup - COMPLETE

## What Was Done

### 1. Bot Lifecycle Integration
- Integrated `core/bot_lifecycle.py` with `api/server.py`
- Bot control endpoints now sync with lifecycle manager
- Dashboard backend can query real bot status

### 2. Startup Scripts Created
- `start-trading-bot.ps1` - Starts both trading bot (8000) and dashboard backend (8001)
- `stop-trading-bot.ps1` - Stops all services cleanly
- `test_bot_startup.py` - Validates configuration before starting

### 3. Documentation
- `TRADING_BOT_STARTUP.md` - Complete startup guide
- Explains architecture, configuration, monitoring

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   APEX Trading System                    │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────────┐      ┌──────────────────┐        │
│  │  Trading Bot     │      │  Dashboard       │        │
│  │  + API Server    │      │  Backend         │        │
│  │  Port 8000       │      │  Port 8001       │        │
│  │                  │      │                  │        │
│  │  • Agent Loop    │      │  • REST API      │        │
│  │  • Trade Exec    │      │  • Data Queries  │        │
│  │  • MT5 Broker    │      │  • WebSocket     │        │
│  │  • LLM Calls     │      │                  │        │
│  └────────┬─────────┘      └────────┬─────────┘        │
│           │                         │                   │
│           │  Writes                 │  Reads            │
│           ▼                         ▼                   │
│  ┌─────────────────────────────────────────────┐       │
│  │         DuckDB Databases                     │       │
│  │  • system_logs.duckdb (bot activity)        │       │
│  │  • trade_journal.duckdb (trades, P&L)       │       │
│  │  • market_data.duckdb (OHLCV cache)         │       │
│  └─────────────────────────────────────────────┘       │
│                                                          │
│  ┌──────────────────────────────────────────────┐      │
│  │  Dashboard Frontend (Port 3000)              │      │
│  │  • React + TypeScript                        │      │
│  │  • Vite dev server                           │      │
│  │  • Proxies to port 8001                      │      │
│  └──────────────────────────────────────────────┘      │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## How to Start Trading

### Step 1: Test Configuration

```powershell
python test_bot_startup.py
```

This validates:
- All imports work
- Databases are accessible
- MT5 connection works
- LLM (Ollama) is running

### Step 2: Start Services

```powershell
# Start trading bot + dashboard backend
.\start-trading-bot.ps1

# In a new terminal, start frontend
cd frontend/dashboard
npm run dev
```

### Step 3: Monitor Dashboard

Open http://localhost:3000

- **Bot Control Tab**: Shows bot status, start/stop controls
- **Logs Tab**: Real-time bot activity
- **Trade Journal**: All trades and signals
- **Performance**: P&L metrics and analytics

## What Happens When Bot Starts

### Initialization (First 10 seconds)
1. Loads configuration from `.env`
2. Connects to MT5 broker (demo account)
3. Initializes LangGraph agent pipeline
4. Creates database connections
5. Starts scheduler for position management

### First Cycle (5 minutes)
1. **Data Collector**: Fetches OHLCV for all symbols (XAUUSD, EURUSD, etc.)
2. **Market Analyst**: Calculates RSI, MACD, Bollinger Bands
3. **Sentiment Agent**: Analyzes recent news sentiment
4. **Calendar Agent**: Checks economic events
5. **Macro Agent**: Fetches VIX, DXY, yields
6. **Risk Manager**: Checks position limits, correlation
7. **Orchestrator**: LLM makes trading decision
8. **Execution Agent**: Places trade via MT5 (if signal generated)

### Continuous Operation
- Bot cycle repeats every 5 minutes
- Position management runs every 15 seconds (trailing stops, SL/TP)
- All decisions logged to `system_logs.duckdb`
- All trades logged to `trade_journal.duckdb`

## Current Configuration

From `.env`:
- **APP_ENV**: `live` (real trading mode)
- **MT5_LOGIN**: 102168389 (demo account - SAFE)
- **MT5_SERVER**: MetaQuotes-Demo
- **LLM_PRIMARY**: `local` (Ollama)
- **OLLAMA_MODEL**: `apex-trader`

## Safety Notes

✅ **Currently Safe**:
- Using MT5 demo account (no real money)
- Can test all functionality without risk

⚠️ **Before Going Live**:
1. Change `APP_ENV=paper` for paper trading first
2. Test for at least 1 week with paper trading
3. Review all trades in dashboard
4. Adjust risk settings if needed
5. Only then switch to live account

## Monitoring Commands

```powershell
# Check if bot is running
Get-Process python | Where-Object {$_.MainWindowTitle -like "*main.py*"}

# Check ports
Get-NetTCPConnection -LocalPort 8000,8001

# View real-time logs
tail -f logs/apex_bot.log

# API health check
curl http://localhost:8000/api/v1/status
curl http://localhost:8001/api/v1/bot/status
```

## Troubleshooting

### Bot Not Starting
- Check MT5 is installed and running
- Verify `.env` credentials
- Ensure port 8000 is free
- Check console for errors

### Dashboard Shows Empty Data
- Wait for first bot cycle (5 minutes)
- Verify trading bot is running (not just dashboard)
- Check database files exist in `data/` folder

### No Trades Executed
- Check `APP_ENV` setting
- Verify MT5 connection successful
- Review logs for decision reasoning
- Check risk manager isn't blocking (correlation, limits)

## Next Steps

1. ✅ Run `python test_bot_startup.py`
2. ✅ Start bot with `.\start-trading-bot.ps1`
3. ✅ Start frontend with `cd frontend/dashboard && npm run dev`
4. ⏳ Wait 5 minutes for first cycle
5. ⏳ Check dashboard for bot activity
6. ⏳ Review logs and trades
7. ⏳ Monitor for 1 hour to ensure stability

## Files Created

- `start-trading-bot.ps1` - Unified startup script
- `stop-trading-bot.ps1` - Clean shutdown script
- `test_bot_startup.py` - Configuration validator
- `TRADING_BOT_STARTUP.md` - Detailed startup guide
- `REAL_TRADING_SETUP_COMPLETE.md` - This file

## Integration Complete

The trading bot is now fully integrated with the dashboard:
- Bot writes to databases → Dashboard reads from databases
- Bot lifecycle manager syncs state
- All tabs should show real data after first cycle
- Logs are accurate and show actual bot activity

You're ready to start real trading! 🚀
