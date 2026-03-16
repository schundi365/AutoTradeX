"""
Unit Tests for Model Registry

Tests model registration, retrieval, deployment tagging, and metadata tracking.
"""

import pytest
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path
import pickle

from ml.model_registry import (
    ModelRegistry,
    ModelMetadata,
    ModelType,
    DeploymentStatus,
    DeploymentEnvironment
)


@pytest.fixture
def temp_registry():
    """Create a temporary model registry for testing"""
    temp_dir = tempfile.mkdtemp()
    registry = ModelRegistry(
        db_path=f"{temp_dir}/registry.db",
        models_root=temp_dir
    )
    yield registry
    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_metadata():
    """Create sample model metadata"""
    return ModelMetadata(
        model_id="",  # Will be generated
        model_name="test_xgboost",
        model_type=ModelType.XGBOOST.value,
        version=1,
        created_at=datetime.now(),
        training_start_date=datetime.now() - timedelta(days=180),
        training_end_date=datetime.now(),
        num_training_samples=10000,
        hyperparameters={
            'max_depth': 5,
            'learning_rate': 0.05,
            'n_estimators': 200
        },
        feature_names=['rsi_14', 'ema_20', 'volume_ratio', 'volatility_20'],
        num_features=4,
        train_metrics={
            'accuracy': 0.65,
            'precision': 0.63,
            'recall': 0.67,
            'f1_score': 0.65,
            'roc_auc': 0.70
        },
        validation_metrics={
            'accuracy': 0.58,
            'precision': 0.56,
            'recall': 0.60,
            'f1_score': 0.58,
            'roc_auc': 0.62
        },
        test_metrics={
            'accuracy': 0.57,
            'precision': 0.55,
            'recall': 0.59,
            'f1_score': 0.57,
            'roc_auc': 0.61
        },
        deployment_status=DeploymentStatus.TRAINING.value,
        git_commit_hash="abc123def456",
        training_script_path="ml/supervised_training.py"
    )


@pytest.fixture
def sample_model_file():
    """Create a sample model file (pickled dict)"""
    model = {'type': 'xgboost', 'params': {'max_depth': 5}}
    return pickle.dumps(model)


class TestModelRegistration:
    """Test model registration functionality"""
    
    def test_register_model_generates_uuid(self, temp_registry, sample_metadata, sample_model_file):
        """Test that registering a model generates a unique UUID"""
        model_id = temp_registry.register_model(sample_metadata, sample_model_file)
        
        assert model_id is not None
        assert len(model_id) == 36  # UUID format
        assert sample_metadata.model_id == model_id
    
    def test_register_model_creates_directory(self, temp_registry, sample_metadata, sample_model_file):
        """Test that registering a model creates the correct directory structure"""
        model_id = temp_registry.register_model(sample_metadata, sample_model_file)
        
        # Check that supervised directory exists
        supervised_dir = Path(temp_registry.models_root) / "supervised"
        assert supervised_dir.exists()
        
        # Check that model directory was created
        model_dirs = list(supervised_dir.glob("test_xgboost_v1_*"))
        assert len(model_dirs) == 1
        
        # Check that model file exists
        model_file = model_dirs[0] / "model.pkl"
        assert model_file.exists()
        
        # Check that metadata file exists
        metadata_file = model_dirs[0] / "metadata.json"
        assert metadata_file.exists()
    
    def test_register_model_stores_in_database(self, temp_registry, sample_metadata, sample_model_file):
        """Test that registering a model stores metadata in database"""
        model_id = temp_registry.register_model(sample_metadata, sample_model_file)
        
        # Retrieve model
        retrieved_metadata, _ = temp_registry.get_model(model_id)
        
        assert retrieved_metadata.model_id == model_id
        assert retrieved_metadata.model_name == sample_metadata.model_name
        assert retrieved_metadata.model_type == sample_metadata.model_type
        assert retrieved_metadata.version == sample_metadata.version
    
    def test_register_reinforcement_model(self, temp_registry, sample_model_file):
        """Test registering a reinforcement learning model"""
        metadata = ModelMetadata(
            model_id="",
            model_name="test_ppo",
            model_type=ModelType.PPO.value,
            version=1,
            created_at=datetime.now(),
            training_start_date=datetime.now() - timedelta(days=30),
            training_end_date=datetime.now(),
            num_training_samples=100000,
            hyperparameters={'learning_rate': 3e-4, 'n_steps': 2048},
            feature_names=['state_1', 'state_2'],
            num_features=2,
            train_metrics={'sharpe_ratio': 1.8},
            validation_metrics={'sharpe_ratio': 1.6},
            test_metrics={'sharpe_ratio': 1.5},
            deployment_status=DeploymentStatus.TRAINING.value
        )
        
        model_id = temp_registry.register_model(metadata, sample_model_file)
        
        # Check that reinforcement directory exists
        rl_dir = Path(temp_registry.models_root) / "reinforcement"
        assert rl_dir.exists()
        
        # Check that model file has .zip extension
        model_dirs = list(rl_dir.glob("test_ppo_v1_*"))
        assert len(model_dirs) == 1
        model_file = model_dirs[0] / "model.zip"
        assert model_file.exists()


class TestModelRetrieval:
    """Test model retrieval functionality"""
    
    def test_get_model_returns_metadata_and_file(self, temp_registry, sample_metadata, sample_model_file):
        """Test that get_model returns both metadata and model file"""
        model_id = temp_registry.register_model(sample_metadata, sample_model_file)
        
        metadata, model_file = temp_registry.get_model(model_id)
        
        assert metadata.model_id == model_id
        assert model_file == sample_model_file
    
    def test_get_model_raises_error_for_invalid_id(self, temp_registry):
        """Test that get_model raises error for non-existent model"""
        with pytest.raises(ValueError, match="Model not found"):
            temp_registry.get_model("invalid-uuid")
    
    def test_list_models_returns_all_models(self, temp_registry, sample_model_file):
        """Test that list_models returns all registered models"""
        # Register multiple models
        metadata1 = ModelMetadata(
            model_id="",
            model_name="model_1",
            model_type=ModelType.XGBOOST.value,
            version=1,
            created_at=datetime.now(),
            training_start_date=datetime.now() - timedelta(days=180),
            training_end_date=datetime.now(),
            num_training_samples=10000,
            hyperparameters={},
            feature_names=['f1'],
            num_features=1,
            train_metrics={'accuracy': 0.6},
            validation_metrics={'accuracy': 0.55},
            test_metrics={'accuracy': 0.54},
            deployment_status=DeploymentStatus.TRAINING.value
        )
        
        metadata2 = ModelMetadata(
            model_id="",
            model_name="model_2",
            model_type=ModelType.LIGHTGBM.value,
            version=1,
            created_at=datetime.now(),
            training_start_date=datetime.now() - timedelta(days=180),
            training_end_date=datetime.now(),
            num_training_samples=10000,
            hyperparameters={},
            feature_names=['f1'],
            num_features=1,
            train_metrics={'accuracy': 0.6},
            validation_metrics={'accuracy': 0.55},
            test_metrics={'accuracy': 0.54},
            deployment_status=DeploymentStatus.TRAINING.value
        )
        
        temp_registry.register_model(metadata1, sample_model_file)
        temp_registry.register_model(metadata2, sample_model_file)
        
        models = temp_registry.list_models()
        
        assert len(models) == 2
        assert any(m.model_name == "model_1" for m in models)
        assert any(m.model_name == "model_2" for m in models)
    
    def test_list_models_with_filters(self, temp_registry, sample_model_file):
        """Test that list_models filters correctly"""
        # Register models with different types
        metadata1 = ModelMetadata(
            model_id="",
            model_name="xgb_model",
            model_type=ModelType.XGBOOST.value,
            version=1,
            created_at=datetime.now(),
            training_start_date=datetime.now() - timedelta(days=180),
            training_end_date=datetime.now(),
            num_training_samples=10000,
            hyperparameters={},
            feature_names=['f1'],
            num_features=1,
            train_metrics={'accuracy': 0.6},
            validation_metrics={'accuracy': 0.55},
            test_metrics={'accuracy': 0.54},
            deployment_status=DeploymentStatus.PRODUCTION.value
        )
        
        metadata2 = ModelMetadata(
            model_id="",
            model_name="lgb_model",
            model_type=ModelType.LIGHTGBM.value,
            version=1,
            created_at=datetime.now(),
            training_start_date=datetime.now() - timedelta(days=180),
            training_end_date=datetime.now(),
            num_training_samples=10000,
            hyperparameters={},
            feature_names=['f1'],
            num_features=1,
            train_metrics={'accuracy': 0.6},
            validation_metrics={'accuracy': 0.55},
            test_metrics={'accuracy': 0.54},
            deployment_status=DeploymentStatus.TRAINING.value
        )
        
        temp_registry.register_model(metadata1, sample_model_file)
        temp_registry.register_model(metadata2, sample_model_file)
        
        # Filter by model type
        xgb_models = temp_registry.list_models(filters={'model_type': ModelType.XGBOOST.value})
        assert len(xgb_models) == 1
        assert xgb_models[0].model_name == "xgb_model"
        
        # Filter by deployment status
        prod_models = temp_registry.list_models(filters={'deployment_status': DeploymentStatus.PRODUCTION.value})
        assert len(prod_models) == 1
        assert prod_models[0].model_name == "xgb_model"


class TestDeploymentManagement:
    """Test deployment status and tagging functionality"""
    
    def test_update_deployment_status(self, temp_registry, sample_metadata, sample_model_file):
        """Test updating deployment status"""
        model_id = temp_registry.register_model(sample_metadata, sample_model_file)
        
        # Update to TESTING
        temp_registry.update_deployment_status(
            model_id,
            DeploymentStatus.TESTING.value,
            DeploymentEnvironment.PAPER.value
        )
        
        # Retrieve and verify
        metadata, _ = temp_registry.get_model(model_id)
        assert metadata.deployment_status == DeploymentStatus.TESTING.value
        assert metadata.deployment_environment == DeploymentEnvironment.PAPER.value
        assert metadata.deployment_timestamp is not None
    
    def test_update_deployment_to_production(self, temp_registry, sample_metadata, sample_model_file):
        """Test deploying model to production"""
        model_id = temp_registry.register_model(sample_metadata, sample_model_file)
        
        # Update to PRODUCTION
        temp_registry.update_deployment_status(
            model_id,
            DeploymentStatus.PRODUCTION.value,
            DeploymentEnvironment.LIVE.value
        )
        
        # Retrieve and verify
        metadata, _ = temp_registry.get_model(model_id)
        assert metadata.deployment_status == DeploymentStatus.PRODUCTION.value
        assert metadata.deployment_environment == DeploymentEnvironment.LIVE.value
        assert metadata.deployment_timestamp is not None
    
    def test_update_deployment_status_validates_status(self, temp_registry, sample_metadata, sample_model_file):
        """Test that invalid deployment status raises error"""
        model_id = temp_registry.register_model(sample_metadata, sample_model_file)
        
        with pytest.raises(ValueError, match="Invalid deployment status"):
            temp_registry.update_deployment_status(model_id, "INVALID_STATUS")
    
    def test_update_deployment_status_validates_environment(self, temp_registry, sample_metadata, sample_model_file):
        """Test that invalid deployment environment raises error"""
        model_id = temp_registry.register_model(sample_metadata, sample_model_file)
        
        with pytest.raises(ValueError, match="Invalid deployment environment"):
            temp_registry.update_deployment_status(
                model_id,
                DeploymentStatus.PRODUCTION.value,
                "INVALID_ENV"
            )
    
    def test_get_current_production_model(self, temp_registry, sample_model_file):
        """Test retrieving current production model"""
        # Register two models of same type
        metadata1 = ModelMetadata(
            model_id="",
            model_name="model_v1",
            model_type=ModelType.XGBOOST.value,
            version=1,
            created_at=datetime.now() - timedelta(days=7),
            training_start_date=datetime.now() - timedelta(days=180),
            training_end_date=datetime.now() - timedelta(days=7),
            num_training_samples=10000,
            hyperparameters={},
            feature_names=['f1'],
            num_features=1,
            train_metrics={'accuracy': 0.6},
            validation_metrics={'accuracy': 0.55},
            test_metrics={'accuracy': 0.54},
            deployment_status=DeploymentStatus.RETIRED.value
        )
        
        metadata2 = ModelMetadata(
            model_id="",
            model_name="model_v2",
            model_type=ModelType.XGBOOST.value,
            version=2,
            created_at=datetime.now(),
            training_start_date=datetime.now() - timedelta(days=180),
            training_end_date=datetime.now(),
            num_training_samples=10000,
            hyperparameters={},
            feature_names=['f1'],
            num_features=1,
            train_metrics={'accuracy': 0.65},
            validation_metrics={'accuracy': 0.60},
            test_metrics={'accuracy': 0.59},
            deployment_status=DeploymentStatus.PRODUCTION.value
        )
        
        temp_registry.register_model(metadata1, sample_model_file)
        model_id2 = temp_registry.register_model(metadata2, sample_model_file)
        
        # Get current production model
        prod_model = temp_registry.get_current_production_model(ModelType.XGBOOST.value)
        
        assert prod_model is not None
        assert prod_model.model_id == model_id2
        assert prod_model.model_name == "model_v2"
        assert prod_model.version == 2
    
    def test_get_current_production_model_returns_none_if_not_found(self, temp_registry):
        """Test that get_current_production_model returns None if no production model exists"""
        prod_model = temp_registry.get_current_production_model(ModelType.XGBOOST.value)
        assert prod_model is None


class TestMetadataTracking:
    """Test comprehensive metadata tracking"""
    
    def test_metadata_includes_hyperparameters(self, temp_registry, sample_metadata, sample_model_file):
        """Test that hyperparameters are stored and retrieved correctly"""
        model_id = temp_registry.register_model(sample_metadata, sample_model_file)
        
        metadata, _ = temp_registry.get_model(model_id)
        
        assert metadata.hyperparameters == sample_metadata.hyperparameters
        assert metadata.hyperparameters['max_depth'] == 5
        assert metadata.hyperparameters['learning_rate'] == 0.05
    
    def test_metadata_includes_training_data_range(self, temp_registry, sample_metadata, sample_model_file):
        """Test that training data date range is stored"""
        model_id = temp_registry.register_model(sample_metadata, sample_model_file)
        
        metadata, _ = temp_registry.get_model(model_id)
        
        assert metadata.training_start_date is not None
        assert metadata.training_end_date is not None
        assert metadata.num_training_samples == 10000
    
    def test_metadata_includes_feature_list(self, temp_registry, sample_metadata, sample_model_file):
        """Test that feature list is stored"""
        model_id = temp_registry.register_model(sample_metadata, sample_model_file)
        
        metadata, _ = temp_registry.get_model(model_id)
        
        assert metadata.feature_names == sample_metadata.feature_names
        assert metadata.num_features == 4
        assert 'rsi_14' in metadata.feature_names
    
    def test_metadata_includes_performance_metrics(self, temp_registry, sample_metadata, sample_model_file):
        """Test that train/val/test metrics are stored"""
        model_id = temp_registry.register_model(sample_metadata, sample_model_file)
        
        metadata, _ = temp_registry.get_model(model_id)
        
        assert metadata.train_metrics['accuracy'] == 0.65
        assert metadata.validation_metrics['accuracy'] == 0.58
        assert metadata.test_metrics['accuracy'] == 0.57
    
    def test_metadata_includes_git_commit_hash(self, temp_registry, sample_metadata, sample_model_file):
        """Test that git commit hash is stored"""
        model_id = temp_registry.register_model(sample_metadata, sample_model_file)
        
        metadata, _ = temp_registry.get_model(model_id)
        
        assert metadata.git_commit_hash == "abc123def456"
        assert metadata.training_script_path == "ml/supervised_training.py"


class TestRegistryUtilities:
    """Test utility functions"""
    
    def test_get_registry_stats(self, temp_registry, sample_model_file):
        """Test getting registry statistics"""
        # Register multiple models
        for i in range(3):
            metadata = ModelMetadata(
                model_id="",
                model_name=f"model_{i}",
                model_type=ModelType.XGBOOST.value if i < 2 else ModelType.LIGHTGBM.value,
                version=1,
                created_at=datetime.now(),
                training_start_date=datetime.now() - timedelta(days=180),
                training_end_date=datetime.now(),
                num_training_samples=10000,
                hyperparameters={},
                feature_names=['f1'],
                num_features=1,
                train_metrics={'accuracy': 0.6},
                validation_metrics={'accuracy': 0.55},
                test_metrics={'accuracy': 0.54},
                deployment_status=DeploymentStatus.TRAINING.value if i < 2 else DeploymentStatus.PRODUCTION.value
            )
            temp_registry.register_model(metadata, sample_model_file)
        
        stats = temp_registry.get_registry_stats()
        
        assert stats['total_models'] == 3
        assert stats['by_type'][ModelType.XGBOOST.value] == 2
        assert stats['by_type'][ModelType.LIGHTGBM.value] == 1
        assert stats['by_status'][DeploymentStatus.TRAINING.value] == 2
        assert stats['by_status'][DeploymentStatus.PRODUCTION.value] == 1
        assert stats['storage_size_mb'] > 0
    
    def test_delete_model(self, temp_registry, sample_metadata, sample_model_file):
        """Test deleting a model"""
        model_id = temp_registry.register_model(sample_metadata, sample_model_file)
        
        # Verify model exists
        metadata, _ = temp_registry.get_model(model_id)
        assert metadata.model_id == model_id
        
        # Delete model
        temp_registry.delete_model(model_id, delete_files=True)
        
        # Verify model is deleted
        with pytest.raises(ValueError, match="Model not found"):
            temp_registry.get_model(model_id)
    
    def test_get_model_history(self, temp_registry, sample_model_file):
        """Test getting version history for a model"""
        # Register multiple versions of same model
        for version in [1, 2, 3]:
            metadata = ModelMetadata(
                model_id="",
                model_name="my_model",
                model_type=ModelType.XGBOOST.value,
                version=version,
                created_at=datetime.now() + timedelta(days=version),
                training_start_date=datetime.now() - timedelta(days=180),
                training_end_date=datetime.now(),
                num_training_samples=10000,
                hyperparameters={},
                feature_names=['f1'],
                num_features=1,
                train_metrics={'accuracy': 0.6 + version * 0.01},
                validation_metrics={'accuracy': 0.55 + version * 0.01},
                test_metrics={'accuracy': 0.54 + version * 0.01},
                deployment_status=DeploymentStatus.TRAINING.value
            )
            temp_registry.register_model(metadata, sample_model_file)
        
        history = temp_registry.get_model_history("my_model")
        
        assert len(history) == 3
        # Should be ordered by created_at DESC (newest first)
        assert history[0].version == 3
        assert history[1].version == 2
        assert history[2].version == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
