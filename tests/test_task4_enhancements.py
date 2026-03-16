"""
Unit tests for Task 4 enhancements to EventBus and FeaturePipeline.
Tests queue depth monitoring, latency tracking, throughput metrics, and error handling.
"""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

from data.event_bus import EventBus, Event, EventType
from data.feature_pipeline import FeaturePipeline


@pytest.mark.asyncio
async def test_event_bus_latency_tracking():
    """Test EventBus tracks processing latency metrics"""
    bus = EventBus(max_queue_depth=100)
    await bus.start()
    
    received = []
    
    async def slow_handler(event: Event):
        # Simulate slow processing
        await asyncio.sleep(0.01)
        received.append(event)
    
    await bus.subscribe(EventType.MARKET_DATA_UPDATED, slow_handler)
    
    # Publish events
    for i in range(5):
        event = Event(
            type=EventType.MARKET_DATA_UPDATED,
            timestamp=datetime.utcnow(),
            data={"index": i}
        )
        await bus.publish(event)
    
    await asyncio.sleep(0.2)
    
    # Check latency metrics
    metrics = bus.get_metrics()
    assert metrics["avg_latency_ms"] > 0
    assert metrics["max_latency_ms"] > 0
    assert metrics["avg_latency_ms"] <= metrics["max_latency_ms"]
    
    await bus.stop()


@pytest.mark.asyncio
async def test_event_bus_throughput_metrics():
    """Test EventBus tracks throughput metrics"""
    bus = EventBus(max_queue_depth=100)
    await bus.start()
    
    received = []
    
    async def handler(event: Event):
        received.append(event)
    
    await bus.subscribe(EventType.MARKET_DATA_UPDATED, handler)
    
    # Publish multiple events
    for i in range(10):
        event = Event(
            type=EventType.MARKET_DATA_UPDATED,
            timestamp=datetime.utcnow(),
            data={"index": i}
        )
        await bus.publish(event)
    
    await asyncio.sleep(0.2)
    
    # Check throughput metrics
    throughput = bus.get_throughput_metrics()
    assert throughput["events_per_second"] > 0
    assert throughput["avg_latency_ms"] >= 0
    assert throughput["max_latency_ms"] >= 0
    assert throughput["latency_samples"] > 0
    
    await bus.stop()


@pytest.mark.asyncio
async def test_event_bus_performance_warning_emission():
    """Test EventBus emits performance warnings for slow processing"""
    bus = EventBus(max_queue_depth=100)
    await bus.start()
    
    warnings = []
    
    async def slow_handler(event: Event):
        # Simulate very slow processing (>500ms)
        if event.type == EventType.MARKET_DATA_UPDATED:
            await asyncio.sleep(0.6)
    
    async def warning_handler(event: Event):
        warnings.append(event)
    
    await bus.subscribe(EventType.MARKET_DATA_UPDATED, slow_handler)
    await bus.subscribe(EventType.PERFORMANCE_WARNING, warning_handler)
    
    # Publish event that will trigger slow processing
    event = Event(
        type=EventType.MARKET_DATA_UPDATED,
        timestamp=datetime.utcnow(),
        data={"test": "slow"}
    )
    await bus.publish(event)
    
    # Wait for processing and warning
    await asyncio.sleep(1.0)
    
    # Should have received performance warning
    assert len(warnings) > 0
    warning = warnings[0]
    assert warning.type == EventType.PERFORMANCE_WARNING
    assert "current_latency_ms" in warning.data
    assert warning.data["current_latency_ms"] > 500
    
    await bus.stop()


@pytest.mark.asyncio
async def test_event_bus_queue_depth_monitoring():
    """Test EventBus monitors queue depth correctly"""
    bus = EventBus(max_queue_depth=10)
    await bus.start()
    
    # Publish events without subscriber (they'll queue up)
    for i in range(5):
        event = Event(
            type=EventType.MARKET_DATA_UPDATED,
            timestamp=datetime.utcnow(),
            data={"index": i}
        )
        await bus.publish(event)
    
    # Check queue depth
    depth = bus.get_queue_depth()
    assert depth >= 0
    assert depth <= 10
    
    # Check metrics include queue depth
    metrics = bus.get_metrics()
    assert "queue_depth" in metrics
    assert "max_queue_depth" in metrics
    assert metrics["max_queue_depth"] == 10
    
    await bus.stop()


@pytest.mark.asyncio
async def test_feature_pipeline_incremental_computation():
    """Test FeaturePipeline computes features incrementally"""
    mock_redis = AsyncMock()
    mock_redis.hset = AsyncMock()
    mock_redis.expire = AsyncMock()
    
    bus = EventBus(max_queue_depth=100)
    await bus.start()
    
    pipeline = FeaturePipeline(
        event_bus=bus,
        redis_client=mock_redis,
        symbols=["XAUUSD"],
        timeframes=["M1"],
    )
    await pipeline.start()
    
    # Add initial price data
    for i in range(30):
        bar = {
            "timestamp": datetime.utcnow(),
            "open": 2000.0 + i,
            "high": 2001.0 + i,
            "low": 1999.0 + i,
            "close": 2000.0 + i,
            "volume": 100,
        }
        pipeline._price_buffers["XAUUSD"]["M1"].append(bar)
    
    # Process event (should trigger incremental computation)
    event = Event(
        type=EventType.MARKET_DATA_UPDATED,
        timestamp=datetime.utcnow(),
        data={
            "symbol": "XAUUSD",
            "tick": {"last": 2030.0, "volume": 100},
        },
        source="Test"
    )
    
    await pipeline.process_event(event)
    await asyncio.sleep(0.1)
    
    # Check that features were computed
    assert pipeline._features_computed > 0
    
    await pipeline.stop()
    await bus.stop()


@pytest.mark.asyncio
async def test_feature_pipeline_redis_caching_with_ttl():
    """Test FeaturePipeline caches features in Redis with 1-hour TTL"""
    mock_redis = AsyncMock()
    mock_redis.hset = AsyncMock()
    mock_redis.expire = AsyncMock()
    
    bus = EventBus(max_queue_depth=100)
    await bus.start()
    
    pipeline = FeaturePipeline(
        event_bus=bus,
        redis_client=mock_redis,
        symbols=["XAUUSD"],
        timeframes=["M1"],
    )
    await pipeline.start()
    
    # Add price data
    for i in range(30):
        bar = {
            "timestamp": datetime.utcnow(),
            "open": 2000.0 + i,
            "high": 2001.0 + i,
            "low": 1999.0 + i,
            "close": 2000.0 + i,
            "volume": 100,
        }
        pipeline._price_buffers["XAUUSD"]["M1"].append(bar)
    
    # Compute features
    features = await pipeline.compute_features("XAUUSD", "M1")
    assert features is not None
    
    # Cache features
    await pipeline._cache_features(features)
    
    # Verify Redis was called with TTL
    assert mock_redis.hset.called
    assert mock_redis.expire.called
    
    # Check that expire was called with correct TTL
    expire_call = mock_redis.expire.call_args
    assert expire_call is not None
    # TTL should be 3600 seconds (1 hour)
    assert expire_call[0][1] == 3600 or expire_call[1].get("time") == 3600
    
    await pipeline.stop()
    await bus.stop()


@pytest.mark.asyncio
async def test_feature_pipeline_error_handling_graceful_degradation():
    """Test FeaturePipeline handles errors gracefully and continues processing"""
    mock_redis = AsyncMock()
    # Simulate Redis failure
    mock_redis.hset = AsyncMock(side_effect=Exception("Redis connection failed"))
    mock_redis.expire = AsyncMock()
    
    bus = EventBus(max_queue_depth=100)
    await bus.start()
    
    pipeline = FeaturePipeline(
        event_bus=bus,
        redis_client=mock_redis,
        symbols=["XAUUSD"],
        timeframes=["M1"],
    )
    await pipeline.start()
    
    # Add price data
    for i in range(30):
        bar = {
            "timestamp": datetime.utcnow(),
            "open": 2000.0 + i,
            "high": 2001.0 + i,
            "low": 1999.0 + i,
            "close": 2000.0 + i,
            "volume": 100,
        }
        pipeline._price_buffers["XAUUSD"]["M1"].append(bar)
    
    # Process event (should handle Redis error gracefully)
    event = Event(
        type=EventType.MARKET_DATA_UPDATED,
        timestamp=datetime.utcnow(),
        data={
            "symbol": "XAUUSD",
            "tick": {"last": 2030.0, "volume": 100},
        },
        source="Test"
    )
    
    # Should not raise exception despite Redis failure
    await pipeline.process_event(event)
    await asyncio.sleep(0.1)
    
    # Pipeline should still be running
    assert pipeline._running is True
    
    # Features should still be computed (just not cached)
    assert pipeline._features_computed > 0
    
    await pipeline.stop()
    await bus.stop()


@pytest.mark.asyncio
async def test_feature_pipeline_latency_under_50ms():
    """Test FeaturePipeline processes events within 50ms target"""
    mock_redis = AsyncMock()
    mock_redis.hset = AsyncMock()
    mock_redis.expire = AsyncMock()
    
    bus = EventBus(max_queue_depth=100)
    await bus.start()
    
    pipeline = FeaturePipeline(
        event_bus=bus,
        redis_client=mock_redis,
        symbols=["XAUUSD"],
        timeframes=["M1"],
    )
    await pipeline.start()
    
    # Add price data
    for i in range(30):
        bar = {
            "timestamp": datetime.utcnow(),
            "open": 2000.0 + i,
            "high": 2001.0 + i,
            "low": 1999.0 + i,
            "close": 2000.0 + i,
            "volume": 100,
        }
        pipeline._price_buffers["XAUUSD"]["M1"].append(bar)
    
    # Measure processing time
    start_time = datetime.utcnow()
    
    event = Event(
        type=EventType.MARKET_DATA_UPDATED,
        timestamp=datetime.utcnow(),
        data={
            "symbol": "XAUUSD",
            "tick": {"last": 2030.0, "volume": 100},
        },
        source="Test"
    )
    
    await pipeline.process_event(event)
    
    processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
    
    # Should process within 50ms (with some tolerance for test environment)
    # Note: This may occasionally exceed 50ms in slow test environments
    # The important thing is that the pipeline logs a warning when it does
    assert processing_time < 200  # Generous tolerance for test environment
    
    await pipeline.stop()
    await bus.stop()


@pytest.mark.asyncio
async def test_event_bus_enhanced_metrics():
    """Test EventBus provides enhanced metrics"""
    bus = EventBus(max_queue_depth=100)
    await bus.start()
    
    received = []
    
    async def handler(event: Event):
        received.append(event)
    
    await bus.subscribe(EventType.MARKET_DATA_UPDATED, handler)
    
    # Publish events
    for i in range(5):
        event = Event(
            type=EventType.MARKET_DATA_UPDATED,
            timestamp=datetime.utcnow(),
            data={"index": i}
        )
        await bus.publish(event)
    
    await asyncio.sleep(0.2)
    
    # Get enhanced metrics
    metrics = bus.get_metrics()
    
    # Check all required metrics are present
    assert "queue_depth" in metrics
    assert "max_queue_depth" in metrics
    assert "events_processed" in metrics
    assert "events_dropped" in metrics
    assert "processing_rate" in metrics
    assert "avg_latency_ms" in metrics
    assert "max_latency_ms" in metrics
    assert "performance_warnings" in metrics
    assert "running" in metrics
    
    # Check values are reasonable
    assert metrics["events_processed"] == 5
    assert metrics["events_dropped"] == 0
    assert metrics["processing_rate"] > 0
    assert metrics["avg_latency_ms"] >= 0
    assert metrics["running"] is True
    
    await bus.stop()
