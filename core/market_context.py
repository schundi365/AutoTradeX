"""
APEX Bot — Market-Wide Context Engine
Real-time market state tracking for autonomous decision-making.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum

import numpy as np
from loguru import logger as log

from core.models import TradingSignal, Direction, AssetClass
from core.config import settings, CORRELATION_GROUPS


class MarketRegime(str, Enum):
    STRONG_TREND = "STRONG_TREND"
    WEAK_TREND = "WEAK_TREND"
    RANGING = "RANGING"
    HIGH_VOLATILE = "HIGH_VOLATILE"
    LOW_VOLATILE = "LOW_VOLATILE"
    BREAKOUT = "BREAKOUT"


class RiskAppetite(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    RISK_OFF = "RISK_OFF"


@dataclass
class SectorStrength:
    sector: str
    momentum: float
    strength: str  # STRONG, WEAK
    trend: str  # UP, DOWN, FLAT
    symbols: List[str]


@dataclass
class CorrelationCluster:
    symbols: List[str]
    avg_score: float
    correlation: float
    signals: List[TradingSignal]


@dataclass
class MarketContext:
    """Comprehensive market state snapshot"""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    regime: MarketRegime = MarketRegime.WEAK_TREND
    risk_appetite: RiskAppetite = RiskAppetite.MEDIUM
    sector_rotation: Dict[str, SectorStrength] = field(default_factory=dict)
    correlation_clusters: List[CorrelationCluster] = field(default_factory=list)
    liquidity_conditions: str = "NORMAL"
    is_news_blackout: bool = False
    correlation_risk: float = 0.0
    
    def summary(self) -> str:
        return (
            f"Regime={self.regime.value} | Risk={self.risk_appetite.value} | "
            f"Liquidity={self.liquidity_conditions} | Blackout={self.is_news_blackout}"
        )


class MarketStateEngine:
    """
    Maintains real-time view of entire market.
    Updates every 15 seconds.
    """
    
    def __init__(self):
        self.symbols: Dict[str, dict] = {}
        self.correlations: Dict[str, Dict[str, float]] = {}
        self.sector_strength: Dict[str, SectorStrength] = {}
        self.macro_indicators: Dict[str, float] = {}
        self.flow_data: Dict[str, dict] = {}
        self.last_update: Optional[datetime] = None
        
    async def update(self, quotes: dict, ohlcv_cache: dict, macro_data: dict):
        """Update market state with latest data"""
        self.symbols = quotes
        self.macro_indicators = macro_data
        self.last_update = datetime.utcnow()
        
        # Update sector strength
        await self._update_sector_strength(ohlcv_cache)
        
        # Update correlations
        await self._update_correlations(ohlcv_cache)
        
    async def _update_sector_strength(self, ohlcv_cache: dict):
        """Calculate momentum for each sector"""
        sectors = {
            "METALS": ["XAUUSD", "XAGUSD", "XPTUSD"],
            "CRYPTO": ["BTCUSD", "ETHUSD"],
            "FOREX_MAJOR": ["EURUSD", "GBPUSD", "USDJPY"],
            "COMMODITIES": ["USOIL", "NATGAS"],
        }
        
        for sector, symbols in sectors.items():
            momentums = []
            for symbol in symbols:
                if symbol in ohlcv_cache:
                    data = ohlcv_cache[symbol]
                    if len(data) >= 20:
                        # Simple momentum: (current - 20 bars ago) / 20 bars ago
                        momentum = (data[-1].get('close', 0) - data[-20].get('close', 1)) / data[-20].get('close', 1)
                        momentums.append(momentum)
            
            if momentums:
                avg_momentum = sum(momentums) / len(momentums)
                self.sector_strength[sector] = SectorStrength(
                    sector=sector,
                    momentum=avg_momentum,
                    strength="STRONG" if abs(avg_momentum) > 0.02 else "WEAK",
                    trend="UP" if avg_momentum > 0.005 else "DOWN" if avg_momentum < -0.005 else "FLAT",
                    symbols=symbols
                )
    
    async def _update_correlations(self, ohlcv_cache: dict):
        """Calculate correlation matrix between symbols"""
        symbols = list(ohlcv_cache.keys())
        if len(symbols) < 2:
            return
        
        # Build price change matrix
        price_changes = {}
        for symbol in symbols:
            data = ohlcv_cache.get(symbol, [])
            if len(data) >= 20:
                changes = [
                    (data[i].get('close', 0) - data[i-1].get('close', 1)) / data[i-1].get('close', 1)
                    for i in range(1, min(20, len(data)))
                ]
                price_changes[symbol] = changes
        
        # Calculate correlations
        for sym1 in price_changes:
            self.correlations[sym1] = {}
            for sym2 in price_changes:
                if sym1 != sym2 and len(price_changes[sym1]) == len(price_changes[sym2]):
                    corr = np.corrcoef(price_changes[sym1], price_changes[sym2])[0, 1]
                    self.correlations[sym1][sym2] = corr if not np.isnan(corr) else 0.0
    
    def get_market_context(self, is_news_blackout: bool = False) -> MarketContext:
        """Returns comprehensive market state"""
        # Classify regime based on macro and sector data
        regime = self._classify_regime()
        
        # Calculate risk appetite
        risk_appetite = self._calculate_risk_appetite()
        
        # Assess liquidity
        liquidity = self._assess_liquidity()
        
        # Calculate correlation risk
        corr_risk = self._calculate_correlation_risk()
        
        return MarketContext(
            regime=regime,
            risk_appetite=risk_appetite,
            sector_rotation=self.sector_strength,
            correlation_clusters=[],
            liquidity_conditions=liquidity,
            is_news_blackout=is_news_blackout,
            correlation_risk=corr_risk
        )
    
    def _classify_regime(self) -> MarketRegime:
        """Classify overall market regime"""
        # Use macro indicators
        dxy_trend = self.macro_indicators.get("dxy_trend", "FLAT")
        yield_trend = self.macro_indicators.get("yield_trend", "FLAT")
        
        # Count strong sectors
        strong_sectors = sum(
            1 for s in self.sector_strength.values() 
            if s.strength == "STRONG"
        )
        
        if strong_sectors >= 3:
            return MarketRegime.STRONG_TREND
        elif strong_sectors >= 2:
            return MarketRegime.WEAK_TREND
        else:
            return MarketRegime.RANGING
    
    def _calculate_risk_appetite(self) -> RiskAppetite:
        """Calculate market risk appetite"""
        macro_regime = self.macro_indicators.get("macro_regime", "NEUTRAL")
        
        if macro_regime == "SEVERE_RISK_OFF":
            return RiskAppetite.RISK_OFF
        elif macro_regime == "RISK_OFF":
            return RiskAppetite.LOW
        elif macro_regime == "RISK_ON":
            return RiskAppetite.HIGH
        else:
            return RiskAppetite.MEDIUM
    
    def _assess_liquidity(self) -> str:
        """Assess market liquidity conditions"""
        # Simple heuristic based on time of day
        hour = datetime.utcnow().hour
        
        # Low liquidity: Asian session (22:00-08:00 UTC)
        if hour >= 22 or hour < 8:
            return "LOW"
        # High liquidity: London/NY overlap (12:00-16:00 UTC)
        elif 12 <= hour < 16:
            return "HIGH"
        else:
            return "NORMAL"
    
    def _calculate_correlation_risk(self) -> float:
        """Calculate average correlation across portfolio"""
        if not self.correlations:
            return 0.0
        
        all_corrs = []
        for sym1_corrs in self.correlations.values():
            all_corrs.extend(abs(c) for c in sym1_corrs.values())
        
        return sum(all_corrs) / len(all_corrs) if all_corrs else 0.0
    
    def group_by_correlation(self, signals: List[TradingSignal]) -> List[CorrelationCluster]:
        """Group signals by correlation"""
        if not signals:
            return []
        
        clusters = []
        used_symbols = set()
        
        for signal in signals:
            if signal.symbol in used_symbols:
                continue
            
            # Find correlated symbols
            cluster_signals = [signal]
            cluster_symbols = [signal.symbol]
            
            for other_signal in signals:
                if other_signal.symbol in used_symbols or other_signal.symbol == signal.symbol:
                    continue
                
                # Check correlation
                corr = self.correlations.get(signal.symbol, {}).get(other_signal.symbol, 0.0)
                if abs(corr) > 0.7:  # High correlation threshold
                    cluster_signals.append(other_signal)
                    cluster_symbols.append(other_signal.symbol)
            
            # Mark as used
            used_symbols.update(cluster_symbols)
            
            # Calculate cluster metrics
            avg_score = sum(s.score for s in cluster_signals) / len(cluster_signals)
            avg_corr = sum(
                abs(self.correlations.get(s1, {}).get(s2, 0.0))
                for s1 in cluster_symbols
                for s2 in cluster_symbols
                if s1 != s2
            ) / max(len(cluster_symbols) * (len(cluster_symbols) - 1), 1)
            
            clusters.append(CorrelationCluster(
                symbols=cluster_symbols,
                avg_score=avg_score,
                correlation=avg_corr,
                signals=cluster_signals
            ))
        
        return sorted(clusters, key=lambda c: c.avg_score, reverse=True)
