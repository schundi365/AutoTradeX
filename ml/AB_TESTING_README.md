# A/B Testing Framework

## Overview

The A/B Testing Framework enables comparing multiple strategy variants in production by allocating capital across variants, tracking performance metrics separately, and adaptively rebalancing based on statistical significance testing.

## Features

- **Capital Allocation**: Distribute trading capital across strategy variants based on configured weights
- **Performance Tracking**: Track comprehensive metrics separately for each variant
- **Statistical Testing**: Compute statistical significance using t-tests
- **Adaptive Rebalancing**: Automatically reduce allocation for underperforming variants
- **Weekly Rebalancing**: Periodic rebalancing based on performance data

## Requirements Validated

- **Requirement 16.1**: Allocate capital across variants based on configured weights
- **Requirement 16.2**: Track performance metrics separately per variant
- **Requirement 16.3**: Compute statistical significance using t-tests
- **Requirement 16.4**: Reduce allocation for underperforming variants (>2 std dev below mean)

## Usage Example

```python
from ml.ab_testing_framework import ABTestingFramework, VariantConfig, Trade
from datetime import datetime

# Define strategy variants
variants = [
    VariantConfig(
        variant_id="conservative",
        name="Conservative Strategy",
        initial_weight=0.3,
        description="Low risk, steady returns"
    ),
    VariantConfig(
        variant_id="aggressive",
        name="Aggressive Strategy",
        initial_weight=0.3,
        description="High risk, high reward"
    ),
    VariantConfig(
        variant_id="balanced",
        name="Balanced Strategy",
        initial_weight=0.4,
        description="Medium risk, balanced approach"
    )
]

# Initialize framework
framework = ABTestingFramework(
    total_capital=100000.0,
    variants=variants,
    rebalance_frequency_days=7,
    min_trades_for_testing=30,
    significance_level=0.05,
    underperformance_threshold_std=2.0
)

# Allocate capital
allocation = framework.allocate_capital()
print(f"Initial allocation: {allocation}")

# Record trades
trade = Trade(
    trade_id="trade_001",
    variant_id="conservative",
    timestamp=datetime.now(),
    symbol="XAUUSD",
    direction="LONG",
    entry_price=2000.0,
    exit_price=2010.0,
    position_size=1.0,
    pnl=100.0,
    holding_time_seconds=3600,
    capital_allocated=30000.0
)
framework.record_trade(trade)

# Get metrics for a variant
metrics = framework.get_variant_metrics("conservative")
print(f"Conservative strategy metrics:")
print(f"  Total return: ${metrics.total_return:.2f}")
print(f"  Sharpe ratio: {metrics.sharpe_ratio:.2f}")
print(f"  Win rate: {metrics.win_rate:.2%}")
print(f"  Number of trades: {metrics.num_trades}")

# Compute statistical significance between variants
result = framework.compute_statistical_significance("conservative", "aggressive")
if result:
    print(f"\nStatistical test results:")
    print(f"  t-statistic: {result.t_statistic:.4f}")
    print(f"  p-value: {result.p_value:.4f}")
    print(f"  Significant: {result.is_significant}")

# Check for underperformers
underperformers = framework.identify_underperforming_variants()
print(f"\nUnderperforming variants: {underperformers}")

# Rebalance allocation
if framework.should_rebalance():
    new_weights = framework.rebalance_allocation()
    print(f"\nNew allocation weights: {new_weights}")

# Generate comparison report
report = framework.get_comparison_report()
print(f"\nComparison report generated at: {report['timestamp']}")
```

## Performance Metrics Tracked

For each variant, the framework tracks:

- **Total return**: Sum of all P&L
- **Sharpe ratio**: Risk-adjusted return metric
- **Sortino ratio**: Downside risk-adjusted return
- **Max drawdown**: Maximum peak-to-trough decline
- **Win rate**: Percentage of profitable trades
- **Profit factor**: Gross profit / gross loss
- **Average trade P&L**: Mean profit/loss per trade
- **Average holding time**: Mean duration of trades
- **Number of trades**: Total trade count
- **Capital allocated**: Current capital allocation

## Statistical Testing

The framework uses independent samples t-tests to compare performance between variants:

- **Null hypothesis**: No difference in mean returns between variants
- **Significance level**: α = 0.05 (configurable)
- **Minimum sample size**: 30 trades per variant (configurable)
- **Output**: t-statistic, p-value, 95% confidence interval

## Adaptive Rebalancing

The rebalancing algorithm:

1. Identifies underperformers (Sharpe ratio > 2 std dev below mean)
2. Reduces underperformer allocation by 50%
3. Redistributes capital to non-underperformers proportionally to their Sharpe ratios
4. Normalizes weights to sum to 1.0
5. Updates capital allocation

Rebalancing occurs weekly by default (configurable).

## Testing

The framework includes comprehensive tests:

- **Unit tests**: `tests/test_ab_testing_framework.py`
- **Property tests**: `tests/property_tests/test_ab_testing_properties.py`

Property tests validate:
- Property 41: Capital allocation matches configured weights (±1%)
- Property 42: Metrics tracked separately per variant
- Property 43: Statistical significance computed using t-tests
- Property 44: Adaptive allocation reduces underperformers

Run tests:
```bash
# Unit tests
python -m pytest tests/test_ab_testing_framework.py -v

# Property tests
python -m pytest tests/property_tests/test_ab_testing_properties.py -v
```

## Integration with APEX Trading Bot

The A/B testing framework integrates with the APEX autonomous trading bot to:

1. **Allocate capital** across different strategy variants
2. **Track performance** of each variant separately
3. **Automatically rebalance** based on statistical performance
4. **Provide dashboard data** for side-by-side comparison

The framework can be used to test:
- Different ML models
- Different risk management parameters
- Different entry/exit strategies
- Different position sizing algorithms

## Configuration Parameters

- `total_capital`: Total capital available for allocation
- `variants`: List of VariantConfig objects
- `rebalance_frequency_days`: Days between rebalancing (default: 7)
- `min_trades_for_testing`: Minimum trades for statistical testing (default: 30)
- `significance_level`: Alpha for statistical tests (default: 0.05)
- `underperformance_threshold_std`: Std deviations below mean to trigger reduction (default: 2.0)

## Notes

- Weights must sum to 1.0 (within ±1% tolerance)
- Statistical tests require minimum sample size per variant
- Rebalancing only occurs after the configured frequency period
- All metrics are computed incrementally for efficiency
- The framework is thread-safe for concurrent trade recording
