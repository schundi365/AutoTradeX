"""
APEX Bot — Technical Analysis, Adaptive Risk & Position Management
═══════════════════════════════════════════════════════════════════

TRADE EXECUTION PHASE
  1. AdaptiveRiskManager  — analyse market conditions (regime, volatility, trend strength)
  2. PositionSizer        — calculate optimal lot size using ATR / Kelly / Volatility methods
  3. TradeExecutor        — execute trade with optimal parameters, log everything
  4. TradeLogger          — structured log: symbol, direction, price, SL, TP, lot, order#, timestamp

POSITION MANAGEMENT PHASE (real-time polling loop)
  1. PositionVerifier     — confirm position still exists on broker
  2. IndicatorRefresher   — fetch live OHLCV, recalculate all indicators in real time
  3. DynamicSLEngine      — tighten SL when trend momentum weakens or reverses
  4. DynamicTPEngine      — extend TP when trend accelerates (ADX rise, momentum surge)
  5. TrailingStopEngine   — ATR-based, step-based, and break-even trailing
  6. PositionCleaner      — detect and cleanly remove broker-closed positions

All state is stored in PositionTracker (in-memory + optional DB persistence).
"""
from __future__ import annotations

import asyncio
import uuid
import math
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, List, Tuple

import pandas as pd
import numpy as np

from core.models import (
    TradingSignal, Direction, SignalStrength, AssetClass,
    Trade, TradeStatus, Quote,
)
from core.config import settings
from core.logger import get_agent_logger

log = get_agent_logger("STRATEGY")


# ═══════════════════════════════════════════════════════
#  ENUMS & CONSTANTS
# ═══════════════════════════════════════════════════════

class MarketRegime(str, Enum):
    STRONG_TREND  = "STRONG_TREND"    # ADX > 35, clear directional move
    WEAK_TREND    = "WEAK_TREND"      # ADX 20-35
    RANGING       = "RANGING"         # ADX < 20, price bouncing
    HIGH_VOLATILE = "HIGH_VOLATILE"   # ATR spike > 2x normal
    LOW_VOLATILE  = "LOW_VOLATILE"    # ATR compressed < 0.5x normal
    BREAKOUT      = "BREAKOUT"        # Volatility expanding from compression

class SizingMethod(str, Enum):
    FIXED_PCT   = "FIXED_PCT"         # % of account balance
    ATR_BASED   = "ATR_BASED"         # risk / (ATR * multiplier)
    KELLY       = "KELLY"             # Kelly criterion
    VOLATILITY  = "VOLATILITY"        # inverse volatility weighting

class TrailingMode(str, Enum):
    ATR         = "ATR"               # trail by N * ATR
    STEP        = "STEP"              # move SL by fixed step increments
    BREAKEVEN   = "BREAKEVEN"         # move SL to entry once in profit
    PARABOLIC   = "PARABOLIC"         # Parabolic SAR based

ASSET_MAP = {
    "XAU": AssetClass.METAL,    "XAG": AssetClass.METAL,    "XPT": AssetClass.METAL,
    "BTC": AssetClass.CRYPTO,   "ETH": AssetClass.CRYPTO,   "SOL": AssetClass.CRYPTO,
    "USD": AssetClass.FOREX,    "EUR": AssetClass.FOREX,     "GBP": AssetClass.FOREX,
    "AUD": AssetClass.FOREX,    "JPY": AssetClass.FOREX,     "CHF": AssetClass.FOREX,
    "OIL": AssetClass.COMMODITY,"GAS": AssetClass.COMMODITY,
}

def _asset_class(symbol: str) -> AssetClass:
    for prefix, cls in ASSET_MAP.items():
        if prefix in symbol.upper():
            return cls
    return AssetClass.STOCK


# ═══════════════════════════════════════════════════════
#  MARKET CONDITION SNAPSHOT
# ═══════════════════════════════════════════════════════

@dataclass
class MarketConditions:
    symbol:           str
    timeframe:        str
    timestamp:        datetime           = field(default_factory=datetime.utcnow)
    regime:           MarketRegime       = MarketRegime.RANGING
    adx:              float              = 0.0
    trend_direction:  Optional[Direction]= None
    atr:              float              = 0.0
    atr_pct:          float              = 0.0
    atr_ratio:        float              = 1.0
    rsi:              float              = 50.0
    momentum:         float              = 0.0
    volume_ratio:     float              = 1.0
    bb_width:         float              = 0.0
    support:          Optional[float]    = None
    resistance:       Optional[float]    = None
    risk_multiplier:  float              = 1.0

    def to_log_str(self) -> str:
        return (
            f"Regime={self.regime.value} | ADX={self.adx:.1f} | "
            f"ATR={self.atr:.5f}({self.atr_pct:.2f}%) | "
            f"RSI={self.rsi:.1f} | Vol×{self.volume_ratio:.2f} | "
            f"RiskMult={self.risk_multiplier:.2f}"
        )


# ═══════════════════════════════════════════════════════
#  EXECUTION RECORD  (full audit trail per trade)
# ═══════════════════════════════════════════════════════

@dataclass
class ExecutionRecord:
    execution_id:     str
    signal_id:        str
    symbol:           str
    direction:        str
    strategy:         str
    timeframe:        str
    signal_price:     float
    execution_price:  float
    slippage:         float
    stop_loss:        float
    take_profit:      float
    lot_size:         float
    account_balance:  float
    risk_amount:      float
    risk_pct:         float
    sizing_method:    str
    market_regime:    str
    atr:              float
    adx:              float
    rsi:              float
    broker_order_id:  str       = ""
    broker_name:      str       = ""
    execution_time:   datetime  = field(default_factory=datetime.utcnow)
    order_latency_ms: int       = 0
    status:           str       = "PENDING"
    notes:            str       = ""

    def to_log_line(self) -> str:
        return (
            f"[EXEC#{self.execution_id[:8]}] "
            f"{self.direction} {self.lot_size} {self.symbol} "
            f"@ {self.execution_price:.5f} | "
            f"SL={self.stop_loss:.5f} TP={self.take_profit:.5f} | "
            f"Risk={self.risk_pct:.2f}%(${self.risk_amount:.2f}) | "
            f"Order#{self.broker_order_id} | "
            f"Regime={self.market_regime} | "
            f"ATR={self.atr:.5f} ADX={self.adx:.1f} RSI={self.rsi:.1f} | "
            f"Slippage={self.slippage:+.5f} | "
            f"Latency={self.order_latency_ms}ms | "
            f"Time={self.execution_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}"
        )


# ═══════════════════════════════════════════════════════
#  MANAGED POSITION  (live position state)
# ═══════════════════════════════════════════════════════

@dataclass
class ManagedPosition:
    trade:                   Trade
    exec_record:             ExecutionRecord
    conditions_at_entry:     MarketConditions
    highest_price:           float           = 0.0
    lowest_price:            float           = 999_999_999.0
    sl_tightened_count:      int             = 0
    tp_extended_count:       int             = 0
    trailing_active:         bool            = False
    breakeven_triggered:     bool            = False
    last_managed_at:         datetime        = field(default_factory=datetime.utcnow)
    last_sl:                 float           = 0.0
    last_tp:                 float           = 0.0
    management_log:          list            = field(default_factory=list)
    closed_reason:           Optional[str]   = None

    def log_event(self, event: str):
        ts    = datetime.utcnow().strftime("%H:%M:%S")
        entry = f"[{ts}] {event}"
        self.management_log.append(entry)
        log.info("[POSITION] {} | {}", self.trade.symbol, event)

    @property
    def unrealised_pnl_pct(self) -> float:
        if not self.trade.current_price or not self.trade.entry_price:
            return 0.0
        diff = self.trade.current_price - self.trade.entry_price
        if self.trade.direction == Direction.SELL:
            diff = -diff
        return (diff / self.trade.entry_price) * 100


# ═══════════════════════════════════════════════════════
#  1. ADAPTIVE RISK MANAGER
# ═══════════════════════════════════════════════════════

class AdaptiveRiskManager:
    """
    Analyses market conditions and produces a MarketConditions snapshot.
    Outputs:
      - regime classification
      - risk_multiplier (scales position size up/down)
      - full indicator values for downstream use
    """

    async def analyse(self, df: pd.DataFrame, symbol: str, timeframe: str) -> MarketConditions:
        cond = MarketConditions(symbol=symbol, timeframe=timeframe)
        if len(df) < 30:
            return cond
        try:
            cond.atr          = _calc_atr(df, 14)
            cond.adx          = self._calc_adx(df, 14)
            cond.rsi          = self._calc_rsi(df, 14)
            cond.momentum     = self._calc_momentum(df, 10)
            cond.volume_ratio = self._calc_volume_ratio(df, 20)
            cond.bb_width     = self._calc_bb_width(df, 20)
            cond.atr_ratio    = self._calc_atr_ratio(df, 14, 20)
            cond.atr_pct      = (cond.atr / df["close"].iloc[-1]) * 100
            cond.trend_direction     = self._calc_trend_direction(df)
            cond.support, cond.resistance = self._calc_sr_levels(df)
            cond.regime          = self._classify_regime(cond)
            cond.risk_multiplier = self._calc_risk_multiplier(cond)
        except Exception as e:
            log.warning("AdaptiveRiskManager error {} {}: {}", symbol, timeframe, e)
        log.info("[MARKET] MarketConditions | {} {} | {}", symbol, timeframe, cond.to_log_str())
        return cond

    def _calc_adx(self, df: pd.DataFrame, period: int = 14) -> float:
        try:
            import pandas_ta as ta
            result = df.ta.adx(length=period)
            if result is not None:
                col = f"ADX_{period}"
                if col in result.columns:
                    val = result[col].iloc[-1]
                    return float(val) if not pd.isna(val) else 20.0
        except Exception:
            pass
        # Manual Wilder ADX fallback
        high, low, close = df["high"], df["low"], df["close"]
        tr = pd.concat([high - low,
                        (high - close.shift()).abs(),
                        (low  - close.shift()).abs()], axis=1).max(axis=1)
        atr      = tr.ewm(alpha=1/period, adjust=False).mean()
        dm_plus  = (high.diff()).clip(lower=0)
        dm_minus = (-low.diff()).clip(lower=0)
        dm_plus  = dm_plus.where(dm_plus > (-low.diff()), 0)
        dm_minus = dm_minus.where(dm_minus > high.diff(), 0)
        di_plus  = 100 * dm_plus.ewm(alpha=1/period, adjust=False).mean() / (atr + 1e-9)
        di_minus = 100 * dm_minus.ewm(alpha=1/period, adjust=False).mean() / (atr + 1e-9)
        dx       = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus + 1e-9)
        adx      = dx.ewm(alpha=1/period, adjust=False).mean().iloc[-1]
        return round(float(adx), 2)

    def _calc_rsi(self, df: pd.DataFrame, period: int = 14) -> float:
        delta = df["close"].diff()
        gain  = delta.clip(lower=0).rolling(period).mean()
        loss  = (-delta.clip(upper=0)).rolling(period).mean()
        rs    = gain / (loss + 1e-9)
        rsi   = 100 - (100 / (1 + rs))
        return round(float(rsi.iloc[-1]), 2)

    def _calc_momentum(self, df: pd.DataFrame, period: int = 10) -> float:
        roc = ((df["close"].iloc[-1] - df["close"].iloc[-period-1]) /
               (df["close"].iloc[-period-1] + 1e-9)) * 100
        return round(float(roc), 4)

    def _calc_volume_ratio(self, df: pd.DataFrame, avg_period: int = 20) -> float:
        avg = df["volume"].rolling(avg_period).mean().iloc[-1]
        cur = df["volume"].iloc[-1]
        return round(float(cur / (avg + 1e-9)), 2)

    def _calc_bb_width(self, df: pd.DataFrame, period: int = 20) -> float:
        mid   = df["close"].rolling(period).mean()
        std   = df["close"].rolling(period).std()
        upper = mid + 2 * std
        lower = mid - 2 * std
        width = ((upper - lower) / (mid + 1e-9) * 100).iloc[-1]
        return round(float(width), 4)

    def _calc_atr_ratio(self, df: pd.DataFrame, period: int = 14, avg_period: int = 20) -> float:
        high, low, close = df["high"], df["low"], df["close"]
        tr = pd.concat([high - low,
                        (high - close.shift()).abs(),
                        (low  - close.shift()).abs()], axis=1).max(axis=1)
        atr_series = tr.rolling(period).mean()
        current    = atr_series.iloc[-1]
        avg_past   = atr_series.iloc[-(avg_period+1):-1].mean()
        return round(float(current / (avg_past + 1e-9)), 2)

    def _calc_trend_direction(self, df: pd.DataFrame) -> Optional[Direction]:
        ema20 = df["close"].ewm(span=20).mean().iloc[-1]
        ema50 = df["close"].ewm(span=50).mean().iloc[-1]
        if ema20 > ema50 * 1.001:  return Direction.BUY
        if ema20 < ema50 * 0.999:  return Direction.SELL
        return None

    def _calc_sr_levels(self, df: pd.DataFrame, lookback: int = 50) -> Tuple[float, float]:
        w = df.tail(lookback)
        return float(w["low"].min()), float(w["high"].max())

    def _classify_regime(self, c: MarketConditions) -> MarketRegime:
        profile = settings.get_asset_profile(c.symbol)
        v_thresh = profile.get("volatility_threshold", 2.0)
        
        if c.atr_ratio > v_thresh:       return MarketRegime.HIGH_VOLATILE
        if c.atr_ratio < 0.5:            return MarketRegime.LOW_VOLATILE
        if c.adx > 35:                   return MarketRegime.STRONG_TREND
        if c.adx > 20:                   return MarketRegime.WEAK_TREND
        if c.bb_width < 2.0 and c.volume_ratio > 1.5:
                                        return MarketRegime.BREAKOUT
        return MarketRegime.RANGING

    def _calc_risk_multiplier(self, c: MarketConditions) -> float:
        profile = settings.get_asset_profile(c.symbol)
        multipliers = profile.get("regime_multipliers", {})
        
        base = multipliers.get(c.regime.value, 1.0)
        if c.rsi > 75 or c.rsi < 25:   base *= 0.85
        if c.volume_ratio > 1.5:      base *= 1.10
        return round(min(max(base, 0.2), 2.0), 2)


# ═══════════════════════════════════════════════════════
#  2. POSITION SIZER
# ═══════════════════════════════════════════════════════

class PositionSizer:
    """
    Calculates optimal lot size based on risk config + market conditions.
    Supports ATR-based, Kelly, Volatility, and Fixed-% methods.
    """

    def calculate(
        self,
        signal:          TradingSignal,
        conditions:      MarketConditions,
        account_balance: float,
        method:          SizingMethod = SizingMethod.ATR_BASED,
    ) -> Tuple[float, float, float]:
        """Returns (lot_size, risk_amount_$, risk_pct)"""
        profile = settings.get_asset_profile(signal.symbol)
        
        # Use profile-specific risk cap, falling back to global settings
        max_risk_pct  = profile.get("max_risk_pct", settings.risk.max_risk_per_trade_pct)
        max_lot       = profile.get("max_lot", settings.risk.max_lot_size)
        
        base_risk_pct  = max_risk_pct / 100
        adj_risk_pct   = base_risk_pct * conditions.risk_multiplier
        risk_amount    = account_balance * adj_risk_pct

        sl_distance = abs(signal.entry_price - signal.stop_loss)
        if sl_distance < 1e-9:
            sl_distance = conditions.atr * 1.5

        if method == SizingMethod.ATR_BASED:
            lot = self._atr_based(risk_amount, sl_distance, signal.symbol)
        elif method == SizingMethod.KELLY:
            lot = self._kelly(risk_amount, sl_distance, signal.confidence,
                              signal.risk_reward, account_balance, signal.symbol)
        elif method == SizingMethod.VOLATILITY:
            lot = self._volatility_based(risk_amount, conditions.atr_pct, signal.symbol)
        else:
            lot = self._atr_based(account_balance * base_risk_pct, sl_distance, signal.symbol)

        lot = round(min(max(lot, 0.01), max_lot), 2)

        pv              = _point_value(signal.symbol)
        actual_risk_pct = (sl_distance * lot * pv * 100) / (account_balance + 1e-9) / pv
        actual_risk_amt = account_balance * actual_risk_pct

        log.info(
            "[SIZER] PositionSizer | {} {} | {}/{} | Lot={} | Risk={:.2f}%(${:.2f}) | SLdist={:.5f}",
            signal.direction, signal.symbol, method.value, conditions.regime.value,
            lot, actual_risk_pct * 100, actual_risk_amt, sl_distance,
        )
        return lot, round(actual_risk_amt, 2), round(actual_risk_pct * 100, 4)

    def _atr_based(self, risk_amount: float, sl_dist: float, symbol: str) -> float:
        pv  = _point_value(symbol)
        lot = risk_amount / max(sl_dist * pv * 100 / pv, 1e-9)
        return round(lot, 2)

    def _kelly(self, risk_amount, sl_dist, win_rate, avg_rr, balance, symbol) -> float:
        kelly_f    = win_rate - ((1 - win_rate) / max(avg_rr, 0.1))
        kelly_f    = max(kelly_f, 0.0)
        kelly_amt  = min(balance * kelly_f * 0.5, risk_amount * 1.5)  # half-Kelly, capped
        return self._atr_based(kelly_amt, sl_dist, symbol)

    def _volatility_based(self, risk_amount: float, atr_pct: float, symbol: str) -> float:
        target_vol = 1.5
        factor     = target_vol / max(atr_pct, 0.1)
        return self._atr_based(risk_amount * factor, atr_pct / 100 or 0.001, symbol)


# ═══════════════════════════════════════════════════════
#  3 + 4. TRADE EXECUTOR + TRADE LOGGER
# ═══════════════════════════════════════════════════════

class TradeExecutor:
    """
    Executes a signal through the broker.
    Produces a full ExecutionRecord for audit logging.
    """

    def __init__(self, broker, sizer: PositionSizer, account_balance: float):
        self.broker          = broker
        self.sizer           = sizer
        self.account_balance = account_balance

    async def execute(
        self,
        signal:       TradingSignal,
        conditions:   MarketConditions,
        sizing_method: SizingMethod = SizingMethod.ATR_BASED,
    ) -> Tuple[Optional[Trade], Optional[ExecutionRecord]]:

        exec_id = str(uuid.uuid4())

        # Phase 2: Size the position
        lot_size, risk_amt, risk_pct = self.sizer.calculate(
            signal, conditions, self.account_balance, sizing_method
        )

        # Phase 3: Build and place order
        trade = Trade(
            id=exec_id,
            broker=self.broker.name,
            symbol=signal.symbol,
            asset_class=signal.asset_class,
            direction=signal.direction,
            lot_size=lot_size,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            strategy=signal.strategy,
            signal_id=signal.id,
        )

        t_start = datetime.utcnow()
        try:
            executed = await self.broker.place_order(trade)
        except Exception as e:
            log.error("TradeExecutor: FAILED placing {} {} — {}", signal.symbol, signal.direction, e)
            return None, None
        t_end   = datetime.utcnow()

        latency_ms  = int((t_end - t_start).total_seconds() * 1000)
        fill_price  = executed.entry_price
        slippage    = fill_price - signal.entry_price
        if signal.direction == Direction.SELL:
            slippage = -slippage

        # Phase 4: Structured execution record
        record = ExecutionRecord(
            execution_id=exec_id,
            signal_id=signal.id,
            symbol=signal.symbol,
            direction=signal.direction.value,
            strategy=signal.strategy,
            timeframe=signal.timeframe,
            signal_price=signal.entry_price,
            execution_price=fill_price,
            slippage=round(slippage, 5),
            stop_loss=executed.stop_loss,
            take_profit=executed.take_profit,
            lot_size=lot_size,
            account_balance=self.account_balance,
            risk_amount=risk_amt,
            risk_pct=risk_pct,
            sizing_method=sizing_method.value,
            market_regime=conditions.regime.value,
            atr=round(conditions.atr, 5),
            adx=round(conditions.adx, 2),
            rsi=round(conditions.rsi, 2),
            broker_order_id=executed.broker_order_id or "",
            broker_name=self.broker.name.value,
            execution_time=t_end,
            order_latency_ms=latency_ms,
            status="OPEN",
        )

        log.success("[EXEC] TRADE EXECUTED | {}", record.to_log_line())
        await _write_audit_log(record)

        return executed, record


async def _write_audit_log(record: ExecutionRecord):
    from pathlib import Path
    log_path = Path("logs") / f"trades_{datetime.utcnow().strftime('%Y-%m-%d')}.jsonl"
    try:
        log_path.parent.mkdir(exist_ok=True)
        line = json.dumps(asdict(record), default=str) + "\n"
        try:
            import aiofiles
            async with aiofiles.open(log_path, "a") as f:
                await f.write(line)
        except ImportError:
            with open(log_path, "a") as f:
                f.write(line)
    except Exception as e:
        log.debug("Audit log write error: {}", e)


# ═══════════════════════════════════════════════════════
#  POSITION TRACKER
# ═══════════════════════════════════════════════════════

class PositionTracker:
    """Thread-safe registry of all open ManagedPosition objects."""

    def __init__(self):
        self._positions: Dict[str, ManagedPosition] = {}
        self._lock = asyncio.Lock()

    async def add(self, pos: ManagedPosition):
        async with self._lock:
            self._positions[pos.trade.id] = pos
            log.info("[POSITION] Tracking {} {} (id={})", pos.trade.direction, pos.trade.symbol, pos.trade.id[:8])

    async def remove(self, trade_id: str) -> Optional[ManagedPosition]:
        async with self._lock:
            pos = self._positions.pop(trade_id, None)
            if pos:
                log.info("[POSITION] Untracked {} ({})", pos.trade.symbol, trade_id[:8])
            return pos

    async def get_all(self) -> List[ManagedPosition]:
        async with self._lock:
            return list(self._positions.values())

    async def update_trade(self, trade_id: str, **kwargs):
        async with self._lock:
            if trade_id in self._positions:
                pos = self._positions[trade_id]
                for k, v in kwargs.items():
                    if hasattr(pos.trade, k):   setattr(pos.trade, k, v)
                    elif hasattr(pos, k):       setattr(pos, k, v)

    @property
    def count(self) -> int:
        return len(self._positions)


# Singleton
_tracker = PositionTracker()

def get_position_tracker() -> PositionTracker:
    return _tracker


# ═══════════════════════════════════════════════════════
#  STEP 3: DYNAMIC SL ENGINE
# ═══════════════════════════════════════════════════════

class DynamicSLEngine:
    """
    Tightens Stop-Loss when any of these trigger:
      - RSI crosses back through 50 against trade direction
      - MACD histogram flips against direction
      - Price closes back through EMA20 against direction
      - ADX collapses (trend losing strength)
    """

    def evaluate(
        self,
        pos:           ManagedPosition,
        df:            pd.DataFrame,
        conditions:    MarketConditions,
        current_price: float,
    ) -> Optional[float]:
        trade      = pos.trade
        current_sl = trade.stop_loss
        direction  = trade.direction
        atr        = conditions.atr
        rsi        = conditions.rsi
        adx        = conditions.adx

        ema20      = float(df["close"].ewm(span=20).mean().iloc[-1])
        macdh_now  = self._macdh(df, 0)
        macdh_prev = self._macdh(df, 1)

        triggers  = []
        new_sl    = current_sl

        if direction == Direction.BUY:
            # ── BUY: all tightening moves SL upward ──
            if rsi < 50 and trade.current_price and trade.current_price > trade.entry_price:
                candidate = current_price - atr * 1.0
                if candidate > current_sl:
                    new_sl = max(new_sl, candidate)
                    triggers.append(f"RSI dipped below 50 ({rsi:.1f})")

            if macdh_now < 0 and macdh_prev >= 0:
                candidate = current_price - atr * 0.8
                if candidate > current_sl:
                    new_sl = max(new_sl, candidate)
                    triggers.append("MACD histogram flipped negative")

            if df["close"].iloc[-1] < ema20 * 0.999:
                candidate = current_price - atr * 0.5
                if candidate > current_sl:
                    new_sl = max(new_sl, candidate)
                    triggers.append(f"Close below EMA20 ({ema20:.5f})")

            if adx < 20 and pos.conditions_at_entry.adx > 25:
                candidate = current_price - atr * 1.2
                if candidate > current_sl:
                    new_sl = max(new_sl, candidate)
                    triggers.append(f"ADX collapsed: {pos.conditions_at_entry.adx:.1f}→{adx:.1f}")

        else:  # SELL
            # ── SELL: all tightening moves SL downward ──
            if rsi > 50 and trade.current_price and trade.current_price < trade.entry_price:
                candidate = current_price + atr * 1.0
                if candidate < current_sl:
                    new_sl = min(new_sl, candidate)
                    triggers.append(f"RSI rose above 50 ({rsi:.1f})")

            if macdh_now > 0 and macdh_prev <= 0:
                candidate = current_price + atr * 0.8
                if candidate < current_sl:
                    new_sl = min(new_sl, candidate)
                    triggers.append("MACD histogram flipped positive")

            if df["close"].iloc[-1] > ema20 * 1.001:
                candidate = current_price + atr * 0.5
                if candidate < current_sl:
                    new_sl = min(new_sl, candidate)
                    triggers.append(f"Close above EMA20 ({ema20:.5f})")

            if adx < 20 and pos.conditions_at_entry.adx > 25:
                candidate = current_price + atr * 1.2
                if candidate < current_sl:
                    new_sl = min(new_sl, candidate)
                    triggers.append(f"ADX collapsed: {pos.conditions_at_entry.adx:.1f}→{adx:.1f}")

        if new_sl != current_sl and triggers:
            pos.sl_tightened_count += 1
            pos.log_event(
                f"SL TIGHTENED #{pos.sl_tightened_count}: "
                f"{current_sl:.5f} → {new_sl:.5f} ({new_sl-current_sl:+.5f}) | "
                f"Triggers: {', '.join(triggers)}"
            )
            return round(new_sl, 5)
        return None

    def _macdh(self, df: pd.DataFrame, offset: int = 0) -> float:
        ema12  = df["close"].ewm(span=12).mean()
        ema26  = df["close"].ewm(span=26).mean()
        macd   = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        hist   = macd - signal
        idx    = -(1 + offset)
        return float(hist.iloc[idx]) if len(hist) >= abs(idx) else 0.0


# ═══════════════════════════════════════════════════════
#  STEP 4: DYNAMIC TP ENGINE
# ═══════════════════════════════════════════════════════

class DynamicTPEngine:
    """
    Extends Take-Profit when:
      - ADX rising strongly (trend acceleration)
      - MACD histogram expanding in trade direction
      - Momentum surging (ROC > threshold)
      - Price already reached original TP
    """

    def evaluate(
        self,
        pos:           ManagedPosition,
        df:            pd.DataFrame,
        conditions:    MarketConditions,
        current_price: float,
    ) -> Optional[float]:
        trade       = pos.trade
        current_tp  = trade.take_profit
        direction   = trade.direction
        atr         = conditions.atr
        adx         = conditions.adx
        momentum    = conditions.momentum
        vol_ratio   = conditions.volume_ratio

        triggers    = []
        extension   = 0.0

        # Condition 1: ADX accelerating meaningfully
        if adx > 35 and adx > pos.conditions_at_entry.adx + 5:
            extension += atr * 1.0
            triggers.append(f"ADX accelerated {pos.conditions_at_entry.adx:.1f}→{adx:.1f}")

        # Condition 2: Momentum surge in trade direction
        if direction == Direction.BUY  and momentum > 0.5:
            extension += atr * 0.5
            triggers.append(f"Momentum +{momentum:.2f}%")
        elif direction == Direction.SELL and momentum < -0.5:
            extension += atr * 0.5
            triggers.append(f"Momentum {momentum:.2f}%")

        # Condition 3: Volume surge confirming the move
        if vol_ratio > 2.0:
            extension += atr * 0.3
            triggers.append(f"Volume surge ×{vol_ratio:.1f}")

        # Condition 4: Price already hit/exceeded original TP
        if direction == Direction.BUY  and current_price >= current_tp * 0.998:
            extension += atr * 1.5
            triggers.append("Original TP reached — extending")
        elif direction == Direction.SELL and current_price <= current_tp * 1.002:
            extension += atr * 1.5
            triggers.append("Original TP reached — extending")

        if extension <= 0 or not triggers:
            return None

        new_tp = current_tp + extension if direction == Direction.BUY else current_tp - extension

        # Validate new R:R is still at least 1.5:1
        sl_dist = abs(current_price - trade.stop_loss)
        tp_dist = abs(new_tp - current_price)
        if sl_dist > 0 and (tp_dist / sl_dist) < 1.5:
            return None

        pos.tp_extended_count += 1
        pos.log_event(
            f"TP EXTENDED #{pos.tp_extended_count}: "
            f"{current_tp:.5f} → {new_tp:.5f} (+{extension:.5f}) | "
            f"New R:R {tp_dist/sl_dist:.1f}:1 | "
            f"Triggers: {', '.join(triggers)}"
        )
        return round(new_tp, 5)


# ═══════════════════════════════════════════════════════
#  STEP 5: TRAILING STOP ENGINE
# ═══════════════════════════════════════════════════════

class TrailingStopEngine:
    """
    Manages trailing stops as price moves favourably.
    Activates after 1 ATR profit. Supports 4 modes.
    """

    def evaluate(
        self,
        pos:           ManagedPosition,
        df:            pd.DataFrame,
        conditions:    MarketConditions,
        current_price: float,
        mode:          TrailingMode = TrailingMode.ATR,
    ) -> Optional[float]:
        trade     = pos.trade
        current_sl = trade.stop_loss
        direction  = trade.direction
        entry      = trade.entry_price
        atr        = conditions.atr

        # Track price extremes
        if direction == Direction.BUY:
            if current_price > pos.highest_price:
                pos.highest_price = current_price
        else:
            if current_price < pos.lowest_price:
                pos.lowest_price = current_price

        # Calculate profit in ATR multiples
        profit_atr = 0.0
        if atr > 0:
            raw = (current_price - entry) if direction == Direction.BUY else (entry - current_price)
            profit_atr = raw / atr

        # Activate trailing after 1 ATR profit
        if profit_atr >= 1.0 and not pos.trailing_active:
            pos.trailing_active = True
            pos.log_event(f"TRAILING STOP ACTIVATED — profit={profit_atr:.1f} ATR at {current_price:.5f}")

        if not pos.trailing_active:
            return None

        new_sl: Optional[float] = None

        if mode == TrailingMode.ATR:
            peak = pos.highest_price if direction == Direction.BUY else pos.lowest_price
            new_sl = peak - atr * 1.5 if direction == Direction.BUY else peak + atr * 1.5

        elif mode == TrailingMode.STEP:
            step = atr * 0.5
            if direction == Direction.BUY:
                steps  = math.floor((current_price - entry) / step)
                new_sl = entry + steps * step - atr * 1.5
            else:
                steps  = math.floor((entry - current_price) / step)
                new_sl = entry - steps * step + atr * 1.5

        elif mode == TrailingMode.BREAKEVEN:
            if not pos.breakeven_triggered and profit_atr >= 1.0:
                be_level = entry + atr * 0.1 if direction == Direction.BUY else entry - atr * 0.1
                pos.breakeven_triggered = True
                pos.log_event(f"BREAK-EVEN triggered — SL→{be_level:.5f}")
                new_sl = be_level
            elif pos.breakeven_triggered:
                peak   = pos.highest_price if direction == Direction.BUY else pos.lowest_price
                new_sl = peak - atr if direction == Direction.BUY else peak + atr

        elif mode == TrailingMode.PARABOLIC:
            new_sl = self._parabolic_sar(df, direction, current_sl)

        if new_sl is None:
            return None

        # Trailing SL must only move in the profitable direction
        if direction == Direction.BUY  and new_sl <= current_sl: return None
        if direction == Direction.SELL and new_sl >= current_sl: return None

        pos.log_event(
            f"TRAILING SL [{mode.value}]: {current_sl:.5f} → {new_sl:.5f} "
            f"({new_sl-current_sl:+.5f}) | Price={current_price:.5f} | "
            f"Peak={pos.highest_price:.5f}"
        )
        return round(new_sl, 5)

    def _parabolic_sar(self, df: pd.DataFrame, direction: Direction, current_sl: float) -> Optional[float]:
        try:
            import pandas_ta as ta
            sar = df.ta.psar()
            if sar is not None:
                col = "PSARl_0.02_0.2" if direction == Direction.BUY else "PSARs_0.02_0.2"
                if col in sar.columns:
                    val = sar[col].dropna().iloc[-1]
                    if not pd.isna(val):
                        return float(val)
        except Exception:
            pass
        return None


# ═══════════════════════════════════════════════════════
#  POSITION MANAGER  (the full real-time management loop)
# ═══════════════════════════════════════════════════════

class PositionManager:
    """
    Polls every `poll_interval` seconds and runs the full 6-step
    management cycle for every tracked open position.
    """

    def __init__(self, broker, tracker: PositionTracker, poll_interval: int = 15):
        self.broker        = broker
        self.tracker       = tracker
        self.poll_interval = poll_interval
        self.risk_mgr      = AdaptiveRiskManager()
        self.sl_engine     = DynamicSLEngine()
        self.tp_engine     = DynamicTPEngine()
        self.trail_engine  = TrailingStopEngine()
        self._running      = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task    = asyncio.create_task(self._loop())
        log.info("🔄 PositionManager STARTED — poll interval={}s", self.poll_interval)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        log.info("🛑 PositionManager STOPPED")

    # ── Main polling loop ─────────────────────────────

    async def _loop(self):
        while self._running:
            try:
                positions = await self.tracker.get_all()
                if positions:
                    log.info("🔄 PositionManager: managing {} open position(s)…", len(positions))
                    results = await asyncio.gather(
                        *[self._manage_one(pos) for pos in positions],
                        return_exceptions=True,
                    )
                    for r in results:
                        if isinstance(r, Exception):
                            log.error("PositionManager sub-task error: {}", r)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("PositionManager loop error: {}", e)
            await asyncio.sleep(self.poll_interval)

    async def _manage_one(self, pos: ManagedPosition):
        """Full 6-step cycle for one position."""
        trade  = pos.trade
        symbol = trade.symbol

        # ──────────────────────────────────────────────
        # STEP 1: Verify position still exists on broker
        # ──────────────────────────────────────────────
        still_open = await self._verify_position(pos)
        if not still_open:
            await self._handle_closed_position(pos, reason="Not found on broker (SL/TP/manual close)")
            return

        # ──────────────────────────────────────────────
        # STEP 2: Fetch live market data + recalculate
        # ──────────────────────────────────────────────
        from data.market_feed import MarketFeed
        feed  = MarketFeed()
        bars  = await feed.get_ohlcv(symbol, "H1", bars=200)
        if not bars or len(bars) < 50:
            log.warning("PositionManager: insufficient bars for {}", symbol)
            return

        df            = _bars_to_df(bars)
        quote         = await feed.get_quote(symbol)
        current_price = quote.mid if quote else float(df["close"].iloc[-1])

        await self.tracker.update_trade(trade.id, current_price=current_price)
        trade.current_price = current_price

        conditions = await self.risk_mgr.analyse(df, symbol, "H1")
        pnl        = _calc_pnl(trade, current_price)
        await self.tracker.update_trade(trade.id, pnl=pnl)

        log.info(
            "📊 {} {} | Px={:.5f} Entry={:.5f} | PnL={:+.2f} | "
            "SL={:.5f} TP={:.5f} | {} | RSI={:.1f} ADX={:.1f}",
            trade.direction, symbol, current_price, trade.entry_price,
            pnl, trade.stop_loss, trade.take_profit,
            conditions.regime.value, conditions.rsi, conditions.adx,
        )

        new_sl   = trade.stop_loss
        new_tp   = trade.take_profit
        modified = False

        # ──────────────────────────────────────────────
        # STEP 3: Dynamic SL — tighten if trend weakens
        # ──────────────────────────────────────────────
        sl_update = self.sl_engine.evaluate(pos, df, conditions, current_price)
        if sl_update is not None:
            new_sl   = sl_update
            modified = True

        # ──────────────────────────────────────────────
        # STEP 4: Dynamic TP — extend if trend accelerates
        # ──────────────────────────────────────────────
        tp_update = self.tp_engine.evaluate(pos, df, conditions, current_price)
        if tp_update is not None:
            new_tp   = tp_update
            modified = True

        # ──────────────────────────────────────────────
        # STEP 5: Trailing stop — follow price
        # ──────────────────────────────────────────────
        trail_update = self.trail_engine.evaluate(pos, df, conditions, current_price, TrailingMode.ATR)
        if trail_update is not None:
            # Trailing takes precedence — it's always tighter
            if trade.direction == Direction.BUY  and trail_update > new_sl:
                new_sl = trail_update; modified = True
            elif trade.direction == Direction.SELL and trail_update < new_sl:
                new_sl = trail_update; modified = True

        # ── Apply broker modification if needed ───────
        if modified:
            try:
                await self.broker.modify_trade(trade, sl=new_sl, tp=new_tp)
                await self.tracker.update_trade(trade.id, stop_loss=new_sl, take_profit=new_tp)
                pos.last_sl = new_sl
                pos.last_tp = new_tp
                log.info("✏️ {} MODIFIED | SL={:.5f} TP={:.5f}", symbol, new_sl, new_tp)
            except Exception as e:
                log.error("modify_trade FAILED for {}: {}", symbol, e)

        pos.last_managed_at = datetime.utcnow()

    # ── Step 1: verify position exists ───────────────

    async def _verify_position(self, pos: ManagedPosition) -> bool:
        """Return True if position still open at broker."""
        try:
            broker_trades = await self.broker.get_open_trades()
            broker_ids    = {t.broker_order_id for t in broker_trades}
            exists        = pos.trade.broker_order_id in broker_ids
            if not exists:
                log.info("📋 PositionVerifier: {} {} closed externally (order#{})",
                         pos.trade.direction, pos.trade.symbol, pos.trade.broker_order_id)
            return exists
        except Exception as e:
            log.warning("PositionVerifier error for {}: {} — assuming open", pos.trade.symbol, e)
            return True   # Safe default: assume open if check fails

    # ── Step 6: handle + clean up closed positions ───

    async def _handle_closed_position(self, pos: ManagedPosition, reason: str):
        """Detect close price, compute final P&L, log audit record, remove from tracker."""
        trade = pos.trade
        try:
            quote       = await self.broker.get_quote(trade.symbol)
            close_price = quote.mid
        except Exception:
            close_price = trade.current_price or trade.entry_price

        final_pnl         = _calc_pnl(trade, close_price)
        duration          = _duration_str(trade.open_time)
        trade.status      = TradeStatus.CLOSED
        trade.close_price = close_price
        trade.close_time  = datetime.utcnow()
        trade.pnl         = final_pnl
        pos.closed_reason = reason

        log.info(
            "📋 POSITION CLOSED | {} {} | "
            "Entry={:.5f} Close={:.5f} | PnL={:+.2f} | "
            "Duration={} | Reason={} | "
            "SL_tightenings={} | TP_extensions={} | Trailing={}",
            trade.direction, trade.symbol,
            trade.entry_price, close_price, final_pnl,
            duration, reason,
            pos.sl_tightened_count, pos.tp_extended_count, pos.trailing_active,
        )

        # Log last N management events
        if pos.management_log:
            recent = pos.management_log[-10:]
            log.info("📋 Last {} management events for {}:\n  {}",
                     len(recent), trade.symbol, "\n  ".join(recent))

        # Write closed record to JSONL audit trail
        closed_entry = {
            "type": "CLOSED", "trade_id": trade.id,
            "symbol": trade.symbol, "direction": str(trade.direction),
            "entry_price": trade.entry_price, "close_price": close_price,
            "final_pnl": final_pnl, "close_reason": reason,
            "open_time": str(trade.open_time), "close_time": str(trade.close_time),
            "duration": duration,
            "sl_tightened_count": pos.sl_tightened_count,
            "tp_extended_count":  pos.tp_extended_count,
            "trailing_active":    pos.trailing_active,
            "management_events":  len(pos.management_log),
        }
        try:
            from pathlib import Path
            log_path = Path("logs") / f"trades_{datetime.utcnow().strftime('%Y-%m-%d')}.jsonl"
            with open(log_path, "a") as f:
                f.write(json.dumps(closed_entry, default=str) + "\n")
        except Exception as e:
            log.debug("Closed trade audit write error: {}", e)

        # Step 6: Clean up — remove from tracker
        await self.tracker.remove(trade.id)


# ═══════════════════════════════════════════════════════
#  TECHNICAL ANALYSER  (signal generation, regime-aware)
# ═══════════════════════════════════════════════════════

class TechnicalAnalyser:
    """
    Generates TradingSignals using all enabled strategies.
    Each signal includes market regime context for downstream sizing.
    """

    def __init__(self):
        self.strategies = settings.strategy.enabled_strategies
        self.timeframes  = settings.strategy.timeframes
        self.risk_mgr    = AdaptiveRiskManager()

    async def analyse(self, symbol: str, quote) -> list[TradingSignal]:
        from data.market_feed import MarketFeed
        feed    = MarketFeed()
        signals: list[TradingSignal] = []

        for tf in self.timeframes:
            try:
                bars = await feed.get_ohlcv(symbol, tf, bars=200)
                if not bars or len(bars) < 50:
                    continue
                df         = _bars_to_df(bars)
                conditions = await self.risk_mgr.analyse(df, symbol, tf)

                # Skip highly volatile conditions — too risky for automated entry
                if conditions.regime == MarketRegime.HIGH_VOLATILE:
                    log.info("⛔ {} {} — HIGH_VOLATILE regime, skipping signal generation", symbol, tf)
                    continue

                if "ai_momentum" in self.strategies:
                    sig = self._ai_momentum(df, symbol, tf, quote, conditions)
                    if sig: 
                        sig = self._apply_smc_confluence(df, sig)
                        signals.append(sig)

                if "mean_reversion" in self.strategies:
                    if conditions.regime in (MarketRegime.RANGING, MarketRegime.LOW_VOLATILE):
                        sig = self._mean_reversion(df, symbol, tf, quote, conditions)
                        if sig: 
                            sig = self._apply_smc_confluence(df, sig)
                            signals.append(sig)

                if "breakout" in self.strategies:
                    if conditions.regime in (MarketRegime.BREAKOUT, MarketRegime.STRONG_TREND):
                        sig = self._breakout(df, symbol, tf, quote, conditions)
                        if sig: 
                            sig = self._apply_smc_confluence(df, sig)
                            signals.append(sig)

            except Exception as e:
                log.debug("Technical error {} {}: {}", symbol, tf, e)

        return signals
    async def analyse_from_indicators(
        self,
        symbol: str,
        ohlcv: list[dict],
        indicators: dict,
        quote,
        market_regime: str = "WEAK_TREND"
    ) -> list[TradingSignal]:
        """
        Generate signals using pre-computed indicators (fast path).
        Avoids re-computing indicators that are already cached.
        """
        if not ohlcv or len(ohlcv) < 50:
            return []

        try:
            # Convert to DataFrame
            df = _bars_to_df(ohlcv)

            # Create MarketConditions from pre-computed indicators
            conditions = MarketConditions(
                symbol=symbol,
                timeframe=self.timeframe,
                adx=indicators.get("adx", 20.0),
                atr=indicators.get("atr", 0.0),
                atr_pct=indicators.get("atr_pct", 0.0),
                atr_ratio=indicators.get("atr_ratio", 1.0),
                rsi=indicators.get("rsi", 50.0),
                momentum=indicators.get("momentum", 0.0),
                volume_ratio=indicators.get("volume_ratio", 1.0),
                bb_width=indicators.get("bb_width", 0.0),
            )

            # Classify regime
            conditions.regime = self._classify_regime_from_indicators(indicators)
            conditions.risk_multiplier = self._calc_risk_multiplier(conditions)

            # Generate signals using existing strategies
            signals = []

            # Try each strategy
            sig = self._ai_momentum(df, symbol, self.timeframe, quote, conditions)
            if sig:
                signals.append(sig)

            sig = self._mean_reversion(df, symbol, self.timeframe, quote, conditions)
            if sig:
                signals.append(sig)

            sig = self._breakout(df, symbol, self.timeframe, quote, conditions)
            if sig:
                signals.append(sig)

            return signals

        except Exception as e:
            log.error(f"Error analyzing {symbol} from indicators: {e}")
            return []

    def _classify_regime_from_indicators(self, indicators: dict) -> MarketRegime:
        """Classify market regime from pre-computed indicators"""
        adx = indicators.get("adx", 20.0)
        atr_ratio = indicators.get("atr_ratio", 1.0)

        if atr_ratio > 2.0:
            return MarketRegime.HIGH_VOLATILE
        elif atr_ratio < 0.5:
            return MarketRegime.LOW_VOLATILE
        elif adx > 35:
            return MarketRegime.STRONG_TREND
        elif adx > 20:
            return MarketRegime.WEAK_TREND
        else:
            return MarketRegime.RANGING


    # ── STRATEGY 1: AI Momentum ──────────────────────

    def _ai_momentum(self, df, symbol, tf, quote, conditions: MarketConditions) -> Optional[TradingSignal]:
        """EMA trend + RSI + MACD + Volume + ADX. ATR SL/TP scaled by regime."""
        try:
            import pandas_ta as ta
        except ImportError:
            return self._fallback_signal(df, symbol, tf, quote, "ai_momentum", conditions)

        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df.ta.ema(length=200, append=True)
        df.ta.rsi(length=14, append=True)
        df.ta.macd(append=True)

        last  = df.iloc[-1]
        prev  = df.iloc[-2]
        ema20 = last.get("EMA_20")
        ema50 = last.get("EMA_50")
        ema200= last.get("EMA_200")
        rsi   = last.get("RSI_14", conditions.rsi)
        macdh = last.get("MACDh_12_26_9", 0)
        pmach = prev.get("MACDh_12_26_9", 0)

        if None in (ema20, ema50):
            return None
        if conditions.adx < 18:
            return None   # Not enough trend for momentum strategy

        score, direction, reasons = 0.0, None, []

        if ema20 > ema50:
            direction = Direction.BUY;  score += 2.0
            reasons.append(f"EMA20 {ema20:.4f} > EMA50 {ema50:.4f}")
        else:
            direction = Direction.SELL; score += 2.0
            reasons.append(f"EMA20 {ema20:.4f} < EMA50 {ema50:.4f}")

        if ema200:
            if direction == Direction.BUY  and last["close"] > ema200:
                score += 1.5; reasons.append("Price > EMA200 — HTF bull")
            elif direction == Direction.SELL and last["close"] < ema200:
                score += 1.5; reasons.append("Price < EMA200 — HTF bear")

        if direction == Direction.BUY:
            if   50 < rsi < 72: score += 2.0; reasons.append(f"RSI {rsi:.1f} bullish zone")
            elif rsi < 35:      score += 1.5; reasons.append(f"RSI {rsi:.1f} oversold")
        else:
            if   28 < rsi < 50: score += 2.0; reasons.append(f"RSI {rsi:.1f} bearish zone")
            elif rsi > 65:      score += 1.5; reasons.append(f"RSI {rsi:.1f} overbought")

        if   direction == Direction.BUY  and macdh > 0 and pmach <= 0:
            score += 2.5; reasons.append("MACD bullish crossover ★")
        elif direction == Direction.SELL and macdh < 0 and pmach >= 0:
            score += 2.5; reasons.append("MACD bearish crossover ★")
        elif direction == Direction.BUY  and macdh > 0:
            score += 1.0; reasons.append("MACD positive histogram")
        elif direction == Direction.SELL and macdh < 0:
            score += 1.0; reasons.append("MACD negative histogram")

        avg_vol = df["volume"].rolling(20).mean().iloc[-1]
        if last["volume"] > avg_vol * 1.2:
            score += 1.5; reasons.append(f"Volume ×{last['volume']/avg_vol:.1f}")
        if conditions.adx > 30:
            score += 1.0; reasons.append(f"ADX={conditions.adx:.1f} strong trend")

        if score < settings.strategy.min_signal_score:
            return None

        atr   = conditions.atr
        entry = quote.ask if direction == Direction.BUY else quote.bid
        sl_m  = {MarketRegime.STRONG_TREND:1.2, MarketRegime.WEAK_TREND:1.5,
                 MarketRegime.RANGING:2.0, MarketRegime.LOW_VOLATILE:1.8,
                 MarketRegime.BREAKOUT:1.3}.get(conditions.regime, 1.5)
        tp_m  = sl_m * 2.0
        sl    = entry - atr*sl_m if direction == Direction.BUY else entry + atr*sl_m
        tp    = entry + atr*tp_m if direction == Direction.BUY else entry - atr*tp_m
        rr    = round((atr*tp_m) / (atr*sl_m), 2)

        return TradingSignal(
            id=str(uuid.uuid4()), symbol=symbol,
            asset_class=_asset_class(symbol), direction=direction,
            score=round(min(score,10),1),
            confidence=round(min(score/10.5, 0.95),2),
            strength=SignalStrength.STRONG if score >= 8.5 else SignalStrength.MEDIUM,
            strategy="ai_momentum", timeframe=tf,
            entry_price=round(entry,5), stop_loss=round(sl,5), take_profit=round(tp,5),
            risk_reward=rr, reasoning=" | ".join(reasons),
            metadata={"regime":conditions.regime.value,"adx":conditions.adx,
                      "atr":conditions.atr,"atr_pct":conditions.atr_pct,
                      "atr_ratio":conditions.atr_ratio,"rsi":conditions.rsi,
                      "volume_ratio":conditions.volume_ratio,
                      "risk_multiplier":conditions.risk_multiplier},
        )

    # ── STRATEGY 2: Mean Reversion ───────────────────

    def _mean_reversion(self, df, symbol, tf, quote, conditions: MarketConditions) -> Optional[TradingSignal]:
        """BB extremes + RSI + Stochastic. Only fires in RANGING / LOW_VOLATILE."""
        try:
            import pandas_ta as ta
            df.ta.bbands(length=20, std=2.0, append=True)
            df.ta.rsi(length=14, append=True)
            df.ta.stoch(append=True)
        except ImportError:
            return None

        last     = df.iloc[-1]
        close    = last["close"]
        bbu      = last.get("BBU_20_2.0")
        bbl      = last.get("BBL_20_2.0")
        bbm      = last.get("BBM_20_2.0")
        rsi      = last.get("RSI_14", conditions.rsi)
        stoch_k  = last.get("STOCHk_14_3_3", 50)

        if None in (bbu, bbl, bbm):
            return None

        direction, score, reasons = None, 0.0, []

        if close <= bbl * 1.002 and rsi < 35:
            direction = Direction.BUY
            score     = 7.0 + (35 - rsi) * 0.08
            reasons   = [f"At lower BB ({bbl:.5f}) | RSI oversold {rsi:.1f}"]
            if stoch_k and stoch_k < 25:
                score += 1.0; reasons.append(f"Stoch oversold {stoch_k:.1f}")
        elif close >= bbu * 0.998 and rsi > 65:
            direction = Direction.SELL
            score     = 7.0 + (rsi - 65) * 0.08
            reasons   = [f"At upper BB ({bbu:.5f}) | RSI overbought {rsi:.1f}"]
            if stoch_k and stoch_k > 75:
                score += 1.0; reasons.append(f"Stoch overbought {stoch_k:.1f}")

        if direction is None or score < settings.strategy.min_signal_score:
            return None

        atr   = conditions.atr
        entry = quote.ask if direction == Direction.BUY else quote.bid
        sl    = entry - atr*2.5 if direction == Direction.BUY else entry + atr*2.5
        tp    = float(bbm)
        tp_d  = abs(tp - entry)
        sl_d  = abs(sl - entry)
        if sl_d <= 0 or tp_d / sl_d < 1.2:
            return None

        return TradingSignal(
            id=str(uuid.uuid4()), symbol=symbol,
            asset_class=_asset_class(symbol), direction=direction,
            score=round(min(score,10),1),
            confidence=round(min(score/11, 0.90),2),
            strength=SignalStrength.MEDIUM,
            strategy="mean_reversion", timeframe=tf,
            entry_price=round(entry,5), stop_loss=round(sl,5), take_profit=round(tp,5),
            risk_reward=round(tp_d/sl_d,2), reasoning=" | ".join(reasons),
            metadata={"regime":conditions.regime.value,"adx":conditions.adx,
                      "atr":conditions.atr,"atr_pct":conditions.atr_pct,
                      "atr_ratio":conditions.atr_ratio,"rsi":conditions.rsi,
                      "volume_ratio":conditions.volume_ratio,"bb_width":conditions.bb_width},
        )

    # ── STRATEGY 3: Breakout ─────────────────────────

    def _breakout(self, df, symbol, tf, quote, conditions: MarketConditions) -> Optional[TradingSignal]:
        """Volume-confirmed breakout from compressed BB range."""
        last      = df.iloc[-1]
        close     = last["close"]
        lookback  = df.tail(20)
        rh        = float(lookback["high"].max())
        rl        = float(lookback["low"].min())
        rng       = rh - rl

        if rng <= 0 or conditions.bb_width > 3.0:
            return None

        avg_vol   = df["volume"].rolling(20).mean().iloc[-1]
        vol_surge = last["volume"] > avg_vol * 1.8
        atr       = conditions.atr

        direction, score, reasons = None, 6.5, []
        if close > rh and vol_surge:
            direction = Direction.BUY
            reasons.append(f"Breakout > {rh:.5f} | Vol ×{last['volume']/avg_vol:.1f}")
            score += conditions.volume_ratio * 0.5
        elif close < rl and vol_surge:
            direction = Direction.SELL
            reasons.append(f"Breakdown < {rl:.5f} | Vol ×{last['volume']/avg_vol:.1f}")
            score += conditions.volume_ratio * 0.5

        if direction is None or score < settings.strategy.min_signal_score:
            return None

        entry = quote.ask if direction == Direction.BUY else quote.bid
        sl    = entry - atr*1.5 if direction == Direction.BUY else entry + atr*1.5
        tp    = entry + rng*1.5 if direction == Direction.BUY else entry - rng*1.5
        rr    = abs(tp-entry)/abs(sl-entry)
        if rr < 1.5: return None

        return TradingSignal(
            id=str(uuid.uuid4()), symbol=symbol,
            asset_class=_asset_class(symbol), direction=direction,
            score=round(min(score,10),1), confidence=round(min(score/10,0.88),2),
            strength=SignalStrength.MEDIUM,
            strategy="breakout", timeframe=tf,
            entry_price=round(entry,5), stop_loss=round(sl,5), take_profit=round(tp,5),
            risk_reward=round(rr,2), reasoning=" | ".join(reasons),
            metadata={"regime":conditions.regime.value,"adx":conditions.adx,
                      "atr":conditions.atr,"atr_pct":conditions.atr_pct,
                      "atr_ratio":conditions.atr_ratio,"rsi":conditions.rsi,
                      "volume_ratio":conditions.volume_ratio,
                      "bb_width":conditions.bb_width,"range_size":rng},
        )

    # ── SMC CONFLUENCE FILTER ────────────────────────
    def _apply_smc_confluence(self, df: pd.DataFrame, signal: TradingSignal) -> TradingSignal:
        """
        Refines signal score based on Smart Money Concepts (SMC).
        SMC acts as a multiplier (0.8x to 1.2x) rather than a primary trigger.
        """
        obs = self._detect_order_blocks(df)
        fvgs = self._detect_fvg(df)
        
        last = df.iloc[-1]
        close = last["close"]
        multiplier = 1.0
        confluences = []

        # 1. Order Block (OB) Confluence
        # Price currently sitting in a fresh OB of the same direction
        relevant_ob = next((ob for ob in obs if ob['type'] == ('BULLISH' if signal.direction == Direction.BUY else 'BEARISH') 
                           and ob['low'] <= close <= ob['high']), None)
        
        if relevant_ob:
            multiplier += 0.15
            confluences.append(f"OB Support (+15%)")
        
        # 2. Fair Value Gap (FVG) Confluence
        # Unfilled FVG just below (for BUY) or above (for SELL) price acting as a magnet
        # This is high-probability logic if price just bounced off it
        recent_fvg = next((fvg for fvg in fvgs if fvg['type'] == ('BULLISH' if signal.direction == Direction.BUY else 'BEARISH')), None)
        
        if recent_fvg:
            # For a buy, we want the FVG to be below the current price (support)
            fvg_is_support = (signal.direction == Direction.BUY and recent_fvg['top'] <= close)
            fvg_is_resistance = (signal.direction == Direction.SELL and recent_fvg['bottom'] >= close)
            
            if fvg_is_support or fvg_is_resistance:
                multiplier += 0.10
                confluences.append(f"FVG Confluence (+10%)")

        # Apply multiplier to score and confidence
        old_score = signal.score
        signal.score = round(min(10.0, signal.score * multiplier), 1)
        signal.confidence = round(min(1.0, signal.confidence * multiplier), 2)
        
        if confluences:
            signal.reasoning += f" | SMC Filter (x{multiplier:.2f}): " + ", ".join(confluences)
            log.info("📊 SMC Filter: {} {} score {:.1f} -> {:.1f} | {}", 
                     signal.symbol, signal.direction, old_score, signal.score, ", ".join(confluences))
        
        return signal

    def _detect_order_blocks(self, df: pd.DataFrame, lookback: int = 50) -> list[dict]:
        """
        Standardized OB Detection:
        Bullish OB: Last down-candle before a break of structure (BOS) or 2x ATR move.
        Bearish OB: Last up-candle before a break of structure (BOS) or 2x ATR move.
        """
        obs = []
        atr = _calc_atr(df, 14)
        
        for i in range(len(df) - lookback, len(df) - 5):
            # Bullish OB: Red candle followed by large green move
            if df.iloc[i]['close'] < df.iloc[i]['open']:
                move = df.iloc[i+1:i+4]['close'].max() - df.iloc[i]['close']
                if move > atr * 1.5:  # Scaled by ATR for determinism
                    obs.append({'type': 'BULLISH', 'high': df.iloc[i]['high'], 'low': df.iloc[i]['low'], 'index': i})
            # Bearish OB: Green candle followed by large red move
            elif df.iloc[i]['close'] > df.iloc[i]['open']:
                move = df.iloc[i]['close'] - df.iloc[i+1:i+4]['close'].min()
                if move > atr * 1.5:
                    obs.append({'type': 'BEARISH', 'high': df.iloc[i]['high'], 'low': df.iloc[i]['low'], 'index': i})
        return obs

    def _detect_fvg(self, df: pd.DataFrame) -> list[dict]:
        """Detects Fair Value Gaps (imbalances) with strict gap rules."""
        fvgs = []
        for i in range(len(df) - 20, len(df) - 2):
            # Bullish FVG: Low(i+2) > High(i)
            if df.iloc[i+2]['low'] > df.iloc[i]['high']:
                fvgs.append({'type': 'BULLISH', 'bottom': df.iloc[i]['high'], 'top': df.iloc[i+2]['low']})
            # Bearish FVG: High(i+2) < Low(i)
            elif df.iloc[i+2]['high'] < df.iloc[i]['low']:
                fvgs.append({'type': 'BEARISH', 'top': df.iloc[i]['low'], 'bottom': df.iloc[i+2]['high']})
        return fvgs

    def _detect_rsi_divergence(self, df: pd.DataFrame) -> Optional[str]:
        """Detects simple RSI price/indicator divergence."""
        if 'RSI_14' not in df.columns: return None
        # Last 2 local peaks/troughs
        recent = df.tail(20)
        # Simplified: check start vs end of window
        p1, p2 = recent.iloc[0]['close'], recent.iloc[-1]['close']
        r1, r2 = recent.iloc[0]['RSI_14'], recent.iloc[-1]['RSI_14']
        
        if p2 < p1 and r2 > r1: return 'BULLISH'
        if p2 > p1 and r2 < r1: return 'BEARISH'
        return None

    def _fallback_signal(self, df, symbol, tf, quote, strategy, conditions) -> Optional[TradingSignal]:
        """Simple EMA crossover when pandas_ta unavailable."""
        if len(df) < 50: return None
        ema20 = float(df["close"].ewm(span=20).mean().iloc[-1])
        ema50 = float(df["close"].ewm(span=50).mean().iloc[-1])
        direction = Direction.BUY if ema20 > ema50 else Direction.SELL
        entry = quote.ask if direction == Direction.BUY else quote.bid
        atr   = _calc_atr(df, 14)
        sl    = entry - atr*1.5 if direction == Direction.BUY else entry + atr*1.5
        tp    = entry + atr*2.5 if direction == Direction.BUY else entry - atr*2.5
        return TradingSignal(
            id=str(uuid.uuid4()), symbol=symbol, asset_class=_asset_class(symbol),
            direction=direction, score=6.5, confidence=0.60,
            strength=SignalStrength.MEDIUM, strategy=strategy, timeframe=tf,
            entry_price=round(entry,5), stop_loss=round(sl,5), take_profit=round(tp,5),
            risk_reward=round(abs(tp-entry)/abs(sl-entry),2),
            reasoning="EMA crossover (fallback)",
            metadata={"regime":conditions.regime.value,"adx":conditions.adx,
                      "atr":conditions.atr,"atr_pct":conditions.atr_pct,
                      "atr_ratio":conditions.atr_ratio,"rsi":conditions.rsi,
                      "volume_ratio":conditions.volume_ratio},
        )


# ═══════════════════════════════════════════════════════
#  SHARED HELPERS
# ═══════════════════════════════════════════════════════

def _bars_to_df(bars: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(bars)
    df.columns = [c.lower() for c in df.columns]
    df = df.rename(columns={"timestamp": "time"})
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["close"])
    return df.reset_index(drop=True)


def _calc_atr(df: pd.DataFrame, period: int = 14) -> float:
    high, low, close = df["high"], df["low"], df["close"]
    tr  = pd.concat([high - low,
                     (high - close.shift()).abs(),
                     (low  - close.shift()).abs()], axis=1).max(axis=1)
    val = tr.rolling(period).mean().iloc[-1]
    return float(val) if not pd.isna(val) else float(high.iloc[-1] - low.iloc[-1])


def _point_value(symbol: str) -> float:
    """Approximate point value per lot. Override with broker contract spec in production."""
    s = symbol.upper()
    if "JPY" in s: return 1_000
    if "XAU" in s: return 100
    if "XAG" in s: return 50
    if "BTC" in s: return 1
    if "OIL" in s: return 1_000
    return 10_000   # default forex


def _calc_pnl(trade: Trade, current_price: float) -> float:
    diff = current_price - trade.entry_price
    if trade.direction == Direction.SELL:
        diff = -diff
    pv = _point_value(trade.symbol)
    return round(diff * trade.lot_size * pv / 100, 2)


def _duration_str(open_time: Optional[datetime]) -> str:
    if not open_time: return "unknown"
    delta = datetime.utcnow() - open_time
    hours, rem = divmod(int(delta.total_seconds()), 3600)
    return f"{hours}h {rem//60}m"
