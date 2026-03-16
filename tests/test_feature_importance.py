"""
Unit tests for Feature Importance Analysis using SHAP values.

Tests Requirements: 15.1, 15.2, 15.3, 15.4
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path
import tempfile
import shutil
import os

# Import ML libraries at module level
xgboost = pytest.importorskip("xgboost")
lightgbm = pytest.importorskip("lightgbm")
shap = pytest.importorskip("shap")

from ml.feature_importance import (
    FeatureImportanceAnalyzer,
    FeatureImportanceResult
)


@pytest.fixture
def temp_dir():
    """Create temporary directory for test files"""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def sample_data():
    """Create sample feature data for testing"""
    np.random.seed(42)
    n_samples = 200
    n_features = 10
    
    # Create feature data
    X = pd.DataFrame(
        np.random.randn(n_samples, n_features),
        columns=[f'feature_{i}' for i in range(n_features)]
    )
    
    # Create target (binary classification)
    # Make it somewhat predictable based on features
    y = (X['feature_0'] + X['feature_1'] * 0.5 + np.random.randn(n_samples) * 0.1 > 0).astype(int)
    
    return X, y


@pytest.fixture
def trained_xgboost_model(sample_data):
    """Create a trained XGBoost model for testing"""
    X, y = sample_data
    
    # Train simple model
    model = xgboost.XGBClassifier(
        n_estimators=50,
        max_depth=3,
        learning_rate=0.1,
        random_state=42
    )
    model.fit(X, y)
    
    return model


@pytest.fixture
def trained_lightgbm_model(sample_data):
    """Create a trained LightGBM model for testing"""
    X, y = sample_data
    
    # Train simple model
    model = lightgbm.LGBMClassifier(
        n_estimators=50,
        max_depth=3,
        learning_rate=0.1,
        random_state=42,
        verbose=-1
    )
    model.fit(X, y)
    
    return model


@pytest.fixture
def analyzer(temp_dir):
    """Create FeatureImportanceAnalyzer instance"""
    return FeatureImportanceAnalyzer(model_dir=temp_dir)


def test_analyzer_initialization(temp_dir):
    """Test FeatureImportanceAnalyzer initialization"""
    analyzer = FeatureImportanceAnalyzer(model_dir=temp_dir)
    
    assert analyzer.model_dir == temp_dir
    assert os.path.exists(temp_dir)


def test_compute_shap_values_xgboost(analyzer, trained_xgboost_model, sample_data):
    """
    Test SHAP value computation for XGBoost model.
    Requirements: 15.1
    """
    X, _ = sample_data
    
    shap_values, explainer = analyzer.compute_shap_values(
        model=trained_xgboost_model,
        X=X,
        model_type="xgboost",
        max_samples=100
    )
    
    # Check SHAP values shape
    assert shap_values.shape[0] <= 100  # Respects max_samples
    assert shap_values.shape[1] == X.shape[1]  # One value per feature
    
    # Check SHAP values are numeric
    assert np.isfinite(shap_values).all()
    
    # Check explainer was created
    assert explainer is not None


def test_rank_features_by_shap(analyzer, trained_xgboost_model, sample_data):
    """
    Test feature ranking by mean absolute SHAP value.
    Requirements: 15.2
    """
    X, _ = sample_data
    
    # Compute SHAP values
    shap_values, _ = analyzer.compute_shap_values(
        model=trained_xgboost_model,
        X=X,
        model_type="xgboost"
    )
    
    # Rank features
    feature_rankings = analyzer.rank_features_by_shap(
        shap_values=shap_values,
        feature_names=list(X.columns)
    )
    
    # Check rankings structure
    assert len(feature_rankings) == X.shape[1]
    assert all(isinstance(item, tuple) for item in feature_rankings)
    assert all(len(item) == 2 for item in feature_rankings)
    
    # Check rankings are sorted (descending)
    importances = [item[1] for item in feature_rankings]
    assert importances == sorted(importances, reverse=True)
    
    # Check all importances are non-negative
    assert all(imp >= 0 for imp in importances)


def test_compute_interaction_values_xgboost(analyzer, trained_xgboost_model, sample_data):
    """
    Test SHAP interaction value computation for XGBoost.
    Requirements: 15.3
    """
    X, _ = sample_data
    
    interaction_values = analyzer.compute_interaction_values(
        model=trained_xgboost_model,
        X=X,
        model_type="xgboost",
        max_samples=50  # Small sample for speed
    )
    
    # Check interaction values shape (n_samples, n_features, n_features)
    assert interaction_values.shape[0] <= 50
    assert interaction_values.shape[1] == X.shape[1]
    assert interaction_values.shape[2] == X.shape[1]
    
    # Check values are numeric
    assert np.isfinite(interaction_values).all()


def test_generate_feature_importance_plots(analyzer, trained_xgboost_model, sample_data, temp_dir):
    """
    Test feature importance plot generation.
    Requirements: 15.4
    """
    X, _ = sample_data
    
    # Compute SHAP values
    shap_values, _ = analyzer.compute_shap_values(
        model=trained_xgboost_model,
        X=X,
        model_type="xgboost",
        max_samples=100
    )
    
    # Generate plots
    output_dir = os.path.join(temp_dir, "plots")
    plot_paths = analyzer.generate_feature_importance_plots(
        shap_values=shap_values,
        X=X.iloc[:len(shap_values)],
        feature_names=list(X.columns),
        output_dir=output_dir,
        top_n=10
    )
    
    # Check output directory was created
    assert os.path.exists(output_dir)
    
    # Check plot files were created
    assert 'bar_plot' in plot_paths
    assert 'summary_plot' in plot_paths
    assert 'waterfall_plot' in plot_paths
    
    # Check files exist
    for plot_type, plot_path in plot_paths.items():
        assert os.path.exists(plot_path)
        assert plot_path.endswith('.png')


def test_analyze_feature_importance_complete_pipeline(analyzer, trained_xgboost_model, sample_data):
    """
    Test complete feature importance analysis pipeline.
    Requirements: 15.1, 15.2, 15.3, 15.4
    """
    X, _ = sample_data
    
    result = analyzer.analyze_feature_importance(
        model=trained_xgboost_model,
        X=X,
        model_type="xgboost",
        model_id="test_model",
        compute_interactions=True,
        max_samples=100,
        top_n_features=10
    )
    
    # Check result structure
    assert isinstance(result, FeatureImportanceResult)
    
    # Check feature rankings
    assert len(result.feature_rankings) == X.shape[1]
    assert all(isinstance(item, tuple) for item in result.feature_rankings)
    
    # Check SHAP values
    assert result.shap_values.shape[1] == X.shape[1]
    
    # Check feature names
    assert result.feature_names == list(X.columns)
    
    # Check interaction values were computed
    assert result.interaction_values is not None
    
    # Check plots directory
    assert result.plots_dir is not None
    assert os.path.exists(result.plots_dir)


def test_get_top_feature_interactions(analyzer, trained_xgboost_model, sample_data):
    """
    Test identification of top feature interactions.
    Requirements: 15.3
    """
    X, _ = sample_data
    
    # Compute interaction values
    interaction_values = analyzer.compute_interaction_values(
        model=trained_xgboost_model,
        X=X,
        model_type="xgboost",
        max_samples=50
    )
    
    # Get top interactions
    top_interactions = analyzer.get_top_feature_interactions(
        interaction_values=interaction_values,
        feature_names=list(X.columns),
        top_n=5
    )
    
    # Check structure
    assert len(top_interactions) == 5
    assert all(isinstance(item, tuple) for item in top_interactions)
    assert all(len(item) == 3 for item in top_interactions)
    
    # Check interactions are sorted (descending)
    interaction_strengths = [item[2] for item in top_interactions]
    assert interaction_strengths == sorted(interaction_strengths, reverse=True)
    
    # Check all strengths are non-negative
    assert all(strength >= 0 for strength in interaction_strengths)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
