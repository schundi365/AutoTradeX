"""
Unit tests for A/B Testing Framework

Tests the core functionality of the A/B testing framework including
capital allocation, performance tracking, statistical testing, and
adaptive rebalancing.
"""

import pytest
import numpy as np
from datetime import datetime, timedelta
from ml.ab_testing_framework import (
    ABTestingFramework,
    VariantConfig,
    Trade,
    VariantMetrics,
    StatisticalTestResult
)


@pytest.fixture
def sample_variants():
    """Create sample variant configurations"""
    return [
        VariantConfig(
            variant_id="variant_a",
            name="Conservative Strategy",
            initial_weight=0.3,
            description="Low risk, steady returns"
        ),
        VariantConfig(
            variant_id="variant_b",
            name="Aggressive Strategy",
            initial_weight=0.3,
            description="High risk, high reward"
        ),
        VariantConfig(
            variant_id="variant_c",
            name="Balanced Strategy",
            initial_weight=0.4,
            description="Medium risk, balanced approach"
        )
    ]


@pytest.fixture
def ab_framework(sample_variants):
    """Create an A/B testing framework instance"""
    return ABTestingFramework(
        total_capital=100000.0,
        variants=sample_variants,
        rebalance_frequency_days=7,
        min_trades_for_testing=30,
        significance_level=0.05,
        underperformance_threshold_std=2.0
    )



def create_sample_trade(
    variant_id: str,
    pnl: float,
    capital: float = 10000.0,
    timestamp: datetime = None
) -> Trade:
    """Helper to create a sample trade"""
    if timestamp is None:
        timestamp = datetime.now()
    
    return Trade(
        trade_id=f"trade_{timestamp.timestamp()}",
        variant_id=variant_id,
        timestamp=timestamp,
        symbol="XAUUSD",
        direction="LONG",
        entry_price=2000.0,
        exit_price=2000.0 + (pnl / 100.0),  # Simplified
        position_size=1.0,
        pnl=pnl,
        holding_time_seconds=3600,
        capital_allocated=capital
    )


class TestABTestingFrameworkInitialization:
    """Test framework initialization"""
    
    def test_initialization_with_valid_weights(self, sample_variants):
        """Test that framework initializes correctly with valid weights"""
        framework = ABTestingFramework(
            total_capital=100000.0,
            variants=sample_variants
        )
        
        assert framework.total_capital == 100000.0
        assert len(framework.variants) == 3
        assert len(framework.metrics) == 3
        assert all(v in framework.metrics for v in ["variant_a", "variant_b", "variant_c"])
    
    def test_initialization_with_invalid_weights(self):
        """Test that framework raises error with invalid weights"""
        invalid_variants = [
            VariantConfig("v1", "V1", 0.5),
            VariantConfig("v2", "V2", 0.3)  # Sum = 0.8, not 1.0
        ]
        
        with pytest.raises(ValueError, match="must sum to 1.0"):
            ABTestingFramework(total_capital=100000.0, variants=invalid_variants)



class TestCapitalAllocation:
    """Test capital allocation functionality"""
    
    def test_initial_capital_allocation(self, ab_framework):
        """Test that initial capital is allocated according to weights"""
        allocation = ab_framework.allocate_capital()
        
        # Check allocation matches weights (within 1% tolerance)
        assert abs(allocation["variant_a"] - 30000.0) < 300.0  # 30% of 100k
        assert abs(allocation["variant_b"] - 30000.0) < 300.0  # 30% of 100k
        assert abs(allocation["variant_c"] - 40000.0) < 400.0  # 40% of 100k
        
        # Check total allocation equals total capital
        total_allocated = sum(allocation.values())
        assert abs(total_allocated - 100000.0) < 1000.0
    
    def test_allocation_updates_metrics(self, ab_framework):
        """Test that allocation updates variant metrics"""
        ab_framework.allocate_capital()
        
        assert ab_framework.metrics["variant_a"].capital_allocated == 30000.0
        assert ab_framework.metrics["variant_b"].capital_allocated == 30000.0
        assert ab_framework.metrics["variant_c"].capital_allocated == 40000.0


class TestTradeRecording:
    """Test trade recording and metrics tracking"""
    
    def test_record_single_trade(self, ab_framework):
        """Test recording a single trade"""
        trade = create_sample_trade("variant_a", pnl=500.0)
        ab_framework.record_trade(trade)
        
        metrics = ab_framework.get_variant_metrics("variant_a")
        assert metrics.num_trades == 1
        assert len(metrics.trades) == 1
        assert metrics.total_return == 500.0
    
    def test_record_multiple_trades(self, ab_framework):
        """Test recording multiple trades"""
        trades = [
            create_sample_trade("variant_a", pnl=500.0),
            create_sample_trade("variant_a", pnl=-200.0),
            create_sample_trade("variant_a", pnl=300.0)
        ]
        
        for trade in trades:
            ab_framework.record_trade(trade)
        
        metrics = ab_framework.get_variant_metrics("variant_a")
        assert metrics.num_trades == 3
        assert metrics.total_return == 600.0
        assert abs(metrics.avg_trade_pnl - 200.0) < 0.01

    
    def test_win_rate_calculation(self, ab_framework):
        """Test win rate calculation"""
        trades = [
            create_sample_trade("variant_a", pnl=100.0),  # Win
            create_sample_trade("variant_a", pnl=-50.0),  # Loss
            create_sample_trade("variant_a", pnl=200.0),  # Win
            create_sample_trade("variant_a", pnl=150.0),  # Win
        ]
        
        for trade in trades:
            ab_framework.record_trade(trade)
        
        metrics = ab_framework.get_variant_metrics("variant_a")
        assert abs(metrics.win_rate - 0.75) < 0.01  # 3 wins out of 4
    
    def test_profit_factor_calculation(self, ab_framework):
        """Test profit factor calculation"""
        trades = [
            create_sample_trade("variant_a", pnl=300.0),  # Profit
            create_sample_trade("variant_a", pnl=-100.0),  # Loss
            create_sample_trade("variant_a", pnl=200.0),  # Profit
        ]
        
        for trade in trades:
            ab_framework.record_trade(trade)
        
        metrics = ab_framework.get_variant_metrics("variant_a")
        # Profit factor = gross profit / gross loss = 500 / 100 = 5.0
        assert abs(metrics.profit_factor - 5.0) < 0.01
    
    def test_sharpe_ratio_calculation(self, ab_framework):
        """Test Sharpe ratio calculation"""
        # Create trades with consistent positive returns
        trades = [create_sample_trade("variant_a", pnl=100.0, capital=10000.0) for _ in range(10)]
        
        for trade in trades:
            ab_framework.record_trade(trade)
        
        metrics = ab_framework.get_variant_metrics("variant_a")
        # With consistent returns, Sharpe should be very high (low std)
        assert metrics.sharpe_ratio > 0
    
    def test_max_drawdown_calculation(self, ab_framework):
        """Test max drawdown calculation"""
        # Create a sequence with a drawdown
        trades = [
            create_sample_trade("variant_a", pnl=1000.0),  # Peak
            create_sample_trade("variant_a", pnl=-500.0),  # Drawdown
            create_sample_trade("variant_a", pnl=-300.0),  # Further drawdown
            create_sample_trade("variant_a", pnl=500.0),   # Recovery
        ]
        
        for trade in trades:
            ab_framework.record_trade(trade)
        
        metrics = ab_framework.get_variant_metrics("variant_a")
        # Max drawdown should be positive and less than 1.0
        assert 0 < metrics.max_drawdown < 1.0



class TestStatisticalSignificance:
    """Test statistical significance testing"""
    
    def test_insufficient_data_returns_none(self, ab_framework):
        """Test that statistical test returns None with insufficient data"""
        # Add only 10 trades (less than min_trades_for_testing=30)
        for _ in range(10):
            ab_framework.record_trade(create_sample_trade("variant_a", pnl=100.0))
            ab_framework.record_trade(create_sample_trade("variant_b", pnl=150.0))
        
        result = ab_framework.compute_statistical_significance("variant_a", "variant_b")
        assert result is None
    
    def test_statistical_test_with_sufficient_data(self, ab_framework):
        """Test statistical test with sufficient data"""
        # Add 40 trades to each variant
        np.random.seed(42)
        for _ in range(40):
            ab_framework.record_trade(
                create_sample_trade("variant_a", pnl=np.random.normal(100, 50))
            )
            ab_framework.record_trade(
                create_sample_trade("variant_b", pnl=np.random.normal(150, 50))
            )
        
        result = ab_framework.compute_statistical_significance("variant_a", "variant_b")
        
        assert result is not None
        assert isinstance(result, StatisticalTestResult)
        assert result.variant_a_id == "variant_a"
        assert result.variant_b_id == "variant_b"
        assert isinstance(result.p_value, float)
        assert 0 <= result.p_value <= 1
        assert isinstance(result.is_significant, bool)
    
    def test_confidence_interval_calculation(self, ab_framework):
        """Test that confidence interval is calculated"""
        np.random.seed(42)
        for _ in range(40):
            ab_framework.record_trade(
                create_sample_trade("variant_a", pnl=np.random.normal(100, 50))
            )
            ab_framework.record_trade(
                create_sample_trade("variant_b", pnl=np.random.normal(150, 50))
            )
        
        result = ab_framework.compute_statistical_significance("variant_a", "variant_b")
        
        assert result is not None
        assert len(result.confidence_interval_95) == 2
        lower, upper = result.confidence_interval_95
        assert lower < upper



class TestUnderperformanceDetection:
    """Test underperformance detection"""
    
    def test_no_underperformers_with_similar_performance(self, ab_framework):
        """Test that no underperformers are detected when all perform similarly"""
        np.random.seed(42)
        # All variants have similar performance
        for _ in range(40):
            ab_framework.record_trade(
                create_sample_trade("variant_a", pnl=np.random.normal(100, 20))
            )
            ab_framework.record_trade(
                create_sample_trade("variant_b", pnl=np.random.normal(105, 20))
            )
            ab_framework.record_trade(
                create_sample_trade("variant_c", pnl=np.random.normal(95, 20))
            )
        
        underperformers = ab_framework.identify_underperforming_variants()
        assert len(underperformers) == 0
    
    def test_identifies_clear_underperformer(self, ab_framework):
        """Test that clear underperformer is identified"""
        # Use a lower threshold for this test
        ab_framework.underperformance_threshold_std = 1.0  # More sensitive
        
        np.random.seed(42)
        # Create trades with very different Sharpe ratios
        # variant_a and variant_b: consistent positive returns (high Sharpe)
        # variant_c: highly volatile negative returns (very low/negative Sharpe)
        for _ in range(50):
            ab_framework.record_trade(
                create_sample_trade("variant_a", pnl=np.random.normal(50, 5), capital=10000.0)
            )
            ab_framework.record_trade(
                create_sample_trade("variant_b", pnl=np.random.normal(50, 5), capital=10000.0)
            )
            ab_framework.record_trade(
                create_sample_trade("variant_c", pnl=np.random.normal(-50, 50), capital=10000.0)
            )
        
        underperformers = ab_framework.identify_underperforming_variants()
        # With 1-std threshold and extreme difference, variant_c should be identified
        assert "variant_c" in underperformers


class TestRebalancing:
    """Test adaptive rebalancing"""
    
    def test_no_rebalance_before_frequency(self, ab_framework):
        """Test that rebalancing doesn't occur before frequency period"""
        # Set last rebalance to 3 days ago
        ab_framework.last_rebalance_time = datetime.now() - timedelta(days=3)
        
        assert not ab_framework.should_rebalance()
        
        # Rebalance should return current weights unchanged
        new_weights = ab_framework.rebalance_allocation()
        assert new_weights == ab_framework.current_weights
    
    def test_rebalance_after_frequency(self, ab_framework):
        """Test that rebalancing occurs after frequency period"""
        # Set last rebalance to 8 days ago
        ab_framework.last_rebalance_time = datetime.now() - timedelta(days=8)
        
        assert ab_framework.should_rebalance()

    
    def test_rebalance_reduces_underperformer_allocation(self, ab_framework):
        """Test that rebalancing reduces allocation for underperformers"""
        # Set last rebalance to trigger rebalancing
        ab_framework.last_rebalance_time = datetime.now() - timedelta(days=8)
        # Use more sensitive threshold
        ab_framework.underperformance_threshold_std = 1.0
        
        np.random.seed(42)
        # Create clear underperformer with extreme Sharpe difference
        for _ in range(50):
            ab_framework.record_trade(
                create_sample_trade("variant_a", pnl=np.random.normal(50, 5), capital=10000.0)
            )
            ab_framework.record_trade(
                create_sample_trade("variant_b", pnl=np.random.normal(50, 5), capital=10000.0)
            )
            ab_framework.record_trade(
                create_sample_trade("variant_c", pnl=np.random.normal(-50, 50), capital=10000.0)
            )
        
        initial_weight_c = ab_framework.current_weights["variant_c"]
        
        new_weights = ab_framework.rebalance_allocation()
        
        # variant_c should have reduced weight
        assert new_weights["variant_c"] < initial_weight_c
        
        # Weights should still sum to 1.0
        assert abs(sum(new_weights.values()) - 1.0) < 0.01
    
    def test_rebalance_increases_outperformer_allocation(self, ab_framework):
        """Test that rebalancing redistributes capital from underperformers"""
        ab_framework.last_rebalance_time = datetime.now() - timedelta(days=8)
        # Use more sensitive threshold
        ab_framework.underperformance_threshold_std = 1.0
        
        np.random.seed(123)  # Different seed for different distribution
        # variant_c clearly underperforms
        for _ in range(50):
            ab_framework.record_trade(
                create_sample_trade("variant_a", pnl=np.random.normal(50, 5), capital=10000.0)
            )
            ab_framework.record_trade(
                create_sample_trade("variant_b", pnl=np.random.normal(50, 5), capital=10000.0)
            )
            ab_framework.record_trade(
                create_sample_trade("variant_c", pnl=np.random.normal(-100, 50), capital=10000.0)
            )
        
        initial_weight_c = ab_framework.current_weights["variant_c"]
        
        new_weights = ab_framework.rebalance_allocation()
        
        # variant_c should have reduced weight (it's the clear underperformer)
        assert new_weights["variant_c"] < initial_weight_c
        # Weights should still sum to 1.0
        assert abs(sum(new_weights.values()) - 1.0) < 0.01


class TestComparisonReport:
    """Test comparison report generation"""
    
    def test_report_structure(self, ab_framework):
        """Test that comparison report has correct structure"""
        report = ab_framework.get_comparison_report()
        
        assert "timestamp" in report
        assert "total_capital" in report
        assert "variants" in report
        assert "statistical_tests" in report
        assert "underperformers" in report
        assert "last_rebalance" in report
        assert "next_rebalance_due" in report
    
    def test_report_includes_all_variants(self, ab_framework):
        """Test that report includes all variants"""
        report = ab_framework.get_comparison_report()
        
        assert len(report["variants"]) == 3
        assert "variant_a" in report["variants"]
        assert "variant_b" in report["variants"]
        assert "variant_c" in report["variants"]
    
    def test_report_includes_metrics(self, ab_framework):
        """Test that report includes performance metrics"""
        # Add some trades
        for _ in range(5):
            ab_framework.record_trade(create_sample_trade("variant_a", pnl=100.0))
        
        report = ab_framework.get_comparison_report()
        variant_a_data = report["variants"]["variant_a"]
        
        assert "metrics" in variant_a_data
        metrics = variant_a_data["metrics"]
        assert "total_return" in metrics
        assert "sharpe_ratio" in metrics
        assert "win_rate" in metrics
        assert "num_trades" in metrics
