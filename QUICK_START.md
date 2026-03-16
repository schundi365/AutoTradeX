# APEX Trading Bot - Quick Start

## 🚀 Start Everything

```powershell
# 1. Test configuration (optional but recommended)
python test_bot_startup.py

# 2. Start trading bot + dashboard backend
.\start-trading-bot.ps1

# 3. In a NEW terminal, start frontend
cd frontend/dashboard
npm run dev

# 4. Open browser
# http://localhost:3000
```

## 🛑 Stop Everything

```powershell
.\stop-trading-bot.ps1
```

## 📊 What You'll See

### First 5 Minutes
- Dashboard shows "STOPPED" or "STARTING"
- Logs tab will be empty or show initialization
- Wait for first bot cycle to complete

### After First Cycle
- **Bot Control**: Status changes to "RUNNING"
- **Logs**: Shows data collection, analysis, decisions
- **Trade Journal**: Shows any signals or trades
- **Performance**: Shows P&L metrics

## ⚙️ Current Setup

- **Mode**: Live (demo account - safe)
- **Broker**: MT5 Demo (MetaQuotes)
- **Cycle**: Every 5 minutes
- **Assets**: XAUUSD, EURUSD, GBPUSD, USDJPY, BTCUSD

## 🔍 Quick Checks

```powershell
# Is bot running?
curl http://localhost:8000/api/v1/status

# Dashboard backend OK?
curl http://localhost:8001/api/v1/bot/status

# Check processes
Get-Process python
```

## 📝 Important Notes

1. First cycle takes 5 minutes - be patient!
2. Demo account = no real money at risk
3. All decisions are logged to databases
4. Dashboard updates when you refresh
5. WebSocket "disconnected" is normal (REST API works fine)

## 🆘 Problems?

See `TRADING_BOT_STARTUP.md` for detailed troubleshooting.

## 📚 More Info

- `TRADING_BOT_STARTUP.md` - Complete guide
- `REAL_TRADING_SETUP_COMPLETE.md` - Architecture details
- `test_bot_startup.py` - Configuration validator
