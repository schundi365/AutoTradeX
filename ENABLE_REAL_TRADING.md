# Enable Real Trading - Quick Fix

## Problem
Bot is running in MONITOR MODE, which means it's only simulating trades, not placing real orders.

## Root Cause
The bot was started with the `--monitor` flag, which enables monitor-only mode.

## Solution

### Step 1: Stop the Bot
```powershell
.\stop-apex.ps1
```

### Step 2: Start Bot for Real Trading

**Option A: Use the startup script (recommended)**
```powershell
.\start-apex.ps1
```

**Option B: Start manually**
```powershell
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Start bot WITHOUT --monitor flag
python main.py --autostart --port 8000
```

### Step 3: Verify Real Trading is Enabled

Check the logs for:
```
✅ GOOD: "⚡ ExecutionAgent: Executing X approved signals..."
         "📊 Placing order: Direction.BUY XAUUSD..."

❌ BAD:  "👀 MONITOR MODE: Skipping real order execution..."
         "📊 VIRTUAL EXECUTION: Direction.BUY XAUUSD..."
```

Or check the dashboard:
1. Open http://localhost:8000
2. Go to Bot Control tab
3. Look for "Monitor Mode: OFF" status

## Important Safety Notes

### Before Enabling Real Trading

1. **Verify Broker Connection**
   - Check MT5 is connected
   - Verify account balance
   - Confirm you're on the correct account (demo vs live)

2. **Check Risk Settings**
   - Review `MAX_RISK_PER_TRADE_PCT` in CONFIG tab
   - Verify `MAX_OPEN_TRADES` limit
   - Check `MAX_DAILY_DRAWDOWN_PCT`

3. **Start Small**
   - Consider reducing position sizes initially
   - Monitor first few trades closely
   - Gradually increase risk as confidence builds

### Environment Settings

Your `.env` file shows:
```
APP_ENV=live              # You're in LIVE mode
MT5_SERVER=MetaQuotes-Demo  # But using DEMO server (safe!)
```

This is GOOD - you're in live mode but connected to a demo account, so you can test real order execution without risking real money.

## Command-Line Flags Reference

```powershell
# Monitor mode (simulation only)
python main.py --monitor --autostart

# Real trading (default)
python main.py --autostart

# Paper trading mode
python main.py --mode paper --autostart

# Live trading mode
python main.py --mode live --autostart
```

## Troubleshooting

### Orders Still Not Placing

1. **Check broker connection**
   ```powershell
   # In Python console
   from brokers.base import BrokerFactory
   from core.config import settings
   
   factory = BrokerFactory(settings)
   mt5 = factory.get("MT5")
   print(f"Connected: {mt5.connected}")
   ```

2. **Check execution logs**
   ```powershell
   # Search for execution attempts
   Select-String -Path logs\apex_*.log -Pattern "Placing order|place_order"
   ```

3. **Verify signals are being approved**
   - Signals must pass all 10 risk gates (G1-G10)
   - Check logs for "APPROVED" messages
   - Review rejection reasons if signals are blocked

### Monitor Mode Still Active

If monitor mode is still active after restart:

1. Check if `MONITOR_ONLY=true` is in `.env` file
2. Remove the line or set to `MONITOR_ONLY=false`
3. Restart the bot

## Current Status

Based on your logs:
- ✅ Bot is generating signals
- ✅ Signals are passing risk gates
- ✅ 5 signals approved (XAGUSD, AUDUSD x2, NVDA, USOIL)
- ❌ Orders not placed (monitor mode active)

After restarting without `--monitor` flag, these signals should execute as real orders.
