# APEX Trading Bot - Quick Start Guide

## Prerequisites

1. **MT5 Running**: MetaTrader 5 must be open and logged in
2. **Python Environment**: Virtual environment activated
3. **Environment Variables**: `.env` file configured with MT5 credentials

## Method 1: Using start.ps1 Script (Recommended)

### Start Everything
```powershell
./start.ps1
```

python -m uvicorn api.server:app --reload --port 8000


This starts:
- Trading bot API server on port 8000
- Dashboard at http://localhost:8000
- Bot in STOPPED state (ready to start)

### Access Dashboard
Open browser: **http://localhost:8000**

### Start Trading
Click the **"START BOT"** button in the sidebar

### Stop Everything
```powershell
./stop.ps1
```

## Method 2: Command Line with Auto-Start

### Start Bot Immediately
```powershell
python main.py --mode full --autostart --port 8000
```

This starts:
- API server on port 8000
- Dashboard at http://localhost:8000
- Bot automatically starts trading

### Stop Bot
Press `Ctrl+C` in the terminal

## Method 3: Dashboard Control Only

### 1. Start the Service
```powershell
./start.ps1
```

### 2. Open Dashboard
http://localhost:8000

### 3. Use Dashboard Buttons
- **START BOT**: Starts trading (sidebar or config tab)
- **STOP BOT**: Stops trading (sidebar)
- **RESTART BOT**: Restarts trading (config tab)

## What Happens When Bot Starts

1. **Connects to MT5**: Establishes broker connection
2. **Loads Configuration**: Reads risk settings from `.env` and config
3. **Initializes Agents**: Starts 6 agent pipeline
   - Data Collector
   - Market Analyst
   - Sentiment Agent
   - Calendar Agent
   - Risk Manager
   - Orchestrator
4. **Begins Trading Cycle**: Runs every 5 minutes
   - Analyzes market conditions
   - Generates trading signals
   - Makes GO/NOGO decisions
   - Executes approved trades
   - Manages open positions

## Monitoring the Bot

### Dashboard Tabs

**Overview Tab**
- Bot status (green = running, red = stopped)
- Account balance & equity
- Performance metrics
- Recent trades
- News feed

**Trades Tab**
- Open positions (live from MT5)
- Trade history
- Bot decision history (GO/NOGO with timing)

**Bot Logs Tab**
- Real-time system logs
- Filter by level (INFO/WARNING/ERROR)
- Auto-scroll option

**Analytics Tab**
- Performance charts
- Win rate by asset class
- Strategy breakdown

**Config Tab**
- Risk management settings
- Signal gates
- Save configuration
- Restart bot

## Verify Bot is Running

### Check Dashboard
1. Open http://localhost:8000
2. Look for green dot next to "APEX TRADING BOT"
3. "Active Agents" should show "6 ACTIVE"

### Check Logs
1. Go to "Bot Logs" tab
2. Look for messages like:
   - `🚀 APEX Bot started`
   - `🔄 Bot cycle #1 starting...`
   - `[ORCHESTRATOR] Processing signals...`

### Check Console
If running from command line, you'll see:
```
2026-03-10 12:00:00.000 | INFO | api.server | 🚀 APEX Bot started
2026-03-10 12:00:05.000 | INFO | api.server | 🔄 Bot cycle #1 starting...
```

## Troubleshooting

### Bot Won't Start

**Check MT5 Connection**
```powershell
python -c "from brokers.base import BrokerFactory; from core.config import settings; import asyncio; async def test(): broker = BrokerFactory(settings).get('MT5'); await broker.connect(); print(f'Connected: {broker.connected}'); asyncio.run(test())"
```

**Check .env File**
Verify these are set correctly:
```
MT5_LOGIN=your_login
MT5_PASSWORD=your_password
MT5_SERVER=your_server
MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
```

**Check Port 8000**
Make sure nothing else is using port 8000:
```powershell
netstat -ano | findstr :8000
```

### Dashboard Not Loading

**Clear Browser Cache**
- Press `Ctrl+Shift+Delete`
- Clear cached images and files
- Reload page

**Check Service is Running**
```powershell
# Should show Python process on port 8000
netstat -ano | findstr :8000
```

### No Trades Being Placed

**Check Monitor Mode**
```powershell
# Should show: Monitor Only: False
python -c "from core.config import settings; print(f'Monitor Only: {settings.monitor_only}')"
```

**Check Pending Orders**
1. Go to "Trades" tab
2. Look at "Pending Orders" count
3. Check "Bot Decision History" for rejections

**Check Bot Logs**
Look for:
- `[ORCHESTRATOR] APPROVED` - Signals being approved
- `[EXEC] Executing` - Trades being placed
- `[RISK_MANAGER] REJECTED` - Signals being blocked

## Configuration

### Risk Settings (Config Tab)

**Max Risk Per Trade**: 2% (default)
- Maximum account risk per single trade

**Max Combined Risk**: 6% (default)
- Maximum total risk across all open trades

**Max Daily Drawdown**: 2% (default)
- Stop trading if daily loss exceeds this

**Max Open Trades**: 10 (default)
- Maximum number of simultaneous positions

### Signal Gates (Config Tab)

**Min Signal Score**: 6.5 (default)
- Minimum quality score for signals

**Min Confidence**: 60% (default)
- Minimum confidence level

**Min Risk:Reward**: 1.8:1 (default)
- Minimum risk-to-reward ratio

## Files and Locations

### Scripts
- `start.ps1` - Start service
- `stop.ps1` - Stop service
- `main.py` - Main bot entry point

### Configuration
- `.env` - Environment variables (MT5 credentials, API keys)
- `core/config.py` - Settings class

### Dashboard
- `frontend/trading-bot-dashboard.html` - Main dashboard
- `frontend/apex-api-client.js` - API client

### Data
- `data/market_data.duckdb` - Main database (decisions, training data)
- `data/system_logs.duckdb` - System logs
- `data/trades.db` - Trade history

### Logs
- `logs/apex_bot_YYYY-MM-DD.log` - Daily log files

## Quick Reference

### Start Bot
```powershell
./start.ps1
# Then click "START BOT" in dashboard
```

### Stop Bot
```powershell
./stop.ps1
# Or click "STOP BOT" in dashboard
```

### Restart Bot
```powershell
# In dashboard: Config tab → "⚡ RESTART BOT" button
```

### View Logs
```powershell
# Real-time
Get-Content logs/apex_bot_$(Get-Date -Format 'yyyy-MM-dd').log -Wait -Tail 50

# Or use dashboard: Bot Logs tab
```

### Check Status
```powershell
curl http://localhost:8000/api/status
```

## Support

### Check Documentation
- `OLD_DASHBOARD_COMPLETE_FIX.md` - Dashboard features
- `PENDING_ORDERS_FIX.md` - Trading issues
- `DECISION_TIMING_FIX.md` - Decision history
- `BACKEND_ROUTING_CLARIFICATION.md` - API endpoints

### Common Issues
1. **Port already in use**: Stop other services on port 8000
2. **MT5 not connected**: Make sure MT5 is running and logged in
3. **No trades**: Check risk settings and signal gates
4. **Dashboard blank**: Clear browser cache and reload

## Summary

**Simplest way to start:**
1. Open MT5 and log in
2. Run `./start.ps1`
3. Open http://localhost:8000
4. Click "START BOT" button
5. Monitor in "Trades" and "Bot Logs" tabs

That's it! The bot will start analyzing markets and placing trades automatically.
