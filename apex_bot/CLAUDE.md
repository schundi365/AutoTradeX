# APEX Trading Bot — Claude Code Instructions

This document is the single source of truth for building the APEX Trading Bot.
Read this entire file before writing any code. Follow it precisely.

---

## Project Goal

Build a production-ready, agentic algorithmic trading bot that:
- Uses a multi-agent LangGraph pipeline to analyse markets and execute trades
- Supports MetaTrader 5 (metals/forex), CCXT (crypto), and Paper trading
- Runs a local fine-tuned Ollama LLM as primary brain with cloud LLM fallback
- Persists all data in DuckDB (analytics) and ChromaDB (news RAG)
- Serves a glassmorphic dashboard via FastAPI + WebSocket

---

## Project Structure

Create this exact folder layout. Do not deviate from it.

```
apex_bot/
├── CLAUDE.md                        ← this file
├── main.py                          ← entry point
├── requirements.txt
├── .env.example
├── Dockerfile
├── docker-compose.yml
│
├── core/
│   ├── __init__.py
│   ├── config.py                    ← all settings from .env
│   ├── models.py                    ← all Pydantic data models
│   ├── logger.py                    ← loguru + WebSocket sink
│   └── database.py                  ← DuckDB connection + schema
│
├── agents/
│   ├── __init__.py
│   ├── graph.py                     ← LangGraph pipeline (main workflow)
│   ├── data_collector.py            ← OHLCV + news fetching
│   ├── market_analyst.py            ← technical analysis + SMC
│   ├── sentiment_agent.py           ← news NLP + ChromaDB RAG
│   ├── macro_agent.py               ← DXY + US10Y risk-on/off filter
│   ├── calendar_agent.py            ← economic event blackouts
│   ├── risk_manager.py              ← Kelly sizing + veto logic
│   ├── orchestrator.py              ← final LLM decision
│   └── execution_agent.py           ← broker order placement
│
├── brokers/
│   ├── __init__.py
│   ├── base.py                      ← BaseBroker abstract class
│   ├── mt5_broker.py                ← MetaTrader 5 implementation
│   ├── ccxt_broker.py               ← Bybit/Binance implementation
│   └── paper_broker.py              ← in-memory simulation
│
├── strategies/
│   ├── __init__.py
│   ├── technical.py                 ← indicators + signal scoring
│   ├── smc.py                       ← Smart Money Concepts (OB, FVG)
│   └── position_manager.py          ← dynamic SL/TP + trailing stops
│
├── data/
│   ├── __init__.py
│   ├── market_feed.py               ← OHLCV data provider
│   ├── news_feed.py                 ← NewsAPI + RSS + GDELT
│   ├── macro_feed.py                ← DXY + US10Y data
│   └── calendar_feed.py             ← ForexFactory / economic calendar
│
├── memory/
│   ├── __init__.py
│   ├── chroma_store.py              ← ChromaDB news embedding + retrieval
│   └── duckdb_store.py              ← trade history + OHLCV + KPIs
│
├── llm/
│   ├── __init__.py
│   └── client.py                    ← tiered LLM caller (Ollama → DeepSeek → Claude)
│
├── api/
│   ├── __init__.py
│   └── server.py                    ← FastAPI + WebSocket + static files
│
├── frontend/
│   ├── trading-bot-dashboard.html   ← glassmorphic UI (already built)
│   └── apex-api-client.js           ← WebSocket + REST wiring (already built)
│
├── scripts/
│   ├── prepare_training_data.py     ← export DuckDB trades as JSONL
│   ├── finetune.py                  ← Unsloth fine-tuning script
│   └── init_db.sql                  ← DuckDB schema creation
│
└── logs/                            ← rotating daily log files
```

---

## Technology Stack

Use exactly these libraries. Do not substitute alternatives.

```
# Core framework
langgraph==0.2.28
langchain==0.2.16

# LLM providers
anthropic>=0.34.2          # Claude fallback
httpx>=0.27.0              # Ollama HTTP calls
# deepseek uses openai-compatible API, use openai package

# Broker integrations
MetaTrader5==5.0.4424      # Windows only; mock on Linux
ccxt==4.3.91               # crypto exchanges
alpaca-py==0.30.1          # stocks (optional)

# Data & storage
duckdb==1.1.0              # analytics + trade history
chromadb==0.5.0            # vector store for news RAG
pandas==2.2.3
pandas-ta==0.3.14b         # technical indicators

# API server
fastapi==0.115.0
uvicorn==0.31.0
websockets==13.1
python-dotenv==1.0.1

# ML / fine-tuning (scripts only, not imported in bot)
# unsloth, transformers, trl — install separately when fine-tuning

# Utilities
loguru==0.7.2
aiohttp==3.10.5
feedparser==6.0.11
pydantic==2.9.0
apscheduler==3.10.4
```

---

## Environment Variables

All configuration comes from `.env`. Never hardcode values.
Create `.env.example` with these keys:

```bash
# App
APP_ENV=paper              # paper | live
LOG_LEVEL=INFO

# LLM — tiered fallback (Ollama → DeepSeek → Claude)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=apex-trader   # your fine-tuned model name
DEEPSEEK_API_KEY=
ANTHROPIC_API_KEY=
LLM_TIMEOUT_SECONDS=8      # per-tier timeout before falling back

# Brokers
MT5_LOGIN=
MT5_PASSWORD=
MT5_SERVER=MetaQuotes-Demo
EXCHANGE_ID=bybit
EXCHANGE_API_KEY=
EXCHANGE_SECRET=
EXCHANGE_SANDBOX=true

# Data feeds
NEWS_API_KEY=

# Storage
DUCKDB_PATH=./data/apex.db
CHROMA_PATH=./data/chromadb

# Risk defaults (overrideable via API)
MAX_RISK_PCT=1.5           # % per trade
MAX_DAILY_DRAWDOWN_PCT=2.0 # hard equity veto
MAX_OPEN_TRADES=10

# Notifications
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

---

## Data Models (core/models.py)

Define ALL shared models here. Every other module imports from this file.
Required models (implement all of these):

```python
# Enums
class Direction(str, Enum): BUY, SELL
class TradeStatus(str, Enum): PENDING, OPEN, CLOSED, FAILED
class AssetClass(str, Enum): METAL, COMMODITY, FOREX, STOCK, CRYPTO
class MarketRegime(str, Enum): STRONG_TREND, WEAK_TREND, RANGING, HIGH_VOLATILE, LOW_VOLATILE, BREAKOUT
class NewsImpact(str, Enum): HIGH, MEDIUM, LOW
class BrokerName(str, Enum): MT5, CCXT, PAPER

# Core data models
class Quote(BaseModel): symbol, bid, ask, spread, timestamp
class OHLCV(BaseModel): symbol, timeframe, timestamp, open, high, low, close, volume
class TradingSignal(BaseModel): id, symbol, asset_class, direction, score (0-10),
    confidence (0-1), strategy, timeframe, entry_price, stop_loss, take_profit,
    risk_reward, reasoning, metadata
class Trade(BaseModel): id, broker, symbol, direction, lot_size, entry_price,
    stop_loss, take_profit, status, pnl, strategy, broker_order_id, open_time, close_time
class NewsItem(BaseModel): id, title, summary, source, url, published,
    symbols, sentiment (-1 to +1), impact, processed
class CalendarEvent(BaseModel): id, title, currency, impact, scheduled,
    previous, forecast, actual, released
class MacroSnapshot(BaseModel): timestamp, dxy_value, dxy_change_pct,
    us10y_yield, us10y_change_bps, risk_regime ("RISK_ON" | "RISK_OFF" | "NEUTRAL")
class MarketConditions(BaseModel): symbol, timeframe, regime, adx, rsi,
    atr, atr_pct, momentum, volume_ratio, bb_width, risk_multiplier
class ExecutionRecord(BaseModel): full audit trail per trade — see below
class BotState(BaseModel): LangGraph state passed between all agents
```

`BotState` must contain:
```python
class BotState(BaseModel):
    # Data layer
    quotes: dict[str, Quote]
    ohlcv_cache: dict[str, list[OHLCV]]
    news_items: list[NewsItem]
    calendar_events: list[CalendarEvent]
    macro: Optional[MacroSnapshot]
    # Agent outputs
    pending_signals: list[TradingSignal]
    approved_signals: list[TradingSignal]
    open_trades: list[Trade]
    # Control flags
    is_news_blackout: bool
    macro_regime: str           # "RISK_ON" | "RISK_OFF" | "NEUTRAL"
    market_regime: str
    cycle_number: int
    messages: list[AgentMessage]
```

---

## LLM Client (llm/client.py)

This is critical. Implement a tiered fallback that never blocks the pipeline.

```
Tier 1: Local Ollama (apex-trader fine-tuned model)
  → timeout: LLM_TIMEOUT_SECONDS (default 8s)
  → if unavailable or timeout: fall to Tier 2

Tier 2: DeepSeek API (openai-compatible)
  → timeout: 12s
  → if unavailable or timeout: fall to Tier 3

Tier 3: Claude Haiku via Anthropic SDK
  → timeout: 15s
  → if all tiers fail: return None, log error, pipeline continues
```

Rules:
- NEVER let an LLM failure crash the pipeline
- Log which tier was used for every call
- If all tiers fail, agents must handle `None` response gracefully
- Use `asyncio.wait_for()` for timeouts, not `httpx` timeouts alone
- Keep call signatures identical across tiers so agents don't know which fired

Ollama call format:
```python
POST http://localhost:11434/api/generate
{
  "model": "apex-trader",
  "prompt": f"{system}\n\n{user}",
  "stream": false,
  "options": {"temperature": 0.1, "num_predict": max_tokens}
}
```

---

## Agent Pipeline (agents/graph.py)

Build a LangGraph `StateGraph` with this exact node order:

```
START
  → data_collector       # fetch quotes, OHLCV, news, calendar, macro
  → market_analyst       # technical signals + SMC confluence check
  → sentiment_agent      # news NLP + ChromaDB RAG retrieval
  → macro_agent          # DXY/US10Y risk-on/off filter — can veto all signals
  → calendar_agent       # news blackout enforcement — can veto all signals
  → risk_manager         # Kelly sizing + correlation filter + 2% daily veto
  → orchestrator         # LLM final review (uses tiered LLM client)
  → execution_agent      # place orders via broker, write to DuckDB + ChromaDB
END
```

Each node receives `BotState`, modifies it, returns it. No node has side effects
outside of its designated responsibilities (e.g. only execution_agent writes trades).

Include a sequential fallback `run_pipeline()` async function for when LangGraph
is not installed. Every agent node must be importable standalone.

---

## Agent Specifications

### data_collector
- Fetch live quotes for all configured symbols in parallel (`asyncio.gather`)
- Fetch OHLCV for each symbol × each timeframe
- Fetch latest 50 news items from news_feed
- Fetch upcoming 48h calendar events from calendar_feed
- Fetch MacroSnapshot (DXY + US10Y) from macro_feed
- Cache results in BotState

### market_analyst
- Run `TechnicalAnalyser.analyse()` for each symbol
- Run `SMCAnalyser.check_confluence()` as a filter on technical signals
  - SMC is a FILTER only, not a signal generator
  - A signal passes SMC check if price is near an unmitigated Order Block OR
    there is an unfilled Fair Value Gap within 1 ATR of entry
  - If no SMC confluence: reduce signal score by 1.5 (do not discard)
- Use LLM (via tiered client) to generate reasoning text for top signals only
- Apply ReAct pattern: Thought → Action → Observation → Conclusion

### sentiment_agent
- For each pending signal, query ChromaDB for the 5 most similar past news events
- Combine retrieved context with current news to classify sentiment
- Boost or reduce signal confidence based on sentiment alignment
- Store new news embeddings in ChromaDB for future RAG

### macro_agent
- Fetch DXY and US10Y data
- Classify macro regime:
  - RISK_OFF: DXY rising > 0.3% AND/OR US10Y rising > 5bps → reduce all position sizes by 40%, veto BUY signals on Gold
  - RISK_ON: DXY falling AND US10Y falling → allow full sizing, Gold BUY signals get +0.5 score boost
  - NEUTRAL: no adjustment
- Set `BotState.macro_regime`
- This agent can set `approved_signals = []` if macro is severely adverse (DXY > +0.8% in one session)

### calendar_agent
- Check all events within configurable blackout windows:
  - HIGH impact: block 15min before, 30min after
  - MEDIUM impact: block 5min before, 15min after
- If any blackout active: set `is_news_blackout = True`, clear `pending_signals`
- Also tighten SL multiplier on signals when high-impact event is within 60min

### risk_manager
- Apply Kelly Criterion for position sizing:
  ```
  kelly_fraction = win_rate - ((1 - win_rate) / avg_rr)
  use half-Kelly: kelly_fraction * 0.5
  lot_size = (account_balance * kelly_fraction * risk_multiplier) / sl_distance
  ```
- Hard veto conditions (set `approved_signals = []`):
  - Daily drawdown has exceeded `MAX_DAILY_DRAWDOWN_PCT`
  - Open trades >= `MAX_OPEN_TRADES`
  - Margin level below 200%
- Correlation filter: reject signals where same direction already held on 3+ correlated pairs
- Apply `MarketConditions.risk_multiplier` from AdaptiveRiskManager

### orchestrator
- Receives `approved_signals` from risk_manager
- For each signal, call LLM with full context (signal details + macro + news summary)
- LLM must return structured JSON: `{"symbol": "XAUUSD", "decision": "APPROVE", "reason": "..."}`
- If LLM returns None (all tiers failed): approve signals with score > 8.0, reject rest
- Log every decision with reasoning

### execution_agent
- For each orchestrator-approved signal: place order via appropriate broker
- Build `ExecutionRecord` capturing: fill price, slippage, latency_ms, lot_size,
  risk_pct, risk_amount, market_regime, atr, adx, rsi, broker_order_id, timestamp
- Write `ExecutionRecord` to DuckDB `executions` table
- Store trade context (signal reasoning + news) as ChromaDB embedding for future RAG
- Trigger PositionManager to begin tracking the new trade

---

## Smart Money Concepts (strategies/smc.py)

Implement as a confluence filter, not a signal generator.

```python
class SMCAnalyser:
    def check_confluence(self, signal: TradingSignal, df: pd.DataFrame) -> SMCResult:
        """
        Returns SMCResult with:
          - has_confluence: bool
          - confluence_type: "ORDER_BLOCK" | "FVG" | "BOTH" | "NONE"
          - nearest_ob: Optional[OrderBlock]
          - nearest_fvg: Optional[FairValueGap]
          - score_adjustment: float  # -1.5 to +1.0
        """
```

Order Block detection rules:
- A bullish OB is the last bearish candle before a strong bullish move (3+ ATR move)
- A bearish OB is the last bullish candle before a strong bearish move
- An OB is "unmitigated" if price has not returned to its range since formation
- Only consider OBs formed within the last 50 bars
- OB zone = the full high-low range of that candle

Fair Value Gap detection rules:
- A bullish FVG: candle[i].low > candle[i-2].high (gap up, unfilled space)
- A bearish FVG: candle[i].high < candle[i-2].low (gap down, unfilled space)
- FVG is "unfilled" if current price has not traded through the gap
- Only consider FVGs within the last 30 bars

Score adjustment:
- Signal near unmitigated OB AND unfilled FVG: +1.0
- Signal near unmitigated OB only: +0.5
- Signal near unfilled FVG only: +0.3
- No SMC confluence: -1.5

---

## Database Layer (memory/duckdb_store.py)

Use DuckDB exclusively. No PostgreSQL, no SQLite.

### Single-Writer Pattern (critical)
```python
class DuckDBStore:
    """
    All writes go through a single asyncio.Queue.
    Reads use read-only connections (concurrent safe).
    """
    def __init__(self, db_path: str):
        self._write_conn = duckdb.connect(db_path)
        self._write_queue = asyncio.Queue()
        self._writer_task = None

    async def start(self):
        self._writer_task = asyncio.create_task(self._writer_loop())

    async def _writer_loop(self):
        while True:
            sql, params, future = await self._write_queue.get()
            try:
                result = self._write_conn.execute(sql, params)
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)

    async def execute_write(self, sql: str, params: list = []):
        future = asyncio.get_event_loop().create_future()
        await self._write_queue.put((sql, params, future))
        return await future

    def execute_read(self, sql: str, params: list = []):
        # Read-only connection — safe to create per query
        con = duckdb.connect(self._db_path, read_only=True)
        result = con.execute(sql, params).fetchall()
        con.close()
        return result
```

### Required Tables (create in scripts/init_db.sql)
```sql
-- OHLCV market data
CREATE TABLE IF NOT EXISTS ohlcv (
    symbol VARCHAR, timeframe VARCHAR, timestamp TIMESTAMP,
    open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE,
    PRIMARY KEY (symbol, timeframe, timestamp)
);

-- All trade executions (immutable audit log)
CREATE TABLE IF NOT EXISTS executions (
    execution_id VARCHAR PRIMARY KEY,
    signal_id VARCHAR, symbol VARCHAR, direction VARCHAR,
    strategy VARCHAR, timeframe VARCHAR,
    signal_price DOUBLE, execution_price DOUBLE, slippage DOUBLE,
    stop_loss DOUBLE, take_profit DOUBLE,
    lot_size DOUBLE, account_balance DOUBLE,
    risk_amount DOUBLE, risk_pct DOUBLE,
    market_regime VARCHAR, atr DOUBLE, adx DOUBLE, rsi DOUBLE,
    broker_order_id VARCHAR, broker_name VARCHAR,
    execution_time TIMESTAMP, order_latency_ms INTEGER,
    status VARCHAR, notes VARCHAR
);

-- Closed trade summary (for training data + analytics)
CREATE TABLE IF NOT EXISTS closed_trades (
    trade_id VARCHAR PRIMARY KEY,
    symbol VARCHAR, direction VARCHAR, strategy VARCHAR,
    entry_price DOUBLE, close_price DOUBLE, final_pnl DOUBLE,
    lot_size DOUBLE, risk_pct DOUBLE,
    open_time TIMESTAMP, close_time TIMESTAMP,
    duration_minutes INTEGER, close_reason VARCHAR,
    sl_tightened_count INTEGER, tp_extended_count INTEGER,
    trailing_active BOOLEAN, max_adverse_excursion DOUBLE,
    max_favorable_excursion DOUBLE
);

-- Daily KPI snapshots for dashboard
CREATE TABLE IF NOT EXISTS daily_kpis (
    date DATE PRIMARY KEY,
    total_pnl DOUBLE, daily_pnl DOUBLE, win_rate DOUBLE,
    total_trades INTEGER, profit_factor DOUBLE,
    sharpe_ratio DOUBLE, max_drawdown DOUBLE,
    account_balance DOUBLE
);

-- News items (deduplicated)
CREATE TABLE IF NOT EXISTS news (
    id VARCHAR PRIMARY KEY, title VARCHAR, source VARCHAR,
    published TIMESTAMP, sentiment DOUBLE, impact VARCHAR,
    symbols VARCHAR, processed BOOLEAN
);
```

---

## ChromaDB (memory/chroma_store.py)

Use ChromaDB for news RAG only. Keep it simple.

```python
class ChromaStore:
    def __init__(self, path: str):
        import chromadb
        self.client = chromadb.PersistentClient(path=path)
        self.news_collection = self.client.get_or_create_collection(
            name="apex_news",
            metadata={"hnsw:space": "cosine"}
        )
        self.trade_collection = self.client.get_or_create_collection(
            name="apex_trade_context"
        )

    def store_news(self, item: NewsItem):
        """Embed and store a news item."""

    def retrieve_similar_news(self, query_text: str, n=5) -> list[NewsItem]:
        """Find the 5 most similar past news events for RAG context."""

    def store_trade_context(self, trade: Trade, reasoning: str, news_summary: str):
        """Store the full context of a trade decision for future learning."""

    def retrieve_similar_trades(self, signal: TradingSignal, n=3) -> list[dict]:
        """Find similar past trade setups and their outcomes."""
```

Use the default embedding function (sentence-transformers). Do not call any LLM API for embeddings.

---

## Position Manager (strategies/position_manager.py)

Real-time position management loop. Polls every 15 seconds.

Implement these 6 steps per position per cycle:

1. **Verify** — call `broker.get_open_trades()`, confirm position still exists. If not found → go to step 6.
2. **Refresh** — fetch fresh OHLCV bars, recalculate all indicators via `AdaptiveRiskManager`
3. **Dynamic SL** — tighten stop-loss if any trigger fires:
   - RSI crosses back through 50 against trade direction
   - MACD histogram flips against trade direction
   - Price closes back through EMA20 against trade direction
   - ADX drops below 20 when entry ADX was above 25
4. **Dynamic TP** — extend take-profit if trend accelerates:
   - ADX rising more than 5 points since entry
   - Momentum (ROC) surging in trade direction > 0.5%
   - Volume surge > 2x average
   - Price already hit original TP (extend by 1.5x ATR)
5. **Trailing Stop** — activate after 1 ATR profit:
   - Default mode: ATR trailing (trail 1.5 ATR from peak price)
   - Breakeven first: move SL to entry + 0.1 ATR once 1 ATR in profit
   - Then: trail 1.5 ATR below peak (BUY) or above trough (SELL)
6. **Cleanup** — if position closed externally (SL/TP hit):
   - Fetch close price from broker
   - Calculate final P&L
   - Write to DuckDB `closed_trades` table
   - Store trade outcome in ChromaDB for future RAG
   - Log full management history (SL tightenings, TP extensions, trailing events)
   - Remove from PositionTracker

SL and TP modifications must only move in the favourable direction:
- BUY: SL can only move up, TP can only move up
- SELL: SL can only move down, TP can only move down

---

## Macro Agent (agents/macro_agent.py)

This is the global risk-on/risk-off filter. Build it as a standalone agent node.

```python
async def macro_agent_node(state: BotState) -> BotState:
    """
    Fetches DXY and US10Y data.
    Classifies macro regime.
    Applies regime rules to signals.
    """
```

DXY and US10Y data sources (try in order):
1. `yfinance`: `yf.download("DX-Y.NYB")` for DXY, `yf.download("^TNX")` for US10Y
2. Alpha Vantage API (if ALPHA_VANTAGE_KEY set)
3. Mock data if both unavailable (log a warning)

Macro regime rules:
```
RISK_OFF conditions (any one triggers):
  - DXY day change > +0.3%
  - US10Y day change > +5 basis points
  Effects:
  - Reduce ALL lot sizes by 40%
  - Veto all XAUUSD BUY signals (Gold falls when USD rises)
  - Add "MACRO_RISK_OFF" to signal reasoning

RISK_ON conditions (both must be true):
  - DXY day change < -0.2%
  - US10Y day change < -3 basis points
  Effects:
  - XAUUSD BUY signals get +0.5 score boost
  - Allow standard sizing

SEVERE RISK_OFF (hard veto):
  - DXY day change > +0.8% in single session
  Effects:
  - Set approved_signals = [] (no trades at all)
  - Log reason clearly
```

---

## Fine-Tuning Pipeline (scripts/)

### scripts/prepare_training_data.py
- Query DuckDB `closed_trades` table
- For each closed trade, generate a training example:
  - Input: market conditions at entry (indicators, macro, news summary)
  - Output: structured decision with reasoning and outcome
- Format as JSONL using this template:
  ```json
  {
    "instruction": "Analyse this trading setup and make a decision.",
    "input": "..market conditions..",
    "output": "DECISION: BUY\nCONFIDENCE: 0.78\nREASONING:\n1. ...\nENTRY: ..\nSTOP_LOSS: ..\nTAKE_PROFIT: ..\nRISK_REWARD: 2.5:1"
  }
  ```
- Minimum 200 examples before fine-tuning. Log a warning if fewer.
- Save to `training_data/apex_training_YYYY-MM-DD.jsonl`

### scripts/finetune.py
- Use Unsloth + QLoRA (4-bit quantization)
- Base model: `unsloth/llama-3.1-8b-bnb-4bit`
- LoRA rank: 16
- Epochs: 3
- After training: convert to GGUF (q4_k_m quantization)
- Output: `models/apex_trading_model.gguf`
- Print instructions for loading into Ollama via Modelfile

---

## API Server (api/server.py)

FastAPI with these endpoints:

```
GET  /                     → serve frontend/trading-bot-dashboard.html
GET  /apex-api-client.js   → serve frontend JS
GET  /api/status           → bot health, account info, connected brokers
GET  /api/trades/open      → open positions with live P&L
GET  /api/trades/history   → closed trades from DuckDB (paginated)
GET  /api/analytics        → KPIs from DuckDB daily_kpis table
GET  /api/news             → latest news from news_feed
GET  /api/calendar         → upcoming events from calendar_feed
GET  /api/macro            → current DXY, US10Y, macro regime
GET  /api/config           → current bot configuration
POST /api/config           → update runtime configuration
POST /api/bot/start        → start the agent pipeline loop
POST /api/bot/stop         → stop the agent pipeline loop
WS   /ws                   → real-time log stream + state updates
```

WebSocket must broadcast:
- Every log line (type: "log") with fields: time, level, msg, agent
- State updates (type: "state_update") every pipeline cycle: open_trades count,
  pending signals, macro regime, is_news_blackout

---

## Logging Rules

Use `loguru` throughout. Every log line must include the agent name.

Log levels:
- `INFO` — normal operations, cycle starts, data fetched
- `SUCCESS` — trade executed, signal approved
- `WARNING` — fallback triggered, signal rejected, blackout active
- `ERROR` — broker failure, LLM all tiers failed, DB write error

Special prefixes that the frontend uses to colour log lines:
- Lines starting with `SIGNAL` → amber in frontend
- Lines starting with `TRADE` → green in frontend
- Lines starting with `🤖`, `🧠`, or `🔮` → purple (AI) in frontend
- Lines starting with `⚠` → red in frontend

Never log sensitive data (passwords, API keys, account numbers).

---

## Error Handling Rules

Apply these rules everywhere, no exceptions:

1. **Broker calls** — always wrap in try/except, never crash the pipeline
2. **LLM calls** — use tiered fallback (llm/client.py), handle None return
3. **DuckDB writes** — go through write queue, log failures but don't crash
4. **Data feeds** — fall back to mock data if real feed unavailable (paper mode)
5. **Agent nodes** — catch all exceptions, log them, return unchanged state
6. **Position manager** — if broker verify call fails, assume position open (safe default)

Pattern to use everywhere:
```python
try:
    result = await some_operation()
except Exception as e:
    log.error("Operation failed for {}: {}", context, e)
    return safe_default
```

---

## Implementation Order

Build in this sequence. Each phase must be complete before the next.

### Phase 1 — Foundation
1. `core/models.py` — all Pydantic models
2. `core/config.py` — settings from .env
3. `core/logger.py` — loguru setup
4. `llm/client.py` — tiered LLM caller
5. `scripts/init_db.sql` — DuckDB schema
6. `memory/duckdb_store.py` — single-writer DB layer

### Phase 2 — Brokers & Data
7. `brokers/base.py` — BaseBroker abstract class
8. `brokers/paper_broker.py` — in-memory simulation (test with this first)
9. `brokers/mt5_broker.py` — MT5 implementation
10. `brokers/ccxt_broker.py` — CCXT implementation
11. `data/market_feed.py` — OHLCV provider
12. `data/news_feed.py` — NewsAPI + RSS
13. `data/macro_feed.py` — DXY + US10Y
14. `data/calendar_feed.py` — economic events

### Phase 3 — Strategies
15. `strategies/technical.py` — indicators + scoring
16. `strategies/smc.py` — SMC confluence filter
17. `strategies/position_manager.py` — real-time trade management

### Phase 4 — Agents
18. `memory/chroma_store.py` — ChromaDB RAG
19. `agents/data_collector.py`
20. `agents/market_analyst.py`
21. `agents/sentiment_agent.py`
22. `agents/macro_agent.py`
23. `agents/calendar_agent.py`
24. `agents/risk_manager.py`
25. `agents/orchestrator.py`
26. `agents/execution_agent.py`
27. `agents/graph.py` — wire everything into LangGraph

### Phase 5 — API & Integration
28. `api/server.py` — FastAPI + WebSocket
29. `main.py` — entry point
30. `Dockerfile` + `docker-compose.yml`

### Phase 6 — Fine-Tuning Pipeline
31. `scripts/prepare_training_data.py`
32. `scripts/finetune.py`

---

## Testing Approach

Always start in paper mode:
```bash
APP_ENV=paper python main.py
```

Paper mode rules:
- `PaperBroker` is always used regardless of other broker config
- All data feeds fall back to mock data if real APIs unavailable
- LLM still runs (real API calls) but no real orders are placed
- DuckDB writes are real (you accumulate training data in paper mode)
- Run paper mode for minimum 2 weeks before considering live

Verify the pipeline works by checking:
- Logs show all 7 agents running each cycle
- DuckDB `executions` table is being written to
- ChromaDB is accumulating news embeddings
- WebSocket delivers log lines to the dashboard in real time
- Position manager loop is running every 15 seconds

---

## Key Decisions Summary

| Decision | Choice | Reason |
|---|---|---|
| Primary LLM | Ollama (fine-tuned) | Free, fast, private, no latency |
| LLM fallback chain | Ollama → DeepSeek → Claude Haiku | Reliability + cost hierarchy |
| Analytics DB | DuckDB | Embedded, columnar, fast for OHLCV queries |
| Vector store | ChromaDB | Local, simple, good for news RAG |
| SMC role | Confluence filter only | Too subjective to be primary signal |
| Position sizing | Kelly Criterion (half) | Mathematically optimal, prevents over-sizing |
| Fine-tuning | Unsloth + QLoRA + GGUF | Low VRAM, fast, Ollama-compatible output |
| Training data source | DuckDB closed_trades | Your own real trade outcomes |
| Training timing | After 200+ real/paper trades | Prevents overfitting on sparse data |
| Write safety | Single asyncio writer for DuckDB | Prevents concurrent write lock errors |
