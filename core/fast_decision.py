"""
APEX Bot — Fast Path Decision Engine
Rule-based decisions for 90% of signals, only call LLM for edge cases.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple, List
from enum import Enum

from loguru import logger as log

from core.models import TradingSignal
from core.market_context import MarketContext, MarketRegime, RiskAppetite
from core.config import settings


class Decision(str, Enum):
    GO = "GO"
    NOGO = "NOGO"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass
class FastDecisionResult:
    decision: Decision
    confidence: float
    reason: str
    needs_llm_review: bool


class FastDecisionEngine:
    """
    Rule-based decision engine for clear signals.
    Returns GO/NOGO for 90% of cases, NEEDS_REVIEW for edge cases.

    Integrates with ML model predictions when available (backward compatible).
    Requirements: 11.1
    """

    def __init__(self, model_inference_service=None):
        """
        Initialize FastDecisionEngine.

        Args:
            model_inference_service: Optional ModelInferenceService for ML predictions
                                    If None, operates in rule-based mode only (backward compatible)

        Requirements: 11.1
        """
        # Thresholds for auto-approval
        self.strong_signal_score = 8.0
        self.strong_confidence = 0.8
        self.strong_risk_reward = 2.5

        # Thresholds for auto-rejection
        self.weak_signal_score = 6.0
        self.weak_confidence = 0.5
        self.weak_risk_reward = 1.5

        # Edge case thresholds (between strong and weak)
        self.edge_score_min = 6.5
        self.edge_score_max = 7.5

        # ML integration (optional, backward compatible)
        self.model_inference_service = model_inference_service
        self.ml_enabled = model_inference_service is not None

        # ML prediction thresholds
        self.ml_strong_prediction = 0.65  # High confidence UP prediction
        self.ml_weak_prediction = 0.35    # High confidence DOWN prediction
        self.ml_min_confidence = 0.6      # Minimum confidence to use ML prediction

        if self.ml_enabled:
            log.info("FastDecisionEngine initialized with ML predictions enabled")
        else:
            log.info("FastDecisionEngine initialized in rule-based mode (backward compatible)")

    async def evaluate(self, signal: TradingSignal, market_context: MarketContext) -> FastDecisionResult:
        """
        Evaluate signal using rule-based logic with optional ML enhancement.
        Returns: (decision, confidence, needs_llm_review)

        Requirements: 11.1
        """

        # Get ML prediction if available (non-blocking, backward compatible)
        ml_prediction = None
        if self.ml_enabled:
            try:
                ml_prediction = await self._get_ml_prediction(signal.symbol)
            except Exception as e:
                log.warning(f"ML prediction failed for {signal.symbol}: {e}")
                # Continue with rule-based logic (backward compatible)

        # ── STRONG SIGNALS — AUTO APPROVE ──────────────────────────────────
        if self._is_strong_signal(signal, market_context, ml_prediction):
            reason = f"Strong signal: score={signal.score:.1f}, conf={signal.confidence:.0%}, RR={signal.risk_reward:.2f}"
            if ml_prediction:
                reason += f", ML={ml_prediction.prediction:.2f}"

            return FastDecisionResult(
                decision=Decision.GO,
                confidence=0.95,
                reason=reason,
                needs_llm_review=False
            )

        # ── WEAK SIGNALS — AUTO REJECT ────────────────────────────────────
        if self._is_weak_signal(signal, market_context, ml_prediction):
            return FastDecisionResult(
                decision=Decision.NOGO,
                confidence=0.9,
                reason=self._get_rejection_reason(signal, market_context, ml_prediction),
                needs_llm_review=False
            )

        # ── EDGE CASES — NEEDS LLM REVIEW ─────────────────────────────────
        reason = f"Edge case: score={signal.score:.1f}, needs expert review"
        if ml_prediction:
            reason += f", ML={ml_prediction.prediction:.2f}"

        return FastDecisionResult(
            decision=Decision.NEEDS_REVIEW,
            confidence=0.0,
            reason=reason,
            needs_llm_review=True
        )

    async def _get_ml_prediction(self, symbol: str):
        """
        Get ML prediction for symbol (non-blocking, backward compatible).

        Requirements: 11.1

        Returns:
            Prediction object or None if not available
        """
        if not self.model_inference_service:
            return None

        try:
            # Get prediction from inference service
            # Features will be fetched from Redis by the service
            prediction = await self.model_inference_service.predict(symbol)
            return prediction
        except Exception as e:
            log.warning(f"Failed to get ML prediction for {symbol}: {e}")
            return None

    def _is_strong_signal(
        self,
        signal: TradingSignal,
        market_context: MarketContext,
        ml_prediction=None
    ) -> bool:
        """
        Check if signal meets all strong criteria.

        ML prediction can boost confidence if available.
        Requirements: 11.1
        """
        # Core metrics
        strong_metrics = (
            signal.score >= self.strong_signal_score and
            signal.confidence >= self.strong_confidence and
            signal.risk_reward >= self.strong_risk_reward
        )

        if not strong_metrics:
            # Check if ML prediction is very strong and can override
            if ml_prediction and self._ml_strongly_agrees(signal, ml_prediction):
                log.info(
                    f"ML prediction boosting signal for {signal.symbol}: "
                    f"ML={ml_prediction.prediction:.2f}, conf={ml_prediction.confidence:.2f}"
                )
                # ML strongly agrees, lower the bar slightly
                strong_metrics = (
                    signal.score >= self.strong_signal_score - 0.5 and
                    signal.confidence >= self.strong_confidence - 0.1 and
                    signal.risk_reward >= self.strong_risk_reward - 0.3
                )

                if not strong_metrics:
                    return False
            else:
                return False

        # Market context checks
        favorable_regime = market_context.regime in [
            MarketRegime.STRONG_TREND,
            MarketRegime.BREAKOUT
        ]

        low_correlation_risk = market_context.correlation_risk < 0.3

        not_blackout = not market_context.is_news_blackout

        favorable_risk_appetite = market_context.risk_appetite in [
            RiskAppetite.HIGH,
            RiskAppetite.MEDIUM
        ]

        # All conditions must be met
        return (
            favorable_regime and
            low_correlation_risk and
            not_blackout and
            favorable_risk_appetite
        )

    def _is_weak_signal(
        self,
        signal: TradingSignal,
        market_context: MarketContext,
        ml_prediction=None
    ) -> bool:
        """
        Check if signal should be auto-rejected.

        ML prediction can veto if it strongly disagrees.
        Requirements: 11.1
        """
        # Core metrics failures
        weak_metrics = (
            signal.score < self.weak_signal_score or
            signal.confidence < self.weak_confidence or
            signal.risk_reward < self.weak_risk_reward
        )

        if weak_metrics:
            return True

        # ML veto: if ML strongly disagrees with signal direction, reject
        if ml_prediction and self._ml_strongly_disagrees(signal, ml_prediction):
            log.info(
                f"ML prediction vetoing signal for {signal.symbol}: "
                f"ML={ml_prediction.prediction:.2f}, conf={ml_prediction.confidence:.2f}"
            )
            return True

        # Market context vetoes
        if market_context.is_news_blackout:
            return True

        if market_context.risk_appetite == RiskAppetite.RISK_OFF:
            return True

        if market_context.regime == MarketRegime.HIGH_VOLATILE:
            return True

        # Technical indicator failures
        adx = signal.metadata.get("adx", 0.0)
        if adx < settings.risk.min_adx:  # Configurable ADX threshold
            return True

        atr_ratio = signal.metadata.get("atr_ratio", 1.0)
        if atr_ratio > 2.5:  # Too volatile
            return True

        volume_ratio = signal.metadata.get("volume_ratio", 1.0)
        if volume_ratio < 0.8:  # Low volume
            return True

        return False

    def _ml_strongly_agrees(self, signal: TradingSignal, ml_prediction) -> bool:
        """
        Check if ML prediction strongly agrees with signal direction.

        Requirements: 11.1
        """
        if not ml_prediction or ml_prediction.confidence < self.ml_min_confidence:
            return False

        # For LONG signals, ML should predict UP (>0.65)
        # For SHORT signals, ML should predict DOWN (<0.35)
        if signal.direction == "LONG":
            return ml_prediction.prediction >= self.ml_strong_prediction
        elif signal.direction == "SHORT":
            return ml_prediction.prediction <= self.ml_weak_prediction

        return False

    def _ml_strongly_disagrees(self, signal: TradingSignal, ml_prediction) -> bool:
        """
        Check if ML prediction strongly disagrees with signal direction.

        Requirements: 11.1
        """
        if not ml_prediction or ml_prediction.confidence < self.ml_min_confidence:
            return False

        # For LONG signals, ML predicting strong DOWN is a veto
        # For SHORT signals, ML predicting strong UP is a veto
        if signal.direction == "LONG":
            return ml_prediction.prediction <= self.ml_weak_prediction
        elif signal.direction == "SHORT":
            return ml_prediction.prediction >= self.ml_strong_prediction

        return False

    def _get_rejection_reason(
        self,
        signal: TradingSignal,
        market_context: MarketContext,
        ml_prediction=None
    ) -> str:
        """Get specific rejection reason"""
        reasons = []

        if signal.score < self.weak_signal_score:
            reasons.append(f"score={signal.score:.1f}<{self.weak_signal_score}")

        if signal.confidence < self.weak_confidence:
            reasons.append(f"conf={signal.confidence:.0%}<{self.weak_confidence:.0%}")

        if signal.risk_reward < self.weak_risk_reward:
            reasons.append(f"RR={signal.risk_reward:.2f}<{self.weak_risk_reward}")

        if ml_prediction and self._ml_strongly_disagrees(signal, ml_prediction):
            reasons.append(f"ML_veto={ml_prediction.prediction:.2f}")

        if market_context.is_news_blackout:
            reasons.append("news_blackout")

        if market_context.risk_appetite == RiskAppetite.RISK_OFF:
            reasons.append("risk_off")

        adx = signal.metadata.get("adx", 0.0)
        if adx < settings.risk.min_adx:
            reasons.append(f"adx={adx:.1f}<{settings.risk.min_adx}")

        atr_ratio = signal.metadata.get("atr_ratio", 1.0)
        if atr_ratio > 2.5:
            reasons.append(f"atr_ratio={atr_ratio:.2f}>2.5")

        return "Weak signal: " + ", ".join(reasons) if reasons else "Weak signal"



def analyze_cross_asset_signals(
    signals: List[TradingSignal],
    market_state: MarketStateEngine,
    max_per_cluster: int = 2
) -> List[TradingSignal]:
    """
    Analyze signals in context of entire market.
    Limit positions per correlation cluster for diversification.
    """
    if not signals:
        return []
    
    # Group by correlation
    clusters = market_state.group_by_correlation(signals)
    
    log.info(f"[FAST_PATH] Grouped {len(signals)} signals into {len(clusters)} correlation clusters")
    
    # Select best signals from each cluster
    approved = []
    for cluster in clusters:
        # Sort by score within cluster
        cluster_signals = sorted(
            cluster.signals,
            key=lambda s: s.score,
            reverse=True
        )[:max_per_cluster]
        
        approved.extend(cluster_signals)
        
        log.debug(
            f"[FAST_PATH] Cluster {cluster.symbols[:3]}... "
            f"(corr={cluster.correlation:.2f}): "
            f"selected {len(cluster_signals)}/{len(cluster.signals)} signals"
        )
    
    return approved
