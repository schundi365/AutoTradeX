"""
PPO Agent Training for Position Sizing

Implements PPO (Proximal Policy Optimization) agent training using Stable-Baselines3.
Trains agents to learn optimal position sizing for maximizing risk-adjusted returns.

Requirements: 12.2, 12.4
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from pathlib import Path
import joblib
import json

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback, EvalCallback
from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.monitor import Monitor

from ml.rl_training_environment import TradingEnvironment
from data.historical_data_warehouse import HistoricalDataWarehouse
from data.feature_pipeline import FeaturePipeline
from core.logger import get_agent_logger

log = get_agent_logger("PPO_TRAINING")


@dataclass
class PPOConfig:
    """Configuration for PPO agent training"""
    symbol: str
    timeframe: str = "M15"
    training_months: int = 6
    initial_capital: float = 10000.0
    max_position_size: float = 0.02  # 2% max per trade
    trade_cost: float = 0.0001  # 0.01% per trade
    reward_window: int = 100  # Rolling window for Sharpe calculation
    
    # PPO hyperparameters
    learning_rate: float = 3e-4
    n_steps: int = 2048
    batch_size: int = 64
    n_epochs: int = 10
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_range: float = 0.2
    ent_coef: float = 0.01
    
    # Training parameters
    total_timesteps: int = 1_000_000  # 1M timesteps
    eval_freq: int = 10_000
    min_sharpe_for_promotion: float = 1.5  # Minimum Sharpe for paper trading


@dataclass
class AgentMetrics:
    """Performance metrics for trained agent"""
    sharpe_ratio: float
    total_return: float
    num_trades: int
    win_rate: float
    avg_pnl: float
    max_drawdown: float
    
    def meets_promotion_criteria(self, min_sharpe: float = 1.5) -> bool:
        """
        Check if agent meets criteria for promotion to paper trading.
        
        Requirements: 12.5 - Promote to paper trading if Sharpe > 1.5
        """
        return self.sharpe_ratio > min_sharpe


class TradingCallback(BaseCallback):
    """
    Custom callback for monitoring training progress.
    Logs metrics and saves best models.
    """
    
    def __init__(self, eval_env: TradingEnvironment, eval_freq: int = 10000, verbose: int = 1):
        super().__init__(verbose)
        self.eval_env = eval_env
        self.eval_freq = eval_freq
        self.best_sharpe = -np.inf
        self.eval_count = 0
    
    def _on_step(self) -> bool:
        """Called after each step"""
        # Evaluate periodically
        if self.n_calls % self.eval_freq == 0:
            self.eval_count += 1
            
            # Run evaluation episode
            obs, _ = self.eval_env.reset()
            done = False
            
            while not done:
                action, _ = self.model.predict(obs, deterministic=True)
                obs, reward, terminated, truncated, info = self.eval_env.step(action)
                done = terminated or truncated
            
            # Get statistics
            stats = self.eval_env.get_trade_statistics()
            sharpe = stats['sharpe_ratio']
            
            log.info(f"Evaluation {self.eval_count}: Sharpe={sharpe:.3f}, "
                    f"Return={stats['total_return']:.2%}, "
                    f"Trades={stats['num_trades']}, "
                    f"WinRate={stats['win_rate']:.2%}")
            
            # Track best model
            if sharpe > self.best_sharpe:
                self.best_sharpe = sharpe
                log.info(f"New best Sharpe ratio: {sharpe:.3f}")
        
        return True


class PPOAgentTrainer:
    """
    PPO agent trainer for position sizing.
    
    Features:
    - Trains PPO agent with Stable-Baselines3
    - Uses TradingEnvironment with historical data
    - Implements reward function as Sharpe ratio
    - Constrains position sizes to risk management rules
    - Evaluates on out-of-sample data
    - Promotes to paper trading if Sharpe > 1.5
    
    Requirements: 12.1, 12.2, 12.4, 12.5
    """
    
    def __init__(
        self,
        warehouse: HistoricalDataWarehouse,
        feature_pipeline: Optional[FeaturePipeline] = None,
        models_dir: str = "models/reinforcement"
    ):
        self.warehouse = warehouse
        self.feature_pipeline = feature_pipeline
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        log.info("PPO Agent Trainer initialized")
        log.info(f"Models directory: {self.models_dir}")
    
    def create_training_environment(
        self,
        config: PPOConfig,
        start_date: datetime,
        end_date: datetime
    ) -> TradingEnvironment:
        """
        Create training environment with historical data.
        
        Args:
            config: Training configuration
            start_date: Start date for training data
            end_date: End date for training data
        
        Returns:
            TradingEnvironment instance
        """
        env = TradingEnvironment(
            warehouse=self.warehouse,
            feature_pipeline=self.feature_pipeline,
            symbol=config.symbol,
            timeframe=config.timeframe,
            start_date=start_date,
            end_date=end_date,
            initial_capital=config.initial_capital,
            max_position_size=config.max_position_size,
            trade_cost=config.trade_cost,
            reward_window=config.reward_window
        )
        
        return env
    
    def train_agent(
        self,
        config: PPOConfig,
        train_start: Optional[datetime] = None,
        train_end: Optional[datetime] = None,
        eval_start: Optional[datetime] = None,
        eval_end: Optional[datetime] = None
    ) -> Tuple[PPO, AgentMetrics, Dict[str, Any]]:
        """
        Train PPO agent with specified configuration.
        
        Requirements: 12.2, 12.4
        
        Args:
            config: Training configuration
            train_start: Training data start date (default: 6 months ago)
            train_end: Training data end date (default: 1 month ago)
            eval_start: Evaluation data start date (default: 1 month ago)
            eval_end: Evaluation data end date (default: now)
        
        Returns:
            Tuple of (trained_agent, metrics, metadata)
        """
        log.info(f"Starting PPO agent training for {config.symbol}")
        
        # Set default date ranges
        now = datetime.now()
        if train_start is None:
            train_start = now - timedelta(days=config.training_months * 30)
        if train_end is None:
            train_end = now - timedelta(days=30)  # Leave 1 month for evaluation
        if eval_start is None:
            eval_start = train_end
        if eval_end is None:
            eval_end = now
        
        log.info(f"Training period: {train_start} to {train_end}")
        log.info(f"Evaluation period: {eval_start} to {eval_end}")
        
        # Create training environment
        train_env = self.create_training_environment(config, train_start, train_end)
        train_env = Monitor(train_env)  # Wrap with Monitor for logging
        train_env = DummyVecEnv([lambda: train_env])  # Vectorize environment
        
        # Create evaluation environment
        eval_env = self.create_training_environment(config, eval_start, eval_end)
        
        # Create PPO agent
        log.info("Creating PPO agent with hyperparameters:")
        log.info(f"  learning_rate: {config.learning_rate}")
        log.info(f"  n_steps: {config.n_steps}")
        log.info(f"  batch_size: {config.batch_size}")
        log.info(f"  n_epochs: {config.n_epochs}")
        log.info(f"  gamma: {config.gamma}")
        log.info(f"  gae_lambda: {config.gae_lambda}")
        log.info(f"  clip_range: {config.clip_range}")
        log.info(f"  ent_coef: {config.ent_coef}")
        
        agent = PPO(
            policy="MlpPolicy",
            env=train_env,
            learning_rate=config.learning_rate,
            n_steps=config.n_steps,
            batch_size=config.batch_size,
            n_epochs=config.n_epochs,
            gamma=config.gamma,
            gae_lambda=config.gae_lambda,
            clip_range=config.clip_range,
            ent_coef=config.ent_coef,
            verbose=1,
            tensorboard_log=str(self.models_dir / "tensorboard")
        )
        
        # Create callback for monitoring
        callback = TradingCallback(eval_env=eval_env, eval_freq=config.eval_freq)
        
        # Train agent
        log.info(f"Training agent for {config.total_timesteps} timesteps...")
        agent.learn(
            total_timesteps=config.total_timesteps,
            callback=callback,
            progress_bar=True
        )
        
        log.info("Training complete")
        
        # Evaluate on out-of-sample data
        log.info("Evaluating agent on out-of-sample data...")
        metrics = self.evaluate_agent(agent, eval_env)
        
        log.info(f"Evaluation metrics:")
        log.info(f"  Sharpe ratio: {metrics.sharpe_ratio:.3f}")
        log.info(f"  Total return: {metrics.total_return:.2%}")
        log.info(f"  Number of trades: {metrics.num_trades}")
        log.info(f"  Win rate: {metrics.win_rate:.2%}")
        log.info(f"  Average P&L: {metrics.avg_pnl:.2f}")
        log.info(f"  Max drawdown: {metrics.max_drawdown:.2%}")
        
        # Check promotion criteria
        if metrics.meets_promotion_criteria(config.min_sharpe_for_promotion):
            log.info(f"✓ Agent meets promotion criteria (Sharpe {metrics.sharpe_ratio:.3f} > {config.min_sharpe_for_promotion})")
            promotion_status = "ELIGIBLE_FOR_PAPER_TRADING"
        else:
            log.warning(f"✗ Agent does not meet promotion criteria (Sharpe {metrics.sharpe_ratio:.3f} <= {config.min_sharpe_for_promotion})")
            promotion_status = "REJECTED"
        
        # Prepare metadata
        metadata = {
            'model_type': 'PPO',
            'symbol': config.symbol,
            'timeframe': config.timeframe,
            'training_months': config.training_months,
            'train_start_date': train_start.isoformat(),
            'train_end_date': train_end.isoformat(),
            'eval_start_date': eval_start.isoformat(),
            'eval_end_date': eval_end.isoformat(),
            'hyperparameters': {
                'learning_rate': config.learning_rate,
                'n_steps': config.n_steps,
                'batch_size': config.batch_size,
                'n_epochs': config.n_epochs,
                'gamma': config.gamma,
                'gae_lambda': config.gae_lambda,
                'clip_range': config.clip_range,
                'ent_coef': config.ent_coef,
            },
            'training_timesteps': config.total_timesteps,
            'max_position_size': config.max_position_size,
            'reward_window': config.reward_window,
            'metrics': {
                'sharpe_ratio': metrics.sharpe_ratio,
                'total_return': metrics.total_return,
                'num_trades': metrics.num_trades,
                'win_rate': metrics.win_rate,
                'avg_pnl': metrics.avg_pnl,
                'max_drawdown': metrics.max_drawdown,
            },
            'promotion_status': promotion_status,
            'min_sharpe_for_promotion': config.min_sharpe_for_promotion,
            'created_at': datetime.now().isoformat()
        }
        
        return agent, metrics, metadata
    
    def evaluate_agent(
        self,
        agent: PPO,
        eval_env: TradingEnvironment,
        num_episodes: int = 1
    ) -> AgentMetrics:
        """
        Evaluate agent on evaluation environment.
        
        Requirements: 12.5 - Evaluate on out-of-sample data
        
        Args:
            agent: Trained PPO agent
            eval_env: Evaluation environment
            num_episodes: Number of episodes to run
        
        Returns:
            AgentMetrics with performance metrics
        """
        all_stats = []
        
        for episode in range(num_episodes):
            obs, _ = eval_env.reset()
            done = False
            
            while not done:
                action, _ = agent.predict(obs, deterministic=True)
                obs, reward, terminated, truncated, info = eval_env.step(action)
                done = terminated or truncated
            
            # Get episode statistics
            stats = eval_env.get_trade_statistics()
            all_stats.append(stats)
        
        # Average metrics across episodes
        avg_sharpe = np.mean([s['sharpe_ratio'] for s in all_stats])
        avg_return = np.mean([s['total_return'] for s in all_stats])
        avg_trades = np.mean([s['num_trades'] for s in all_stats])
        avg_win_rate = np.mean([s['win_rate'] for s in all_stats])
        avg_pnl = np.mean([s['avg_pnl'] for s in all_stats])
        avg_drawdown = np.mean([s['max_drawdown'] for s in all_stats])
        
        return AgentMetrics(
            sharpe_ratio=avg_sharpe,
            total_return=avg_return,
            num_trades=int(avg_trades),
            win_rate=avg_win_rate,
            avg_pnl=avg_pnl,
            max_drawdown=avg_drawdown
        )
    
    def save_agent(
        self,
        agent: PPO,
        metadata: Dict[str, Any],
        model_name: Optional[str] = None
    ) -> Path:
        """
        Save trained agent and metadata to disk.
        
        Args:
            agent: Trained PPO agent
            metadata: Agent metadata
            model_name: Optional model name (auto-generated if None)
        
        Returns:
            Path to saved model directory
        """
        if model_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            model_name = f"ppo_{metadata['symbol']}_{timestamp}"
        
        model_dir = self.models_dir / model_name
        model_dir.mkdir(parents=True, exist_ok=True)
        
        # Save agent
        agent_path = model_dir / "agent.zip"
        agent.save(str(agent_path))
        
        # Save metadata
        metadata_path = model_dir / "metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        log.info(f"Agent saved to {model_dir}")
        
        return model_dir
    
    def load_agent(self, model_dir: Path) -> Tuple[PPO, Dict[str, Any]]:
        """
        Load trained agent and metadata from disk.
        
        Args:
            model_dir: Path to model directory
        
        Returns:
            Tuple of (agent, metadata)
        """
        agent_path = model_dir / "agent.zip"
        metadata_path = model_dir / "metadata.json"
        
        if not agent_path.exists():
            raise FileNotFoundError(f"Agent file not found: {agent_path}")
        
        # Load agent
        agent = PPO.load(str(agent_path))
        
        # Load metadata
        metadata = {}
        if metadata_path.exists():
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
        
        log.info(f"Agent loaded from {model_dir}")
        
        return agent, metadata
