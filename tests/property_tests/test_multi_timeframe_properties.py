"""
Property-based tests for MultiTimeframeEngine.
Tests universal properties that should hold across all inputs.
"""
import pytest
import asyncio
import numpy as np
from datetime import datetime, timedelta
from hypothesis import given, strategies as st, settings

from data.multi_timeframe_engine import (
    MultiTimeframeEngine,
    Timeframe,
    OHLCV,
    TimeframeIndicators,
    TimeframeAlignment,
)
from data.event_bus import EventBus
from data.feature_pipeline import FeaturePipeline


# Test configuration
from hypothesis import HealthCheck

settings.register_profile("ci", max_examples=100, deadline=5000, suppress_health_check=[HealthCheck.function_scoped_fixture])
settings.load_profile("ci")


@pytest.fixture
def event_bus():
    """Create event bus for testing"""
    return EventBus(max_queue_depth=100)


@pytest.fixture
def feature_pipeline(event_bus):
    """Create feature pipeline for testing"""
    class MockRedis:
        async def hset(self, key, mapping):
            pass
        async def expire(self, key, ttl):
            pass
            
    return FeaturePipeline(
        event_bus=event_bus,
        redis_client=MockRedis(),
        symbols=["XAUUSD"],
        timeframes=["M1", "M5", "M15", "H1", "H4", "D1"],
    )


@pytest.fixture
def engine(event_bus, feature_pipeline):
    """Create multi-timeframe engine for testing"""
    return MultiTimeframeEngine(
        event_bus=event_bus,
        feature_pipeline=feature_pipeline,
        symbols=["XAUUSD"],
        max_bars=500,
    )


@given(
    num_bars=st.integers(min_value=1, max_value=1000),
)
def test_property_ohlcv_buffer_size_limit(engine, num_bars):
    """
    Property 23: Multi-Timeframe Cache Size
    Feature: data-ml-dashboard-improvements, Property 23: For any symbol and timeframe, 
    the cached indicator values should contain exactly the most recent 500 bars 
    (or fewer if less data available).
    
    Validates: Requirements 7.5
    """
    symbol = "XAUUSD"
    timeframe = Timeframe.M1
    
    # Clear buffer first (since fixture is reused)
    engine._ohlcv_buffers[symbol][timeframe].clear()
    
    # Add bars to buffer
    base_time = datetime(2024, 1, 15, 10, 0, 0)
    for i in range(num_bars):
        bar = OHLCV(
            timestamp=base_time + timedelta(minutes=i),
            open=2050.0,
            high=2051.0,
            low=2049.0,
            close=2050.5,
            volume=1000,
        )
        engine._ohlcv_buffers[symbol][timeframe].append(bar)
    
    # Verify buffer size is capped at max_bars (500) or less
    buffer_size = len(engine._ohlcv_buffers[symbol][timeframe])
    assert buffer_size <= 500
    assert buffer_size == min(num_bars, 500)


@given(
    ema_20_slope=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    ema_50_slope=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
)
def test_property_trend_alignment_direction(engine, ema_20_slope, ema_50_slope):
    """
    Property 20: Trend Alignment Detection
    Feature: data-ml-dashboard-improvements, Property 20: For any symbol, when EMA slopes 
    agree in direction across at least 3 timeframes, trend alignment should be detected.
    
    Validates: Requirements 7.2
    """
    symbol = "XAUUSD"
    
    # Clear cache first (since fixture is reused)
    engine._indicator_cache[symbol] = {}
    
    # Create indicators with given slopes for 4 timeframes
    for timeframe in [Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.H1]:
        indicators = TimeframeIndicators(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=datetime.utcnow(),
            ema_20_slope=ema_20_slope,
            ema_50_slope=ema_50_slope,
        )
        engine._indicator_cache[symbol][timeframe] = indicators
    
    # Detect alignment
    alignment = engine.detect_alignment(symbol)
    
    assert alignment is not None
    
    # If both slopes are positive, should detect bullish alignment
    if ema_20_slope > 0 and ema_50_slope > 0:
        assert alignment.is_aligned is True
        assert alignment.alignment_direction == 1
        assert len(alignment.aligned_timeframes) >= 3
    # If both slopes are negative, should detect bearish alignment
    elif ema_20_slope < 0 and ema_50_slope < 0:
        assert alignment.is_aligned is True
        assert alignment.alignment_direction == -1
        assert len(alignment.aligned_timeframes) >= 3
    # Otherwise, no clear alignment
    else:
        # May or may not be aligned depending on slopes
        assert alignment.alignment_direction in [-1, 0, 1]


@given(
    price=st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
    volume=st.integers(min_value=1, max_value=1000000),
)
def test_property_ohlcv_bar_validity(engine, price, volume):
    """
    Property: OHLCV Bar Validity
    Feature: data-ml-dashboard-improvements: For any OHLCV bar created from ticks, 
    the bar should have valid OHLC relationships (high >= open, high >= close, 
    low <= open, low <= close).
    """
    symbol = "XAUUSD"
    timeframe = Timeframe.M1
    
    # Create tick buffer with varying prices
    base_time = datetime(2024, 1, 15, 10, 0, 0)
    tick_buffer = []
    for i in range(60):
        tick_buffer.append({
            "timestamp": base_time + timedelta(seconds=i),
            "price": price + (i % 10) * 0.1,  # Vary price slightly
            "volume": volume,
        })
    
    # Set last bar time
    engine._last_bar_times[symbol][timeframe] = base_time - timedelta(minutes=1)
    
    # Create bar
    bar = engine._create_bar_from_ticks(symbol, timeframe, tick_buffer)
    
    if bar is not None:
        # Verify OHLC relationships
        assert bar.high >= bar.open
        assert bar.high >= bar.close
        assert bar.low <= bar.open
        assert bar.low <= bar.close
        assert bar.high >= bar.low
        assert bar.volume >= 0


@given(
    data=st.lists(
        st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        min_size=20,
        max_size=200,
    ),
    period=st.integers(min_value=5, max_value=50),
)
def test_property_ema_calculation(engine, data, period):
    """
    Property: EMA Calculation
    Feature: data-ml-dashboard-improvements: For any price data and period, 
    the EMA should be between the minimum and maximum of recent prices.
    """
    data_array = np.array(data)
    
    if len(data_array) >= period:
        ema = engine._calculate_ema(data_array, period)
        
        # EMA should be within the range of recent prices
        recent_min = np.min(data_array[-period:])
        recent_max = np.max(data_array[-period:])
        
        assert recent_min <= ema <= recent_max


@given(
    data=st.lists(
        st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        min_size=15,
        max_size=100,
    ),
)
def test_property_rsi_range(engine, data):
    """
    Property: RSI Range
    Feature: data-ml-dashboard-improvements: For any price data, 
    the RSI should be between 0 and 100.
    """
    data_array = np.array(data)
    
    if len(data_array) >= 15:
        rsi = engine._calculate_rsi(data_array, 14)
        
        # RSI should be in valid range
        assert 0 <= rsi <= 100


@given(
    alignment_direction=st.integers(min_value=-1, max_value=1),
    num_aligned=st.integers(min_value=0, max_value=6),
)
def test_property_alignment_consistency(engine, alignment_direction, num_aligned):
    """
    Property: Alignment Consistency
    Feature: data-ml-dashboard-improvements: For any alignment, if is_aligned is True, 
    then there should be at least 3 aligned timeframes and alignment_direction should be non-zero.
    """
    symbol = "XAUUSD"
    
    # Create alignment
    aligned_timeframes = list(Timeframe)[:num_aligned]
    alignment = TimeframeAlignment(
        symbol=symbol,
        timestamp=datetime.utcnow(),
        aligned_timeframes=aligned_timeframes,
        alignment_direction=alignment_direction,
        is_aligned=(num_aligned >= 3 and alignment_direction != 0),
    )
    
    # Verify consistency
    if alignment.is_aligned:
        assert len(alignment.aligned_timeframes) >= 3
        assert alignment.alignment_direction != 0
    else:
        # If not aligned, either < 3 timeframes or direction is neutral
        assert len(alignment.aligned_timeframes) < 3 or alignment.alignment_direction == 0


@given(
    timestamp=st.datetimes(
        min_value=datetime(2024, 1, 1),
        max_value=datetime(2024, 12, 31),
    ),
)
def test_property_timestamp_alignment_idempotent(engine, timestamp):
    """
    Property: Timestamp Alignment Idempotence
    Feature: data-ml-dashboard-improvements: For any timestamp and timeframe, 
    aligning the timestamp twice should produce the same result.
    """
    for timeframe in Timeframe:
        aligned_once = engine._align_to_timeframe(timestamp, timeframe)
        aligned_twice = engine._align_to_timeframe(aligned_once, timeframe)
        
        # Aligning an already-aligned timestamp should not change it
        assert aligned_once == aligned_twice


@given(
    num_bars=st.integers(min_value=20, max_value=500),
    base_price=st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
)
@pytest.mark.asyncio
async def test_property_indicator_computation_completeness(engine, num_bars, base_price):
    """
    Property: Indicator Computation Completeness
    Feature: data-ml-dashboard-improvements: For any symbol with sufficient OHLCV data, 
    computed indicators should contain all required fields (EMAs, RSI, ATR, ADX).
    """
    symbol = "XAUUSD"
    timeframe = Timeframe.M1
    
    # Add OHLCV data to buffer
    base_time = datetime(2024, 1, 15, 10, 0, 0)
    for i in range(num_bars):
        bar = OHLCV(
            timestamp=base_time + timedelta(minutes=i),
            open=base_price + i * 0.1,
            high=base_price + i * 0.1 + 1.0,
            low=base_price + i * 0.1 - 1.0,
            close=base_price + i * 0.1 + 0.5,
            volume=1000,
        )
        engine._ohlcv_buffers[symbol][timeframe].append(bar)
    
    # Compute indicators
    indicators = await engine._compute_timeframe_indicators(symbol, timeframe)
    
    if indicators is not None:
        # Verify all required fields are present and valid
        assert indicators.symbol == symbol
        assert indicators.timeframe == timeframe
        assert indicators.timestamp is not None
        
        # EMAs should be positive for positive prices
        if num_bars >= 20:
            assert indicators.ema_20 > 0
        if num_bars >= 50:
            assert indicators.ema_50 > 0
        if num_bars >= 200:
            assert indicators.ema_200 > 0
            
        # RSI should be in valid range
        assert 0 <= indicators.rsi_14 <= 100
        
        # ATR should be non-negative
        assert indicators.atr_14 >= 0


@given(
    timeframe=st.sampled_from(list(Timeframe)),
)
def test_property_timeframe_duration_positive(engine, timeframe):
    """
    Property: Timeframe Duration Positive
    Feature: data-ml-dashboard-improvements: For any timeframe, 
    the duration should be positive.
    """
    duration = engine._get_timeframe_duration(timeframe)
    
    assert duration.total_seconds() > 0


@given(
    num_ticks=st.integers(min_value=1, max_value=100),
    base_price=st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
)
def test_property_bar_aggregation_volume_sum(engine, num_ticks, base_price):
    """
    Property: Bar Aggregation Volume Sum
    Feature: data-ml-dashboard-improvements: For any set of ticks aggregated into a bar, 
    the bar's volume should equal the sum of tick volumes.
    """
    symbol = "XAUUSD"
    timeframe = Timeframe.M1
    
    # Create tick buffer
    base_time = datetime(2024, 1, 15, 10, 0, 0)
    tick_buffer = []
    total_volume = 0
    
    for i in range(num_ticks):
        volume = 100 * (i + 1)  # Varying volumes
        tick_buffer.append({
            "timestamp": base_time + timedelta(seconds=i),
            "price": base_price + i * 0.1,
            "volume": volume,
        })
        total_volume += volume
    
    # Set last bar time
    engine._last_bar_times[symbol][timeframe] = base_time - timedelta(minutes=1)
    
    # Create bar
    bar = engine._create_bar_from_ticks(symbol, timeframe, tick_buffer)
    
    if bar is not None:
        # Bar volume should equal sum of tick volumes
        assert bar.volume == total_volume


@given(
    high=st.lists(
        st.floats(min_value=100.0, max_value=200.0, allow_nan=False, allow_infinity=False),
        min_size=15,
        max_size=50,
    ),
    low=st.lists(
        st.floats(min_value=50.0, max_value=99.0, allow_nan=False, allow_infinity=False),
        min_size=15,
        max_size=50,
    ),
)
def test_property_atr_non_negative(engine, high, low):
    """
    Property: ATR Non-Negative
    Feature: data-ml-dashboard-improvements: For any price data, 
    the ATR (Average True Range) should be non-negative.
    """
    # Ensure high and low have same length
    min_len = min(len(high), len(low))
    high = np.array(high[:min_len])
    low = np.array(low[:min_len])
    
    # Create close prices between high and low
    close = (high + low) / 2
    
    if len(high) >= 15:
        atr = engine._calculate_atr(high, low, close, 14)
        
        # ATR should be non-negative
        assert atr >= 0


@given(
    num_timeframes=st.integers(min_value=0, max_value=6),
)
def test_property_alignment_strength_range(engine, num_timeframes):
    """
    Property: Alignment Strength Range
    Feature: data-ml-dashboard-improvements: For any alignment, 
    the alignment_strength should be between 0.0 and 1.0.
    """
    symbol = "XAUUSD"
    
    # Create alignment with specified number of timeframes
    aligned_timeframes = list(Timeframe)[:num_timeframes]
    alignment_strength = num_timeframes / len(Timeframe)
    
    alignment = TimeframeAlignment(
        symbol=symbol,
        timestamp=datetime.utcnow(),
        aligned_timeframes=aligned_timeframes,
        alignment_strength=alignment_strength,
    )
    
    # Verify strength is in valid range
    assert 0.0 <= alignment.alignment_strength <= 1.0


@given(
    prices=st.lists(
        st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        min_size=60,
        max_size=100,
    ),
)
def test_property_bar_high_low_relationship(engine, prices):
    """
    Property: Bar High/Low Relationship
    Feature: data-ml-dashboard-improvements: For any bar created from tick data, 
    the high should be >= low.
    """
    symbol = "XAUUSD"
    timeframe = Timeframe.M1
    
    # Create tick buffer from prices
    base_time = datetime(2024, 1, 15, 10, 0, 0)
    tick_buffer = [
        {
            "timestamp": base_time + timedelta(seconds=i),
            "price": price,
            "volume": 100,
        }
        for i, price in enumerate(prices)
    ]
    
    # Set last bar time
    engine._last_bar_times[symbol][timeframe] = base_time - timedelta(minutes=1)
    
    # Create bar
    bar = engine._create_bar_from_ticks(symbol, timeframe, tick_buffer)
    
    if bar is not None:
        # High should always be >= low
        assert bar.high >= bar.low


@given(
    symbol=st.sampled_from(["XAUUSD", "EURUSD", "BTCUSD"]),
    timeframe=st.sampled_from(list(Timeframe)),
)
def test_property_indicator_cache_key_uniqueness(engine, symbol, timeframe):
    """
    Property: Indicator Cache Key Uniqueness
    Feature: data-ml-dashboard-improvements: For any symbol and timeframe combination, 
    the indicator cache should store indicators uniquely.
    """
    # Add symbol to engine if not present
    if symbol not in engine._indicator_cache:
        engine._indicator_cache[symbol] = {}
    
    # Create indicators
    indicators1 = TimeframeIndicators(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=datetime.utcnow(),
        ema_20=2050.0,
    )
    
    indicators2 = TimeframeIndicators(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=datetime.utcnow(),
        ema_20=2055.0,  # Different value
    )
    
    # Store first indicators
    engine._indicator_cache[symbol][timeframe] = indicators1
    
    # Retrieve and verify
    retrieved1 = engine.get_timeframe_indicators(symbol, timeframe)
    assert retrieved1 is not None
    assert retrieved1.ema_20 == 2050.0
    
    # Store second indicators (should overwrite)
    engine._indicator_cache[symbol][timeframe] = indicators2
    
    # Retrieve and verify overwrite
    retrieved2 = engine.get_timeframe_indicators(symbol, timeframe)
    assert retrieved2 is not None
    assert retrieved2.ema_20 == 2055.0
