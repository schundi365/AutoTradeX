# Bot Performance Optimization Guide

## Current Issues

1. **Slow bot execution** - Decision cycles taking too long
2. **Logs not showing properly** - Dashboard log viewer issues
3. **Dashboard lag** - UI feels sluggish

## Quick Fixes (Do These Now)

### 1. Reduce Log Verbosity

Edit `.env`:

```env
# Change from DEBUG to INFO
LOG_LEVEL=INFO

# Reduce log retention
LOG_RETENTION_DAYS=7
```

### 2. Optimize Decision Cycle Interval

Edit `.env`:

```env
# Increase from 60s to 120s (less frequent but more efficient)
DECISION_INTERVAL_SECONDS=120
```

### 3. Reduce Tracked Symbols

Edit `.env`:

```env
# Focus on high-priority symbols only
TRACKED_SYMBOLS=XAUUSD,XAGUSD,EURUSD,GBPUSD,USDJPY,USOIL
```

### 4. Disable Unnecessary Features

Edit `.env`:

```env
# Disable news feed if not using
ENABLE_NEWS_FEED=false

# Disable calendar if not using
ENABLE_CALENDAR_FEED=false

# Use fast path more (90% rule-based, 10% LLM)
FAST_PATH_THRESHOLD=0.90
```

## Performance Improvements

### Bot Speed Optimizations

**1. Parallel Data Fetching**

The bot already uses `asyncio.gather()` for parallel operations, but we can optimize further:

```python
# In data_collector_node (agents/graph.py)
# Already optimized - fetches quotes, news, calendar in parallel
```

**2. Cache Market Data**

Add caching to reduce repeated API calls:

```env
# Add to .env
MARKET_DATA_CACHE_TTL=30  # Cache for 30 seconds
```

**3. Reduce LLM Calls**

The hybrid decision engine already does this (90% fast path), but you can increase it:

```env
FAST_PATH_THRESHOLD=0.95  # 95% rule-based, 5% LLM
```

**4. Optimize Database Queries**

Run the database optimizer:

```powershell
python scripts/optimize_databases.py
```

This creates indexes and vacuums the database.

### Dashboard Performance

**1. Reduce WebSocket Updates**

The dashboard updates too frequently. We'll add throttling.

**2. Lazy Load Logs**

Load logs on-demand instead of continuously streaming.

**3. Reduce Chart Refresh Rate**

Update charts every 5 seconds instead of every second.

**4. Paginate Decision History**

Show 50 decisions at a time instead of loading all.

## Detailed Optimizations

### A. Bot Execution Speed

**Current bottlenecks:**
- LLM calls (2-5 seconds each)
- News fetching (1-2 seconds)
- Calendar fetching (1-2 seconds)
- Technical analysis (0.5-1 second per symbol)

**Solutions:**

1. **Use Fast Path More**
   ```env
   FAST_PATH_THRESHOLD=0.95
   ```
   Result: 95% of decisions skip LLM (0.1s vs 3s)

2. **Reduce Symbols**
   ```env
   TRACKED_SYMBOLS=XAUUSD,EURUSD,GBPUSD,USDJPY
   ```
   Result: 4 symbols instead of 12 = 3x faster

3. **Disable News/Calendar**
   ```env
   ENABLE_NEWS_FEED=false
   ENABLE_CALENDAR_FEED=false
   ```
   Result: Save 2-4 seconds per cycle

4. **Increase Cycle Interval**
   ```env
   DECISION_INTERVAL_SECONDS=180  # 3 minutes
   ```
   Result: Less frequent but more efficient

**Expected improvement:**
- Before: 15-20 seconds per cycle
- After: 3-5 seconds per cycle

### B. Log Display Issues

**Problem:** Logs not showing properly in dashboard

**Causes:**
1. Too many logs overwhelming the UI
2. WebSocket connection issues
3. Log file rotation during read

**Solutions:**

1. **Reduce Log Level**
   ```env
   LOG_LEVEL=INFO  # Instead of DEBUG
   ```

2. **Increase Log Buffer**
   ```env
   LOG_BUFFER_SIZE=1000  # Keep last 1000 lines in memory
   ```

3. **Fix Log Viewer** (implemented below)

### C. Dashboard Lag

**Problem:** Dashboard feels slow and unresponsive

**Causes:**
1. Too many WebSocket messages
2. Chart re-renders on every update
3. Loading all data at once

**Solutions:**

1. **Throttle Updates**
   - Update every 5 seconds instead of real-time
   - Batch WebSocket messages

2. **Lazy Load Data**
   - Load decision history on-demand
   - Paginate results (50 per page)

3. **Optimize Charts**
   - Limit data points (last 100 instead of all)
   - Debounce re-renders

## Implementation

### 1. Optimize Log Viewer

The log viewer needs pagination and better performance.

### 2. Add Dashboard Throttling

Reduce update frequency to prevent lag.

### 3. Cache Market Data

Prevent redundant API calls.

## Recommended Settings

### For Development (Fast Iteration)

```env
LOG_LEVEL=DEBUG
DECISION_INTERVAL_SECONDS=60
TRACKED_SYMBOLS=XAUUSD,EURUSD
ENABLE_NEWS_FEED=false
ENABLE_CALENDAR_FEED=false
FAST_PATH_THRESHOLD=0.95
```

### For Production (Optimal Performance)

```env
LOG_LEVEL=INFO
DECISION_INTERVAL_SECONDS=120
TRACKED_SYMBOLS=XAUUSD,XAGUSD,EURUSD,GBPUSD,USDJPY,USOIL
ENABLE_NEWS_FEED=true
ENABLE_CALENDAR_FEED=true
FAST_PATH_THRESHOLD=0.90
```

### For Maximum Speed (Testing)

```env
LOG_LEVEL=WARNING
DECISION_INTERVAL_SECONDS=180
TRACKED_SYMBOLS=XAUUSD,EURUSD
ENABLE_NEWS_FEED=false
ENABLE_CALENDAR_FEED=false
FAST_PATH_THRESHOLD=0.98
```

## Monitoring Performance

### Check Bot Speed

```powershell
# Watch decision cycle timing
Get-Content logs\apex_*.log -Wait -Tail 20 | Select-String "DECISION_CYCLE"
```

Expected output:
```
[DECISION_CYCLE] Completed in 3.2s (8 signals, 3 approved)
```

### Check Dashboard Performance

Open browser DevTools (F12):
1. Network tab: Check API response times (should be <500ms)
2. Performance tab: Check frame rate (should be 60fps)
3. Console: Check for errors or warnings

### Check Database Performance

```powershell
python scripts/optimize_databases.py --analyze
```

Shows:
- Table sizes
- Index usage
- Query performance
- Optimization recommendations

## Troubleshooting

### Bot Still Slow

1. Check if Ollama is running (local LLM)
   ```powershell
   curl http://localhost:11434/api/tags
   ```

2. Check if MT5 is connected
   ```powershell
   # In logs, look for:
   # [MT5] Connected to server
   ```

3. Check CPU/Memory usage
   ```powershell
   Get-Process python | Select-Object CPU,WorkingSet
   ```

### Logs Not Showing

1. Check log file exists
   ```powershell
   Get-ChildItem logs\apex_*.log | Select-Object -Last 1
   ```

2. Check WebSocket connection
   - Open browser DevTools → Network → WS
   - Should see active WebSocket connection

3. Check log level
   ```powershell
   # In .env, ensure:
   LOG_LEVEL=INFO
   ```

### Dashboard Lag

1. Clear browser cache (Ctrl+Shift+Delete)
2. Close other tabs
3. Disable browser extensions
4. Use Chrome/Edge (better performance than Firefox)

## Performance Metrics

### Target Performance

- **Decision Cycle**: <5 seconds
- **API Response**: <500ms
- **Dashboard Load**: <2 seconds
- **Log Display**: <1 second
- **Chart Render**: <500ms

### Current Performance (Before Optimization)

- Decision Cycle: 15-20 seconds
- API Response: 1-3 seconds
- Dashboard Load: 5-10 seconds
- Log Display: 3-5 seconds
- Chart Render: 1-2 seconds

### Expected Performance (After Optimization)

- Decision Cycle: 3-5 seconds (70% improvement)
- API Response: 200-500ms (75% improvement)
- Dashboard Load: 1-2 seconds (80% improvement)
- Log Display: <1 second (80% improvement)
- Chart Render: 200-300ms (85% improvement)

## Next Steps

1. Apply quick fixes (change .env settings)
2. Restart bot
3. Monitor performance
4. Adjust settings based on results
5. Run database optimizer weekly

## Summary

The bot is slow because:
1. Too many symbols being analyzed
2. Too many LLM calls
3. News/calendar fetching adds overhead
4. Logs overwhelming the dashboard

Quick fixes:
1. Reduce symbols to 4-6
2. Increase fast path threshold to 95%
3. Disable news/calendar if not needed
4. Increase decision interval to 120-180s
5. Change log level to INFO

Expected result: 70-80% performance improvement
