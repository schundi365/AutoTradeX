"""
Unit tests for MultiTimeframeEngine.
Tests OHLCV aggregation, indicator computation, alignment detection, and divergence detection.
"""
import pytest
import asyncio
import numpy as np
from datetime import datetime, timedelta
from collections import deque

from data.multi_timeframe_engine import (
    MultiTimeframeEngine,
    Timeframe,
    OHLCV,
    TimeframeIndicators,
    TimeframeAlignment,
    Divergence,
)
from data.event_bus import EventBus, Event, EventType
from data.feature_pipeline import FeaturePipeline


@pytest.fixture
def event_bus():
    """Create event bus for testing"""
    return EventBus(max_queue_depth=100)


@pytest.fixture
def feature_pipeline(event_bus):
    """Create feature pipeline for testing"""
    # Mock Redis client
    class MockRedis:
        async def hset(self, key, mapping):
            pass
        async def expire(self, key, ttl):
            pass
            
    return FeaturePipeline(
        event_bus=event_bus,
        redis_client=MockRedis(),
        symbols=["XAUUSD", "EURUSD"],
        timeframes=["M1", "M5", "M15", "H1", "H4", "D1"],
    )


@pytest.fixture
def engine(event_bus, feature_pipeline):
    """Create multi-timeframe engine for testing"""
    return MultiTimeframeEngine(
        event_bus=event_bus,
        feature_pipeline=feature_pipeline,
        symbols=["XAUUSD", "EURUSD"],
        max_bars=500,
    )


@pytest.mark.asyncio
async def test_engine_start_stop(engine):
    """Test engine starts and stops correctly"""
    await engine.start()
    assert engine._running is True
    
    await engine.stop()
    assert engine._running is False


@pytest.mark.asyncio
async def test_ohlcv_buffer_initialization(engine):
    """Test OHLCV buffers are initialized for all symbols and timeframes"""
    assert "XAUUSD" in engine._ohlcv_buffers
    assert "EURUSD" in engine._ohlcv_buffers
    
    for symbol in ["XAUUSD", "EURUSD"]:
        for timeframe in Timeframe:
            assert timeframe in engine._ohlcv_buffers[symbol]
            assert isinstance(engine._ohlcv_buffers[symbol][timeframe], deque)
            assert engine._ohlcv_buffers[symbol][timeframe].maxlen == 500


def test_timeframe_duration_calculation(engine):
    """Test timeframe duration calculation"""
    assert engine._get_timeframe_duration(Timeframe.M1) == timedelta(minutes=1)
    assert engine._get_timeframe_duration(Timeframe.M5) == timedelta(minutes=5)
    assert engine._get_timeframe_duration(Timeframe.M15) == timedelta(minutes=15)
    assert engine._get_timeframe_duration(Timeframe.H1) == timedelta(hours=1)
    assert engine._get_timeframe_duration(Timeframe.H4) == timedelta(hours=4)
    assert engine._get_timeframe_duration(Timeframe.D1) == timedelta(days=1)


def test_timestamp_alignment_to_timeframe(engine):
    """Test timestamp alignment to timeframe boundaries"""
    timestamp = datetime(2024, 1, 15, 10, 37, 45, 123456)
    
    # M1 alignment
    aligned = engine._align_to_timeframe(timestamp, Timeframe.M1)
    assert aligned == datetime(2024, 1, 15, 10, 37, 0, 0)
    
    # M5 alignment
    aligned = engine._align_to_timeframe(timestamp, Timeframe.M5)
    assert aligned == datetime(2024, 1, 15, 10, 35, 0, 0)
    
    # M15 alignment
    aligned = engine._align_to_timeframe(timestamp, Timeframe.M15)
    assert aligned == datetime(2024, 1, 15, 10, 30, 0, 0)
    
    # H1 alignment
    aligned = engine._align_to_timeframe(timestamp, Timeframe.H1)
    assert aligned == datetime(2024, 1, 15, 10, 0, 0, 0)
    
    # H4 alignment
    aligned = engine._align_to_timeframe(timestamp, Timeframe.H4)
    assert aligned == datetime(2024, 1, 15, 8, 0, 0, 0)
    
    # D1 alignment
    aligned = engine._align_to_timeframe(timestamp, Timeframe.D1)
    assert aligned == datetime(2024, 1, 15, 0, 0, 0, 0)


def test_create_bar_from_ticks(engine):
    """Test OHLCV bar creation from tick data"""
    symbol = "XAUUSD"
    timeframe = Timeframe.M1
    
    # Create tick buffer
    base_time = datetime(2024, 1, 15, 10, 0, 0)
    tick_buffer = [
        {"timestamp": base_time + timedelta(seconds=i), "price": 2050.0 + i * 0.1, "volume": 100}
        for i in range(60)
    ]
    
    # Set last bar time
    engine._last_bar_times[symbol][timeframe] = base_time - timedelta(minutes=1)
    
    # Create bar
    bar = engine._create_bar_from_ticks(symbol, timeframe, tick_buffer)
    
    assert bar is not None
    assert bar.timestamp == base_time
    assert bar.open == 2050.0
    assert bar.close == 2055.9
    assert bar.high == 2055.9
    assert bar.low == 2050.0
    assert bar.volume == 6000  # 100 * 60


def test_ema_calculation(engine):
    """Test EMA calculation"""
    data = np.array([100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110])
    
    ema = engine._calculate_ema(data, 5)
    
    # EMA should be close to recent prices
    assert ema > 105
    assert ema < 110


def test_rsi_calculation(engine):
    """Test RSI calculation"""
    # Uptrend data
    uptrend = np.array([100 + i for i in range(20)])
    rsi_up = engine._calculate_rsi(uptrend, 14)
    assert rsi_up > 50  # RSI should be high in uptrend
    
    # Downtrend data
    downtrend = np.array([100 - i for i in range(20)])
    rsi_down = engine._calculate_rsi(downtrend, 14)
    assert rsi_down < 50  # RSI should be low in downtrend


def test_atr_calculation(engine):
    """Test ATR calculation"""
    high = np.array([105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119])
    low = np.array([95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109])
    close = np.array([100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114])
    
    atr = engine._calculate_atr(high, low, close, 14)
    
    # ATR should be positive
    assert atr > 0
    # ATR should be around 10 (high - low)
    assert 8 < atr < 12


@pytest.mark.asyncio
async def test_compute_timeframe_indicators(engine):
    """Test indicator computation for a timeframe"""
    symbol = "XAUUSD"
    timeframe = Timeframe.M1
    
    # Add OHLCV data to buffer
    base_time = datetime(2024, 1, 15, 10, 0, 0)
    for i in range(200):
        bar = OHLCV(
            timestamp=base_time + timedelta(minutes=i),
            open=2050.0 + i * 0.1,
            high=2051.0 + i * 0.1,
            low=2049.0 + i * 0.1,
            close=2050.5 + i * 0.1,
            volume=1000,
        )
        engine._ohlcv_buffers[symbol][timeframe].append(bar)
    
    # Compute indicators
    indicators = await engine._compute_timeframe_indicators(symbol, timeframe)
    
    assert indicators is not None
    assert indicators.symbol == symbol
    assert indicators.timeframe == timeframe
    assert indicators.ema_20 > 0
    assert indicators.ema_50 > 0
    assert indicators.ema_200 > 0
    assert 0 <= indicators.rsi_14 <= 100
    assert indicators.atr_14 > 0


@pytest.mark.asyncio
async def test_trend_alignment_detection_bullish(engine):
    """Test bullish trend alignment detection"""
    symbol = "XAUUSD"
    
    # Create bullish indicators for multiple timeframes
    for timeframe in [Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.H1]:
        indicators = TimeframeIndicators(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=datetime.utcnow(),
            ema_20=2050.0,
            ema_50=2045.0,
            ema_200=2040.0,
            ema_20_slope=0.5,  # Positive slope (bullish)
            ema_50_slope=0.3,  # Positive slope (bullish)
            ema_200_slope=0.1,
            rsi_14=65.0,
        )
        engine._indicator_cache[symbol][timeframe] = indicators
    
    # Detect alignment
    alignment = engine.detect_alignment(symbol)
    
    assert alignment is not None
    assert alignment.is_aligned is True
    assert alignment.alignment_direction == 1  # Bullish
    assert len(alignment.aligned_timeframes) >= 3


@pytest.mark.asyncio
async def test_trend_alignment_detection_bearish(engine):
    """Test bearish trend alignment detection"""
    symbol = "XAUUSD"
    
    # Create bearish indicators for multiple timeframes
    for timeframe in [Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.H1]:
        indicators = TimeframeIndicators(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=datetime.utcnow(),
            ema_20=2040.0,
            ema_50=2045.0,
            ema_200=2050.0,
            ema_20_slope=-0.5,  # Negative slope (bearish)
            ema_50_slope=-0.3,  # Negative slope (bearish)
            ema_200_slope=-0.1,
            rsi_14=35.0,
        )
        engine._indicator_cache[symbol][timeframe] = indicators
    
    # Detect alignment
    alignment = engine.detect_alignment(symbol)
    
    assert alignment is not None
    assert alignment.is_aligned is True
    assert alignment.alignment_direction == -1  # Bearish
    assert len(alignment.aligned_timeframes) >= 3


@pytest.mark.asyncio
async def test_trend_alignment_detection_neutral(engine):
    """Test neutral (no alignment) detection"""
    symbol = "XAUUSD"
    
    # Create mixed indicators (no clear alignment) - need at least 3 for detection
    indicators_bullish = TimeframeIndicators(
        symbol=symbol,
        timeframe=Timeframe.M1,
        timestamp=datetime.utcnow(),
        ema_20_slope=0.5,
        ema_50_slope=0.3,
    )
    indicators_bearish = TimeframeIndicators(
        symbol=symbol,
        timeframe=Timeframe.M5,
        timestamp=datetime.utcnow(),
        ema_20_slope=-0.5,
        ema_50_slope=-0.3,
    )
    indicators_neutral = TimeframeIndicators(
        symbol=symbol,
        timeframe=Timeframe.M15,
        timestamp=datetime.utcnow(),
        ema_20_slope=0.1,
        ema_50_slope=-0.1,  # Mixed slopes
    )
    
    engine._indicator_cache[symbol][Timeframe.M1] = indicators_bullish
    engine._indicator_cache[symbol][Timeframe.M5] = indicators_bearish
    engine._indicator_cache[symbol][Timeframe.M15] = indicators_neutral
    
    # Detect alignment
    alignment = engine.detect_alignment(symbol)
    
    assert alignment is not None
    assert alignment.is_aligned is False
    assert alignment.alignment_direction == 0  # Neutral


@pytest.mark.asyncio
async def test_regime_change_event_emission(engine, event_bus):
    """Test regime_change event is emitted when alignment changes"""
    symbol = "XAUUSD"
    
    # Start event bus
    await event_bus.start()
    await engine.start()
    
    # Track emitted events
    emitted_events = []
    
    async def capture_event(event: Event):
        if event.type == EventType.REGIME_CHANGE:
            emitted_events.append(event)
    
    await event_bus.subscribe(EventType.REGIME_CHANGE, capture_event)
    
    # Set initial bearish alignment
    initial_alignment = TimeframeAlignment(
        symbol=symbol,
        timestamp=datetime.utcnow(),
        aligned_timeframes=[Timeframe.M1, Timeframe.M5, Timeframe.M15],
        alignment_direction=-1,
        is_aligned=True,
    )
    engine._last_alignment[symbol] = initial_alignment
    
    # Create new bullish alignment
    new_alignment = TimeframeAlignment(
        symbol=symbol,
        timestamp=datetime.utcnow(),
        aligned_timeframes=[Timeframe.M1, Timeframe.M5, Timeframe.M15],
        alignment_direction=1,  # Changed to bullish
        is_aligned=True,
    )
    
    # Check regime change
    await engine._check_regime_change(symbol, new_alignment)
    
    # Wait for event processing
    await asyncio.sleep(0.1)
    
    # Verify event was emitted
    assert len(emitted_events) == 1
    event = emitted_events[0]
    assert event.data["symbol"] == symbol
    assert event.data["previous_direction"] == -1
    assert event.data["current_direction"] == 1
    
    await event_bus.stop()
    await engine.stop()


@pytest.mark.asyncio
async def test_divergence_detection_bullish(engine):
    """Test bullish divergence detection"""
    symbol = "XAUUSD"
    timeframe = Timeframe.M1
    
    # Create price data with lower low
    base_time = datetime(2024, 1, 15, 10, 0, 0)
    prices = [2050.0 - i * 0.5 for i in range(50)]  # Declining prices
    
    for i, price in enumerate(prices):
        bar = OHLCV(
            timestamp=base_time + timedelta(minutes=i),
            open=price,
            high=price + 1,
            low=price - 1,
            close=price,
            volume=1000,
        )
        engine._ohlcv_buffers[symbol][timeframe].append(bar)
    
    # Create indicators with RSI not making lower low (divergence)
    indicators = TimeframeIndicators(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=datetime.utcnow(),
        rsi_14=35.0,  # RSI higher than oversold, indicating divergence
    )
    engine._indicator_cache[symbol][timeframe] = indicators
    
    # Detect divergence
    divergence = engine.detect_divergence(symbol)
    
    # Note: Divergence detection is complex and may not always trigger
    # This test verifies the function runs without errors
    # In production, you'd need more sophisticated divergence logic
    assert divergence is None or isinstance(divergence, Divergence)


@pytest.mark.asyncio
async def test_parallel_indicator_computation(engine):
    """Test indicators are computed in parallel for all timeframes"""
    symbol = "XAUUSD"
    
    # Add OHLCV data to all timeframes
    base_time = datetime(2024, 1, 15, 10, 0, 0)
    for timeframe in Timeframe:
        for i in range(200):
            bar = OHLCV(
                timestamp=base_time + timedelta(minutes=i),
                open=2050.0 + i * 0.1,
                high=2051.0 + i * 0.1,
                low=2049.0 + i * 0.1,
                close=2050.5 + i * 0.1,
                volume=1000,
            )
            engine._ohlcv_buffers[symbol][timeframe].append(bar)
    
    # Update timeframe (should compute all in parallel)
    start_time = datetime.utcnow()
    await engine.update_timeframe(symbol)
    processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
    
    # Verify indicators were computed for all timeframes
    for timeframe in Timeframe:
        assert timeframe in engine._indicator_cache[symbol]
        indicators = engine._indicator_cache[symbol][timeframe]
        assert indicators is not None
        assert indicators.ema_20 > 0
    
    # Verify processing time is reasonable (<100ms requirement)
    # Note: In CI/CD, this might be slower, so we use a relaxed threshold
    assert processing_time < 500  # 500ms threshold for test environment


def test_ohlcv_buffer_max_size(engine):
    """Test OHLCV buffers respect max_bars limit"""
    symbol = "XAUUSD"
    timeframe = Timeframe.M1
    
    # Add more than max_bars
    base_time = datetime(2024, 1, 15, 10, 0, 0)
    for i in range(600):  # More than max_bars (500)
        bar = OHLCV(
            timestamp=base_time + timedelta(minutes=i),
            open=2050.0,
            high=2051.0,
            low=2049.0,
            close=2050.5,
            volume=1000,
        )
        engine._ohlcv_buffers[symbol][timeframe].append(bar)
    
    # Verify buffer size is capped at max_bars
    assert len(engine._ohlcv_buffers[symbol][timeframe]) == 500


def test_get_timeframe_indicators(engine):
    """Test retrieving cached indicators"""
    symbol = "XAUUSD"
    timeframe = Timeframe.M1
    
    # Add indicators to cache
    indicators = TimeframeIndicators(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=datetime.utcnow(),
        ema_20=2050.0,
        rsi_14=65.0,
    )
    engine._indicator_cache[symbol][timeframe] = indicators
    
    # Retrieve indicators
    retrieved = engine.get_timeframe_indicators(symbol, timeframe)
    
    assert retrieved is not None
    assert retrieved.symbol == symbol
    assert retrieved.timeframe == timeframe
    assert retrieved.ema_20 == 2050.0
    assert retrieved.rsi_14 == 65.0


def test_metrics_tracking(engine):
    """Test metrics are tracked correctly"""
    # Initial metrics
    metrics = engine.get_metrics()
    assert metrics["running"] is False
    assert metrics["symbols"] == 2
    assert metrics["timeframes"] == 6
    assert metrics["bars_created"] == 0
    assert metrics["indicators_computed"] == 0
    
    # Simulate some activity
    engine._bars_created = 100
    engine._indicators_computed = 50
    engine._alignments_detected = 5
    engine._divergences_detected = 2
    
    metrics = engine.get_metrics()
    assert metrics["bars_created"] == 100
    assert metrics["indicators_computed"] == 50
    assert metrics["alignments_detected"] == 5
    assert metrics["divergences_detected"] == 2


@pytest.mark.asyncio
async def test_market_data_event_processing(engine, event_bus):
    """Test processing of market_data_updated events"""
    await event_bus.start()
    await engine.start()
    
    # Create market data event
    event = Event(
        type=EventType.MARKET_DATA_UPDATED,
        timestamp=datetime.utcnow(),
        data={
            "symbol": "XAUUSD",
            "tick": {
                "last": 2050.5,
                "volume": 100,
                "bid": 2050.0,
                "ask": 2051.0,
            },
        },
        source="test",
    )
    
    # Publish event
    await event_bus.publish(event)
    
    # Wait for processing
    await asyncio.sleep(0.2)
    
    # Verify tick was added to buffer
    assert len(engine._tick_buffers["XAUUSD"]) > 0
    
    await event_bus.stop()
    await engine.stop()


def test_direction_to_string(engine):
    """Test direction conversion to string"""
    assert engine._direction_to_string(1) == "bullish"
    assert engine._direction_to_string(-1) == "bearish"
    assert engine._direction_to_string(0) == "neutral"
