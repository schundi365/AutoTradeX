# APEX Trading Bot - Complete Architecture Guide

## System Overview

APEX is an Agentic AI Trading Bot using LangGraph to coordinate 7 specialist agents for automated trading decisions.

---

## Technical Stack

### Backend (Python 3.12)

#### Core Framework & Agent Orchestration
- **LangGraph** - Multi-agent workflow orchestration with state management
- **FastAPI** - High-performance async REST API server
- **Pydantic** - Data validation and settings management
- **asyncio** - Asynchronous I/O for concurrent operations

#### AI & Machine Learning
- **Ollama** - Local LLM inference (fine-tuned apex-trader model)
- **Groq** - Cloud LLM inference (llama-3.3-70b-versatile)
- **DeepSeek** - Cloud LLM fallback (deepseek-chat)
- **Anthropic Claude** - Final LLM fallback (claude-haiku-4-5)
- **OpenAI SDK** - Unified interface for Groq/DeepSeek
- **ChromaDB** - Vector database for long-term memory and context retrieval

#### Data & Storage
- **DuckDB** - Embedded analytical database (OLAP)
  - Trade history, executions, analytics
  - Sentiment analysis logs
  - LLM call metrics
  - Bot decision logs
- **pandas** - Data manipulation and analysis
- **yfinance** - Market data fetching (stocks, indices, commodities)

#### Trading & Brokers
- **MetaTrader5** (MT5) - Forex, metals, indices broker integration
- **CCXT** - Cryptocurrency exchange integration (Binance, etc.)
- **asyncio** - Async broker operations

#### Technical Analysis
- **pandas-ta** / **ta-lib** - Technical indicators (RSI, ADX, ATR, MACD, etc.)
- **numpy** - Numerical computations
- Custom implementations for:
  - Order blocks detection
  - Fair Value Gaps (FVG)
  - Liquidity zones
  - Smart Money Concepts (SMC)

#### News & Data Feeds
- **aiohttp** - Async HTTP client for news APIs
- **feedparser** - RSS feed parsing (Reuters, Bloomberg)
- **NewsAPI** - Financial news aggregation
- **GDELT** - Geopolitical event database
- **httpx** - HTTP client for LLM APIs

#### Logging & Monitoring
- **loguru** - Advanced logging with rotation and formatting
- **WebSocket** - Real-time log streaming to dashboard
- **APScheduler** - Scheduled tasks (training, cleanup)

#### Utilities
- **python-dotenv** - Environment variable management
- **pathlib** - Modern file path handling
- **threading** - Thread-safe operations for DuckDB

### Frontend (Vanilla JavaScript + HTML5)

#### Core Technologies
- **HTML5** - Semantic markup
- **CSS3** - Modern styling with:
  - CSS Grid & Flexbox for layouts
  - CSS Variables for theming
  - Animations and transitions
  - Responsive design
- **Vanilla JavaScript (ES6+)** - No framework dependencies
  - Async/await for API calls
  - Fetch API for HTTP requests
  - WebSocket for real-time updates
  - LocalStorage for state persistence

#### Visualization
- **Chart.js** - Interactive charts and graphs
  - Equity curves
  - Performance analytics
  - Latency trends
  - P&L visualization

#### UI Components
- Custom-built components (no UI framework):
  - Tabbed navigation
  - Collapsible sections
  - Real-time ticker strip
  - Trade tables with filtering
  - KPI cards
  - Log viewer with auto-scroll
  - Modal dialogs

#### API Client
- **apex-api-client.js** - Custom API wrapper
  - RESTful API calls
  - WebSocket connection management
  - Mock data generators for testing
  - Error handling and retries

### Infrastructure & Deployment

#### Development
- **Python venv** - Virtual environment isolation
- **pip** - Package management
- **Git** - Version control

#### Production (VPS/Cloud)
- **Docker** - Containerization (optional)
- **Docker Compose** - Multi-container orchestration
- **systemd** - Service management on Linux
- **nginx** - Reverse proxy (optional)
- **Supervisor** - Process monitoring (alternative to systemd)

#### Monitoring & Maintenance
- **cron** - Scheduled tasks (backups, log rotation)
- **logrotate** - Log file management
- **Custom watchdog** - Bot health monitoring and auto-restart

### Development Tools

#### Code Quality
- **Python 3.12** type hints
- **Pydantic** for runtime validation
- **asyncio** for concurrent operations
- **Exception handling** at every layer

#### Testing
- Manual testing via dashboard
- API endpoint testing with curl/Postman
- Broker connection testing scripts
- LLM tier testing utilities

### Data Flow Technologies

#### Real-time Communication
```
Frontend ←→ WebSocket ←→ FastAPI ←→ Loguru
Frontend ←→ REST API ←→ FastAPI ←→ Agents/Brokers/DB
```

#### Async Pipeline
```
LangGraph StateGraph → Async Agents → Async Brokers → Async DB
```

#### Database Architecture
```
DuckDB (Single-writer pattern)
  ├── Write Queue (asyncio.Queue)
  ├── Writer Loop (background task)
  └── Read-only connections (concurrent)
```

### Key Design Patterns

1. **Single-writer Pattern** (DuckDB) - All writes through async queue
2. **Tiered Fallback** (LLM) - Automatic failover across 4 tiers
3. **Factory Pattern** (Brokers) - Unified interface for MT5/CCXT/Paper
4. **State Machine** (LangGraph) - Agent pipeline with state transitions
5. **Observer Pattern** (WebSocket) - Real-time log broadcasting
6. **Repository Pattern** (Storage) - Data access abstraction
7. **Strategy Pattern** (Technical Analysis) - Pluggable indicators

### Performance Optimizations

- **Async I/O** throughout the stack
- **Connection pooling** for HTTP clients
- **Caching** for ticker data (60s TTL)
- **Lazy imports** to reduce startup time
- **Batch operations** for database writes
- **Rate limit caching** to avoid redundant API calls
- **Mock data** for development/testing

### Security Considerations

- **Environment variables** for sensitive data (.env)
- **No hardcoded credentials**
- **HTTPS** for all external API calls
- **Input validation** with Pydantic
- **SQL injection prevention** (parameterized queries)
- **CORS** configuration for API access
- **WebSocket authentication** (optional)

---

## 1. CORE COMPONENTS

### core/models.py
- **BotState**: Main state object passed through agent pipeline
  - quotes, news_items, calendar_events, pending_signals, approved_signals
  - open_trades, account_info, market_regime, macro_data
- **Trade**: Represents a single trade (open/closed)
- **TradingSignal**: Generated by MarketAnalyst, filtered by RiskManager
- **AccountInfo, Quote, NewsItem, CalendarEvent**: Data models

### core/config.py
- **Settings**: Loads from .env (API keys, broker credentials)
- **Risk parameters**: max_risk_per_trade_pct, max_open_trades, etc.
- **Strategy parameters**: min_signal_score, min_confidence, etc.
- **Regime multipliers**: REGIME_SL_MULTIPLIERS, REGIME_TP_MULTIPLIERS

### core/logger.py
- Loguru-based logging with WebSocket broadcasting
- Logs go to console + files (logs/apex_*.log)
- Dashboard receives real-time logs via WebSocket

---

## 2. AGENT WORKFLOW (LangGraph Pipeline)

**File**: agents/graph.py

### Agent Execution Order:
1. **data_collector_node** → Fetches quotes, news, calendar, account info
2. **market_analyst_node** → Technical analysis + ReAct reasoning → TradingSignals
3. **sentiment_agent_node** → NLP on news → adjusts signal confidence
4. **calendar_agent_node** → Checks economic events → sets news blackout
5. **macro_agent_node** → Fetches DXY, US10Y trends
6. **risk_manager_node** → Applies 10 quality gates (G1-G10) + position sizing
7. **orchestrator_node** → LLM final GO/NOGO decision
8. **execution_agent_node** → Places orders via broker

### Key Functions:
- **build_agent_graph()**: Creates LangGraph StateGraph
- **run_agent_pipeline()**: Fallback sequential execution if LangGraph unavailable

---

## 3. DATA FLOW

### Market Data Flow:
`
Broker (MT5/CCXT) → MarketFeed → data_collector_node → BotState.quotes
                                                      → BotState.ohlcv_cache
`

### News Data Flow:
`
NewsAPI/RSS/GDELT → NewsFeed → data_collector_node → BotState.news_items
                                                    → sentiment_agent_node
`

### Trade Execution Flow:
`
TradingSignal → risk_manager_node → orchestrator_node → execution_agent_node
             → Broker.place_order() → Trade (with broker_order_id)
             → storage.store_trade() → DuckDB
`

### Dashboard Data Flow:
`
Frontend → GET /api/status → api/server.py → BrokerFactory.get_account()
                                           → storage.get_analytics()
                                           → Returns JSON
`

---

## 4. API ENDPOINTS (api/server.py)

### Bot Control:
- **POST /api/bot/start** → Starts bot loop (_bot_main_loop)
- **POST /api/bot/stop** → Stops bot loop
- **POST /api/bot/restart** → Restart bot

### Data Endpoints:
- **GET /api/status** → Bot health, account info, performance stats
- **GET /api/trades/open** → Live open positions (synced with MT5)
- **GET /api/trades/history** → Closed trades from DuckDB
- **GET /api/analytics** → Win rate, profit factor, Sharpe, equity curve
- **GET /api/news** → Latest news items
- **GET /api/calendar** → Upcoming economic events
- **GET /api/sentiment/latest** → Latest sentiment analysis
- **GET /api/ticker** → Live ticker prices (yfinance, cached 60s)

### AI/MLOps Endpoints:
- **GET /api/ai/metrics** → Model performance metrics
- **GET /api/ai/history** → Training run history
- **GET /api/ai/apex-health** → Ollama health (latency, decision quality, retrain recommendation)

### Configuration:
- **GET /api/config** → Current bot configuration
- **POST /api/config** → Update risk/strategy/AI settings

### WebSocket:
- **WS /ws** → Real-time logs + state updates

---

## 5. DATABASE SCHEMA (DuckDB)

**Files**: memory/duckdb_store.py, data/storage.py

### Tables:

#### ohlcv
- symbol, timeframe, timestamp, open, high, low, close, volume
- Used for technical analysis

#### executions
- execution_id, signal_id, symbol, direction, strategy
- entry_price, stop_loss, take_profit, lot_size
- broker_order_id, status, execution_time
- Tracks all order placements

#### closed_trades
- trade_id, symbol, direction, strategy
- entry_price, close_price, final_pnl
- open_time, close_time, duration_minutes, close_reason
- Used for analytics

#### sentiment_analysis
- timestamp, news_summary, adjustments_json
- Logs sentiment agent output

#### decision_log
- timestamp, symbol, context_json, outcome, final_pnl
- Tracks orchestrator GO/NOGO decisions

#### llm_calls (for Apex Health monitoring)
- timestamp, agent, model, latency_ms, success, timeout, error
- Tracks LLM performance

#### bot_decisions (for Apex Health monitoring)
- timestamp, decision, confidence, outcome
- Tracks GO/NOGO outcomes

#### model_metadata
- model_name, model_type, last_trained, training_samples
- Tracks Ollama model info

---

## 6. LLM TIER SYSTEM (llm/client.py)

### Fallback Chain:
1. **Tier 1: Ollama** (apex-trader fine-tuned model)
   - Timeout: 8s
   - Primary for 95%+ of calls
   
2. **Tier 2: Groq** (llama-3.3-70b-versatile)
   - Timeout: 10s
   - Rate limit handling (auto-skip when limited)
   
3. **Tier 3: DeepSeek** (deepseek-chat)
   - Timeout: 12s
   
4. **Tier 4: Claude Haiku**
   - Timeout: 15s
   - Final fallback

### Rate Limit Handling:
- Detects 429 errors
- Parses retry_after from error messages
- Caches rate limit state
- Auto-skips tier until limit expires

### Usage:
`python
from llm.client import call_llm

response = await call_llm(
    system="You are a trading analyst",
    user="Analyze this signal",
    max_tokens=512,
    agent="market_analyst"  # For logging
)
`

---

## 7. BROKER INTEGRATION (brokers/base.py)

### BaseBroker Interface:
- connect(), disconnect()
- get_account() → AccountInfo
- get_quote(symbol) → Quote
- place_order(trade) → Trade
- close_trade(trade) → Trade
- modify_trade(trade, sl, tp) → Trade
- get_open_trades() → list[Trade]
- get_historical_data(symbol, timeframe, bars) → list[dict]

### Implementations:
- **MT5Broker**: MetaTrader 5 (Forex, Metals, Indices)
- **CCXTBroker**: Crypto exchanges (Binance, etc.)
- **PaperBroker**: In-memory simulation

### BrokerFactory:
`python
from brokers.base import BrokerFactory

factory = BrokerFactory(settings)
mt5 = factory.get("MT5")
await mt5.connect()
account = await mt5.get_account()
`

---

## 8. FRONTEND-BACKEND COMMUNICATION

### Frontend Files:
- **trading-bot-dashboard.html**: Main dashboard UI
- **apex-api-client.js**: API client wrapper

### Dashboard Tabs:
1. **TRADES**: Open positions, bot decision history
2. **ANALYTICS**: Performance stats, trade history, filters
3. **AI & MLOPS**: Apex health, LLM pipeline, training
4. **CONFIG**: Bot configuration, API keys

### Data Loading:
`javascript
// apex-api-client.js
const APEX = {
    async getStatus() {
        const res = await fetch('/api/status');
        return res.json();
    },
    async getOpenTrades() {
        const res = await fetch('/api/trades/open');
        return res.json();
    },
    // ... more methods
};
`

### WebSocket Updates:
`javascript
const ws = new WebSocket('ws://localhost:8000/ws');
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'log') {
        appendLog(data.message);
    } else if (data.type === 'state_update') {
        updateDashboard(data);
    }
};
`

---

## 9. FILE ORGANIZATION

### Project Structure:
`
apex-bot/
├── agents/
│   ├── graph.py          # LangGraph pipeline
│   ├── macro_agent.py    # DXY/US10Y fetcher
│   ├── memory.py         # ChromaDB long-term memory
│   └── __init__.py
├── api/
│   ├── server.py         # FastAPI REST + WebSocket
│   └── __init__.py
├── brokers/
│   ├── base.py           # Broker abstraction + implementations
│   └── __init__.py
├── core/
│   ├── config.py         # Settings + environment
│   ├── logger.py         # Loguru + WebSocket
│   ├── models.py         # Pydantic data models
│   └── __init__.py
├── data/
│   ├── storage.py        # DuckDB trade storage
│   ├── market_feed.py    # MarketFeed, NewsFeed, CalendarFeed
│   ├── news_feed.py      # Re-export
│   ├── calendar_feed.py  # Re-export
│   └── apex.db           # DuckDB database
├── frontend/
│   ├── trading-bot-dashboard.html
│   └── apex-api-client.js
├── llm/
│   └── client.py         # Tiered LLM client
├── memory/
│   └── duckdb_store.py   # DuckDB async wrapper
├── strategies/
│   └── technical.py      # Technical analysis (RSI, ADX, ATR, etc.)
├── utils/
│   ├── orchestrator.py   # Bot orchestration
│   ├── trainer.py        # Model training
│   └── position_manager.py
├── scripts/
│   ├── init_apex_health_tables.py
│   └── prepare_training_data.py
├── main.py               # Entry point
├── .env                  # API keys, credentials
└── requirements.txt
`

---

## 10. KEY WORKFLOWS

### Bot Startup:
1. User runs python main.py or clicks START in dashboard
2. POST /api/bot/start → _bot_main_loop() starts
3. Loop runs every 5 minutes (300s)
4. Each cycle: build_agent_graph() → graph.ainvoke(state)

### Trade Execution:
1. MarketAnalyst generates TradingSignals
2. RiskManager applies 10 gates (G1-G10)
3. Orchestrator makes final GO/NOGO decision
4. ExecutionAgent calls broker.place_order()
5. Trade stored in DuckDB + added to BotState.open_trades

### Trade Closure:
1. _sync_trades_with_broker() checks MT5 every cycle
2. If trade closed (SL/TP hit), updates status
3. storage.store_trade() persists to closed_trades table
4. Analytics recalculated

### Dashboard Update:
1. Frontend polls /api/status every 5s
2. WebSocket pushes real-time logs
3. _broadcast_state_update() sends portfolio snapshot

---

## 11. TROUBLESHOOTING GUIDE

### Issue: Bot not starting
- Check logs: Get-Content logs\apex_*.log -Wait -Tail 20
- Verify .env has all API keys
- Check MT5 connection: login, password, server

### Issue: No trades executing
- Check RiskManager logs for gate rejections
- Verify min_signal_score, min_confidence in config
- Check news blackout status
- Review orchestrator GO/NOGO decisions

### Issue: LLM errors
- Check Ollama is running: curl http://localhost:11434/api/tags
- Verify Groq API key not rate limited
- Check llm/client.py logs for tier fallback

### Issue: Dashboard not loading data
- Check API server running: curl http://localhost:8000/api/status
- Open browser console for JavaScript errors
- Verify CORS settings in api/server.py

### Issue: Database errors
- Check DuckDB file exists: data/apex.db
- Run init script: python scripts/init_apex_health_tables.py
- Check memory/duckdb_store.py logs

---

## 12. MONITORING COMMANDS (Windows PowerShell)

### Real-time log monitoring:
`powershell
Get-Content logs\apex_*.log -Wait -Tail 20
`

### Search for errors:
`powershell
Select-String -Path logs\apex_*.log -Pattern "ERROR|WARN" | Select-Object -Last 20
`

### Count LLM tier usage:
`powershell
Select-String -Path logs\apex_*.log -Pattern "LLM Tier" | Group-Object Line | Sort-Object Count -Descending
`

### Check Groq rate limits:
`powershell
Select-String -Path logs\apex_*.log -Pattern "Groq.*rate"
`

---

## 13. CONFIGURATION

### Environment Variables (.env):
`
# Broker
MT5_LOGIN=12345678
MT5_PASSWORD=your_password
MT5_SERVER=YourBroker-Live
MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe

# LLM APIs
GROQ_API_KEY=gsk_...
DEEPSEEK_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=apex-trader

# News
NEWS_API_KEY=your_newsapi_key

# Exchange (Crypto)
EXCHANGE_ID=binance
EXCHANGE_API_KEY=...
EXCHANGE_SECRET=...
EXCHANGE_SANDBOX=true
`

### Risk Settings (core/config.py):
- max_risk_per_trade_pct: 2.0
- max_open_trades: 5
- max_daily_drawdown_pct: 5.0
- min_equity_pct: 80.0
- max_consecutive_losses: 3

### Strategy Settings:
- min_signal_score: 6.5
- min_confidence: 0.65
- min_risk_reward: 1.8
- min_adx: 20.0
- min_atr_ratio: 0.8

---

## 14. DEPLOYMENT

### Local Development:
`powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
`

### VPS Deployment:
See CLOUD_DEPLOYMENT_PLAN.md for full guide

Quick start:
`ash
chmod +x deploy.sh
./deploy.sh
`

---

## 15. TESTING

### Test Ollama connection:
`powershell
python test_ollama_connection.py
`

### Test API endpoints:
`powershell
curl http://localhost:8000/api/status
curl http://localhost:8000/api/trades/open
`

### Test broker connection:
`python
from brokers.base import BrokerFactory
from core.config import settings

factory = BrokerFactory(settings)
mt5 = factory.get("MT5")
await mt5.connect()
print(await mt5.get_account())
`

---

## 16. FUTURE DEBUGGING

### When a trade doesn't execute:
1. Check MarketAnalyst logs for signal generation
2. Check RiskManager logs for gate rejections (G1-G10)
3. Check Orchestrator logs for GO/NOGO decision
4. Check ExecutionAgent logs for broker errors
5. Check broker logs for order rejection reasons

### When dashboard shows wrong data:
1. Check API endpoint response: curl http://localhost:8000/api/analytics
2. Check DuckDB tables: python -c "import duckdb; print(duckdb.connect('data/apex.db').execute('SELECT * FROM closed_trades').fetchall())"
3. Check frontend console for JavaScript errors
4. Check apex-api-client.js for API call failures

### When LLM calls fail:
1. Check which tier failed: grep logs for "LLM Tier"
2. Check Ollama: curl http://localhost:11434/api/tags
3. Check Groq rate limit: grep logs for "rate limited"
4. Check API keys in .env

---

## 17. AUTONOMOUS TRADING SYSTEM (NEW)

### Overview
The autonomous trading system is a hybrid decision engine that makes 90% of trading decisions using rule-based logic, with only edge cases requiring LLM review. This results in **60-70x faster** decision making compared to the original LLM-only approach.

### Performance Comparison

| Metric | Before (LLM-Only) | After (Autonomous) | Improvement |
|--------|-------------------|-------------------|-------------|
| Decision Time | 24-72s | < 1s | **60-70x faster** |
| LLM Calls | 12+ per cycle | 0-2 per cycle | **90% reduction** |
| Autonomy | Low | High | **90% rule-based** |
| Throughput | 0.2 symbols/s | 12+ symbols/s | **60x increase** |

### Architecture Components

#### 1. Market Context Engine (core/market_context.py)
**Purpose**: Maintains real-time view of entire market state

**Key Classes**:
- `MarketStateEngine`: Tracks all symbols, correlations, sector strength
- `MarketContext`: Comprehensive market snapshot (regime, risk appetite, liquidity)
- `SectorStrength`: Momentum tracking across asset sectors

**Features**:
- Updates every 15 seconds with latest market data
- Calculates correlation matrix between symbols
- Classifies market regime (STRONG_TREND, WEAK_TREND, RANGING, etc.)
- Monitors sector rotation (METALS, CRYPTO, FOREX, COMMODITIES)
- Assesses risk appetite (HIGH, MEDIUM, LOW, RISK_OFF)
- Evaluates liquidity conditions by time of day

**Usage**:
```python
from core.market_context import MarketStateEngine

engine = MarketStateEngine()
await engine.update(quotes, ohlcv_cache, macro_data)
context = engine.get_market_context(is_news_blackout=False)
# context.regime, context.risk_appetite, context.correlation_risk
```

#### 2. Fast Decision Engine (core/fast_decision.py)
**Purpose**: Rule-based decision logic for 90% of signals

**Decision Types**:
- `GO`: Auto-approve strong signals (no LLM needed)
- `NOGO`: Auto-reject weak signals (no LLM needed)
- `NEEDS_REVIEW`: Edge cases requiring LLM batch review

**Auto-Approval Criteria** (Strong Signals):
- Score ≥ 8.0
- Confidence ≥ 0.8 (80%)
- Risk/Reward ≥ 2.5
- Favorable market regime (STRONG_TREND or BREAKOUT)
- Low correlation risk (< 0.3)
- No news blackout
- Risk appetite HIGH or MEDIUM

**Auto-Rejection Criteria** (Weak Signals):
- Score < 6.0 OR Confidence < 0.5 OR R:R < 1.5
- News blackout active
- Risk appetite RISK_OFF
- High volatility regime
- ADX < 20 (too choppy)
- ATR ratio > 2.5 (too volatile)
- Volume ratio < 0.8 (low volume)

**Cross-Asset Analysis**:
- Groups signals by correlation
- Limits positions per correlation cluster (max 2)
- Ensures portfolio diversification

**Usage**:
```python
from core.fast_decision import FastDecisionEngine

engine = FastDecisionEngine()
result = engine.evaluate(signal, market_context)
# result.decision (GO/NOGO/NEEDS_REVIEW)
# result.confidence, result.reason
```

#### 3. Market Data Lake (core/data_lake.py)
**Purpose**: Centralized data access with pre-computed indicators

**Key Classes**:
- `MarketDataLake`: Caches all market data and indicators
- `SymbolData`: Complete data package per symbol

**Pre-Computed Indicators**:
- RSI (14-period)
- ADX (14-period)
- ATR (14-period) + ATR ratio
- EMA (20, 50)
- MACD + Signal
- Bollinger Bands width
- Volume ratio
- Momentum

**Features**:
- Single call to get all symbol data
- Indicators cached and refreshed every 15 seconds
- Eliminates redundant calculations
- Parallel indicator computation for all symbols

**Usage**:
```python
from core.data_lake import MarketDataLake

lake = MarketDataLake()
await lake.update_all(quotes, ohlcv_data, news, calendar)

# Get all data for one symbol
symbol_data = await lake.get_symbol_data("XAUUSD")
# symbol_data.ohlcv, symbol_data.indicators, symbol_data.quote

# Get pre-computed indicators
indicators = lake.get_cached_indicators("XAUUSD")
# indicators['rsi'], indicators['adx'], indicators['atr']
```

#### 4. Outcome Tracker & Adaptive Learning (core/outcome_tracker.py)
**Purpose**: Track decision outcomes and adapt thresholds

**Key Classes**:
- `OutcomeTracker`: Logs all decisions and outcomes
- `AdaptiveThresholds`: Adjusts decision thresholds based on performance
- `DecisionRecord`: Individual decision with outcome

**Learning Logic**:
- Win rate < 45% or Avg PnL < -$50 → **Tighten** thresholds (more selective)
- Win rate > 65% and Avg PnL > $100 → **Loosen** thresholds (more aggressive)
- Moderate performance → Gradually return to baseline

**Tracked Metrics**:
- Win rate by regime
- Average PnL by regime
- Recent performance (last 20 trades)
- Pattern success rates

**Usage**:
```python
from core.outcome_tracker import OutcomeTracker, AdaptiveThresholds

tracker = OutcomeTracker()
adaptive = AdaptiveThresholds(tracker)

# Log decision
await tracker.log_decision(signal, "GO", trade)

# Update outcome when trade closes
await tracker.update_outcome(trade.id, Outcome.WIN, pnl=150.0)

# Adjust thresholds periodically
await adaptive.adjust_based_on_performance()
```

#### 5. Autonomous Orchestrator (agents/autonomous_orchestrator.py)
**Purpose**: Main hybrid decision engine

**Process Flow**:
1. Update market state with latest data
2. Apply cross-asset diversification
3. Fast path evaluation (90% of signals)
4. Batch LLM review for edge cases (10% of signals)
5. Log decisions for learning
6. Update adaptive thresholds periodically

**Performance Tracking**:
- Total decisions made
- Fast path percentage
- Average decision time (ms)
- Recent win rate and PnL
- Regime-specific performance

**Usage**:
```python
from agents.autonomous_orchestrator import AutonomousOrchestrator

orchestrator = AutonomousOrchestrator()
state = await orchestrator.process_signals(state)

# Get performance stats
stats = orchestrator.get_performance_stats()
# stats['fast_path_pct'], stats['avg_decision_time_ms']
```

#### 6. Parallel Symbol Analysis (agents/parallel_analyzer.py)
**Purpose**: Concurrent analysis of all symbols

**Features**:
- Analyzes all symbols in parallel instead of sequentially
- Uses pre-computed indicators from data lake
- Handles errors gracefully per symbol
- Returns all results concurrently

**Performance**:
- Before: 2-6 seconds per symbol (sequential)
- After: < 100ms per symbol (parallel)
- Total time for 12 symbols: < 1 second

**Usage**:
```python
from agents.parallel_analyzer import analyze_all_symbols_parallel

signals = await analyze_all_symbols_parallel(
    symbols=["XAUUSD", "EURUSD", "BTCUSD"],
    data_lake=data_lake,
    state=bot_state
)
```

### Integration with Existing System

#### Modified Files:

**agents/graph.py**:
- Integrated autonomous orchestrator into `orchestrator_node`
- Falls back to original LLM orchestrator if disabled
- Controlled by `settings.use_autonomous_orchestrator` flag

**strategies/technical.py**:
- Added `analyse_from_indicators()` method to `TechnicalAnalyser`
- Supports generating signals from pre-computed indicators
- Avoids redundant indicator calculations

**api/server.py**:
- Added `/api/autonomous/stats` endpoint
- Returns performance metrics, fast path usage, adaptive thresholds

### Configuration

#### Enable/Disable:
```python
# In core/config.py or .env
USE_AUTONOMOUS_ORCHESTRATOR=true  # Default: enabled
```

#### Adjust Thresholds (Advanced):
```python
# In agents/autonomous_orchestrator.py
# FastDecisionEngine.__init__()
self.strong_signal_score = 8.0      # Auto-approve threshold
self.strong_confidence = 0.8        # 80% confidence
self.strong_risk_reward = 2.5       # 2.5:1 R:R

self.weak_signal_score = 6.0        # Auto-reject threshold
self.weak_confidence = 0.5          # 50% confidence
self.weak_risk_reward = 1.5         # 1.5:1 R:R
```

### API Endpoints

#### GET /api/autonomous/stats
Returns autonomous orchestrator performance statistics.

**Response**:
```json
{
  "enabled": true,
  "performance": {
    "total_decisions": 150,
    "fast_path_percentage": 92.0,
    "llm_decisions": 12,
    "avg_decision_time_ms": 85
  },
  "recent_performance": {
    "win_rate": 0.65,
    "avg_pnl": 125.50,
    "total_trades": 20,
    "wins": 13,
    "losses": 7
  },
  "regime_performance": {
    "STRONG_TREND": {
      "wins": 8,
      "losses": 2,
      "win_rate": 0.80,
      "avg_pnl": 180.25
    }
  },
  "adaptive_thresholds": {
    "min_score": 6.5,
    "min_confidence": 0.6,
    "min_rr": 1.8
  }
}
```

### Log Patterns

Watch for these log entries to verify autonomous system is working:

**Autonomous Processing**:
```
[AUTONOMOUS] Processing 12 signals...
[AUTONOMOUS] Market context: Regime=STRONG_TREND | Risk=HIGH | Liquidity=HIGH
[AUTONOMOUS] Diversification: 12 → 10 signals after correlation filtering
```

**Fast Path Decisions**:
```
[FAST_PATH] ✓ XAUUSD BUY — Strong signal: score=8.5, conf=85%, RR=3.2
[FAST_PATH] ✗ EURUSD SELL — Weak signal: score=5.8<6.0, conf=45%<50%
[FAST_PATH] ? BTCUSD BUY — needs LLM review
[FAST_PATH] Stats: 92.0% fast path (138/150 decisions)
```

**LLM Batch Review**:
```
[LLM_BATCH] Reviewing 2 edge cases...
[LLM_BATCH] ✓ BTCUSD BUY — approved
[LLM_BATCH] ✗ GBPUSD SELL — rejected
[LLM_BATCH] Reviewed 2 signals in 450ms (225ms per signal)
```

**Completion**:
```
[AUTONOMOUS] Completed in 850ms | Fast path: 10, LLM: 2 | Total approved: 8/12
```

**Adaptive Learning**:
```
[ADAPTIVE] Recent performance: WR=65.0%, Avg PnL=$125.50, Trades=20
[ADAPTIVE] Loosening thresholds due to strong performance: score>=6.3, conf>=58%, RR>=1.7
```

### Testing & Verification

#### Test Suite:
```powershell
python scripts/test_autonomous_system.py
```

Expected output: `🎉 All tests passed! System is ready to test.`

#### Check if Active:
```powershell
python scripts/check_autonomous_active.py
```

Shows:
- Autonomous system status (enabled/disabled)
- Performance metrics (fast path %, decision time)
- Recent performance (win rate, PnL)
- Adaptive thresholds
- Recent log activity

#### Monitor Performance:
```powershell
# Via API
curl http://localhost:8000/api/autonomous/stats

# Via logs
Select-String -Path logs\apex_*.log -Pattern "\[AUTONOMOUS\]|\[FAST_PATH\]" | Select-Object -Last 20
```

### Troubleshooting

#### Issue: Fast Path % Too Low (< 80%)
**Cause**: Most signals are edge cases  
**Solution**: 
- Review threshold settings in `FastDecisionEngine`
- Check if market conditions are unusual
- Verify signal quality from `MarketAnalyst`

#### Issue: Decision Time > 2 seconds
**Cause**: LLM is slow or timing out  
**Solution**:
- Check LLM tier fallback in logs
- Verify network connectivity
- Check if Ollama is running: `curl http://localhost:11434/api/tags`

#### Issue: No Autonomous Logs
**Cause**: System not enabled or bot not running  
**Solution**:
- Check `settings.use_autonomous_orchestrator = True`
- Verify bot is running: `curl http://localhost:8000/api/status`
- Wait for at least one bot cycle (5 minutes)

#### Issue: Adaptive Thresholds Not Adjusting
**Cause**: Not enough trade history  
**Solution**:
- Need at least 10 completed trades for adjustment
- Check `OutcomeTracker` is logging decisions
- Verify trades are closing and outcomes being recorded

### Performance Targets

- ✅ **Fast Path Usage**: > 85%
- ✅ **Decision Time**: < 1000ms
- ✅ **LLM Calls**: 0-2 per cycle
- ✅ **Win Rate**: Tracked by regime
- ✅ **Autonomy**: 90% rule-based

### Key Benefits

1. **Speed**: 60-70x faster decision making
2. **Autonomy**: 90% of decisions made without LLM
3. **Intelligence**: Uses full market context for better decisions
4. **Adaptability**: Learns from outcomes and adjusts thresholds
5. **Diversification**: Cross-asset analysis prevents over-correlation
6. **Scalability**: Parallel processing handles more symbols efficiently
7. **Cost Efficiency**: 90% reduction in LLM API calls

### Documentation Files

- `AUTONOMOUS_TRADING_STRATEGY.md` - Original strategy document
- `AUTONOMOUS_IMPLEMENTATION_SUMMARY.md` - Technical implementation details
- `AUTONOMOUS_QUICK_START.md` - Quick reference guide
- `START_AUTONOMOUS_BOT.md` - Startup guide
- `SYSTEM_READY.md` - Verification and status

---

**END OF ARCHITECTURE GUIDE**

For specific issues, check the relevant module's docstring or the logs.
