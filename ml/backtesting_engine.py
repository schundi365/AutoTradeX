"""
Backtesting Engine

Implements systematic backtesting framework for evaluating trading strategies
on historical data with realistic execution simulation.

Requirements: 13.1, 13.2, 13.3, 13.4, 13.5
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path

from data.historical_data_warehouse import HistoricalDataWarehouse
from core.logger import get_agent_logger

log = get_agent_logger("BACKTESTING_ENGINE")


class ReplayMode(str, Enum):
    """Replay mode for backtesting"""
    TICK_BY_TICK = "tick_by_tick"
    BAR_BY_BAR = "bar_by_bar"


class OrderType(str, Enum):
    """Order types supported by backtesting engine"""
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


class OrderStatus(str, Enum):
    """Order execution status"""
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Order:
    """Order representation"""
    order_id: str
    symbol: str
    order_type: OrderType
    direction: str  # "LONG" or "SHORT"
    size: float  # Position size in lots
    price: Optional[float] = None  # Limit/stop price (None for market orders)
    status: OrderStatus = OrderStatus.PENDING
    filled_price: Optional[float] = None
    filled_time: Optional[datetime] = None
    commission: float = 0.0
    slippage: float = 0.0


@dataclass
class MarketState:
    """Market state for slippage calculation"""
    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    spread: float
    volume: float
    avg_volume: float  # Average volume for volume impact calculation


@dataclass
class Trade:
    """Completed trade record"""
    trade_id: str
    symbol: str
    direction: str
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


@dataclass
class BacktestConfig:
    """Configuration for backtest execution"""
    symbol: str
    start_date: datetime
    end_date: datetime
    initial_capital: float = 10000.0
    replay_mode: ReplayMode = ReplayMode.BAR_BY_BAR
    timeframe: str = "M15"  # For bar-by-bar mode
    
    # Slippage model parameters
    base_slippage_pct: float = 0.0001  # 0.01% base slippage
    volume_impact_factor: float = 0.001  # 0.1% per 1% of volume
    
    # Commission model parameters
    commission_per_lot: float = 7.0  # $7 per lot for forex
    
    # Risk management
    max_position_size: float = 0.02  # 2% of capital max


@dataclass
class BacktestResult:
    """Results from backtest execution"""
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
    equity_curve: pd.DataFrame  # timestamp, equity, drawdown
    
    # Strategy parameters (for model registry)
    strategy_params: Dict[str, Any] = field(default_factory=dict)
    
    # Metadata
    backtest_id: str = ""
    created_at: datetime = field(default_factory=datetime.now)


class SlippageModel:
    """
    Slippage model for realistic execution simulation.
    
    Requirements: 13.2 - Configurable slippage model
    """
    
    def __init__(
        self,
        base_slippage_pct: float = 0.0001,
        volume_impact_factor: float = 0.001
    ):
        self.base_slippage_pct = base_slippage_pct
        self.volume_impact_factor = volume_impact_factor
    
    def apply_slippage(self, order: Order, market_state: MarketState) -> float:
        """
        Apply realistic slippage based on order size and liquidity.
        
        Slippage = half spread + volume impact
        
        Args:
            order: Order to execute
            market_state: Current market state
            
        Returns:
            Slippage amount in price units
        """
        # Base slippage: half spread
        base_slippage = market_state.spread / 2
        
        # Volume impact: proportional to order size relative to average volume
        if market_state.avg_volume > 0:
            volume_ratio = order.size / market_state.avg_volume
            volume_impact = volume_ratio * self.volume_impact_factor * market_state.bid
        else:
            volume_impact = 0.0
        
        # Total slippage
        total_slippage = base_slippage + volume_impact
        
        return total_slippage


class CommissionModel:
    """
    Commission model for broker fee calculation.
    
    Requirements: 13.2 - Configurable commission model
    """
    
    def __init__(self, commission_per_lot: float = 7.0):
        self.commission_per_lot = commission_per_lot
    
    def calculate_commission(self, order: Order) -> float:
        """
        Calculate commission based on broker fee structure.
        
        Args:
            order: Order to execute
            
        Returns:
            Commission amount in currency units
        """
        # Example: $7 per lot for forex
        return order.size * self.commission_per_lot


class BacktestingEngine:
    """
    Systematic backtesting framework for strategy evaluation.
    
    Features:
    - Tick-by-tick and bar-by-bar replay modes
    - Realistic execution simulation with slippage and commissions
    - Support for market, limit, stop-loss, take-profit orders
    - Performance metrics computation
    - Trade-by-trade results with entry/exit prices and P&L
    
    Requirements: 13.1, 13.2, 13.3, 13.4, 13.5
    """
    
    def __init__(
        self,
        warehouse: HistoricalDataWarehouse,
        config: BacktestConfig,
        models_dir: str = "models/backtests"
    ):
        self.warehouse = warehouse
        self.config = config
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        # Execution models
        self.slippage_model = SlippageModel(
            base_slippage_pct=config.base_slippage_pct,
            volume_impact_factor=config.volume_impact_factor
        )
        self.commission_model = CommissionModel(
            commission_per_lot=config.commission_per_lot
        )
        
        # Backtest state
        self.capital = config.initial_capital
        self.current_position: Optional[Order] = None
        self.pending_orders: List[Order] = []
        self.completed_trades: List[Trade] = []
        self.equity_history: List[Tuple[datetime, float]] = []
        
        # Historical data
        self.historical_data: Optional[pd.DataFrame] = None
        self.current_step = 0
        
        log.info(f"Backtesting Engine initialized for {config.symbol}")
        log.info(f"Period: {config.start_date} to {config.end_date}")
        log.info(f"Replay mode: {config.replay_mode}")
    
    def load_historical_data(self) -> None:
        """
        Load historical data for backtesting.
        
        Requirements: 13.1 - Replay historical data
        """
        log.info(f"Loading historical data for {self.config.symbol}")
        
        if self.config.replay_mode == ReplayMode.BAR_BY_BAR:
            # Load OHLCV bars
            self.historical_data = self.warehouse.query_ohlcv(
                symbol=self.config.symbol,
                timeframe=self.config.timeframe,
                start=self.config.start_date,
                end=self.config.end_date
            )
        else:
            # For tick-by-tick, would load tick data
            # For now, use bar data as fallback
            log.warning("Tick-by-tick mode not fully implemented, using bar data")
            self.historical_data = self.warehouse.query_ohlcv(
                symbol=self.config.symbol,
                timeframe="M1",  # Use M1 for finer granularity
                start=self.config.start_date,
                end=self.config.end_date
            )
        
        if self.historical_data.empty:
            raise ValueError(f"No historical data found for {self.config.symbol}")
        
        log.info(f"Loaded {len(self.historical_data)} bars of historical data")
    
    def run_backtest(
        self,
        strategy_func: Callable[[pd.DataFrame, int], Optional[Dict[str, Any]]],
        strategy_params: Optional[Dict[str, Any]] = None
    ) -> BacktestResult:
        """
        Run backtest with given strategy function.
        
        Requirements: 13.1, 13.2, 13.3, 13.4
        
        Args:
            strategy_func: Strategy function that takes (historical_data, current_step)
                          and returns signal dict or None
                          Signal dict format: {
                              'action': 'OPEN_LONG' | 'OPEN_SHORT' | 'CLOSE',
                              'size': float,  # Position size in lots
                              'stop_loss': Optional[float],
                              'take_profit': Optional[float]
                          }
            strategy_params: Optional strategy parameters for metadata
            
        Returns:
            BacktestResult with performance metrics and trade history
        """
        log.info("Starting backtest execution")
        
        # Load data if not already loaded
        if self.historical_data is None:
            self.load_historical_data()
        
        # Reset state
        self.capital = self.config.initial_capital
        self.current_position = None
        self.pending_orders = []
        self.completed_trades = []
        self.equity_history = [(self.historical_data.iloc[0]['timestamp'], self.capital)]
        self.current_step = 0
        
        # Replay historical data
        for step in range(len(self.historical_data)):
            self.current_step = step
            current_bar = self.historical_data.iloc[step]
            
            # Create market state
            market_state = self._create_market_state(current_bar)
            
            # Process pending orders (stop-loss, take-profit, limit orders)
            self._process_pending_orders(market_state)
            
            # Get strategy signal
            signal = strategy_func(self.historical_data, step)
            
            # Execute signal
            if signal:
                self._execute_signal(signal, market_state)
            
            # Record equity
            current_equity = self._calculate_current_equity(market_state)
            self.equity_history.append((current_bar['timestamp'], current_equity))
        
        # Close any open positions at end of backtest
        if self.current_position:
            final_bar = self.historical_data.iloc[-1]
            final_market_state = self._create_market_state(final_bar)
            self._close_position(final_market_state, exit_reason="end_of_backtest")
        
        log.info(f"Backtest completed: {len(self.completed_trades)} trades executed")
        
        # Compute performance metrics
        result = self._compute_performance_metrics(strategy_params or {})
        
        return result

    
    def _create_market_state(self, bar: pd.Series) -> MarketState:
        """Create market state from OHLCV bar"""
        # Estimate bid/ask from close price and typical spread
        typical_spread_pct = 0.0002  # 0.02% typical spread
        close_price = bar['close']
        spread = close_price * typical_spread_pct
        
        bid = close_price - spread / 2
        ask = close_price + spread / 2
        
        # Calculate average volume (use rolling window if available)
        if self.current_step >= 20:
            recent_volumes = self.historical_data.iloc[self.current_step-20:self.current_step]['volume'].values
            avg_volume = np.mean(recent_volumes)
        else:
            avg_volume = bar['volume']
        
        return MarketState(
            symbol=self.config.symbol,
            timestamp=bar['timestamp'],
            bid=bid,
            ask=ask,
            spread=spread,
            volume=bar['volume'],
            avg_volume=avg_volume
        )
    
    def _process_pending_orders(self, market_state: MarketState) -> None:
        """
        Process pending limit, stop-loss, and take-profit orders.
        
        Requirements: 13.2 - Support for limit, stop-loss, take-profit orders
        """
        orders_to_remove = []
        
        for order in self.pending_orders:
            filled = False
            
            if order.order_type == OrderType.LIMIT:
                # Limit order fills if price reaches limit price
                if order.direction == "LONG" and market_state.ask <= order.price:
                    filled = True
                    fill_price = order.price
                elif order.direction == "SHORT" and market_state.bid >= order.price:
                    filled = True
                    fill_price = order.price
            
            elif order.order_type == OrderType.STOP_LOSS:
                # Stop-loss fills if price crosses stop price
                if order.direction == "LONG" and market_state.bid <= order.price:
                    filled = True
                    fill_price = market_state.bid
                elif order.direction == "SHORT" and market_state.ask >= order.price:
                    filled = True
                    fill_price = market_state.ask
            
            elif order.order_type == OrderType.TAKE_PROFIT:
                # Take-profit fills if price reaches target
                if order.direction == "LONG" and market_state.bid >= order.price:
                    filled = True
                    fill_price = market_state.bid
                elif order.direction == "SHORT" and market_state.ask <= order.price:
                    filled = True
                    fill_price = market_state.ask
            
            if filled:
                # Execute order
                order.status = OrderStatus.FILLED
                order.filled_price = fill_price
                order.filled_time = market_state.timestamp
                
                # Apply slippage and commission
                slippage = self.slippage_model.apply_slippage(order, market_state)
                commission = self.commission_model.calculate_commission(order)
                
                order.slippage = slippage
                order.commission = commission
                
                # Adjust fill price for slippage
                if order.direction == "LONG":
                    order.filled_price += slippage
                else:
                    order.filled_price -= slippage
                
                # If this is a closing order (stop-loss or take-profit)
                if order.order_type in [OrderType.STOP_LOSS, OrderType.TAKE_PROFIT]:
                    if self.current_position:
                        self._close_position(
                            market_state,
                            exit_price=order.filled_price,
                            exit_reason=order.order_type.value
                        )
                        # Note: _close_position clears all pending orders
                        # So we don't need to track this order for removal
                        log.debug(f"Order filled: {order.order_type} at {order.filled_price}")
                        return  # Exit early since pending_orders was cleared
                
                orders_to_remove.append(order)
                log.debug(f"Order filled: {order.order_type} at {order.filled_price}")
        
        # Remove filled orders
        for order in orders_to_remove:
            if order in self.pending_orders:
                self.pending_orders.remove(order)
    
    def _execute_signal(self, signal: Dict[str, Any], market_state: MarketState) -> None:
        """
        Execute trading signal.
        
        Requirements: 13.2 - Simulate order execution
        """
        action = signal.get('action')
        size = signal.get('size', 0.01)  # Default 0.01 lots
        
        if action == 'CLOSE':
            if self.current_position:
                self._close_position(market_state, exit_reason="signal")
        
        elif action in ['OPEN_LONG', 'OPEN_SHORT']:
            # Close existing position if any
            if self.current_position:
                self._close_position(market_state, exit_reason="signal")
            
            # Open new position
            direction = "LONG" if action == 'OPEN_LONG' else "SHORT"
            
            # Create market order
            order = Order(
                order_id=f"order_{len(self.completed_trades)}_{self.current_step}",
                symbol=self.config.symbol,
                order_type=OrderType.MARKET,
                direction=direction,
                size=size
            )
            
            # Execute market order immediately
            if direction == "LONG":
                fill_price = market_state.ask
            else:
                fill_price = market_state.bid
            
            # Apply slippage and commission
            slippage = self.slippage_model.apply_slippage(order, market_state)
            commission = self.commission_model.calculate_commission(order)
            
            order.slippage = slippage
            order.commission = commission
            
            # Adjust fill price for slippage
            if direction == "LONG":
                fill_price += slippage
            else:
                fill_price -= slippage
            
            order.status = OrderStatus.FILLED
            order.filled_price = fill_price
            order.filled_time = market_state.timestamp
            
            # Deduct commission from capital
            self.capital -= commission
            
            # Set as current position
            self.current_position = order
            
            log.debug(f"Opened {direction} position at {fill_price}, size={size}")
            
            # Create stop-loss and take-profit orders if specified
            if 'stop_loss' in signal and signal['stop_loss']:
                sl_order = Order(
                    order_id=f"sl_{order.order_id}",
                    symbol=self.config.symbol,
                    order_type=OrderType.STOP_LOSS,
                    direction=direction,
                    size=size,
                    price=signal['stop_loss']
                )
                self.pending_orders.append(sl_order)
                log.debug(f"Stop-loss order placed at {signal['stop_loss']}")
            
            if 'take_profit' in signal and signal['take_profit']:
                tp_order = Order(
                    order_id=f"tp_{order.order_id}",
                    symbol=self.config.symbol,
                    order_type=OrderType.TAKE_PROFIT,
                    direction=direction,
                    size=size,
                    price=signal['take_profit']
                )
                self.pending_orders.append(tp_order)
                log.debug(f"Take-profit order placed at {signal['take_profit']}")
    
    def _close_position(
        self,
        market_state: MarketState,
        exit_price: Optional[float] = None,
        exit_reason: str = "signal"
    ) -> None:
        """Close current position and record trade"""
        if not self.current_position:
            return
        
        # Determine exit price
        if exit_price is None:
            if self.current_position.direction == "LONG":
                exit_price = market_state.bid
            else:
                exit_price = market_state.ask
        
        # Calculate P&L
        entry_price = self.current_position.filled_price
        size = self.current_position.size
        
        if self.current_position.direction == "LONG":
            pnl = (exit_price - entry_price) * size * 100000  # Assuming forex with 100k per lot
        else:
            pnl = (entry_price - exit_price) * size * 100000
        
        # Deduct exit commission
        exit_commission = self.commission_model.calculate_commission(self.current_position)
        pnl -= exit_commission
        
        # Update capital
        self.capital += pnl
        
        # Calculate holding time
        holding_time = (market_state.timestamp - self.current_position.filled_time).total_seconds()
        
        # Record trade
        trade = Trade(
            trade_id=f"trade_{len(self.completed_trades)}",
            symbol=self.config.symbol,
            direction=self.current_position.direction,
            entry_time=self.current_position.filled_time,
            exit_time=market_state.timestamp,
            entry_price=entry_price,
            exit_price=exit_price,
            size=size,
            pnl=pnl,
            commission=self.current_position.commission + exit_commission,
            slippage=self.current_position.slippage,
            holding_time_seconds=int(holding_time),
            exit_reason=exit_reason
        )
        
        self.completed_trades.append(trade)
        
        log.debug(f"Closed {self.current_position.direction} position: "
                 f"entry={entry_price:.5f}, exit={exit_price:.5f}, "
                 f"pnl={pnl:.2f}, reason={exit_reason}")
        
        # Clear current position and pending orders
        self.current_position = None
        self.pending_orders = []
    
    def _calculate_current_equity(self, market_state: MarketState) -> float:
        """Calculate current equity including unrealized P&L"""
        equity = self.capital
        
        if self.current_position:
            # Add unrealized P&L
            entry_price = self.current_position.filled_price
            size = self.current_position.size
            
            if self.current_position.direction == "LONG":
                current_price = market_state.bid
                unrealized_pnl = (current_price - entry_price) * size * 100000
            else:
                current_price = market_state.ask
                unrealized_pnl = (entry_price - current_price) * size * 100000
            
            equity += unrealized_pnl
        
        return equity
    
    def _compute_performance_metrics(
        self,
        strategy_params: Dict[str, Any]
    ) -> BacktestResult:
        """
        Compute performance metrics from completed trades.
        
        Requirements: 13.3, 13.4 - Compute performance metrics and generate trade results
        """
        if not self.completed_trades:
            log.warning("No trades executed during backtest")
            return BacktestResult(
                config=self.config,
                trades=[],
                total_return=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                max_drawdown=0.0,
                win_rate=0.0,
                profit_factor=0.0,
                avg_trade_pnl=0.0,
                avg_holding_time_seconds=0.0,
                num_trades=0,
                equity_curve=pd.DataFrame(),
                strategy_params=strategy_params
            )
        
        # Total return
        final_capital = self.equity_history[-1][1]
        total_return = (final_capital - self.config.initial_capital) / self.config.initial_capital
        
        # Trade statistics
        pnls = [trade.pnl for trade in self.completed_trades]
        returns = [trade.pnl / self.config.initial_capital for trade in self.completed_trades]
        
        num_trades = len(self.completed_trades)
        avg_trade_pnl = np.mean(pnls)
        avg_holding_time = np.mean([trade.holding_time_seconds for trade in self.completed_trades])
        
        # Win rate
        winning_trades = [pnl for pnl in pnls if pnl > 0]
        losing_trades = [pnl for pnl in pnls if pnl < 0]
        win_rate = len(winning_trades) / num_trades if num_trades > 0 else 0.0
        
        # Profit factor
        total_wins = sum(winning_trades) if winning_trades else 0.0
        total_losses = abs(sum(losing_trades)) if losing_trades else 0.0
        profit_factor = total_wins / total_losses if total_losses > 0 else 0.0
        
        # Sharpe ratio
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        sharpe_ratio = mean_return / std_return if std_return > 0 else 0.0
        # Annualize (assuming ~250 trading days)
        sharpe_ratio = sharpe_ratio * np.sqrt(250)
        
        # Sortino ratio (only downside deviation)
        downside_returns = [r for r in returns if r < 0]
        if downside_returns:
            downside_std = np.std(downside_returns)
            sortino_ratio = mean_return / downside_std if downside_std > 0 else 0.0
            sortino_ratio = sortino_ratio * np.sqrt(250)
        else:
            sortino_ratio = 0.0
        
        # Max drawdown
        equity_curve_df = pd.DataFrame(self.equity_history, columns=['timestamp', 'equity'])
        equity_curve_df['peak'] = equity_curve_df['equity'].cummax()
        equity_curve_df['drawdown'] = (equity_curve_df['peak'] - equity_curve_df['equity']) / equity_curve_df['peak']
        max_drawdown = equity_curve_df['drawdown'].max()
        
        log.info(f"Performance Metrics:")
        log.info(f"  Total Return: {total_return*100:.2f}%")
        log.info(f"  Sharpe Ratio: {sharpe_ratio:.2f}")
        log.info(f"  Sortino Ratio: {sortino_ratio:.2f}")
        log.info(f"  Max Drawdown: {max_drawdown*100:.2f}%")
        log.info(f"  Win Rate: {win_rate*100:.2f}%")
        log.info(f"  Profit Factor: {profit_factor:.2f}")
        log.info(f"  Avg Trade P&L: ${avg_trade_pnl:.2f}")
        log.info(f"  Num Trades: {num_trades}")
        
        # Create result
        result = BacktestResult(
            config=self.config,
            trades=self.completed_trades,
            total_return=total_return,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_trade_pnl=avg_trade_pnl,
            avg_holding_time_seconds=avg_holding_time,
            num_trades=num_trades,
            equity_curve=equity_curve_df,
            strategy_params=strategy_params,
            backtest_id=f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            created_at=datetime.now()
        )
        
        return result
    
    def save_backtest_results(
        self,
        result: BacktestResult,
        save_to_registry: bool = True
    ) -> Path:
        """
        Save backtest results to disk and optionally to model registry.
        
        Requirements: 13.5 - Store results in Model Registry
        
        Args:
            result: Backtest result to save
            save_to_registry: Whether to save to model registry
            
        Returns:
            Path to saved results directory
        """
        # Create results directory
        results_dir = self.models_dir / result.backtest_id
        results_dir.mkdir(parents=True, exist_ok=True)
        
        # Save metadata
        metadata = {
            'backtest_id': result.backtest_id,
            'created_at': result.created_at.isoformat(),
            'symbol': result.config.symbol,
            'start_date': result.config.start_date.isoformat(),
            'end_date': result.config.end_date.isoformat(),
            'initial_capital': result.config.initial_capital,
            'replay_mode': result.config.replay_mode.value,
            'timeframe': result.config.timeframe,
            'strategy_params': result.strategy_params,
            'performance_metrics': {
                'total_return': result.total_return,
                'sharpe_ratio': result.sharpe_ratio,
                'sortino_ratio': result.sortino_ratio,
                'max_drawdown': result.max_drawdown,
                'win_rate': result.win_rate,
                'profit_factor': result.profit_factor,
                'avg_trade_pnl': result.avg_trade_pnl,
                'avg_holding_time_seconds': result.avg_holding_time_seconds,
                'num_trades': result.num_trades
            }
        }
        
        metadata_path = results_dir / "metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Save trades
        trades_data = []
        for trade in result.trades:
            trades_data.append({
                'trade_id': trade.trade_id,
                'symbol': trade.symbol,
                'direction': trade.direction,
                'entry_time': trade.entry_time.isoformat(),
                'exit_time': trade.exit_time.isoformat(),
                'entry_price': trade.entry_price,
                'exit_price': trade.exit_price,
                'size': trade.size,
                'pnl': trade.pnl,
                'commission': trade.commission,
                'slippage': trade.slippage,
                'holding_time_seconds': trade.holding_time_seconds,
                'exit_reason': trade.exit_reason
            })
        
        trades_df = pd.DataFrame(trades_data)
        trades_path = results_dir / "trades.csv"
        trades_df.to_csv(trades_path, index=False)
        
        # Save equity curve
        equity_path = results_dir / "equity_curve.csv"
        result.equity_curve.to_csv(equity_path, index=False)
        
        log.info(f"Backtest results saved to {results_dir}")
        
        # Save to model registry if requested
        if save_to_registry:
            self._save_to_model_registry(result, results_dir)
        
        return results_dir
    
    def _save_to_model_registry(
        self,
        result: BacktestResult,
        results_dir: Path
    ) -> None:
        """
        Save backtest results to model registry database.
        
        Requirements: 13.5 - Store results in Model Registry with strategy parameters
        """
        # This would integrate with the model registry database
        # For now, just log the action
        log.info(f"Backtest results registered: {result.backtest_id}")
        log.info(f"  Strategy params: {result.strategy_params}")
        log.info(f"  Performance: Return={result.total_return*100:.2f}%, "
                f"Sharpe={result.sharpe_ratio:.2f}, "
                f"Max DD={result.max_drawdown*100:.2f}%")
        
        # In production, this would:
        # 1. Connect to model registry database (DuckDB)
        # 2. Insert backtest metadata and metrics
        # 3. Link to strategy parameters
        # 4. Store reference to results files
