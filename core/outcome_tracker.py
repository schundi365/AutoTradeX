"""
APEX Bot — Outcome Tracker & Adaptive Learning
Track decision outcomes to improve future decisions.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

from loguru import logger as log

from core.models import TradingSignal, Trade
from core.config import settings


class Outcome(str, Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"
    PENDING = "PENDING"


@dataclass
class DecisionRecord:
    """Record of a trading decision and its outcome"""
    timestamp: datetime
    symbol: str
    decision: str  # GO, NOGO
    signal_score: float
    confidence: float
    risk_reward: float
    indicators: Dict[str, float]
    market_regime: str
    outcome: Outcome
    pnl: float = 0.0
    trade_id: Optional[str] = None


class OutcomeTracker:
    """
    Track decision outcomes to improve future decisions.
    """
    
    def __init__(self):
        self.decision_history: List[DecisionRecord] = []
        self._lock = asyncio.Lock()
    
    async def log_decision(
        self,
        signal: TradingSignal,
        decision: str,
        trade: Optional[Trade] = None
    ):
        """Log a trading decision"""
        async with self._lock:
            record = DecisionRecord(
                timestamp=datetime.utcnow(),
                symbol=signal.symbol,
                decision=decision,
                signal_score=signal.score,
                confidence=signal.confidence,
                risk_reward=signal.risk_reward,
                indicators=signal.metadata or {},
                market_regime=signal.metadata.get("regime", "UNKNOWN") if signal.metadata else "UNKNOWN",
                outcome=Outcome.PENDING,
                trade_id=trade.id if trade else None
            )
            
            self.decision_history.append(record)
            
            # Keep only last 1000 decisions
            if len(self.decision_history) > 1000:
                self.decision_history = self.decision_history[-1000:]
    
    async def update_outcome(self, trade_id: str, outcome: Outcome, pnl: float):
        """Update outcome for a completed trade"""
        async with self._lock:
            for record in self.decision_history:
                if record.trade_id == trade_id:
                    record.outcome = outcome
                    record.pnl = pnl
                    log.info(
                        f"[OUTCOME] {record.symbol} {outcome.value}: "
                        f"score={record.signal_score:.1f}, pnl=${pnl:.2f}"
                    )
                    break
    
    def get_pattern_success_rate(self, pattern: Dict[str, any]) -> float:
        """
        Get success rate for specific pattern.
        Pattern can include: regime, score_range, symbol, etc.
        """
        matches = [
            d for d in self.decision_history
            if self._matches_pattern(d, pattern) and d.outcome != Outcome.PENDING
        ]
        
        if not matches:
            return 0.5  # Default 50% if no data
        
        wins = sum(1 for d in matches if d.outcome == Outcome.WIN)
        return wins / len(matches)
    
    def _matches_pattern(self, record: DecisionRecord, pattern: Dict[str, any]) -> bool:
        """Check if record matches pattern"""
        for key, value in pattern.items():
            if key == "regime":
                if record.market_regime != value:
                    return False
            elif key == "symbol":
                if record.symbol != value:
                    return False
            elif key == "score_min":
                if record.signal_score < value:
                    return False
            elif key == "score_max":
                if record.signal_score > value:
                    return False
        
        return True
    
    def get_recent_performance(self, lookback_trades: int = 20) -> Dict[str, float]:
        """Get recent performance metrics"""
        recent = [
            d for d in self.decision_history[-lookback_trades:]
            if d.outcome != Outcome.PENDING and d.decision == "GO"
        ]
        
        if not recent:
            return {
                "win_rate": 0.5,
                "avg_pnl": 0.0,
                "total_trades": 0,
                "wins": 0,
                "losses": 0
            }
        
        wins = sum(1 for d in recent if d.outcome == Outcome.WIN)
        losses = sum(1 for d in recent if d.outcome == Outcome.LOSS)
        total_pnl = sum(d.pnl for d in recent)
        
        return {
            "win_rate": wins / len(recent) if recent else 0.5,
            "avg_pnl": total_pnl / len(recent) if recent else 0.0,
            "total_trades": len(recent),
            "wins": wins,
            "losses": losses
        }
    
    def get_regime_performance(self) -> Dict[str, Dict[str, float]]:
        """Get performance breakdown by market regime"""
        regimes = {}
        
        for record in self.decision_history:
            if record.outcome == Outcome.PENDING or record.decision != "GO":
                continue
            
            regime = record.market_regime
            if regime not in regimes:
                regimes[regime] = {"wins": 0, "losses": 0, "total_pnl": 0.0}
            
            if record.outcome == Outcome.WIN:
                regimes[regime]["wins"] += 1
            elif record.outcome == Outcome.LOSS:
                regimes[regime]["losses"] += 1
            
            regimes[regime]["total_pnl"] += record.pnl
        
        # Calculate win rates
        for regime, stats in regimes.items():
            total = stats["wins"] + stats["losses"]
            stats["win_rate"] = stats["wins"] / total if total > 0 else 0.5
            stats["avg_pnl"] = stats["total_pnl"] / total if total > 0 else 0.0
        
        return regimes


class AdaptiveThresholds:
    """
    Adjust decision thresholds based on recent performance.
    """
    
    def __init__(self, outcome_tracker: OutcomeTracker):
        self.outcome_tracker = outcome_tracker
        
        # Initial thresholds
        self.min_score = 6.5
        self.min_confidence = 0.6
        self.min_rr = 1.8
        
        # Adjustment limits
        self.score_min = 6.0
        self.score_max = 8.0
        self.confidence_min = 0.5
        self.confidence_max = 0.85
        self.rr_min = 1.5
        self.rr_max = 3.0
    
    async def adjust_based_on_performance(self):
        """Adjust thresholds based on recent performance"""
        perf = self.outcome_tracker.get_recent_performance(lookback_trades=20)
        
        win_rate = perf["win_rate"]
        avg_pnl = perf["avg_pnl"]
        
        log.info(
            f"[ADAPTIVE] Recent performance: WR={win_rate:.1%}, "
            f"Avg PnL=${avg_pnl:.2f}, Trades={perf['total_trades']}"
        )
        
        # Not enough data yet
        if perf["total_trades"] < 10:
            log.debug("[ADAPTIVE] Not enough trades for adjustment")
            return
        
        # Losing - be more selective
        if win_rate < 0.45 or avg_pnl < -50:
            self.min_score = min(self.min_score + 0.3, self.score_max)
            self.min_confidence = min(self.min_confidence + 0.05, self.confidence_max)
            self.min_rr = min(self.min_rr + 0.2, self.rr_max)
            
            log.warning(
                f"[ADAPTIVE] Tightening thresholds due to poor performance: "
                f"score>={self.min_score:.1f}, conf>={self.min_confidence:.0%}, RR>={self.min_rr:.1f}"
            )
        
        # Winning - can be more aggressive
        elif win_rate > 0.65 and avg_pnl > 100:
            self.min_score = max(self.min_score - 0.2, self.score_min)
            self.min_confidence = max(self.min_confidence - 0.03, self.confidence_min)
            self.min_rr = max(self.min_rr - 0.1, self.rr_min)
            
            log.info(
                f"[ADAPTIVE] Loosening thresholds due to strong performance: "
                f"score>={self.min_score:.1f}, conf>={self.min_confidence:.0%}, RR>={self.min_rr:.1f}"
            )
        
        # Moderate performance - slight adjustment toward baseline
        else:
            # Gradually return to baseline
            baseline_score = 6.5
            baseline_conf = 0.6
            baseline_rr = 1.8
            
            self.min_score = self.min_score * 0.9 + baseline_score * 0.1
            self.min_confidence = self.min_confidence * 0.9 + baseline_conf * 0.1
            self.min_rr = self.min_rr * 0.9 + baseline_rr * 0.1
            
            log.debug(
                f"[ADAPTIVE] Adjusting toward baseline: "
                f"score>={self.min_score:.1f}, conf>={self.min_confidence:.0%}, RR>={self.min_rr:.1f}"
            )
    
    def get_thresholds(self) -> Dict[str, float]:
        """Get current thresholds"""
        return {
            "min_score": self.min_score,
            "min_confidence": self.min_confidence,
            "min_rr": self.min_rr
        }
