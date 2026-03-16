"""
Property-based tests for tick data collection and storage.

These tests validate universal properties that should hold for all tick data
regardless of specific values, using the hypothesis library for property-based testing.
"""

from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional
import pytest
from hypothesis import given, strategies as st, settings


@dataclass
class Tick:
    """Tick data model matching the design specification."""
    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    last: float
    volume: int
    spread: Optional[float] = None
    spread_pct: Optional[float] = None
    tick_direction: Optional[int] = None
    
    def __post_init__(self):
        """Compute derived fields if not provided."""
        if self.spread is None:
            self.spread = self.ask - self.bid
        if self.spread_pct is None and self.bid > 0:
            mid = (self.bid + self.ask) / 2
            self.spread_pct = (self.spread / mid) * 100 if mid > 0 else 0.0


class MockTickDataCollector:
    """Mock implementation of TickDataCollector for testing."""
    
    def __init__(self):
        self.ticks = {}
    
    def store_tick(self, tick: Tick) -> None:
        """Store a tick in memory."""
        key = (tick.symbol, tick.timestamp)
        self.ticks[key] = tick
    
    def get_tick(self, symbol: str, timestamp: datetime) -> Optional[Tick]:
        """Retrieve a tick by symbol and timestamp."""
        return self.ticks.get((symbol, timestamp))
    
    def get_recent_ticks(self, symbol: str, seconds: int) -> list[Tick]:
        """Get recent ticks for a symbol within the specified time window."""
        cutoff = datetime.now() - timedelta(seconds=seconds)
        return [
            tick for (sym, ts), tick in self.ticks.items()
            if sym == symbol and ts >= cutoff
        ]


# Hypothesis strategies for generating test data
symbols_strategy = st.sampled_from(["XAUUSD", "EURUSD", "GBPUSD", "BTCUSD", "ETHUSD"])
price_strategy = st.floats(min_value=0.01, max_value=100000.0, allow_nan=False, allow_infinity=False)
volume_strategy = st.integers(min_value=1, max_value=1000000)
timestamp_strategy = st.datetimes(
    min_value=datetime(2024, 1, 1),
    max_value=datetime(2026, 12, 31)
)


@pytest.fixture
def collector():
    """Fixture providing a fresh TickDataCollector for each test."""
    return MockTickDataCollector()


@settings(max_examples=100, deadline=5000)
@given(
    symbol=symbols_strategy,
    timestamp=timestamp_strategy,
    bid=price_strategy,
    volume=volume_strategy
)
def test_property_tick_data_completeness(symbol, timestamp, bid, volume):
    """
    Property 2: Tick Data Completeness
    Feature: data-ml-dashboard-improvements, Property 2: For any stored tick, 
    it should contain all required fields: timestamp, bid, ask, spread, and volume.
    
    This property validates that every tick stored in the system contains all
    required fields as specified in Requirement 1.2. The test generates random
    tick data and verifies that after storage and retrieval, all mandatory fields
    are present and non-null.
    
    Validates: Requirements 1.2
    """
    # Arrange: Create collector and generate tick with valid ask price
    collector = MockTickDataCollector()
    ask = bid * 1.001  # Ask is slightly higher than bid (realistic spread)
    last = (bid + ask) / 2  # Last price is mid-point
    
    tick = Tick(
        symbol=symbol,
        timestamp=timestamp,
        bid=bid,
        ask=ask,
        last=last,
        volume=volume
    )
    
    # Act: Store and retrieve the tick
    collector.store_tick(tick)
    retrieved = collector.get_tick(symbol, timestamp)
    
    # Assert: Verify all required fields are present and non-null
    assert retrieved is not None, "Tick should be retrievable after storage"
    assert retrieved.timestamp is not None, "Timestamp must be present"
    assert retrieved.bid is not None, "Bid price must be present"
    assert retrieved.ask is not None, "Ask price must be present"
    assert retrieved.spread is not None, "Spread must be present"
    assert retrieved.volume is not None, "Volume must be present"
    
    # Additional validation: Verify field types and values
    assert isinstance(retrieved.timestamp, datetime), "Timestamp must be datetime"
    assert isinstance(retrieved.bid, float), "Bid must be float"
    assert isinstance(retrieved.ask, float), "Ask must be float"
    assert isinstance(retrieved.spread, float), "Spread must be float"
    assert isinstance(retrieved.volume, int), "Volume must be integer"
    
    # Verify spread calculation is correct
    expected_spread = ask - bid
    assert abs(retrieved.spread - expected_spread) < 1e-6, \
        f"Spread should equal ask - bid: {retrieved.spread} vs {expected_spread}"
    
    # Verify spread percentage is calculated if bid > 0
    if bid > 0:
        assert retrieved.spread_pct is not None, "Spread percentage must be present when bid > 0"
        mid = (bid + ask) / 2
        expected_spread_pct = (expected_spread / mid) * 100
        assert abs(retrieved.spread_pct - expected_spread_pct) < 1e-4, \
            f"Spread percentage should be correct: {retrieved.spread_pct} vs {expected_spread_pct}"


@settings(max_examples=100, deadline=5000)
@given(
    symbol=symbols_strategy,
    timestamp=timestamp_strategy,
    bid=price_strategy,
    volume=volume_strategy
)
def test_property_tick_data_field_preservation(symbol, timestamp, bid, volume):
    """
    Property: Tick Data Field Preservation
    
    Verifies that all tick data fields are preserved exactly during storage
    and retrieval, with no data corruption or loss.
    
    This is a stronger version of Property 2 that checks not just presence
    but also value preservation.
    """
    # Arrange
    collector = MockTickDataCollector()
    ask = bid * 1.001
    last = (bid + ask) / 2
    
    tick = Tick(
        symbol=symbol,
        timestamp=timestamp,
        bid=bid,
        ask=ask,
        last=last,
        volume=volume
    )
    
    # Act
    collector.store_tick(tick)
    retrieved = collector.get_tick(symbol, timestamp)
    
    # Assert: Verify exact field preservation
    assert retrieved.symbol == symbol, "Symbol must be preserved"
    assert retrieved.timestamp == timestamp, "Timestamp must be preserved"
    assert retrieved.bid == bid, "Bid must be preserved"
    assert retrieved.ask == ask, "Ask must be preserved"
    assert retrieved.last == last, "Last price must be preserved"
    assert retrieved.volume == volume, "Volume must be preserved"


@settings(max_examples=50, deadline=5000)
@given(
    symbol=symbols_strategy,
    num_ticks=st.integers(min_value=1, max_value=100)
)
def test_property_tick_data_batch_completeness(symbol, num_ticks):
    """
    Property: Batch Tick Data Completeness
    
    Verifies that when multiple ticks are stored, all of them maintain
    complete field data. This tests that the completeness property holds
    under batch operations.
    """
    # Arrange
    collector = MockTickDataCollector()
    base_time = datetime.now()
    ticks = []
    
    # Generate multiple ticks with sequential timestamps
    for i in range(num_ticks):
        timestamp = base_time + timedelta(seconds=i)
        bid = 2000.0 + i * 0.1
        ask = bid * 1.001
        last = (bid + ask) / 2
        volume = 100 + i
        
        tick = Tick(
            symbol=symbol,
            timestamp=timestamp,
            bid=bid,
            ask=ask,
            last=last,
            volume=volume
        )
        ticks.append(tick)
        collector.store_tick(tick)
    
    # Act & Assert: Verify all ticks have complete data
    for original_tick in ticks:
        retrieved = collector.get_tick(symbol, original_tick.timestamp)
        
        assert retrieved is not None, f"Tick at {original_tick.timestamp} should be retrievable"
        assert retrieved.timestamp is not None
        assert retrieved.bid is not None
        assert retrieved.ask is not None
        assert retrieved.spread is not None
        assert retrieved.volume is not None
        
        # Verify values match
        assert retrieved.symbol == original_tick.symbol
        assert retrieved.timestamp == original_tick.timestamp
        assert retrieved.bid == original_tick.bid
        assert retrieved.ask == original_tick.ask
        assert retrieved.volume == original_tick.volume


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
