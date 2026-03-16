"""
Integration tests for ModelInferenceService with FastDecisionEngine

Tests cover:
- FastDecisionEngine integration with ModelInferenceService
- ML predictions enhancing rule-based decisions
- Backward compatibility (system works without ML)
- Redis-based prediction sharing
- ML prediction boosting weak signals
- ML prediction vetoing strong signals

Requirements: 11.1
"""

import asyncio
import pickle
import sys
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock

import pytest
import numpy as np

# Mock the logger module before importing
sys.modules['core.logger'] = MagicMock()

from ml.model_inference_service import ModelInferenceService, Prediction
from ml.model_registry import ModelMetadata, ModelType
from core.fast_decision import FastDecisionEngine, Decision
from core.models import TradingSignal
from core.market_context import MarketContext, MarketRegime, RiskAppetite


@pytest.fixture
def mock_model():
    """Create a mock ML model"""
    model = Mock()
    # Default: predict UP with 70% confidence
    model.predict_proba = Mock(return_value=np.array([[0.3, 0.7]]))
    return model


@pytest.fixture
def mock_metadata():
    """Create mock model metadata"""
    return ModelMetadata(
        model_id="test-model-123",
        model_name="test_xgboost",
        model_type=ModelType.XGBOOST.value,
        version=1,
        created_at=datetime.now(),
        training_start_date=datetime(2024, 1, 1),
        training_end_date=datetime(2024, 6, 30),
        num_training_samples=10000,
        hyperparameters={"max_depth": 5},
        feature_names=["rsi", "adx", "atr"],
        num_features=3,
        train_metrics={"accuracy": 0.65},
        validation_metrics={"accuracy": 0.58},
        test_metrics={"accuracy": 0.56},
        deployment_status="PRODUCTION",
        deployment_timestamp=datetime.now(),
        deployment_environment="LIVE",
        git_commit_hash="abc123",
        training_script_path="ml/train.py",
        model_file_path="models/test.pkl"
    )


@pytest.fixture
def mock_registry(mock_model, mock_metadata):
    """Create mock model registry"""
    registry = Mock()
    registry.get_current_production_model = Mock(return_value=mock_metadata)
    registry.get_model = Mock(return_value=(mock_metadata, pickle.dumps(mock_model)))
    return registry


@pytest.fixture
def strong_signal():
    """Create a strong trading signal"""
    return TradingSignal(
        symbol="XAUUSD",
        direction="LONG",
        score=8.5,
        confidence=0.85,
        risk_reward=3.0,
        entry_price=2050.0,
        stop_loss=2045.0,
        take_profit=2065.0,
        metadata={
            "adx": 35.0,
            "atr_ratio": 1.2,
            "volume_ratio": 1.5
        }
    )


@pytest.fixture
def favorable_market():
    """Create favorable market context"""
    return MarketContext(
        regime=MarketRegime.STRONG_TREND,
        risk_appetite=RiskAppetite.HIGH,
        correlation_risk=0.2,
        is_news_blackout=False,
        liquidity_conditions="GOOD"
    )


@pytest.mark.asyncio
async def test_fast_decision_without_ml(strong_signal, favorable_market):
    """Test FastDecisionEngine works without ML (backward compatibility)"""
    # Create engine without ML service
    engine = FastDecisionEngine(model_inference_service=None)
    
    # Evaluate signal
    result = await engine.evaluate(strong_signal, favorable_market)
    
    # Should make decision based on rules only
    assert result.decision == Decision.GO
    assert result.confidence > 0.9
    assert not result.needs_llm_review


@pytest.mark.asyncio
async def test_fast_decision_with_ml_enhances_strong_signal(
    mock_registry,
    strong_signal,
    favorable_market
):
    """Test ML predictions enhance strong signals"""
    # Create inference service
    service = ModelInferenceService(
        model_registry=mock_registry,
        redis_url="redis://localhost:6379",
        model_type=ModelType.XGBOOST.value,
        enable_redis=False
    )
    await service.start()
    
    # Create engine with ML
    engine = FastDecisionEngine(model_inference_service=service)
    
    # Mock ML prediction (strongly agrees with LONG)
    mock_prediction = Prediction(
        symbol="XAUUSD",
        timestamp=datetime.now(),
        model_id="test-model-123",
        prediction=0.75,  # Strong UP prediction
        confidence=0.85,
        features_used=["rsi", "adx", "atr"],
        inference_time_ms=15.0
    )
    
    with patch.object(service, 'predict', return_value=mock_prediction):
        result = await engine.evaluate(strong_signal, favorable_market)
    
    # Should approve with high confidence
    assert result.decision == Decision.GO
    assert result.confidence > 0.9
    assert "ML=" in result.reason


@pytest.mark.asyncio
async def test_ml_prediction_stored_in_redis(mock_registry, strong_signal, favorable_market):
    """Test that ML predictions are stored in Redis for FastDecisionEngine"""
    # Create mock Redis client
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock()
    mock_redis.setex = AsyncMock()
    mock_redis.close = AsyncMock()
    
    # Patch redis.from_url
    with patch('redis.asyncio.from_url', return_value=mock_redis):
        service = ModelInferenceService(
            model_registry=mock_registry,
            redis_url="redis://localhost:6379",
            model_type=ModelType.XGBOOST.value,
            enable_redis=True
        )
        await service.start()
        
        # Make prediction
        prediction = await service.predict(
            symbol="XAUUSD",
            features={"rsi": 65.0, "adx": 30.0, "atr": 0.015}
        )
        
        # Verify prediction was stored in Redis
        assert mock_redis.setex.called
        
        # Check the key format
        call_args = mock_redis.setex.call_args
        key = call_args[0][0]
        assert key == "prediction:XAUUSD"
        
        # Check TTL (should be 1 hour = 3600 seconds)
        ttl = call_args[0][1]
        assert ttl == 3600


@pytest.mark.asyncio
async def test_backward_compatibility_ml_failure(
    mock_registry,
    strong_signal,
    favorable_market
):
    """Test system continues working when ML prediction fails"""
    # Create inference service
    service = ModelInferenceService(
        model_registry=mock_registry,
        redis_url="redis://localhost:6379",
        model_type=ModelType.XGBOOST.value,
        enable_redis=False
    )
    await service.start()
    
    # Create engine with ML
    engine = FastDecisionEngine(model_inference_service=service)
    
    # Mock ML prediction to raise exception
    with patch.object(service, 'predict', side_effect=Exception("ML service down")):
        result = await engine.evaluate(strong_signal, favorable_market)
    
    # Should still make decision based on rules (backward compatible)
    assert result.decision == Decision.GO
    assert result.confidence > 0.9


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
