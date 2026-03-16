"""
Direct Model Registration (No Logger)

Registers existing models without using the logger to avoid database locks.
"""

import json
import duckdb
import uuid
from pathlib import Path
from datetime import datetime, timedelta

def main():
    print("=" * 60)
    print("REGISTERING EXISTING MODELS TO REGISTRY")
    print("=" * 60)
    
    models_dir = Path("models")
    db_path = models_dir / "registry.db"
    supervised_dir = models_dir / "supervised"
    
    if not supervised_dir.exists():
        print(f"[ERROR] Supervised models directory not found: {supervised_dir}")
        return
    
    # Connect to registry database
    con = duckdb.connect(str(db_path))
    
    # Check current count
    current_count = con.execute("SELECT COUNT(*) FROM model_registry").fetchone()[0]
    print(f"Current registry: {current_count} models\n")
    
    print("--- Scanning Supervised Models ---")
    registered_count = 0
    
    # Scan for model directories
    for model_dir in supervised_dir.iterdir():
        if not model_dir.is_dir() or model_dir.name == ".gitkeep":
            continue
        
        metadata_file = model_dir / "metadata.json"
        model_file = model_dir / "model.pkl"
        
        if not metadata_file.exists() or not model_file.exists():
            print(f"[WARN] Skipping incomplete: {model_dir.name}")
            continue
        
        try:
            # Load metadata
            with open(metadata_file, 'r') as f:
                metadata_dict = json.load(f)
            
            # Parse directory name: {model_type}_{symbol}_{timestamp}
            dir_parts = model_dir.name.split('_')
            if len(dir_parts) < 3:
                print(f"[WARN] Invalid format: {model_dir.name}")
                continue
            
            model_type_str = dir_parts[0].upper()
            symbol = dir_parts[1]
            timestamp_str = '_'.join(dir_parts[2:])
            
            # Parse timestamp
            try:
                created_at = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            except ValueError:
                try:
                    created_at = datetime.strptime(timestamp_str, "%Y%m%d")
                except ValueError:
                    created_at = datetime.now()
            
            # Extract metrics
            train_metrics = metadata_dict.get('train_metrics', {})
            val_metrics = metadata_dict.get('validation_metrics', {})
            test_metrics = metadata_dict.get('test_metrics', {})
            
            # Generate model ID
            model_id = str(uuid.uuid4())
            model_name = f"{model_type_str}_{symbol}"
            
            # Check if already exists
            existing = con.execute("""
                SELECT COUNT(*) FROM model_registry 
                WHERE model_name = ? AND DATE(created_at) = ?
            """, (model_name, created_at.date())).fetchone()[0]
            
            if existing > 0:
                print(f"[INFO] Already registered: {model_dir.name}")
                continue
            
            # Insert into database
            con.execute("""
                INSERT INTO model_registry (
                    model_id, model_name, model_type, version, created_at,
                    training_start_date, training_end_date, num_training_samples,
                    hyperparameters, feature_names, num_features,
                    train_metrics, validation_metrics, test_metrics,
                    deployment_status, deployment_timestamp, deployment_environment,
                    git_commit_hash, training_script_path, model_file_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                model_id,
                model_name,
                model_type_str,
                1,
                created_at,
                (created_at - timedelta(days=180)).date(),
                created_at.date(),
                metadata_dict.get('train_samples', 0),
                json.dumps(metadata_dict.get('hyperparameters', {})),
                metadata_dict.get('feature_names', []),
                len(metadata_dict.get('feature_names', [])),
                json.dumps(train_metrics),
                json.dumps(val_metrics),
                json.dumps(test_metrics),
                "TESTING",
                None,
                None,
                None,
                None,
                f"supervised/{model_dir.name}/model.pkl"
            ))
            
            print(f"[INFO] ✓ Registered: {model_dir.name}")
            registered_count += 1
        
        except Exception as e:
            print(f"[ERROR] Failed to register {model_dir.name}: {e}")
            continue
    
    con.close()
    
    print("\n" + "=" * 60)
    print("REGISTRATION COMPLETE")
    print("=" * 60)
    print(f"Models registered: {registered_count}")
    print(f"\n✓ Refresh the dashboard MODEL REGISTRY to see them!")


if __name__ == "__main__":
    main()
