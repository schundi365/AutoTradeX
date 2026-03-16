# APEX Bot - Complete Module Dependency Map

## Visual Dependency Graph

`
┌─────────────────────────────────────────────────────────────────┐
│                           main.py                               │
│                        (Entry Point)                            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│                        api/server.py                            │
│                      (FastAPI Server)                           │
└─┬───────────────────┬─────────────────┬────────────────────────┘
  │                   │                 │
  │                   │                 └──→ utils/orchestrator.py
  │                   │                 └──→ utils/trainer.py
  │                   │
  │                   └──→ agents/graph.py (Agent Pipeline)
  │                         │
  │                         ├──→ agents/macro_agent.py
  │                         ├──→ agents/memory.py
  │                         │
  │                         ├──→ strategies/technical.py
  │                         │     └──→ pandas-ta, ta-lib
  │                         │
  │                         ├──→ data/market_feed.py
  │                         │     ├──→ data/news_feed.py
  │                         │     └──→ data/calendar_feed.py
  │                         │
  │                         ├──→ llm/client.py
  │                         │     ├──→ Ollama (Tier 1)
  │                         │     ├──→ Groq (Tier 2)
  │                         │     ├──→ DeepSeek (Tier 3)
  │                         │     └──→ Claude (Tier 4)
  │                         │
  │                         └──→ memory/duckdb_store.py
  │                               └──→ DuckDB
  │
  ├──→ brokers/base.py
  │     ├──→ MT5Broker (MetaTrader5)
  │     ├──→ CCXTBroker (ccxt)
  │     └──→ PaperBroker (in-memory)
  │
  ├──→ data/storage.py
  │     └──→ DuckDB (market_data.duckdb)
  │
  └──→ core/
        ├──→ config.py (Settings, .env)
        ├──→ logger.py (loguru + WebSocket)
        └──→ models.py (Pydantic models)
`

---

## Detailed Module Dependencies

### 1. main.py (Entry Point)
**Imports:**
- pi.server → FastAPI app
- core.config → settings
- core.logger → setup_logging

**Purpose:** Starts the FastAPI server with uvicorn

**Dependencies:**
`
main.py
  └── api/server.py
      └── (see api/server.py section)
`

---

### 2. api/server.py (API Layer)
**Imports:**
`python
# Core
from core.config import settings
from core.logger import setup_logging, register_ws_client, get_agent_logger
from core.models import BotState, Trade, AccountInfo, TradeStatus

# Agents
from agents.graph import run_agent_pipeline, build_agent_graph

# Brokers
from brokers.base import BrokerFactory, BrokerName

# Data
from data.storage import storage
from data.market_feed import NewsFeed, CalendarFeed

# Memory
from memory.duckdb_store import DuckDBStore

# Utils
from utils.orchestrator import orchestrator
from utils.trainer import trainer

# External
from fastapi import FastAPI, WebSocket, HTTPException
from pydantic import BaseModel
`

**Dependency Tree:**
`
api/server.py
  ├── core/config.py
  ├── core/logger.py
  ├── core/models.py
  ├── agents/graph.py
  │   └── (see agents/graph.py section)
  ├── brokers/base.py
  │   └── (see brokers/base.py section)
  ├── data/storage.py
  ├── data/market_feed.py
  ├── memory/duckdb_store.py
  ├── utils/orchestrator.py
  └── utils/trainer.py
`

---

### 3. agents/graph.py (Agent Pipeline)
**Imports:**
`python
# Core
from core.models import BotState, TradingSignal, Direction, NewsImpact, AgentMessage
from core.config import settings, REGIME_SL_MULTIPLIERS, REGIME_TP_MULTIPLIERS
from core.logger import get_agent_logger

# LLM
from llm.client import call_llm

# Memory
from memory.duckdb_store import DuckDBStore

# Strategies
from strategies.technical import TechnicalAnalyser, _point_value

# Brokers
from brokers.base import BrokerFactory, BrokerName

# Data
from data.market_feed import MarketFeed, NewsFeed, CalendarFeed

# Agents
from agents.macro_agent import MacroAgent
from agents.memory import memory

# External
from langgraph.graph import StateGraph, START, END
`

**Dependency Tree:**
`
agents/graph.py
  ├── core/models.py
  ├── core/config.py
  ├── core/logger.py
  ├── llm/client.py
  │   ├── httpx (Ollama)
  │   ├── openai (Groq, DeepSeek)
  │   └── anthropic (Claude)
  ├── memory/duckdb_store.py
  │   └── duckdb
  ├── strategies/technical.py
  │   ├── pandas
  │   ├── pandas-ta
  │   └── ta-lib
  ├── brokers/base.py
  │   ├── MetaTrader5
  │   └── ccxt
  ├── data/market_feed.py
  │   ├── aiohttp
  │   ├── yfinance
  │   └── feedparser
  ├── agents/macro_agent.py
  │   └── yfinance
  └── agents/memory.py
      └── chromadb
`

---

### 4. brokers/base.py (Broker Layer)
**Imports:**
`python
# Core
from core.models import Trade, TradeStatus, Direction, OrderType, AccountInfo, Quote
from core.logger import get_agent_logger

# External
import MetaTrader5 as mt5  # MT5Broker
import ccxt.async_support as ccxt  # CCXTBroker
`

**Dependency Tree:**
`
brokers/base.py
  ├── core/models.py
  ├── core/logger.py
  ├── MetaTrader5 (Windows only)
  └── ccxt (crypto exchanges)
`

**No internal dependencies** - This is a leaf module

---

### 5. llm/client.py (LLM Layer)
**Imports:**
`python
# Core
from core.config import settings

# External
import httpx  # Ollama
from openai import AsyncOpenAI  # Groq, DeepSeek
from anthropic import AsyncAnthropic  # Claude
`

**Dependency Tree:**
`
llm/client.py
  ├── core/config.py
  ├── httpx (Ollama HTTP client)
  ├── openai (Groq/DeepSeek SDK)
  └── anthropic (Claude SDK)
`

**No internal dependencies** - This is a leaf module

---

### 6. memory/duckdb_store.py (Database Layer)
**Imports:**
`python
# External
import duckdb
import asyncio
from loguru import logger
`

**Dependency Tree:**
`
memory/duckdb_store.py
  ├── duckdb
  ├── asyncio (Python stdlib)
  └── loguru
`

**No internal dependencies** - This is a leaf module

---

### 7. data/storage.py (Storage Layer)
**Imports:**
`python
# Core
from core.logger import get_agent_logger

# External
import duckdb
import pandas as pd
import threading
`

**Dependency Tree:**
`
data/storage.py
  ├── core/logger.py
  ├── duckdb
  ├── pandas
  └── threading (Python stdlib)
`

---

### 8. data/market_feed.py (Data Feeds)
**Imports:**
`python
# Core
from core.models import Quote, NewsItem, CalendarEvent, NewsImpact
from core.config import settings
from core.logger import get_agent_logger

# Brokers
from brokers.base import BrokerFactory, BrokerName

# Data
from data.storage import storage

# External
import aiohttp
import feedparser
import yfinance as yf
`

**Dependency Tree:**
`
data/market_feed.py
  ├── core/models.py
  ├── core/config.py
  ├── core/logger.py
  ├── brokers/base.py
  ├── data/storage.py
  ├── aiohttp (HTTP client)
  ├── feedparser (RSS)
  └── yfinance (market data)
`

---

### 9. strategies/technical.py (Technical Analysis)
**Imports:**
`python
# Core
from core.models import TradingSignal, Direction, SignalStrength
from core.logger import get_agent_logger

# Data
from data.market_feed import MarketFeed

# External
import pandas as pd
import pandas_ta as ta
import talib  # Optional
import numpy as np
`

**Dependency Tree:**
`
strategies/technical.py
  ├── core/models.py
  ├── core/logger.py
  ├── data/market_feed.py
  ├── pandas
  ├── pandas-ta
  ├── ta-lib (optional)
  └── numpy
`

---

### 10. agents/macro_agent.py (Macro Data)
**Imports:**
`python
# Core
from core.logger import get_agent_logger
from core.models import Direction

# External
import yfinance as yf
import asyncio
`

**Dependency Tree:**
`
agents/macro_agent.py
  ├── core/logger.py
  ├── core/models.py
  └── yfinance
`

**No internal dependencies** - This is a leaf module

---

### 11. agents/memory.py (Long-term Memory)
**Imports:**
`python
# Core
from core.logger import get_agent_logger

# External
import chromadb
from chromadb.utils import embedding_functions
`

**Dependency Tree:**
`
agents/memory.py
  ├── core/logger.py
  └── chromadb
`

**No internal dependencies** - This is a leaf module

---

### 12. core/config.py (Configuration)
**Imports:**
`python
# External
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
`

**Dependency Tree:**
`
core/config.py
  ├── pydantic
  ├── pydantic-settings
  └── python-dotenv
`

**No internal dependencies** - This is a root module

---

### 13. core/logger.py (Logging)
**Imports:**
`python
# Core
from core.config import settings

# External
from loguru import logger
`

**Dependency Tree:**
`
core/logger.py
  ├── core/config.py
  └── loguru
`

---

### 14. core/models.py (Data Models)
**Imports:**
`python
# External
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime
`

**Dependency Tree:**
`
core/models.py
  ├── pydantic
  ├── enum (Python stdlib)
  └── datetime (Python stdlib)
`

**No dependencies** - This is a root module

---

## Circular Dependency Prevention

### Safe Import Order:
1. **core/models.py** (no dependencies)
2. **core/config.py** (no internal dependencies)
3. **core/logger.py** (depends on config)
4. **Leaf modules** (brokers, llm, memory, agents/macro_agent, agents/memory)
5. **Mid-level modules** (data/storage, strategies/technical)
6. **High-level modules** (data/market_feed, agents/graph)
7. **Top-level modules** (api/server, main)

### Lazy Imports Used:
`python
# In agents/graph.py
async def data_collector_node(state: BotState):
    # Import inside function to avoid circular dependency
    from data.market_feed import MarketFeed
    from data.news_feed import NewsFeed
    from data.calendar_feed import CalendarFeed
    ...
`

---

## External Package Dependencies

### Critical Packages:
`
langgraph==0.0.40          # Agent orchestration
fastapi==0.104.1           # API server
duckdb==0.9.2              # Database
MetaTrader5==5.0.45        # Broker (Windows)
ccxt==4.1.92               # Crypto exchanges
pandas==2.1.4              # Data manipulation
pandas-ta==0.3.14b         # Technical indicators
yfinance==0.2.33           # Market data
openai==1.6.1              # Groq/DeepSeek
anthropic==0.8.1           # Claude
chromadb==0.4.18           # Vector DB
loguru==0.7.2              # Logging
aiohttp==3.9.1             # Async HTTP
pydantic==2.5.0            # Validation
`

### Optional Packages:
`
ta-lib==0.4.28             # Alternative technical indicators
docker                     # Containerization
nginx                      # Reverse proxy
`

---

## Import Hierarchy Visualization

`
Level 0 (No dependencies):
  └── core/models.py

Level 1 (Depends on Level 0):
  ├── core/config.py
  └── External packages only:
      ├── brokers/base.py
      ├── llm/client.py
      ├── memory/duckdb_store.py
      ├── agents/macro_agent.py
      └── agents/memory.py

Level 2 (Depends on Level 0-1):
  ├── core/logger.py
  ├── data/storage.py
  └── strategies/technical.py (needs data/market_feed)

Level 3 (Depends on Level 0-2):
  └── data/market_feed.py

Level 4 (Depends on Level 0-3):
  └── agents/graph.py

Level 5 (Depends on Level 0-4):
  ├── api/server.py
  └── utils/orchestrator.py

Level 6 (Entry point):
  └── main.py
`

---

## Dependency Injection Points

### 1. Settings (core/config.py)
Injected everywhere via:
`python
from core.config import settings
`

### 2. Logger (core/logger.py)
Injected everywhere via:
`python
from core.logger import get_agent_logger
log = get_agent_logger("MODULE_NAME")
`

### 3. BrokerFactory (brokers/base.py)
Created on-demand:
`python
from brokers.base import BrokerFactory
factory = BrokerFactory(settings)
broker = factory.get("MT5")
`

### 4. DuckDBStore (memory/duckdb_store.py)
Created per-use:
`python
from memory.duckdb_store import DuckDBStore
store = DuckDBStore(settings.training.duckdb_path)
await store.start()
`

### 5. Storage Singleton (data/storage.py)
Global instance:
`python
from data.storage import storage
storage.store_trade(trade)
`

---

## Testing Dependencies

### Mock Dependencies:
- **Brokers**: PaperBroker (in-memory simulation)
- **LLM**: Mock responses when all tiers fail
- **Market Data**: _mock_quote(), _mock_ohlcv(), _mock_news()
- **Database**: In-memory DuckDB for tests

### Test Isolation:
Each module can be tested independently by mocking its dependencies:
`python
# Test agents/graph.py
from unittest.mock import Mock, patch

@patch('agents.graph.call_llm')
@patch('agents.graph.BrokerFactory')
async def test_orchestrator_node(mock_broker, mock_llm):
    mock_llm.return_value = "GO"
    state = BotState(...)
    result = await orchestrator_node(state)
    assert len(result.final_signals) > 0
`

---

**END OF MODULE DEPENDENCY MAP**
