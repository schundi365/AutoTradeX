"""
APEX Bot — Core Data Models
Shared Pydantic models and enums used across agents, brokers, and API.
"""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════
#  ENUMS
# ═══════════════════════════════════════════════════════

class Direction(str, Enum):
    BUY  = "BUY"
    SELL = "SELL"

class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT  = "LIMIT"
    STOP   = "STOP"

class TradeStatus(str, Enum):
    PENDING = "PENDING"
    OPEN    = "OPEN"
    CLOSED  = "CLOSED"
    FAILED  = "FAILED"
    CANCELLED = "CANCELLED"

class AssetClass(str, Enum):
    METAL     = "METAL"
    COMMODITY = "COMMODITY"
    FOREX     = "FOREX"
    STOCK     = "STOCK"
    CRYPTO    = "CRYPTO"
    INDEX     = "INDEX"

class SignalStrength(str, Enum):
    STRONG = "STRONG"   # score >= 8
    MEDIUM = "MEDIUM"   # score 6.5-8
    WEAK   = "WEAK"     # score < 6.5 (filtered out)

class NewsImpact(str, Enum):
    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    LOW    = "LOW"

class BrokerName(str, Enum):
    MT5     = "MT5"
    CCXT    = "CCXT"
    ALPACA  = "ALPACA"
    IB      = "IB"
    PAPER   = "PAPER"

class AgentStatus(str, Enum):
    IDLE       = "IDLE"
    RUNNING    = "RUNNING"
    WAITING    = "WAITING"
    ERROR      = "ERROR"


# ═══════════════════════════════════════════════════════
#  MARKET DATA
# ═══════════════════════════════════════════════════════

class OHLCV(BaseModel):
    symbol:    str
    timeframe: str
    timestamp: datetime
    open:      float
    high:      float
    low:       float
    close:     float
    volume:    float


class Quote(BaseModel):
    """Real-time bid/ask quote"""
    symbol:    str
    bid:       float
    ask:       float
    spread:    float
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2


# ═══════════════════════════════════════════════════════
#  SIGNALS
# ═══════════════════════════════════════════════════════

class TradingSignal(BaseModel):
    """A trading signal produced by strategy agents"""
    id:           str
    symbol:       str
    asset_class:  AssetClass
    direction:    Direction
    score:        float          # 0-10
    confidence:   float          # 0-1
    strength:     SignalStrength
    strategy:     str            # which strategy generated this
    timeframe:    str
    entry_price:  float
    stop_loss:    float
    take_profit:  float
    risk_reward:  float
    reasoning:    str            # LLM explanation
    created_at:   datetime = Field(default_factory=datetime.utcnow)
    expires_at:   Optional[datetime] = None
    metadata:     dict = Field(default_factory=dict)


# ═══════════════════════════════════════════════════════
#  TRADES
# ═══════════════════════════════════════════════════════

class Trade(BaseModel):
    """A live or historical trade"""
    id:           str
    broker:       BrokerName
    symbol:       str
    asset_class:  AssetClass
    direction:    Direction
    order_type:   OrderType = OrderType.MARKET
    lot_size:     float
    entry_price:  float
    current_price: Optional[float] = None
    stop_loss:    float
    take_profit:  float
    status:       TradeStatus = TradeStatus.PENDING
    open_time:    Optional[datetime] = None
    close_time:   Optional[datetime] = None
    close_price:  Optional[float] = None
    pnl:          float = 0.0
    pnl_pct:      float = 0.0
    commission:   float = 0.0
    strategy:     str = ""
    signal_id:    Optional[str] = None
    broker_order_id: Optional[str] = None
    notes:        str = ""
    metadata:     dict = Field(default_factory=dict)

    @property
    def duration_minutes(self) -> Optional[int]:
        if self.open_time:
            end = self.close_time or datetime.utcnow()
            return int((end - self.open_time).total_seconds() / 60)
        return None


# ═══════════════════════════════════════════════════════
#  NEWS & CALENDAR
# ═══════════════════════════════════════════════════════

class NewsItem(BaseModel):
    id:          str
    title:       str
    summary:     str
    source:      str
    url:         str
    published:   datetime
    symbols:     list[str] = Field(default_factory=list)
    sentiment:   float = 0.0      # -1 (bearish) to +1 (bullish)
    impact:      NewsImpact = NewsImpact.LOW
    categories:  list[str] = Field(default_factory=list)
    processed:   bool = False


class CalendarEvent(BaseModel):
    id:         str
    title:      str
    currency:   str
    impact:     NewsImpact
    scheduled:  datetime
    previous:   Optional[str] = None
    forecast:   Optional[str] = None
    actual:     Optional[str] = None
    released:   bool = False
    bot_action: str = ""          # e.g. "PAUSE_TRADING", "TIGHTEN_SL"


# ═══════════════════════════════════════════════════════
#  AGENT MESSAGES (LangGraph state)
# ═══════════════════════════════════════════════════════

class AgentMessage(BaseModel):
    """Message passed between agents in the graph"""
    from_agent:  str
    to_agent:    str
    message_type: str
    payload:     dict
    timestamp:   datetime = Field(default_factory=datetime.utcnow)


class BotState(BaseModel):
    """Global state passed through the LangGraph workflow"""
    # Current market snapshot
    quotes:          dict[str, Quote]           = Field(default_factory=dict)
    ohlcv_cache:     dict[str, list[OHLCV]]    = Field(default_factory=dict)
    # Intelligence
    news_items:      list[NewsItem]             = Field(default_factory=list)
    calendar_events: list[CalendarEvent]        = Field(default_factory=list)
    # Signals from sub-agents
    pending_signals: list[TradingSignal]        = Field(default_factory=list)
    approved_signals: list[TradingSignal]       = Field(default_factory=list)
    # Portfolio
    open_trades:     list[Trade]                = Field(default_factory=list)
    account_info:    Optional[AccountInfo]      = None
    # Context
    is_news_blackout: bool = False
    market_regime:    str  = "NORMAL"   # NORMAL | VOLATILE | TRENDING
    macro_data:       dict = Field(default_factory=dict)
    messages:         list[AgentMessage] = Field(default_factory=list)
    # Strategy adaptation: populated by strategy_adapter_node each cycle
    strategy_params:  dict = Field(default_factory=dict)


# ═══════════════════════════════════════════════════════
#  ACCOUNT / PORTFOLIO
# ═══════════════════════════════════════════════════════

class AccountInfo(BaseModel):
    broker:      BrokerName
    balance:     float
    equity:      float
    margin:      float
    free_margin: float
    margin_pct:  float
    currency:    str = "USD"
    updated_at:  datetime = Field(default_factory=datetime.utcnow)


class PortfolioStats(BaseModel):
    total_pnl:       float
    today_pnl:       float
    win_rate:        float
    total_trades:    int
    open_trades:     int
    profit_factor:   float
    sharpe_ratio:    float
    max_drawdown:    float
    current_drawdown: float
