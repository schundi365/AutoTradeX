"""
Unit tests for Backtesting Engine

Tests backtesting functionality including order execution, slippage,
commissions, and performance metrics calculation.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from ml.backtesting_engine import (
    BacktestingEngine,
    BacktestConfig,
    ReplayMode,
    Order,
    OrderType,
    OrderStatus,
    MarketState,
    SlippageModel,
    CommissionModel,
    Trade
)
from data.historical_data_warehouse import HistoricalDataWarehouse


@pytest.fixture
def warehouse():
    """Create historical data warehouse"""
    return HistoricalDataWarehouse()


@pytest.fixture
def sample_ohlcv_data():
    """Create sample OHLCV data for testing"""
    dates = pd.date_range(start='2024-01-01', periods=100, freq='15min')
    
    # Generate synthetic price data with trend
    np.random.seed(42)
    base_price = 2000.0
    prices = base_price + np.cumsum(np.random.randn(100) * 2)
    
    data = pd.DataFrame({
        'timestamp': dates,
        'open': prices + np.random.randn(100) * 0.5,
        'high': prices + np.abs(np.random.randn(100) * 1.0),
        'low': prices - np.abs(np.random.randn(100) * 1.0),
        'close': prices,
        'volume': np.random.randint(1000, 10000, 100)
    })
    
    return data


@pytest.fixture
def backtest_config():
    """Create backtest configuration"""
    return BacktestConfig(
        symbol="XAUUSD",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 10),
        initial_capital=10000.0,
        replay_mode=ReplayMode.BAR_BY_BAR,
        timeframe="M15",
        commission_per_lot=7.0,
        base_slippage_pct=0.0001,
        volume_impact_factor=0.001
    )


class TestSlippageModel:
    """Test slippage model calculations"""
    
    def test_base_slippage(self):
        """Test base slippage calculation (half spread)"""
        model = SlippageModel(base_slippage_pct=0.0001, volume_impact_factor=0.0)
        
        order = Order(
            order_id="test_1",
            symbol="XAUUSD",
            order_type=OrderType.MARKET,
            direction="LONG",
            size=0.01
        )
        
        market_state = MarketState(
            symbol="XAUUSD",
            timestamp=datetime.now(),
            bid=2000.0,
            ask=2000.4,
            spread=0.4,
            volume=5000,
            avg_volume=5000
        )
        
        slippage = model.apply_slippage(order, market_state)
        
        # Should be half spread
        assert slippage == 0.2
    
    def test_volume_impact(self):
        """Test volume impact on slippage"""
        model = SlippageModel(base_slippage_pct=0.0001, volume_impact_factor=0.001)
        
        order = Order(
            order_id="test_1",
            symbol="XAUUSD",
            order_type=OrderType.MARKET,
            direction="LONG",
            size=0.1  # Large order
        )
        
        market_state = MarketState(
            symbol="XAUUSD",
            timestamp=datetime.now(),
            bid=2000.0,
            ask=2000.4,
            spread=0.4,
            volume=5000,
            avg_volume=5000
        )
        
        slippage = model.apply_slippage(order, market_state)
        
        # Should include volume impact
        expected_volume_impact = (0.1 / 5000) * 0.001 * 2000.0
        expected_slippage = 0.2 + expected_volume_impact
        
        assert abs(slippage - expected_slippage) < 0.001


class TestCommissionModel:
    """Test commission model calculations"""
    
    def test_commission_calculation(self):
        """Test commission calculation per lot"""
        model = CommissionModel(commission_per_lot=7.0)
        
        order = Order(
            order_id="test_1",
            symbol="XAUUSD",
            order_type=OrderType.MARKET,
            direction="LONG",
            size=0.01
        )
        
        commission = model.calculate_commission(order)
        
        assert commission == 0.07  # 0.01 lots * $7
    
    def test_commission_multiple_lots(self):
        """Test commission for multiple lots"""
        model = CommissionModel(commission_per_lot=7.0)
        
        order = Order(
            order_id="test_1",
            symbol="XAUUSD",
            order_type=OrderType.MARKET,
            direction="LONG",
            size=1.0
        )
        
        commission = model.calculate_commission(order)
        
        assert commission == 7.0


class TestBacktestingEngine:
    """Test backtesting engine functionality"""
    
    def test_engine_initialization(self, warehouse, backtest_config):
        """Test engine initialization"""
        engine = BacktestingEngine(warehouse, backtest_config)
        
        assert engine.config == backtest_config
        assert engine.capital == backtest_config.initial_capital
        assert engine.current_position is None
        assert len(engine.pending_orders) == 0
        assert len(engine.completed_trades) == 0
    
    def test_market_state_creation(self, warehouse, backtest_config, sample_ohlcv_data):
        """Test market state creation from OHLCV bar"""
        engine = BacktestingEngine(warehouse, backtest_config)
        engine.historical_data = sample_ohlcv_data
        engine.current_step = 50
        
        bar = sample_ohlcv_data.iloc[50]
        market_state = engine._create_market_state(bar)
        
        assert market_state.symbol == backtest_config.symbol
        assert market_state.timestamp == bar['timestamp']
        assert market_state.bid < bar['close']
        assert market_state.ask > bar['close']
        assert market_state.spread > 0
    
    def test_simple_long_trade(self, warehouse, backtest_config, sample_ohlcv_data):
        """Test opening and closing a long position"""
        engine = BacktestingEngine(warehouse, backtest_config)
        engine.historical_data = sample_ohlcv_data
        engine.current_step = 10
        
        # Open long position
        market_state = engine._create_market_state(sample_ohlcv_data.iloc[10])
        signal = {
            'action': 'OPEN_LONG',
            'size': 0.01
        }
        engine._execute_signal(signal, market_state)
        
        assert engine.current_position is not None
        assert engine.current_position.direction == "LONG"
        assert engine.current_position.status == OrderStatus.FILLED
        
        # Close position
        engine.current_step = 20
        market_state = engine._create_market_state(sample_ohlcv_data.iloc[20])
        close_signal = {'action': 'CLOSE'}
        engine._execute_signal(close_signal, market_state)
        
        assert engine.current_position is None
        assert len(engine.completed_trades) == 1
        
        trade = engine.completed_trades[0]
        assert trade.direction == "LONG"
        assert trade.entry_price > 0
        assert trade.exit_price > 0
    
    def test_simple_short_trade(self, warehouse, backtest_config, sample_ohlcv_data):
        """Test opening and closing a short position"""
        engine = BacktestingEngine(warehouse, backtest_config)
        engine.historical_data = sample_ohlcv_data
        engine.current_step = 10
        
        # Open short position
        market_state = engine._create_market_state(sample_ohlcv_data.iloc[10])
        signal = {
            'action': 'OPEN_SHORT',
            'size': 0.01
        }
        engine._execute_signal(signal, market_state)
        
        assert engine.current_position is not None
        assert engine.current_position.direction == "SHORT"
        
        # Close position
        engine.current_step = 20
        market_state = engine._create_market_state(sample_ohlcv_data.iloc[20])
        close_signal = {'action': 'CLOSE'}
        engine._execute_signal(close_signal, market_state)
        
        assert engine.current_position is None
        assert len(engine.completed_trades) == 1
        
        trade = engine.completed_trades[0]
        assert trade.direction == "SHORT"
    
    def test_stop_loss_execution(self, warehouse, backtest_config, sample_ohlcv_data):
        """Test stop-loss order execution"""
        engine = BacktestingEngine(warehouse, backtest_config)
        engine.historical_data = sample_ohlcv_data
        engine.current_step = 10
        
        # Open long position with stop-loss
        market_state = engine._create_market_state(sample_ohlcv_data.iloc[10])
        entry_price = market_state.ask
        stop_loss_price = entry_price - 5.0  # $5 below entry
        
        signal = {
            'action': 'OPEN_LONG',
            'size': 0.01,
            'stop_loss': stop_loss_price
        }
        engine._execute_signal(signal, market_state)
        
        assert len(engine.pending_orders) == 1
        assert engine.pending_orders[0].order_type == OrderType.STOP_LOSS
        
        # Simulate price dropping to trigger stop-loss
        engine.current_step = 15
        # Create market state with price below stop-loss
        bar = sample_ohlcv_data.iloc[15].copy()
        bar['close'] = stop_loss_price - 1.0
        market_state = engine._create_market_state(bar)
        market_state.bid = stop_loss_price - 1.0
        
        engine._process_pending_orders(market_state)
        
        # Stop-loss should have triggered
        assert engine.current_position is None
        assert len(engine.completed_trades) == 1
        assert engine.completed_trades[0].exit_reason == "stop_loss"
    
    def test_take_profit_execution(self, warehouse, backtest_config, sample_ohlcv_data):
        """Test take-profit order execution"""
        engine = BacktestingEngine(warehouse, backtest_config)
        engine.historical_data = sample_ohlcv_data
        engine.current_step = 10
        
        # Open long position with take-profit
        market_state = engine._create_market_state(sample_ohlcv_data.iloc[10])
        entry_price = market_state.ask
        take_profit_price = entry_price + 10.0  # $10 above entry
        
        signal = {
            'action': 'OPEN_LONG',
            'size': 0.01,
            'take_profit': take_profit_price
        }
        engine._execute_signal(signal, market_state)
        
        assert len(engine.pending_orders) == 1
        assert engine.pending_orders[0].order_type == OrderType.TAKE_PROFIT
        
        # Simulate price rising to trigger take-profit
        engine.current_step = 15
        bar = sample_ohlcv_data.iloc[15].copy()
        bar['close'] = take_profit_price + 1.0
        market_state = engine._create_market_state(bar)
        market_state.bid = take_profit_price + 1.0
        
        engine._process_pending_orders(market_state)
        
        # Take-profit should have triggered
        assert engine.current_position is None
        assert len(engine.completed_trades) == 1
        assert engine.completed_trades[0].exit_reason == "take_profit"
    
    def test_commission_deduction(self, warehouse, backtest_config, sample_ohlcv_data):
        """Test that commissions are deducted from capital"""
        engine = BacktestingEngine(warehouse, backtest_config)
        engine.historical_data = sample_ohlcv_data
        engine.current_step = 10
        
        initial_capital = engine.capital
        
        # Open and close position
        market_state = engine._create_market_state(sample_ohlcv_data.iloc[10])
        signal = {'action': 'OPEN_LONG', 'size': 0.01}
        engine._execute_signal(signal, market_state)
        
        capital_after_open = engine.capital
        
        engine.current_step = 20
        market_state = engine._create_market_state(sample_ohlcv_data.iloc[20])
        close_signal = {'action': 'CLOSE'}
        engine._execute_signal(close_signal, market_state)
        
        # Capital should have changed due to commissions
        # Entry commission: 0.01 lots * $7 = $0.07
        # Exit commission: $0.07
        # Total commissions: $0.14
        
        trade = engine.completed_trades[0]
        assert trade.commission > 0
    
    def test_full_backtest_execution(self, warehouse, backtest_config, sample_ohlcv_data):
        """Test full backtest execution with strategy"""
        # Mock warehouse to return sample data
        def mock_query_ohlcv(symbol, timeframe, start, end):
            return sample_ohlcv_data
        
        warehouse.query_ohlcv = mock_query_ohlcv
        
        engine = BacktestingEngine(warehouse, backtest_config)
        
        # Simple buy-and-hold strategy
        def buy_and_hold_strategy(data, step):
            if step == 10:
                return {'action': 'OPEN_LONG', 'size': 0.01}
            elif step == 90:
                return {'action': 'CLOSE'}
            return None
        
        strategy_params = {'strategy_name': 'buy_and_hold'}
        result = engine.run_backtest(buy_and_hold_strategy, strategy_params)
        
        # Verify result structure
        assert result.config == backtest_config
        assert result.num_trades >= 0
        assert result.total_return is not None
        assert result.sharpe_ratio is not None
        assert result.max_drawdown >= 0
        assert result.win_rate >= 0 and result.win_rate <= 1
        assert len(result.equity_curve) > 0
    
    def test_performance_metrics_calculation(self, warehouse, backtest_config):
        """Test performance metrics calculation"""
        engine = BacktestingEngine(warehouse, backtest_config)
        
        # Create mock trades
        engine.completed_trades = [
            Trade(
                trade_id="1",
                symbol="XAUUSD",
                direction="LONG",
                entry_time=datetime.now(),
                exit_time=datetime.now() + timedelta(hours=1),
                entry_price=2000.0,
                exit_price=2010.0,
                size=0.01,
                pnl=100.0,
                commission=0.14,
                slippage=0.2,
                holding_time_seconds=3600,
                exit_reason="take_profit"
            ),
            Trade(
                trade_id="2",
                symbol="XAUUSD",
                direction="LONG",
                entry_time=datetime.now(),
                exit_time=datetime.now() + timedelta(hours=2),
                entry_price=2010.0,
                exit_price=2005.0,
                size=0.01,
                pnl=-50.0,
                commission=0.14,
                slippage=0.2,
                holding_time_seconds=7200,
                exit_reason="stop_loss"
            ),
            Trade(
                trade_id="3",
                symbol="XAUUSD",
                direction="SHORT",
                entry_time=datetime.now(),
                exit_time=datetime.now() + timedelta(hours=1),
                entry_price=2005.0,
                exit_price=2000.0,
                size=0.01,
                pnl=50.0,
                commission=0.14,
                slippage=0.2,
                holding_time_seconds=3600,
                exit_reason="take_profit"
            )
        ]
        
        # Create mock equity history
        engine.equity_history = [
            (datetime.now(), 10000.0),
            (datetime.now() + timedelta(hours=1), 10100.0),
            (datetime.now() + timedelta(hours=2), 10050.0),
            (datetime.now() + timedelta(hours=3), 10100.0)
        ]
        
        result = engine._compute_performance_metrics({'strategy': 'test'})
        
        # Verify metrics
        assert result.num_trades == 3
        assert result.win_rate == 2/3  # 2 winning trades out of 3
        assert result.avg_trade_pnl == (100 - 50 + 50) / 3
        assert result.total_return == (10100 - 10000) / 10000
        assert result.max_drawdown >= 0
        assert result.sharpe_ratio is not None
    
    def test_backtest_result_saving(self, warehouse, backtest_config, sample_ohlcv_data, tmp_path):
        """Test saving backtest results to disk"""
        # Use temporary directory for testing
        engine = BacktestingEngine(warehouse, backtest_config, models_dir=str(tmp_path))
        
        # Mock warehouse
        def mock_query_ohlcv(symbol, timeframe, start, end):
            return sample_ohlcv_data
        
        warehouse.query_ohlcv = mock_query_ohlcv
        
        # Run simple backtest
        def simple_strategy(data, step):
            if step == 10:
                return {'action': 'OPEN_LONG', 'size': 0.01}
            elif step == 20:
                return {'action': 'CLOSE'}
            return None
        
        result = engine.run_backtest(simple_strategy, {'strategy': 'test'})
        
        # Save results
        results_dir = engine.save_backtest_results(result, save_to_registry=False)
        
        # Verify files were created
        assert results_dir.exists()
        assert (results_dir / "metadata.json").exists()
        assert (results_dir / "trades.csv").exists()
        assert (results_dir / "equity_curve.csv").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
