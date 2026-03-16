"""
Reinforcement Learning Training Environment

Implements a gym environment for training RL agents on historical data.
Uses historical data replay with position sizing actions.

Requirements: 12.1, 12.3
"""

import numpy as np
import pandas as pd
import gymnasium as gym
from gymnasium import spaces
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from collections import deque

from data.historical_data_warehouse import HistoricalDataWarehouse
from data.feature_pipeline import FeaturePipeline
from core.logger import get_agent_logger

log = get_agent_logger("RL_ENVIRONMENT")


@dataclass
class TradeRecord:
    """Record of a single trade"""
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    position_size: float  # Percentage of capital
    pnl: float
    capital: float  # Capital at trade time


class TradingEnvironment(gym.Env):
    """
    Gym environment for RL agent training.
    
    Features:
    - Historical data replay (tick-by-tick or bar-by-bar)
    - Action space: position size 0-2% of capital
    - State space: feature vector from FeaturePipeline (100+ features)
    - Reward function: Sharpe ratio over rolling 100 trades
    - Risk management: max 2% position size constraint
    
    Requirements: 12.1, 12.3
    """
    
    metadata = {'render_modes': []}
    
    def __init__(
        self,
        warehouse: HistoricalDataWarehouse,
        feature_pipeline: FeaturePipeline,
        symbol: str,
        timeframe: str = "M15",
        start_date: datetime = None,
        end_date: datetime = None,
        initial_capital: float = 10000.0,
        max_position_size: float = 0.02,  # 2% max
        trade_cost: float = 0.0001,  # 0.01% per trade
        reward_window: int = 100,  # Rolling window for Sharpe calculation
    ):
        super().__init__()
        
        self.warehouse = warehouse
        self.feature_pipeline = feature_pipeline
        self.symbol = symbol
        self.timeframe = timeframe
        self.initial_capital = initial_capital
        self.max_position_size = max_position_size
        self.trade_cost = trade_cost
        self.reward_window = reward_window
        
        # Date range for historical data
        if start_date is None:
            start_date = datetime.now() - timedelta(days=180)  # 6 months default
        if end_date is None:
            end_date = datetime.now()
        
        self.start_date = start_date
        self.end_date = end_date
        
        # Load historical data
        log.info(f"Loading historical data for {symbol} from {start_date} to {end_date}")
        self.historical_data = warehouse.query_ohlcv(
            symbol=symbol,
            timeframe=timeframe,
            start=start_date,
            end=end_date
        )
        
        if self.historical_data.empty:
            raise ValueError(f"No historical data found for {symbol}")
        
        log.info(f"Loaded {len(self.historical_data)} bars of historical data")
        
        # Generate features for all bars
        log.info("Generating features for historical data...")
        self.features_data = self._generate_features()
        log.info(f"Generated {len(self.features_data)} feature vectors")
        
        # Define action space: continuous position size from 0% to 2%
        # Action is a single float value representing position size percentage
        self.action_space = spaces.Box(
            low=0.0,
            high=self.max_position_size,
            shape=(1,),
            dtype=np.float32
        )
        
        # Define observation space: feature vector (will be set after feature generation)
        if len(self.features_data) > 0:
            feature_dim = len(self.features_data[0])
            self.observation_space = spaces.Box(
                low=-np.inf,
                high=np.inf,
                shape=(feature_dim,),
                dtype=np.float32
            )
        else:
            # Default to 100 features if no data yet
            self.observation_space = spaces.Box(
                low=-np.inf,
                high=np.inf,
                shape=(100,),
                dtype=np.float32
            )
        
        # Environment state
        self.current_step = 0
        self.capital = initial_capital
        self.current_position = 0.0  # Current position size
        self.entry_price = 0.0
        self.trade_history: List[TradeRecord] = []
        
        log.info(f"Environment initialized: {len(self.historical_data)} bars, "
                f"feature_dim={self.observation_space.shape[0]}")
    
    def _generate_features(self) -> List[np.ndarray]:
        """
        Generate features for all historical bars.
        Uses simplified feature extraction similar to supervised training.
        """
        features_list = []
        
        for i in range(len(self.historical_data)):
            try:
                # Get window of data up to current bar
                window_data = self.historical_data.iloc[max(0, i-500):i+1]
                
                if len(window_data) < 20:
                    continue
                
                # Extract features
                features = self._extract_features(window_data)
                
                if features:
                    # Convert to numpy array
                    feature_array = np.array(list(features.values()), dtype=np.float32)
                    features_list.append(feature_array)
                else:
                    # Use zeros if feature extraction fails
                    if len(features_list) > 0:
                        features_list.append(np.zeros_like(features_list[0]))
                    
            except Exception as e:
                log.debug(f"Error generating features for bar {i}: {e}")
                if len(features_list) > 0:
                    features_list.append(np.zeros_like(features_list[0]))
        
        return features_list
    
    def _extract_features(self, window_data: pd.DataFrame) -> Optional[Dict[str, float]]:
        """
        Extract features from price data window.
        Simplified version for RL training.
        """
        if len(window_data) < 20:
            return None
        
        features = {}
        
        try:
            close = window_data['close'].values
            high = window_data['high'].values
            low = window_data['low'].values
            volume = window_data['volume'].values
            
            # Price features
            if len(close) >= 2:
                features['return_1bar'] = (close[-1] - close[-2]) / close[-2]
            if len(close) >= 6:
                features['return_5bar'] = (close[-1] - close[-6]) / close[-6]
            if len(close) >= 21:
                features['return_20bar'] = (close[-1] - close[-21]) / close[-21]
            if len(close) >= 51:
                features['return_50bar'] = (close[-1] - close[-51]) / close[-51]
            
            # RSI
            if len(close) >= 15:
                deltas = np.diff(close[-15:])
                gains = np.where(deltas > 0, deltas, 0)
                losses = np.where(deltas < 0, -deltas, 0)
                avg_gain = np.mean(gains)
                avg_loss = np.mean(losses)
                rs = avg_gain / avg_loss if avg_loss != 0 else 0
                features['rsi_14'] = 100 - (100 / (1 + rs)) if rs != 0 else 50
            
            # EMAs
            if len(close) >= 20:
                features['ema_20'] = self._calculate_ema(close, 20)
            if len(close) >= 50:
                features['ema_50'] = self._calculate_ema(close, 50)
            if len(close) >= 200:
                features['ema_200'] = self._calculate_ema(close, 200)
            
            # Volatility
            if len(close) >= 21:
                returns = np.diff(np.log(close[-21:]))
                features['volatility_20'] = np.std(returns)
            
            # Volume features
            if len(volume) >= 21:
                features['volume_ratio'] = volume[-1] / np.mean(volume[-21:-1]) if np.mean(volume[-21:-1]) > 0 else 1.0
            
            # Statistical features
            for window in [20, 50, 100]:
                if len(close) >= window + 1:
                    window_data_slice = close[-window:]
                    mean = np.mean(window_data_slice)
                    std = np.std(window_data_slice)
                    
                    features[f'mean_{window}'] = mean
                    features[f'std_{window}'] = std
                    
                    if std > 0:
                        features[f'zscore_{window}'] = (close[-1] - mean) / std
                    else:
                        features[f'zscore_{window}'] = 0.0
            
            return features
            
        except Exception as e:
            log.debug(f"Error extracting features: {e}")
            return None
    
    def _calculate_ema(self, data: np.ndarray, period: int) -> float:
        """Calculate Exponential Moving Average"""
        if len(data) < period:
            return data[-1]
        
        multiplier = 2 / (period + 1)
        ema = data[-period]
        
        for price in data[-period+1:]:
            ema = (price - ema) * multiplier + ema
        
        return ema
    
    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None) -> Tuple[np.ndarray, dict]:
        """
        Reset environment to initial state.
        
        Returns:
            observation: Initial state
            info: Additional information
        """
        super().reset(seed=seed)
        
        self.current_step = 0
        self.capital = self.initial_capital
        self.current_position = 0.0
        self.entry_price = 0.0
        self.trade_history = []
        
        # Return first observation
        if len(self.features_data) > 0:
            observation = self.features_data[0]
        else:
            observation = np.zeros(self.observation_space.shape, dtype=np.float32)
        
        info = {
            'capital': self.capital,
            'position': self.current_position,
            'step': self.current_step
        }
        
        return observation, info
    
    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, dict]:
        """
        Execute one step in the environment.
        
        Args:
            action: Position size (0 to max_position_size)
        
        Returns:
            observation: Next state
            reward: Reward for this step
            terminated: Whether episode is done
            truncated: Whether episode was truncated
            info: Additional information
        """
        # Extract position size from action
        position_size = float(action[0])
        
        # Constrain to max position size (risk management)
        position_size = np.clip(position_size, 0.0, self.max_position_size)
        
        # Get current and next price
        current_bar = self.historical_data.iloc[self.current_step]
        current_price = current_bar['close']
        
        # Execute trade if position size changed
        if position_size != self.current_position:
            # Close existing position if any
            if self.current_position > 0:
                exit_price = current_price
                pnl = self._calculate_pnl(self.entry_price, exit_price, self.current_position)
                
                # Apply trading costs
                pnl -= self.capital * self.current_position * self.trade_cost
                
                self.capital += pnl
                
                # Record trade
                trade = TradeRecord(
                    entry_time=self.historical_data.iloc[self.current_step - 1]['timestamp'],
                    exit_time=current_bar['timestamp'],
                    entry_price=self.entry_price,
                    exit_price=exit_price,
                    position_size=self.current_position,
                    pnl=pnl,
                    capital=self.capital
                )
                self.trade_history.append(trade)
            
            # Open new position if size > 0
            if position_size > 0:
                self.entry_price = current_price
                # Apply trading costs
                self.capital -= self.capital * position_size * self.trade_cost
            
            self.current_position = position_size
        
        # Move to next step
        self.current_step += 1
        
        # Check if episode is done
        terminated = self.current_step >= len(self.features_data) - 1
        truncated = False
        
        # Get next observation
        if not terminated:
            observation = self.features_data[self.current_step]
        else:
            observation = np.zeros(self.observation_space.shape, dtype=np.float32)
        
        # Calculate reward (Sharpe ratio over rolling window)
        reward = self._calculate_reward()
        
        info = {
            'capital': self.capital,
            'position': self.current_position,
            'step': self.current_step,
            'num_trades': len(self.trade_history),
            'total_return': (self.capital - self.initial_capital) / self.initial_capital
        }
        
        return observation, reward, terminated, truncated, info
    
    def _calculate_pnl(self, entry_price: float, exit_price: float, position_size: float) -> float:
        """
        Calculate P&L for a trade.
        
        Args:
            entry_price: Entry price
            exit_price: Exit price
            position_size: Position size as percentage of capital
        
        Returns:
            P&L in currency units
        """
        # Calculate return
        price_return = (exit_price - entry_price) / entry_price
        
        # Calculate P&L based on position size
        pnl = self.capital * position_size * price_return
        
        return pnl
    
    def _calculate_reward(self) -> float:
        """
        Calculate reward as Sharpe ratio over rolling 100-trade window.
        
        Requirements: 12.2 - Reward function is Sharpe ratio over rolling 100 trades
        
        Returns:
            Sharpe ratio (or 0 if insufficient trades)
        """
        if len(self.trade_history) < 10:
            # Not enough trades for meaningful Sharpe ratio
            return 0.0
        
        # Get last N trades (up to reward_window)
        recent_trades = self.trade_history[-self.reward_window:]
        
        # Calculate returns for each trade
        returns = [trade.pnl / trade.capital for trade in recent_trades]
        
        # Calculate Sharpe ratio
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        
        if std_return > 0:
            sharpe_ratio = mean_return / std_return
        else:
            sharpe_ratio = 0.0
        
        return sharpe_ratio
    
    def render(self):
        """Render environment (not implemented)"""
        pass
    
    def get_trade_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about trades executed in the environment.
        
        Returns:
            Dictionary with trade statistics
        """
        if not self.trade_history:
            return {
                'num_trades': 0,
                'total_pnl': 0.0,
                'avg_pnl': 0.0,
                'win_rate': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0,
                'final_capital': self.capital
            }
        
        # Calculate statistics
        pnls = [trade.pnl for trade in self.trade_history]
        returns = [trade.pnl / trade.capital for trade in self.trade_history]
        
        num_trades = len(self.trade_history)
        total_pnl = sum(pnls)
        avg_pnl = np.mean(pnls)
        win_rate = sum(1 for pnl in pnls if pnl > 0) / num_trades
        
        # Sharpe ratio
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        sharpe_ratio = mean_return / std_return if std_return > 0 else 0.0
        
        # Max drawdown
        capital_curve = [self.initial_capital]
        for trade in self.trade_history:
            capital_curve.append(trade.capital)
        
        peak = capital_curve[0]
        max_drawdown = 0.0
        for capital in capital_curve:
            if capital > peak:
                peak = capital
            drawdown = (peak - capital) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return {
            'num_trades': num_trades,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'win_rate': win_rate,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'final_capital': self.capital,
            'total_return': (self.capital - self.initial_capital) / self.initial_capital
        }
