"""
Unit tests for Model Retraining Pipeline

Tests the automated model retraining pipeline including:
- Model retraining with 6 months of data
- Out-of-sample evaluation
- Model comparison and promotion logic
- Retraining result logging
"""

import pytest
import tempfile
import shutil
import json
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import numpy as np

from ml.model_retraining_pipeline import (
    ModelRetrainingPipeline,
    RetrainingResult,
    RetrainingStatus,
    PromotionDecision
)
from ml.model_registry import ModelRegistry, ModelMetadata, ModelType, DeploymentStatus


# Simple dummy model class that can be pickled
class DummyModel:
    """Dummy model for testing that can be pickled"""
    def __init__(self):
        self.params = {'max_depth': 5}
    
    def get_params(self):
        return self.params


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests"""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def model_registry(temp_dir):
    """Create test model registry"""
    db_path = Path(temp_dir) / "test_registry.db"
    models_root = Path(temp_dir) / "models"
    return ModelRegistry(db_path=str(db_path), models_root=str(models_root))


@pytest.fixture
def retraining_pipeline(model_registry, temp_dir):
    """Create test retraining pipeline"""
    data_path = Path(temp_dir) / "data"
    log_path = Path(temp_dir) / "retraining_log.jsonl"
    
    return ModelRetrainingPipeline(
        model_registry=model_registry,
        data_source_path=str(data_path),
        retraining_log_path=str(log_path),
        enable_scheduling=False  # Disable scheduling for tests
    )


class TestModelRetrainingPipeline:
    """Test suite for ModelRetrainingPipeline"""
    
    def test_initialization(self, retraining_pipeline, temp_dir):
        """Test pipeline initialization"""
        assert retraining_pipeline.model_registry is not None
        assert retraining_pipeline.retraining_log_path.parent.exists()
        assert retraining_pipeline.scheduler is None  # Disabled for tests
    
    def test_initialization_with_scheduling(self, model_registry, temp_dir):
        """Test pipeline initialization with scheduling enabled"""
        pipeline = ModelRetrainingPipeline(
            model_registry=model_registry,
            data_source_path=str(Path(temp_dir) / "data"),
            retraining_log_path=str(Path(temp_dir) / "log.jsonl"),
            enable_scheduling=True,
            schedule_day="monday",
            schedule_hour=3,
            schedule_minute=30
        )
        
        assert pipeline.scheduler is not None
        assert not pipeline.scheduler.running
    
    def test_scheduler_start_stop(self, model_registry, temp_dir):
        """Test scheduler start and stop"""
        pipeline = ModelRetrainingPipeline(
            model_registry=model_registry,
            data_source_path=str(Path(temp_dir) / "data"),
            retraining_log_path=str(Path(temp_dir) / "log.jsonl"),
            enable_scheduling=True
        )
        
        # Start scheduler
        pipeline.start_scheduler()
        assert pipeline.scheduler.running
        
        # Stop scheduler
        pipeline.stop_scheduler()
        assert not pipeline.scheduler.running
    
    @patch('ml.model_retraining_pipeline.SupervisedTrainingPipeline')
    def test_retrain_supervised_model(self, mock_training_pipeline, retraining_pipeline):
        """Test retraining a supervised model"""
        # Mock training pipeline
        mock_pipeline_instance = Mock()
        mock_training_pipeline.return_value = mock_pipeline_instance
        
        # Mock training data generation
        X_train = np.random.rand(100, 10)
        y_train = np.random.randint(0, 2, 100)
        X_val = np.random.rand(20, 10)
        y_val = np.random.randint(0, 2, 20)
        X_test = np.random.rand(20, 10)
        y_test = np.random.randint(0, 2, 20)
        feature_names = [f"feature_{i}" for i in range(10)]
        
        mock_pipeline_instance.generate_training_data.return_value = (
            X_train, y_train, X_val, y_val, X_test, y_test, feature_names
        )
        
        # Mock model training
        mock_model = DummyModel()
        train_metrics = {'accuracy': 0.85, 'precision': 0.83}
        val_metrics = {'accuracy': 0.82, 'precision': 0.80}
        test_metrics = {'accuracy': 0.81, 'precision': 0.79}
        
        mock_pipeline_instance.train_xgboost.return_value = (
            mock_model, train_metrics, val_metrics
        )
        mock_pipeline_instance._evaluate_model.return_value = test_metrics
        
        # Retrain model
        model_id, metrics = retraining_pipeline.retrain_model(
            model_type=ModelType.XGBOOST.value,
            training_months=6
        )
        
        # Verify results
        assert model_id is not None
        assert metrics == test_metrics
        assert 'accuracy' in metrics
        
        # Verify training pipeline was called correctly
        mock_pipeline_instance.generate_training_data.assert_called_once()
        mock_pipeline_instance.train_xgboost.assert_called_once()
    
    def test_compare_models_with_improvement(self, retraining_pipeline, model_registry):
        """Test comparing models when retrained model improves"""
        # Create current model
        current_metadata = ModelMetadata(
            model_id="current_123",
            model_name="xgboost_current",
            model_type=ModelType.XGBOOST.value,
            version=1,
            created_at=datetime.now() - timedelta(days=30),
            training_start_date=datetime.now() - timedelta(days=210),
            training_end_date=datetime.now() - timedelta(days=30),
            num_training_samples=1000,
            hyperparameters={},
            feature_names=["f1", "f2"],
            num_features=2,
            train_metrics={'accuracy': 0.80},
            validation_metrics={'accuracy': 0.78},
            test_metrics={'accuracy': 0.77},  # Current: 77%
            deployment_status=DeploymentStatus.PRODUCTION.value
        )
        
        current_model_bytes = pickle.dumps(DummyModel())
        current_id = model_registry.register_model(current_metadata, current_model_bytes)
        
        # Create retrained model with improvement
        retrained_metadata = ModelMetadata(
            model_id="retrained_456",
            model_name="xgboost_retrained",
            model_type=ModelType.XGBOOST.value,
            version=2,
            created_at=datetime.now(),
            training_start_date=datetime.now() - timedelta(days=180),
            training_end_date=datetime.now(),
            num_training_samples=1000,
            hyperparameters={},
            feature_names=["f1", "f2"],
            num_features=2,
            train_metrics={'accuracy': 0.82},
            validation_metrics={'accuracy': 0.80},
            test_metrics={'accuracy': 0.79},  # Retrained: 79% (2.6% improvement)
            deployment_status=DeploymentStatus.TRAINING.value
        )
        
        retrained_model_bytes = pickle.dumps(DummyModel())
        retrained_id = model_registry.register_model(retrained_metadata, retrained_model_bytes)
        
        # Compare models
        improvement_pct, should_promote = retraining_pipeline.compare_models(
            retrained_model_id=retrained_id,
            current_model_id=current_id,
            primary_metric="accuracy"
        )
        
        # Verify results
        assert improvement_pct > 2.0  # Should be ~2.6%
        assert should_promote is True
    
    def test_compare_models_without_improvement(self, retraining_pipeline, model_registry):
        """Test comparing models when retrained model doesn't improve enough"""
        # Create current model
        current_metadata = ModelMetadata(
            model_id="current_123",
            model_name="xgboost_current",
            model_type=ModelType.XGBOOST.value,
            version=1,
            created_at=datetime.now() - timedelta(days=30),
            training_start_date=datetime.now() - timedelta(days=210),
            training_end_date=datetime.now() - timedelta(days=30),
            num_training_samples=1000,
            hyperparameters={},
            feature_names=["f1", "f2"],
            num_features=2,
            train_metrics={'accuracy': 0.80},
            validation_metrics={'accuracy': 0.78},
            test_metrics={'accuracy': 0.77},  # Current: 77%
            deployment_status=DeploymentStatus.PRODUCTION.value
        )
        
        current_model_bytes = pickle.dumps(DummyModel())
        current_id = model_registry.register_model(current_metadata, current_model_bytes)
        
        # Create retrained model with small improvement
        retrained_metadata = ModelMetadata(
            model_id="retrained_456",
            model_name="xgboost_retrained",
            model_type=ModelType.XGBOOST.value,
            version=2,
            created_at=datetime.now(),
            training_start_date=datetime.now() - timedelta(days=180),
            training_end_date=datetime.now(),
            num_training_samples=1000,
            hyperparameters={},
            feature_names=["f1", "f2"],
            num_features=2,
            train_metrics={'accuracy': 0.81},
            validation_metrics={'accuracy': 0.79},
            test_metrics={'accuracy': 0.775},  # Retrained: 77.5% (0.65% improvement)
            deployment_status=DeploymentStatus.TRAINING.value
        )
        
        retrained_model_bytes = pickle.dumps(DummyModel())
        retrained_id = model_registry.register_model(retrained_metadata, retrained_model_bytes)
        
        # Compare models
        improvement_pct, should_promote = retraining_pipeline.compare_models(
            retrained_model_id=retrained_id,
            current_model_id=current_id,
            primary_metric="accuracy"
        )
        
        # Verify results
        assert improvement_pct < 2.0  # Should be ~0.65%
        assert should_promote is False
    
    def test_promote_model(self, retraining_pipeline, model_registry):
        """Test promoting a model to production"""
        # Create a model
        metadata = ModelMetadata(
            model_id="test_123",
            model_name="xgboost_test",
            model_type=ModelType.XGBOOST.value,
            version=1,
            created_at=datetime.now(),
            training_start_date=datetime.now() - timedelta(days=180),
            training_end_date=datetime.now(),
            num_training_samples=1000,
            hyperparameters={},
            feature_names=["f1", "f2"],
            num_features=2,
            train_metrics={'accuracy': 0.80},
            validation_metrics={'accuracy': 0.78},
            test_metrics={'accuracy': 0.77},
            deployment_status=DeploymentStatus.TRAINING.value
        )
        
        model_bytes = pickle.dumps(DummyModel())
        model_id = model_registry.register_model(metadata, model_bytes)
        
        # Promote model
        retraining_pipeline.promote_model(model_id, environment="PAPER")
        
        # Verify promotion
        promoted_metadata, _ = model_registry.get_model(model_id)
        assert promoted_metadata.deployment_status == DeploymentStatus.PRODUCTION.value
        assert promoted_metadata.deployment_environment == "PAPER"
        assert promoted_metadata.deployment_timestamp is not None
    
    def test_log_retraining_result(self, retraining_pipeline):
        """Test logging retraining results"""
        result = RetrainingResult(
            job_id="test_job_123",
            model_type=ModelType.XGBOOST.value,
            timestamp=datetime.now(),
            status=RetrainingStatus.COMPLETED.value,
            retrained_model_id="retrained_123",
            current_model_id="current_456",
            retrained_metrics={'accuracy': 0.79},
            current_metrics={'accuracy': 0.77},
            promotion_decision=PromotionDecision.PROMOTED.value,
            performance_improvement_pct=2.6
        )
        
        # Log result
        retraining_pipeline._log_retraining_result(result)
        
        # Verify log file exists and contains result
        assert retraining_pipeline.retraining_log_path.exists()
        
        with open(retraining_pipeline.retraining_log_path, 'r') as f:
            log_line = f.readline()
            logged_data = json.loads(log_line)
            
            assert logged_data['job_id'] == "test_job_123"
            assert logged_data['model_type'] == ModelType.XGBOOST.value
            assert logged_data['status'] == RetrainingStatus.COMPLETED.value
            assert logged_data['promotion_decision'] == PromotionDecision.PROMOTED.value
    
    def test_get_retraining_history(self, retraining_pipeline):
        """Test retrieving retraining history"""
        # Log multiple results
        for i in range(5):
            result = RetrainingResult(
                job_id=f"job_{i}",
                model_type=ModelType.XGBOOST.value if i % 2 == 0 else ModelType.LIGHTGBM.value,
                timestamp=datetime.now() - timedelta(days=i),
                status=RetrainingStatus.COMPLETED.value,
                retrained_model_id=f"model_{i}",
                retrained_metrics={'accuracy': 0.75 + i * 0.01},
                promotion_decision=PromotionDecision.PROMOTED.value if i % 2 == 0 else PromotionDecision.KEPT_CURRENT.value
            )
            retraining_pipeline._log_retraining_result(result)
        
        # Get all history
        history = retraining_pipeline.get_retraining_history()
        assert len(history) == 5
        
        # Verify most recent first
        assert history[0].job_id == "job_4"
        assert history[-1].job_id == "job_0"
        
        # Get filtered history
        xgboost_history = retraining_pipeline.get_retraining_history(
            model_type=ModelType.XGBOOST.value
        )
        assert len(xgboost_history) == 3  # jobs 0, 2, 4
        assert all(h.model_type == ModelType.XGBOOST.value for h in xgboost_history)
    
    def test_get_retraining_history_empty(self, retraining_pipeline):
        """Test retrieving history when log file doesn't exist"""
        history = retraining_pipeline.get_retraining_history()
        assert len(history) == 0
    
    @patch('ml.model_retraining_pipeline.SupervisedTrainingPipeline')
    def test_retrain_and_evaluate_no_current_model(
        self,
        mock_training_pipeline,
        retraining_pipeline,
        model_registry
    ):
        """Test retraining when no current production model exists"""
        # Mock training pipeline
        mock_pipeline_instance = Mock()
        mock_training_pipeline.return_value = mock_pipeline_instance
        
        # Mock training data and model
        X_train = np.random.rand(100, 10)
        y_train = np.random.randint(0, 2, 100)
        X_val = np.random.rand(20, 10)
        y_val = np.random.randint(0, 2, 20)
        X_test = np.random.rand(20, 10)
        y_test = np.random.randint(0, 2, 20)
        feature_names = [f"feature_{i}" for i in range(10)]
        
        mock_pipeline_instance.generate_training_data.return_value = (
            X_train, y_train, X_val, y_val, X_test, y_test, feature_names
        )
        
        mock_model = DummyModel()
        train_metrics = {'accuracy': 0.85}
        val_metrics = {'accuracy': 0.82}
        test_metrics = {'accuracy': 0.81}
        
        mock_pipeline_instance.train_xgboost.return_value = (
            mock_model, train_metrics, val_metrics
        )
        mock_pipeline_instance._evaluate_model.return_value = test_metrics
        
        # Run retraining
        result = retraining_pipeline.retrain_and_evaluate_model(
            model_type=ModelType.XGBOOST.value,
            auto_promote=True
        )
        
        # Verify result
        assert result.status == RetrainingStatus.COMPLETED.value
        assert result.promotion_decision == PromotionDecision.NO_CURRENT_MODEL.value
        assert result.retrained_model_id is not None
        assert result.current_model_id is None
        
        # Verify model was promoted
        promoted_model = model_registry.get_current_production_model(ModelType.XGBOOST.value)
        assert promoted_model is not None
        assert promoted_model.model_id == result.retrained_model_id
    
    def test_retraining_result_to_dict(self):
        """Test RetrainingResult serialization"""
        result = RetrainingResult(
            job_id="test_job",
            model_type=ModelType.XGBOOST.value,
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            status=RetrainingStatus.COMPLETED.value,
            retrained_model_id="retrained_123",
            current_model_id="current_456",
            retrained_metrics={'accuracy': 0.79},
            current_metrics={'accuracy': 0.77},
            promotion_decision=PromotionDecision.PROMOTED.value,
            performance_improvement_pct=2.6
        )
        
        result_dict = result.to_dict()
        
        assert result_dict['job_id'] == "test_job"
        assert result_dict['timestamp'] == "2024-01-15T10:30:00"
        assert result_dict['performance_improvement_pct'] == 2.6
    
    def test_invalid_model_type(self, retraining_pipeline):
        """Test retraining with invalid model type"""
        with pytest.raises(ValueError, match="Unknown model type"):
            retraining_pipeline.retrain_model("INVALID_TYPE")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
