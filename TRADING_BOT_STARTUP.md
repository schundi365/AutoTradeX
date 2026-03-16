# APEX Trading Bot - Complete Startup Guide

## Overview

The APEX trading system consists of THREE separate services:

1. **Trading Bot + API** (port 8000) - Executes trades, runs agent pipeline
2. **Dashboard Backend** (port 8001) - Serves dashboard data from databases
3. **Dashboard Frontend** (port 3000) - React UI for monitoring

## Quick Start

### Option 1: Automated Startup (Recommended)

```powershell
# Start trading bot + dashboard backend
.\start-trading-bot.ps1

# In a separate terminal, start the frontend
cd frontend/dashboard
npm run dev
```

### Option 2: Manual Startup

```powershell
# Terminal 1: Trading Bot (port 8000)
.\.venv\Scripts\Activate.ps1
python main.py --mode full --autostart --port 8000

# Terminal 2: Dashboard Backend (port 8001)
.\.venv\Scripts\Activate.ps1
python api/dashboard_backend.py

# Terminal 3: Dashboard Frontend (port 3000)
cd frontend/dashboard
npm run dev
```

## Configuration

### Current Settings (.env)

- **APP_ENV**: `live` (real trading mode)
- **MT5_LOGIN**: 102168389 (demo account)
- **MT5_SERVER**: MetaQuotes-Demo
- **LLM_PRIMARY**: `local` (using Ollama)
- **OLLAMA_MODEL**: `apex-trader`

### Trading Modes

Edit `APP_ENV` in `.env`:

- `development` - Mock data, no real trades
- `paper` - Paper trading with real market data
- `live` - Real trading (use with caution!)

## What Happens When Bot Starts

1. **Initialization**
   - Connects to MT5 broker
   - Loads configuration from `.env`
   - Initializes agent pipeline (LangGraph)
   - Sets up database connections

2. **Bot Loop** (every 5 minutes)
   - Data Collector: Fetches market data (OHLCV, quotes)
   - Market Analyst: Technical analysis (RSI, MACD, Bollinger Bands)
   - Sentiment Agent: News sentiment analysis
   - Calendar Agent: Economic events impact
   - Macro Agent: Macro indicators (VIX, DXY, yields)
   - Risk Manager: Position sizing, correlation checks
   - Orchestrator: LLM decision making
   - Execution Agent: Places trades via MT5

3. **Position Management** (every 15 seconds)
   - Updates trailing stops
   - Checks stop loss / take profit
   - Syncs with broker state

4. **Logging**
   - All decisions → `data/system_logs.duckdb`
   - All trades → `data/trade_journal.duckdb`
   - Performance metrics → calculated on-demand

## Dashboard Integration

The dashboard reads from:

- `data/system_logs.duckdb` - Bot activity, signals, errors
- `data/trade_journal.duckdb` - Trade history, P&L
- `data/market_data.duckdb` - Market data cache

The trading bot writes to these databases automatically.

## Monitoring

### Check if Bot is Running

```powershell
# Check processes
Get-Process python | Where-Object {$_.MainWindowTitle -like "*main.py*"}

# Check ports
Get-NetTCPConnection -LocalPort 8000,8001
```

### View Logs

```powershell
# Real-time logs from bot
tail -f logs/apex_bot.log

# Or check dashboard Logs tab
```

### API Health Check

```powershell
# Trading bot API
curl http://localhost:8000/api/v1/status

# Dashboard backend
curl http://localhost:8001/api/v1/bot/status
```

## Stopping the Bot

```powershell
# Stop all services
.\stop-trading-bot.ps1

# Or manually
# Press Ctrl+C in each terminal
```

## Troubleshooting

### Bot Not Starting

1. Check MT5 is installed and running
2. Verify `.env` credentials are correct
3. Check if port 8000 is already in use
4. Look for errors in console output

### Dashboard Shows Empty Data

1. Ensure trading bot is running (not just dashboard backend)
2. Wait for first bot cycle to complete (5 minutes)
3. Check database files exist in `data/` folder
4. Verify dashboard backend is connected to correct databases

### No Trades Being Executed

1. Check `APP_ENV` setting (development mode doesn't trade)
2. Verify MT5 connection is successful
3. Check risk manager isn't blocking trades (correlation, exposure limits)
4. Review logs for decision reasoning

### WebSocket Disconnected

This is normal! The dashboard works fine with REST API only. WebSocket is optional for real-time updates.

## Safety Features

- **Monitor Mode**: Add `--monitor` flag to prevent any trades
- **Paper Trading**: Set `APP_ENV=paper` for simulation
- **Risk Limits**: Configured in `core/config.py`
  - Max position size: 2% of account per trade
  - Max total exposure: 10% of account
  - Correlation checks prevent overexposure

## Next Steps

1. Start the bot with `.\start-trading-bot.ps1`
2. Open dashboard at http://localhost:3000
3. Monitor first cycle (5 minutes)
4. Check Logs tab for bot activity
5. Review Trade Journal for any signals/trades
6. Adjust risk settings in Config tab if needed

## Important Notes

- First cycle takes 5 minutes to complete
- Bot logs every decision to database
- Dashboard updates every time you refresh or when data changes
- MT5 demo account is safe for testing
- Always test with paper trading before going live!
