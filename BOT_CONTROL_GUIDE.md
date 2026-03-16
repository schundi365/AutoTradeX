# Bot Control & Activity Monitor Guide

## Overview

The Bot Control Dashboard is your mission control center for the APEX trading bot. It provides:

1. **Bot Lifecycle Control** - Start, stop, pause, and restart the bot
2. **Real-time Activity Monitoring** - Track everything the bot is doing
3. **Scheduled Jobs Management** - Monitor and control cron jobs and periodic tasks
4. **Async Jobs Tracking** - Monitor background jobs like model training and data processing

**Location:** `/control` in the dashboard (now the default landing page)

---

## Bot Status & Control

### Status Indicators

The bot can be in one of four states:

| Status | Icon | Meaning | Available Actions |
|--------|------|---------|-------------------|
| **RUNNING** | 🟢 Green checkmark | Bot is actively trading | Pause, Stop, Restart |
| **STOPPED** | 🔴 Red X | Bot is completely stopped | Start, Restart |
| **PAUSED** | 🟡 Yellow pause | Bot is paused (positions open, no new trades) | Resume, Stop |
| **ERROR** | 🔴 Red warning | Bot encountered an error | Start, Restart |

### Control Actions

#### Start Bot
- **When to use:** Bot is stopped and you want to begin trading
- **What it does:**
  - Initializes all trading components
  - Connects to MT5 and data sources
  - Begins monitoring markets
  - Starts making trading decisions
- **Safety:** Confirm you're in the correct environment (PAPER vs LIVE)

#### Stop Bot
- **When to use:** You want to completely shut down trading
- **What it does:**
  - Closes all open positions immediately
  - Cancels all pending orders
  - Disconnects from data sources
  - Stops all background processes
- **Safety:** Requires confirmation - will close positions at market price

#### Pause Bot
- **When to use:** You want to temporarily halt new trades but keep positions open
- **What it does:**
  - Stops opening new positions
  - Keeps existing positions open
  - Continues monitoring for stop-loss/take-profit
  - Maintains data collection
- **Use case:** Market uncertainty, news events, temporary risk reduction

#### Restart Bot
- **When to use:** Bot is stuck, configuration changed, or after updates
- **What it does:**
  - Gracefully stops the bot (2-second delay)
  - Closes positions if in RUNNING state
  - Reinitializes all components
  - Starts fresh
- **Safety:** Requires confirmation

### Status Details

The dashboard displays key metrics:

- **Active Positions:** Number of currently open trades
- **Pending Orders:** Number of limit/stop orders waiting to execute
- **Uptime:** How long the bot has been running (HH:MM:SS format)
- **Last Started:** Timestamp when bot was last started
- **Last Stopped:** Timestamp when bot was last stopped
- **Error Message:** Detailed error if status is ERROR

---

## Activity Log Tab

### What It Tracks

The Activity Log shows **everything** the bot does in real-time:

#### Activity Types

1. **BOT_CONTROL**
   - Bot started/stopped/paused/restarted
   - Configuration changes
   - Manual interventions

2. **TRADE_OPENED**
   - New position opened
   - Symbol, direction, size, entry price
   - Reasoning and signal score

3. **TRADE_CLOSED**
   - Position closed
   - Exit price, P&L, holding time
   - Exit reason (TP, SL, manual, etc.)

4. **MODEL_PREDICTION**
   - ML model generated prediction
   - Symbol, prediction, confidence
   - Model version used

5. **DATA_COLLECTION**
   - Tick data collected
   - Order book snapshots
   - News articles processed
   - Economic data updated

6. **FEATURE_UPDATE**
   - Technical indicators recalculated
   - Feature vectors updated
   - Cached in Redis

7. **HEALTH_CHECK**
   - System health monitoring
   - Database connections
   - API availability
   - Resource usage

8. **ALERT**
   - Data quality issues
   - Performance warnings
   - System errors
   - Risk limit breaches

### Activity Status

Each activity has a status:

- **success** (green) - Completed successfully
- **running** (blue) - Currently in progress
- **failed** (red) - Failed with error
- **pending** (gray) - Queued, not started yet

### Usage Tips

1. **Monitor in real-time** - Auto-refreshes every 5 seconds
2. **Filter by type** - Focus on specific activities (trades, predictions, etc.)
3. **Check timestamps** - Verify bot is actively working
4. **Investigate failures** - Red status indicates issues to review
5. **Cross-reference with logs** - Use Logs dashboard for detailed debugging

---

## Scheduled Jobs Tab

### What Are Scheduled Jobs?

Scheduled jobs are recurring tasks that run automatically on a schedule (like cron jobs):

#### Default Scheduled Jobs

1. **Weekly Model Retraining**
   - **Schedule:** Every Sunday at 02:00 UTC
   - **Duration:** ~30 minutes
   - **Purpose:** Retrain ML models with latest data
   - **Type:** model_training

2. **Daily Data Archival**
   - **Schedule:** Every day at 00:00 UTC
   - **Duration:** ~2 minutes
   - **Purpose:** Archive old data to cold storage
   - **Type:** data_collection

3. **Weekly Portfolio Rebalancing**
   - **Schedule:** Every Monday at 09:00 UTC
   - **Duration:** ~45 seconds
   - **Purpose:** Rebalance portfolio weights
   - **Type:** rebalancing

4. **System Health Check**
   - **Schedule:** Every 5 minutes
   - **Duration:** ~2 seconds
   - **Purpose:** Monitor system health
   - **Type:** health_check

### Job Information

For each scheduled job, you can see:

- **Job Name:** Descriptive name
- **Type:** Category (model_training, data_collection, etc.)
- **Schedule:** When it runs (cron-like description)
- **Last Run:** When it last executed
- **Last Duration:** How long it took
- **Next Run:** When it will run next
- **Status:** active, paused, or failed

### Job Controls

#### Pause Job
- Temporarily disable a scheduled job
- Job won't run until resumed
- Use when: Maintenance, testing, or temporary issues

#### Resume Job
- Re-enable a paused job
- Resumes normal schedule
- Next run time is recalculated

#### Run Now
- Trigger job to run immediately
- Doesn't affect regular schedule
- Creates an async job (see Async Jobs tab)
- Use when: Need immediate execution, testing, or catching up

### Best Practices

1. **Don't pause critical jobs** - Health checks and data collection should stay active
2. **Monitor last run times** - Ensure jobs are executing as expected
3. **Check durations** - Sudden increases may indicate issues
4. **Use "Run Now" for testing** - Verify jobs work before waiting for schedule
5. **Review failed jobs** - Check logs for error details

---

## Async Jobs Tab

### What Are Async Jobs?

Async (asynchronous) jobs are long-running background tasks that execute independently:

#### Common Async Jobs

1. **Model Training**
   - Triggered by: Scheduled job or manual start
   - Duration: 10-30 minutes
   - Progress tracking: Yes
   - Can cancel: Yes (before completion)

2. **Data Backfill**
   - Triggered by: Manual request or system recovery
   - Duration: Varies (minutes to hours)
   - Progress tracking: Yes
   - Can cancel: Yes

3. **Historical Analysis**
   - Triggered by: Manual request
   - Duration: 5-15 minutes
   - Progress tracking: Yes
   - Can cancel: Yes

4. **Model Deployment**
   - Triggered by: Manual deployment
   - Duration: 1-2 minutes
   - Progress tracking: Yes
   - Can cancel: No (once started)

### Job Information

For each async job, you can see:

- **Job ID:** Unique identifier (first 8 characters shown)
- **Type:** What the job is doing
- **Status:** pending, running, completed, or failed
- **Progress:** Percentage complete (0-100%)
- **Started:** When the job began
- **Completed:** When the job finished (if done)
- **Result:** Output data (if completed)
- **Error:** Error message (if failed)

### Job Controls

#### Cancel Job
- Stop a running or pending job
- Only available for jobs in "running" or "pending" status
- Cannot cancel completed or failed jobs
- Use when: Job is stuck, no longer needed, or consuming too many resources

### Monitoring Tips

1. **Check progress regularly** - Ensure jobs are advancing
2. **Stuck at 0%?** - May be loading data, check logs
3. **Failed jobs** - Review error message and logs
4. **Long-running jobs** - Model training can take 30+ minutes
5. **Cancel if needed** - Don't let stuck jobs consume resources

---

## Integration with Other Dashboards

### Bot Control → Logs
- Activity shows WHAT happened
- Logs show WHY and HOW (detailed debugging)
- Use together for troubleshooting

### Bot Control → System Health
- Bot Control shows bot status
- System Health shows infrastructure status
- Both needed for complete picture

### Bot Control → Model Training
- Scheduled jobs trigger training
- Async jobs track training progress
- Model Training dashboard shows results

### Bot Control → Configuration
- Stop bot before major config changes
- Restart bot after config updates
- Monitor activity log for config change effects

---

## Safety & Best Practices

### Before Starting Bot

1. ✅ Check environment (PAPER vs LIVE)
2. ✅ Review configuration settings
3. ✅ Verify database connections (System Health)
4. ✅ Check for recent errors (Logs)
5. ✅ Ensure sufficient capital
6. ✅ Review risk limits

### During Operation

1. 📊 Monitor activity log regularly
2. 🔍 Check for failed activities
3. ⏰ Verify scheduled jobs are running
4. 📈 Watch async job progress
5. 🚨 Respond to alerts promptly
6. 💰 Monitor active positions count

### Before Stopping Bot

1. ⚠️ Understand positions will close at market price
2. 📉 Check current market conditions
3. 💵 Review open P&L
4. 📝 Document reason for stopping
5. 🔔 Consider pausing instead if temporary

### Emergency Procedures

#### Bot Stuck or Unresponsive
1. Check System Health dashboard
2. Review Logs for errors
3. Try Restart (not Stop)
4. If restart fails, Stop then Start
5. Check database connections

#### Unexpected Losses
1. Pause bot immediately
2. Review Trade Journal for recent trades
3. Check Logs for decision reasoning
4. Review Configuration for risk limits
5. Investigate before resuming

#### System Errors
1. Check error message in Bot Status
2. Review Logs for detailed error
3. Verify System Health status
4. Stop bot if critical error
5. Fix underlying issue before restart

---

## API Endpoints Reference

### Bot Control
- `GET /api/v1/bot/status` - Get bot status
- `POST /api/v1/bot/start` - Start bot
- `POST /api/v1/bot/stop` - Stop bot
- `POST /api/v1/bot/pause` - Pause bot
- `POST /api/v1/bot/restart` - Restart bot

### Activity Monitoring
- `GET /api/v1/bot/activity` - Get activity log
  - Query params: `limit`, `activity_type`

### Scheduled Jobs
- `GET /api/v1/bot/scheduled-jobs` - List scheduled jobs
- `POST /api/v1/bot/scheduled-jobs/{job_id}/pause` - Pause job
- `POST /api/v1/bot/scheduled-jobs/{job_id}/resume` - Resume job
- `POST /api/v1/bot/scheduled-jobs/{job_id}/run-now` - Trigger job

### Async Jobs
- `GET /api/v1/bot/async-jobs` - List async jobs
- `POST /api/v1/bot/async-jobs/{job_id}/cancel` - Cancel job

---

## Troubleshooting

### Bot Won't Start
**Symptoms:** Start button fails, error status
**Solutions:**
1. Check System Health for infrastructure issues
2. Review Logs for startup errors
3. Verify MT5 connection
4. Check database connectivity
5. Ensure no other bot instance is running

### Bot Keeps Stopping
**Symptoms:** Bot stops unexpectedly, error status
**Solutions:**
1. Check error message in status
2. Review Logs for crash details
3. Verify sufficient system resources
4. Check for data quality issues
5. Review recent configuration changes

### No Activity Showing
**Symptoms:** Activity log is empty or stale
**Solutions:**
1. Verify bot status is RUNNING
2. Check if markets are open
3. Review Configuration for enabled strategies
4. Check signal score threshold
5. Verify data collection is working

### Scheduled Job Not Running
**Symptoms:** Last run time is old, status is failed
**Solutions:**
1. Check job status (active vs paused)
2. Review Logs for job errors
3. Try "Run Now" to test manually
4. Verify system resources available
5. Check for conflicting jobs

### Async Job Stuck
**Symptoms:** Progress at 0% or not advancing
**Solutions:**
1. Wait 5-10 minutes (may be loading data)
2. Check Logs for job progress details
3. Verify system resources (CPU, memory)
4. Cancel and restart if truly stuck
5. Check for data availability issues

---

## Production Deployment Notes

### Current Implementation

The current implementation uses **in-memory storage** for:
- Bot state
- Activity logs
- Scheduled jobs list
- Async jobs list

This is suitable for **development and testing** but not production.

### Production Requirements

For production deployment, implement:

1. **Persistent Storage**
   - Store bot state in Redis or database
   - Store activity logs in TimescaleDB
   - Store job metadata in PostgreSQL

2. **Actual Bot Integration**
   - Connect to real bot process (not mock)
   - Implement process management (systemd, supervisor)
   - Handle graceful shutdown and restart

3. **Job Scheduling**
   - Integrate with APScheduler or Celery
   - Implement job queue (Redis, RabbitMQ)
   - Add job result storage

4. **WebSocket Broadcasting**
   - Broadcast bot status changes
   - Stream activity log updates
   - Push job progress updates

5. **Authentication & Authorization**
   - Require login for bot control
   - Role-based access (admin, viewer)
   - Audit log for control actions

6. **Safety Features**
   - Confirmation for LIVE environment actions
   - Rate limiting on control actions
   - Emergency stop button
   - Position size limits enforcement

---

## Next Steps

1. **Test in Development**
   - Start dashboard: `.\start-dashboard.ps1`
   - Navigate to Bot Control (default page)
   - Test all control actions
   - Monitor activity log

2. **Integrate with Real Bot**
   - Connect API endpoints to actual bot process
   - Implement persistent storage
   - Add job scheduling system

3. **Add Monitoring**
   - Set up alerts for bot stops
   - Monitor job failures
   - Track activity patterns

4. **Enhance Security**
   - Add authentication
   - Implement access controls
   - Add audit logging

---

## Summary

The Bot Control Dashboard gives you complete visibility and control over your trading bot:

✅ **Start/Stop/Pause/Restart** - Full lifecycle control
✅ **Activity Monitoring** - See everything the bot does
✅ **Scheduled Jobs** - Manage recurring tasks
✅ **Async Jobs** - Track long-running operations
✅ **Real-time Updates** - 5-second refresh
✅ **Safety Controls** - Confirmations for critical actions

This is your primary interface for operating the APEX trading bot safely and effectively.
