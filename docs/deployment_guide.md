# APEX Trading Bot — Deployment & Setup Guide

> **Last updated:** 2026-02-27
> **Tested on:** Windows 11, Python 3.12, MT5 MetaQuotes-Demo

---

## 1. Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.12 | From Microsoft Store or python.org |
| MetaTrader 5 | Latest | Windows only |
| Git | Any | For version control |
| Ollama | Latest | Optional — cloud LLM fallback works without it |

---

## 2. Initial Setup

### 2.1 Clone & Create Virtual Environment

```powershell
cd c:\Users\srika\Labs\AgenticAI\AutoTrade

python -m venv .venv
.venv\Scripts\Activate
```

### 2.2 Install All Dependencies

The `requirements.txt` covers the core bot. Some packages must be installed separately because they are Windows-only or have heavy dependencies.

**Step 1 — Core bot packages:**
```powershell
pip install -r requirements.txt
```

**Step 2 — Packages not in requirements.txt (install manually):**
```powershell
pip install MetaTrader5 pandas pandas-ta aiohttp
pip install chromadb
pip install yfinance
pip install fastapi uvicorn python-dotenv pydantic apscheduler
pip install scikit-learn skl2onnx
```

**Why separate?**
- `MetaTrader5` — Windows-only, not included in requirements.txt for cross-platform reasons
- `pandas 3.0.x` — requirements.txt pins 2.2.3 but 3.0.x works fine on Python 3.12
- `chromadb` — large install with ML deps, kept optional
- `yfinance` — needed by macro agent for DXY/US10Y data

**Fine-tuning only (install when ready to fine-tune, NOT for running the bot):**
```powershell
pip install unsloth trl transformers accelerate bitsandbytes
# or for Google Colab:
pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
```

### 2.3 Configure Environment

```powershell
copy .env.example .env
```

Edit `.env` with your values:

```bash
# App mode
APP_ENV=development          # development | paper | live

# MT5 Broker (required for live/paper forex+metals trading)
MT5_LOGIN=your_account_number
MT5_PASSWORD=your_password
MT5_SERVER=MetaQuotes-Demo   # or your broker's server name

# LLM — tiered fallback (Ollama → DeepSeek → Claude Haiku)
ANTHROPIC_API_KEY=your_key   # Claude Haiku fallback (Tier 3)
DEEPSEEK_API_KEY=your_key    # DeepSeek fallback (Tier 2)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=apex-trader     # name after fine-tuning

# Training pipeline
FRED_API_KEY=your_fred_key   # free at fred.stlouisfed.org
DUCKDB_PATH=data/apex.db
```

**Minimum required to run:** `ANTHROPIC_API_KEY` or `DEEPSEEK_API_KEY` (at least one LLM).
**For MT5 execution:** `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER` + MT5 desktop running.

---

## 3. MetaTrader 5 Setup

### 3.1 Platform Configuration

1. Install MT5 from your broker or [metatrader5.com](https://www.metatrader5.com)
2. Log in to your demo or live account
3. In MT5: **Tools → Options → Expert Advisors**
   - Check "Allow automated trading"
   - Check "Allow DLL imports"
4. Keep MT5 running in the background while APEX is running

### 3.2 Verify MT5 Connection

```powershell
# Quick connectivity test
.venv\Scripts\python.exe scripts/debug_mt5_alive.py
```

Expected output:
```
MT5 Account: 102168389
Connected! Account: 102168389 | Balance: 103007.2 GBP
XAUUSD Bid: 5262.37 Ask: 5262.67
```

### 3.3 Check Calendar API Support

```powershell
.venv\Scripts\python.exe scripts/debug_mt5_alive.py
```

The script also lists available `calendar_*` methods. If none appear, MT5 calendar data falls back to empty list (non-critical — calendar feed still works via other sources).

---

## 4. Database Initialisation

DuckDB is embedded — no server needed. The schema is created automatically on first run. To initialise manually:

```powershell
.venv\Scripts\python.exe -c "
import duckdb
con = duckdb.connect('data/apex.db')
with open('scripts/init_db.sql') as f:
    con.executescript(f.read())
con.close()
print('DB initialised')
"
```

Tables created: `ohlcv`, `executions`, `closed_trades`, `daily_kpis`, `news`, `decision_log`

---

## 5. Running the Bot

### 5.1 Development Mode (Paper Trading, Mock Data)

Safest starting point. Uses `PaperBroker` with mock prices, real LLM calls.

```powershell
cd c:\Users\srika\Labs\AgenticAI\AutoTrade
.venv\Scripts\python.exe main.py
```

Open `http://localhost:8000` → Click **START BOT** on the dashboard.

### 5.2 Monitor Mode (MT5 Connected, No Orders)

MT5 provides real prices and OHLCV. The pipeline runs fully but the execution agent logs signals without placing orders.

```powershell
APP_ENV=live .venv\Scripts\python.exe main.py --monitor
```

This is the recommended mode for initial testing. Verified working — all 8 agents run, real MT5 data, real LLM reasoning, no trades placed.

### 5.3 Live / Paper Mode (Real Orders via MT5)

```powershell
# Paper trading (uses PaperBroker regardless of APP_ENV)
APP_ENV=paper .venv\Scripts\python.exe main.py

# Live MT5 execution (real orders on MT5 demo/live account)
APP_ENV=live .venv\Scripts\python.exe main.py
```

**WARNING:** `APP_ENV=live` will place real orders on your MT5 account. Start with demo account only.

### 5.4 Auto-start Bot on Launch

```powershell
APP_ENV=live .venv\Scripts\python.exe main.py --autostart
```

---

## 6. Dashboard

Access at `http://localhost:8000` once the server is running.

| Tab | Purpose |
|---|---|
| DASHBOARD | Live equity, open positions, daily P&L |
| TRADES | Open and closed trade history |
| ANALYTICS | KPIs: win rate, Sharpe, drawdown |
| BOT LOGS | Real-time agent log stream via WebSocket |
| MLOPS | Model performance metrics |
| TRAINING | Full training pipeline (see section 7) |
| CONFIG | Runtime config override (risk, strategy params) |

---

## 7. Training Pipeline

The full training pipeline is accessible from the **TRAINING** tab in the dashboard. All parameters are configurable at runtime — no hardcoded values in scripts.

### 7.1 Configure Before Running

In the dashboard → TRAINING tab → right panel, set:
- **FRED API Key** (free at [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html))
- **Start Date** (default: 2018-01-01)
- **Base Model** (default: `unsloth/llama-3.1-8b-bnb-4bit`)
- **Ollama Model Name** (what you'll call the fine-tuned model in Ollama)

Click **Save Configuration** before running any steps.

### 7.2 Pipeline Steps (run in order)

**Step 1 — Collect Historical OHLCV** (yfinance + CCXT)
```powershell
.venv\Scripts\python.exe scripts/collect_historical_data.py
# Options:
#   --source yfinance|ccxt|all
#   --start 2020-01-01
#   --tf 1h
```
Saves to `data/raw/` and loads into DuckDB `ohlcv` table.

**Step 2 — Collect Macro Data** (FRED + CFTC COT)
```powershell
.venv\Scripts\python.exe scripts/collect_macro_data.py --fred-key YOUR_KEY
# Options:
#   --source fred|cot|all
#   --skip-db  (skip DuckDB load)
```
FRED key required for macro indicators (DXY, US10Y, VIX, CPI, Gold).
COT data (CFTC Gold futures positioning) downloads free without a key.

**Step 3 — Paper Trade to Collect Decisions**

Run the bot in paper/monitor mode. Every pipeline cycle writes to the `decision_log` table in DuckDB. Minimum 200 decisions needed before fine-tuning (synthetic seed examples fill the gap initially).

**Step 4 — Export Training Data**
```powershell
.venv\Scripts\python.exe scripts/prepare_training_data.py
# Options:
#   --include-synthetic   force include synthetic seed examples
#   --min 100             lower threshold for testing
#   --stats               print breakdown after export
```
Exports `training_data/apex_training_YYYY-MM-DD.jsonl` and `apex_training_latest.jsonl`.

**Step 5 — Fine-Tune** (requires 16GB+ VRAM or Google Colab)
```powershell
pip install unsloth trl transformers accelerate bitsandbytes
.venv\Scripts\python.exe scripts/fine_tune.py
# Options:
#   --epochs 3
#   --rank 16
#   --lr 2e-4
#   --eval-split 0.1
```
Outputs LoRA adapters + merged 16-bit model to `models/apex_trading_model`.

**Step 6 — Convert to GGUF + Load into Ollama**
```powershell
.venv\Scripts\python.exe scripts/conversion.py
```
Requires `llama.cpp` installed. Converts to `models/apex_trading_llm.gguf` and registers with Ollama as `apex-trader`.

After conversion, set in `.env`:
```bash
OLLAMA_MODEL=apex-trader
```

---

## 8. LLM Tier Configuration

The bot uses a tiered fallback — if Tier 1 is unavailable, it falls to Tier 2, then Tier 3. All tiers use identical call signatures.

| Tier | Model | Timeout | Requires |
|---|---|---|---|
| 1 | Ollama `apex-trader` (local) | 8s | Ollama running + fine-tuned model |
| 2 | DeepSeek `deepseek-chat` | 12s | `DEEPSEEK_API_KEY` in `.env` |
| 3 | Claude Haiku `claude-3-haiku-20240307` | 15s | `ANTHROPIC_API_KEY` in `.env` |
| Fallback | None — approve signals with score > 8.0 | — | Always available |

**To use Tier 1 (local Ollama):**
```powershell
# Install Ollama from https://ollama.com
ollama pull llama3.1:8b
# After fine-tuning:
ollama create apex-trader -f Modelfile
```

---

## 9. Known Issues & Fixes Applied

### 9.1 Windows Unicode Encoding (cp1252)

**Symptom:** `UnicodeEncodeError: 'charmap' codec can't encode character` in terminal output.
**Cause:** Windows console defaults to cp1252, which can't render emoji characters in log messages.
**Fix applied** in `core/logger.py`:
```python
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
```
**Alternative workaround:**
```powershell
$env:PYTHONIOENCODING = "utf-8"
.venv\Scripts\python.exe main.py
```

### 9.2 pandas Version

`pandas==2.2.3` specified in `requirements.txt` — no Python 3.12 wheel for older versions. If pip installs `pandas 3.x`, that is fine and tested working. Do not downgrade.

### 9.3 DuckDB Concurrent Connections

Never open a second `duckdb.connect()` on the same file while a write connection is open. The `DuckDBStore` uses a single-writer `asyncio.Queue` pattern. Read queries reuse the write connection.

```python
# WRONG — will raise "database is locked"
con = duckdb.connect("data/apex.db", read_only=True)

# CORRECT — use the store's execute_read() which reuses the write conn
result = store.execute_read("SELECT * FROM closed_trades LIMIT 10")
```

### 9.4 MT5 Multiple Reconnects

During the agent pipeline, `MT5Broker.connect()` is called once per symbol in the market analyst node. This is benign (MT5 SDK is idempotent on repeated `initialize()` calls) but slightly slow. Future optimisation: share a single `MT5Broker` instance via `BrokerFactory` across agents.

### 9.5 Quote Prices in Signals

When `APP_ENV=development`, the `MarketFeed` returns mock prices for signal entry/exit levels (e.g., XAUUSD at ~2320 instead of real ~5262). The broker's `place_order` fills at actual market price regardless. For accurate lot sizing in paper mode, set `APP_ENV=live` even without placing real orders (use `--monitor` flag).

---

## 10. Verified Working — Full Pipeline Test (2026-02-27)

Tested with `APP_ENV=live --monitor` against MetaQuotes-Demo account (£103,007 balance):

```
[DATA]       12 quotes loaded from MT5 | 2 news | 2 calendar events
[ANALYST]    12 symbols × 3 timeframes = 36 condition scans
             8 top signals selected (score >= 6.5)
             ReAct reasoning via DeepSeek (Ollama offline)
[SENTIMENT]  XAUUSD boosted 78% → 100% confidence
[CALENDAR]   No blackouts active
[MACRO]      DXY/yield trends checked
[RISK]       7/8 approved | UKOIL SELL rejected (score 6.5 < 7.5)
[ORCHESTRATOR] LLM final approval via DeepSeek
[EXEC]       MONITOR MODE — 7 virtual executions logged
             NATGAS BUY | USOIL BUY | XAUUSD BUY (x2) | XAGUSD BUY (x2)
```

Total pipeline time: ~90 seconds (dominated by LLM calls to cloud API).
With local Ollama running: expected ~15-20 seconds per cycle.

---

## 11. Quick Reference — Common Commands

```powershell
# Start server (development mode)
.venv\Scripts\python.exe main.py

# Start server (live MT5, monitor only — no orders)
APP_ENV=live .venv\Scripts\python.exe main.py --monitor

# Start server (live MT5, real orders)
APP_ENV=live .venv\Scripts\python.exe main.py

# Run single pipeline cycle (no API server)
.venv\Scripts\python.exe main.py --mode paper

# Test MT5 connection
.venv\Scripts\python.exe scripts/debug_mt5_alive.py

# Collect historical data
.venv\Scripts\python.exe scripts/collect_historical_data.py --source all

# Collect macro data (needs FRED key)
.venv\Scripts\python.exe scripts/collect_macro_data.py --fred-key YOUR_KEY

# Export training data
.venv\Scripts\python.exe scripts/prepare_training_data.py --include-synthetic

# Fine-tune (needs GPU)
.venv\Scripts\python.exe scripts/fine_tune.py --epochs 3

# Convert to GGUF
.venv\Scripts\python.exe scripts/conversion.py
```

---

## 12. File Structure Reference

```
AutoTrade/
├── main.py                     ← entry point (uvicorn + bot loop)
├── .env                        ← your secrets (never commit)
├── .env.example                ← template
├── requirements.txt
│
├── core/
│   ├── config.py               ← all settings (RiskConfig, TrainingConfig, etc.)
│   ├── models.py               ← Pydantic models (BotState, Trade, Signal, etc.)
│   └── logger.py               ← loguru + WebSocket sink
│
├── agents/
│   └── graph.py                ← 8-node LangGraph pipeline
│
├── brokers/
│   └── base.py                 ← MT5Broker, CCXTBroker, PaperBroker, BrokerFactory
│
├── strategies/
│   └── technical.py            ← indicators, SMC filter, position manager
│
├── data/
│   ├── market_feed.py          ← OHLCV provider
│   ├── news_feed.py            ← NewsAPI + RSS
│   └── calendar_feed.py        ← economic events
│
├── memory/
│   ├── duckdb_store.py         ← single-writer async DB layer
│   └── chroma_store.py         ← ChromaDB news RAG
│
├── llm/
│   └── client.py               ← tiered LLM fallback
│
├── api/
│   └── server.py               ← FastAPI + WebSocket + training endpoints
│
├── frontend/
│   └── trading-bot-dashboard.html
│
├── scripts/
│   ├── collect_historical_data.py
│   ├── collect_macro_data.py
│   ├── collect_sentiment_data.py
│   ├── prepare_training_data.py
│   ├── fine_tune.py
│   ├── conversion.py
│   ├── debug_mt5_alive.py
│   └── init_db.sql
│
└── data/
    ├── apex.db                 ← main DuckDB (trades, decisions, KPIs)
    ├── market_data.duckdb      ← OHLCV cache
    ├── raw/                    ← collected CSV files
    └── macro/                  ← FRED + COT CSV files
```
