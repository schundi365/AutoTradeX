"""
Test script for autonomous trading system.
Verifies all components are working correctly.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger as log


async def test_imports():
    """Test that all new modules can be imported"""
    log.info("Testing imports...")
    
    try:
        from core.market_context import MarketStateEngine, MarketContext
        log.info("✓ market_context imported")
        
        from core.fast_decision import FastDecisionEngine, Decision
        log.info("✓ fast_decision imported")
        
        from core.data_lake import MarketDataLake
        log.info("✓ data_lake imported")
        
        from core.outcome_tracker import OutcomeTracker, AdaptiveThresholds
        log.info("✓ outcome_tracker imported")
        
        from agents.autonomous_orchestrator import AutonomousOrchestrator
        log.info("✓ autonomous_orchestrator imported")
        
        from agents.parallel_analyzer import analyze_all_symbols_parallel
        log.info("✓ parallel_analyzer imported")
        
        return True
    except Exception as e:
        log.error(f"Import failed: {e}")
        return False


async def test_market_context():
    """Test market context engine"""
    log.info("\nTesting MarketContext...")
    
    try:
        from core.market_context import MarketStateEngine
        
        engine = MarketStateEngine()
        
        # Test with empty data
        context = engine.get_market_context()
        log.info(f"✓ Market context created: {context.summary()}")
        
        return True
    except Exception as e:
        log.error(f"MarketContext test failed: {e}")
        return False


async def test_fast_decision():
    """Test fast decision engine"""
    log.info("\nTesting FastDecisionEngine...")
    
    try:
        from core.fast_decision import FastDecisionEngine
        from core.market_context import MarketContext, MarketRegime, RiskAppetite
        from core.models import TradingSignal, Direction, AssetClass
        
        engine = FastDecisionEngine()
        
        # Create test signal - strong
        strong_signal = TradingSignal(
            id="test1",
            symbol="XAUUSD",
            asset_class=AssetClass.METAL,
            direction=Direction.BUY,
            entry_price=2000.0,
            stop_loss=1990.0,
            take_profit=2030.0,
            score=8.5,
            confidence=0.85,
            risk_reward=3.0,
            strength="STRONG",
            strategy="test",
            timeframe="M15",
            reasoning="Test signal",
            metadata={"adx": 35, "atr_ratio": 1.2, "volume_ratio": 1.5}
        )
        
        # Create test market context
        context = MarketContext(
            regime=MarketRegime.STRONG_TREND,
            risk_appetite=RiskAppetite.HIGH,
            correlation_risk=0.2
        )
        
        result = engine.evaluate(strong_signal, context)
        log.info(f"✓ Strong signal decision: {result.decision.value} (confidence: {result.confidence})")
        
        # Test weak signal
        weak_signal = TradingSignal(
            id="test2",
            symbol="EURUSD",
            asset_class=AssetClass.FOREX,
            direction=Direction.SELL,
            entry_price=1.1000,
            stop_loss=1.1050,
            take_profit=1.0950,
            score=5.5,
            confidence=0.45,
            risk_reward=1.0,
            strength="WEAK",
            strategy="test",
            timeframe="M15",
            reasoning="Test signal",
            metadata={"adx": 15, "atr_ratio": 0.8, "volume_ratio": 0.7}
        )
        
        result = engine.evaluate(weak_signal, context)
        log.info(f"✓ Weak signal decision: {result.decision.value} (reason: {result.reason})")
        
        return True
    except Exception as e:
        log.error(f"FastDecision test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_data_lake():
    """Test market data lake"""
    log.info("\nTesting MarketDataLake...")
    
    try:
        from core.data_lake import MarketDataLake
        
        lake = MarketDataLake()
        
        # Test with empty data
        snapshot = await lake.get_market_snapshot()
        log.info(f"✓ Market snapshot created with {len(snapshot)} keys")
        
        # Test indicator computation with sample data
        sample_ohlcv = [
            {"open": 2000 + i, "high": 2005 + i, "low": 1995 + i, "close": 2002 + i, "volume": 1000}
            for i in range(100)
        ]
        
        indicators = await lake._compute_indicators("XAUUSD", sample_ohlcv)
        log.info(f"✓ Computed {len(indicators)} indicators: {list(indicators.keys())}")
        
        return True
    except Exception as e:
        log.error(f"DataLake test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_outcome_tracker():
    """Test outcome tracker"""
    log.info("\nTesting OutcomeTracker...")
    
    try:
        from core.outcome_tracker import OutcomeTracker, AdaptiveThresholds
        from core.models import TradingSignal, Direction, AssetClass
        
        tracker = OutcomeTracker()
        adaptive = AdaptiveThresholds(tracker)
        
        # Log a test decision
        signal = TradingSignal(
            id="test1",
            symbol="XAUUSD",
            asset_class=AssetClass.METAL,
            direction=Direction.BUY,
            entry_price=2000.0,
            stop_loss=1990.0,
            take_profit=2030.0,
            score=8.0,
            confidence=0.8,
            risk_reward=3.0,
            strength="STRONG",
            strategy="test",
            timeframe="M15",
            reasoning="Test",
            metadata={"regime": "STRONG_TREND"}
        )
        
        await tracker.log_decision(signal, "GO")
        log.info("✓ Decision logged")
        
        # Get performance
        perf = tracker.get_recent_performance()
        log.info(f"✓ Performance retrieved: {perf}")
        
        # Get thresholds
        thresholds = adaptive.get_thresholds()
        log.info(f"✓ Adaptive thresholds: {thresholds}")
        
        return True
    except Exception as e:
        log.error(f"OutcomeTracker test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_autonomous_orchestrator():
    """Test autonomous orchestrator"""
    log.info("\nTesting AutonomousOrchestrator...")
    
    try:
        from agents.autonomous_orchestrator import AutonomousOrchestrator
        
        orchestrator = AutonomousOrchestrator()
        
        # Get stats
        stats = orchestrator.get_performance_stats()
        log.info(f"✓ Orchestrator stats: {stats}")
        
        return True
    except Exception as e:
        log.error(f"AutonomousOrchestrator test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests"""
    log.info("=" * 60)
    log.info("AUTONOMOUS TRADING SYSTEM - TEST SUITE")
    log.info("=" * 60)
    
    tests = [
        ("Imports", test_imports),
        ("MarketContext", test_market_context),
        ("FastDecision", test_fast_decision),
        ("DataLake", test_data_lake),
        ("OutcomeTracker", test_outcome_tracker),
        ("AutonomousOrchestrator", test_autonomous_orchestrator),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            log.error(f"Test {name} crashed: {e}")
            results.append((name, False))
    
    # Summary
    log.info("\n" + "=" * 60)
    log.info("TEST RESULTS")
    log.info("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        log.info(f"{status} - {name}")
    
    log.info("=" * 60)
    log.info(f"TOTAL: {passed}/{total} tests passed")
    log.info("=" * 60)
    
    if passed == total:
        log.info("🎉 All tests passed! System is ready to test.")
        return 0
    else:
        log.error(f"❌ {total - passed} test(s) failed. Fix issues before testing.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
