"""
Unit tests for EventBus component.
Tests event publishing, subscription, queue management, and metrics.
"""
import pytest
import asyncio
from datetime import datetime
from data.event_bus import EventBus, Event, EventType


@pytest.mark.asyncio
async def test_event_bus_start_stop():
    """Test EventBus can start and stop cleanly"""
    bus = EventBus(max_queue_depth=100)
    
    await bus.start()
    assert bus._running is True
    
    await bus.stop()
    assert bus._running is False


@pytest.mark.asyncio
async def test_event_publishing():
    """Test event publishing to subscribers"""
    bus = EventBus(max_queue_depth=100)
    await bus.start()
    
    received_events = []
    
    async def handler(event: Event):
        received_events.append(event)
    
    # Subscribe handler
    await bus.subscribe(EventType.MARKET_DATA_UPDATED, handler)
    
    # Publish event
    event = Event(
        type=EventType.MARKET_DATA_UPDATED,
        timestamp=datetime.utcnow(),
        data={"symbol": "XAUUSD", "price": 2050.0}
    )
    await bus.publish(event)
    
    # Wait for processing
    await asyncio.sleep(0.1)
    
    # Verify event was received
    assert len(received_events) == 1
    assert received_events[0].type == EventType.MARKET_DATA_UPDATED
    assert received_events[0].data["symbol"] == "XAUUSD"
    
    await bus.stop()


@pytest.mark.asyncio
async def test_multiple_subscribers():
    """Test multiple subscribers receive the same event"""
    bus = EventBus(max_queue_depth=100)
    await bus.start()
    
    received_1 = []
    received_2 = []
    
    async def handler1(event: Event):
        received_1.append(event)
    
    async def handler2(event: Event):
        received_2.append(event)
    
    # Subscribe both handlers
    await bus.subscribe(EventType.MARKET_DATA_UPDATED, handler1)
    await bus.subscribe(EventType.MARKET_DATA_UPDATED, handler2)
    
    # Publish event
    event = Event(
        type=EventType.MARKET_DATA_UPDATED,
        timestamp=datetime.utcnow(),
        data={"symbol": "EURUSD"}
    )
    await bus.publish(event)
    
    # Wait for processing
    await asyncio.sleep(0.1)
    
    # Both handlers should receive the event
    assert len(received_1) == 1
    assert len(received_2) == 1
    assert received_1[0].data["symbol"] == "EURUSD"
    assert received_2[0].data["symbol"] == "EURUSD"
    
    await bus.stop()


@pytest.mark.asyncio
async def test_queue_depth_limit():
    """Test queue drops events when full"""
    bus = EventBus(max_queue_depth=5)
    await bus.start()
    
    # Publish more events than queue can hold
    for i in range(10):
        event = Event(
            type=EventType.MARKET_DATA_UPDATED,
            timestamp=datetime.utcnow(),
            data={"index": i}
        )
        await bus.publish(event)
    
    # Wait a bit
    await asyncio.sleep(0.1)
    
    # Some events should be dropped
    assert bus._events_dropped > 0
    
    await bus.stop()


@pytest.mark.asyncio
async def test_unsubscribe():
    """Test unsubscribing from events"""
    bus = EventBus(max_queue_depth=100)
    await bus.start()
    
    received = []
    
    async def handler(event: Event):
        received.append(event)
    
    # Subscribe
    await bus.subscribe(EventType.MARKET_DATA_UPDATED, handler)
    
    # Publish first event
    event1 = Event(
        type=EventType.MARKET_DATA_UPDATED,
        timestamp=datetime.utcnow(),
        data={"index": 1}
    )
    await bus.publish(event1)
    await asyncio.sleep(0.1)
    
    # Unsubscribe
    bus.unsubscribe(EventType.MARKET_DATA_UPDATED, handler)
    
    # Publish second event
    event2 = Event(
        type=EventType.MARKET_DATA_UPDATED,
        timestamp=datetime.utcnow(),
        data={"index": 2}
    )
    await bus.publish(event2)
    await asyncio.sleep(0.1)
    
    # Should only receive first event
    assert len(received) == 1
    assert received[0].data["index"] == 1
    
    await bus.stop()


@pytest.mark.asyncio
async def test_error_handling_in_handler():
    """Test that errors in one handler don't affect others"""
    bus = EventBus(max_queue_depth=100)
    await bus.start()
    
    received_good = []
    
    async def bad_handler(event: Event):
        raise ValueError("Handler error")
    
    async def good_handler(event: Event):
        received_good.append(event)
    
    # Subscribe both handlers
    await bus.subscribe(EventType.MARKET_DATA_UPDATED, bad_handler)
    await bus.subscribe(EventType.MARKET_DATA_UPDATED, good_handler)
    
    # Publish event
    event = Event(
        type=EventType.MARKET_DATA_UPDATED,
        timestamp=datetime.utcnow(),
        data={"test": "data"}
    )
    await bus.publish(event)
    
    # Wait for processing
    await asyncio.sleep(0.1)
    
    # Good handler should still receive event
    assert len(received_good) == 1
    
    await bus.stop()


@pytest.mark.asyncio
async def test_get_metrics():
    """Test metrics reporting"""
    bus = EventBus(max_queue_depth=100)
    await bus.start()
    
    received = []
    
    async def handler(event: Event):
        received.append(event)
    
    await bus.subscribe(EventType.MARKET_DATA_UPDATED, handler)
    
    # Publish some events
    for i in range(5):
        event = Event(
            type=EventType.MARKET_DATA_UPDATED,
            timestamp=datetime.utcnow(),
            data={"index": i}
        )
        await bus.publish(event)
    
    await asyncio.sleep(0.2)
    
    # Get metrics
    metrics = bus.get_metrics()
    
    assert metrics["running"] is True
    assert metrics["events_processed"] == 5
    assert metrics["events_dropped"] == 0
    assert metrics["processing_rate"] > 0
    
    await bus.stop()


@pytest.mark.asyncio
async def test_queue_depth():
    """Test queue depth reporting"""
    bus = EventBus(max_queue_depth=100)
    await bus.start()
    
    # Publish events without subscriber (they'll queue up briefly)
    for i in range(10):
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
    
    await bus.stop()


@pytest.mark.asyncio
async def test_event_type_filtering():
    """Test that handlers only receive events of subscribed type"""
    bus = EventBus(max_queue_depth=100)
    await bus.start()
    
    market_events = []
    news_events = []
    
    async def market_handler(event: Event):
        market_events.append(event)
    
    async def news_handler(event: Event):
        news_events.append(event)
    
    # Subscribe to different event types
    await bus.subscribe(EventType.MARKET_DATA_UPDATED, market_handler)
    await bus.subscribe(EventType.HIGH_IMPACT_NEWS, news_handler)
    
    # Publish different event types
    market_event = Event(
        type=EventType.MARKET_DATA_UPDATED,
        timestamp=datetime.utcnow(),
        data={"symbol": "XAUUSD"}
    )
    news_event = Event(
        type=EventType.HIGH_IMPACT_NEWS,
        timestamp=datetime.utcnow(),
        data={"headline": "Fed raises rates"}
    )
    
    await bus.publish(market_event)
    await bus.publish(news_event)
    
    await asyncio.sleep(0.1)
    
    # Each handler should only receive its event type
    assert len(market_events) == 1
    assert len(news_events) == 1
    assert market_events[0].type == EventType.MARKET_DATA_UPDATED
    assert news_events[0].type == EventType.HIGH_IMPACT_NEWS
    
    await bus.stop()
