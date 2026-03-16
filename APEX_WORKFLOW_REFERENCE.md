# APEX Bot - Quick Workflow Reference

## Complete Trade Lifecycle

### 1. BOT CYCLE START (Every 5 minutes)
`
api/server.py::_bot_main_loop()
  ↓
agents/graph.py::build_agent_graph()
  ↓
graph.ainvoke(BotState)
`

### 2. DATA COLLECTION
`
agents/graph.py::data_collector_node()
  ↓
data/market_feed.py::MarketFeed.get_quote()  → BotState.quotes
data/market_feed.py::NewsFeed.fetch_latest() → BotState.news_items
data/market_feed.py::CalendarFeed.fetch_upcoming() → BotState.calendar_events
brokers/base.py::MT5Broker.get_account() → BotState.account_info
`

### 3. TECHNICAL ANALYSIS
`
agents/graph.py::market_analyst_node()
  ↓
strategies/technical.py::TechnicalAnalyser.analyse()
  ↓
Generates TradingSignal objects
  ↓
ReAct reasoning loop (LLM validates each signal)
  ↓
BotState.pending_signals
`

### 4. SENTIMENT ANALYSIS
`
agents/graph.py::sentiment_agent_node()
  ↓
llm/client.py::call_llm() → Sentiment adjustments
  ↓
Updates signal.confidence based on news alignment
  ↓
memory/duckdb_store.py::log_sentiment_analysis()
`

### 5. CALENDAR CHECK
`
agents/graph.py::calendar_agent_node()
  ↓
Checks upcoming high-impact events
  ↓
Sets BotState.is_news_blackout if event within window
  ↓
Filters signals for affected currencies
`

### 6. MACRO ANALYSIS
`
agents/graph.py::macro_agent_node()
  ↓
agents/macro_agent.py::MacroAgent.get_macro_sentiment()
  ↓
Fetches DXY, US10Y trends
  ↓
BotState.macro_data
`

### 7. RISK MANAGEMENT (10 GATES)
`
agents/graph.py::risk_manager_node()
  ↓
For each signal:
  G1: Check min_signal_score
  G2: Check min_confidence
  G3: Check min_risk_reward
  G4: Check ADX (trend strength)
  G5: Check ATR (volatility)
  G6: Check volume
  G7: Check news blackout
  G8: Check macro regime
  G9: Check daily drawdown
  G10: Check max open trades
  ↓
Position sizing (Half-Kelly + regime multipliers)
  ↓
BotState.approved_signals
`

### 8. ORCHESTRATOR DECISION
`
agents/graph.py::orchestrator_node()
  ↓
llm/client.py::call_llm() → GO/NOGO decision
  ↓
memory/duckdb_store.py::log_decision()
  ↓
BotState.final_signals
`

### 9. EXECUTION
`
agents/graph.py::execution_agent_node()
  ↓
brokers/base.py::MT5Broker.place_order()
  ↓
Trade object with broker_order_id
  ↓
data/storage.py::storage.store_trade()
  ↓
BotState.open_trades.append(trade)
`

### 10. TRADE MONITORING
`
api/server.py::_sync_trades_with_broker()
  ↓
brokers/base.py::MT5Broker.get_open_trades()
  ↓
Compare with BotState.open_trades
  ↓
If closed: Update status, store to closed_trades
`

### 11. DASHBOARD UPDATE
`
api/server.py::_broadcast_state_update()
  ↓
WebSocket → frontend
  ↓
frontend/trading-bot-dashboard.html updates UI
`

---

## API Request Flow

### GET /api/status
`
frontend → GET /api/status
  ↓
api/server.py::get_status()
  ↓
brokers/base.py::BrokerFactory.get("MT5").get_account()
  ↓
api/server.py::_get_comprehensive_analytics()
  ↓
data/storage.py::storage.get_analytics()
  ↓
Returns JSON to frontend
`

### GET /api/trades/open
`
frontend → GET /api/trades/open
  ↓
api/server.py::get_open_trades()
  ↓
brokers/base.py::MT5Broker.get_open_trades()
  ↓
Reconcile with BotState.open_trades
  ↓
Returns JSON to frontend
`

### GET /api/analytics
`
frontend → GET /api/analytics
  ↓
api/server.py::get_analytics()
  ↓
api/server.py::_get_comprehensive_analytics()
  ↓
data/storage.py::storage.get_analytics()
  ↓
Merges DB trades + MT5 history + open P&L
  ↓
Calculates win_rate, profit_factor, Sharpe, drawdown
  ↓
Returns JSON to frontend
`

### GET /api/ai/apex-health
`
frontend → GET /api/ai/apex-health
  ↓
api/server.py::get_apex_health()
  ↓
memory/duckdb_store.py::DuckDBStore.execute_read()
  ↓
Queries llm_calls, bot_decisions, model_metadata tables
  ↓
Calculates latency, GO win rate, retrain recommendation
  ↓
Returns JSON to frontend
`

---

## LLM Call Flow

### Orchestrator Decision
`
agents/graph.py::orchestrator_node()
  ↓
llm/client.py::call_llm(agent="orchestrator")
  ↓
Tier 1: llm/client.py::_call_ollama()
  → http://localhost:11434/api/generate
  → Success? Return response
  → Timeout/Error? Fall to Tier 2
  ↓
Tier 2: llm/client.py::_call_groq()
  → Check rate limit cache
  → If limited, skip to Tier 3
  → https://api.groq.com/openai/v1/chat/completions
  → Success? Return response
  → Rate limit? Cache retry_after, fall to Tier 3
  ↓
Tier 3: llm/client.py::_call_deepseek()
  → https://api.deepseek.com/chat/completions
  → Success? Return response
  → Error? Fall to Tier 4
  ↓
Tier 4: llm/client.py::_call_claude()
  → Anthropic API
  → Success? Return response
  → Error? Return None
`

---

## Database Write Flow

### Trade Execution
`
agents/graph.py::execution_agent_node()
  ↓
Trade object created
  ↓
data/storage.py::storage.store_trade(trade)
  ↓
memory/duckdb_store.py::DuckDBStore.execute_write()
  ↓
Enqueues write to _write_queue
  ↓
_writer_loop() processes queue
  ↓
DuckDB INSERT into executions table
`

### Sentiment Logging
`
agents/graph.py::sentiment_agent_node()
  ↓
memory/duckdb_store.py::DuckDBStore.log_sentiment_analysis()
  ↓
INSERT into sentiment_analysis table
`

### Decision Logging
`
agents/graph.py::orchestrator_node()
  ↓
memory/duckdb_store.py::DuckDBStore.log_decision()
  ↓
INSERT into decision_log table
`

---

## Error Handling Flow

### LLM Failure
`
llm/client.py::call_llm()
  ↓
All tiers fail
  ↓
Returns None
  ↓
Caller checks if response is None
  ↓
Uses fallback logic (e.g., skip signal, use default)
`

### Broker Connection Failure
`
brokers/base.py::MT5Broker.connect()
  ↓
Connection fails
  ↓
Returns False
  ↓
Caller logs warning
  ↓
Uses mock data or skips cycle
`

### Database Write Failure
`
memory/duckdb_store.py::execute_write()
  ↓
DuckDB error
  ↓
Exception caught in _writer_loop()
  ↓
Logs error
  ↓
Sets exception on future
  ↓
Caller handles exception
`

---

## Module Dependencies

### agents/graph.py depends on:
- core.models (BotState, TradingSignal, Trade)
- core.config (settings, regime multipliers)
- core.logger (get_agent_logger)
- llm.client (call_llm)
- memory.duckdb_store (DuckDBStore)
- strategies.technical (TechnicalAnalyser)
- brokers.base (BrokerFactory)
- data.market_feed (MarketFeed, NewsFeed, CalendarFeed)
- agents.macro_agent (MacroAgent)
- agents.memory (memory)

### api/server.py depends on:
- core.config (settings)
- core.logger (get_agent_logger, register_ws_client)
- core.models (BotState, Trade, AccountInfo, TradeStatus)
- agents.graph (run_agent_pipeline, build_agent_graph)
- brokers.base (BrokerFactory)
- data.storage (storage)
- data.market_feed (NewsFeed, CalendarFeed)
- memory.duckdb_store (DuckDBStore)
- utils.orchestrator (orchestrator)
- utils.trainer (trainer)

### frontend/trading-bot-dashboard.html depends on:
- apex-api-client.js (APEX object)
- Chart.js (for charts)
- WebSocket connection to /ws

---

**END OF WORKFLOW REFERENCE**
