"""
Unit tests for RL training pipeline.

Tests the trading environment, PPO agent training, and evaluation components.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import shutil

from ml.rl_training_environment import TradingEnvironment, TradeRecord
from ml.ppo_agent_training import PPOAgentTrainer, PPOConfig, AgentMetrics
from ml.rl_agent_evaluation import RLAgentEvaluator, EvaluationResult
from data.historical_data_warehouse import HistoricalDataWarehouse
from data.feature_pipeline import FeaturePipeline
from data.event_bus import EventBus


class MockRedis:
    """Mock Redis client for testing"""
    async def get(self, key):
        return None
    
    async def set(self, key, value, ex=None):
        pass
    
    async def setex(self, key, time, value):
        pass


@pytest.fixture
def warehouse():
    """Create test warehouse with sample data"""
    with tempfile.TemporaryDirectory() as tmpdir:
        warehouse = HistoricalDataWarehouse(
            db_path=f"{tmpdir}/test.duckdb",
            parquet_root=f"{tmpdir}/parquet"
        )
        
        # Create sample OHLCV data
        dates = pd.date_range(
            start=datetime.now() - timedelta(days=90),
            end=datetime.now(),
            freq='15min'
        )
        
        sample_data = pd.DataFrame({
            'timestamp': dates,
            'open': 2000 + np.random.randn(len(dates)) * 10,
            'high': 2005 + np.random.randn(len(dates)) * 10,
            'low': 1995 + np.random.randn(len(dates)) * 10,
            'close': 2000 + np.random.randn(len(dates)) * 10,
            'volume': np.random.randint(100, 1000, len(dates))
        })
        
        # Store data
        warehouse.store_ohlcv("XAUUSD", "M15", sample_data)
        
        yield warehouse


@pytest.fixture
def feature_pipeline():
    """Create test feature pipeline"""
    event_bus = EventBus()
    redis_client = MockRedis()
    
    pipeline = FeaturePipeline(
        event_bus=event_bus,
        redis_client=redis_client,
        symbols=["XAUUSD"],
        timeframes=["M15"]
    )
    
    return pipeline


@pytest.fixture
def temp_models_dir():
    """Create temporary models directory"""
    tmpdir = tempfile.mkdtemp()
    yield Path(tmpdir)
    shutil.rmtree(tmpdir)


def test_trading_environment_creation(warehouse, feature_pipeline):
    """Test creating a trading environment"""
    env = TradingEnvironment(
        warehouse=warehouse,
        feature_pipeline=feature_pipeline,
        symbol="XAUUSD",
        timeframe="M15",
        start_date=datetime.now() - timedelta(days=60),
        end_date=datetime.now() - timedelta(days=30),
        initial_capital=10000.0,
        max_position_size=0.02
    )
    
    assert env is not None
    assert env.symbol == "XAUUSD"
    assert env.timeframe == "M15"
    assert env.initial_capital == 10000.0
    assert env.max_position_size == 0.02
    assert len(env.historical_data) > 0
    assert len(env.features_data) > 0


def test_trading_environment_reset(warehouse, feature_pipeline):
    """Test environment reset"""
    env = TradingEnvironment(
        warehouse=warehouse,
        feature_pipeline=feature_pipeline,
        symbol="XAUUSD",
        timeframe="M15",
        start_date=datetime.now() - timedelta(days=60),
        end_date=datetime.now() - timedelta(days=30),
        initial_capital=10000.0,
        max_position_size=0.02
    )
    
    obs, info = env.reset()
    
    assert obs is not None
    assert obs.shape == env.observation_space.shape
    assert info['capital'] == 10000.0
    assert info['position'] == 0.0
    assert info['step'] == 0


def test_trading_environment_step(warehouse, feature_pipeline):
    """Test environment step"""
    env = TradingEnvironment(
        warehouse=warehouse,
        feature_pipeline=feature_pipeline,
        symbol="XAUUSD",
        timeframe="M15",
        start_date=datetime.now() - timedelta(days=60),
        end_date=datetime.now() - timedelta(days=30),
        initial_capital=10000.0,
        max_position_size=0.02
    )
    
    obs, info = env.reset()
    
    # Take a step with 1% position size
    action = np.array([0.01], dtype=np.float32)
    obs, reward, terminated, truncated, info = env.step(action)
    
    assert obs is not None
    assert isinstance(reward, float)
    assert isinstance(terminated, bool)
    assert isinstance(truncated, bool)
    assert 'capital' in info
    assert 'position' in info


def test_position_size_constraint(warehouse, feature_pipeline):
    """Test that position size is constrained to max 2%"""
    env = TradingEnvironment(
        warehouse=warehouse,
        feature_pipeline=feature_pipeline,
        symbol="XAUUSD",
        timeframe="M15",
        start_date=datetime.now() - timedelta(days=60),
        end_date=datetime.now() - timedelta(days=30),
        initial_capital=10000.0,
        max_position_size=0.02
    )
    
    obs, info = env.reset()
    
    # Try to take action with 5% position size (should be clipped to 2%)
    action = np.array([0.05], dtype=np.float32)
    obs, reward, terminated, truncated, info = env.step(action)
    
    # Position should be clipped to max 2%
    assert info['position'] <= 0.02


def test_reward_calculation(warehouse, feature_pipeline):
    """Test Sharpe ratio reward calculation"""
    env = TradingEnvironment(
        warehouse=warehouse,
        feature_pipeline=feature_pipeline,
        symbol="XAUUSD",
        timeframe="M15",
        start_date=datetime.now() - timedelta(days=60),
        end_date=datetime.now() - timedelta(days=30),
        initial_capital=10000.0,
        max_position_size=0.02,
        reward_window=100
    )
    
    # Create some sample trades
    for i in range(20):
        trade = TradeRecord(
            entry_time=datetime.now(),
            exit_time=datetime.now(),
            entry_price=2000.0,
            exit_price=2010.0 if i % 2 == 0 else 1990.0,  # Alternating wins/losses
            position_size=0.01,
            pnl=100.0 if i % 2 == 0 else -100.0,
            capital=10000.0
        )
        env.trade_history.append(trade)
    
    # Calculate reward
    reward = env._calculate_reward()
    
    # Should return a Sharpe ratio (can be positive or negative)
    assert isinstance(reward, float)
    assert not np.isnan(reward)


def test_trade_statistics(warehouse, feature_pipeline):
    """Test trade statistics calculation"""
    env = TradingEnvironment(
        warehouse=warehouse,
        feature_pipeline=feature_pipeline,
        symbol="XAUUSD",
        timeframe="M15",
        start_date=datetime.now() - timedelta(days=60),
        end_date=datetime.now() - timedelta(days=30),
        initial_capital=10000.0,
        max_position_size=0.02
    )
    
    # Run a short episode
    obs, info = env.reset()
    done = False
    steps = 0
    
    while not done and steps < 50:
        action = env.action_space.sample()
        obs, reward, terminated, truncated, info = env.step(action)
        done = terminated or truncated
        steps += 1
    
    # Get statistics
    stats = env.get_trade_statistics()
    
    assert 'num_trades' in stats
    assert 'total_pnl' in stats
    assert 'avg_pnl' in stats
    assert 'win_rate' in stats
    assert 'sharpe_ratio' in stats
    assert 'max_drawdown' in stats
    assert 'final_capital' in stats
    assert 'total_return' in stats


def test_agent_metrics():
    """Test AgentMetrics dataclass"""
    metrics = AgentMetrics(
        sharpe_ratio=1.8,
        total_return=0.15,
        num_trades=100,
        win_rate=0.60,
        avg_pnl=15.0,
        max_drawdown=0.08
    )
    
    # Should meet promotion criteria (Sharpe > 1.5)
    assert metrics.meets_promotion_criteria(1.5) == True
    
    # Should not meet higher criteria
    assert metrics.meets_promotion_criteria(2.0) == False


def test_ppo_config():
    """Test PPOConfig dataclass"""
    config = PPOConfig(
        symbol="XAUUSD",
        timeframe="M15",
        training_months=6,
        max_position_size=0.02,
        total_timesteps=1000,
        min_sharpe_for_promotion=1.5
    )
    
    assert config.symbol == "XAUUSD"
    assert config.timeframe == "M15"
    assert config.training_months == 6
    assert config.max_position_size == 0.02
    assert config.total_timesteps == 1000
    assert config.min_sharpe_for_promotion == 1.5


def test_evaluator_creation(warehouse, feature_pipeline, temp_models_dir):
    """Test creating an RL agent evaluator"""
    evaluator = RLAgentEvaluator(
        warehouse=warehouse,
        feature_pipeline=feature_pipeline,
        models_dir=str(temp_models_dir),
        min_sharpe_for_promotion=1.5
    )
    
    assert evaluator is not None
    assert evaluator.min_sharpe_for_promotion == 1.5
    assert len(evaluator.evaluation_history) == 0


def test_evaluation_result():
    """Test EvaluationResult dataclass"""
    metrics = AgentMetrics(
        sharpe_ratio=1.8,
        total_return=0.15,
        num_trades=100,
        win_rate=0.60,
        avg_pnl=15.0,
        max_drawdown=0.08
    )
    
    result = EvaluationResult(
        agent_id="test_agent",
        symbol="XAUUSD",
        evaluation_date=datetime.now(),
        eval_start_date=datetime.now() - timedelta(days=30),
        eval_end_date=datetime.now(),
        metrics=metrics,
        promotion_eligible=True,
        promotion_reason="Sharpe > 1.5",
        detailed_stats={}
    )
    
    assert result.agent_id == "test_agent"
    assert result.symbol == "XAUUSD"
    assert result.promotion_eligible == True
    assert result.metrics.sharpe_ratio == 1.8


def test_feature_extraction(warehouse, feature_pipeline):
    """Test feature extraction from historical data"""
    env = TradingEnvironment(
        warehouse=warehouse,
        feature_pipeline=feature_pipeline,
        symbol="XAUUSD",
        timeframe="M15",
        start_date=datetime.now() - timedelta(days=60),
        end_date=datetime.now() - timedelta(days=30),
        initial_capital=10000.0,
        max_position_size=0.02
    )
    
    # Get a window of data
    window_data = env.historical_data.iloc[:50]
    
    # Extract features
    features = env._extract_features(window_data)
    
    assert features is not None
    assert isinstance(features, dict)
    assert len(features) > 0
    
    # Check for expected features
    assert 'return_1bar' in features or 'rsi_14' in features or 'ema_20' in features


def test_pnl_calculation(warehouse, feature_pipeline):
    """Test P&L calculation"""
    env = TradingEnvironment(
        warehouse=warehouse,
        feature_pipeline=feature_pipeline,
        symbol="XAUUSD",
        timeframe="M15",
        start_date=datetime.now() - timedelta(days=60),
        end_date=datetime.now() - timedelta(days=30),
        initial_capital=10000.0,
        max_position_size=0.02
    )
    
    # Test profitable trade
    pnl = env._calculate_pnl(
        entry_price=2000.0,
        exit_price=2020.0,  # 1% gain
        position_size=0.01  # 1% of capital
    )
    
    # Should be approximately 1% of 1% of capital = 1.0
    assert pnl > 0
    assert abs(pnl - 1.0) < 0.1
    
    # Test losing trade
    pnl = env._calculate_pnl(
        entry_price=2000.0,
        exit_price=1980.0,  # 1% loss
        position_size=0.01
    )
    
    assert pnl < 0
    assert abs(pnl + 1.0) < 0.1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
