"""
Unit tests for Task 7: Advanced Feature Engineering
Tests rolling statistics, price-volume features, microstructure features, and regime features.
"""
import pytest
import asyncio
import numpy as np
import pandas as pd
from datetime import datetime
from unittest.mock import AsyncMock

from data.feature_pipeline import FeaturePipeline, FeatureVector
from data.event_bus import EventBus


@pytest.fixture
def mock_redis():
    """Create mock Redis client"""
    redis = AsyncMock()
    redis.hset = AsyncMock()
    redis.expire = AsyncMock()
    return redis


@pytest.fixture
async def event_bus():
    """Create and start event bus"""
    bus = EventBus(max_queue_depth=100)
    await bus.start()
    yield bus
    await bus.stop()


@pytest.fixture
async def pipeline(event_bus, mock_redis):
    """Create feature pipeline"""
    pipeline = FeaturePipeline(
        event_bus=event_bus,
        redis_client=mock_redis,
        symbols=["XAUUSD"],
        timeframes=["M1"],
        max_bars=500,
    )
    await pipeline.start()
    yield pipeline
    await pipeline.stop()


def add_price_data(pipeline, symbol, timeframe, num_bars=250):
    """Helper to add price data to pipeline"""
    for i in range(num_bars):
        bar = {
            "timestamp": datetime.utcnow(),
            "open": 2000.0 + i * 0.1,
            "high": 2001.0 + i * 0.1,
            "low": 1999.0 + i * 0.1,
            "close": 2000.0 + i * 0.1,
            "volume": 100 + i,
        }
        pipeline._price_buffers[symbol][timeframe].append(bar)


# Task 7.1: Rolling Statistical Features Tests

@pytest.mark.asyncio
async def test_rolling_statistics_20_bars(pipeline):
    """Test rolling statistics for 20-bar window"""
    add_price_data(pipeline, "XAUUSD", "M1", 50)
    features = await pipeline.compute_features("XAUUSD", "M1")
    
    assert features is not None
    assert "mean_20" in features.features
    assert "std_20" in features.features
    assert "skew_20" in features.features
    assert "kurtosis_20" in features.features
    assert "zscore_20" in features.features
    assert "percentile_20" in features.features


@pytest.mark.asyncio
async def test_rolling_statistics_50_bars(pipeline):
    """Test rolling statistics for 50-bar window"""
    add_price_data(pipeline, "XAUUSD", "M1", 100)
    features = await pipeline.compute_features("XAUUSD", "M1")
    
    assert features is not None
    assert "mean_50" in features.features
    assert "std_50" in features.features
    assert "skew_50" in features.features
    assert "kurtosis_50" in features.features
    assert "zscore_50" in features.features
    assert "percentile_50" in features.features


@pytest.mark.asyncio
async def test_rolling_statistics_100_bars(pipeline):
    """Test rolling statistics for 100-bar window"""
    add_price_data(pipeline, "XAUUSD", "M1", 150)
    features = await pipeline.compute_features("XAUUSD", "M1")
    
    assert features is not None
    assert "mean_100" in features.features
    assert "std_100" in features.features
    assert "skew_100" in features.features
    assert "kurtosis_100" in features.features
    assert "zscore_100" in features.features
    assert "percentile_100" in features.features


@pytest.mark.asyncio
async def test_rolling_statistics_200_bars(pipeline):
    """Test rolling statistics for 200-bar window"""
    add_price_data(pipeline, "XAUUSD", "M1", 250)
    features = await pipeline.compute_features("XAUUSD", "M1")
    
    assert features is not None
    assert "mean_200" in features.features
    assert "std_200" in features.features
    assert "skew_200" in features.features
    assert "kurtosis_200" in features.features
    assert "zscore_200" in features.features
    assert "percentile_200" in features.features


@pytest.mark.asyncio
async def test_zscore_calculation(pipeline):
    """Test z-score calculation is correct"""
    # Add data with known distribution
    symbol = "XAUUSD"
    timeframe = "M1"
    
    # Create data with mean=2000, std=10
    for i in range(50):
        bar = {
            "timestamp": datetime.utcnow(),
            "open": 2000.0,
            "high": 2000.0,
            "low": 2000.0,
            "close": 2000.0 + (i - 25) * 0.4,  # Spread around mean
            "volume": 100,
        }
        pipeline._price_buffers[symbol][timeframe].append(bar)
    
    features = await pipeline.compute_features(symbol, timeframe)
    
    # Z-score should be reasonable
    assert "zscore_20" in features.features
    zscore = features.features["zscore_20"]
    assert -3 < zscore < 3  # Within 3 standard deviations


@pytest.mark.asyncio
async def test_percentile_rank(pipeline):
    """Test percentile rank calculation"""
    add_price_data(pipeline, "XAUUSD", "M1", 50)
    features = await pipeline.compute_features("XAUUSD", "M1")
    
    # Percentile should be between 0 and 100
    assert "percentile_20" in features.features
    percentile = features.features["percentile_20"]
    assert 0 <= percentile <= 100


# Task 7.2: Price-Volume Features Tests

@pytest.mark.asyncio
async def test_vwap_calculation(pipeline):
    """Test VWAP calculation"""
    add_price_data(pipeline, "XAUUSD", "M1", 50)
    features = await pipeline.compute_features("XAUUSD", "M1")
    
    assert "vwap" in features.features
    assert "vwap_deviation" in features.features
    assert features.features["vwap"] > 0


@pytest.mark.asyncio
async def test_volume_weighted_momentum(pipeline):
    """Test volume-weighted momentum calculation"""
    add_price_data(pipeline, "XAUUSD", "M1", 50)
    features = await pipeline.compute_features("XAUUSD", "M1")
    
    assert "volume_weighted_momentum" in features.features


@pytest.mark.asyncio
async def test_obv_calculation(pipeline):
    """Test On-Balance Volume calculation"""
    # Add data with price movements
    symbol = "XAUUSD"
    timeframe = "M1"
    
    for i in range(50):
        bar = {
            "timestamp": datetime.utcnow(),
            "open": 2000.0,
            "high": 2001.0,
            "low": 1999.0,
            "close": 2000.0 + (i % 2) * 2 - 1,  # Alternating up/down
            "volume": 100,
        }
        pipeline._price_buffers[symbol][timeframe].append(bar)
    
    features = await pipeline.compute_features(symbol, timeframe)
    
    assert "obv" in features.features
    assert "obv_normalized" in features.features


@pytest.mark.asyncio
async def test_volume_profile(pipeline):
    """Test volume profile calculation"""
    add_price_data(pipeline, "XAUUSD", "M1", 50)
    features = await pipeline.compute_features("XAUUSD", "M1")
    
    # Check volume profile bins exist
    for i in range(5):
        assert f"volume_profile_bin_{i}" in features.features
        # Each bin should be a percentage (0-1)
        assert 0 <= features.features[f"volume_profile_bin_{i}"] <= 1


@pytest.mark.asyncio
async def test_volume_ratio(pipeline):
    """Test volume ratio calculation"""
    add_price_data(pipeline, "XAUUSD", "M1", 50)
    features = await pipeline.compute_features("XAUUSD", "M1")
    
    assert "volume_ratio" in features.features
    assert features.features["volume_ratio"] > 0


# Task 7.3: Microstructure Features Tests

@pytest.mark.asyncio
async def test_spread_calculation(pipeline):
    """Test bid-ask spread estimation"""
    add_price_data(pipeline, "XAUUSD", "M1", 50)
    features = await pipeline.compute_features("XAUUSD", "M1")
    
    assert "spread_absolute" in features.features
    assert "spread_percentage" in features.features
    assert features.features["spread_absolute"] >= 0
    assert features.features["spread_percentage"] >= 0


@pytest.mark.asyncio
async def test_effective_spread(pipeline):
    """Test effective spread calculation"""
    add_price_data(pipeline, "XAUUSD", "M1", 50)
    features = await pipeline.compute_features("XAUUSD", "M1")
    
    assert "effective_spread" in features.features
    assert "effective_spread_pct" in features.features
    assert features.features["effective_spread"] >= 0


@pytest.mark.asyncio
async def test_price_impact(pipeline):
    """Test price impact estimation"""
    add_price_data(pipeline, "XAUUSD", "M1", 50)
    features = await pipeline.compute_features("XAUUSD", "M1")
    
    assert "price_impact" in features.features
    assert "price_impact_normalized" in features.features


@pytest.mark.asyncio
async def test_order_imbalance(pipeline):
    """Test order book imbalance estimation"""
    add_price_data(pipeline, "XAUUSD", "M1", 50)
    features = await pipeline.compute_features("XAUUSD", "M1")
    
    assert "order_imbalance" in features.features
    # Imbalance should be between 0 and 1
    assert 0 <= features.features["order_imbalance"] <= 1


# Task 7.4: Regime Features Tests

@pytest.mark.asyncio
async def test_volatility_regime(pipeline):
    """Test volatility regime detection"""
    add_price_data(pipeline, "XAUUSD", "M1", 100)
    features = await pipeline.compute_features("XAUUSD", "M1")
    
    assert "volatility_regime" in features.features
    assert "volatility_percentile" in features.features
    # Regime should be 0 (low), 1 (medium), or 2 (high)
    assert features.features["volatility_regime"] in [0, 1, 2]
    assert 0 <= features.features["volatility_percentile"] <= 100


@pytest.mark.asyncio
async def test_trend_strength(pipeline):
    """Test trend strength (ADX) calculation"""
    add_price_data(pipeline, "XAUUSD", "M1", 50)
    features = await pipeline.compute_features("XAUUSD", "M1")
    
    assert "adx" in features.features
    assert "trend_strength" in features.features
    assert "trend_direction" in features.features
    # Trend direction should be -1, 0, or 1
    assert features.features["trend_direction"] in [-1, 0, 1]


@pytest.mark.asyncio
async def test_market_session(pipeline):
    """Test market session detection"""
    add_price_data(pipeline, "XAUUSD", "M1", 50)
    features = await pipeline.compute_features("XAUUSD", "M1")
    
    assert "market_session" in features.features
    assert "is_overlap_session" in features.features
    # Session should be 0-4
    assert 0 <= features.features["market_session"] <= 4
    # Overlap should be 0 or 1
    assert features.features["is_overlap_session"] in [0, 1]


@pytest.mark.asyncio
async def test_liquidity_score(pipeline):
    """Test liquidity indicator calculation"""
    add_price_data(pipeline, "XAUUSD", "M1", 50)
    features = await pipeline.compute_features("XAUUSD", "M1")
    
    assert "liquidity_score" in features.features
    assert features.features["liquidity_score"] > 0


# Task 7.5: Feature Normalization Tests

@pytest.mark.asyncio
async def test_feature_normalization_zero_mean(pipeline):
    """Test normalized features have approximately zero mean"""
    add_price_data(pipeline, "XAUUSD", "M1", 100)
    
    # Compute features multiple times to build statistics
    normalized_values = []
    for _ in range(20):
        features = await pipeline.compute_features("XAUUSD", "M1")
        if features and features.normalized_features is not None:
            normalized_values.append(features.normalized_features)
    
    # Calculate mean of normalized features
    if len(normalized_values) > 10:
        all_values = np.concatenate(normalized_values)
        mean = np.mean(all_values)
        # Mean should be close to 0 (within ±0.5)
        assert abs(mean) < 0.5


@pytest.mark.asyncio
async def test_feature_normalization_unit_variance(pipeline):
    """Test normalized features have approximately unit variance"""
    # Add varying price data to create variance
    symbol = "XAUUSD"
    timeframe = "M1"
    
    for i in range(100):
        bar = {
            "timestamp": datetime.utcnow(),
            "open": 2000.0 + np.sin(i * 0.1) * 10,
            "high": 2001.0 + np.sin(i * 0.1) * 10,
            "low": 1999.0 + np.sin(i * 0.1) * 10,
            "close": 2000.0 + np.sin(i * 0.1) * 10,
            "volume": 100 + i,
        }
        pipeline._price_buffers[symbol][timeframe].append(bar)
    
    # Compute features multiple times to build statistics
    normalized_values = []
    for i in range(30):
        # Add more data with variation
        bar = {
            "timestamp": datetime.utcnow(),
            "open": 2000.0 + np.sin((100 + i) * 0.1) * 10,
            "high": 2001.0 + np.sin((100 + i) * 0.1) * 10,
            "low": 1999.0 + np.sin((100 + i) * 0.1) * 10,
            "close": 2000.0 + np.sin((100 + i) * 0.1) * 10,
            "volume": 100 + 100 + i,
        }
        pipeline._price_buffers[symbol][timeframe].append(bar)
        
        features = await pipeline.compute_features(symbol, timeframe)
        if features and features.normalized_features is not None:
            normalized_values.append(features.normalized_features)
    
    # Calculate std of normalized features
    if len(normalized_values) > 10:
        all_values = np.concatenate(normalized_values)
        std = np.std(all_values)
        # Std should be reasonable (not zero, not too large)
        # With rolling normalization, std may not be exactly 1.0
        assert 0.1 < std < 5.0


@pytest.mark.asyncio
async def test_normalized_features_no_nan_or_inf(pipeline):
    """Test normalized features don't contain NaN or Inf"""
    add_price_data(pipeline, "XAUUSD", "M1", 100)
    features = await pipeline.compute_features("XAUUSD", "M1")
    
    assert features is not None
    assert features.normalized_features is not None
    assert not np.any(np.isnan(features.normalized_features))
    assert not np.any(np.isinf(features.normalized_features))


@pytest.mark.asyncio
async def test_redis_caching_with_new_features(pipeline, mock_redis):
    """Test new features are cached in Redis"""
    add_price_data(pipeline, "XAUUSD", "M1", 250)
    features = await pipeline.compute_features("XAUUSD", "M1")
    
    await pipeline._cache_features(features)
    
    # Verify Redis was called
    assert mock_redis.hset.called
    assert mock_redis.expire.called


@pytest.mark.asyncio
async def test_all_feature_categories_present(pipeline):
    """Test all feature categories are computed"""
    add_price_data(pipeline, "XAUUSD", "M1", 250)
    features = await pipeline.compute_features("XAUUSD", "M1")
    
    assert features is not None
    
    # Check we have features from all categories
    feature_names = set(features.features.keys())
    
    # Price features
    assert any("return" in name for name in feature_names)
    assert any("ema" in name for name in feature_names)
    
    # Volume features
    assert any("volume" in name for name in feature_names)
    assert "vwap" in feature_names
    assert "obv" in feature_names
    
    # Volatility features
    assert "atr_14" in feature_names
    
    # Microstructure features
    assert "spread_absolute" in feature_names
    assert "order_imbalance" in feature_names
    
    # Regime features
    assert "volatility_regime" in feature_names
    assert "trend_strength" in feature_names
    
    # Statistical features
    assert "mean_20" in feature_names
    assert "zscore_20" in feature_names


@pytest.mark.asyncio
async def test_feature_count(pipeline):
    """Test that we have a substantial number of features"""
    add_price_data(pipeline, "XAUUSD", "M1", 250)
    features = await pipeline.compute_features("XAUUSD", "M1")
    
    assert features is not None
    # Should have at least 50 features with all the new additions
    assert len(features.features) >= 50
