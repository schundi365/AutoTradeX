"""
APEX Bot — Core Configuration
Loads and validates all settings from environment variables.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).parent.parent


class AppEnv(str, Enum):
    DEVELOPMENT = "development"
    PAPER       = "paper"
    LIVE        = "live"


class LLMProvider(str, Enum):
    CLAUDE  = "claude"
    OPENAI  = "openai"
    LOCAL   = "local"


# ── RISK DEFAULTS (override via DB config panel) ─────────
@dataclass
class RiskConfig:
    max_risk_per_trade_pct: float = 1.5     # % of account per trade
    max_daily_drawdown_pct: float = 5.0     # halt if exceeded
    max_open_trades: int          = 10
    max_lot_size: float           = 2.0
    max_correlated_pairs: int     = 3       # max similar direction trades
    # News blackout windows (minutes)
    blackout_before_high_impact: int = 15
    blackout_after_high_impact: int  = 30
    blackout_before_med_impact: int  = 5
    blackout_after_med_impact: int   = 15


# ── STRATEGY DEFAULTS ────────────────────────────────────
@dataclass
class StrategyConfig:
    enabled_strategies: list[str] = field(default_factory=lambda: [
        "ai_momentum",
        "mean_reversion",
        "news_sentiment",
    ])
    timeframes: list[str] = field(default_factory=lambda: ["M15", "H1", "H4"])
    min_signal_score: float = 6.5       # out of 10
    min_confidence: float   = 0.60      # 0-1
    sentiment_threshold: float = 0.65   # min sentiment score to trade


# ── ASSET UNIVERSE ───────────────────────────────────────
@dataclass
class AssetConfig:
    metals:      list[str] = field(default_factory=lambda: ["XAUUSD", "XAGUSD", "XPTUSD"])
    commodities: list[str] = field(default_factory=lambda: ["USOIL", "UKOIL", "NATGAS"])
    forex:       list[str] = field(default_factory=lambda: ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"])
    stocks:      list[str] = field(default_factory=lambda: ["AAPL", "NVDA", "MSFT", "TSLA", "AMZN"])
    crypto:      list[str] = field(default_factory=lambda: ["BTC/USDT", "ETH/USDT", "SOL/USDT"])

    @property
    def all_mt5_symbols(self) -> list[str]:
        return self.metals + self.commodities + self.forex

    @property
    def all_symbols(self) -> list[str]:
        return self.metals + self.commodities + self.forex + self.stocks + self.crypto


# ── MASTER CONFIG ────────────────────────────────────────
@dataclass
class Config:
    # Environment
    env: AppEnv = AppEnv(os.getenv("APP_ENV", "development"))
    secret_key: str = os.getenv("APP_SECRET_KEY", "dev-secret")
    log_level: str  = os.getenv("LOG_LEVEL", "INFO")

    # MT5
    mt5_login:    int  = int(os.getenv("MT5_LOGIN", "0"))
    mt5_password: str  = os.getenv("MT5_PASSWORD", "")
    mt5_server:   str  = os.getenv("MT5_SERVER", "MetaQuotes-Demo")
    mt5_path:     str  = os.getenv("MT5_PATH", "")

    # Crypto
    exchange_id:      str  = os.getenv("EXCHANGE_ID", "binance")
    exchange_api_key: str  = os.getenv("EXCHANGE_API_KEY", "")
    exchange_secret:  str  = os.getenv("EXCHANGE_SECRET", "")
    exchange_sandbox: bool = os.getenv("EXCHANGE_SANDBOX", "true").lower() == "true"

    # Alpaca
    alpaca_api_key:    str = os.getenv("ALPACA_API_KEY", "")
    alpaca_secret_key: str = os.getenv("ALPACA_SECRET_KEY", "")
    alpaca_base_url:   str = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    # AI
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    openai_api_key:    str = os.getenv("OPENAI_API_KEY", "")
    llm_provider: LLMProvider = LLMProvider(os.getenv("LLM_PRIMARY", "claude"))
    llm_model: str     = os.getenv("LLM_MODEL", "claude-sonnet-4-6")

    # Data
    news_api_key:       str = os.getenv("NEWS_API_KEY", "")
    alpha_vantage_key:  str = os.getenv("ALPHA_VANTAGE_KEY", "")
    polygon_api_key:    str = os.getenv("POLYGON_API_KEY", "")

    # DB
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./apex_dev.db")
    redis_url:    str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Notifications
    telegram_token:   str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    slack_webhook:    str = os.getenv("SLACK_WEBHOOK_URL", "")

    # Sub-configs
    risk:     RiskConfig     = field(default_factory=RiskConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    assets:   AssetConfig    = field(default_factory=AssetConfig)

    @property
    def is_live(self) -> bool:
        return self.env == AppEnv.LIVE

    @property
    def is_paper(self) -> bool:
        return self.env in (AppEnv.PAPER, AppEnv.DEVELOPMENT)


# Singleton — import this everywhere
settings = Config()
