# APEX Property-Based Tests

This directory contains property-based tests for the APEX autonomous trading bot's data, ML, and dashboard improvements.

## Overview

Property-based testing validates universal properties that should hold for all inputs, complementing traditional unit tests that check specific examples. We use the [Hypothesis](https://hypothesis.readthedocs.io/) library for property-based testing.

## Test Structure

```
tests/
├── __init__.py
├── README.md
├── requirements-test.txt
└── property_tests/
    ├── __init__.py
    └── test_tick_data_properties.py
```

## Running Tests

### Install Test Dependencies

```bash
pip install -r tests/requirements-test.txt
```

### Run All Tests

```bash
pytest
```

### Run Specific Test File

```bash
pytest tests/property_tests/test_tick_data_properties.py
```

### Run with Coverage

```bash
pytest --cov=. --cov-report=html
```

### Run Property Tests Only

```bash
pytest -m property
```

## Property Test Format

Each property test follows this structure:

```python
@settings(max_examples=100, deadline=5000)
@given(
    param1=strategy1,
    param2=strategy2
)
def test_property_name(param1, param2):
    """
    Property N: Property Name
    Feature: data-ml-dashboard-improvements, Property N: Property description
    
    Detailed explanation of what this property validates.
    
    Validates: Requirements X.Y
    """
    # Arrange: Set up test data
    # Act: Perform operation
    # Assert: Verify property holds
```

## Property Test Categories

### 1. Data Integrity Properties
- **Property 2**: Tick Data Completeness - All stored ticks contain required fields
- **Property 5**: Order Book Level Completeness
- **Property 10**: Sentiment Result Completeness
- **Property 28**: Model Feature Consistency

### 2. Calculation Properties
- **Property 7**: Order Book Imbalance Calculation
- **Property 24**: Feature Normalization
- **Property 31**: RL Reward Function Correctness

### 3. Latency Properties
- **Property 1**: Tick Capture Latency (<100ms)
- **Property 6**: Large Order Event Latency (<200ms)
- **Property 9**: Sentiment Processing Latency (<5s)
- **Property 16**: Indicator Recomputation Latency (<50ms)

### 4. Retention Properties
- **Property 3**: Tick Data Retention (24 hours in memory)
- **Property 8**: Order Book Snapshot Retention (6 hours)
- **Property 23**: Multi-Timeframe Cache Size (500 bars)

### 5. Detection Properties
- **Property 20**: Trend Alignment Detection
- **Property 21**: Divergence Detection
- **Property 25**: Data Quality Anomaly Detection

### 6. Business Logic Properties
- **Property 30**: Model Accuracy Threshold (>52%)
- **Property 33**: RL Agent Promotion Criteria (Sharpe >1.5)
- **Property 48**: Model Promotion Logic

## Configuration

### Hypothesis Settings

- **max_examples**: 100 iterations per property test (minimum for statistical confidence)
- **deadline**: 5000ms timeout per test case
- **seed**: Fixed at 42 for reproducibility in CI/CD

### Pytest Configuration

See `pytest.ini` for full configuration including:
- Test discovery patterns
- Coverage settings
- Markers for test categorization
- Asyncio configuration

## Writing New Property Tests

1. **Identify the Property**: What universal truth should hold?
2. **Define Strategies**: Use Hypothesis strategies to generate test data
3. **Write the Test**: Follow the AAA pattern (Arrange, Act, Assert)
4. **Add Documentation**: Include property number and requirement references
5. **Tag Appropriately**: Use `@pytest.mark.property` marker

### Example

```python
from hypothesis import given, strategies as st, settings

@settings(max_examples=100, deadline=5000)
@given(
    symbol=st.sampled_from(["XAUUSD", "EURUSD"]),
    price=st.floats(min_value=0.01, max_value=100000)
)
@pytest.mark.property
def test_property_example(symbol, price):
    """
    Property X: Example Property
    Feature: data-ml-dashboard-improvements, Property X: Description
    
    Validates: Requirements Y.Z
    """
    # Test implementation
    pass
```

## CI/CD Integration

Property tests are integrated into the CI/CD pipeline:

1. **Linting Stage**: Code quality checks
2. **Unit Test Stage**: Traditional unit tests
3. **Property Test Stage**: Property-based tests with fixed seed
4. **Integration Test Stage**: End-to-end tests
5. **Performance Test Stage**: Latency and throughput validation

## Best Practices

1. **Use Appropriate Strategies**: Choose strategies that generate realistic data
2. **Set Reasonable Bounds**: Avoid extreme values that would never occur in production
3. **Test One Property**: Each test should validate a single property
4. **Document Clearly**: Explain what property is being tested and why
5. **Handle Edge Cases**: Consider zero, negative, and boundary values
6. **Keep Tests Fast**: Use deadline parameter to prevent slow tests
7. **Use Fixed Seeds**: Ensure reproducibility in CI/CD environments

## Troubleshooting

### Tests Failing Intermittently

- Check if using random data without fixed seed
- Verify hypothesis seed is set in pytest.ini
- Look for race conditions in async tests

### Tests Running Slowly

- Reduce max_examples for expensive operations
- Increase deadline if legitimate operations are slow
- Profile tests to identify bottlenecks

### Hypothesis Finds Unexpected Failures

- This is good! Hypothesis found an edge case
- Use `@example()` decorator to add the failing case as a regression test
- Fix the underlying issue in the implementation

## References

- [Hypothesis Documentation](https://hypothesis.readthedocs.io/)
- [Property-Based Testing Guide](https://hypothesis.works/articles/what-is-property-based-testing/)
- [Design Document](.kiro/specs/data-ml-dashboard-improvements/design.md)
- [Requirements Document](.kiro/specs/data-ml-dashboard-improvements/requirements.md)
