"""
APEX Trading Bot — Correlation Agent
======================================
Sits between market_analyst and sentiment_agent in the LangGraph pipeline.

Responsibilities:
  1. Correlation confirmation  — boost/reduce signal score based on aligned assets
  2. Leading indicator check   — flag premature signals before leaders have moved
  3. Divergence detection      — generate catch-up signals when correlated assets split
  4. Correlation-adjusted size — scale lot sizes down for correlated open positions
  5. Over-correlation veto     — reject signals when group concentration is too high

Pipeline position:
  market_analyst → [correlation_agent] → sentiment_agent → ...
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd
import numpy as np

from core.models import (
    BotState, TradingSignal, Direction, AssetClass,
    SignalStrength, AgentMessage, Trade,
)
from core.correlations import (
    STATIC_CORRELATIONS, CORRELATION_GROUPS, GROUP_MAX_SAME_DIRECTION,
    DIVERGENCE_PAIRS, DynamicCorrelationEngine,
    get_group, get_group_max,
)
from core.logger import get_agent_logger

log = get_agent_logger("CORR")

# Singleton dynamic engine — shared across cycles
_dyn_engine = DynamicCorrelationEngine()


# ─────────────────────────────────────────────────────────────────────────────
#  DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ConfirmationResult:
    boost:          float           # net score adjustment (-2.0 to +2.0)
    confirmations:  int
    contradictions: int
    detail:         list[str]       # human-readable per-asset results


@dataclass
class LeadingResult:
    aligned:  bool
    warnings: list[str]
    confidence_factor: float        # 1.0 = no change, 0.8 = reduce by 20%


@dataclass
class DivergenceSignal:
    symbol:       str
    direction:    str
    score:        float
    confidence:   float
    leader:       str
    leader_change: float
    lagger_change: float
    reasoning:    str


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS — price momentum from quote / OHLCV cache
# ─────────────────────────────────────────────────────────────────────────────

def _get_session_change_pct(symbol: str, state: BotState) -> Optional[float]:
    """
    Return approximate session change % for a symbol.
    Uses OHLCV cache (close vs open of most recent bar), falling back to quote spread.
    """
    # Try OHLCV cache first
    bars = state.ohlcv_cache.get(symbol)
    if bars and len(bars) >= 2:
        try:
            recent = bars[-1]
            prev   = bars[-2]
            # Handle both dict and OHLCV model
            c_now  = recent.close  if hasattr(recent, "close")  else recent["close"]
            c_prev = prev.close    if hasattr(prev,   "close")  else prev["close"]
            if c_prev and c_prev != 0:
                return (c_now - c_prev) / c_prev * 100
        except Exception:
            pass

    # Fall back to quote mid-price vs yesterday's stored price
    quote = state.quotes.get(symbol)
    if quote:
        mid = (quote.bid + quote.ask) / 2
        yesterday = getattr(quote, "prev_close", None)
        if yesterday and yesterday != 0:
            return (mid - yesterday) / yesterday * 100

    return None


def _get_momentum_direction(symbol: str, state: BotState, bars: int = 5) -> Optional[str]:
    """
    Return "BUY" / "SELL" / None based on short-term momentum.
    Uses rate-of-change over last `bars` periods.
    """
    ohlcv = state.ohlcv_cache.get(symbol)
    if not ohlcv or len(ohlcv) < bars + 1:
        return None

    try:
        closes = []
        for b in ohlcv[-(bars + 1):]:
            c = b.close if hasattr(b, "close") else b["close"]
            closes.append(float(c))

        roc = (closes[-1] - closes[0]) / closes[0] * 100
        if   roc > 0.05:  return "BUY"
        elif roc < -0.05: return "SELL"
        return None  # flat / inconclusive
    except Exception:
        return None


def _get_roc(symbol: str, state: BotState, bars: int = 5) -> Optional[float]:
    """Return raw rate-of-change % over last `bars` periods."""
    ohlcv = state.ohlcv_cache.get(symbol)
    if not ohlcv or len(ohlcv) < bars + 1:
        return None
    try:
        closes = [
            float(b.close if hasattr(b, "close") else b["close"])
            for b in ohlcv[-(bars + 1):]
        ]
        return (closes[-1] - closes[0]) / closes[0] * 100
    except Exception:
        return None


def _asset_class_for(symbol: str) -> AssetClass:
    """Best-effort asset class mapping."""
    s = symbol.upper()
    if s in ("BTCUSD", "ETHUSD", "SOLUSD", "BNBUSD"):
        return AssetClass.CRYPTO
    if s in ("USOIL", "UKCRUOIL", "NATGAS"):
        return AssetClass.COMMODITY
    if s in ("XAUUSD", "XAGUSD", "XPTUSD"):
        return AssetClass.METAL
    if s in ("SPX500", "NAS100", "UK100", "GER40"):
        return AssetClass.STOCK
    return AssetClass.FOREX


# ─────────────────────────────────────────────────────────────────────────────
#  1. CORRELATION CONFIRMATION SCORER
# ─────────────────────────────────────────────────────────────────────────────

async def correlation_confirmation(
    signal: TradingSignal,
    state: BotState,
) -> ConfirmationResult:
    """
    For each correlated asset defined in STATIC_CORRELATIONS:
      - If a positive-correlated asset moves in the SAME direction  → +0.5
      - If a negative-correlated asset moves in the OPPOSITE direction → +0.5
      - Contradiction (expected alignment but moving opposite)       → -0.7

    Final boost is clamped to [-2.0, +2.0].

    Also optionally enriches with dynamic Pearson coefficients if OHLCV
    data is available for the correlated asset.
    """
    corr = STATIC_CORRELATIONS.get(signal.symbol)
    if not corr:
        return ConfirmationResult(boost=0.0, confirmations=0, contradictions=0, detail=[])

    confirmations = 0
    contradictions = 0
    detail: list[str] = []

    # ── Positive correlations ─────────────────────────────────────────────
    for asset in corr.get("positive", []):
        if asset not in state.ohlcv_cache and asset not in state.quotes:
            continue

        asset_dir = _get_momentum_direction(asset, state)
        if asset_dir is None:
            detail.append(f"  {asset:10s} → inconclusive (no data)")
            continue

        if asset_dir == signal.direction.value:
            confirmations += 1
            detail.append(f"  ✅ {asset:10s} → {asset_dir} (correlated, CONFIRMS)")
        else:
            contradictions += 1
            detail.append(f"  ❌ {asset:10s} → {asset_dir} (correlated, CONTRADICTS)")

    # ── Negative correlations ─────────────────────────────────────────────
    opposite = "SELL" if signal.direction == Direction.BUY else "BUY"
    for asset in corr.get("negative", []):
        if asset not in state.ohlcv_cache and asset not in state.quotes:
            continue

        asset_dir = _get_momentum_direction(asset, state)
        if asset_dir is None:
            detail.append(f"  {asset:10s} → inconclusive (no data)")
            continue

        if asset_dir == opposite:
            # e.g. DXY falling while we want to BUY Gold = GOOD
            confirmations += 1
            detail.append(f"  ✅ {asset:10s} → {asset_dir} (inverse-correlated, CONFIRMS)")
        else:
            contradictions += 1
            detail.append(f"  ❌ {asset:10s} → {asset_dir} (inverse-correlated, CONTRADICTS)")

    # ── Dynamic Pearson enrichment (opportunistic) ────────────────────────
    # Weight adjustments based on strength of correlation coefficient
    dyn_adjustment = 0.0
    known_assets = list(state.ohlcv_cache.keys())
    if known_assets:
        dyn_results = _dyn_engine.get_all_correlations(
            signal.symbol, known_assets[:8], timeframe="H1"
        )
        for dyn in dyn_results:
            if not dyn.is_reliable:
                continue
            partner_dir = _get_momentum_direction(dyn.symbol_b, state)
            if partner_dir is None:
                continue
            # Strong positive correlation moving same way = extra boost
            if dyn.coefficient >= 0.70 and partner_dir == signal.direction.value:
                dyn_adjustment += 0.2
                detail.append(f"  📊 {dyn.symbol_b:10s} Pearson={dyn.coefficient:+.2f} CONFIRMS (dynamic)")
            # Strong negative correlation moving opposite way = extra boost
            elif dyn.coefficient <= -0.70 and partner_dir == opposite:
                dyn_adjustment += 0.2
                detail.append(f"  📊 {dyn.symbol_b:10s} Pearson={dyn.coefficient:+.2f} CONFIRMS inverse (dynamic)")

    # ── Final boost calculation ───────────────────────────────────────────
    raw_boost = (confirmations * 0.5) - (contradictions * 0.7) + dyn_adjustment
    boost = max(-2.0, min(2.0, raw_boost))

    return ConfirmationResult(
        boost=round(boost, 2),
        confirmations=confirmations,
        contradictions=contradictions,
        detail=detail,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  2. LEADING INDICATOR PRE-FILTER
# ─────────────────────────────────────────────────────────────────────────────

async def leading_indicator_check(
    signal: TradingSignal,
    state: BotState,
) -> LeadingResult:
    """
    Checks whether the leading indicators for a signal's instrument
    have already moved in the required direction.

    If the leader hasn't moved yet → signal is early → reduce confidence.
    """
    corr = STATIC_CORRELATIONS.get(signal.symbol)
    if not corr:
        return LeadingResult(aligned=True, warnings=[], confidence_factor=1.0)

    warnings: list[str] = []
    penalties = 0
    leaders_checked = 0

    for leader in corr.get("leading", []):
        if leader not in state.ohlcv_cache and leader not in state.quotes:
            continue

        leaders_checked += 1
        leader_roc = _get_roc(leader, state, bars=5)
        if leader_roc is None:
            continue

        # Determine whether leader should be rising or falling
        leader_corr = STATIC_CORRELATIONS.get(signal.symbol, {})
        is_positive  = leader in leader_corr.get("positive", [])
        is_negative  = leader in leader_corr.get("negative", [])

        if signal.direction == Direction.BUY:
            if is_positive and leader_roc < -0.05:
                warnings.append(
                    f"Leading indicator {leader} falling ({leader_roc:+.3f}%) "
                    f"while signal is BUY — may be premature"
                )
                penalties += 1
            elif is_negative and leader_roc > 0.05:
                warnings.append(
                    f"Leading indicator {leader} rising ({leader_roc:+.3f}%) "
                    f"while signal is BUY — inverse leader not cooperating"
                )
                penalties += 1
        else:  # SELL
            if is_positive and leader_roc > 0.05:
                warnings.append(
                    f"Leading indicator {leader} rising ({leader_roc:+.3f}%) "
                    f"while signal is SELL — may be premature"
                )
                penalties += 1
            elif is_negative and leader_roc < -0.05:
                warnings.append(
                    f"Leading indicator {leader} falling ({leader_roc:+.3f}%) "
                    f"while signal is SELL — inverse leader not cooperating"
                )
                penalties += 1

    if leaders_checked == 0:
        return LeadingResult(aligned=True, warnings=[], confidence_factor=1.0)

    # Each penalty reduces confidence by 10%, max 30% reduction
    confidence_factor = max(0.70, 1.0 - (penalties * 0.10))
    aligned = penalties == 0

    return LeadingResult(
        aligned=aligned,
        warnings=warnings,
        confidence_factor=round(confidence_factor, 2),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  3. DIVERGENCE SIGNAL DETECTOR
# ─────────────────────────────────────────────────────────────────────────────

async def detect_divergence_signals(state: BotState) -> list[DivergenceSignal]:
    """
    Scans DIVERGENCE_PAIRS for catch-up opportunities.

    A divergence signal fires when:
      - The leader has moved significantly (>= threshold)
      - The lagger has barely moved (<= 30% of threshold)
      - The expected directional relationship holds

    Returns candidate signals at score=7.0 — these still need to pass
    the full technical analysis gate in market_analyst before trading.
    """
    candidates: list[DivergenceSignal] = []

    for leader, lagger, same_direction, threshold, sig_symbol, sig_dir in DIVERGENCE_PAIRS:
        # Need data for both
        leader_chg = _get_session_change_pct(leader, state)
        lagger_chg = _get_session_change_pct(lagger, state)

        if leader_chg is None or lagger_chg is None:
            continue

        # Has leader moved enough?
        leader_moved = abs(leader_chg) >= abs(threshold)
        if not leader_moved:
            continue

        # Is leader moving in the expected direction?
        correct_direction = (leader_chg > 0) == (threshold > 0)
        if not correct_direction:
            continue

        # Has lagger NOT moved yet (< 30% of threshold)?
        lagger_lagging = abs(lagger_chg) < abs(threshold) * 0.30
        if not lagger_lagging:
            continue

        # Don't generate a divergence signal if it contradicts existing open position
        existing = next(
            (t for t in state.open_trades if t.symbol == sig_symbol), None
        )
        if existing and existing.direction.value != sig_dir:
            continue

        reasoning = (
            f"DIVERGENCE SIGNAL: {leader} moved {leader_chg:+.3f}% "
            f"but {lagger} only moved {lagger_chg:+.3f}% — "
            f"catch-up expected on {sig_symbol} {sig_dir}"
        )

        # Confidence scales with how much the leader moved vs threshold
        strength_ratio = min(2.0, abs(leader_chg) / abs(threshold))
        confidence = round(min(0.80, 0.60 + strength_ratio * 0.10), 2)

        candidates.append(DivergenceSignal(
            symbol=sig_symbol,
            direction=sig_dir,
            score=7.0,
            confidence=confidence,
            leader=leader,
            leader_change=round(leader_chg, 4),
            lagger_change=round(lagger_chg, 4),
            reasoning=reasoning,
        ))
        log.info(
            "📐 DIVERGENCE: {} moved {:.3f}% — {} catch-up {} expected (confidence {:.0%})",
            leader, leader_chg, sig_symbol, sig_dir, confidence,
        )

    return candidates


def _divergence_to_signal(div: DivergenceSignal, state: BotState) -> Optional[TradingSignal]:
    """Convert a DivergenceSignal to a TradingSignal using live quote data."""
    quote = state.quotes.get(div.symbol)
    if not quote:
        return None

    mid = (quote.bid + quote.ask) / 2
    atr_proxy = quote.spread * 50  # rough ATR proxy when OHLCV unavailable

    # Try to get proper ATR from OHLCV
    bars = state.ohlcv_cache.get(div.symbol)
    if bars and len(bars) >= 15:
        try:
            highs  = [float(b.high  if hasattr(b,"high")  else b["high"])  for b in bars[-15:]]
            lows   = [float(b.low   if hasattr(b,"low")   else b["low"])   for b in bars[-15:]]
            closes = [float(b.close if hasattr(b,"close") else b["close"]) for b in bars[-15:]]
            trs = [
                max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
                for i in range(1, len(highs))
            ]
            atr_proxy = float(np.mean(trs))
        except Exception:
            pass

    is_buy   = div.direction == "BUY"
    sl       = round(mid - atr_proxy * 1.5, 5) if is_buy else round(mid + atr_proxy * 1.5, 5)
    tp       = round(mid + atr_proxy * 2.5, 5) if is_buy else round(mid - atr_proxy * 2.5, 5)
    sl_dist  = abs(mid - sl)
    tp_dist  = abs(mid - tp)
    rr       = round(tp_dist / sl_dist, 2) if sl_dist > 0 else 0.0

    return TradingSignal(
        id=str(uuid.uuid4()),
        symbol=div.symbol,
        asset_class=_asset_class_for(div.symbol),
        direction=Direction(div.direction),
        score=div.score,
        confidence=div.confidence,
        strength=SignalStrength.MEDIUM,
        strategy="correlation_divergence",
        timeframe="H1",
        entry_price=round(mid, 5),
        stop_loss=sl,
        take_profit=tp,
        risk_reward=rr,
        reasoning=div.reasoning,
        metadata={
            "leader":         div.leader,
            "leader_change":  div.leader_change,
            "lagger_change":  div.lagger_change,
            "source":         "divergence_detector",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
#  4. CORRELATION-ADJUSTED LOT SIZE
# ─────────────────────────────────────────────────────────────────────────────

def correlation_adjusted_lot_size(
    signal: TradingSignal,
    open_trades: list[Trade],
    base_lot_size: float,
) -> tuple[float, str]:
    """
    Scale down lot size when correlated positions are already open.

    Rules:
      0 existing same-direction positions in group → 100% size
      1 existing                                   →  70% size
      2 existing                                   →  50% size
      3 or more                                    →  35% size

    Returns (adjusted_lot_size, reason_string)
    """
    group = get_group(signal.symbol)
    if group is None:
        return base_lot_size, "no correlation group — full size"

    # Count same-direction trades in the same correlation group
    group_members = CORRELATION_GROUPS.get(group, [])
    same_dir_count = sum(
        1 for t in open_trades
        if t.symbol in group_members
        and t.symbol != signal.symbol
        and t.direction.value == signal.direction.value
    )

    scale_factors = {0: 1.00, 1: 0.70, 2: 0.50, 3: 0.35}
    scale = scale_factors.get(min(same_dir_count, 3), 0.35)
    adjusted = round(base_lot_size * scale, 2)
    adjusted = max(adjusted, 0.01)  # never below minimum

    reason = (
        f"group={group}, existing_same_dir={same_dir_count}, "
        f"scale={scale:.0%}, lot={base_lot_size}→{adjusted}"
    )
    return adjusted, reason


# ─────────────────────────────────────────────────────────────────────────────
#  5. GROUP CONCENTRATION VETO
# ─────────────────────────────────────────────────────────────────────────────

def check_group_concentration(
    signal: TradingSignal,
    open_trades: list[Trade],
) -> tuple[bool, str]:
    """
    Returns (allowed, reason).
    allowed=False means the signal must be rejected due to group concentration.
    """
    group = get_group(signal.symbol)
    if group is None:
        return True, "no group"

    max_allowed = GROUP_MAX_SAME_DIRECTION.get(group, 2)
    if max_allowed == 0:
        return False, f"symbol in reference-only group '{group}' — not traded directly"

    group_members = CORRELATION_GROUPS.get(group, [])
    existing_same_dir = [
        t for t in open_trades
        if t.symbol in group_members
        and t.direction.value == signal.direction.value
    ]

    if len(existing_same_dir) >= max_allowed:
        return False, (
            f"group '{group}' already has {len(existing_same_dir)} "
            f"{signal.direction.value} positions (max {max_allowed})"
        )

    return True, f"group '{group}' has {len(existing_same_dir)}/{max_allowed} positions — OK"


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN AGENT NODE
# ─────────────────────────────────────────────────────────────────────────────

async def correlation_agent_node(state: BotState) -> BotState:
    """
    LangGraph node — runs after market_analyst, before sentiment_agent.

    Steps per signal:
      1. Group concentration veto        (hard reject if group is full)
      2. Correlation confirmation score  (boost / reduce signal score)
      3. Leading indicator check         (reduce confidence if leaders not aligned)
      4. Reject if net boost < -1.0      (majority of related assets contradict)
      5. Adjust lot size for correlation (scale down if correlated positions open)

    Additional:
      6. Detect divergence signals and inject into pending_signals
    """
    log.info(
        "📐 CorrelationAgent: Evaluating {} signals | {} open trades",
        len(state.pending_signals), len(state.open_trades),
    )

    if not state.pending_signals:
        # Still run divergence detection even with no pending signals
        divs = await detect_divergence_signals(state)
        for div in divs:
            sig = _divergence_to_signal(div, state)
            if sig and sig.risk_reward >= 1.5:
                state.pending_signals.append(sig)
                log.info("📐 Injected divergence signal: {} {} score={:.1f}",
                         sig.symbol, sig.direction.value, sig.score)
        return state

    enhanced: list[TradingSignal] = []

    # Process all signals concurrently
    tasks = [
        _evaluate_signal(signal, state)
        for signal in state.pending_signals
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for signal, result in zip(state.pending_signals, results):
        if isinstance(result, Exception):
            log.error("CorrelationAgent error for {}: {}", signal.symbol, result)
            enhanced.append(signal)  # pass through unchanged on error
            continue

        accepted, final_signal = result
        if accepted:
            enhanced.append(final_signal)

    # ── Divergence detection ──────────────────────────────────────────────
    divs = await detect_divergence_signals(state)
    for div in divs:
        # Skip if we already have a signal for this symbol+direction
        already = any(
            s.symbol == div.symbol and s.direction.value == div.direction
            for s in enhanced
        )
        if already:
            continue

        sig = _divergence_to_signal(div, state)
        if sig is None:
            continue

        # Divergence signals still need to pass group concentration check
        allowed, reason = check_group_concentration(sig, state.open_trades)
        if not allowed:
            log.info("📐 Divergence signal {} {} rejected: {}", sig.symbol, sig.direction.value, reason)
            continue

        if sig.risk_reward >= 1.5:
            enhanced.append(sig)
            log.success("📐 Divergence signal added: {} {} score={:.1f} conf={:.0%}",
                        sig.symbol, sig.direction.value, sig.score, sig.confidence)

    log.info(
        "📐 CorrelationAgent: {}/{} signals passed (+{} divergence) | {} rejected",
        len([s for s in enhanced if s.strategy != "correlation_divergence"]),
        len(state.pending_signals),
        len([s for s in enhanced if s.strategy == "correlation_divergence"]),
        len(state.pending_signals) - len([s for s in enhanced if s.strategy != "correlation_divergence"]),
    )

    state.pending_signals = enhanced
    return state


async def _evaluate_signal(
    signal: TradingSignal,
    state: BotState,
) -> tuple[bool, TradingSignal]:
    """
    Evaluate a single signal through the correlation pipeline.
    Returns (accepted, modified_signal).
    """

    # ── Step 1: Group concentration veto ─────────────────────────────────
    allowed, conc_reason = check_group_concentration(signal, state.open_trades)
    if not allowed:
        log.info(
            "📐 REJECTED {} {} — group veto: {}",
            signal.direction.value, signal.symbol, conc_reason,
        )
        return False, signal

    # ── Step 2: Correlation confirmation score ────────────────────────────
    conf_result = await correlation_confirmation(signal, state)
    original_score = signal.score
    signal.score = round(min(10.0, max(0.0, signal.score + conf_result.boost)), 2)
    signal.metadata["correlation_boost"]    = conf_result.boost
    signal.metadata["corr_confirmations"]   = conf_result.confirmations
    signal.metadata["corr_contradictions"]  = conf_result.contradictions

    log.info(
        "📐 {} {} | score {:.1f}→{:.1f} | confirms={} contradicts={} | boost={:+.2f}",
        signal.direction.value, signal.symbol,
        original_score, signal.score,
        conf_result.confirmations, conf_result.contradictions,
        conf_result.boost,
    )
    for line in conf_result.detail:
        log.debug("   {}", line)

    # ── Step 3: Reject if too many contradictions ─────────────────────────
    REJECTION_BOOST_THRESHOLD = -1.0
    if conf_result.boost < REJECTION_BOOST_THRESHOLD:
        log.info(
            "📐 REJECTED {} {} — correlation boost {:.2f} < threshold {:.2f} "
            "(confirms={}, contradicts={})",
            signal.direction.value, signal.symbol,
            conf_result.boost, REJECTION_BOOST_THRESHOLD,
            conf_result.confirmations, conf_result.contradictions,
        )
        return False, signal

    # ── Step 4: Leading indicator check ──────────────────────────────────
    leading = await leading_indicator_check(signal, state)
    if not leading.aligned:
        original_conf = signal.confidence
        signal.confidence = round(signal.confidence * leading.confidence_factor, 3)
        signal.metadata["leading_factor"]   = leading.confidence_factor
        signal.metadata["leading_warnings"] = leading.warnings
        for w in leading.warnings:
            log.warning("📐 Leading indicator: {} {} — {}", signal.symbol, signal.direction.value, w)
        log.info(
            "📐 {} {} confidence adjusted {:.0%}→{:.0%} (leading factor {:.0%})",
            signal.direction.value, signal.symbol,
            original_conf, signal.confidence, leading.confidence_factor,
        )

    # ── Step 5: Correlation-adjusted lot size ─────────────────────────────
    base_lot = signal.metadata.get("lot_size", 0.01)
    adj_lot, size_reason = correlation_adjusted_lot_size(
        signal, state.open_trades, base_lot
    )
    if adj_lot != base_lot:
        signal.metadata["lot_size"]           = adj_lot
        signal.metadata["lot_size_base"]      = base_lot
        signal.metadata["lot_size_reason"]    = size_reason
        log.info(
            "📐 {} {} lot size adjusted {:.2f}→{:.2f} ({})",
            signal.direction.value, signal.symbol, base_lot, adj_lot, size_reason,
        )

    return True, signal


# ─────────────────────────────────────────────────────────────────────────────
#  SUMMARY HELPER  (used by orchestrator for LLM context)
# ─────────────────────────────────────────────────────────────────────────────

def build_correlation_summary(signal: TradingSignal) -> str:
    """
    Build a human-readable correlation summary for LLM prompts.
    """
    meta = signal.metadata
    lines = [f"Correlation analysis for {signal.symbol} {signal.direction.value}:"]

    boost = meta.get("correlation_boost")
    if boost is not None:
        lines.append(
            f"  Score adjustment: {boost:+.2f} "
            f"({meta.get('corr_confirmations',0)} confirms, "
            f"{meta.get('corr_contradictions',0)} contradicts)"
        )

    warnings = meta.get("leading_warnings", [])
    if warnings:
        lines.append("  Leading indicator warnings:")
        for w in warnings:
            lines.append(f"    - {w}")

    if meta.get("source") == "divergence_detector":
        lines.append(
            f"  SOURCE: Divergence signal — "
            f"{meta.get('leader')} moved {meta.get('leader_change',0):+.3f}% "
            f"but {signal.symbol} only moved {meta.get('lagger_change',0):+.3f}%"
        )

    lot_reason = meta.get("lot_size_reason")
    if lot_reason and meta.get("lot_size_base") != meta.get("lot_size"):
        lines.append(f"  Lot size: {lot_reason}")

    return "\n".join(lines)
