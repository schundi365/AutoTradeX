# Agent Logs Tracking & Download Guide

## Overview

Track and download logs from each agent in the decision-making pipeline with timestamps and agent attribution.

## Decision-Making Agents

The bot uses 8 agents in sequence:

1. **DATA_COLLECTOR** - Fetches quotes, OHLCV, news, calendar
2. **MARKET_ANALYST** - Technical analysis, generates signals
3. **SENTIMENT_AGENT** - News sentiment analysis
4. **CALENDAR_AGENT** - Economic calendar checks
5. **MACRO_AGENT** - DXY/US10Y macro data
6. **RISK_MANAGER** - Signal filtering, position sizing
7. **ORCHESTRATOR** - LLM final decision
8. **EXECUTION_AGENT** - Places orders via broker

Plus supporting agents:
- **FAST_DECISION** - Rule-based fast path (90% of decisions)
- **BOT_LIFECYCLE** - Bot startup/shutdown
- **API** - Dashboard API requests

## How to Track Agent Logs

### 1. Filter by Agent

1. Go to http://localhost:8000
2. Click "BOT LOGS" tab
3. Select agent from dropdown:
   - ALL AGENTS (default)
   - DATA_COLLECTOR
   - MARKET_ANALYST
   - SENTIMENT_AGENT
   - CALENDAR_AGENT
   - MACRO_AGENT
   - RISK_MANAGER
   - ORCHESTRATOR
   - EXECUTION_AGENT
   - FAST_DECISION
   - BOT_LIFECYCLE
   - API

### 2. Combine Filters

You can combine Level + Agent filters:

**Example 1: Training logs from API**
- Level: TRAINING
- Agent: API
- Shows only training-related API calls

**Example 2: Signals from Risk Manager**
- Level: SIGNAL
- Agent: RISK_MANAGER
- Shows only risk management decisions

**Example 3: Errors from Orchestrator**
- Level: ERRORS
- Agent: ORCHESTRATOR
- Shows only LLM errors

### 3. Download Agent Logs

1. Select filters (Level + Agent)
2. Click "📥 DOWNLOAD"
3. File saved as: `apex_logs_training_risk_manager_2026-03-11T10-47-00.txt`

## Download Format

Downloaded files include a header with summary:

```
═══════════════════════════════════════════════════════════════════
  APEX TRADING BOT - LOG EXPORT
═══════════════════════════════════════════════════════════════════

Export Date: 3/11/2026, 10:47:00 AM
Filter: TRAINING
Agent: RISK_MANAGER
Time Range: 10:46:50 - 10:47:35
Total Entries: 15

Agent Breakdown:
  RISK_MANAGER        : 8 entries
  API                 : 4 entries
  ORCHESTRATOR        : 3 entries

═══════════════════════════════════════════════════════════════════
TIME     | LEVEL    | AGENT                | MESSAGE
═══════════════════════════════════════════════════════════════════

10:46:50 | AI       | API                  | Auto-detected timeframe: M15
10:46:52 | AI       | API                  | Training config: timeframe=M15
10:46:55 | AI       | API                  | Starting training pipeline for XAUUSD
10:46:58 | AI       | RISK_MANAGER         | Generating training data for XAUUSD
10:47:01 | AI       | RISK_MANAGER         | Training period: 6 months
10:47:03 | INFO     | RISK_MANAGER         | Querying historical data
10:47:06 | INFO     | RISK_MANAGER         | Retrieved 3653 bars
10:47:11 | AI       | RISK_MANAGER         | Generated 1853 training samples
10:47:14 | INFO     | RISK_MANAGER         | Label distribution: UP=1035, DOWN=818
10:47:17 | AI       | RISK_MANAGER         | Train set: 1482 samples
10:47:20 | INFO     | RISK_MANAGER         | Validation set: 371 samples
10:47:22 | AI       | ORCHESTRATOR         | Training XGBoost model
10:47:26 | INFO     | ORCHESTRATOR         | XGBoost validation metrics: accuracy=0.4960
10:47:29 | SIGNAL   | ORCHESTRATOR         | Model rejected: accuracy 0.4960 < 0.521
10:47:32 | SIGNAL   | API                  | Logged training attempt: xgboost XAUUSD - rejected
10:47:35 | SIGNAL   | API                  | Model training completed but rejected for XAUUSD
```

## Agent-Specific Use Cases

### Track Data Collection

**Filter:** DATA_COLLECTOR
**Shows:**
- Quote fetching
- OHLCV data retrieval
- News/calendar updates
- Account info sync

**Example logs:**
```
10:30:15 | INFO | DATA_COLLECTOR | Refreshing market data for 12 symbols
10:30:18 | INFO | DATA_COLLECTOR | 12 quotes | 50 news | 8 calendar events loaded
10:30:20 | INFO | DATA_COLLECTOR | Account: MT5 | Balance: 120000.00 USD
```

### Track Signal Generation

**Filter:** MARKET_ANALYST
**Shows:**
- Technical analysis
- Signal generation
- Strategy adjustments
- ReAct reasoning

**Example logs:**
```
10:31:05 | INFO | MARKET_ANALYST | Scanning 12 symbols for technical setups
10:31:08 | INFO | MARKET_ANALYST | 8 signals pass score≥6.5 gate
10:31:10 | INFO | MARKET_ANALYST | [ReAct] BUY XAUUSD | Score: 7.2 | Reason: Strong breakout
```

### Track Risk Decisions

**Filter:** RISK_MANAGER
**Shows:**
- Signal filtering (G1-G10 gates)
- Position sizing
- Risk budget tracking
- Rejections with reasons

**Example logs:**
```
10:32:15 | INFO | RISK_MANAGER | Evaluating 8 signals against 3 open trades
10:32:18 | INFO | RISK_MANAGER | Existing open trades using $4,335 (3.6% of account)
10:32:20 | INFO | RISK_MANAGER | Prioritized 8 signals by quality (conf × score)
10:32:22 | INFO | RISK_MANAGER | [RISK] APPROVED BUY XAUUSD | T1:0.77 lots | R:R 2.0
10:32:24 | INFO | RISK_MANAGER | [RISK] REJECTED SELL GBPUSD — P-03: combined open risk at 6.0% cap
10:32:26 | INFO | RISK_MANAGER | 3/8 signals approved (SOP gates G1-G10)
```

### Track LLM Decisions

**Filter:** ORCHESTRATOR
**Shows:**
- LLM calls
- Final approve/reject decisions
- Reasoning
- Fallback logic

**Example logs:**
```
10:33:10 | INFO | ORCHESTRATOR | [LLM_BATCH] Reviewing 3 signals with LLM
10:33:15 | INFO | ORCHESTRATOR | [LLM_BATCH] Approved 2/3 signals
10:33:17 | INFO | ORCHESTRATOR | [LLM_BATCH] Rejected SELL EURUSD: weak setup
```

### Track Trade Execution

**Filter:** EXECUTION_AGENT
**Shows:**
- Order placement
- Trade confirmations
- Execution errors
- Broker responses

**Example logs:**
```
10:34:05 | INFO | EXECUTION_AGENT | Placing BUY order: XAUUSD 0.77 lots @ 2650.50
10:34:08 | INFO | EXECUTION_AGENT | Order executed: ticket #12345678
10:34:10 | INFO | EXECUTION_AGENT | Trade opened: XAUUSD BUY 0.77 lots | SL: 2620 | TP: 2710
```

### Track Fast Path Decisions

**Filter:** FAST_DECISION
**Shows:**
- Rule-based decisions (90% of signals)
- Fast path approvals
- Bypass reasons

**Example logs:**
```
10:35:05 | INFO | FAST_DECISION | [FAST_PATH] 7/8 signals approved by rules
10:35:07 | INFO | FAST_DECISION | [FAST_PATH] Skipped LLM for high-confidence signals
10:35:09 | INFO | FAST_DECISION | [FAST_PATH] 1 signal sent to LLM for review
```

## Decision Cycle Timeline

Track a complete decision cycle by downloading ALL logs:

```
10:30:00 | BOT_LIFECYCLE    | Starting decision cycle #42
10:30:02 | DATA_COLLECTOR   | Refreshing market data for 12 symbols
10:30:05 | DATA_COLLECTOR   | 12 quotes | 50 news | 8 calendar events loaded
10:30:08 | MARKET_ANALYST   | Scanning 12 symbols for technical setups
10:30:12 | MARKET_ANALYST   | 8 signals pass score≥6.5 gate
10:30:15 | SENTIMENT_AGENT  | Analysing 50 news items against 8 signals
10:30:18 | SENTIMENT_AGENT  | XAUUSD confidence 65% → 73% (positive news)
10:30:20 | CALENDAR_AGENT   | Checking 8 upcoming events
10:30:22 | CALENDAR_AGENT   | No blackout active
10:30:24 | MACRO_AGENT      | Fetching global macro indicators
10:30:27 | MACRO_AGENT      | DXY trend: FLAT, Yield trend: FLAT
10:30:30 | RISK_MANAGER     | Evaluating 8 signals against 3 open trades
10:30:35 | RISK_MANAGER     | 3/8 signals approved (SOP gates G1-G10)
10:30:38 | ORCHESTRATOR     | [LLM_BATCH] Reviewing 3 signals with LLM
10:30:45 | ORCHESTRATOR     | [LLM_BATCH] Approved 2/3 signals
10:30:48 | EXECUTION_AGENT  | Placing 2 orders
10:30:52 | EXECUTION_AGENT  | 2 trades opened successfully
10:30:55 | BOT_LIFECYCLE    | Decision cycle #42 completed in 55s
```

## Filename Convention

Downloaded files follow this pattern:

```
apex_logs_{level}_{agent}_{timestamp}.txt
```

Examples:
- `apex_logs_all_all_agents_2026-03-11T10-47-00.txt`
- `apex_logs_training_api_2026-03-11T10-47-00.txt`
- `apex_logs_signals_risk_manager_2026-03-11T10-47-00.txt`
- `apex_logs_errors_orchestrator_2026-03-11T10-47-00.txt`

## Tips

### Debug Decision Rejections

1. Filter: SIGNAL + RISK_MANAGER
2. Look for "REJECTED" messages
3. See rejection reasons (G1-G10 gates)

### Monitor Agent Performance

1. Download ALL logs for a day
2. Count entries per agent
3. Identify bottlenecks

### Track Training Progress

1. Filter: TRAINING + API
2. Watch training pipeline
3. Download for analysis

### Analyze LLM Usage

1. Filter: AI + ORCHESTRATOR
2. See LLM call frequency
3. Check fast path effectiveness

### Export for Team Review

1. Select relevant filters
2. Download logs
3. Share text file with team

## Summary

- ✅ 11 agent filters available
- ✅ Combine Level + Agent filters
- ✅ Download with agent attribution
- ✅ Header includes agent breakdown
- ✅ Timestamped filenames
- ✅ Track complete decision cycles
- ✅ Debug agent-specific issues

Now you can track every agent's activity with timestamps and download for analysis!
