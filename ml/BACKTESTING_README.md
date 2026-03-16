# Backtesting Engine

Systematic backtesting framework for evaluating trading strategies on historical data with realistic execution simulation.

## Features

### Replay Modes
- **Bar-by-Bar**: Replay historical OHLCV bars sequentially
- **Tick-by-Tick**: Replay individual price ticks (uses M1 bars as fallback)

### Order Types
- **Market Orders**: Execute immediately at current market price
- **Limit Orders**: Execute when price reaches specified limit
- **Stop-Loss Orders**: Automatically close position when price hits stop level
- **Take-Profit Orders**: Automatically close position when price hits target

### Execution Simulation
- **Slippage Model**: Realistic slippage based on spread and volume impact
  - Base slippage: Half of bid-ask spread
  - Volume impact: Proportional to order size relative to average volume
- **Commission Model**: Configurable broker fees per lot
- **Risk Management**: Position size constraints (default max 2% of capital)

### Performance Metrics
- Total Return
- Sharpe Ratio (annualized)
- Sortino Ratio (annualized)
- Maximum Drawdown
- Win Rate
- Profit Factor
- Average Trade P&L
- Average Holding Time
- Number of Trades

### Results Storage
- Trade-by-trade results with entry/exit prices and P&L
- Equity curve with drawdown overlay
- Strategy parameters and metadata
- Integration with Model Registry

## Requirements

Validates the following requirements from the design document:
- **Requirement 13.1**: Replay historical data tick-by-tick or bar-by-bar
- **Requirement 13.2**: Simulate order execution with configurable slippage and commission models
- **Requirement 13.3**: Compute performance metrics (total return, Sharpe ratio, max drawdown, win rate)
- **Requirement 13.4**: Generate trade-by-trade results with entry/exit prices and P&L
- **Requirement 13.5**: Store results in Model Registry with strategy parameters

## Usage

### Basic Example

```python
from ml.backtesting_engine import BacktestingEngine, BacktestConfig, ReplayMode
from data.historical_data_warehouse import HistoricalDataWarehouse
from datetime import datetime, timedelta

# Initialize warehouse
warehouse = HistoricalDataWarehouse()

# Configure backtest
config = BacktestConfig(
    symbol="XAUUSD",
    start_date=datetime.now() - timedelta(days=180),
    end_date=datetime.now(),
    initial_capital=10000.0,
    replay_mode=ReplayMode.BAR_BY_BAR,
    timeframe="M15",
    commission_per_lot=7.0
)

# Create engine
engine = BacktestingEngine(warehouse, config)

# Define strategy function
def my_strategy(historical_data, current_step):
    # Your strategy logic here
    # Return signal dict or None
    if should_buy:
        return {
            'action': 'OPEN_LONG',
            'size': 0.01,
            'stop_loss': stop_price,
            'take_profit': target_price
        }
    return None

# Run backtest
strategy_params = {'strategy_name': 'my_strategy', 'param1': value1}
result = engine.run_backtest(my_strategy, strategy_params)

# Save results
results_dir = engine.save_backtest_results(result, save_to_registry=True)

# Print performance
print(f"Total Return: {result.total_return*100:.2f}%")
print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
print(f"Max Drawdown: {result.max_drawdown*100:.2f}%")
print(f"Win Rate: {result.win_rate*100:.2f}%")
```

### Strategy Function Format

Your strategy function should accept two parameters:
- `historical_data`: pandas DataFrame with OHLCV data
- `current_step`: Current bar index in the backtest

And return either:
- `None`: No action
- Signal dict with the following format:

```python
{
    'action': 'OPEN_LONG' | 'OPEN_SHORT' | 'CLOSE',
    'size': float,  # Position size in lots (e.g., 0.01)
    'stop_loss': Optional[float],  # Stop-loss price
    'take_profit': Optional[float]  # Take-profit price
}
```

### Moving Average Crossover Example

```python
def ma_crossover_strategy(historical_data, current_step, fast=20, slow=50):
    if current_step < slow:
        return None
    
    # Calculate MAs
    window = historical_data.iloc[max(0, current_step-slow):current_step+1]
    close = window['close'].values
    
    fast_ma = np.mean(close[-fast:])
    slow_ma = np.mean(close[-slow:])
    
    # Previous MAs
    if current_step > slow:
        prev_window = historical_data.iloc[max(0, current_step-slow-1):current_step]
        prev_close = prev_window['close'].values
        prev_fast_ma = np.mean(prev_close[-fast:])
        prev_slow_ma = np.mean(prev_close[-slow:])
    else:
        return None
    
    current_price = close[-1]
    atr = np.std(close[-20:])
    
    # Bullish crossover
    if prev_fast_ma <= prev_slow_ma and fast_ma > slow_ma:
        return {
            'action': 'OPEN_LONG',
            'size': 0.01,
            'stop_loss': current_price - 2 * atr,
            'take_profit': current_price + 3 * atr
        }
    
    # Bearish crossover
    elif prev_fast_ma >= prev_slow_ma and fast_ma < slow_ma:
        return {
            'action': 'OPEN_SHORT',
            'size': 0.01,
            'stop_loss': current_price + 2 * atr,
            'take_profit': current_price - 3 * atr
        }
    
    return None
```

### RSI Mean Reversion Example

```python
def rsi_strategy(historical_data, current_step, period=14, oversold=30, overbought=70):
    if current_step < period + 1:
        return None
    
    # Calculate RSI
    window = historical_data.iloc[max(0, current_step-period-1):current_step+1]
    close = window['close'].values
    
    deltas = np.diff(close)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    
    if avg_loss == 0:
        rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
    
    current_price = close[-1]
    atr = np.std(close[-20:])
    
    # Oversold: buy
    if rsi < oversold:
        return {
            'action': 'OPEN_LONG',
            'size': 0.01,
            'stop_loss': current_price - 2 * atr,
            'take_profit': current_price + 2 * atr
        }
    
    # Overbought: sell
    elif rsi > overbought:
        return {
            'action': 'OPEN_SHORT',
            'size': 0.01,
            'stop_loss': current_price + 2 * atr,
            'take_profit': current_price - 2 * atr
        }
    
    return None
```

## Configuration Options

### BacktestConfig

```python
BacktestConfig(
    symbol: str,                    # Trading symbol (e.g., "XAUUSD")
    start_date: datetime,           # Backtest start date
    end_date: datetime,             # Backtest end date
    initial_capital: float = 10000.0,  # Starting capital
    replay_mode: ReplayMode = ReplayMode.BAR_BY_BAR,  # Replay mode
    timeframe: str = "M15",         # Timeframe for bar-by-bar mode
    
    # Slippage model
    base_slippage_pct: float = 0.0001,  # 0.01% base slippage
    volume_impact_factor: float = 0.001,  # 0.1% per 1% of volume
    
    # Commission model
    commission_per_lot: float = 7.0,  # $7 per lot
    
    # Risk management
    max_position_size: float = 0.02  # 2% max position size
)
```

## Slippage Model

The slippage model simulates realistic execution costs:

```python
slippage = base_slippage + volume_impact

where:
  base_slippage = spread / 2  # Half of bid-ask spread
  volume_impact = (order_size / avg_volume) * volume_impact_factor * price
```

Example:
- Spread: $0.40
- Order size: 0.1 lots
- Average volume: 5000
- Price: $2000
- Volume impact factor: 0.001

```
base_slippage = 0.40 / 2 = $0.20
volume_impact = (0.1 / 5000) * 0.001 * 2000 = $0.04
total_slippage = $0.24
```

## Commission Model

Simple per-lot commission structure:

```python
commission = order_size * commission_per_lot
```

Example:
- Order size: 0.01 lots
- Commission per lot: $7.00
- Total commission: $0.07

## Performance Metrics

### Total Return
```
total_return = (final_capital - initial_capital) / initial_capital
```

### Sharpe Ratio (Annualized)
```
sharpe_ratio = (mean_return / std_return) * sqrt(252)
```

### Sortino Ratio (Annualized)
```
sortino_ratio = (mean_return / downside_std) * sqrt(252)
```

### Maximum Drawdown
```
drawdown = (peak_equity - current_equity) / peak_equity
max_drawdown = max(drawdown over all time)
```

### Win Rate
```
win_rate = winning_trades / total_trades
```

### Profit Factor
```
profit_factor = total_wins / abs(total_losses)
```

## Results Structure

### BacktestResult

```python
@dataclass
class BacktestResult:
    config: BacktestConfig
    trades: List[Trade]
    
    # Performance metrics
    total_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    avg_trade_pnl: float
    avg_holding_time_seconds: float
    num_trades: int
    
    # Equity curve
    equity_curve: pd.DataFrame  # columns: timestamp, equity, peak, drawdown
    
    # Strategy parameters
    strategy_params: Dict[str, Any]
    
    # Metadata
    backtest_id: str
    created_at: datetime
```

### Trade Record

```python
@dataclass
class Trade:
    trade_id: str
    symbol: str
    direction: str  # "LONG" or "SHORT"
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    size: float  # Position size in lots
    pnl: float
    commission: float
    slippage: float
    holding_time_seconds: int
    exit_reason: str  # "take_profit", "stop_loss", "signal", "end_of_backtest"
```

## Saved Files

When you save backtest results, the following files are created:

```
models/backtests/{backtest_id}/
├── metadata.json          # Backtest configuration and performance metrics
├── trades.csv            # Trade-by-trade results
└── equity_curve.csv      # Equity curve with drawdown
```

### metadata.json
```json
{
  "backtest_id": "backtest_20240115_103045",
  "created_at": "2024-01-15T10:30:45",
  "symbol": "XAUUSD",
  "start_date": "2024-01-01T00:00:00",
  "end_date": "2024-01-10T00:00:00",
  "initial_capital": 10000.0,
  "replay_mode": "bar_by_bar",
  "timeframe": "M15",
  "strategy_params": {
    "strategy_name": "MA_Crossover",
    "fast_period": 20,
    "slow_period": 50
  },
  "performance_metrics": {
    "total_return": 0.0523,
    "sharpe_ratio": 1.85,
    "sortino_ratio": 2.34,
    "max_drawdown": 0.0234,
    "win_rate": 0.65,
    "profit_factor": 2.15,
    "avg_trade_pnl": 45.23,
    "avg_holding_time_seconds": 3600,
    "num_trades": 25
  }
}
```

## Testing

Run the test suite:

```bash
python -m pytest tests/test_backtesting_engine.py -v
```

Test coverage includes:
- Slippage model calculations
- Commission model calculations
- Market order execution
- Stop-loss order execution
- Take-profit order execution
- Long and short trades
- Performance metrics calculation
- Results saving

## Examples

See `ml/example_backtest_usage.py` for complete examples:
- Moving Average Crossover strategy
- RSI Mean Reversion strategy
- Strategy comparison framework

Run examples:

```bash
python ml/example_backtest_usage.py
```

## Integration with Model Registry

The backtesting engine integrates with the Model Registry to store backtest results alongside trained models. This enables:

1. **Strategy Versioning**: Track different strategy variants and parameters
2. **Performance Comparison**: Compare backtest results across strategies
3. **Model Selection**: Choose best-performing strategies for deployment
4. **Reproducibility**: Store all parameters needed to reproduce results

When `save_to_registry=True`, backtest results are registered with:
- Strategy parameters
- Performance metrics
- Links to result files
- Timestamp and metadata

## Best Practices

1. **Use Sufficient Historical Data**: At least 6 months for meaningful results
2. **Test Multiple Timeframes**: Validate strategy across different timeframes
3. **Include Transaction Costs**: Always enable slippage and commissions
4. **Avoid Overfitting**: Test on out-of-sample data
5. **Consider Market Regimes**: Test across different market conditions
6. **Use Realistic Position Sizing**: Don't exceed risk management limits
7. **Validate Stop-Loss/Take-Profit**: Ensure risk/reward ratios are realistic
8. **Compare to Benchmark**: Compare against buy-and-hold baseline

## Limitations

1. **Tick Data**: Full tick-by-tick replay not yet implemented (uses M1 bars)
2. **Market Impact**: Simplified volume impact model
3. **Liquidity**: Assumes all orders can be filled
4. **Slippage**: Fixed model, doesn't account for market volatility
5. **Overnight Gaps**: Bar-by-bar mode doesn't simulate gap risk
6. **Multiple Positions**: Currently supports one position at a time

## Future Enhancements

- [ ] Full tick-by-tick replay with actual tick data
- [ ] Multiple simultaneous positions
- [ ] Portfolio-level backtesting (multiple symbols)
- [ ] Walk-forward optimization
- [ ] Monte Carlo simulation
- [ ] Advanced slippage models (volatility-based)
- [ ] Market impact models for large orders
- [ ] Overnight gap simulation
- [ ] Margin and leverage simulation
- [ ] Real-time backtest visualization
