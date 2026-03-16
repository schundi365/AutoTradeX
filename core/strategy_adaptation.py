"""
APEX Bot — Strategy Adaptation Engine
======================================
Closes the feedback loop between live performance and decision parameters.

What this does:
  1. Maintains a StrategyProfile per market regime — not just threshold tweaks,
     but full parameter sets: indicator weights, TP/SL multipliers, which
     signal strategies to prefer or avoid.
  2. After every N trades, mutates the active profile based on what is actually
     working in the CURRENT regime rather than in all regimes combined.
  3. Identifies which signal-generating strategies (momentum, breakout, etc.)
     are outperforming in the current regime and injects a score bonus so the
     market_analyst favours them.
  4. Tracks per-symbol performance — if XAUUSD is cold, its signals are scored
     down; if EURUSD is on fire, its signals get a bump.
  5. Exposes get_signal_adjustments() so market_analyst and risk_manager can
     consume the adapted parameters without any hard-coded imports loop.

Integration:
  strategy_adapter_node reads this engine and writes the result into
  BotState.strategy_params.  Downstream nodes read from that dict.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from loguru import logger as log


# ─────────────────────────────────────────────────────────────────────────────
#  BASE REGIME PROFILES
#  These are the starting points before live-performance tuning.
#  Each field is the "intended" value for this market condition.
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StrategyProfile:
    regime: str

    # ── Decision thresholds ───────────────────────────────────────────────
    min_score:        float = 6.5   # minimum signal score to even consider
    min_confidence:   float = 0.60  # minimum LLM/model confidence
    min_rr:           float = 1.8   # minimum risk/reward ratio
    min_adx:          float = 20.0  # minimum ADX (trend strength)
    max_atr_ratio:    float = 2.0   # maximum ATR multiplier (volatility cap)
    min_volume_ratio: float = 0.8   # minimum volume vs average

    # ── Position sizing / SL/TP ───────────────────────────────────────────
    sl_multiplier:    float = 1.5   # ATR × this = stop loss distance
    tp_multiplier:    float = 2.5   # ATR × this = take profit distance

    # ── Strategy signal preferences ───────────────────────────────────────
    preferred_strategies: List[str] = field(default_factory=list)
    avoided_strategies:   List[str] = field(default_factory=list)

    # Score adjustment applied to signals from preferred/avoided strategies
    strategy_score_bonus:   float = 0.5   # added to preferred
    strategy_score_penalty: float = -0.8  # added to avoided

    # ── Learned adjustments (overwritten by adaptation engine) ────────────
    score_adjustment:      float = 0.0   # net learned delta for score gate
    confidence_adjustment: float = 0.0   # net learned delta for confidence gate
    rr_adjustment:         float = 0.0   # net learned delta for RR gate

    # ── Symbol heat-map (symbol → score delta) ────────────────────────────
    symbol_score_delta: Dict[str, float] = field(default_factory=dict)

    # ── Metadata ──────────────────────────────────────────────────────────
    source:       str      = "default"   # "default" | "adapted"
    win_rate:     float    = 0.0
    trade_count:  int      = 0
    last_updated: datetime = field(default_factory=datetime.utcnow)

    # ── Convenience: effective thresholds (base + learned delta) ─────────
    @property
    def effective_min_score(self) -> float:
        return round(self.min_score + self.score_adjustment, 2)

    @property
    def effective_min_confidence(self) -> float:
        return round(self.min_confidence + self.confidence_adjustment, 3)

    @property
    def effective_min_rr(self) -> float:
        return round(self.min_rr + self.rr_adjustment, 2)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["last_updated"] = self.last_updated.isoformat()
        d["effective_min_score"]      = self.effective_min_score
        d["effective_min_confidence"] = self.effective_min_confidence
        d["effective_min_rr"]         = self.effective_min_rr
        return d


# ── Baseline profiles per MarketRegime ────────────────────────────────────────

_BASE_PROFILES: Dict[str, StrategyProfile] = {

    "STRONG_TREND": StrategyProfile(
        regime="STRONG_TREND",
        min_score=6.0,         # slightly easier — strong trends carry
        min_confidence=0.58,
        min_rr=2.0,
        min_adx=25.0,          # only real trending markets
        max_atr_ratio=2.2,
        min_volume_ratio=0.9,  # want volume behind the move
        sl_multiplier=1.5,
        tp_multiplier=3.0,     # let winners run in strong trends
        preferred_strategies=["momentum", "breakout", "order_block"],
        avoided_strategies=["mean_reversion", "range_fade"],
        strategy_score_bonus=0.7,
        strategy_score_penalty=-1.0,
    ),

    "WEAK_TREND": StrategyProfile(
        regime="WEAK_TREND",
        min_score=6.5,
        min_confidence=0.60,
        min_rr=1.8,
        min_adx=18.0,
        max_atr_ratio=2.0,
        min_volume_ratio=0.8,
        sl_multiplier=1.5,
        tp_multiplier=2.5,
        preferred_strategies=["momentum", "order_block"],
        avoided_strategies=["range_fade"],
        strategy_score_bonus=0.4,
        strategy_score_penalty=-0.6,
    ),

    "RANGING": StrategyProfile(
        regime="RANGING",
        min_score=7.0,         # higher bar — false breakouts are lethal
        min_confidence=0.65,
        min_rr=1.6,
        min_adx=0.0,           # ADX is irrelevant in ranges — remove this gate
        max_atr_ratio=1.5,
        min_volume_ratio=0.7,
        sl_multiplier=1.0,     # tight stops at range boundaries
        tp_multiplier=1.8,     # take profit before the other side of range
        preferred_strategies=["mean_reversion", "range_fade", "fvg"],
        avoided_strategies=["breakout", "momentum"],
        strategy_score_bonus=0.8,
        strategy_score_penalty=-1.2,
    ),

    "HIGH_VOLATILE": StrategyProfile(
        regime="HIGH_VOLATILE",
        min_score=7.5,         # very selective — noise is high
        min_confidence=0.70,
        min_rr=2.5,            # need bigger cushion for wide spreads
        min_adx=22.0,
        max_atr_ratio=2.8,     # slightly more tolerant since vol is the game
        min_volume_ratio=1.0,  # must have volume or it's just noise
        sl_multiplier=2.0,     # wide stops to survive spikes
        tp_multiplier=3.0,
        preferred_strategies=["breakout", "order_block"],
        avoided_strategies=["mean_reversion", "range_fade", "fvg"],
        strategy_score_bonus=0.5,
        strategy_score_penalty=-1.5,
    ),

    "LOW_VOLATILE": StrategyProfile(
        regime="LOW_VOLATILE",
        min_score=7.0,
        min_confidence=0.65,
        min_rr=1.8,
        min_adx=15.0,
        max_atr_ratio=1.2,
        min_volume_ratio=0.7,
        sl_multiplier=1.2,
        tp_multiplier=2.0,
        preferred_strategies=["fvg", "order_block"],
        avoided_strategies=["breakout"],
        strategy_score_bonus=0.3,
        strategy_score_penalty=-0.5,
    ),

    "BREAKOUT": StrategyProfile(
        regime="BREAKOUT",
        min_score=6.2,
        min_confidence=0.60,
        min_rr=2.2,
        min_adx=22.0,
        max_atr_ratio=3.0,     # breakouts can spike ATR
        min_volume_ratio=1.1,  # breakout must have volume
        sl_multiplier=1.8,
        tp_multiplier=3.5,     # big moves expected
        preferred_strategies=["breakout", "momentum", "order_block"],
        avoided_strategies=["mean_reversion", "range_fade"],
        strategy_score_bonus=0.8,
        strategy_score_penalty=-1.2,
    ),
}

# Fallback for unexpected regime strings
_BASE_PROFILES["NORMAL"]    = _BASE_PROFILES["WEAK_TREND"]
_BASE_PROFILES["VOLATILE"]  = _BASE_PROFILES["HIGH_VOLATILE"]
_BASE_PROFILES["TRENDING"]  = _BASE_PROFILES["STRONG_TREND"]


# ─────────────────────────────────────────────────────────────────────────────
#  STRATEGY ADAPTATION ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class StrategyAdaptationEngine:
    """
    Builds a live-performance-adapted StrategyProfile for the current
    market regime.

    Adaptation rules (applied on top of the base profile):
      - Overall regime win rate < 40%  → tighten score +0.5, conf +0.05
      - Overall regime win rate < 30%  → tighten score +1.0, conf +0.10, RR +0.3
      - Overall regime win rate > 65%  → loosen score -0.3, conf -0.03
      - Per-strategy win rate          → adjust strategy preference score
      - Per-symbol win rate            → adjust symbol_score_delta
      - < 5 trades in regime           → use base profile (cold start)
    """

    # How often (in bot cycles) to re-adapt — avoids thrashing
    ADAPT_EVERY_N_CYCLES = 5

    # Caps on how far learned adjustments can move from base
    MAX_SCORE_DELTA      =  2.0
    MIN_SCORE_DELTA      = -1.0
    MAX_CONF_DELTA       =  0.20
    MIN_CONF_DELTA       = -0.10
    MAX_RR_DELTA         =  0.80
    MIN_RR_DELTA         = -0.30

    def __init__(self):
        self._cycle_count = 0
        self._cached_profile: Optional[StrategyProfile] = None
        self._cached_regime:  str = ""

    def get_adapted_profile(
        self,
        regime: str,
        outcome_tracker,         # OutcomeTracker instance
    ) -> StrategyProfile:
        """
        Return a StrategyProfile for the current regime, adapted from
        live performance data.  Uses cached value if regime unchanged and
        within the adapt-every-N window.
        """
        self._cycle_count += 1

        # Use cache unless regime changed or adaptation window expired
        if (
            self._cached_profile is not None
            and self._cached_regime == regime
            and self._cycle_count % self.ADAPT_EVERY_N_CYCLES != 0
        ):
            return self._cached_profile

        # Deep copy of base profile so we never mutate the baseline
        import copy
        profile = copy.deepcopy(
            _BASE_PROFILES.get(regime.upper(), _BASE_PROFILES["WEAK_TREND"])
        )
        profile.regime = regime

        # ── Pull regime-specific performance ─────────────────────────────
        regime_perf = outcome_tracker.get_regime_performance()
        regime_stats = regime_perf.get(regime, {})
        win_rate    = regime_stats.get("win_rate", 0.0)
        trade_count = regime_stats.get("wins", 0) + regime_stats.get("losses", 0)

        profile.win_rate    = win_rate
        profile.trade_count = trade_count
        profile.source      = "default"

        if trade_count < 5:
            log.info(
                "[STRATEGY] Regime '{}': only {} trades — using base profile",
                regime, trade_count,
            )
            self._cached_profile = profile
            self._cached_regime  = regime
            return profile

        # ── Regime-level threshold adaptation ────────────────────────────
        profile.source = "adapted"
        score_delta = 0.0
        conf_delta  = 0.0
        rr_delta    = 0.0

        if win_rate < 0.30:
            score_delta = +1.0
            conf_delta  = +0.10
            rr_delta    = +0.30
            log.warning(
                "[STRATEGY] Regime '{}' WIN RATE {:.0%} — CRITICALLY TIGHTENING "
                "(score+1.0, conf+0.10, RR+0.30)",
                regime, win_rate,
            )
        elif win_rate < 0.40:
            score_delta = +0.50
            conf_delta  = +0.05
            log.warning(
                "[STRATEGY] Regime '{}' WIN RATE {:.0%} — tightening "
                "(score+0.5, conf+0.05)",
                regime, win_rate,
            )
        elif win_rate > 0.65:
            score_delta = -0.30
            conf_delta  = -0.03
            log.info(
                "[STRATEGY] Regime '{}' WIN RATE {:.0%} — loosening "
                "(score-0.3, conf-0.03)",
                regime, win_rate,
            )

        # Clamp deltas
        profile.score_adjustment      = max(self.MIN_SCORE_DELTA, min(self.MAX_SCORE_DELTA, score_delta))
        profile.confidence_adjustment = max(self.MIN_CONF_DELTA,  min(self.MAX_CONF_DELTA,  conf_delta))
        profile.rr_adjustment         = max(self.MIN_RR_DELTA,    min(self.MAX_RR_DELTA,    rr_delta))

        # ── Strategy-level preference adaptation ─────────────────────────
        # Which strategies have been winning/losing in this regime?
        strategy_win_rates = _compute_strategy_win_rates(outcome_tracker, regime)
        for strategy, s_win_rate in strategy_win_rates.items():
            if strategy.startswith("_n_"):
                continue   # skip count-tracking keys
            s_trades = strategy_win_rates.get(f"_n_{strategy}", 0)
            if s_trades < 3:
                continue   # not enough signal

            if s_win_rate >= 0.60 and strategy not in profile.preferred_strategies:
                profile.preferred_strategies.append(strategy)
                log.info(
                    "[STRATEGY] Regime '{}' — promoting strategy '{}' "
                    "(win rate {:.0%} over {} trades)",
                    regime, strategy, s_win_rate, s_trades,
                )
            elif s_win_rate < 0.35 and strategy not in profile.avoided_strategies:
                profile.avoided_strategies.append(strategy)
                # Remove from preferred if it was there
                profile.preferred_strategies = [
                    s for s in profile.preferred_strategies if s != strategy
                ]
                log.warning(
                    "[STRATEGY] Regime '{}' — demoting strategy '{}' "
                    "(win rate {:.0%} over {} trades)",
                    regime, strategy, s_win_rate, s_trades,
                )

        # ── Symbol-level score delta ─────────────────────────────────────
        symbol_deltas = _compute_symbol_score_deltas(outcome_tracker, regime)
        profile.symbol_score_delta = symbol_deltas

        for sym, delta in symbol_deltas.items():
            if abs(delta) >= 0.3:
                direction = "hot" if delta > 0 else "cold"
                log.info(
                    "[STRATEGY] Regime '{}' — symbol {} is {} (delta {:+.2f})",
                    regime, sym, direction, delta,
                )

        profile.last_updated = datetime.utcnow()

        log.info(
            "[STRATEGY] Profile for '{}' | WR={:.0%} | n={} | "
            "eff_score≥{:.1f} eff_conf≥{:.0%} eff_RR≥{:.1f} | "
            "preferred={} avoided={}",
            regime,
            win_rate,
            trade_count,
            profile.effective_min_score,
            profile.effective_min_confidence,
            profile.effective_min_rr,
            profile.preferred_strategies[:3],
            profile.avoided_strategies[:3],
        )

        self._cached_profile = profile
        self._cached_regime  = regime
        return profile

    def apply_signal_adjustments(
        self,
        signals: list,
        profile: StrategyProfile,
    ) -> list:
        """
        Apply strategy bonuses/penalties and symbol deltas to a list of
        TradingSignal objects.  Returns the same list with modified scores.
        """
        for sig in signals:
            original = sig.score
            delta = 0.0

            # Strategy preference bonus / penalty
            strat = (sig.strategy or "").lower()
            if any(p in strat for p in profile.preferred_strategies):
                delta += profile.strategy_score_bonus
            elif any(a in strat for a in profile.avoided_strategies):
                delta += profile.strategy_score_penalty

            # Symbol heat-map delta
            sym_delta = profile.symbol_score_delta.get(sig.symbol, 0.0)
            delta += sym_delta

            if delta != 0.0:
                sig.score = round(max(0.0, min(10.0, sig.score + delta)), 2)
                sig.metadata["strategy_adaptation_delta"] = delta
                sig.metadata["strategy_regime"]            = profile.regime
                log.debug(
                    "[STRATEGY] {} {} score {:.1f}→{:.1f} (delta {:+.2f}, strategy={})",
                    sig.direction, sig.symbol, original, sig.score, delta, strat,
                )

        return signals


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _compute_strategy_win_rates(
    outcome_tracker,
    regime: str,
) -> Dict[str, float]:
    """
    Compute per-strategy win rates from the outcome tracker's decision
    history, filtered to the given regime.  Returns dict of:
      strategy → win_rate  (plus _n_<strategy> → count keys)
    """
    buckets: Dict[str, Dict[str, int]] = {}

    for record in outcome_tracker.decision_history:
        from core.outcome_tracker import Outcome  # avoid circular at top
        if record.outcome == Outcome.PENDING or record.decision != "GO":
            continue
        if record.market_regime != regime:
            continue

        strategy = record.indicators.get("strategy", "unknown")
        if strategy not in buckets:
            buckets[strategy] = {"wins": 0, "losses": 0}

        if record.outcome == Outcome.WIN:
            buckets[strategy]["wins"] += 1
        elif record.outcome == Outcome.LOSS:
            buckets[strategy]["losses"] += 1

    result: Dict[str, float] = {}
    for strategy, stats in buckets.items():
        total = stats["wins"] + stats["losses"]
        if total > 0:
            result[strategy]          = stats["wins"] / total
            result[f"_n_{strategy}"]  = total   # stash count alongside
    return result


def _compute_symbol_score_deltas(
    outcome_tracker,
    regime: str,
    lookback: int = 30,
) -> Dict[str, float]:
    """
    For each symbol traded in the last `lookback` completed trades in this
    regime, compute a score delta in [-0.8, +0.8]:
      delta = (win_rate - 0.50) * 1.6   →  0.50 WR = 0.0,  0.80 WR = +0.48
    """
    from core.outcome_tracker import Outcome

    buckets: Dict[str, Dict[str, int]] = {}
    relevant = [
        r for r in outcome_tracker.decision_history[-lookback:]
        if r.outcome != Outcome.PENDING
        and r.decision == "GO"
        and r.market_regime == regime
    ]

    for record in relevant:
        sym = record.symbol
        if sym not in buckets:
            buckets[sym] = {"wins": 0, "losses": 0}
        if record.outcome == Outcome.WIN:
            buckets[sym]["wins"] += 1
        elif record.outcome == Outcome.LOSS:
            buckets[sym]["losses"] += 1

    deltas: Dict[str, float] = {}
    for sym, stats in buckets.items():
        total = stats["wins"] + stats["losses"]
        if total < 3:
            continue   # need at least 3 for significance
        wr = stats["wins"] / total
        delta = round((wr - 0.50) * 1.6, 2)
        delta = max(-0.8, min(0.8, delta))
        deltas[sym] = delta

    return deltas


# Singleton — shared across the pipeline run
_engine = StrategyAdaptationEngine()


def get_engine() -> StrategyAdaptationEngine:
    """Return the module-level singleton engine."""
    return _engine
