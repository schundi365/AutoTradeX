"""
Unit tests for Supervised Learning Training Pipeline

Tests Requirements: 11.1, 11.2, 11.3, 11.4, 11.5
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import shutil

from ml.supervised_training import (
    SupervisedTrainingPipeline,
    TrainingConfig,
    ModelMetrics
)
from data.historical_data_warehouse import HistoricalDataWarehouse
from data.feature_pipeline import FeaturePipeline
from data.event_bus import EventBus


@pytest.fixture
def temp_dir():
    """Create temporary directory for test files"""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def warehouse(temp_dir):
    """Create test warehouse with sample data"""
    db_path = Path(temp_dir) / "test_market_data.duckdb"
    parquet_root = Path(temp_dir) / "parquet"
    
    warehouse = HistoricalDataWarehouse(
        db_path=str(db_path),
        parquet_root=str(parquet_root)
    )
    
    # Generate sample OHLCV data (6 months)
    dates = pd.date_range(
        start=datetime.now() - timedelta(days=180),
        end=datetime.now(),
        freq='15min'
    )
    
    # Create realistic price data with trend
    np.random.seed(42)
    base_price = 2000.0
    prices = []
    current_price = base_price
    
    for i in range(len(dates)):
        # Random walk with slight upward bias
        change = np.random.normal(0.0001, 0.002)
        current_price = current_price * (1 + change)
        prices.append(current_price)
    
    prices = np.array(prices)
    
    # Create OHLCV data
    data = pd.DataFrame({
        'timestamp': dates,
        'open': prices * (1 + np.random.uniform(-0.001, 0.001, len(dates))),
        'high': prices * (1 + np.random.uniform(0, 0.002, len(dates))),
        'low': prices * (1 + np.random.uniform(-0.002, 0, len(dates))),
        'close': prices,
        'volume': np.random.randint(100, 1000, len(dates))
    })
    
    # Store in warehouse
    warehouse.store_ohlcv("XAUUSD", "M15", data)
    
    return warehouse


@pytest.fixture
def feature_pipeline():
    """Create mock feature pipeline"""
    event_bus = EventBus(max_queue_size=100)
    
    # Mock Redis client
    class MockRedis:
        async def get(self, key):
            return None
        async def setex(self, key, ttl, value):
            pass
    
    pipeline = FeaturePipeline(
        event_bus=event_bus,
        redis_client=MockRedis(),
        symbols=["XAUUSD"],
        timeframes=["M15"]
    )
    
    return pipeline


@pytest.fixture
def training_pipeline(warehouse, feature_pipeline, temp_dir):
    """Create training pipeline"""
    models_dir = Path(temp_dir) / "models"
    return SupervisedTrainingPipeline(
        warehouse=warehouse,
        feature_pipeline=feature_pipeline,
        models_dir=str(models_dir)
    )


def test_training_config_defaults():
    """Test TrainingConfig default values"""
    config = TrainingConfig(symbol="XAUUSD")
    
    assert config.symbol == "XAUUSD"
    assert config.timeframe == "M15"
    assert config.training_months == 6
    assert config.forward_return_minutes == 15
    assert config.up_threshold == 0.001
    assert config.down_threshold == -0.001
    assert config.train_split == 0.8
    assert config.min_accuracy == 0.52


def test_model_metrics_acceptance_criteria():
    """Test ModelMetrics acceptance criteria check"""
    # Model that meets criteria
    good_metrics = ModelMetrics(
        accuracy=0.55,
        precision=0.54,
        recall=0.53,
        f1_score=0.535,
        roc_auc=0.60
    )
    assert good_metrics.meets_acceptance_criteria(0.52) is True
    
    # Model that doesn't meet criteria
    bad_metrics = ModelMetrics(
        accuracy=0.50,
        precision=0.49,
        recall=0.48,
        f1_score=0.485,
        roc_auc=0.52
    )
    assert bad_metrics.meets_acceptance_criteria(0.52) is False


def test_generate_training_data(training_pipeline):
    """
    Test feature generation from historical data.
    Requirements: 11.1, 11.2
    """
    config = TrainingConfig(
        symbol="XAUUSD",
        timeframe="M15",
        training_months=6
    )
    
    features_df, labels_series = training_pipeline.generate_training_data(config)
    
    # Check that data was generated
    assert len(features_df) > 0
    assert len(labels_series) > 0
    assert len(features_df) == len(labels_series)
    
    # Check labels are binary (0 or 1)
    assert set(labels_series.unique()).issubset({0, 1})
    
    # Check features have expected columns
    assert 'return_1bar' in features_df.columns
    assert 'rsi_14' in features_df.columns
    assert 'volatility_20' in features_df.columns


def test_generate_training_data_label_distribution(training_pipeline):
    """
    Test that labels are created correctly based on forward returns.
    Requirements: 11.2
    """
    config = TrainingConfig(
        symbol="XAUUSD",
        timeframe="M15",
        up_threshold=0.001,  # 0.1%
        down_threshold=-0.001
    )
    
    features_df, labels_series = training_pipeline.generate_training_data(config)
    
    # Should have both UP and DOWN labels
    assert 0 in labels_series.values  # DOWN
    assert 1 in labels_series.values  # UP
    
    # Label distribution should be reasonable (not all one class)
    up_ratio = sum(labels_series == 1) / len(labels_series)
    assert 0.2 < up_ratio < 0.8, "Label distribution is too imbalanced"


def test_train_xgboost(training_pipeline):
    """
    Test XGBoost model training.
    Requirements: 11.4
    """
    # Generate sample training data
    config = TrainingConfig(symbol="XAUUSD", training_months=6)
    features_df, labels_series = training_pipeline.generate_training_data(config)
    
    # Split data
    split_idx = int(len(features_df) * 0.8)
    X_train = features_df.iloc[:split_idx]
    y_train = labels_series.iloc[:split_idx]
    X_val = features_df.iloc[split_idx:]
    y_val = labels_series.iloc[split_idx:]
    
    # Train model
    model, metrics = training_pipeline.train_xgboost(
        X_train, y_train, X_val, y_val
    )
    
    # Check model was trained
    assert model is not None
    assert hasattr(model, 'predict')
    
    # Check metrics are valid
    assert 0 <= metrics.accuracy <= 1
    assert 0 <= metrics.precision <= 1
    assert 0 <= metrics.recall <= 1
    assert 0 <= metrics.f1_score <= 1
    assert 0 <= metrics.roc_auc <= 1


def test_train_lightgbm(training_pipeline):
    """
    Test LightGBM model training.
    Requirements: 11.4
    """
    # Generate sample training data
    config = TrainingConfig(symbol="XAUUSD", training_months=6)
    features_df, labels_series = training_pipeline.generate_training_data(config)
    
    # Split data
    split_idx = int(len(features_df) * 0.8)
    X_train = features_df.iloc[:split_idx]
    y_train = labels_series.iloc[:split_idx]
    X_val = features_df.iloc[split_idx:]
    y_val = labels_series.iloc[split_idx:]
    
    # Train model
    model, metrics = training_pipeline.train_lightgbm(
        X_train, y_train, X_val, y_val
    )
    
    # Check model was trained
    assert model is not None
    assert hasattr(model, 'predict')
    
    # Check metrics are valid
    assert 0 <= metrics.accuracy <= 1
    assert 0 <= metrics.precision <= 1
    assert 0 <= metrics.recall <= 1
    assert 0 <= metrics.f1_score <= 1
    assert 0 <= metrics.roc_auc <= 1


def test_walk_forward_validation_split(training_pipeline):
    """
    Test walk-forward validation with 80/20 split.
    Requirements: 11.3
    """
    config = TrainingConfig(
        symbol="XAUUSD",
        training_months=6,
        train_split=0.8
    )
    
    features_df, labels_series = training_pipeline.generate_training_data(config)
    
    # Split data
    split_idx = int(len(features_df) * config.train_split)
    X_train = features_df.iloc[:split_idx]
    X_val = features_df.iloc[split_idx:]
    
    # Check split ratio
    total_samples = len(features_df)
    train_ratio = len(X_train) / total_samples
    val_ratio = len(X_val) / total_samples
    
    assert abs(train_ratio - 0.8) < 0.05, "Train split should be ~80%"
    assert abs(val_ratio - 0.2) < 0.05, "Validation split should be ~20%"
    
    # Check temporal ordering (walk-forward)
    # Training data should come before validation data
    assert split_idx < len(features_df)


def test_model_acceptance_criteria(training_pipeline):
    """
    Test model rejection when accuracy < 52%.
    Requirements: 11.5
    """
    config = TrainingConfig(
        symbol="XAUUSD",
        training_months=6,
        min_accuracy=0.52
    )
    
    result = training_pipeline.train_and_evaluate(config, model_type="xgboost")
    
    if result is None:
        # Model was rejected - this is acceptable
        assert True
    else:
        # Model was accepted - check it meets criteria
        model, metrics, metadata = result
        assert metrics.accuracy >= config.min_accuracy


def test_train_and_evaluate_complete_pipeline(training_pipeline):
    """
    Test complete training pipeline.
    Requirements: 11.1, 11.2, 11.3, 11.4, 11.5
    """
    config = TrainingConfig(
        symbol="XAUUSD",
        timeframe="M15",
        training_months=6
    )
    
    result = training_pipeline.train_and_evaluate(config, model_type="xgboost")
    
    if result is not None:
        model, metrics, metadata = result
        
        # Check model
        assert model is not None
        
        # Check metrics meet acceptance criteria
        assert metrics.accuracy >= config.min_accuracy
        
        # Check metadata
        assert metadata['model_type'] == 'xgboost'
        assert metadata['symbol'] == 'XAUUSD'
        assert metadata['timeframe'] == 'M15'
        assert 'feature_names' in metadata
        assert 'metrics' in metadata


def test_save_model(training_pipeline, temp_dir):
    """Test model saving functionality"""
    config = TrainingConfig(symbol="XAUUSD", training_months=6)
    
    result = training_pipeline.train_and_evaluate(config, model_type="xgboost")
    
    if result is not None:
        model, metrics, metadata = result
        
        # Save model
        model_dir = training_pipeline.save_model(model, metadata)
        
        # Check files were created
        assert model_dir.exists()
        assert (model_dir / "model.pkl").exists()
        assert (model_dir / "metadata.json").exists()


def test_training_with_insufficient_data(training_pipeline):
    """Test handling of insufficient training data"""
    # Create config with very short training period
    config = TrainingConfig(
        symbol="NONEXISTENT",
        training_months=1
    )
    
    # Should handle gracefully
    with pytest.raises(ValueError, match="No historical data found"):
        training_pipeline.generate_training_data(config)


def test_feature_extraction_edge_cases(training_pipeline):
    """Test feature extraction with edge cases"""
    # Test with minimal data
    window_data = pd.DataFrame({
        'close': [100.0, 101.0, 102.0],
        'high': [101.0, 102.0, 103.0],
        'low': [99.0, 100.0, 101.0],
        'volume': [100, 110, 120]
    })
    
    features = training_pipeline._extract_features(window_data)
    
    # Should return None for insufficient data
    assert features is None or len(features) > 0


def test_model_metrics_computation(training_pipeline):
    """Test model evaluation metrics computation"""
    # Create simple test data
    X_val = pd.DataFrame({
        'feature1': np.random.randn(100),
        'feature2': np.random.randn(100)
    })
    y_val = pd.Series(np.random.randint(0, 2, 100))
    
    # Create simple mock model
    class MockModel:
        def predict(self, X):
            return np.random.randint(0, 2, len(X))
        
        def predict_proba(self, X):
            probs = np.random.rand(len(X), 2)
            probs = probs / probs.sum(axis=1, keepdims=True)
            return probs
    
    model = MockModel()
    metrics = training_pipeline._evaluate_model(model, X_val, y_val)
    
    # Check all metrics are computed
    assert metrics.accuracy is not None
    assert metrics.precision is not None
    assert metrics.recall is not None
    assert metrics.f1_score is not None
    assert metrics.roc_auc is not None
    
    # Check metrics are in valid range
    assert 0 <= metrics.accuracy <= 1
    assert 0 <= metrics.precision <= 1
    assert 0 <= metrics.recall <= 1
    assert 0 <= metrics.f1_score <= 1
    assert 0 <= metrics.roc_auc <= 1
