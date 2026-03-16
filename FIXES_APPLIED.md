# Fixes Applied - March 11, 2026

## Issue 1: Training History Endpoint Error ✅ FIXED

**Error**: `'coroutine' object has no attribute 'get_history'`

**Location**: `api/ml_endpoints.py`

**Cause**: Naming conflict - the endpoint function `get_training_history()` had the same name as the helper function, causing recursive coroutine calls.

**Fix**: Renamed endpoint to `get_training_history_endpoint()` to avoid conflict.

```python
# Before (BROKEN)
@router.get("/training-history")
async def get_training_history(...):
    history_tracker = get_training_history()  # Calls itself!

# After (FIXED)
@router.get("/training-history")
async def get_training_history_endpoint(...):
    history_tracker = get_training_history()  # Calls helper function
```

## Issue 2: Data Collection DateTime Comparison Error ✅ FIXED

**Error**: `Invalid comparison between dtype=datetime64[ns] and Timestamp`

**Location**: `scripts/collect_extended_historical_data.py`

**Cause**: Comparing timezone-aware and timezone-naive datetime objects.

**Fix**: Ensure both dataframes have timezone-naive indexes before comparison.

```python
# Added timezone normalization
if hasattr(resampled.index, 'tz') and resampled.index.tz is not None:
    resampled.index = resampled.index.tz_localize(None)
if hasattr(intraday_df.index, 'tz') and intraday_df.index.tz is not None:
    intraday_df.index = intraday_df.index.tz_localize(None)

cutoff = pd.Timestamp(intraday_df.index.min())
resampled_old = resampled[resampled.index < cutoff]  # Now works!
```

## Issue 3: WebSocket Disconnecting (INVESTIGATING)

**Symptoms**: 
- WebSocket connects then immediately disconnects
- 500 Internal Server Error on some endpoint
- Reconnecting every 3 seconds

**Possible Causes**:
1. Backend server crashed or restarting
2. An endpoint is throwing an unhandled exception
3. WebSocket handler has an error

**Next Steps**:
1. Check backend logs for the 500 error details
2. Restart the backend server
3. Check which endpoint is returning 500

## How to Restart

```powershell
# Stop current server
# Press Ctrl+C in the terminal running the bot

# Restart
.\start-apex.ps1

# Or manually
python main.py --mode paper --autostart --port 8000
```

## Verification

After restart, verify:
- [ ] Dashboard loads without errors
- [ ] WebSocket stays connected
- [ ] Training history endpoint works
- [ ] Data collection works without datetime errors

## Files Modified

1. `api/ml_endpoints.py` - Fixed training history endpoint naming
2. `scripts/collect_extended_historical_data.py` - Fixed datetime comparison

## Status

- ✅ Training history endpoint fixed
- ✅ Data collection datetime error fixed
- ⏳ WebSocket issue needs server restart
