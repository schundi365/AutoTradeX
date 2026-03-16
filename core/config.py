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
    CLAUDE   = "claude"
    OPENAI   = "openai"
    DEEPSEEK = "deepseek"
    GROQ     = "groq"
    GEMINI   = "gemini"
    LOCAL    = "local"


# ── SOP CONSTANTS (Section 03/04/06 — regime-based multipliers) ──────────
# SL multiplier × ATR for each market regime
REGIME_SL_MULTIPLIERS: dict[str, float] = {
    "STRONG_TREND":  1.2,
    "WEAK_TREND":    1.5,
    "RANGING":       2.0,
    "LOW_VOLATILE":  1.8,
    "BREAKOUT":      1.3,
    "HIGH_VOLATILE": 2.5,  # entry blocked anyway
}

# TP multiplier × SL distance (R:R numerator) per regime
REGIME_TP_MULTIPLIERS: dict[str, float] = {
    "STRONG_TREND":  3.0,
    "WEAK_TREND":    2.5,
    "RANGING":       2.0,
    "LOW_VOLATILE":  2.2,
    "BREAKOUT":      3.5,
    "HIGH_VOLATILE": 2.0,
}

# Risk multiplier applied to Half-Kelly result per regime (Section 6.2)
REGIME_RISK_MULTIPLIERS: dict[str, float] = {
    "STRONG_TREND":  1.30,
    "WEAK_TREND":    1.00,
    "RANGING":       0.70,
    "LOW_VOLATILE":  0.80,
    "BREAKOUT":      1.10,
    "HIGH_VOLATILE": 0.50,
    "MACRO_RISK_OFF": 0.60,
    "MACRO_RISK_ON":  1.20,
}

# Trailing stop mode per regime (Section 05)
REGIME_TRAIL_MODE: dict[str, str] = {
    "STRONG_TREND":  "ATR",
    "WEAK_TREND":    "STEP",
    "RANGING":       "BREAKEVEN",
    "BREAKOUT":      "ATR",
    "LOW_VOLATILE":  "STEP",
    "HIGH_VOLATILE": "BREAKEVEN",
}

# Correlation groups (Section 08) — max same-direction positions
CORRELATION_GROUPS: dict[str, tuple[list[str], int]] = {
    "USD_PAIRS":   (["EURUSD", "GBPUSD", "AUDUSD", "USDCHF", "USDCAD", "USDJPY"], 2),
    "SAFE_HAVENS": (["XAUUSD", "XAGUSD", "USDCHF", "USDJPY"], 2),
    "RISK_ASSETS": (["SP500", "BTC", "ETH", "USOIL"], 2),
    "CRYPTO":      (["BTC", "ETH", "SOL"], 1),
    "ENERGY":      (["USOIL", "UKOIL", "NATGAS"], 2),
}


# ── RISK DEFAULTS (override via DB config panel) ─────────
@dataclass
class RiskConfig:
    # SOP Section 06 hard limits
    max_risk_per_trade_pct: float = 2.0     # G9 / Section 6.3: 2% hard cap
    max_combined_risk_pct: float  = 6.0     # Section 6.3: 6% total open risk
    max_daily_drawdown_pct: float = 2.0     # Section 6.3 / G9: 2% daily halt
    max_consecutive_losses: int   = 5       # Section 6.3: pause 4h after 5 losses
    min_equity_pct: float         = 70.0    # Section 6.3: stop below 70% of peak
    drawdown_scale_threshold_pct: float = 5.0   # Section 8 P-04: scale down 50% at 5% DD
    max_open_trades: int          = 10      # G10 / Section 6.3
    max_trades_per_symbol: int    = 2       # Section 6.3: max 2 per symbol
    max_lot_size: float           = 2.0
    max_correlated_pairs: int     = 2       # Section 8.1
    # SOP Section 01 signal gate thresholds
    min_signal_score: float   = 6.5   # G1
    min_confidence: float     = 0.60  # G2
    min_risk_reward: float    = 1.8   # G3
    min_adx: float            = 15.0  # G4 - Lowered from 18 to catch gold trends earlier
    min_atr_ratio: float      = 0.5   # G5 lower
    max_atr_ratio: float      = 2.0   # G5 upper
    min_volume_ratio: float   = 0.8   # G6
    # News blackout windows (minutes)
    blackout_before_high_impact: int = 15
    blackout_after_high_impact: int  = 30
    blackout_before_med_impact: int  = 5
    blackout_after_med_impact: int   = 15
    # Management cycle interval (seconds)
    position_mgmt_interval_sec: int = 15


# ── STRATEGY DEFAULTS ────────────────────────────────────
@dataclass
class StrategyConfig:
    enabled_strategies: list[str] = field(default_factory=lambda: [
        "ai_momentum",
        "mean_reversion",
        "news_sentiment",
    ])
    timeframes: list[str] = field(default_factory=lambda: ["M15", "M30", "H1", "H4"])
    min_signal_score: float = 6.5       # G1: SOP minimum score
    min_confidence: float   = 0.60      # G2: SOP minimum confidence
    sentiment_threshold: float = 0.65   # min sentiment score to trade


# ── TRAINING PIPELINE CONFIG ─────────────────────────────
@dataclass
class TrainingConfig:
    # --- Data collection ---
    fred_api_key: str = field(default_factory=lambda: os.getenv("FRED_API_KEY", ""))
    historical_start_date: str = "2018-01-01"
    ccxt_start_date: str = "2019-01-01"
    yfinance_timeframe: str = "1h"
    ccxt_timeframe: str = "1h"
    raw_data_dir: str = "data/raw"
    macro_data_dir: str = "data/macro"
    duckdb_path: str = field(default_factory=lambda: os.getenv("DUCKDB_PATH", "data/apex.db"))
    # yfinance symbol map: internal name → yfinance ticker
    yfinance_symbols: dict = field(default_factory=lambda: {
        "XAUUSD": "GC=F",       # COMEX gold futures — correct Yahoo Finance ticker for gold 1h OHLCV
        "XAGUSD": "SI=F",       # silver futures — XAGUSD=X is not a valid Yahoo ticker
        "USOIL":  "CL=F",
        "EURUSD": "EURUSD=X",
        "GBPUSD": "GBPUSD=X",
        "USDJPY": "USDJPY=X",
        "AUDUSD": "AUDUSD=X",
        "DXY":    "DX-Y.NYB",
        "US10Y":  "^TNX",
        "SP500":  "^GSPC",
        "VIX":    "^VIX",
        "BTC":    "BTC-USD",
        "ETH":    "ETH-USD",
    })
    ccxt_symbols: list = field(default_factory=lambda: [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    ])
    # FRED macro series: series_id → friendly name
    fred_series: dict = field(default_factory=lambda: {
        "DTWEXBGS":  "DXY",           # USD broad index (daily)
        "DGS10":     "US10Y",         # 10-year Treasury yield (daily)
        "DGS2":      "US2Y",          # 2-year Treasury yield (daily)
        "T10YIE":    "BREAKEVEN_10Y", # 10-year breakeven inflation (daily)
        "VIXCLS":    "VIX",           # CBOE VIX (daily)
        "DEXUSEU":   "EURUSD",        # EUR/USD spot (daily)
        "DEXUSUK":   "GBPUSD",        # GBP/USD spot (daily)
        "CPIAUCSL":  "CPI",           # US CPI (monthly — forward-filled)
        "FEDFUNDS":  "FED_RATE",      # Fed Funds Rate (monthly — forward-filled)
        # GOLD: not available via FRED free tier — gold OHLCV comes from yfinance GC=F
    })
    # Sentiment collection keywords (for GDELT / news filtering)
    sentiment_keywords: list = field(default_factory=lambda: [
        "gold price", "XAUUSD", "DXY dollar index", "Federal Reserve",
        "interest rates", "inflation CPI", "treasury yields",
    ])
    # --- Training export ---
    min_training_examples: int = 200
    training_data_dir: str = "training_data"
    include_synthetic: bool = True
    # --- Fine-tuning ---
    base_model: str = field(default_factory=lambda: os.getenv(
        "FINETUNE_BASE_MODEL", "unsloth/llama-3.1-8b-bnb-4bit"
    ))
    lora_rank: int = 8
    lora_alpha: int = 16
    num_epochs: int = 1
    batch_size: int = 1
    gradient_accumulation: int = 16
    learning_rate: float = 2e-4
    max_seq_length: int = 512
    eval_split: float = 0.0
    model_output_dir: str = "models/apex_trading_model"
    checkpoint_dir: str = "checkpoints/apex_qlora"
    # --- GGUF conversion ---
    gguf_output: str = "models/apex_trading_llm.gguf"
    quant_type: str = "q4_k_m"                     # q4_k_m | q8_0 | q5_k_m | f16
    ollama_model_name: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "apex-trader"))
    # --- Kaggle remote training ---
    kaggle_username: str = field(default_factory=lambda: os.getenv("KAGGLE_USERNAME", ""))
    kaggle_api_key: str  = field(default_factory=lambda: os.getenv("KAGGLE_KEY", ""))
    kaggle_dataset_name: str = "apex-training-data"
    kaggle_kernel_name: str  = "apex-qlora-finetune"
    kaggle_gpu_type: str     = "gpu"   # gpu=T4 (free) | gpu_t4_x2=Pro | nvidiagpup100=P100
    # --- RunPod Serverless remote training ---
    runpod_api_key: str     = field(default_factory=lambda: os.getenv("RUNPOD_API_KEY", ""))
    runpod_endpoint_id: str = field(default_factory=lambda: os.getenv("RUNPOD_ENDPOINT_ID", ""))
    # --- Docker image build (for RunPod) ---
    docker_hub_username: str = field(default_factory=lambda: os.getenv("DOCKER_HUB_USERNAME", ""))
    docker_image_name: str   = field(default_factory=lambda: os.getenv("DOCKER_IMAGE_NAME", "apex-runpod"))
    # --- Automation ---
    llm_training_schedule: str = "0 2 * * 6"  # Cron: Sat 02:00


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
    monitor_only: bool = os.getenv("MONITOR_ONLY", "false").lower() == "true"
    autostart: bool = os.getenv("AUTOSTART", "false").lower() == "true"
    bot_cycle_minutes: int = int(os.getenv("BOT_CYCLE_MINUTES", "1"))  # Decision cycle interval

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
    deepseek_api_key:  str = os.getenv("DEEPSEEK_API_KEY", "")
    groq_api_key:      str = os.getenv("GROQ_API_KEY", "")
    gemini_api_key:    str = os.getenv("GEMINI_API_KEY", "")
    llm_provider: LLMProvider = LLMProvider(os.getenv("LLM_PRIMARY", "claude"))
    llm_model: str     = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str   = os.getenv("OLLAMA_MODEL", "llama3")
    llm_timeout: float  = float(os.getenv("LLM_TIMEOUT", "60.0"))

    # Data
    news_api_key:       str = os.getenv("NEWS_API_KEY", "")
    alpha_vantage_key:  str = os.getenv("ALPHA_VANTAGE_KEY", "")
    polygon_api_key:    str = os.getenv("POLYGON_API_KEY", "")
    calendar_provider:  str = os.getenv("CALENDAR_PROVIDER", "investingcom")

    # DB
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./apex_dev.db")
    redis_url:    str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    timescaledb_url: str = os.getenv("TIMESCALEDB_URL", "postgresql://postgres:password@localhost:5432/apex_timescale")

    # Notifications
    telegram_token:   str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    slack_webhook:    str = os.getenv("SLACK_WEBHOOK_URL", "")

    # Sub-configs
    risk:     RiskConfig     = field(default_factory=RiskConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    assets:   AssetConfig    = field(default_factory=AssetConfig)
    training: TrainingConfig = field(default_factory=TrainingConfig)

    # Dynamic Profiles
    _profiles: dict = field(default_factory=dict)

    def __post_init__(self):
        """Load asset profiles after initialization."""
        self._load_profiles()

    def _load_profiles(self):
        """Loads per-asset risk profiles from config/asset_profiles.json"""
        profile_path = ROOT_DIR / "config" / "asset_profiles.json"
        if profile_path.exists():
            try:
                import json
                with open(profile_path, "r") as f:
                    self._profiles = json.load(f)
            except Exception as e:
                print(f"Error loading asset_profiles.json: {e}")
        else:
            # Fallback empty profiles
            self._profiles = {}

    def get_asset_profile(self, symbol: str) -> dict:
        """Retrieve profile for symbol, falling back to DEFAULT then global risk settings."""
        s = symbol.upper()
        # Direct match
        if s in self._profiles:
            return self._profiles[s]
        
        # Partial match (e.g. XAUUSD matches XAU)
        for key in self._profiles:
            if key != "DEFAULT" and key in s:
                return self._profiles[key]
                
        # DEFAULT from file
        if "DEFAULT" in self._profiles:
            return self._profiles["DEFAULT"]
            
        # Hardcoded default mapping to global RiskConfig
        return {
            "max_risk_pct": self.risk.max_risk_per_trade_pct,
            "max_lot": self.risk.max_lot_size,
            "regime_multipliers": {
                "STRONG_TREND": 1.3,
                "WEAK_TREND": 1.0,
                "RANGING": 0.7,
                "HIGH_VOLATILE": 0.5,
                "LOW_VOLATILE": 0.8,
                "BREAKOUT": 1.1
            },
            "volatility_threshold": 2.0
        }

    @property
    def is_live(self) -> bool:
        return self.env == AppEnv.LIVE

    @property
    def is_paper(self) -> bool:
        return self.env in (AppEnv.PAPER, AppEnv.DEVELOPMENT)


# Singleton — import this everywhere
settings = Config()
