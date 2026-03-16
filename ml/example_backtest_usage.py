"""
Example usage of the Backtesting Engine

Demonstrates how to use the backtesting engine to evaluate trading strategies
on historical data with realistic execution simulation.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from ml.backtesting_engine import (
    BacktestingEngine,
    BacktestConfig,
    ReplayMode
)
from data.historical_data_warehouse import HistoricalDataWarehouse
from core.logger import get_agent_logger

log = get_agent_logger("BACKTEST_EXAMPLE")


def simple_moving_average_strategy(
    historical_data: pd.DataFrame,
    current_step: int,
    fast_period: int = 20,
    slow_period: int = 50
) -> Optional[Dict[str, Any]]:
    """
    Simple moving average crossover strategy.
    
    Args:
        historical_data: Historical OHLCV data
        current_step: Current step in backtest
        fast_period: Fast MA period
        slow_period: Slow MA period
        
    Returns:
        Signal dict or None
    """
    # Need enough data for slow MA
    if current_step < slow_period:
        return None
    
    # Calculate moving averages
    window_data = historical_data.iloc[max(0, current_step-slow_period):current_step+1]
    close_prices = window_data['close'].values
    
    fast_ma = np.mean(close_prices[-fast_period:])
    slow_ma = np.mean(close_prices[-slow_period:])
    
    # Previous MAs
    if current_step > slow_period:
        prev_window = historical_data.iloc[max(0, current_step-slow_period-1):current_step]
        prev_close = prev_window['close'].values
        prev_fast_ma = np.mean(prev_close[-fast_period:])
        prev_slow_ma = np.mean(prev_close[-slow_period:])
    else:
        return None
    
    # Detect crossover
    current_price = close_prices[-1]
    
    # Bullish crossover: fast MA crosses above slow MA
    if prev_fast_ma <= prev_slow_ma and fast_ma > slow_ma:
        # Calculate stop-loss and take-profit
        atr = np.std(close_prices[-20:]) if len(close_prices) >= 20 else current_price * 0.01
        stop_loss = current_price - 2 * atr
        take_profit = current_price + 3 * atr
        
        return {
            'action': 'OPEN_LONG',
            'size': 0.01,  # 0.01 lots
            'stop_loss': stop_loss,
            'take_profit': take_profit
        }
    
    # Bearish crossover: fast MA crosses below slow MA
    elif prev_fast_ma >= prev_slow_ma and fast_ma < slow_ma:
        # Calculate stop-loss and take-profit
        atr = np.std(close_prices[-20:]) if len(close_prices) >= 20 else current_price * 0.01
        stop_loss = current_price + 2 * atr
        take_profit = current_price - 3 * atr
        
        return {
            'action': 'OPEN_SHORT',
            'size': 0.01,
            'stop_loss': stop_loss,
            'take_profit': take_profit
        }
    
    return None


def rsi_strategy(
    historical_data: pd.DataFrame,
    current_step: int,
    rsi_period: int = 14,
    oversold: float = 30,
    overbought: float = 70
) -> Optional[Dict[str, Any]]:
    """
    RSI-based mean reversion strategy.
    
    Args:
        historical_data: Historical OHLCV data
        current_step: Current step in backtest
        rsi_period: RSI calculation period
        oversold: Oversold threshold
        overbought: Overbought threshold
        
    Returns:
        Signal dict or None
    """
    # Need enough data for RSI
    if current_step < rsi_period + 1:
        return None
    
    # Calculate RSI
    window_data = historical_data.iloc[max(0, current_step-rsi_period-1):current_step+1]
    close_prices = window_data['close'].values
    
    deltas = np.diff(close_prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains[-rsi_period:])
    avg_loss = np.mean(losses[-rsi_period:])
    
    if avg_loss == 0:
        rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
    
    current_price = close_prices[-1]
    
    # Oversold: buy signal
    if rsi < oversold:
        atr = np.std(close_prices[-20:]) if len(close_prices) >= 20 else current_price * 0.01
        stop_loss = current_price - 2 * atr
        take_profit = current_price + 2 * atr
        
        return {
            'action': 'OPEN_LONG',
            'size': 0.01,
            'stop_loss': stop_loss,
            'take_profit': take_profit
        }
    
    # Overbought: sell signal
    elif rsi > overbought:
        atr = np.std(close_prices[-20:]) if len(close_prices) >= 20 else current_price * 0.01
        stop_loss = current_price + 2 * atr
        take_profit = current_price - 2 * atr
        
        return {
            'action': 'OPEN_SHORT',
            'size': 0.01,
            'stop_loss': stop_loss,
            'take_profit': take_profit
        }
    
    return None


def run_ma_crossover_backtest():
    """Run backtest with moving average crossover strategy"""
    log.info("=" * 60)
    log.info("Running Moving Average Crossover Backtest")
    log.info("=" * 60)
    
    # Initialize warehouse
    warehouse = HistoricalDataWarehouse()
    
    # Configure backtest
    config = BacktestConfig(
        symbol="XAUUSD",
        start_date=datetime.now() - timedelta(days=180),  # 6 months
        end_date=datetime.now(),
        initial_capital=10000.0,
        replay_mode=ReplayMode.BAR_BY_BAR,
        timeframe="M15",
        commission_per_lot=7.0,
        base_slippage_pct=0.0001,
        volume_impact_factor=0.001
    )
    
    # Create backtesting engine
    engine = BacktestingEngine(warehouse, config)
    
    # Define strategy parameters
    strategy_params = {
        'strategy_name': 'MA_Crossover',
        'fast_period': 20,
        'slow_period': 50,
        'position_size': 0.01
    }
    
    # Create strategy function with parameters
    def strategy_func(data, step):
        return simple_moving_average_strategy(
            data, step,
            fast_period=strategy_params['fast_period'],
            slow_period=strategy_params['slow_period']
        )
    
    # Run backtest
    result = engine.run_backtest(strategy_func, strategy_params)
    
    # Save results
    results_dir = engine.save_backtest_results(result, save_to_registry=True)
    
    log.info(f"\nBacktest completed!")
    log.info(f"Results saved to: {results_dir}")
    log.info(f"\nPerformance Summary:")
    log.info(f"  Total Return: {result.total_return*100:.2f}%")
    log.info(f"  Sharpe Ratio: {result.sharpe_ratio:.2f}")
    log.info(f"  Sortino Ratio: {result.sortino_ratio:.2f}")
    log.info(f"  Max Drawdown: {result.max_drawdown*100:.2f}%")
    log.info(f"  Win Rate: {result.win_rate*100:.2f}%")
    log.info(f"  Profit Factor: {result.profit_factor:.2f}")
    log.info(f"  Number of Trades: {result.num_trades}")
    log.info(f"  Avg Trade P&L: ${result.avg_trade_pnl:.2f}")
    
    return result


def run_rsi_backtest():
    """Run backtest with RSI mean reversion strategy"""
    log.info("=" * 60)
    log.info("Running RSI Mean Reversion Backtest")
    log.info("=" * 60)
    
    # Initialize warehouse
    warehouse = HistoricalDataWarehouse()
    
    # Configure backtest
    config = BacktestConfig(
        symbol="EURUSD",
        start_date=datetime.now() - timedelta(days=90),  # 3 months
        end_date=datetime.now(),
        initial_capital=10000.0,
        replay_mode=ReplayMode.BAR_BY_BAR,
        timeframe="M15",
        commission_per_lot=7.0
    )
    
    # Create backtesting engine
    engine = BacktestingEngine(warehouse, config)
    
    # Define strategy parameters
    strategy_params = {
        'strategy_name': 'RSI_MeanReversion',
        'rsi_period': 14,
        'oversold': 30,
        'overbought': 70,
        'position_size': 0.01
    }
    
    # Create strategy function with parameters
    def strategy_func(data, step):
        return rsi_strategy(
            data, step,
            rsi_period=strategy_params['rsi_period'],
            oversold=strategy_params['oversold'],
            overbought=strategy_params['overbought']
        )
    
    # Run backtest
    result = engine.run_backtest(strategy_func, strategy_params)
    
    # Save results
    results_dir = engine.save_backtest_results(result, save_to_registry=True)
    
    log.info(f"\nBacktest completed!")
    log.info(f"Results saved to: {results_dir}")
    log.info(f"\nPerformance Summary:")
    log.info(f"  Total Return: {result.total_return*100:.2f}%")
    log.info(f"  Sharpe Ratio: {result.sharpe_ratio:.2f}")
    log.info(f"  Sortino Ratio: {result.sortino_ratio:.2f}")
    log.info(f"  Max Drawdown: {result.max_drawdown*100:.2f}%")
    log.info(f"  Win Rate: {result.win_rate*100:.2f}%")
    log.info(f"  Profit Factor: {result.profit_factor:.2f}")
    log.info(f"  Number of Trades: {result.num_trades}")
    log.info(f"  Avg Trade P&L: ${result.avg_trade_pnl:.2f}")
    
    return result


def compare_strategies():
    """Compare multiple strategy variants"""
    log.info("=" * 60)
    log.info("Comparing Multiple Strategy Variants")
    log.info("=" * 60)
    
    results = []
    
    # Test different MA periods
    for fast, slow in [(10, 30), (20, 50), (30, 100)]:
        log.info(f"\nTesting MA({fast},{slow})...")
        
        warehouse = HistoricalDataWarehouse()
        config = BacktestConfig(
            symbol="XAUUSD",
            start_date=datetime.now() - timedelta(days=180),
            end_date=datetime.now(),
            initial_capital=10000.0,
            replay_mode=ReplayMode.BAR_BY_BAR,
            timeframe="M15"
        )
        
        engine = BacktestingEngine(warehouse, config)
        
        strategy_params = {
            'strategy_name': f'MA_Crossover_{fast}_{slow}',
            'fast_period': fast,
            'slow_period': slow,
            'position_size': 0.01
        }
        
        def strategy_func(data, step):
            return simple_moving_average_strategy(data, step, fast, slow)
        
        result = engine.run_backtest(strategy_func, strategy_params)
        results.append((f"MA({fast},{slow})", result))
    
    # Print comparison
    log.info("\n" + "=" * 60)
    log.info("Strategy Comparison Results")
    log.info("=" * 60)
    log.info(f"{'Strategy':<20} {'Return':<10} {'Sharpe':<10} {'Max DD':<10} {'Trades':<10}")
    log.info("-" * 60)
    
    for name, result in results:
        log.info(f"{name:<20} {result.total_return*100:>8.2f}% "
                f"{result.sharpe_ratio:>9.2f} "
                f"{result.max_drawdown*100:>8.2f}% "
                f"{result.num_trades:>9}")
    
    return results


if __name__ == "__main__":
    # Run individual backtests
    ma_result = run_ma_crossover_backtest()
    print("\n")
    rsi_result = run_rsi_backtest()
    print("\n")
    
    # Compare strategies
    comparison_results = compare_strategies()
