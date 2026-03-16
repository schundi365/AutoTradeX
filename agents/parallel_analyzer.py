"""
APEX Bot — Parallel Symbol Analysis
Analyze all symbols concurrently instead of sequentially.
"""
from __future__ import annotations
import asyncio
from typing import List
from datetime import datetime

from loguru import logger as log

from core.models import TradingSignal, BotState
from core.config import settings
from core.data_lake import MarketDataLake


async def analyze_all_symbols_parallel(
    symbols: List[str],
    data_lake: MarketDataLake,
    state: BotState
) -> List[TradingSignal]:
    """
    Analyze all symbols in parallel instead of sequentially.
    """
    log.info(f"[PARALLEL] Analyzing {len(symbols)} symbols concurrently...")
    
    start_time = datetime.utcnow()
    
    # Create tasks for all symbols
    tasks = [
        analyze_symbol(symbol, data_lake, state)
        for symbol in symbols
    ]
    
    # Execute in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Filter successful results
    signals = []
    errors = 0
    
    for symbol, result in zip(symbols, results):
        if isinstance(result, Exception):
            log.warning(f"[PARALLEL] Error analyzing {symbol}: {result}")
            errors += 1
        elif isinstance(result, TradingSignal):
            signals.append(result)
        elif isinstance(result, list):
            signals.extend(result)
    
    elapsed = (datetime.utcnow() - start_time).total_seconds()
    
    log.info(
        f"[PARALLEL] Completed {len(symbols)} symbols in {elapsed:.2f}s "
        f"({elapsed/len(symbols)*1000:.0f}ms per symbol) | "
        f"Signals: {len(signals)}, Errors: {errors}"
    )
    
    return signals


async def analyze_symbol(
    symbol: str,
    data_lake: MarketDataLake,
    state: BotState
) -> TradingSignal | List[TradingSignal] | None:
    """
    Analyze a single symbol using pre-computed indicators.
    """
    try:
        # Get all data for symbol from data lake (single call)
        symbol_data = await data_lake.get_symbol_data(symbol)
        
        if not symbol_data or not symbol_data.ohlcv:
            log.debug(f"[PARALLEL] No data for {symbol}")
            return None
        
        # Get pre-computed indicators
        indicators = symbol_data.indicators
        
        if not indicators:
            log.debug(f"[PARALLEL] No indicators for {symbol}")
            return None
        
        # Use existing technical analysis strategy
        from strategies.technical import TechnicalAnalyser
        
        analyser = TechnicalAnalyser()
        
        # Generate signals using pre-computed indicators
        signals = await analyser.analyse_from_indicators(
            symbol=symbol,
            ohlcv=symbol_data.ohlcv,
            indicators=indicators,
            quote=symbol_data.quote,
            market_regime=state.market_regime
        )
        
        return signals
        
    except Exception as e:
        log.error(f"[PARALLEL] Error analyzing {symbol}: {e}")
        return None


async def batch_indicator_computation(
    symbols: List[str],
    data_lake: MarketDataLake
) -> dict:
    """
    Pre-compute indicators for all symbols in parallel.
    """
    log.info(f"[PARALLEL] Pre-computing indicators for {len(symbols)} symbols...")
    
    start_time = datetime.utcnow()
    
    # Data lake handles parallel computation internally
    # Just trigger the update
    await data_lake._compute_all_indicators()
    
    elapsed = (datetime.utcnow() - start_time).total_seconds()
    
    log.info(
        f"[PARALLEL] Indicator computation completed in {elapsed:.2f}s "
        f"({elapsed/len(symbols)*1000:.0f}ms per symbol)"
    )
    
    return data_lake.indicators_cache
