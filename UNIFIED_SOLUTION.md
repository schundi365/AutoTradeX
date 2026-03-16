# APEX Trading System - Unified Solution

## ✅ COMPLETE - All Services Merged into ONE

Everything now runs on **port 8000** - trading bot + dashboard API + WebSocket.

## Start Everything

```powershell
.\start.ps1
```

This starts ONE service that includes:
- Trading bot (agent pipeline, MT5 connection, trade execution)
- Dashboard API (all `/api/v1/*` endpoints)
- WebSocket for real-time updates

## Start Frontend (Separate Terminal)

```powershell
cd frontend/dashboard
npm run dev
```

Opens at http://localhost:3000

## Stop Everything

```powershell
.\stop.ps1
```

## What Changed

### Before (Confusing)
- Port 8000: Trading bot
- Port 8001: Dashboard backend
- Two separate processes
- Dashboard buttons didn't control real bot
- Had to start/stop multiple services

### After (Unified)
- Port 8000: Everything
- ONE process
- Dashboard buttons control real bot via `bot_manager`
- ONE command to start/stop

## How It Works

1. **api/server.py** - Main FastAPI app on port 8000
2. **api/dashboard_routes.py** - Dashboard routes added to main app
3. **core/bot_lifecycle.py** - Singleton that tracks bot state
4. **Dashboard buttons** → Call `/api/v1/bot/start|stop|restart` → Control `bot_manager` → Actually starts/stops bot loop

## Bot Control Flow

```
Dashboard UI
    ↓
POST /api/v1/bot/start
    ↓
bot_manager.start()
    ↓
_bot_running = True
    ↓
Bot loop starts running
```

## Endpoints

All on port 8000:

### Trading Bot API (Original)
- `/api/status` - Bot health
- `/api/trades/open` - Open positions
- `/api/analytics` - Performance
- `/api/bot/start` - Start bot (old endpoint)

### Dashboard API (New, `/api/v1/` prefix)
- `/api/v1/logs` - System logs
- `/api/v1/bot/status` - Bot status
- `/api/v1/bot/start` - Start bot
- `/api/v1/bot/stop` - Stop bot
- `/api/v1/bot/restart` - Restart bot
- `/api/v1/bot/activity` - Activity log
- `/ws/dashboard` - WebSocket

## Files Modified

1. **api/server.py** - Added `app.include_router(dashboard_router)`
2. **api/dashboard_routes.py** - NEW - Dashboard-specific routes
3. **frontend/dashboard/vite.config.ts** - Changed proxy from 8001 → 8000
4. **frontend/dashboard/src/**/*.tsx** - Changed WebSocket URLs from 8001 → 8000
5. **start.ps1** - NEW - Simple unified startup
6. **stop.ps1** - NEW - Simple stop script

## Testing

```powershell
# Start the bot
.\start.ps1

# In another terminal, start frontend
cd frontend/dashboard
npm run dev

# Open http://localhost:3000
# Click "Start Bot" in dashboard
# Watch logs appear in real-time
# Click "Stop Bot" to stop
```

## Benefits

✅ ONE service to manage
✅ ONE port to remember (8000)
✅ Dashboard buttons actually work
✅ Simpler architecture
✅ Easier to deploy
✅ Less confusion

## Migration from Old Setup

If you have old processes running:

```powershell
# Stop old services
Get-NetTCPConnection -LocalPort 8000,8001 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }

# Start new unified service
.\start.ps1
```

## Summary

You now have a **truly unified solution** where:
- Everything runs in ONE process
- Dashboard buttons control the real bot
- ONE command starts everything
- No more confusion about multiple services

Just run `.\start.ps1` and you're done!
