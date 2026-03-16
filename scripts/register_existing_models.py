"""
Register Existing Models to Registry

This script scans the models/supervised/ and models/reinforcement/ directories
and registers any models that exist on disk but are not in the registry database.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Simple logging without database
def log_info(msg):
    print(f"[INFO] {msg}")

def log_warning(msg):
    print(f"[WARN] {msg}")

def log_error(msg):
    print(f"[ERROR] {msg}")

# Import after setting up path
from ml.model_registry import ModelRegistry, ModelMetadata, ModelType


def register_supervised_models(registry: ModelRegistry, models_dir: Path):
    """Register supervised learning models from disk"""
    supervised_dir = models_dir / "supervised"
    
    if not supervised_dir.exists():
        log_warning(f"Supervised models directory not found: {supervised_dir}")
        return 0
    
    registered_count = 0
    
    # Scan for model directories
    for model_dir in supervised_dir.iterdir():
        if not model_dir.is_dir() or model_dir.name == ".gitkeep":
            continue
        
        metadata_file = model_dir / "metadata.json"
        model_file = model_dir / "model.pkl"
        
        if not metadata_file.exists() or not model_file.exists():
            log_warning(f"Skipping incomplete model directory: {model_dir.name}")
            continue
        
        try:
            # Load metadata from disk
            with open(metadata_file, 'r') as f:
                metadata_dict = json.load(f)
            
            # Parse model name and type from directory name
            # Format: {model_type}_{symbol}_{timestamp}
            dir_parts = model_dir.name.split('_')
            if len(dir_parts) < 3:
                log_warning(f"Invalid directory name format: {model_dir.name}")
                continue
            
            model_type_str = dir_parts[0].upper()
            symbol = dir_parts[1]
            timestamp_str = '_'.join(dir_parts[2:])
            
            # Determine model type
            if model_type_str == "XGBOOST":
                model_type = ModelType.XGBOOST.value
            elif model_type_str == "LIGHTGBM":
                model_type = ModelType.LIGHTGBM.value
            else:
                log_warning(f"Unknown model type: {model_type_str}")
                continue
            
            # Parse timestamp
            try:
                created_at = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            except ValueError:
                try:
                    created_at = datetime.strptime(timestamp_str, "%Y%m%d")
                except ValueError:
                    log_warning(f"Could not parse timestamp: {timestamp_str}")
                    created_at = datetime.now()
            
            # Extract metrics from metadata
            train_metrics = metadata_dict.get('train_metrics', {})
            val_metrics = metadata_dict.get('validation_metrics', {})
            test_metrics = metadata_dict.get('test_metrics', {})
            
            # Create ModelMetadata
            model_metadata = ModelMetadata(
                model_id="",  # Will be generated
                model_name=f"{model_type_str}_{symbol}",
                model_type=model_type,
                version=1,
                created_at=created_at,
                training_start_date=created_at - timedelta(days=180),  # Estimate
                training_end_date=created_at,
                num_training_samples=metadata_dict.get('train_samples', 0),
                hyperparameters=metadata_dict.get('hyperparameters', {}),
                feature_names=metadata_dict.get('feature_names', []),
                num_features=len(metadata_dict.get('feature_names', [])),
                train_metrics=train_metrics,
                validation_metrics=val_metrics,
                test_metrics=test_metrics,
                deployment_status="TESTING",  # Default to TESTING
                deployment_timestamp=None,
                deployment_environment=None,
                git_commit_hash=None,
                training_script_path=None,
                model_file_path=""
            )
            
            # Load model file
            with open(model_file, 'rb') as f:
                model_bytes = f.read()
            
            # Check if already registered
            existing_models = registry.list_models(filters={
                'model_name': model_metadata.model_name
            })
            
            # Check if this exact model is already registered by comparing metrics
            already_registered = False
            for existing in existing_models:
                if (existing.created_at.date() == created_at.date() and
                    existing.validation_metrics.get('accuracy') == val_metrics.get('accuracy')):
                    already_registered = True
                    log_info(f"Model already registered: {model_dir.name}")
                    break
            
            if not already_registered:
                # Register model
                model_id = registry.register_model(model_metadata, model_bytes)
                log_info(f"✓ Registered: {model_dir.name} (ID: {model_id})")
                registered_count += 1
        
        except Exception as e:
            log_error(f"Failed to register {model_dir.name}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    return registered_count


def register_reinforcement_models(registry: ModelRegistry, models_dir: Path):
    """Register reinforcement learning models from disk"""
    rl_dir = models_dir / "reinforcement"
    
    if not rl_dir.exists():
        log_warning(f"Reinforcement models directory not found: {rl_dir}")
        return 0
    
    registered_count = 0
    
    # Scan for model directories
    for model_dir in rl_dir.iterdir():
        if not model_dir.is_dir():
            continue
        
        metadata_file = model_dir / "metadata.json"
        model_file = model_dir / "agent.zip"
        
        if not metadata_file.exists() or not model_file.exists():
            log_warning(f"Skipping incomplete model directory: {model_dir.name}")
            continue
        
        try:
            # Load metadata from disk
            with open(metadata_file, 'r') as f:
                metadata_dict = json.load(f)
            
            # Parse model name from directory name
            # Format: ppo_{symbol}_{timestamp}
            dir_parts = model_dir.name.split('_')
            if len(dir_parts) < 3:
                log_warning(f"Invalid directory name format: {model_dir.name}")
                continue
            
            symbol = dir_parts[1]
            timestamp_str = '_'.join(dir_parts[2:])
            
            # Parse timestamp
            try:
                created_at = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            except ValueError:
                try:
                    created_at = datetime.strptime(timestamp_str, "%Y%m%d")
                except ValueError:
                    log_warning(f"Could not parse timestamp: {timestamp_str}")
                    created_at = datetime.now()
            
            # Create ModelMetadata
            model_metadata = ModelMetadata(
                model_id="",  # Will be generated
                model_name=f"PPO_{symbol}",
                model_type=ModelType.PPO.value,
                version=1,
                created_at=created_at,
                training_start_date=created_at - timedelta(days=180),
                training_end_date=created_at,
                num_training_samples=metadata_dict.get('num_episodes', 0),
                hyperparameters=metadata_dict.get('hyperparameters', {}),
                feature_names=metadata_dict.get('feature_names', []),
                num_features=len(metadata_dict.get('feature_names', [])),
                train_metrics=metadata_dict.get('train_metrics', {}),
                validation_metrics=metadata_dict.get('validation_metrics', {}),
                test_metrics=metadata_dict.get('test_metrics', {}),
                deployment_status="TESTING",
                deployment_timestamp=None,
                deployment_environment=None,
                git_commit_hash=None,
                training_script_path=None,
                model_file_path=""
            )
            
            # Load model file
            with open(model_file, 'rb') as f:
                model_bytes = f.read()
            
            # Check if already registered
            existing_models = registry.list_models(filters={
                'model_name': model_metadata.model_name
            })
            
            already_registered = False
            for existing in existing_models:
                if existing.created_at.date() == created_at.date():
                    already_registered = True
                    log_info(f"Model already registered: {model_dir.name}")
                    break
            
            if not already_registered:
                # Register model
                model_id = registry.register_model(model_metadata, model_bytes)
                log_info(f"✓ Registered: {model_dir.name} (ID: {model_id})")
                registered_count += 1
        
        except Exception as e:
            log_error(f"Failed to register {model_dir.name}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    return registered_count


def main():
    """Main function"""
    log_info("=" * 60)
    log_info("REGISTERING EXISTING MODELS TO REGISTRY")
    log_info("=" * 60)
    
    # Initialize registry
    registry = ModelRegistry()
    models_dir = Path("models")
    
    # Get current registry stats
    stats = registry.get_registry_stats()
    log_info(f"Current registry: {stats['total_models']} models")
    
    # Register supervised models
    log_info("\n--- Scanning Supervised Models ---")
    supervised_count = register_supervised_models(registry, models_dir)
    
    # Register reinforcement models
    log_info("\n--- Scanning Reinforcement Models ---")
    rl_count = register_reinforcement_models(registry, models_dir)
    
    # Final stats
    log_info("\n" + "=" * 60)
    log_info("REGISTRATION COMPLETE")
    log_info("=" * 60)
    log_info(f"Supervised models registered: {supervised_count}")
    log_info(f"Reinforcement models registered: {rl_count}")
    log_info(f"Total new registrations: {supervised_count + rl_count}")
    
    # Show updated stats
    stats = registry.get_registry_stats()
    log_info(f"\nUpdated registry: {stats['total_models']} models")
    log_info(f"By type: {stats['by_type']}")
    log_info(f"By status: {stats['by_status']}")
    
    log_info("\n✓ All existing models have been registered!")
    log_info("  Refresh the dashboard MODEL REGISTRY to see them.")


if __name__ == "__main__":
    main()
