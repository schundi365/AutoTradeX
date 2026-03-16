"""
APEX Bot — Market Data Lake
Centralized access to all market data with pre-computed indicators.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field

import pandas as pd
import pandas_ta as ta
from loguru import logger as log

from core.models import Quote, OHLCV
from core.config import settings


@dataclass
class SymbolData:
    """Complete data package for a symbol"""
    symbol: str
    ohlcv: List[dict]
    indicators: Dict[str, float]
    quote: Optional[Quote]
    news: List[dict] = field(default_factory=list)
    events: List[dict] = field(default_factory=list)
    correlations: Dict[str, float] = field(default_factory=dict)
    last_update: datetime = field(default_factory=datetime.utcnow)


class MarketDataLake:
    """
    Centralized access to all market data.
    Pre-computed indicators, cached results.
    """
    
    def __init__(self):
        self.ohlcv_cache: Dict[str, List[dict]] = {}
        self.indicators_cache: Dict[str, Dict[str, float]] = {}
        self.quotes_cache: Dict[str, Quote] = {}
        self.news_cache: List[dict] = []
        self.calendar_cache: List[dict] = []
        self.correlation_matrix: Dict[str, Dict[str, float]] = {}
        self.last_update: Optional[datetime] = None
        self._update_lock = asyncio.Lock()
    
    async def update_all(self, quotes: dict, ohlcv_data: dict, news: list, calendar: list):
        """Update all cached data"""
        async with self._update_lock:
            self.quotes_cache = quotes
            self.ohlcv_cache = ohlcv_data
            self.news_cache = news
            self.calendar_cache = calendar
            self.last_update = datetime.utcnow()
            
            # Pre-compute indicators for all symbols
            await self._compute_all_indicators()
    
    async def _compute_all_indicators(self):
        """Compute indicators for all symbols in parallel"""
        tasks = [
            self._compute_indicators(symbol, data)
            for symbol, data in self.ohlcv_cache.items()
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for symbol, result in zip(self.ohlcv_cache.keys(), results):
            if isinstance(result, dict):
                self.indicators_cache[symbol] = result
            else:
                log.warning(f"Failed to compute indicators for {symbol}: {result}")
    
    async def _compute_indicators(self, symbol: str, ohlcv_data: List[dict]) -> Dict[str, float]:
        """Compute all indicators for one symbol"""
        if not ohlcv_data or len(ohlcv_data) < 50:
            return {}
        
        try:
            # Convert to DataFrame
            df = pd.DataFrame(ohlcv_data)
            
            # Ensure required columns
            if not all(col in df.columns for col in ['open', 'high', 'low', 'close', 'volume']):
                return {}
            
            # Compute indicators
            indicators = {}
            
            # RSI
            rsi = ta.rsi(df['close'], length=14)
            indicators['rsi'] = float(rsi.iloc[-1]) if not rsi.empty else 50.0
            
            # ADX
            adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
            if adx_df is not None and not adx_df.empty:
                indicators['adx'] = float(adx_df['ADX_14'].iloc[-1]) if 'ADX_14' in adx_df.columns else 20.0
            else:
                indicators['adx'] = 20.0
            
            # ATR
            atr = ta.atr(df['high'], df['low'], df['close'], length=14)
            if not atr.empty:
                indicators['atr'] = float(atr.iloc[-1])
                indicators['atr_pct'] = (indicators['atr'] / df['close'].iloc[-1]) * 100
                
                # ATR ratio (current vs 50-period average)
                if len(atr) >= 50:
                    atr_avg = atr.iloc[-50:].mean()
                    indicators['atr_ratio'] = indicators['atr'] / atr_avg if atr_avg > 0 else 1.0
                else:
                    indicators['atr_ratio'] = 1.0
            else:
                indicators['atr'] = 0.0
                indicators['atr_pct'] = 0.0
                indicators['atr_ratio'] = 1.0
            
            # EMAs
            ema_20 = ta.ema(df['close'], length=20)
            ema_50 = ta.ema(df['close'], length=50)
            if not ema_20.empty:
                indicators['ema_20'] = float(ema_20.iloc[-1])
            if not ema_50.empty:
                indicators['ema_50'] = float(ema_50.iloc[-1])
            
            # MACD
            macd_df = ta.macd(df['close'])
            if macd_df is not None and not macd_df.empty:
                if 'MACD_12_26_9' in macd_df.columns:
                    indicators['macd'] = float(macd_df['MACD_12_26_9'].iloc[-1])
                if 'MACDs_12_26_9' in macd_df.columns:
                    indicators['macd_signal'] = float(macd_df['MACDs_12_26_9'].iloc[-1])
            
            # Bollinger Bands
            bb_df = ta.bbands(df['close'], length=20)
            if bb_df is not None and not bb_df.empty:
                if 'BBU_20_2.0' in bb_df.columns and 'BBL_20_2.0' in bb_df.columns:
                    bb_upper = bb_df['BBU_20_2.0'].iloc[-1]
                    bb_lower = bb_df['BBL_20_2.0'].iloc[-1]
                    bb_mid = (bb_upper + bb_lower) / 2
                    indicators['bb_width'] = ((bb_upper - bb_lower) / bb_mid) * 100 if bb_mid > 0 else 0.0
            
            # Volume ratio
            if 'volume' in df.columns and len(df) >= 20:
                current_vol = df['volume'].iloc[-1]
                avg_vol = df['volume'].iloc[-20:].mean()
                indicators['volume_ratio'] = current_vol / avg_vol if avg_vol > 0 else 1.0
            else:
                indicators['volume_ratio'] = 1.0
            
            # Momentum
            if len(df) >= 10:
                momentum = (df['close'].iloc[-1] - df['close'].iloc[-10]) / df['close'].iloc[-10]
                indicators['momentum'] = momentum
            else:
                indicators['momentum'] = 0.0
            
            return indicators
            
        except Exception as e:
            log.error(f"Error computing indicators for {symbol}: {e}")
            return {}
    
    async def get_symbol_data(self, symbol: str, timeframe: str = "M15") -> Optional[SymbolData]:
        """Get all data for a symbol in one call"""
        if symbol not in self.ohlcv_cache:
            return None
        
        return SymbolData(
            symbol=symbol,
            ohlcv=self.ohlcv_cache.get(symbol, []),
            indicators=self.indicators_cache.get(symbol, {}),
            quote=self.quotes_cache.get(symbol),
            news=[n for n in self.news_cache if symbol in n.get('symbols', [])],
            events=[e for e in self.calendar_cache if symbol in e.get('affected', [])],
            correlations=self.correlation_matrix.get(symbol, {}),
        )
    
    async def get_market_snapshot(self) -> dict:
        """Get entire market state in one call"""
        return {
            "all_symbols": self.ohlcv_cache,
            "all_indicators": self.indicators_cache,
            "all_quotes": self.quotes_cache,
            "market_news": self.news_cache,
            "upcoming_events": self.calendar_cache,
            "correlations": self.correlation_matrix,
            "last_update": self.last_update,
        }
    
    def get_cached_indicators(self, symbol: str) -> Dict[str, float]:
        """Get pre-computed indicators for a symbol"""
        return self.indicators_cache.get(symbol, {})
    
    def is_stale(self, max_age_seconds: int = 30) -> bool:
        """Check if data is stale"""
        if not self.last_update:
            return True
        
        age = (datetime.utcnow() - self.last_update).total_seconds()
        return age > max_age_seconds
