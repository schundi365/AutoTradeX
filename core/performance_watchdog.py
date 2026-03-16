"""
APEX Bot — Performance Watchdog
================================
Monitors live trading performance and does three things no other module does:

  1. MISSED SIGNAL DETECTION
     After every cycle, look at signals that were NOGO'd in the previous
     4–8 hours and check whether price subsequently moved favourably.
     If it did, that is a false negative — a missed opportunity.
     The watchdog counts these, groups them by rejection reason, and surfaces
     an insight: "You keep rejecting EURUSD BUY signals for 'ADX too low'
     but 3 of those moves paid +1.8% — consider loosening ADX gate."

  2. DEGRADATION DETECTION
     Compare a short (10-trade) win-rate window against a longer baseline
     (50-trade).  If the short window drops more than DROP_THRESHOLD (10 pp)
     below baseline, emit a WARNING alert and recommend tighter thresholds.
     At a CRITICAL drop (20 pp), flag that model retraining should be
     triggered.

  3. POSITIVE FACTOR IDENTIFICATION
     Alongside the negatives, identify what IS working:
     - Which regimes are profitable
     - Which strategies are winning
     - Which symbols are on a hot streak
     Output these as a structured "what's working" summary so the
     orchestrator can give them more weight in its LLM context.

All output goes into a WatchdogReport dataclass which is serialised to
BotState.strategy_params["watchdog_report"] by the strategy_adapter_node.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from loguru import logger as log


# ─────────────────────────────────────────────────────────────────────────────
#  DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MissedSignal:
    """A NOGO decision that turned out to be a missed opportunity."""
    timestamp:       datetime
    symbol:          str
    direction:       str
    rejection_reason: str
    entry_price_at_rejection: float
    current_price:   float
    estimated_pnl_pct: float   # positive = would have been profitable
    atr_at_rejection: float


@dataclass
class WatchdogReport:
    timestamp:          datetime = field(default_factory=datetime.utcnow)

    # ── Performance state ─────────────────────────────────────────────────
    alert_level:        str = "OK"        # "OK" | "WARNING" | "CRITICAL"
    is_degraded:        bool = False
    degradation_reason: str = ""

    win_rate_short:     float = 0.0       # last 10 resolved trades
    win_rate_baseline:  float = 0.0       # last 50 resolved trades
    win_rate_drop:      float = 0.0       # short - baseline (negative = degradation)

    avg_pnl_short:      float = 0.0
    avg_pnl_baseline:   float = 0.0
    total_resolved:     int   = 0

    # ── Missed signals ────────────────────────────────────────────────────
    missed_signals:      List[MissedSignal] = field(default_factory=list)
    missed_count:        int   = 0
    missed_total_pnl_pct: float = 0.0     # sum of estimated missed profits
    top_miss_reason:     str = ""         # most common rejection reason
    top_miss_symbol:     str = ""         # symbol with most misses

    # ── What's working ────────────────────────────────────────────────────
    hot_symbols:        List[str] = field(default_factory=list)
    hot_strategies:     List[str] = field(default_factory=list)
    best_regime:        str = ""
    cold_symbols:       List[str] = field(default_factory=list)

    # ── Suggested adjustments ─────────────────────────────────────────────
    suggested_adjustments: Dict[str, float] = field(default_factory=dict)

    # ── Retraining flag ───────────────────────────────────────────────────
    trigger_retraining: bool = False
    retraining_reason:  str  = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        d["missed_signals"] = [
            {**ms, "timestamp": ms["timestamp"].isoformat()}
            for ms in d["missed_signals"]
        ]
        return d

    def llm_summary(self) -> str:
        """Compact summary for injecting into the orchestrator LLM prompt."""
        lines = [f"[WATCHDOG] {self.alert_level} | WR short={self.win_rate_short:.0%} "
                 f"baseline={self.win_rate_baseline:.0%} drop={self.win_rate_drop:+.0%}"]

        if self.is_degraded:
            lines.append(f"  ⚠ DEGRADED: {self.degradation_reason}")

        if self.missed_count > 0:
            lines.append(
                f"  Missed signals (last 4h): {self.missed_count} | "
                f"top reason='{self.top_miss_reason}' | "
                f"top symbol={self.top_miss_symbol}"
            )

        if self.hot_symbols:
            lines.append(f"  HOT symbols: {', '.join(self.hot_symbols[:4])}")
        if self.cold_symbols:
            lines.append(f"  COLD symbols: {', '.join(self.cold_symbols[:4])}")
        if self.hot_strategies:
            lines.append(f"  Winning strategies: {', '.join(self.hot_strategies[:3])}")

        if self.suggested_adjustments:
            adj = ", ".join(f"{k}:{v:+.2f}" for k, v in self.suggested_adjustments.items())
            lines.append(f"  Suggested adjustments: {adj}")

        if self.trigger_retraining:
            lines.append(f"  ML RETRAIN FLAGGED: {self.retraining_reason}")

        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  PERFORMANCE WATCHDOG
# ─────────────────────────────────────────────────────────────────────────────

class PerformanceWatchdog:
    """
    Run once per bot cycle (via strategy_adapter_node) to produce a
    WatchdogReport containing degradation alerts, missed signal analysis,
    and hot/cold signal classification.
    """

    # Thresholds
    SHORT_WINDOW    = 10     # trades for short win-rate
    BASELINE_WINDOW = 50     # trades for baseline win-rate
    MIN_TRADES      = 5      # don't alert if fewer resolved trades

    DROP_WARNING    = 0.10   # 10 pp drop triggers WARNING
    DROP_CRITICAL   = 0.20   # 20 pp drop triggers CRITICAL + retrain flag

    # Missed signal parameters
    MISS_LOOKBACK_HOURS = 6  # look at NOGO'd signals from last N hours
    MISS_THRESHOLD_PCT  = 0.40  # price moved > 0.4% favourably → count as miss

    def __init__(self):
        self._last_report: Optional[WatchdogReport] = None
        self._run_count = 0

    async def run(
        self,
        outcome_tracker,    # OutcomeTracker
        state,              # BotState
    ) -> WatchdogReport:
        """
        Full watchdog analysis.  Safe — never raises; returns a safe default
        report on any internal error.
        """
        self._run_count += 1
        try:
            report = WatchdogReport()

            await self._check_performance(report, outcome_tracker)
            await self._detect_missed_signals(report, outcome_tracker, state)
            await self._identify_positive_factors(report, outcome_tracker)
            self._suggest_adjustments(report)

            self._last_report = report
            self._log_report(report)
            return report

        except Exception as exc:
            log.error("[WATCHDOG] Unexpected error: {} — returning safe default", exc)
            return WatchdogReport(alert_level="OK")

    # ── 1. Performance degradation check ─────────────────────────────────

    async def _check_performance(
        self,
        report: WatchdogReport,
        outcome_tracker,
    ):
        from core.outcome_tracker import Outcome

        resolved = [
            r for r in outcome_tracker.decision_history
            if r.outcome != Outcome.PENDING and r.decision == "GO"
        ]

        report.total_resolved = len(resolved)

        if len(resolved) < self.MIN_TRADES:
            return   # not enough data

        # Short window
        short = resolved[-self.SHORT_WINDOW:]
        short_wins = sum(1 for r in short if r.outcome == Outcome.WIN)
        report.win_rate_short = short_wins / len(short)
        report.avg_pnl_short  = sum(r.pnl for r in short) / len(short)

        # Baseline window
        baseline = resolved[-self.BASELINE_WINDOW:]
        base_wins = sum(1 for r in baseline if r.outcome == Outcome.WIN)
        report.win_rate_baseline = base_wins / len(baseline)
        report.avg_pnl_baseline  = sum(r.pnl for r in baseline) / len(baseline)

        report.win_rate_drop = report.win_rate_short - report.win_rate_baseline

        if report.win_rate_drop <= -self.DROP_CRITICAL:
            report.is_degraded        = True
            report.alert_level        = "CRITICAL"
            report.degradation_reason = (
                f"Short win rate {report.win_rate_short:.0%} is "
                f"{abs(report.win_rate_drop):.0%} below "
                f"baseline {report.win_rate_baseline:.0%}"
            )
            report.trigger_retraining = True
            report.retraining_reason  = (
                f"Win rate degraded {abs(report.win_rate_drop):.0%} "
                f"over last {self.SHORT_WINDOW} trades"
            )

        elif report.win_rate_drop <= -self.DROP_WARNING:
            report.is_degraded        = True
            report.alert_level        = "WARNING"
            report.degradation_reason = (
                f"Short win rate {report.win_rate_short:.0%} is "
                f"{abs(report.win_rate_drop):.0%} below baseline"
            )

    # ── 2. Missed signal detection ────────────────────────────────────────

    async def _detect_missed_signals(
        self,
        report: WatchdogReport,
        outcome_tracker,
        state,
    ):
        """
        Identify NOGO decisions from the last MISS_LOOKBACK_HOURS where
        the price subsequently moved favourably — these are false negatives.

        We use the DecisionRecord's indicators dict which stores entry_price
        and direction at decision time.  We compare against current quotes.
        """
        cutoff = datetime.utcnow() - timedelta(hours=self.MISS_LOOKBACK_HOURS)

        nogo_records = [
            r for r in outcome_tracker.decision_history
            if r.decision == "NOGO"
            and r.timestamp >= cutoff
            and r.symbol in state.quotes
        ]

        misses: List[MissedSignal] = []
        miss_reasons: Dict[str, int] = {}
        miss_symbols: Dict[str, int] = {}

        for record in nogo_records:
            quote = state.quotes.get(record.symbol)
            if not quote:
                continue

            entry_price = record.indicators.get("entry_price", 0.0)
            direction   = record.indicators.get("direction", "")
            atr         = record.indicators.get("atr", 0.0)

            if not entry_price or not direction or entry_price == 0:
                continue

            current_mid = (quote.bid + quote.ask) / 2
            pct_move = (current_mid - entry_price) / entry_price * 100

            # Was the move in the direction of the signal?
            if direction in ("BUY", "LONG"):
                favourable_pct = pct_move
            else:
                favourable_pct = -pct_move

            # Only count as missed if move > threshold
            if favourable_pct < self.MISS_THRESHOLD_PCT:
                continue

            # Pull rejection reason from stored metadata
            rejection_reason = record.indicators.get("rejection_reason", "unknown")

            miss = MissedSignal(
                timestamp=record.timestamp,
                symbol=record.symbol,
                direction=direction,
                rejection_reason=rejection_reason,
                entry_price_at_rejection=entry_price,
                current_price=current_mid,
                estimated_pnl_pct=round(favourable_pct, 3),
                atr_at_rejection=atr,
            )
            misses.append(miss)
            miss_reasons[rejection_reason] = miss_reasons.get(rejection_reason, 0) + 1
            miss_symbols[record.symbol]    = miss_symbols.get(record.symbol, 0) + 1

        report.missed_signals       = misses
        report.missed_count         = len(misses)
        report.missed_total_pnl_pct = round(sum(m.estimated_pnl_pct for m in misses), 2)

        if miss_reasons:
            report.top_miss_reason = max(miss_reasons, key=miss_reasons.get)
        if miss_symbols:
            report.top_miss_symbol = max(miss_symbols, key=miss_symbols.get)

    # ── 3. Positive factor identification ────────────────────────────────

    async def _identify_positive_factors(
        self,
        report: WatchdogReport,
        outcome_tracker,
    ):
        from core.outcome_tracker import Outcome

        resolved = [
            r for r in outcome_tracker.decision_history[-self.BASELINE_WINDOW:]
            if r.outcome != Outcome.PENDING and r.decision == "GO"
        ]
        if not resolved:
            return

        # ── Symbol heat map ───────────────────────────────────────────────
        sym_buckets: Dict[str, Dict[str, int]] = {}
        for r in resolved:
            s = r.symbol
            if s not in sym_buckets:
                sym_buckets[s] = {"wins": 0, "total": 0}
            sym_buckets[s]["total"] += 1
            if r.outcome == Outcome.WIN:
                sym_buckets[s]["wins"] += 1

        sym_wrs = {
            s: b["wins"] / b["total"]
            for s, b in sym_buckets.items()
            if b["total"] >= 3
        }

        report.hot_symbols  = sorted(
            [s for s, wr in sym_wrs.items() if wr >= 0.60], key=sym_wrs.get, reverse=True
        )[:5]
        report.cold_symbols = sorted(
            [s for s, wr in sym_wrs.items() if wr < 0.40], key=sym_wrs.get
        )[:5]

        # ── Strategy heat map ─────────────────────────────────────────────
        strat_buckets: Dict[str, Dict[str, int]] = {}
        for r in resolved:
            strat = r.indicators.get("strategy", "unknown")
            if strat not in strat_buckets:
                strat_buckets[strat] = {"wins": 0, "total": 0}
            strat_buckets[strat]["total"] += 1
            if r.outcome == Outcome.WIN:
                strat_buckets[strat]["wins"] += 1

        strat_wrs = {
            s: b["wins"] / b["total"]
            for s, b in strat_buckets.items()
            if b["total"] >= 3
        }
        report.hot_strategies = sorted(
            [s for s, wr in strat_wrs.items() if wr >= 0.55], key=strat_wrs.get, reverse=True
        )[:4]

        # ── Best regime ───────────────────────────────────────────────────
        regime_perf = outcome_tracker.get_regime_performance()
        if regime_perf:
            best = max(
                regime_perf.items(),
                key=lambda kv: kv[1].get("win_rate", 0) * min(kv[1].get("wins", 0) + kv[1].get("losses", 0), 20)
            )
            report.best_regime = best[0]

    # ── 4. Suggested adjustments ──────────────────────────────────────────

    def _suggest_adjustments(self, report: WatchdogReport):
        """
        Convert watchdog findings into concrete parameter adjustments.
        These are SUGGESTIONS stored in the report; the strategy_adapter_node
        decides whether to apply them.
        """
        adj: Dict[str, float] = {}

        if report.is_degraded:
            delta = 0.3 if report.alert_level == "WARNING" else 0.6
            adj["min_score_delta"]      = +delta
            adj["min_confidence_delta"] = +0.05 if report.alert_level == "WARNING" else +0.10

        # If a specific rejection reason dominates missed signals, loosen it
        if report.missed_count >= 3:
            reason = report.top_miss_reason.lower()
            if "adx" in reason:
                adj["min_adx_delta"] = -2.0
            elif "score" in reason or "g1" in reason:
                adj["min_score_delta"] = adj.get("min_score_delta", 0) - 0.3
            elif "confidence" in reason or "g2" in reason:
                adj["min_confidence_delta"] = adj.get("min_confidence_delta", 0) - 0.03
            elif "rr" in reason or "g3" in reason or "risk" in reason:
                adj["min_rr_delta"] = -0.15

        report.suggested_adjustments = adj

    # ── Logging ───────────────────────────────────────────────────────────

    def _log_report(self, report: WatchdogReport):
        level = report.alert_level
        fn = log.warning if level in ("WARNING", "CRITICAL") else log.info

        fn(
            "[WATCHDOG] {} | WR {:.0%} (short) vs {:.0%} (base) | "
            "missed={} | hot={} cold={}",
            level,
            report.win_rate_short,
            report.win_rate_baseline,
            report.missed_count,
            report.hot_symbols[:3],
            report.cold_symbols[:3],
        )

        if report.is_degraded:
            log.warning("[WATCHDOG] DEGRADATION: {}", report.degradation_reason)
        if report.trigger_retraining:
            log.critical("[WATCHDOG] RETRAIN FLAGGED: {}", report.retraining_reason)
        if report.missed_count >= 3:
            log.warning(
                "[WATCHDOG] {} missed signals this cycle | top reason: '{}' | "
                "top symbol: {} | est. missed PnL: {:.2f}%",
                report.missed_count,
                report.top_miss_reason,
                report.top_miss_symbol,
                report.missed_total_pnl_pct,
            )


# Module-level singleton
_watchdog = PerformanceWatchdog()


def get_watchdog() -> PerformanceWatchdog:
    return _watchdog
