"""
Example usage of RL training pipeline.

This script demonstrates how to:
1. Create a training environment with historical data
2. Train a PPO agent for position sizing
3. Evaluate the agent on out-of-sample data
4. Promote the agent to paper trading if it meets criteria
"""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from ml.rl_training_environment import TradingEnvironment
from ml.ppo_agent_training import PPOAgentTrainer, PPOConfig
from ml.rl_agent_evaluation import RLAgentEvaluator
from data.historical_data_warehouse import HistoricalDataWarehouse
from data.feature_pipeline import FeaturePipeline
from data.event_bus import EventBus
from core.logger import get_agent_logger

log = get_agent_logger("RL_EXAMPLE")


async def example_rl_training():
    """
    Example: Train and evaluate an RL agent for position sizing.
    """
    log.info("=" * 80)
    log.info("RL AGENT TRAINING EXAMPLE")
    log.info("=" * 80)
    
    # Initialize components
    warehouse = HistoricalDataWarehouse()
    event_bus = EventBus()
    
    # Note: In production, you would use a real Redis client
    # For this example, we'll use a mock
    class MockRedis:
        async def get(self, key): return None
        async def set(self, key, value, ex=None): pass
        async def setex(self, key, time, value): pass
    
    redis_client = MockRedis()
    
    feature_pipeline = FeaturePipeline(
        event_bus=event_bus,
        redis_client=redis_client,
        symbols=["XAUUSD"],
        timeframes=["M15"]
    )
    
    # Create trainer
    trainer = PPOAgentTrainer(
        warehouse=warehouse,
        feature_pipeline=feature_pipeline,
        models_dir="models/reinforcement"
    )
    
    # Configure training
    config = PPOConfig(
        symbol="XAUUSD",
        timeframe="M15",
        training_months=6,
        initial_capital=10000.0,
        max_position_size=0.02,  # 2% max
        trade_cost=0.0001,  # 0.01% per trade
        reward_window=100,
        total_timesteps=1_000_000,  # 1M timesteps
        min_sharpe_for_promotion=1.5
    )
    
    log.info("\nTraining Configuration:")
    log.info(f"  Symbol: {config.symbol}")
    log.info(f"  Timeframe: {config.timeframe}")
    log.info(f"  Training months: {config.training_months}")
    log.info(f"  Max position size: {config.max_position_size * 100}%")
    log.info(f"  Total timesteps: {config.total_timesteps:,}")
    log.info(f"  Min Sharpe for promotion: {config.min_sharpe_for_promotion}")
    
    # Train agent
    log.info("\n" + "=" * 80)
    log.info("TRAINING AGENT")
    log.info("=" * 80)
    
    agent, metrics, metadata = trainer.train_agent(config)
    
    # Save agent
    log.info("\n" + "=" * 80)
    log.info("SAVING AGENT")
    log.info("=" * 80)
    
    model_dir = trainer.save_agent(agent, metadata)
    log.info(f"Agent saved to: {model_dir}")
    
    # Evaluate agent
    log.info("\n" + "=" * 80)
    log.info("EVALUATING AGENT")
    log.info("=" * 80)
    
    evaluator = RLAgentEvaluator(
        warehouse=warehouse,
        feature_pipeline=feature_pipeline,
        models_dir="models/reinforcement",
        min_sharpe_for_promotion=config.min_sharpe_for_promotion
    )
    
    agent_id = model_dir.name
    
    evaluation_result = evaluator.evaluate_agent_comprehensive(
        agent=agent,
        agent_id=agent_id,
        symbol=config.symbol,
        timeframe=config.timeframe,
        initial_capital=config.initial_capital,
        max_position_size=config.max_position_size,
        trade_cost=config.trade_cost,
        reward_window=config.reward_window
    )
    
    # Generate evaluation report
    report_path = model_dir / "evaluation_report.txt"
    report = evaluator.generate_evaluation_report(evaluation_result, report_path)
    print("\n" + report)
    
    # Promote to paper trading if eligible
    log.info("\n" + "=" * 80)
    log.info("PROMOTION DECISION")
    log.info("=" * 80)
    
    if evaluation_result.promotion_eligible:
        promoted = evaluator.promote_to_paper_trading(
            agent=agent,
            agent_id=agent_id,
            evaluation_result=evaluation_result,
            model_dir=model_dir
        )
        
        if promoted:
            log.info("✓ Agent promoted to paper trading!")
        else:
            log.warning("✗ Promotion failed")
    else:
        log.warning("✗ Agent not eligible for promotion")
        log.warning(f"Reason: {evaluation_result.promotion_reason}")
    
    log.info("\n" + "=" * 80)
    log.info("EXAMPLE COMPLETE")
    log.info("=" * 80)


async def example_environment_test():
    """
    Example: Test the trading environment with random actions.
    """
    log.info("=" * 80)
    log.info("TRADING ENVIRONMENT TEST")
    log.info("=" * 80)
    
    # Initialize components
    warehouse = HistoricalDataWarehouse()
    event_bus = EventBus()
    
    class MockRedis:
        async def get(self, key): return None
        async def set(self, key, value, ex=None): pass
    
    redis_client = MockRedis()
    
    feature_pipeline = FeaturePipeline(
        event_bus=event_bus,
        redis_client=redis_client,
        symbols=["XAUUSD"],
        timeframes=["M15"]
    )
    
    # Create environment
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
    
    log.info(f"Environment created:")
    log.info(f"  Observation space: {env.observation_space}")
    log.info(f"  Action space: {env.action_space}")
    log.info(f"  Historical data: {len(env.historical_data)} bars")
    
    # Run episode with random actions
    log.info("\nRunning episode with random actions...")
    
    obs, info = env.reset()
    done = False
    step_count = 0
    
    while not done and step_count < 100:  # Limit to 100 steps for demo
        # Random action
        action = env.action_space.sample()
        
        obs, reward, terminated, truncated, info = env.step(action)
        done = terminated or truncated
        step_count += 1
        
        if step_count % 20 == 0:
            log.info(f"Step {step_count}: Capital={info['capital']:.2f}, "
                    f"Position={info['position']:.4f}, Trades={info['num_trades']}")
    
    # Get final statistics
    stats = env.get_trade_statistics()
    
    log.info("\nFinal Statistics:")
    log.info(f"  Number of trades: {stats['num_trades']}")
    log.info(f"  Total P&L: {stats['total_pnl']:.2f}")
    log.info(f"  Average P&L: {stats['avg_pnl']:.2f}")
    log.info(f"  Win rate: {stats['win_rate']:.2%}")
    log.info(f"  Sharpe ratio: {stats['sharpe_ratio']:.3f}")
    log.info(f"  Max drawdown: {stats['max_drawdown']:.2%}")
    log.info(f"  Final capital: {stats['final_capital']:.2f}")
    log.info(f"  Total return: {stats['total_return']:.2%}")
    
    log.info("\n" + "=" * 80)
    log.info("TEST COMPLETE")
    log.info("=" * 80)


if __name__ == "__main__":
    # Run environment test
    print("\n" + "=" * 80)
    print("RUNNING ENVIRONMENT TEST")
    print("=" * 80 + "\n")
    asyncio.run(example_environment_test())
    
    # Uncomment to run full training (takes time)
    # print("\n" + "=" * 80)
    # print("RUNNING FULL TRAINING")
    # print("=" * 80 + "\n")
    # asyncio.run(example_rl_training())
