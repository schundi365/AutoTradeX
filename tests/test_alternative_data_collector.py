"""
Unit tests for AlternativeDataCollector.

Tests specific examples, edge cases, and error conditions for alternative data collection.
"""
import pytest
import asyncio
from datetime import datetime

from data.collectors import (
    AlternativeDataCollector,
    OnChainMetrics,
    SocialSentiment,
    OptionsData,
    EconomicEvent,
)
from data.event_bus import EventBus, EventType


@pytest.fixture
def alt_data_collector():
    """Create an AlternativeDataCollector instance"""
    return AlternativeDataCollector(refresh_interval_minutes=5)


@pytest.fixture
def alt_data_collector_with_bus():
    """Create an AlternativeDataCollector with event bus"""
    event_bus = EventBus()
    collector = AlternativeDataCollector(
        event_bus=event_bus,
        refresh_interval_minutes=5
    )
    return collector, event_bus


def test_collector_initialization():
    """Test that AlternativeDataCollector initializes correctly"""
    collector = AlternativeDataCollector(refresh_interval_minutes=5)
    
    assert collector is not None
    assert collector.refresh_interval == 300  # 5 minutes in seconds
    assert collector._running is False
    assert collector.event_bus is None


@pytest.mark.asyncio
async def test_collect_onchain_metrics(alt_data_collector):
    """Test collection of on-chain metrics"""
    metrics = await alt_data_collector.collect_onchain_metrics('BTCUSD')
    
    assert metrics is not None
    assert metrics.symbol == 'BTCUSD'
    assert metrics.source == 'glassnode'
    assert metrics.transaction_volume > 0
    assert metrics.active_addresses > 0
    assert metrics.exchange_inflow > 0
    assert metrics.exchange_outflow > 0
    # Net flow should be calculated
    assert metrics.net_flow == metrics.exchange_outflow - metrics.exchange_inflow


@pytest.mark.asyncio
async def test_collect_social_sentiment(alt_data_collector):
    """Test collection of social sentiment"""
    sentiment = await alt_data_collector.collect_social_sentiment('XAUUSD')
    
    assert sentiment is not None
    assert sentiment.symbol == 'XAUUSD'
    assert sentiment.platform == 'twitter'
    assert sentiment.mention_count > 0
    assert -1.0 <= sentiment.sentiment_score <= 1.0
    assert 0.0 <= sentiment.engagement_score <= 1.0
    assert isinstance(sentiment.trending, bool)


@pytest.mark.asyncio
async def test_collect_options_data(alt_data_collector):
    """Test collection of options data"""
    options = await alt_data_collector.collect_options_data('XAUUSD')
    
    assert options is not None
    assert options.symbol == 'XAUUSD'
    assert options.source == 'options_provider'
    assert options.implied_volatility > 0
    assert options.put_call_ratio > 0
    assert options.max_pain > 0
    assert options.open_interest > 0


@pytest.mark.asyncio
async def test_collect_economic_calendar(alt_data_collector):
    """Test collection of economic calendar events"""
    events = await alt_data_collector.collect_economic_calendar()
    
    assert events is not None
    assert len(events) > 0
    
    for event in events:
        assert event.event_id is not None
        assert event.timestamp is not None
        assert event.country is not None
        assert event.event_name is not None
        assert event.importance in ['LOW', 'MEDIUM', 'HIGH']


@pytest.mark.asyncio
async def test_start_stop_collector(alt_data_collector):
    """Test starting and stopping the collector"""
    # Start collector
    await alt_data_collector.start()
    assert alt_data_collector._running is True
    assert alt_data_collector._collector_task is not None
    
    # Wait a bit
    await asyncio.sleep(0.1)
    
    # Stop collector
    await alt_data_collector.stop()
    assert alt_data_collector._running is False


@pytest.mark.asyncio
async def test_data_unavailable_tracking(alt_data_collector):
    """Test tracking of unavailable data sources"""
    # Initially all sources should be available (None)
    assert alt_data_collector._data_unavailable_since['onchain'] is None
    
    # Mark a source as unavailable
    alt_data_collector._mark_data_unavailable('onchain')
    assert alt_data_collector._data_unavailable_since['onchain'] is not None
    
    # Mark it as available again
    alt_data_collector._mark_data_available('onchain')
    assert alt_data_collector._data_unavailable_since['onchain'] is None


@pytest.mark.asyncio
async def test_alternative_data_update_event(alt_data_collector_with_bus):
    """Test that alternative data updates emit events"""
    collector, event_bus = alt_data_collector_with_bus
    
    # Start event bus
    await event_bus.start()
    
    # Track emitted events
    emitted_events = []
    
    async def capture_event(event):
        emitted_events.append(event)
    
    await event_bus.subscribe(EventType.ALTERNATIVE_DATA_UPDATED, capture_event)
    
    # Emit update event
    await collector._emit_update_event()
    
    # Wait for event processing
    await asyncio.sleep(0.1)
    
    # Stop event bus
    await event_bus.stop()
    
    # Verify event was emitted
    assert len(emitted_events) > 0
    assert emitted_events[0].type == EventType.ALTERNATIVE_DATA_UPDATED
    assert 'sources_available' in emitted_events[0].data
    assert 'sources_unavailable' in emitted_events[0].data


def test_onchain_metrics_to_dict():
    """Test OnChainMetrics serialization to dictionary"""
    metrics = OnChainMetrics(
        symbol='BTCUSD',
        timestamp=datetime.utcnow(),
        source='glassnode',
        transaction_volume=1e9,
        active_addresses=500000,
        exchange_inflow=1e6,
        exchange_outflow=2e6,
        net_flow=1e6,
    )
    
    metrics_dict = metrics.to_dict()
    
    assert metrics_dict['symbol'] == 'BTCUSD'
    assert metrics_dict['source'] == 'glassnode'
    assert metrics_dict['transaction_volume'] == 1e9
    assert metrics_dict['active_addresses'] == 500000
    assert metrics_dict['net_flow'] == 1e6


def test_social_sentiment_to_dict():
    """Test SocialSentiment serialization to dictionary"""
    sentiment = SocialSentiment(
        symbol='XAUUSD',
        timestamp=datetime.utcnow(),
        source='social_aggregator',
        platform='twitter',
        mention_count=1000,
        sentiment_score=0.5,
        engagement_score=0.8,
        trending=True,
    )
    
    sentiment_dict = sentiment.to_dict()
    
    assert sentiment_dict['symbol'] == 'XAUUSD'
    assert sentiment_dict['platform'] == 'twitter'
    assert sentiment_dict['mention_count'] == 1000
    assert sentiment_dict['sentiment_score'] == 0.5
    assert sentiment_dict['trending'] is True


def test_options_data_to_dict():
    """Test OptionsData serialization to dictionary"""
    options = OptionsData(
        symbol='XAUUSD',
        timestamp=datetime.utcnow(),
        source='options_provider',
        implied_volatility=0.25,
        put_call_ratio=1.1,
        max_pain=2050.0,
        open_interest=50000,
    )
    
    options_dict = options.to_dict()
    
    assert options_dict['symbol'] == 'XAUUSD'
    assert options_dict['implied_volatility'] == 0.25
    assert options_dict['put_call_ratio'] == 1.1
    assert options_dict['max_pain'] == 2050.0


def test_economic_event_to_dict():
    """Test EconomicEvent serialization to dictionary"""
    event = EconomicEvent(
        event_id='event_123',
        timestamp=datetime.utcnow(),
        country='US',
        event_name='Non-Farm Payrolls',
        importance='HIGH',
        actual=250000.0,
        forecast=200000.0,
        previous=180000.0,
    )
    
    event_dict = event.to_dict()
    
    assert event_dict['event_id'] == 'event_123'
    assert event_dict['country'] == 'US'
    assert event_dict['event_name'] == 'Non-Farm Payrolls'
    assert event_dict['importance'] == 'HIGH'
    assert event_dict['actual'] == 250000.0


@pytest.mark.asyncio
async def test_multiple_symbol_collection(alt_data_collector):
    """Test collecting data for multiple symbols"""
    symbols = ['BTCUSD', 'ETHUSD', 'XAUUSD']
    
    for symbol in symbols:
        metrics = await alt_data_collector.collect_onchain_metrics(symbol)
        if metrics:  # Only crypto symbols will have on-chain data
            assert metrics.symbol == symbol


@pytest.mark.asyncio
async def test_refresh_interval_configuration():
    """Test that refresh interval is configurable"""
    collector_1min = AlternativeDataCollector(refresh_interval_minutes=1)
    assert collector_1min.refresh_interval == 60
    
    collector_10min = AlternativeDataCollector(refresh_interval_minutes=10)
    assert collector_10min.refresh_interval == 600


@pytest.mark.asyncio
async def test_concurrent_data_collection(alt_data_collector):
    """Test that multiple data sources can be collected concurrently"""
    # Collect from all sources concurrently
    results = await asyncio.gather(
        alt_data_collector.collect_onchain_metrics('BTCUSD'),
        alt_data_collector.collect_social_sentiment('XAUUSD'),
        alt_data_collector.collect_options_data('XAUUSD'),
        alt_data_collector.collect_economic_calendar(),
        return_exceptions=True
    )
    
    # Verify all collections completed
    assert len(results) == 4
    
    # Check that results are of correct types
    assert isinstance(results[0], OnChainMetrics) or results[0] is None
    assert isinstance(results[1], SocialSentiment) or results[1] is None
    assert isinstance(results[2], OptionsData) or results[2] is None
    assert isinstance(results[3], list)


@pytest.mark.asyncio
async def test_collector_handles_errors_gracefully(alt_data_collector):
    """Test that collector handles errors without crashing"""
    # This should not raise an exception even if data collection fails
    try:
        await alt_data_collector._collect_all_onchain()
        await alt_data_collector._collect_all_social()
        await alt_data_collector._collect_all_options()
    except Exception as e:
        pytest.fail(f"Collector should handle errors gracefully, but raised: {e}")
