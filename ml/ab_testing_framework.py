"""
A/B Testing Framework for Strategy Variants

This module implements an A/B testing framework that allows comparing multiple
strategy variants in production by allocating capital across variants, tracking
performance metrics separately, and adaptively rebalancing based on statistical
significance testing.

Requirements:
- Requirement 16.1: Allocate capital across variants based on configured weights
- Requirement 16.2: Track performance metrics separately per variant
- Requirement 16.3: Compute statistical significance using t-tests
- Requirement 16.4: Reduce allocation for underperforming variants (>2 std dev below mean)
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import numpy as np
from scipy import stats


@dataclass
class VariantConfig:
    """Configuration for a strategy variant"""
    variant_id: str
    name: str
    initial_weight: float  # Percentage of capital (0.0 to 1.0)
    description: str = ""


@dataclass
class Trade:
    """Represents a single trade"""
    trade_id: str
    variant_id: str
    timestamp: datetime
    symbol: str
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    exit_price: float
    position_size: float
    pnl: float
    holding_time_seconds: int
    capital_allocated: float


@dataclass
class VariantMetrics:
    """Performance metrics for a strategy variant"""
    variant_id: str
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_trade_pnl: float = 0.0
    avg_holding_time_seconds: float = 0.0
    num_trades: int = 0
    capital_allocated: float = 0.0
    
    # Internal tracking
    trades: List[Trade] = field(default_factory=list)
    returns: List[float] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)


@dataclass
class StatisticalTestResult:
    """Result of statistical significance test between two variants"""
    variant_a_id: str
    variant_b_id: str
    t_statistic: float
    p_value: float
    is_significant: bool  # True if p_value < 0.05
    mean_difference: float
    confidence_interval_95: tuple  # (lower, upper)


class ABTestingFramework:
    """
    A/B Testing Framework for comparing strategy variants in production.
    
    Features:
    - Capital allocation based on configured weights
    - Separate performance tracking per variant
    - Statistical significance testing using t-tests
    - Adaptive allocation based on performance
    - Weekly rebalancing
    """
    
    def __init__(
        self,
        total_capital: float,
        variants: List[VariantConfig],
        rebalance_frequency_days: int = 7,
        min_trades_for_testing: int = 30,
        significance_level: float = 0.05,
        underperformance_threshold_std: float = 2.0
    ):
        """
        Initialize the A/B testing framework.
        
        Args:
            total_capital: Total capital available for allocation
            variants: List of variant configurations
            rebalance_frequency_days: Days between rebalancing (default: 7)
            min_trades_for_testing: Minimum trades per variant for statistical testing (default: 30)
            significance_level: Alpha for statistical tests (default: 0.05)
            underperformance_threshold_std: Std deviations below mean to trigger reduction (default: 2.0)
        """
        self.total_capital = total_capital
        self.variants = {v.variant_id: v for v in variants}
        self.rebalance_frequency_days = rebalance_frequency_days
        self.min_trades_for_testing = min_trades_for_testing
        self.significance_level = significance_level
        self.underperformance_threshold_std = underperformance_threshold_std
        
        # Validate weights sum to 1.0
        total_weight = sum(v.initial_weight for v in variants)
        if not (0.99 <= total_weight <= 1.01):
            raise ValueError(f"Variant weights must sum to 1.0, got {total_weight}")
        
        # Initialize metrics tracking
        self.metrics: Dict[str, VariantMetrics] = {}
        for variant_id in self.variants:
            self.metrics[variant_id] = VariantMetrics(
                variant_id=variant_id,
                capital_allocated=self.variants[variant_id].initial_weight * total_capital
            )
        
        # Track current allocation weights
        self.current_weights = {v.variant_id: v.initial_weight for v in variants}
        
        # Track last rebalance time
        self.last_rebalance_time = datetime.now()
    
    def allocate_capital(self) -> Dict[str, float]:
        """
        Allocate capital across variants based on current weights.
        
        Returns:
            Dictionary mapping variant_id to allocated capital
            
        Validates: Requirement 16.1
        """
        allocation = {}
        for variant_id, weight in self.current_weights.items():
            allocation[variant_id] = weight * self.total_capital
            self.metrics[variant_id].capital_allocated = allocation[variant_id]
        
        return allocation
    
    def record_trade(self, trade: Trade) -> None:
        """
        Record a trade for a specific variant.
        
        Args:
            trade: Trade object with all trade details
            
        Validates: Requirement 16.2
        """
        if trade.variant_id not in self.metrics:
            raise ValueError(f"Unknown variant_id: {trade.variant_id}")
        
        metrics = self.metrics[trade.variant_id]
        metrics.trades.append(trade)
        metrics.num_trades += 1
        
        # Calculate return as percentage
        trade_return = trade.pnl / trade.capital_allocated if trade.capital_allocated > 0 else 0.0
        metrics.returns.append(trade_return)
        
        # Update metrics
        self._update_metrics(trade.variant_id)
    
    def _update_metrics(self, variant_id: str) -> None:
        """Update all performance metrics for a variant"""
        metrics = self.metrics[variant_id]
        trades = metrics.trades
        returns = metrics.returns
        
        if not trades:
            return
        
        # Total return
        metrics.total_return = sum(t.pnl for t in trades)
        
        # Average trade P&L
        metrics.avg_trade_pnl = metrics.total_return / len(trades)
        
        # Average holding time
        metrics.avg_holding_time_seconds = sum(t.holding_time_seconds for t in trades) / len(trades)
        
        # Win rate
        winning_trades = sum(1 for t in trades if t.pnl > 0)
        metrics.win_rate = winning_trades / len(trades)
        
        # Profit factor
        gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
        metrics.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Sharpe ratio
        if len(returns) > 1:
            mean_return = np.mean(returns)
            std_return = np.std(returns, ddof=1)
            metrics.sharpe_ratio = mean_return / std_return if std_return > 0 else 0.0
        
        # Sortino ratio (using only downside deviation)
        if len(returns) > 1:
            mean_return = np.mean(returns)
            downside_returns = [r for r in returns if r < 0]
            if downside_returns:
                downside_std = np.std(downside_returns, ddof=1)
                metrics.sortino_ratio = mean_return / downside_std if downside_std > 0 else 0.0
            else:
                metrics.sortino_ratio = float('inf')
        
        # Max drawdown
        equity_curve = [metrics.capital_allocated]
        for trade in trades:
            equity_curve.append(equity_curve[-1] + trade.pnl)
        
        metrics.equity_curve = equity_curve
        
        peak = equity_curve[0]
        max_dd = 0.0
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, drawdown)
        
        metrics.max_drawdown = max_dd
    
    def get_variant_metrics(self, variant_id: str) -> VariantMetrics:
        """
        Get performance metrics for a specific variant.
        
        Args:
            variant_id: ID of the variant
            
        Returns:
            VariantMetrics object with all performance metrics
            
        Validates: Requirement 16.2
        """
        if variant_id not in self.metrics:
            raise ValueError(f"Unknown variant_id: {variant_id}")
        
        return self.metrics[variant_id]
    
    def get_all_metrics(self) -> Dict[str, VariantMetrics]:
        """
        Get performance metrics for all variants.
        
        Returns:
            Dictionary mapping variant_id to VariantMetrics
            
        Validates: Requirement 16.2
        """
        return self.metrics.copy()
    
    def compute_statistical_significance(
        self,
        variant_a_id: str,
        variant_b_id: str
    ) -> Optional[StatisticalTestResult]:
        """
        Compute statistical significance of performance difference between two variants.
        
        Uses independent samples t-test to compare Sharpe ratios.
        
        Args:
            variant_a_id: ID of first variant
            variant_b_id: ID of second variant
            
        Returns:
            StatisticalTestResult or None if insufficient data
            
        Validates: Requirement 16.3
        """
        metrics_a = self.metrics[variant_a_id]
        metrics_b = self.metrics[variant_b_id]
        
        # Check minimum sample size
        if (metrics_a.num_trades < self.min_trades_for_testing or
            metrics_b.num_trades < self.min_trades_for_testing):
            return None
        
        returns_a = np.array(metrics_a.returns)
        returns_b = np.array(metrics_b.returns)
        
        # Perform independent samples t-test
        t_stat, p_value = stats.ttest_ind(returns_a, returns_b)
        
        # Calculate mean difference
        mean_diff = np.mean(returns_a) - np.mean(returns_b)
        
        # Calculate 95% confidence interval for the difference
        # Using pooled standard error
        n_a = len(returns_a)
        n_b = len(returns_b)
        std_a = np.std(returns_a, ddof=1)
        std_b = np.std(returns_b, ddof=1)
        
        pooled_std = np.sqrt(((n_a - 1) * std_a**2 + (n_b - 1) * std_b**2) / (n_a + n_b - 2))
        se_diff = pooled_std * np.sqrt(1/n_a + 1/n_b)
        
        # t-critical value for 95% CI
        df = n_a + n_b - 2
        t_crit = stats.t.ppf(0.975, df)
        
        ci_lower = mean_diff - t_crit * se_diff
        ci_upper = mean_diff + t_crit * se_diff
        
        return StatisticalTestResult(
            variant_a_id=variant_a_id,
            variant_b_id=variant_b_id,
            t_statistic=float(t_stat),
            p_value=float(p_value),
            is_significant=bool(p_value < self.significance_level),
            mean_difference=float(mean_diff),
            confidence_interval_95=(float(ci_lower), float(ci_upper))
        )
    
    def identify_underperforming_variants(self) -> List[str]:
        """
        Identify variants that underperform by more than 2 standard deviations below mean.
        
        Returns:
            List of variant IDs that are underperforming
            
        Validates: Requirement 16.4
        """
        # Calculate mean and std of Sharpe ratios across all variants
        sharpe_ratios = []
        variant_ids = []
        
        for variant_id, metrics in self.metrics.items():
            if metrics.num_trades >= self.min_trades_for_testing:
                sharpe_ratios.append(metrics.sharpe_ratio)
                variant_ids.append(variant_id)
        
        if len(sharpe_ratios) < 2:
            return []  # Need at least 2 variants to compare
        
        mean_sharpe = np.mean(sharpe_ratios)
        std_sharpe = np.std(sharpe_ratios, ddof=1)
        
        # Identify underperformers
        underperformers = []
        threshold = mean_sharpe - self.underperformance_threshold_std * std_sharpe
        
        for variant_id, sharpe in zip(variant_ids, sharpe_ratios):
            if sharpe < threshold:
                underperformers.append(variant_id)
        
        return underperformers
    
    def rebalance_allocation(self) -> Dict[str, float]:
        """
        Rebalance capital allocation based on performance.
        
        Reduces allocation for underperforming variants and increases for outperformers.
        
        Returns:
            New allocation weights dictionary
            
        Validates: Requirement 16.4
        """
        # Check if rebalancing is due
        time_since_rebalance = datetime.now() - self.last_rebalance_time
        if time_since_rebalance.days < self.rebalance_frequency_days:
            return self.current_weights.copy()
        
        # Identify underperformers
        underperformers = self.identify_underperforming_variants()
        
        if not underperformers:
            # No rebalancing needed
            self.last_rebalance_time = datetime.now()
            return self.current_weights.copy()
        
        # Calculate new weights
        new_weights = self.current_weights.copy()
        
        # Reduce underperformer weights by 50%
        total_reduction = 0.0
        for variant_id in underperformers:
            reduction = new_weights[variant_id] * 0.5
            new_weights[variant_id] -= reduction
            total_reduction += reduction
        
        # Distribute reduction to non-underperformers proportionally
        non_underperformers = [v for v in new_weights.keys() if v not in underperformers]
        
        if non_underperformers:
            # Calculate Sharpe ratios for non-underperformers
            sharpe_ratios = {}
            total_sharpe = 0.0
            
            for variant_id in non_underperformers:
                metrics = self.metrics[variant_id]
                if metrics.num_trades >= self.min_trades_for_testing:
                    sharpe = max(0.0, metrics.sharpe_ratio)  # Use 0 for negative Sharpe
                    sharpe_ratios[variant_id] = sharpe
                    total_sharpe += sharpe
                else:
                    sharpe_ratios[variant_id] = 1.0  # Equal weight if insufficient data
                    total_sharpe += 1.0
            
            # Distribute reduction proportionally to Sharpe ratios
            if total_sharpe > 0:
                for variant_id in non_underperformers:
                    proportion = sharpe_ratios[variant_id] / total_sharpe
                    new_weights[variant_id] += total_reduction * proportion
        
        # Normalize weights to sum to 1.0
        total_weight = sum(new_weights.values())
        if total_weight > 0:
            new_weights = {k: v / total_weight for k, v in new_weights.items()}
        
        # Update current weights
        self.current_weights = new_weights
        self.last_rebalance_time = datetime.now()
        
        # Update capital allocation
        self.allocate_capital()
        
        return new_weights.copy()
    
    def should_rebalance(self) -> bool:
        """
        Check if rebalancing is due based on time since last rebalance.
        
        Returns:
            True if rebalancing should occur
        """
        time_since_rebalance = datetime.now() - self.last_rebalance_time
        return time_since_rebalance.days >= self.rebalance_frequency_days
    
    def get_comparison_report(self) -> Dict:
        """
        Generate a comprehensive comparison report of all variants.
        
        Returns:
            Dictionary with comparison data for dashboard display
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_capital": self.total_capital,
            "variants": {},
            "statistical_tests": [],
            "underperformers": self.identify_underperforming_variants(),
            "last_rebalance": self.last_rebalance_time.isoformat(),
            "next_rebalance_due": (self.last_rebalance_time + timedelta(days=self.rebalance_frequency_days)).isoformat()
        }
        
        # Add variant metrics
        for variant_id, metrics in self.metrics.items():
            variant_config = self.variants[variant_id]
            report["variants"][variant_id] = {
                "name": variant_config.name,
                "description": variant_config.description,
                "current_weight": self.current_weights[variant_id],
                "capital_allocated": metrics.capital_allocated,
                "metrics": {
                    "total_return": metrics.total_return,
                    "sharpe_ratio": metrics.sharpe_ratio,
                    "sortino_ratio": metrics.sortino_ratio,
                    "max_drawdown": metrics.max_drawdown,
                    "win_rate": metrics.win_rate,
                    "profit_factor": metrics.profit_factor,
                    "avg_trade_pnl": metrics.avg_trade_pnl,
                    "avg_holding_time_seconds": metrics.avg_holding_time_seconds,
                    "num_trades": metrics.num_trades
                }
            }
        
        # Add pairwise statistical tests
        variant_ids = list(self.metrics.keys())
        for i in range(len(variant_ids)):
            for j in range(i + 1, len(variant_ids)):
                result = self.compute_statistical_significance(variant_ids[i], variant_ids[j])
                if result:
                    report["statistical_tests"].append({
                        "variant_a": result.variant_a_id,
                        "variant_b": result.variant_b_id,
                        "t_statistic": result.t_statistic,
                        "p_value": result.p_value,
                        "is_significant": result.is_significant,
                        "mean_difference": result.mean_difference,
                        "confidence_interval_95": result.confidence_interval_95
                    })
        
        return report
