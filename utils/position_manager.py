"""
APEX Bot — Position Manager (SOP Sections 03-07, 10)
=====================================================
Implements the 10-step management cycle that runs every 15 seconds:

  Step 1  — Verify position still open in broker
  Step 2  — Refresh OHLCV data + recalculate indicators
  Step 3  — Recalculate market conditions (regime)
  Step 4  — Dynamic SL check (8 tightening triggers)
  Step 5  — Dynamic TP check (6 extension / 5 reduction triggers)
  Step 6  — Trailing stop update (ATR / Step / Breakeven / PSAR)
  Step 7  — Apply SL/TP modifications to broker
  Step 8  — Write updated state to DuckDB
  Step 9  — Detect external closes, log final P&L
  Step 10 — Evaluate T2/T3 tranche conditions

SL can only move toward profit. TP managed adaptively.
"""
from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from core.config import (
    settings,
    REGIME_SL_MULTIPLIERS,
    REGIME_TP_MULTIPLIERS,
    REGIME_TRAIL_MODE,
)
from core.logger import get_agent_logger
from core.models import Trade, Direction

log = get_agent_logger("POSMGR")


# ── In-memory position state tracker ──────────────────────────────────────────
class _PositionState:
    """Ephemeral state attached to each open trade for the management cycle."""
    __slots__ = (
        "trade_id", "symbol", "direction", "entry_price",
        "lot_size", "current_sl", "current_tp",
        "regime", "atr",
        "trailing_active", "trail_mode", "peak_price",
        "tp_extended_count", "tp_reduced", "sl_session",
        "tranche", "lots_t1", "lots_t2", "lots_t3",
        "t2_opened", "t3_opened",
        "last_adx_at_entry", "sl_tightened_this_session",
    )

    def __init__(self, trade: Trade):
        self.trade_id    = trade.id
        self.symbol      = trade.symbol
        self.direction   = trade.direction
        self.entry_price = trade.entry_price
        self.lot_size    = trade.lot_size
        self.current_sl  = trade.stop_loss
        self.current_tp  = trade.take_profit
        self.regime      = trade.metadata.get("regime", "WEAK_TREND") if trade.metadata else "WEAK_TREND"
        self.atr         = trade.metadata.get("atr", 0.0) if trade.metadata else 0.0
        self.trailing_active = False
        self.trail_mode  = REGIME_TRAIL_MODE.get(self.regime, "STEP")
        self.peak_price  = trade.entry_price
        self.tp_extended_count = 0
        self.tp_reduced  = False
        self.sl_session  = trade.stop_loss
        self.tranche     = trade.metadata.get("tranche", "T1") if trade.metadata else "T1"
        self.lots_t1     = trade.metadata.get("lots_t1", trade.lot_size) if trade.metadata else trade.lot_size
        self.lots_t2     = trade.metadata.get("lots_t2", 0.0) if trade.metadata else 0.0
        self.lots_t3     = trade.metadata.get("lots_t3", 0.0) if trade.metadata else 0.0
        self.t2_opened   = False
        self.t3_opened   = False
        self.last_adx_at_entry = trade.metadata.get("adx", 20.0) if trade.metadata else 20.0
        self.sl_tightened_this_session = False


# Registry of active position states
_states: dict[str, _PositionState] = {}


def _get_or_create_state(trade: Trade) -> _PositionState:
    if trade.id not in _states:
        _states[trade.id] = _PositionState(trade)
    return _states[trade.id]


def _is_buy(direction) -> bool:
    return direction in (Direction.BUY, "BUY")


def _profit_in_atr(ps: _PositionState, price: float) -> float:
    if ps.atr == 0:
        return 0.0
    if _is_buy(ps.direction):
        return (price - ps.entry_price) / ps.atr
    return (ps.entry_price - price) / ps.atr


# ── INDICATORS ─────────────────────────────────────────────────────────────────

def _calc_indicators(df: pd.DataFrame) -> dict[str, float]:
    """Calculate all SOP indicators on the last N bars."""
    if df is None or len(df) < 20:
        return {}
    try:
        import pandas_ta as ta
    except ImportError:
        return {}

    close  = df["close"]
    high   = df["high"]
    low    = df["low"]
    volume = df.get("volume", pd.Series([0.0] * len(df)))

    atr_s  = ta.atr(high, low, close, length=14)
    adx_df = ta.adx(high, low, close, length=14)
    rsi_s  = ta.rsi(close, length=14)
    ema20  = ta.ema(close, length=20)
    ema50  = ta.ema(close, length=50)
    macd_df= ta.macd(close, fast=12, slow=26, signal=9)
    bb_df  = ta.bbands(close, length=20, std=2)
    psar_s = ta.psar(high, low, close, af0=0.02, af=0.02, max_af=0.2)

    adx_col = next((c for c in (adx_df.columns if adx_df is not None else []) if c.startswith("ADX_")), None)
    macd_h_col = next((c for c in (macd_df.columns if macd_df is not None else []) if "h" in c.lower()), None)
    psar_col = next((c for c in (psar_s.columns if psar_s is not None and hasattr(psar_s, "columns") else []) if "PSARl" in c or "PSARs" in c), None)

    vol_avg = volume.rolling(20).mean()

    return {
        "atr":          float(atr_s.iloc[-1])   if atr_s is not None  and not atr_s.empty  else 0.0,
        "adx":          float(adx_df[adx_col].iloc[-1]) if adx_col else 20.0,
        "adx_prev":     float(adx_df[adx_col].iloc[-2]) if adx_col and len(adx_df) >= 2 else 20.0,
        "rsi":          float(rsi_s.iloc[-1])    if rsi_s is not None  and not rsi_s.empty  else 50.0,
        "ema20":        float(ema20.iloc[-1])    if ema20 is not None  and not ema20.empty  else close.iloc[-1],
        "ema50":        float(ema50.iloc[-1])    if ema50 is not None  and not ema50.empty  else close.iloc[-1],
        "macd_hist":    float(macd_df[macd_h_col].iloc[-1]) if macd_h_col else 0.0,
        "macd_hist_prev": float(macd_df[macd_h_col].iloc[-2]) if macd_h_col and len(macd_df) >= 2 else 0.0,
        "price":        float(close.iloc[-1]),
        "prev_price":   float(close.iloc[-2])    if len(close) >= 2 else float(close.iloc[-1]),
        "candle_body":  abs(float(close.iloc[-1]) - float(df["open"].iloc[-1])),
        "volume":       float(volume.iloc[-1])   if not volume.empty else 0.0,
        "volume_avg":   float(vol_avg.iloc[-1])  if not vol_avg.empty else 1.0,
        "psar":         float(psar_s[psar_col].iloc[-1]) if psar_col else 0.0,
    }


# ── STEP 4: DYNAMIC SL (8 tightening triggers) ────────────────────────────────

def _compute_new_sl(ps: _PositionState, ind: dict[str, float], news_event_soon: bool) -> float | None:
    """
    SOP Section 3.2 — Evaluate 8 SL tightening triggers.
    Returns candidate new SL or None if no trigger fires.
    SL can only improve (move toward profit).
    """
    price = ind.get("price", ps.entry_price)
    atr   = ind.get("atr", ps.atr) or ps.atr or 1.0
    rsi   = ind.get("rsi", 50.0)
    macd  = ind.get("macd_hist", 0.0)
    macd_prev = ind.get("macd_hist_prev", 0.0)
    ema20 = ind.get("ema20", price)
    adx   = ind.get("adx", 25.0)
    volume = ind.get("volume", 1.0)
    vol_avg = ind.get("volume_avg", 1.0)
    candle_body = ind.get("candle_body", 0.0)
    profit_atr = _profit_in_atr(ps, price)

    buy = _is_buy(ps.direction)
    sign = 1 if buy else -1

    candidates: list[float] = []

    # T1: RSI crosses 50 against direction
    if (buy and rsi < 50) or (not buy and rsi > 50):
        candidates.append(price - sign * atr * 1.0)

    # T2: MACD histogram flips against direction
    if buy and macd < 0 < macd_prev:
        candidates.append(price - atr * 0.8)
    elif not buy and macd > 0 > macd_prev:
        candidates.append(price + atr * 0.8)

    # T3: Price closes through EMA20 against direction (only if 0.5 ATR in profit)
    if profit_atr >= 0.5:
        if (buy and price < ema20) or (not buy and price > ema20):
            candidates.append(price - sign * atr * 0.5)

    # T4: ADX drops below 20 (trend ending) for trades entered when ADX > 25
    if ps.last_adx_at_entry > 25 and adx < 20:
        candidates.append(price - sign * atr * 1.2)

    # T5: Engulfing candle against direction (body > 1 ATR)
    if candle_body > atr:
        open_c = ind.get("prev_price", price)
        if (buy and price < open_c) or (not buy and price > open_c):
            candidates.append(price - sign * atr * 0.7)

    # T6: Volume spike against direction > 2× avg
    if vol_avg > 0 and volume > 2 * vol_avg:
        if (buy and price < ind.get("prev_price", price)) or \
           (not buy and price > ind.get("prev_price", price)):
            candidates.append(price - sign * atr * 0.6)

    # T7: High-impact event within 30 min
    if news_event_soon:
        # Move to nearest round number within 1 ATR
        direction_factor = -1 if buy else 1
        round_lvl = round(price / atr) * atr + direction_factor * atr * 0.5
        candidates.append(round_lvl)

    # T8: Daily max drawdown approaching (within 0.5% of limit) — CRITICAL
    # (Caller sets this flag; move to 0.4 ATR behind price)
    if ps.sl_tightened_this_session:
        candidates.append(price - sign * atr * 0.4)

    if not candidates:
        return None

    # Tightest candidate that improves current SL
    if buy:
        best = max(candidates)            # higher SL = tighter for BUY
        if best > ps.current_sl:
            return best
    else:
        best = min(candidates)            # lower SL = tighter for SELL
        if best < ps.current_sl:
            return best

    return None


# ── BREAKEVEN RULES ────────────────────────────────────────────────────────────

def _check_breakeven(ps: _PositionState, price: float) -> float | None:
    """
    SOP Section 3.3 — Move SL to breakeven EARLIER at 0.5 ATR profit (was 1.0 ATR).
    More aggressive profit protection.
    """
    if ps.atr == 0:
        return None
    profit_atr = _profit_in_atr(ps, price)
    
    # EARLIER breakeven at 0.5 ATR (was 1.0 ATR)
    if profit_atr < 0.5:
        return None
    
    # Smaller buffer for tighter protection
    buf = ps.atr * 0.05  # Was 0.1
    
    if _is_buy(ps.direction):
        be_sl = ps.entry_price + buf
        if be_sl > ps.current_sl:
            log.info("[POSMGR] {} Moving to BREAKEVEN at {:.2f} ATR profit", ps.symbol, profit_atr)
            return be_sl
    else:
        be_sl = ps.entry_price - buf
        if be_sl < ps.current_sl:
            log.info("[POSMGR] {} Moving to BREAKEVEN at {:.2f} ATR profit", ps.symbol, profit_atr)
            return be_sl
    return None


# ── STEP 5: DYNAMIC TP ─────────────────────────────────────────────────────────

def _compute_tp_adjustment(ps: _PositionState, ind: dict[str, float]) -> float | None:
    """
    SOP Section 4.2/4.3 — TP extension and reduction triggers.
    Returns new TP or None if unchanged.
    """
    if ps.tp_reduced:
        return None   # once reduced, cannot re-extend

    price = ind.get("price", ps.entry_price)
    atr   = ind.get("atr", ps.atr) or ps.atr or 1.0
    adx   = ind.get("adx", 20.0)
    rsi   = ind.get("rsi", 50.0)
    macd  = ind.get("macd_hist", 0.0)
    macd_prev = ind.get("macd_hist_prev", 0.0)
    volume = ind.get("volume", 1.0)
    vol_avg = ind.get("volume_avg", 1.0)
    candle_body = ind.get("candle_body", 0.0)

    buy  = _is_buy(ps.direction)
    sign = 1 if buy else -1
    tp   = ps.current_tp

    # Extension triggers (Section 4.2)
    # E1: ADX rose ≥ 5 points and currently > 30 — once per 5pt increment
    if adx > 30 and adx - ps.last_adx_at_entry >= 5 and ps.tp_extended_count < 3:
        tp += sign * atr * 1.0
        ps.tp_extended_count += 1
        log.info("[POSMGR] {} TP extended +1.0 ATR (ADX acceleration)", ps.symbol)

    # E2: Price momentum (ROC) > 0.5% — cap 3 extensions
    roc = abs(price - ind.get("prev_price", price)) / max(ind.get("prev_price", price), 1.0)
    if roc > 0.005 and ps.tp_extended_count < 3:
        tp += sign * atr * 0.5
        ps.tp_extended_count += 1

    # E3: Volume surge > 2× avg (once per trade)
    if vol_avg > 0 and volume > 2 * vol_avg and ps.tp_extended_count == 0:
        tp += sign * atr * 0.3
        ps.tp_extended_count += 1

    # E5: Strong trend candle body > 1.5 ATR
    if candle_body > 1.5 * atr and ps.tp_extended_count < 3:
        tp += sign * atr * 0.4
        ps.tp_extended_count += 1

    # E6: MACD histogram making new high
    if buy and macd > macd_prev and macd > 0 and ps.tp_extended_count < 3:
        tp += atr * 0.3
        ps.tp_extended_count += 1
    elif not buy and macd < macd_prev and macd < 0 and ps.tp_extended_count < 3:
        tp -= atr * 0.3
        ps.tp_extended_count += 1

    # Reduction triggers (Section 4.3) — tighten TP
    # R1: ADX drops below 25 (was above 30 at entry)
    if ps.last_adx_at_entry > 30 and adx < 25:
        remaining = abs(tp - price)
        tp = price + sign * remaining * 0.8
        ps.tp_reduced = True
        log.info("[POSMGR] {} TP reduced 80% remaining (ADX drop)", ps.symbol)

    # R2: RSI exhaustion
    if (buy and rsi > 75) or (not buy and rsi < 25):
        # Move TP to next key S/R (approximate as current_tp × 0.85)
        remaining = abs(tp - price)
        tp = price + sign * remaining * 0.85
        ps.tp_reduced = True

    # R4: High-impact event within 60 min — move TP to nearest key level
    # (Handled externally by calendar_agent; here we just check the metadata flag)

    # Hard minimum R:R 1.8 guard
    sl_dist = abs(ps.current_sl - ps.entry_price)
    tp_dist = abs(tp - ps.entry_price)
    if sl_dist > 0 and tp_dist / sl_dist < 1.8:
        return None   # don't accept a TP that breaks minimum R:R

    if abs(tp - ps.current_tp) < 1e-8:
        return None
    return tp


# ── STEP 6: TRAILING STOP ─────────────────────────────────────────────────────

def _compute_trail_sl(ps: _PositionState, ind: dict[str, float]) -> float | None:
    """
    SOP Section 05 — Tiered trailing stop.
    Activates at 0.5 ATR profit. Tighter trail distance as profit increases.
    """
    price = ind.get("price", ps.entry_price)
    atr   = ind.get("atr", ps.atr) or ps.atr or 1.0
    buy   = _is_buy(ps.direction)

    # Update peak
    if buy:
        ps.peak_price = max(ps.peak_price, price)
    else:
        ps.peak_price = min(ps.peak_price, price)

    profit_atr = _profit_in_atr(ps, price)

    # Activation check - EARLIER at 0.5 ATR (was 1.0 ATR)
    if not ps.trailing_active:
        if profit_atr >= 0.5:
            ps.trailing_active = True
            log.info("[POSMGR] {} Trailing ACTIVATED at {:.2f} ATR profit", ps.symbol, profit_atr)
        else:
            return None

    # TIERED TRAIL DISTANCE - tighter as profit increases
    if profit_atr >= 3.0:
        trail_dist = 0.3  # Lock in 90% of gains
    elif profit_atr >= 2.0:
        trail_dist = 0.5  # Lock in 75% of gains
    elif profit_atr >= 1.0:
        trail_dist = 0.75  # Lock in 62.5% of gains
    else:
        trail_dist = 1.0  # Lock in 50% of gains

    # Adjust for regime
    regime = ps.regime
    if regime == "HIGH_VOLATILE":
        trail_dist *= 1.3  # Wider for volatile markets
    elif regime == "STRONG_TREND":
        trail_dist *= 1.1  # Slightly wider for trends
    elif regime == "RANGING":
        trail_dist *= 0.8  # Tighter for ranging
    
    # Calculate new SL from peak
    new_sl = ps.peak_price - (atr * trail_dist) if buy else ps.peak_price + (atr * trail_dist)

    # Minimum gap: 0.3 ATR (tighter than before)
    min_gap = atr * 0.3

    if buy and price - new_sl < min_gap:
        new_sl = price - min_gap
    elif not buy and new_sl - price < min_gap:
        new_sl = price + min_gap

    # RULE TR-01: SL only moves in profitable direction
    if buy and new_sl <= ps.current_sl:
        return None
    if not buy and new_sl >= ps.current_sl:
        return None

    log.info("[POSMGR] {} Trail SL → {:.5f} [profit:{:.2f}ATR, dist:{:.2f}ATR]", 
             ps.symbol, new_sl, profit_atr, trail_dist)
    
    return new_sl


# ── STEP 10: TRANCHE TRIGGER ──────────────────────────────────────────────────

def _check_tranche_conditions(ps: _PositionState, ind: dict[str, float]) -> list[str]:
    """
    SOP Section 02 — Conditions for T2 and T3 entry.
    Returns list of tranches to open: e.g. ["T2"] or ["T2", "T3"]
    """
    to_open: list[str] = []
    price    = ind.get("price", ps.entry_price)
    adx      = ind.get("adx", 0.0)
    adx_prev = ind.get("adx_prev", 0.0)
    volume   = ind.get("volume", 1.0)
    vol_avg  = ind.get("volume_avg", 1.0)
    atr      = ind.get("atr", ps.atr) or ps.atr or 1.0

    profit_atr = _profit_in_atr(ps, price)

    # T2: T1 ≥ 1.0 ATR profit AND trend indicators aligned
    if not ps.t2_opened and profit_atr >= 1.0 and adx >= 18:
        to_open.append("T2")

    # T3: T1 ≥ 2.0 ATR profit AND ADX rising AND ADX ≥ 25 AND volume > 1.3× avg
    if (not ps.t3_opened and profit_atr >= 2.0
            and adx >= 25 and adx > adx_prev
            and vol_avg > 0 and volume >= 1.3 * vol_avg):
        to_open.append("T3")

    return to_open


# ── MAIN POSITION MANAGER ─────────────────────────────────────────────────────

class PositionManager:
    """
    Runs the SOP 10-step management cycle for every open trade.
    Call `run_cycle(broker, open_trades)` from APScheduler every 15s.
    """

    async def run_cycle(self, broker, open_trades: list[Trade], bot_state=None) -> None:
        """Execute the 10-step SOP management cycle for all open positions."""
        if not open_trades:
            return

        now_utc = datetime.now(timezone.utc)
        news_event_soon = self._news_event_soon(bot_state)

        for trade in list(open_trades):
            try:
                await self._manage_position(trade, broker, open_trades, bot_state, now_utc, news_event_soon)
            except asyncio.CancelledError:
                # Bot is being stopped, exit gracefully
                log.debug("[POSMGR] Position management cycle cancelled")
                raise
            except Exception as e:
                log.error("[POSMGR] Cycle error on {} {}: {}", trade.symbol, trade.id[:8], e)

    def _news_event_soon(self, bot_state) -> bool:
        """Check if a high/medium impact event is within 30 minutes."""
        if bot_state is None:
            return False
        now = datetime.utcnow()
        for ev in getattr(bot_state, "calendar_events", []):
            if getattr(ev, "released", False):
                continue
            mins = (getattr(ev, "scheduled", now) - now).total_seconds() / 60
            impact = getattr(ev, "impact", None)
            if 0 < mins <= 30 and str(impact) in ("HIGH", "NewsImpact.HIGH", "MEDIUM", "NewsImpact.MEDIUM"):
                return True
        return False

    async def _manage_position(
        self, trade: Trade, broker, open_trades: list[Trade],
        bot_state, now_utc: datetime, news_event_soon: bool
    ) -> None:
        ps = _get_or_create_state(trade)

        # ── Step 1: Verify position still open in broker ────────────────────
        try:
            live_trades = await broker.get_open_trades()
            # Match by broker_order_id (MT5 ticket) — the only reliable cross-reference
            live_tickets = {
                str(getattr(t, "broker_order_id", "") or getattr(t, "id", ""))
                for t in live_trades
            }
            our_ticket = str(trade.broker_order_id or "")
            if our_ticket and our_ticket not in live_tickets:
                log.info("[POSMGR] {} ticket={} not in live positions — detecting close",
                         trade.symbol, our_ticket)
                await self._step9_detect_close(trade, open_trades, ps, broker)
                return
        except Exception as e:
            log.warning("[POSMGR] Step 1 verify failed for {}: {}", trade.symbol, e)
            return

        # ── Step 2: Refresh data ────────────────────────────────────────────
        try:
            df = await self._fetch_ohlcv(trade.symbol)
            if df is None or len(df) < 30:
                log.warning("[POSMGR] Step 2 insufficient data for {} — skipping cycle", trade.symbol)
                return
            ind = _calc_indicators(df)
        except Exception as e:
            log.warning("[POSMGR] Step 2 data refresh failed for {}: {}", trade.symbol, e)
            return

        if not ind:
            return

        price = ind.get("price", ps.entry_price)

        # Update ATR from fresh data
        if ind.get("atr", 0.0) > 0:
            ps.atr = ind["atr"]

        # ── Step 3: Recalculate conditions (regime) ─────────────────────────
        try:
            regime = self._classify_regime(ind)
            ps.regime = regime
            ps.trail_mode = REGIME_TRAIL_MODE.get(regime, "STEP")
            if ps.tranche == "T3":
                ps.trail_mode = "PSAR"
        except Exception as e:
            log.warning("[POSMGR] Step 3 regime calc failed: {}", e)

        new_sl = ps.current_sl
        new_tp = ps.current_tp
        modified = False

        # ── Step 4: Dynamic SL ──────────────────────────────────────────────
        try:
            be_sl = _check_breakeven(ps, price)
            if be_sl:
                new_sl = be_sl
                log.info("[POSMGR] {} SL → BREAKEVEN {:.5f}", trade.symbol, new_sl)

            trig_sl = _compute_new_sl(ps, ind, news_event_soon)
            if trig_sl:
                # Take the tighter of breakeven and trigger
                if _is_buy(ps.direction):
                    new_sl = max(new_sl, trig_sl)
                else:
                    new_sl = min(new_sl, trig_sl)
                log.info("[POSMGR] {} SL tightened to {:.5f}", trade.symbol, new_sl)
        except Exception as e:
            log.error("[POSMGR] Step 4 SL calc error: {}", e)

        # ── Step 5: Dynamic TP ──────────────────────────────────────────────
        try:
            adj_tp = _compute_tp_adjustment(ps, ind)
            if adj_tp and adj_tp != ps.current_tp:
                new_tp = adj_tp
                log.info("[POSMGR] {} TP adjusted to {:.5f}", trade.symbol, new_tp)
        except Exception as e:
            log.error("[POSMGR] Step 5 TP calc error: {}", e)

        # ── Step 6: Trailing stop ───────────────────────────────────────────
        try:
            trail_sl = _compute_trail_sl(ps, ind)
            if trail_sl:
                if _is_buy(ps.direction):
                    new_sl = max(new_sl, trail_sl)
                else:
                    new_sl = min(new_sl, trail_sl)
                log.info("[POSMGR] {} Trail SL → {:.5f} [{}]", trade.symbol, new_sl, ps.trail_mode)
        except Exception as e:
            log.error("[POSMGR] Step 6 trail error: {}", e)

        # ── Step 7: Apply modifications ─────────────────────────────────────
        sl_changed = abs(new_sl - ps.current_sl) > 1e-8
        tp_changed = abs(new_tp - ps.current_tp) > 1e-8

        if sl_changed or tp_changed:
            try:
                await broker.modify_trade(trade, sl=new_sl, tp=new_tp)
                ps.current_sl = new_sl
                ps.current_tp = new_tp
                trade.stop_loss   = new_sl
                trade.take_profit = new_tp
                modified = True
                log.info("[POSMGR] {} Modified SL={:.5f} TP={:.5f}", trade.symbol, new_sl, new_tp)
            except asyncio.CancelledError:
                # Bot is being stopped, exit gracefully
                log.debug("[POSMGR] Position management cancelled for {}", trade.symbol)
                raise
            except Exception as e:
                log.error("[POSMGR] Step 7 broker.modify_trade FAILED for {}: {} — retrying", trade.symbol, e)
                try:
                    await asyncio.sleep(1)
                    await broker.modify_trade(trade, sl=new_sl, tp=new_tp)
                    ps.current_sl = new_sl
                    ps.current_tp = new_tp
                    trade.stop_loss   = new_sl
                    trade.take_profit = new_tp
                except Exception as e2:
                    log.error("[POSMGR] Step 7 retry FAILED — CRITICAL: {} {}", trade.symbol, e2)

        # ── Step 8: Update tracker ──────────────────────────────────────────
        try:
            await self._step8_update_tracker(trade, price, ps)
        except Exception as e:
            log.warning("[POSMGR] Step 8 DB write error: {}", e)

        # ── Step 9: Detect close (position was TP/SL hit between steps) ─────
        # Already handled in Step 1; skip repeat broker call

        # ── Step 10: Tranche trigger ────────────────────────────────────────
        try:
            tranches_to_open = _check_tranche_conditions(ps, ind)
            for tranche in tranches_to_open:
                await self._step10_open_tranche(trade, ps, tranche, price, ind, broker)
        except Exception as e:
            log.error("[POSMGR] Step 10 tranche trigger error: {}", e)

    # ── Helpers ────────────────────────────────────────────────────────────────

    async def _fetch_ohlcv(self, symbol: str):
        """Fetch recent OHLCV bars. Uses DuckDB (market_data.duckdb) as primary source."""
        try:
            from pathlib import Path
            import duckdb
            db_path = Path("data/market_data.duckdb")
            if db_path.exists():
                # Use read_only=False but access_mode="READ_ONLY" via pragma to avoid
                # locking conflicts with the main write connection
                con = duckdb.connect(str(db_path))
                df = con.execute(
                    "SELECT timestamp, open, high, low, close, volume "
                    "FROM ohlcv WHERE symbol=? AND timeframe='M15' "
                    "ORDER BY timestamp DESC LIMIT 250",
                    [symbol],
                ).df()
                con.close()
                if len(df) >= 30:
                    df = df.sort_values("timestamp").reset_index(drop=True)
                    return df
        except Exception as e:
            log.warning("[POSMGR] OHLCV fetch failed for {}: {}", symbol, e)
        return None

    def _classify_regime(self, ind: dict[str, float]) -> str:
        """Classify market regime from indicators (SOP Section 11 reference)."""
        adx = ind.get("adx", 20.0)
        atr_ratio = ind.get("atr_ratio", 1.0)

        if atr_ratio > 2.0:
            return "HIGH_VOLATILE"
        if atr_ratio < 0.5:
            return "LOW_VOLATILE"
        if adx > 35:
            return "STRONG_TREND"
        if adx >= 20:
            return "WEAK_TREND"
        return "RANGING"

    async def _step8_update_tracker(self, trade: Trade, price: float, ps: _PositionState):
        """Write position update to DuckDB."""
        from pathlib import Path
        import duckdb
        db_path = Path("data/apex.db")
        unrealised_pnl = (
            (price - ps.entry_price) * ps.lot_size * 100000
            if _is_buy(ps.direction)
            else (ps.entry_price - price) * ps.lot_size * 100000
        )
        try:
            con = duckdb.connect(str(db_path))
            con.execute("""
                CREATE TABLE IF NOT EXISTS position_tracker (
                    trade_id TEXT, symbol TEXT, direction TEXT,
                    current_sl DOUBLE, current_tp DOUBLE,
                    current_price DOUBLE, unrealised_pnl DOUBLE,
                    trailing_active BOOLEAN, trail_mode TEXT, regime TEXT,
                    tranche TEXT, updated_at TIMESTAMP
                )
            """)
            con.execute("DELETE FROM position_tracker WHERE trade_id=?", [trade.id])
            con.execute(
                "INSERT INTO position_tracker VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    trade.id, ps.symbol, str(ps.direction),
                    ps.current_sl, ps.current_tp,
                    price, unrealised_pnl,
                    ps.trailing_active, ps.trail_mode, ps.regime,
                    ps.tranche, datetime.utcnow(),
                ]
            )
            con.close()
        except Exception as e:
            log.warning("[POSMGR] DB tracker write error: {}", e)

    async def _step9_detect_close(
        self, trade: Trade, open_trades: list[Trade],
        ps: _PositionState, broker
    ):
        """Position closed externally (SL/TP hit). Log to DuckDB and remove from tracker."""
        log.info("[POSMGR] Position {} {} detected as CLOSED externally", trade.symbol, trade.id[:8])
        if trade in open_trades:
            open_trades.remove(trade)
        _states.pop(trade.id, None)

        # Log to closed_trades table
        try:
            from pathlib import Path
            import duckdb
            db_path = Path("data/apex.db")
            con = duckdb.connect(str(db_path))
            con.execute("""
                CREATE TABLE IF NOT EXISTS closed_trades (
                    trade_id TEXT, symbol TEXT, direction TEXT,
                    entry_price DOUBLE, exit_sl DOUBLE, exit_tp DOUBLE,
                    lot_size DOUBLE, tranche TEXT, closed_at TIMESTAMP
                )
            """)
            con.execute(
                "INSERT INTO closed_trades VALUES (?,?,?,?,?,?,?,?,?)",
                [
                    trade.id, ps.symbol, str(ps.direction),
                    ps.entry_price, ps.current_sl, ps.current_tp,
                    ps.lot_size, ps.tranche, datetime.utcnow(),
                ]
            )
            con.execute("DELETE FROM position_tracker WHERE trade_id=?", [trade.id])
            con.close()
        except Exception as e:
            log.warning("[POSMGR] Step 9 close log error: {}", e)

    async def _step10_open_tranche(
        self, t1_trade: Trade, ps: _PositionState,
        tranche: str, price: float, ind: dict, broker
    ):
        """Open T2 or T3 continuation tranche (SOP Section 2.1)."""
        if tranche == "T2" and ps.t2_opened:
            return
        if tranche == "T3" and ps.t3_opened:
            return

        lot = ps.lots_t2 if tranche == "T2" else ps.lots_t3
        if lot < 0.01:
            return

        atr = ind.get("atr", ps.atr) or ps.atr or 1.0
        buy = _is_buy(ps.direction)

        if tranche == "T2":
            # SL = T1 entry price, TP = entry ± 3.5 ATR
            sl = ps.entry_price
            tp = (price + atr * 3.5) if buy else (price - atr * 3.5)
        else:
            # T3: SL = T2 entry (approximated as T1 entry for simplicity), TP = 5.5 ATR or trailing
            sl = ps.entry_price
            tp = (price + atr * 5.5) if buy else (price - atr * 5.5)

        import uuid
        from core.models import AssetClass
        tranche_trade = Trade(
            id=str(uuid.uuid4()),
            broker=t1_trade.broker,
            symbol=t1_trade.symbol,
            asset_class=getattr(t1_trade, "asset_class", AssetClass.FOREX),
            direction=t1_trade.direction,
            lot_size=lot,
            entry_price=price,
            stop_loss=sl,
            take_profit=tp,
            strategy=t1_trade.strategy + f"_{tranche}",
            signal_id=t1_trade.signal_id,
            metadata={"tranche": tranche, "parent_trade_id": t1_trade.id,
                      "atr": atr, "regime": ps.regime},
        )

        try:
            executed = await broker.place_order(tranche_trade)
            if tranche == "T2":
                ps.t2_opened = True
            else:
                ps.t3_opened = True
            log.info("[POSMGR] TRANCHE {} OPENED: {} {} @ {} SL={} TP={}",
                     tranche, t1_trade.symbol, lot, price, sl, tp)
        except Exception as e:
            log.error("[POSMGR] Failed to open {} for {}: {}", tranche, t1_trade.symbol, e)


# Module-level singleton
position_manager = PositionManager()
