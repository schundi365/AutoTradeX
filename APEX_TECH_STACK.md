# APEX Trading Bot - Technology Stack Diagram

## Complete Technology Stack

`
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND LAYER                          │
├─────────────────────────────────────────────────────────────────┤
│  HTML5 + CSS3 + Vanilla JavaScript (ES6+)                       │
│  ├── Chart.js (visualization)                                   │
│  ├── WebSocket API (real-time updates)                          │
│  ├── Fetch API (HTTP requests)                                  │
│  └── LocalStorage (state persistence)                           │
│                                                                  │
│  Custom Components:                                             │
│  • Tabbed navigation • Collapsible sections                     │
│  • Real-time ticker • Trade tables • KPI cards                  │
│  • Log viewer • Modal dialogs                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↕ HTTP/WebSocket
┌─────────────────────────────────────────────────────────────────┐
│                         API LAYER                               │
├─────────────────────────────────────────────────────────────────┤
│  FastAPI (Python 3.12)                                          │
│  ├── REST Endpoints (GET/POST)                                  │
│  ├── WebSocket Server (real-time logs)                          │
│  ├── CORS Middleware                                            │
│  ├── Pydantic (validation)                                      │
│  └── asyncio (async operations)                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────────┐
│                    AGENT ORCHESTRATION LAYER                    │
├─────────────────────────────────────────────────────────────────┤
│  LangGraph (Multi-agent workflow)                               │
│  ├── StateGraph (state management)                              │
│  ├── 7 Specialist Agents                                        │
│  └── Sequential fallback                                        │
│                                                                  │
│  Agents:                                                        │
│  1. DataCollector    → Market data fetching                     │
│  2. MarketAnalyst    → Technical analysis + ReAct               │
│  3. SentimentAgent   → News NLP analysis                        │
│  4. CalendarAgent    → Economic event monitoring                │
│  5. MacroAgent       → DXY/US10Y trends                         │
│  6. RiskManager      → 10 quality gates + sizing                │
│  7. Orchestrator     → LLM final decision                       │
│  8. ExecutionAgent   → Order placement                          │
└─────────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────────┐
│                         AI/LLM LAYER                            │
├─────────────────────────────────────────────────────────────────┤
│  Tiered LLM System (4 tiers with auto-fallback)                │
│                                                                  │
│  Tier 1: Ollama (Local)                                         │
│  ├── apex-trader (fine-tuned model)                             │
│  ├── http://localhost:11434                                     │
│  └── Timeout: 8s                                                │
│                                                                  │
│  Tier 2: Groq (Cloud)                                           │
│  ├── llama-3.3-70b-versatile                                    │
│  ├── Rate limit handling                                        │
│  └── Timeout: 10s                                               │
│                                                                  │
│  Tier 3: DeepSeek (Cloud)                                       │
│  ├── deepseek-chat                                              │
│  └── Timeout: 12s                                               │
│                                                                  │
│  Tier 4: Claude (Cloud)                                         │
│  ├── claude-haiku-4-5                                           │
│  └── Timeout: 15s                                               │
│                                                                  │
│  Memory:                                                        │
│  └── ChromaDB (vector database for context retrieval)           │
└─────────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────────┐
│                      TECHNICAL ANALYSIS LAYER                   │
├─────────────────────────────────────────────────────────────────┤
│  pandas-ta / ta-lib                                             │
│  ├── RSI (Relative Strength Index)                              │
│  ├── ADX (Average Directional Index)                            │
│  ├── ATR (Average True Range)                                   │
│  ├── MACD (Moving Average Convergence Divergence)               │
│  ├── EMA/SMA (Moving Averages)                                  │
│  └── Volume indicators                                          │
│                                                                  │
│  Custom Smart Money Concepts:                                   │
│  ├── Order Blocks detection                                     │
│  ├── Fair Value Gaps (FVG)                                      │
│  ├── Liquidity zones                                            │
│  └── Break of Structure (BOS)                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────────┐
│                         DATA LAYER                              │
├─────────────────────────────────────────────────────────────────┤
│  DuckDB (Embedded OLAP Database)                                │
│  ├── Single-writer pattern (asyncio.Queue)                      │
│  ├── Read-only connections (concurrent)                         │
│  └── Tables:                                                    │
│      • ohlcv (market data)                                      │
│      • executions (order tracking)                              │
│      • closed_trades (history)                                  │
│      • sentiment_analysis (NLP logs)                            │
│      • decision_log (orchestrator decisions)                    │
│      • llm_calls (performance metrics)                          │
│      • bot_decisions (GO/NOGO outcomes)                         │
│      • model_metadata (training info)                           │
│                                                                  │
│  pandas (Data manipulation)                                     │
│  └── DataFrames for analytics                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────────┐
│                      BROKER INTEGRATION LAYER                   │
├─────────────────────────────────────────────────────────────────┤
│  Broker Abstraction (Factory Pattern)                           │
│                                                                  │
│  MT5Broker (MetaTrader 5)                                       │
│  ├── Forex (EURUSD, GBPUSD, USDJPY, etc.)                       │
│  ├── Metals (XAUUSD, XAGUSD)                                    │
│  ├── Indices (SPX500, US30, etc.)                               │
│  └── Commodities (USOIL, NATGAS)                                │
│                                                                  │
│  CCXTBroker (Crypto Exchanges)                                  │
│  ├── Binance, Coinbase, etc.                                    │
│  ├── BTC/USDT, ETH/USDT, SOL/USDT                               │
│  └── Futures & Spot markets                                     │
│                                                                  │
│  PaperBroker (Simulation)                                       │
│  └── In-memory testing                                          │
└─────────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────────┐
│                      DATA FEEDS LAYER                           │
├─────────────────────────────────────────────────────────────────┤
│  Market Data:                                                   │
│  ├── yfinance (stocks, indices, commodities)                    │
│  ├── MT5 (forex, metals)                                        │
│  └── CCXT (crypto)                                              │
│                                                                  │
│  News Feeds:                                                    │
│  ├── NewsAPI (financial news aggregator)                        │
│  ├── RSS (Reuters, Bloomberg)                                   │
│  └── GDELT (geopolitical events)                                │
│                                                                  │
│  Economic Calendar:                                             │
│  ├── MT5 Calendar API                                           │
│  └── ForexFactory (fallback)                                    │
│                                                                  │
│  Macro Data:                                                    │
│  ├── DXY (US Dollar Index)                                      │
│  └── US10Y (10-Year Treasury Yield)                             │
└─────────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────────┐
│                      LOGGING & MONITORING                       │
├─────────────────────────────────────────────────────────────────┤
│  loguru (Advanced logging)                                      │
│  ├── Console output (colored)                                   │
│  ├── File rotation (logs/apex_*.log)                            │
│  ├── WebSocket broadcasting                                     │
│  └── Structured logging with context                            │
│                                                                  │
│  APScheduler (Task scheduling)                                  │
│  ├── Training runs                                              │
│  ├── Log cleanup                                                │
│  └── Health checks                                              │
└─────────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────────┐
│                    DEPLOYMENT & INFRASTRUCTURE                  │
├─────────────────────────────────────────────────────────────────┤
│  Development:                                                   │
│  ├── Python venv (isolation)                                    │
│  ├── pip (package management)                                   │
│  └── Git (version control)                                      │
│                                                                  │
│  Production:                                                    │
│  ├── Docker + Docker Compose (optional)                         │
│  ├── systemd / Supervisor (process management)                  │
│  ├── nginx (reverse proxy, optional)                            │
│  ├── cron (scheduled tasks)                                     │
│  └── logrotate (log management)                                 │
│                                                                  │
│  Monitoring:                                                    │
│  ├── Custom watchdog (auto-restart)                             │
│  ├── Health check endpoints                                     │
│  └── Log aggregation                                            │
└─────────────────────────────────────────────────────────────────┘
`

---

## Technology Choices & Rationale

### Why LangGraph?
- **State management**: Passes BotState through agent pipeline
- **Flexibility**: Easy to add/remove agents
- **Debugging**: Clear execution flow
- **Fallback**: Can run sequentially if LangGraph unavailable

### Why FastAPI?
- **Performance**: Async/await support, fast execution
- **Modern**: Python 3.12 type hints, Pydantic validation
- **WebSocket**: Built-in support for real-time updates
- **Documentation**: Auto-generated API docs

### Why DuckDB?
- **Embedded**: No separate database server needed
- **OLAP**: Optimized for analytical queries
- **SQL**: Standard SQL interface
- **Performance**: Fast aggregations and analytics

### Why Vanilla JavaScript?
- **No dependencies**: No framework bloat
- **Fast loading**: Minimal bundle size
- **Full control**: Custom components tailored to needs
- **Easy debugging**: No framework abstractions

### Why Ollama Primary?
- **Local**: No API costs, no rate limits
- **Fine-tuned**: Trained on trading decisions
- **Fast**: 8s timeout, low latency
- **Privacy**: Data stays local

### Why 4-Tier LLM?
- **Reliability**: 99.9% uptime with fallbacks
- **Cost optimization**: Use free/cheap tiers first
- **Rate limit handling**: Auto-skip limited tiers
- **Quality**: Claude as final fallback for critical decisions

### Why MetaTrader 5?
- **Industry standard**: Most forex brokers support it
- **Rich API**: Full programmatic control
- **Reliability**: Battle-tested platform
- **Features**: Calendar, indicators, history

---

## Dependencies (requirements.txt)

`	xt
# Core Framework
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
pydantic-settings==2.1.0

# Agent Orchestration
langgraph==0.0.40
langchain-core==0.1.10

# AI/LLM
openai==1.6.1
anthropic==0.8.1
httpx==0.25.2

# Database
duckdb==0.9.2
pandas==2.1.4

# Broker Integration
MetaTrader5==5.0.45
ccxt==4.1.92

# Technical Analysis
pandas-ta==0.3.14b
ta-lib==0.4.28
numpy==1.26.2

# Data Feeds
yfinance==0.2.33
aiohttp==3.9.1
feedparser==6.0.10

# Logging & Monitoring
loguru==0.7.2
apscheduler==3.10.4

# Vector Database
chromadb==0.4.18

# Utilities
python-dotenv==1.0.0
`

---

## Browser Compatibility

### Frontend Requirements:
- **Modern browsers** (Chrome 90+, Firefox 88+, Safari 14+, Edge 90+)
- **JavaScript ES6+** support
- **WebSocket** support
- **Fetch API** support
- **LocalStorage** support
- **CSS Grid & Flexbox** support

### Tested On:
- Chrome 120+ ✓
- Firefox 121+ ✓
- Edge 120+ ✓
- Safari 17+ ✓

---

**END OF TECH STACK DOCUMENTATION**
