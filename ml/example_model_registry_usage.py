"""
Example Usage of Model Registry

Demonstrates how to use the ModelRegistry for:
- Registering trained models
- Retrieving models
- Managing deployment status
- Tracking model versions
"""

import pickle
from datetime import datetime, timedelta
from ml.model_registry import (
    ModelRegistry,
    ModelMetadata,
    ModelType,
    DeploymentStatus,
    DeploymentEnvironment
)


def example_register_supervised_model():
    """Example: Register a supervised learning model"""
    print("\n=== Example 1: Register Supervised Model ===")
    
    # Initialize registry
    registry = ModelRegistry()
    
    # Create model metadata
    metadata = ModelMetadata(
        model_id="",  # Will be auto-generated
        model_name="xgboost_eurusd_predictor",
        model_type=ModelType.XGBOOST.value,
        version=1,
        created_at=datetime.now(),
        training_start_date=datetime.now() - timedelta(days=180),
        training_end_date=datetime.now(),
        num_training_samples=50000,
        hyperparameters={
            'max_depth': 5,
            'learning_rate': 0.05,
            'n_estimators': 200,
            'min_child_weight': 3,
            'subsample': 0.9,
            'colsample_bytree': 0.9
        },
        feature_names=[
            'rsi_14', 'ema_20', 'ema_50', 'volume_ratio',
            'volatility_20', 'return_1bar', 'return_5bar'
        ],
        num_features=7,
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
        git_commit_hash="abc123def456789",
        training_script_path="ml/supervised_training.py"
    )
    
    # Create a dummy model file (in practice, this would be your trained model)
    dummy_model = {
        'type': 'xgboost',
        'params': metadata.hyperparameters,
        'features': metadata.feature_names
    }
    model_file = pickle.dumps(dummy_model)
    
    # Register model
    model_id = registry.register_model(metadata, model_file)
    
    print(f"Model registered successfully!")
    print(f"Model ID: {model_id}")
    print(f"Model Name: {metadata.model_name}")
    print(f"Version: {metadata.version}")
    print(f"Validation Accuracy: {metadata.validation_metrics['accuracy']:.2%}")
    
    return model_id


def example_retrieve_model(model_id: str):
    """Example: Retrieve a model from registry"""
    print("\n=== Example 2: Retrieve Model ===")
    
    registry = ModelRegistry()
    
    # Get model metadata and file
    metadata, model_file = registry.get_model(model_id)
    
    print(f"Retrieved model: {metadata.model_name}")
    print(f"Model Type: {metadata.model_type}")
    print(f"Version: {metadata.version}")
    print(f"Features: {', '.join(metadata.feature_names)}")
    print(f"Training Samples: {metadata.num_training_samples:,}")
    print(f"Deployment Status: {metadata.deployment_status}")
    
    # Deserialize model
    model = pickle.loads(model_file)
    print(f"Model loaded successfully: {model['type']}")


def example_deploy_to_paper_trading(model_id: str):
    """Example: Deploy model to paper trading"""
    print("\n=== Example 3: Deploy to Paper Trading ===")
    
    registry = ModelRegistry()
    
    # Update deployment status
    registry.update_deployment_status(
        model_id,
        DeploymentStatus.TESTING.value,
        DeploymentEnvironment.PAPER.value
    )
    
    print(f"Model {model_id} deployed to paper trading")
    
    # Verify deployment
    metadata, _ = registry.get_model(model_id)
    print(f"Deployment Status: {metadata.deployment_status}")
    print(f"Deployment Environment: {metadata.deployment_environment}")
    print(f"Deployment Timestamp: {metadata.deployment_timestamp}")


def example_promote_to_production(model_id: str):
    """Example: Promote model to production"""
    print("\n=== Example 4: Promote to Production ===")
    
    registry = ModelRegistry()
    
    # Update deployment status
    registry.update_deployment_status(
        model_id,
        DeploymentStatus.PRODUCTION.value,
        DeploymentEnvironment.LIVE.value
    )
    
    print(f"Model {model_id} promoted to production")
    
    # Verify deployment
    metadata, _ = registry.get_model(model_id)
    print(f"Deployment Status: {metadata.deployment_status}")
    print(f"Deployment Environment: {metadata.deployment_environment}")
    print(f"Deployment Timestamp: {metadata.deployment_timestamp}")


def example_list_models():
    """Example: List all models with filters"""
    print("\n=== Example 5: List Models ===")
    
    registry = ModelRegistry()
    
    # List all models
    all_models = registry.list_models()
    print(f"\nTotal models: {len(all_models)}")
    
    # List production models
    prod_models = registry.list_models(
        filters={'deployment_status': DeploymentStatus.PRODUCTION.value}
    )
    print(f"\nProduction models: {len(prod_models)}")
    for model in prod_models:
        print(f"  - {model.model_name} v{model.version} "
              f"(accuracy: {model.validation_metrics.get('accuracy', 0):.2%})")
    
    # List XGBoost models
    xgb_models = registry.list_models(
        filters={'model_type': ModelType.XGBOOST.value}
    )
    print(f"\nXGBoost models: {len(xgb_models)}")
    for model in xgb_models:
        print(f"  - {model.model_name} v{model.version}")


def example_get_current_production_model():
    """Example: Get current production model"""
    print("\n=== Example 6: Get Current Production Model ===")
    
    registry = ModelRegistry()
    
    # Get current production XGBoost model
    prod_model = registry.get_current_production_model(ModelType.XGBOOST.value)
    
    if prod_model:
        print(f"Current production XGBoost model:")
        print(f"  Name: {prod_model.model_name}")
        print(f"  Version: {prod_model.version}")
        print(f"  Deployed: {prod_model.deployment_timestamp}")
        print(f"  Environment: {prod_model.deployment_environment}")
        print(f"  Validation Accuracy: {prod_model.validation_metrics.get('accuracy', 0):.2%}")
    else:
        print("No production XGBoost model found")


def example_model_version_history():
    """Example: Track model version history"""
    print("\n=== Example 7: Model Version History ===")
    
    registry = ModelRegistry()
    
    # Register multiple versions of the same model
    for version in [1, 2, 3]:
        metadata = ModelMetadata(
            model_id="",
            model_name="xgboost_eurusd_predictor",
            model_type=ModelType.XGBOOST.value,
            version=version,
            created_at=datetime.now() + timedelta(days=version),
            training_start_date=datetime.now() - timedelta(days=180),
            training_end_date=datetime.now(),
            num_training_samples=50000 + version * 1000,
            hyperparameters={'max_depth': 5, 'learning_rate': 0.05},
            feature_names=['rsi_14', 'ema_20'],
            num_features=2,
            train_metrics={'accuracy': 0.60 + version * 0.02},
            validation_metrics={'accuracy': 0.55 + version * 0.02},
            test_metrics={'accuracy': 0.54 + version * 0.02},
            deployment_status=DeploymentStatus.TRAINING.value
        )
        
        dummy_model = {'version': version}
        model_file = pickle.dumps(dummy_model)
        
        model_id = registry.register_model(metadata, model_file)
        print(f"Registered version {version}: {model_id}")
    
    # Get version history
    history = registry.get_model_history("xgboost_eurusd_predictor")
    
    print(f"\nVersion history for xgboost_eurusd_predictor:")
    for model in history:
        print(f"  v{model.version}: accuracy={model.validation_metrics['accuracy']:.2%}, "
              f"created={model.created_at.strftime('%Y-%m-%d')}")


def example_registry_stats():
    """Example: Get registry statistics"""
    print("\n=== Example 8: Registry Statistics ===")
    
    registry = ModelRegistry()
    
    stats = registry.get_registry_stats()
    
    print(f"Total models: {stats['total_models']}")
    print(f"\nBy type:")
    for model_type, count in stats['by_type'].items():
        print(f"  {model_type}: {count}")
    
    print(f"\nBy status:")
    for status, count in stats['by_status'].items():
        print(f"  {status}: {count}")
    
    print(f"\nStorage size: {stats['storage_size_mb']:.2f} MB")


def example_reinforcement_learning_model():
    """Example: Register a reinforcement learning model"""
    print("\n=== Example 9: Register RL Model ===")
    
    registry = ModelRegistry()
    
    # Create RL model metadata
    metadata = ModelMetadata(
        model_id="",
        model_name="ppo_position_sizer",
        model_type=ModelType.PPO.value,
        version=1,
        created_at=datetime.now(),
        training_start_date=datetime.now() - timedelta(days=30),
        training_end_date=datetime.now(),
        num_training_samples=1000000,  # 1M timesteps
        hyperparameters={
            'learning_rate': 3e-4,
            'n_steps': 2048,
            'batch_size': 64,
            'n_epochs': 10,
            'gamma': 0.99,
            'gae_lambda': 0.95,
            'clip_range': 0.2
        },
        feature_names=[
            'market_regime', 'volatility', 'trend_strength',
            'risk_appetite', 'current_position'
        ],
        num_features=5,
        train_metrics={'sharpe_ratio': 1.8, 'avg_return': 0.02},
        validation_metrics={'sharpe_ratio': 1.6, 'avg_return': 0.018},
        test_metrics={'sharpe_ratio': 1.5, 'avg_return': 0.017},
        deployment_status=DeploymentStatus.TRAINING.value,
        git_commit_hash="def456abc789",
        training_script_path="ml/ppo_agent_training.py"
    )
    
    # Create dummy RL model file
    dummy_model = {
        'type': 'ppo',
        'policy': 'MlpPolicy',
        'params': metadata.hyperparameters
    }
    model_file = pickle.dumps(dummy_model)
    
    # Register model
    model_id = registry.register_model(metadata, model_file)
    
    print(f"RL Model registered successfully!")
    print(f"Model ID: {model_id}")
    print(f"Model Name: {metadata.model_name}")
    print(f"Training Timesteps: {metadata.num_training_samples:,}")
    print(f"Validation Sharpe Ratio: {metadata.validation_metrics['sharpe_ratio']:.2f}")


def main():
    """Run all examples"""
    print("=" * 60)
    print("Model Registry Usage Examples")
    print("=" * 60)
    
    # Example 1: Register a model
    model_id = example_register_supervised_model()
    
    # Example 2: Retrieve the model
    example_retrieve_model(model_id)
    
    # Example 3: Deploy to paper trading
    example_deploy_to_paper_trading(model_id)
    
    # Example 4: Promote to production
    example_promote_to_production(model_id)
    
    # Example 5: List models
    example_list_models()
    
    # Example 6: Get current production model
    example_get_current_production_model()
    
    # Example 7: Model version history
    example_model_version_history()
    
    # Example 8: Registry statistics
    example_registry_stats()
    
    # Example 9: Register RL model
    example_reinforcement_learning_model()
    
    print("\n" + "=" * 60)
    print("All examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
