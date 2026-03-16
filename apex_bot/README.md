# APEX Trading Bot 🤖⚡

**Agentic AI Multi-Asset Trading System**  
Powered by Claude AI · Supports MT5, Binance, Alpaca, Interactive Brokers

---

## Architecture

```
apex_bot/
├── main.py                  # Entry point
├── requirements.txt
├── .env.example
├── Dockerfile
├── docker-compose.yml
│
├── core/
│   ├── config.py            # All settings (from .env)
│   ├── models.py            # Pydantic data models
│   └── logger.py            # Loguru + WS broadcast logger
│
├── agents/
│   └── graph.py             # LangGraph multi-agent pipeline
│       ├── data_collector   # Fetches quotes, OHLCV, news, calendar
│       ├── market_analyst   # Technical analysis → raw signals
│       ├── sentiment_agent  # LLM news/geo NLP → confidence boost
│       ├── calendar_agent   # Event risk → blackout windows
│       ├── risk_manager     # Portfolio risk → sizing & filtering
│       ├── orchestrator     # Claude LLM → final approval
│       └── execution_agent  # Broker order placement
│
├── brokers/
│   └── base.py              # Broker abstraction layer
│       ├── MT5Broker         # MetaTrader 5
│       ├── CCXTBroker        # 100+ crypto exchanges
│       ├── PaperBroker       # In-memory simulation
│       └── BrokerFactory     # Broker routing & lifecycle
│
├── strategies/
│   └── technical.py         # Technical analysis strategies
│       ├── AI Momentum       # EMA + RSI + MACD + Volume
│       └── Mean Reversion    # Bollinger Bands + RSI extremes
│
├── data/
│   └── market_feed.py       # Data ingestion
│       ├── MarketFeed        # OHLCV + live quotes
│       ├── NewsFeed          # NewsAPI + Reuters RSS + GDELT
│       └── CalendarFeed      # ForexFactory / Investing.com
│
├── api/
│   └── server.py            # FastAPI REST + WebSocket server
│
└── logs/                    # Rotating log files
```

---

## Quick Start

### 1. Clone & Configure
```bash
git clone https://github.com/yourname/apex-bot
cd apex_bot
cp .env.example .env
# Edit .env with your API keys and broker credentials
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run in Paper Mode (safe, no real orders)
```bash
python main.py --mode paper
```

### 4. Run with Dashboard
```bash
# Start the backend
python main.py --port 8000

# Open the frontend dashboard
open trading-bot-dashboard.html
# Point it at: http://localhost:8000
```

### 5. Docker (recommended for production)
```bash
docker-compose up -d
# Dashboard: http://localhost:8000
# Grafana:   http://localhost:3000
```

---

## Configuration

All config is done via `.env` file or the frontend Config panel.

### Required API Keys
| Service | Where to get | Used for |
|---|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com | LLM decisions |
| `MT5_LOGIN/PASSWORD` | Your MT5 broker | Metals, Forex, CFDs |
| `EXCHANGE_API_KEY` | Binance/Bybit | Crypto trading |
| `ALPACA_API_KEY` | alpaca.markets | US Stocks |
| `NEWS_API_KEY` | newsapi.org | News feed |

### Key Settings
```
APP_ENV=paper               # paper | live
LLM_MODEL=claude-sonnet-4-6
MAX_RISK_PER_TRADE=1.5%
MAX_DAILY_DRAWDOWN=5%
MAX_OPEN_TRADES=10
```

---

## Agent Pipeline

Each trading cycle (default: every 5 minutes):

```
DataCollector  →  fetches quotes + news + calendar
MarketAnalyst  →  technical signals (EMA, RSI, MACD, BB)
SentimentAgent →  LLM news alignment scoring  
CalendarAgent  →  event risk, blackout enforcement
RiskManager    →  position sizing, correlation checks
Orchestrator   →  Claude final APPROVE/REJECT decision
ExecutionAgent →  broker order placement
```

---

## Adding a New Strategy

1. Add a method to `strategies/technical.py`:
```python
def _my_strategy(self, df, symbol, tf, quote) -> Optional[TradingSignal]:
    # Your analysis here
    return TradingSignal(...)
```

2. Register in `TechnicalAnalyser.analyse()`:
```python
if "my_strategy" in self.strategies:
    sig = self._my_strategy(df, symbol, tf, quote)
    if sig: signals.append(sig)
```

3. Enable in config:
```
ENABLED_STRATEGIES=ai_momentum,mean_reversion,my_strategy
```

---

## Adding a New Broker

1. Implement `BaseBroker` in `brokers/`:
```python
class MyBroker(BaseBroker):
    name = BrokerName.MY_BROKER
    
    async def connect(self) -> bool: ...
    async def place_order(self, trade: Trade) -> Trade: ...
    # ... implement all abstract methods
```

2. Register in `BrokerFactory._build()`:
```python
if name == BrokerName.MY_BROKER:
    return MyBroker(...)
```

---

## Roadmap

- [ ] TimescaleDB integration for trade history
- [ ] Reinforcement learning strategy optimizer
- [ ] Telegram/Slack real-time alerts
- [ ] Walk-forward backtesting engine
- [ ] Correlation matrix position management
- [ ] Multi-account portfolio support
- [ ] Interactive Brokers broker implementation
- [ ] Webhook support for TradingView alerts

---

## ⚠️ Risk Disclaimer

This software is for educational and research purposes.  
Trading financial instruments involves substantial risk of loss.  
Always test thoroughly in paper mode before trading live.  
Past performance does not guarantee future results.
