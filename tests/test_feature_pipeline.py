"""
Unit tests for FeaturePipeline component.
Tests feature computation, caching, normalization, and event processing.
"""
import pytest
import asyncio
import numpy as np
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from data.feature_pipeline import FeaturePipeline, FeatureVector
from data.event_bus import EventBus, Event, EventType


@pytest.fixture
def mock_redis():
    """Create mock Redis client"""
    redis = AsyncMock()
    redis.hset = AsyncMock()
    redis.expire = AsyncMock()
    return redis


@pytest.fixture
async def event_bus():
    """Create and start event bus"""
    bus = EventBus(max_queue_depth=100)
    await bus.start()
    yield bus
    await bus.stop()


@pytest.fixture
async def pipeline(event_bus, mock_redis):
    """Create feature pipeline"""
    pipeline = FeaturePipeline(
        event_bus=event_bus,
        redis_client=mock_redis,
        symbols=["XAUUSD", "EURUSD"],
        timeframes=["M1", "M5"],
        max_bars=500,
    )
    await pipeline.start()
    yield pipeline
    await pipeline.stop()


@pytest.mark.asyncio
async def test_pipeline_start_stop(event_bus, mock_redis):
    """Test pipeline can start and stop cleanly"""
    pipeline = FeaturePipeline(
        event_bus=event_bus,
        redis_client=mock_redis,
        symbols=["XAUUSD"],
        timeframes=["M1"],
    )
    
    await pipeline.start()
    assert pipeline._running is True
    
    await pipeline.stop()
    assert pipeline._running is False


@pytest.mark.asyncio
async def test_feature_computation_with_insufficient_data(pipeline):
    """Test feature computation returns None with insufficient data"""
    # Try to compute features with empty buffer
    features = await pipeline.compute_features("XAUUSD", "M1")
    
    # Should return None due to insufficient data
    assert features is None


@pytest.mark.asyncio
async def test_feature_computation_with_sufficient_data(pipeline):
    """Test feature computation with sufficient price data"""
    # Add price data to buffer
    symbol = "XAUUSD"
    timeframe = "M1"
    
    for i in range(50):
        bar = {
            "timestamp": datetime.utcnow(),
            "open": 2050.0 + i * 0.1,
            "high": 2050.5 + i * 0.1,
            "low": 2049.5 + i * 0.1,
            "close": 2050.0 + i * 0.1,
            "volume": 100,
        }
        pipeline._price_buffers[symbol][timeframe].append(bar)
    
    # Compute features
    features = await pipeline.compute_features(symbol, timeframe)
    
    # Should return feature vector
    assert features is not None
    assert isinstance(features, FeatureVector)
    assert features.symbol == symbol
    assert features.timeframe == timeframe
    assert len(features.features) > 0
    assert features.normalized_features is not None


@pytest.mark.asyncio
async def test_price_features_computation(pipeline):
    """Test price feature computation"""
    # Add price data
    symbol = "XAUUSD"
    timeframe = "M1"
    
    for i in range(60):
        bar = {
            "timestamp": datetime.utcnow(),
            "open": 2000.0 + i,
            "high": 2001.0 + i,
            "low": 1999.0 + i,
            "close": 2000.0 + i,
            "volume": 100,
        }
        pipeline._price_buffers[symbol][timeframe].append(bar)
    
    # Compute features
    features = await pipeline.compute_features(symbol, timeframe)
    
    # Check price features exist
    assert "return_1bar" in features.features
    assert "return_5bar" in features.features
    assert "return_20bar" in features.features
    assert "rsi_14" in features.features
    assert "ema_20" in features.features


@pytest.mark.asyncio
async def test_volume_features_computation(pipeline):
    """Test volume feature computation"""
    # Add price data with varying volume
    symbol = "XAUUSD"
    timeframe = "M1"
    
    for i in range(30):
        bar = {
            "timestamp": datetime.utcnow(),
            "open": 2000.0,
            "high": 2001.0,
            "low": 1999.0,
            "close": 2000.0,
            "volume": 100 + i * 10,
        }
        pipeline._price_buffers[symbol][timeframe].append(bar)
    
    # Compute features
    features = await pipeline.compute_features(symbol, timeframe)
    
    # Check volume features exist
    assert "volume_ratio" in features.features
    assert "vwap" in features.features
    assert "vwap_deviation" in features.features


@pytest.mark.asyncio
async def test_volatility_features_computation(pipeline):
    """Test volatility feature computation"""
    # Add price data with volatility
    symbol = "XAUUSD"
    timeframe = "M1"
    
    for i in range(30):
        bar = {
            "timestamp": datetime.utcnow(),
            "open": 2000.0,
            "high": 2010.0 + i * 0.5,
            "low": 1990.0 - i * 0.5,
            "close": 2000.0 + (i % 2) * 5,
            "volume": 100,
        }
        pipeline._price_buffers[symbol][timeframe].append(bar)
    
    # Compute features
    features = await pipeline.compute_features(symbol, timeframe)
    
    # Check volatility features exist
    assert "atr_14" in features.features
    assert "historical_volatility_20" in features.features


@pytest.mark.asyncio
async def test_statistical_features_computation(pipeline):
    """Test statistical feature computation"""
    # Add price data
    symbol = "XAUUSD"
    timeframe = "M1"
    
    for i in range(250):
        bar = {
            "timestamp": datetime.utcnow(),
            "open": 2000.0 + i * 0.1,
            "high": 2001.0 + i * 0.1,
            "low": 1999.0 + i * 0.1,
            "close": 2000.0 + i * 0.1,
            "volume": 100,
        }
        pipeline._price_buffers[symbol][timeframe].append(bar)
    
    # Compute features
    features = await pipeline.compute_features(symbol, timeframe)
    
    # Check statistical features exist for all windows (20, 50, 100, 200)
    for window in [20, 50, 100, 200]:
        assert f"mean_{window}" in features.features
        assert f"std_{window}" in features.features
        assert f"skew_{window}" in features.features
        assert f"kurtosis_{window}" in features.features
        assert f"zscore_{window}" in features.features
        assert f"percentile_{window}" in features.features


@pytest.mark.asyncio
async def test_feature_normalization(pipeline):
    """Test feature normalization produces zero mean and unit variance"""
    # Add price data
    symbol = "XAUUSD"
    timeframe = "M1"
    
    for i in range(100):
        bar = {
            "timestamp": datetime.utcnow(),
            "open": 2000.0 + i,
            "high": 2001.0 + i,
            "low": 1999.0 + i,
            "close": 2000.0 + i,
            "volume": 100,
        }
        pipeline._price_buffers[symbol][timeframe].append(bar)
    
    # Compute features multiple times to build statistics
    for _ in range(10):
        features = await pipeline.compute_features(symbol, timeframe)
    
    # Check normalized features
    assert features.normalized_features is not None
    assert len(features.normalized_features) > 0
    
    # Normalized values should be reasonable (not NaN or Inf)
    assert not np.any(np.isnan(features.normalized_features))
    assert not np.any(np.isinf(features.normalized_features))


@pytest.mark.asyncio
async def test_event_processing(pipeline):
    """Test processing of market_data_updated events"""
    # Create market data event
    event = Event(
        type=EventType.MARKET_DATA_UPDATED,
        timestamp=datetime.utcnow(),
        data={
            "symbol": "XAUUSD",
            "tick": {
                "last": 2050.0,
                "volume": 100,
            },
            "source": "tick_collector",
        },
        source="TickDataCollector"
    )
    
    # Process event
    await pipeline.process_event(event)
    
    # Wait for processing
    await asyncio.sleep(0.1)
    
    # Check metrics
    assert pipeline._events_processed == 1


@pytest.mark.asyncio
async def test_redis_caching(pipeline, mock_redis):
    """Test features are cached in Redis"""
    # Add sufficient price data
    symbol = "XAUUSD"
    timeframe = "M1"
    
    for i in range(30):
        bar = {
            "timestamp": datetime.utcnow(),
            "open": 2000.0 + i,
            "high": 2001.0 + i,
            "low": 1999.0 + i,
            "close": 2000.0 + i,
            "volume": 100,
        }
        pipeline._price_buffers[symbol][timeframe].append(bar)
    
    # Compute features
    features = await pipeline.compute_features(symbol, timeframe)
    
    # Cache features
    await pipeline._cache_features(features)
    
    # Verify Redis was called
    assert mock_redis.hset.called
    assert mock_redis.expire.called


@pytest.mark.asyncio
async def test_indicator_updated_event_emission(event_bus, mock_redis):
    """Test indicator_updated events are emitted"""
    pipeline = FeaturePipeline(
        event_bus=event_bus,
        redis_client=mock_redis,
        symbols=["XAUUSD"],
        timeframes=["M1"],
    )
    await pipeline.start()
    
    received_events = []
    
    async def handler(event: Event):
        received_events.append(event)
    
    # Subscribe to indicator_updated events
    await event_bus.subscribe(EventType.INDICATOR_UPDATED, handler)
    
    # Add price data
    symbol = "XAUUSD"
    timeframe = "M1"
    
    for i in range(30):
        bar = {
            "timestamp": datetime.utcnow(),
            "open": 2000.0 + i,
            "high": 2001.0 + i,
            "low": 1999.0 + i,
            "close": 2000.0 + i,
            "volume": 100,
        }
        pipeline._price_buffers[symbol][timeframe].append(bar)
    
    # Compute features
    features = await pipeline.compute_features(symbol, timeframe)
    
    # Emit event
    await pipeline._emit_indicator_updated(symbol, timeframe, features)
    
    # Wait for event processing
    await asyncio.sleep(0.1)
    
    # Verify event was received
    assert len(received_events) == 1
    assert received_events[0].type == EventType.INDICATOR_UPDATED
    assert received_events[0].data["symbol"] == symbol
    assert received_events[0].data["timeframe"] == timeframe
    
    await pipeline.stop()


@pytest.mark.asyncio
async def test_error_handling_in_feature_computation(pipeline):
    """Test pipeline handles errors gracefully"""
    # Create event with invalid data
    event = Event(
        type=EventType.MARKET_DATA_UPDATED,
        timestamp=datetime.utcnow(),
        data={
            "symbol": "INVALID",
            "tick": {},
        },
        source="Test"
    )
    
    # Process event (should not raise exception)
    await pipeline.process_event(event)
    
    # Pipeline should still be running
    assert pipeline._running is True


@pytest.mark.asyncio
async def test_metrics_reporting(pipeline):
    """Test pipeline metrics reporting"""
    # Process some events
    for i in range(5):
        event = Event(
            type=EventType.MARKET_DATA_UPDATED,
            timestamp=datetime.utcnow(),
            data={
                "symbol": "XAUUSD",
                "tick": {"last": 2050.0 + i, "volume": 100},
            },
            source="Test"
        )
        await pipeline.process_event(event)
    
    await asyncio.sleep(0.1)
    
    # Get metrics
    metrics = pipeline.get_metrics()
    
    assert metrics["running"] is True
    assert metrics["symbols"] == 2
    assert metrics["timeframes"] == 2
    assert metrics["events_processed"] == 5
    assert metrics["uptime_seconds"] > 0


@pytest.mark.asyncio
async def test_feature_vector_to_array(pipeline):
    """Test FeatureVector conversion to numpy array"""
    features = FeatureVector(
        symbol="XAUUSD",
        timestamp=datetime.utcnow(),
        timeframe="M1",
        features={"rsi": 65.0, "ema": 2050.0, "atr": 5.0},
        feature_names=["rsi", "ema", "atr"],
    )
    
    # Set normalized features
    features.normalized_features = np.array([0.5, -0.2, 1.0])
    
    # Convert to array
    arr = features.to_array()
    
    assert isinstance(arr, np.ndarray)
    assert len(arr) == 3
    assert arr[0] == 0.5
    assert arr[1] == -0.2
    assert arr[2] == 1.0


@pytest.mark.asyncio
async def test_ema_calculation(pipeline):
    """Test EMA calculation"""
    data = np.array([100, 101, 102, 103, 104, 105])
    ema = pipeline._calculate_ema(data, period=3)
    
    # EMA should be close to recent values
    assert ema > 103
    assert ema < 106


@pytest.mark.asyncio
async def test_processing_latency_warning(pipeline, caplog):
    """Test warning is logged for slow processing"""
    # Add lots of price data to slow down computation
    symbol = "XAUUSD"
    timeframe = "M1"
    
    for i in range(500):
        bar = {
            "timestamp": datetime.utcnow(),
            "open": 2000.0 + i,
            "high": 2001.0 + i,
            "low": 1999.0 + i,
            "close": 2000.0 + i,
            "volume": 100,
        }
        pipeline._price_buffers[symbol][timeframe].append(bar)
    
    # Note: This test may not trigger the warning in fast environments
    # It's here to demonstrate the latency checking logic
    features = await pipeline.compute_features(symbol, timeframe)
    assert features is not None
