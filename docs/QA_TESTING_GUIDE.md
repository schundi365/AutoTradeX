# QA and Testing Guide for APEX Trading Bot

## Overview

This guide provides detailed instructions for quality assurance and testing practices for the APEX trading bot. It covers testing strategies, test writing guidelines, and quality standards.

## Testing Philosophy

The APEX bot uses a dual testing approach:
1. **Unit Tests**: Verify specific examples, edge cases, and error conditions
2. **Property-Based Tests**: Verify universal properties across all inputs

Together, these provide comprehensive coverage: unit tests catch concrete bugs, while property tests verify general correctness.

---

## Test Organization

### Directory Structure

```
tests/
├── unit/                    # Unit tests (70% of tests)
│   ├── core/
│   │   ├── test_tick_collector.py
│   │   ├── test_sentiment_analyzer.py
│   │   ├── test_feature_pipeline.py
│   │   └── test_data_quality_monitor.py
│   ├── agents/
│   │   ├── test_autonomous_orchestrator.py
│   │   └── test_parallel_analyzer.py
│   └── api/
│       ├── test_endpoints.py
│       └── test_websocket.py
├── properties/              # Property-based tests (20% of tests)
│   ├── test_tick_data_properties.py
│   ├── test_order_book_properties.py
│   ├── test_ml_model_properties.py
│   └── test_feature_properties.py
├── integration/             # Integration tests (10% of tests)
│   ├── test_data_flow.py
│   ├── test_ml_pipeline.py
│   └── test_dashboard_updates.py
├── performance/             # Performance benchmarks
│   ├── test_tick_collection_perf.py
│   ├── test_indicator_computation_perf.py
│   └── test_model_inference_perf.py
├── smoke/                   # Smoke tests for deployments
│   └── test_basic_functionality.py
└── conftest.py             # Shared fixtures
```

---

## Unit Testing Guidelines

### Test Structure (AAA Pattern)

```python
def test_function_name():
    """Test description in plain English"""
    # Arrange - Set up test data and dependencies
    collector = TickDataCollector()
    tick = Tick(symbol="XAUUSD", bid=2050.0, ask=2050.5)
    
    # Act - Execute the function being tested
    result = collector.store_tick(tick)
    
    # Assert - Verify the expected outcome
    assert result is True
    assert collector.get_tick_count() == 1
```

### Test Naming Convention

Use descriptive names that explain what is being tested:

**Good**:
```python
def test_tick_collector_stores_valid_tick_successfully()
def test_tick_collector_rejects_negative_prices()
def test_sentiment_analyzer_handles_empty_article()
```

**Bad**:
```python
def test_1()
def test_tick()
def test_error()
```

### Testing Edge Cases

Always test boundary conditions and edge cases:

```python
class TestTickDataCollector:
    def test_empty_symbol(self, collector):
        """Test with empty symbol string"""
        tick = Tick(symbol="", bid=2050.0, ask=2050.5)
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            collector.store_tick(tick)
    
    def test_negative_price(self, collector):
        """Test with negative price"""
        tick = Tick(symbol="XAUUSD", bid=-100.0, ask=2050.5)
        with pytest.raises(ValueError, match="Price cannot be negative"):
            collector.store_tick(tick)
    
    def test_bid_greater_than_ask(self, collector):
        """Test with bid > ask (invalid spread)"""
        tick = Tick(symbol="XAUUSD", bid=2051.0, ask=2050.0)
        with pytest.raises(ValueError, match="Bid cannot exceed ask"):
            collector.store_tick(tick)
    
    def test_zero_volume(self, collector):
        """Test with zero volume"""
        tick = Tick(symbol="XAUUSD", bid=2050.0, ask=2050.5, volume=0)
        # Should store but flag as suspicious
        result = collector.store_tick(tick)
        assert result.warning == "Zero volume detected"
```

### Testing Async Code

Use pytest-asyncio for async tests:

```python
import pytest

@pytest.mark.asyncio
async def test_async_tick_collection():
    """Test async tick collection"""
    collector = TickDataCollector()
    await collector.start()
    
    tick = Tick(symbol="XAUUSD", bid=2050.0, ask=2050.5)
    await collector.on_tick("XAUUSD", tick)
    
    ticks = collector.get_recent_ticks("XAUUSD", seconds=10)
    assert len(ticks) == 1
    
    await collector.stop()
```

### Mocking External Dependencies

Use pytest fixtures and mocks for external dependencies:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def mock_mt5_connection():
    """Mock MT5 connection"""
    with patch('core.tick_collector.MT5Connection') as mock:
        mock.return_value.is_connected.return_value = True
        mock.return_value.subscribe_ticks = AsyncMock()
        yield mock

@pytest.mark.asyncio
async def test_tick_collector_with_mock_mt5(mock_mt5_connection):
    """Test tick collector with mocked MT5"""
    collector = TickDataCollector()
    await collector.start()
    
    # Verify MT5 connection was established
    mock_mt5_connection.return_value.subscribe_ticks.assert_called_once()
```

---

## Property-Based Testing Guidelines

### What Are Property Tests?

Property tests verify that a property (invariant) holds for all possible inputs, not just specific examples.

**Example Property**: "For any tick stored, all required fields should be present"

### Writing Property Tests

Use the `hypothesis` library:

```python
from hypothesis import given, strategies as st
import pytest

@given(
    symbol=st.sampled_from(["XAUUSD", "EURUSD", "BTCUSD"]),
    bid=st.floats(min_value=0.01, max_value=100000, allow_nan=False),
    ask=st.floats(min_value=0.01, max_value=100000, allow_nan=False)
)
def test_property_tick_data_completeness(symbol, bid, ask):
    """
    Feature: data-ml-dashboard-improvements, Property 2: Tick Data Completeness
    
    For any stored tick, it should contain all required fields:
    timestamp, bid, ask, spread, and volume.
    """
    # Ensure ask >= bid
    if ask < bid:
        bid, ask = ask, bid
    
    tick = Tick(
        symbol=symbol,
        timestamp=datetime.now(),
        bid=bid,
        ask=ask,
        last=(bid + ask) / 2,
        volume=100
    )
    
    collector = TickDataCollector()
    collector.store_tick(tick)
    retrieved = collector.get_tick(tick.timestamp)
    
    # Verify all required fields are present and not None
    assert retrieved.timestamp is not None
    assert retrieved.bid is not None
    assert retrieved.ask is not None
    assert retrieved.spread is not None
    assert retrieved.volume is not None
```

### Property Test Tag Format

Every property test MUST include a docstring tag:

```python
"""
Feature: {feature-name}, Property {number}: {property_text}
"""
```

This links the test to the design document property.

### Custom Strategies

Create reusable strategies for domain objects:

```python
from hypothesis import strategies as st

# Strategy for valid symbols
symbol_strategy = st.sampled_from([
    "XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "BTCUSD", "ETHUSD"
])

# Strategy for valid prices
price_strategy = st.floats(
    min_value=0.01,
    max_value=100000,
    allow_nan=False,
    allow_infinity=False
)

# Composite strategy for ticks
@st.composite
def tick_strategy(draw):
    symbol = draw(symbol_strategy)
    bid = draw(price_strategy)
    spread = draw(st.floats(min_value=0.0001, max_value=bid * 0.01))
    ask = bid + spread
    
    return Tick(
        symbol=symbol,
        timestamp=datetime.now(),
        bid=bid,
        ask=ask,
        last=(bid + ask) / 2,
        volume=draw(st.integers(min_value=1, max_value=1000000))
    )

# Usage
@given(tick=tick_strategy())
def test_property_with_custom_strategy(tick):
    """Test using custom tick strategy"""
    assert tick.ask >= tick.bid
    assert tick.spread == tick.ask - tick.bid
```

### Property Test Configuration

Configure hypothesis in `pytest.ini`:

```ini
[pytest]
addopts = 
    --hypothesis-show-statistics
    --hypothesis-seed=12345

[tool:pytest]
hypothesis_profile = ci

[tool:hypothesis]
max_examples = 100
deadline = 5000
verbosity = normal
```

---

## Integration Testing Guidelines

### Test Environment Setup

Use Docker Compose for integration tests:

**docker-compose.test.yml**:
```yaml
version: '3.8'

services:
  timescaledb:
    image: timescale/timescaledb:latest-pg15
    environment:
      POSTGRES_USER: test_user
      POSTGRES_PASSWORD: test_password
      POSTGRES_DB: test_db
    ports:
      - "5432:5432"
  
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
  
  duckdb:
    image: alpine:latest
    volumes:
      - ./test_data:/data
    command: sleep infinity
```

### Integration Test Example

```python
import pytest
import asyncio
from datetime import datetime

@pytest.mark.integration
@pytest.mark.asyncio
async def test_end_to_end_data_flow():
    """
    Test complete data flow: Tick → Event → Indicators → Features → Decision
    """
    # Arrange
    tick_collector = TickDataCollector()
    event_bus = EventBus()
    feature_pipeline = FeaturePipeline(event_bus)
    
    await tick_collector.start()
    await feature_pipeline.start()
    
    # Act - Simulate tick arrival
    tick = Tick(symbol="XAUUSD", bid=2050.0, ask=2050.5, volume=100)
    await tick_collector.on_tick("XAUUSD", tick)
    
    # Wait for event processing
    await asyncio.sleep(0.2)
    
    # Assert - Verify indicators were computed
    indicators = feature_pipeline.get_indicators("XAUUSD")
    assert indicators is not None
    assert "rsi" in indicators
    assert "adx" in indicators
    
    # Assert - Verify features were cached
    features = await feature_pipeline.get_features("XAUUSD")
    assert features is not None
    assert len(features) > 0
    
    # Cleanup
    await tick_collector.stop()
    await feature_pipeline.stop()
```

---

## Performance Testing Guidelines

### Benchmark Tests

Use pytest-benchmark for performance testing:

```python
import pytest

def test_indicator_computation_performance(benchmark):
    """Benchmark indicator computation time"""
    # Setup
    ohlcv_data = generate_sample_ohlcv(250)
    
    # Benchmark
    result = benchmark(compute_indicators, "XAUUSD", ohlcv_data)
    
    # Verify result is valid
    assert result is not None
    assert "rsi" in result
    
    # pytest-benchmark will report:
    # - Mean time
    # - Standard deviation
    # - Min/Max time
    # - Iterations per second

def test_model_inference_latency(benchmark):
    """Benchmark ML model inference time"""
    model = load_model("xgboost_v1")
    features = generate_sample_features()
    
    result = benchmark(model.predict, features)
    
    assert result is not None
    # Target: <20ms per prediction
```

### Load Testing

Test system under high load:

```python
import pytest
import asyncio

@pytest.mark.performance
@pytest.mark.asyncio
async def test_high_tick_volume_load():
    """Test system with 1000 ticks per second"""
    collector = TickDataCollector()
    await collector.start()
    
    # Generate 1000 ticks
    ticks = [
        Tick(symbol=f"SYM{i%10}", bid=2050.0, ask=2050.5, volume=100)
        for i in range(1000)
    ]
    
    # Send all ticks concurrently
    start_time = time.time()
    tasks = [collector.on_tick(tick.symbol, tick) for tick in ticks]
    await asyncio.gather(*tasks)
    elapsed = time.time() - start_time
    
    # Verify all processed within 1 second
    assert elapsed < 1.0
    
    # Verify no data loss
    assert collector.get_total_ticks() == 1000
    
    await collector.stop()
```

---

## Code Coverage Requirements

### Coverage Targets

- **Overall**: ≥85%
- **Core business logic**: ≥90%
- **Data models**: ≥95%
- **Error handling**: ≥80%
- **Integration points**: ≥85%

### Measuring Coverage

```bash
# Run tests with coverage
pytest tests/ --cov=core --cov=agents --cov=api --cov-report=html

# View HTML report
open htmlcov/index.html

# Check coverage threshold
coverage report --fail-under=85
```

### Coverage Report Example

```
Name                          Stmts   Miss  Cover
-------------------------------------------------
core/tick_collector.py          150      8    95%
core/sentiment_analyzer.py      120     15    88%
core/feature_pipeline.py        200     25    88%
agents/autonomous_orch.py       180     20    89%
api/server.py                   100     12    88%
-------------------------------------------------
TOTAL                           750     80    89%
```

---

## Test Fixtures and Utilities

### Shared Fixtures

**conftest.py**:
```python
import pytest
from datetime import datetime, timedelta

@pytest.fixture
def sample_tick():
    """Sample tick for testing"""
    return Tick(
        symbol="XAUUSD",
        timestamp=datetime.now(),
        bid=2050.0,
        ask=2050.5,
        last=2050.25,
        volume=100,
        spread=0.5,
        spread_pct=0.024,
        tick_direction=1
    )

@pytest.fixture
def sample_ohlcv_data():
    """Sample OHLCV data (100 bars)"""
    base_price = 2050.0
    return [
        {
            "timestamp": datetime.now() - timedelta(minutes=100-i),
            "open": base_price + i * 0.1,
            "high": base_price + i * 0.1 + 2,
            "low": base_price + i * 0.1 - 2,
            "close": base_price + i * 0.1 + 1,
            "volume": 1000 + i * 10
        }
        for i in range(100)
    ]

@pytest.fixture
async def event_bus():
    """Event bus for testing"""
    bus = EventBus()
    yield bus
    await bus.shutdown()

@pytest.fixture
def mock_redis():
    """Mock Redis connection"""
    from unittest.mock import AsyncMock
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    return redis

@pytest.fixture
async def test_database():
    """Test database with cleanup"""
    db = await create_test_database()
    yield db
    await db.cleanup()
```

### Test Data Generators

```python
def generate_sample_ohlcv(num_bars: int, base_price: float = 2050.0) -> List[dict]:
    """Generate sample OHLCV data for testing"""
    return [
        {
            "timestamp": datetime.now() - timedelta(minutes=num_bars-i),
            "open": base_price + random.uniform(-5, 5),
            "high": base_price + random.uniform(0, 10),
            "low": base_price + random.uniform(-10, 0),
            "close": base_price + random.uniform(-5, 5),
            "volume": random.randint(500, 2000)
        }
        for i in range(num_bars)
    ]

def generate_sample_features(num_features: int = 50) -> Dict[str, float]:
    """Generate sample feature vector"""
    return {
        f"feature_{i}": random.uniform(-3, 3)
        for i in range(num_features)
    }
```

---

## Testing Async Code

### Async Test Patterns

```python
import pytest
import asyncio

@pytest.mark.asyncio
async def test_concurrent_operations():
    """Test multiple async operations"""
    collector = TickDataCollector()
    
    # Run multiple operations concurrently
    tasks = [
        collector.on_tick("XAUUSD", tick1),
        collector.on_tick("EURUSD", tick2),
        collector.on_tick("BTCUSD", tick3)
    ]
    
    results = await asyncio.gather(*tasks)
    
    assert all(r is True for r in results)

@pytest.mark.asyncio
async def test_timeout_handling():
    """Test operation timeout"""
    collector = TickDataCollector()
    
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            collector.slow_operation(),
            timeout=1.0
        )
```

---

## Mocking and Patching

### When to Mock

Mock external dependencies:
- External APIs (news, market data)
- Databases (for unit tests)
- File system operations
- Network calls
- Time-dependent operations

### Mocking Examples

```python
from unittest.mock import patch, MagicMock, AsyncMock

# Mock external API
@patch('core.sentiment_analyzer.requests.get')
def test_sentiment_analyzer_api_call(mock_get):
    """Test sentiment analyzer with mocked API"""
    mock_response = MagicMock()
    mock_response.json.return_value = {"sentiment": 0.8}
    mock_get.return_value = mock_response
    
    analyzer = SentimentAnalyzer()
    result = analyzer.analyze("Test article")
    
    assert result.sentiment_score == 0.8
    mock_get.assert_called_once()

# Mock async function
@pytest.mark.asyncio
@patch('core.tick_collector.MT5Connection')
async def test_tick_collector_connection(mock_mt5):
    """Test tick collector connection"""
    mock_mt5.return_value.connect = AsyncMock(return_value=True)
    
    collector = TickDataCollector()
    result = await collector.connect()
    
    assert result is True
    mock_mt5.return_value.connect.assert_called_once()

# Mock datetime
@patch('core.tick_collector.datetime')
def test_tick_timestamp(mock_datetime):
    """Test tick timestamp generation"""
    fixed_time = datetime(2024, 1, 15, 10, 30, 0)
    mock_datetime.now.return_value = fixed_time
    
    tick = create_tick("XAUUSD", 2050.0, 2050.5)
    
    assert tick.timestamp == fixed_time
```

---

## Test Execution

### Running Tests Locally

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/unit/core/test_tick_collector.py -v

# Run specific test
pytest tests/unit/core/test_tick_collector.py::test_store_tick_success -v

# Run tests matching pattern
pytest tests/ -k "tick" -v

# Run tests with specific marker
pytest tests/ -m "asyncio" -v

# Run with coverage
pytest tests/ --cov=core --cov-report=html

# Run property tests with statistics
pytest tests/properties/ --hypothesis-show-statistics

# Run performance benchmarks
pytest tests/performance/ --benchmark-only
```

### Test Markers

Define markers in `pytest.ini`:

```ini
[pytest]
markers =
    asyncio: Async tests
    integration: Integration tests
    performance: Performance tests
    slow: Slow tests (>1 second)
    unit: Unit tests
    property: Property-based tests
```

Usage:
```python
@pytest.mark.asyncio
@pytest.mark.slow
async def test_long_running_operation():
    """Test that takes >1 second"""
    pass
```

---

## Continuous Testing

### Pre-commit Hooks

Install pre-commit hooks:

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

### Git Hooks

**.git/hooks/pre-push**:
```bash
#!/bin/bash

echo "Running tests before push..."

# Run unit tests
pytest tests/unit/ -v
if [ $? -ne 0 ]; then
    echo "Unit tests failed. Push aborted."
    exit 1
fi

# Run property tests
pytest tests/properties/ -v --hypothesis-seed=12345
if [ $? -ne 0 ]; then
    echo "Property tests failed. Push aborted."
    exit 1
fi

echo "All tests passed. Proceeding with push."
exit 0
```

Make executable:
```bash
chmod +x .git/hooks/pre-push
```

---

## Test Data Management

### Test Data Strategy

1. **Small datasets**: Embed in test code
2. **Medium datasets**: Store in `tests/fixtures/` directory
3. **Large datasets**: Generate programmatically or download on-demand

### Test Data Files

```
tests/
└── fixtures/
    ├── sample_ohlcv.json
    ├── sample_news.json
    ├── sample_trades.json
    └── sample_model_metadata.json
```

### Loading Test Data

```python
import json
from pathlib import Path

def load_test_fixture(filename: str) -> dict:
    """Load test fixture from JSON file"""
    fixture_path = Path(__file__).parent / "fixtures" / filename
    with open(fixture_path) as f:
        return json.load(f)

# Usage
@pytest.fixture
def sample_news_data():
    return load_test_fixture("sample_news.json")
```

---

## Quality Metrics

### Code Quality Metrics

Track these metrics over time:

- **Code Coverage**: ≥85%
- **Cyclomatic Complexity**: ≤10 per function
- **Maintainability Index**: ≥20
- **Technical Debt Ratio**: ≤5%
- **Duplication**: ≤3%

### Test Quality Metrics

- **Test Pass Rate**: 100%
- **Test Execution Time**: <5 minutes for full suite
- **Flaky Test Rate**: <1%
- **Property Test Iterations**: ≥100 per property

### Performance Metrics

- **Tick Capture Latency**: <100ms (p95)
- **Indicator Computation**: <50ms (p95)
- **Model Inference**: <20ms (p95)
- **API Response Time**: <200ms (p95)
- **Dashboard Update**: <500ms (p95)

---

## Troubleshooting Common Issues

### Flaky Tests

**Symptoms**: Tests pass sometimes, fail other times

**Common Causes**:
- Race conditions in async code
- Time-dependent assertions
- External dependency failures
- Insufficient wait times

**Solutions**:
```python
# Bad - time-dependent
def test_timestamp():
    tick = create_tick()
    assert tick.timestamp == datetime.now()  # Flaky!

# Good - use mocking
@patch('core.tick_collector.datetime')
def test_timestamp(mock_datetime):
    fixed_time = datetime(2024, 1, 15, 10, 30, 0)
    mock_datetime.now.return_value = fixed_time
    tick = create_tick()
    assert tick.timestamp == fixed_time

# Bad - insufficient wait
async def test_async_operation():
    await start_operation()
    result = get_result()  # May not be ready yet!

# Good - proper waiting
async def test_async_operation():
    await start_operation()
    await asyncio.sleep(0.1)  # Wait for completion
    result = get_result()
    assert result is not None
```

### Slow Tests

**Symptoms**: Test suite takes too long

**Solutions**:
- Use smaller test datasets
- Mock expensive operations
- Run slow tests separately
- Parallelize test execution

```bash
# Run tests in parallel
pytest tests/ -n auto  # Requires pytest-xdist

# Skip slow tests
pytest tests/ -m "not slow"
```

### Memory Leaks in Tests

**Detection**:
```python
import pytest
import tracemalloc

@pytest.fixture(autouse=True)
def track_memory():
    """Track memory usage in tests"""
    tracemalloc.start()
    yield
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"Memory: current={current/1024/1024:.1f}MB, peak={peak/1024/1024:.1f}MB")
```

**Prevention**:
- Clean up resources in fixtures
- Use context managers
- Close connections explicitly

---

## Best Practices Summary

### DO
✅ Write tests before or alongside code (TDD)
✅ Test happy path and edge cases
✅ Use descriptive test names
✅ Keep tests independent and isolated
✅ Mock external dependencies
✅ Use fixtures for common setup
✅ Run tests locally before pushing
✅ Maintain high code coverage (≥85%)
✅ Write property tests for universal properties
✅ Document test scenarios

### DON'T
❌ Skip writing tests
❌ Test implementation details
❌ Create test dependencies (test order matters)
❌ Use production data in tests
❌ Ignore failing tests
❌ Commit code without running tests
❌ Mock internal functions (test behavior, not implementation)
❌ Write tests that depend on external services
❌ Hardcode test data that should be generated
❌ Leave commented-out test code

---

## Quick Reference

### Run Security Scans
```bash
bandit -r core/ agents/ api/ -f screen
safety check
pip-audit -r requirements.txt
```

### Run All Tests
```bash
pytest tests/ -v --cov=core --cov=agents --cov=api
```

### Format Code
```bash
black core/ agents/ api/ tests/
isort core/ agents/ api/ tests/
```

### Type Check
```bash
mypy core/ agents/ api/
```

### Pre-commit Check
```bash
pre-commit run --all-files
```
