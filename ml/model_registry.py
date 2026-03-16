"""
Model Registry and Versioning System

This module implements a versioned storage system for trained ML models with
comprehensive metadata tracking, deployment tagging, and DuckDB backend.

Requirements: 14.1, 14.2, 14.3, 14.4, 14.5
"""

import duckdb
import json
import uuid
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

from core.logger import get_agent_logger

log = get_agent_logger("MODEL_REGISTRY")


class ModelType(str, Enum):
    """Supported model types"""
    XGBOOST = "XGBOOST"
    LIGHTGBM = "LIGHTGBM"
    PPO = "PPO"


class DeploymentStatus(str, Enum):
    """Model deployment status"""
    TRAINING = "TRAINING"
    TESTING = "TESTING"
    PRODUCTION = "PRODUCTION"
    RETIRED = "RETIRED"


class DeploymentEnvironment(str, Enum):
    """Deployment environment"""
    PAPER = "PAPER"
    LIVE = "LIVE"


@dataclass
class ModelMetadata:
    """
    Comprehensive metadata for a trained model.
    
    Requirements: 14.1, 14.2, 14.3, 14.4, 14.5
    """
    model_id: str  # UUID
    model_name: str
    model_type: str  # XGBOOST, LIGHTGBM, PPO
    version: int
    created_at: datetime
    
    # Training data
    training_start_date: datetime
    training_end_date: datetime
    num_training_samples: int
    
    # Hyperparameters
    hyperparameters: Dict[str, Any]
    
    # Features
    feature_names: List[str]
    num_features: int
    
    # Performance metrics
    train_metrics: Dict[str, float]
    validation_metrics: Dict[str, float]
    test_metrics: Dict[str, float]
    
    # Deployment
    deployment_status: str  # TRAINING, TESTING, PRODUCTION, RETIRED
    deployment_timestamp: Optional[datetime] = None
    deployment_environment: Optional[str] = None  # PAPER, LIVE
    
    # Code tracking
    git_commit_hash: Optional[str] = None
    training_script_path: Optional[str] = None
    
    # Model file
    model_file_path: str = ""  # Path to serialized model
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        data = asdict(self)
        # Convert datetime objects to ISO format strings
        if isinstance(data['created_at'], datetime):
            data['created_at'] = data['created_at'].isoformat()
        if isinstance(data['training_start_date'], datetime):
            data['training_start_date'] = data['training_start_date'].isoformat()
        if isinstance(data['training_end_date'], datetime):
            data['training_end_date'] = data['training_end_date'].isoformat()
        if data['deployment_timestamp'] and isinstance(data['deployment_timestamp'], datetime):
            data['deployment_timestamp'] = data['deployment_timestamp'].isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ModelMetadata':
        """Create from dictionary"""
        # Convert ISO format strings back to datetime
        if isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if isinstance(data['training_start_date'], str):
            data['training_start_date'] = datetime.fromisoformat(data['training_start_date'])
        if isinstance(data['training_end_date'], str):
            data['training_end_date'] = datetime.fromisoformat(data['training_end_date'])
        if data.get('deployment_timestamp') and isinstance(data['deployment_timestamp'], str):
            data['deployment_timestamp'] = datetime.fromisoformat(data['deployment_timestamp'])
        return cls(**data)


class ModelRegistry:
    """
    Model registry with DuckDB backend for versioned model storage.
    
    Features:
    - Unique version IDs for each model (UUID)
    - Organized directory structure for model files
    - DuckDB schema for model metadata
    - Comprehensive metadata tracking
    - Deployment tagging and status tracking
    - Git commit hash and training script tracking
    
    Storage Structure:
    models/
    ├── supervised/
    │   ├── xgboost_v1_20240101/
    │   │   ├── model.pkl
    │   │   ├── metadata.json
    │   │   └── ...
    │   └── lightgbm_v2_20240115/
    │       └── ...
    ├── reinforcement/
    │   ├── ppo_v1_20240101/
    │   │   ├── model.zip
    │   │   ├── metadata.json
    │   │   └── ...
    │   └── ...
    └── registry.db  # DuckDB with model metadata
    """
    
    def __init__(
        self,
        db_path: str = "models/registry.db",
        models_root: str = "models"
    ):
        self.db_path = Path(db_path)
        self.models_root = Path(models_root)
        self._lock = threading.Lock()
        
        # Ensure directories exist
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.models_root.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories for model types
        (self.models_root / "supervised").mkdir(exist_ok=True)
        (self.models_root / "reinforcement").mkdir(exist_ok=True)
        
        # Initialize database
        self._init_database()
        
        log.info("Model Registry initialized")
        log.info(f"Database: {self.db_path}")
        log.info(f"Models root: {self.models_root}")
    
    def _init_database(self):
        """
        Initialize DuckDB database with model registry schema.
        
        Requirements: 14.4
        """
        with self._lock:
            with duckdb.connect(str(self.db_path)) as con:
                # Create model_registry table
                con.execute("""
                    CREATE TABLE IF NOT EXISTS model_registry (
                        model_id VARCHAR PRIMARY KEY,
                        model_name VARCHAR NOT NULL,
                        model_type VARCHAR NOT NULL,
                        version INTEGER NOT NULL,
                        created_at TIMESTAMP NOT NULL,
                        training_start_date DATE NOT NULL,
                        training_end_date DATE NOT NULL,
                        num_training_samples INTEGER NOT NULL,
                        hyperparameters JSON NOT NULL,
                        feature_names VARCHAR[] NOT NULL,
                        num_features INTEGER NOT NULL,
                        train_metrics JSON NOT NULL,
                        validation_metrics JSON NOT NULL,
                        test_metrics JSON NOT NULL,
                        deployment_status VARCHAR NOT NULL,
                        deployment_timestamp TIMESTAMP,
                        deployment_environment VARCHAR,
                        git_commit_hash VARCHAR,
                        training_script_path VARCHAR,
                        model_file_path VARCHAR NOT NULL,
                        CONSTRAINT deployment_status_check CHECK (
                            deployment_status IN ('TRAINING', 'TESTING', 'PRODUCTION', 'RETIRED')
                        ),
                        CONSTRAINT deployment_environment_check CHECK (
                            deployment_environment IS NULL OR 
                            deployment_environment IN ('PAPER', 'LIVE')
                        )
                    )
                """)
                
                # Create indexes for efficient queries
                con.execute("""
                    CREATE INDEX IF NOT EXISTS idx_model_status 
                    ON model_registry(deployment_status)
                """)
                
                con.execute("""
                    CREATE INDEX IF NOT EXISTS idx_model_created 
                    ON model_registry(created_at DESC)
                """)
                
                con.execute("""
                    CREATE INDEX IF NOT EXISTS idx_model_type 
                    ON model_registry(model_type)
                """)
                
                log.info("Model registry schema initialized")
    
    def register_model(
        self,
        metadata: ModelMetadata,
        model_file: bytes
    ) -> str:
        """
        Register a new model in the registry.
        
        Requirements: 14.1, 14.2, 14.3, 14.4
        
        Args:
            metadata: Model metadata
            model_file: Serialized model file as bytes
            
        Returns:
            model_id: Unique model ID (UUID)
        """
        # Generate unique model ID if not provided
        if not metadata.model_id:
            metadata.model_id = str(uuid.uuid4())
        
        log.info(f"Registering model: {metadata.model_name} (ID: {metadata.model_id})")
        
        # Determine model directory based on type
        if metadata.model_type in [ModelType.XGBOOST.value, ModelType.LIGHTGBM.value]:
            model_category = "supervised"
        elif metadata.model_type == ModelType.PPO.value:
            model_category = "reinforcement"
        else:
            raise ValueError(f"Unknown model type: {metadata.model_type}")
        
        # Create model directory
        timestamp = metadata.created_at.strftime("%Y%m%d")
        model_dir_name = f"{metadata.model_name}_v{metadata.version}_{timestamp}"
        model_dir = self.models_root / model_category / model_dir_name
        model_dir.mkdir(parents=True, exist_ok=True)
        
        # Save model file
        model_file_ext = ".pkl" if model_category == "supervised" else ".zip"
        model_file_path = model_dir / f"model{model_file_ext}"
        
        with open(model_file_path, 'wb') as f:
            f.write(model_file)
        
        # Update metadata with file path
        metadata.model_file_path = str(model_file_path.relative_to(self.models_root))
        
        # Save metadata as JSON
        metadata_path = model_dir / "metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata.to_dict(), f, indent=2)
        
        # Store in database
        self._store_metadata_in_db(metadata)
        
        log.info(f"Model registered successfully: {model_dir}")
        log.info(f"Model ID: {metadata.model_id}")
        
        return metadata.model_id
    
    def _store_metadata_in_db(self, metadata: ModelMetadata):
        """Store model metadata in DuckDB"""
        with self._lock:
            with duckdb.connect(str(self.db_path)) as con:
                con.execute("""
                    INSERT OR REPLACE INTO model_registry (
                        model_id, model_name, model_type, version, created_at,
                        training_start_date, training_end_date, num_training_samples,
                        hyperparameters, feature_names, num_features,
                        train_metrics, validation_metrics, test_metrics,
                        deployment_status, deployment_timestamp, deployment_environment,
                        git_commit_hash, training_script_path, model_file_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    metadata.model_id,
                    metadata.model_name,
                    metadata.model_type,
                    metadata.version,
                    metadata.created_at,
                    metadata.training_start_date.date() if isinstance(metadata.training_start_date, datetime) else metadata.training_start_date,
                    metadata.training_end_date.date() if isinstance(metadata.training_end_date, datetime) else metadata.training_end_date,
                    metadata.num_training_samples,
                    json.dumps(metadata.hyperparameters),
                    metadata.feature_names,
                    metadata.num_features,
                    json.dumps(metadata.train_metrics),
                    json.dumps(metadata.validation_metrics),
                    json.dumps(metadata.test_metrics),
                    metadata.deployment_status,
                    metadata.deployment_timestamp,
                    metadata.deployment_environment,
                    metadata.git_commit_hash,
                    metadata.training_script_path,
                    metadata.model_file_path
                ))
    
    def get_model(self, model_id: str) -> Tuple[ModelMetadata, bytes]:
        """
        Get model metadata and file by ID.
        
        Args:
            model_id: Model ID (UUID)
            
        Returns:
            Tuple of (metadata, model_file_bytes)
        """
        log.info(f"Retrieving model: {model_id}")
        
        # Get metadata from database
        with self._lock:
            with duckdb.connect(str(self.db_path)) as con:
                result = con.execute("""
                    SELECT 
                        model_id, model_name, model_type, version, created_at,
                        training_start_date, training_end_date, num_training_samples,
                        hyperparameters, feature_names, num_features,
                        train_metrics, validation_metrics, test_metrics,
                        deployment_status, deployment_timestamp, deployment_environment,
                        git_commit_hash, training_script_path, model_file_path
                    FROM model_registry
                    WHERE model_id = ?
                """, (model_id,)).fetchone()
        
        if not result:
            raise ValueError(f"Model not found: {model_id}")
        
        # Parse result into ModelMetadata
        metadata = ModelMetadata(
            model_id=result[0],
            model_name=result[1],
            model_type=result[2],
            version=result[3],
            created_at=result[4],
            training_start_date=result[5],
            training_end_date=result[6],
            num_training_samples=result[7],
            hyperparameters=json.loads(result[8]),
            feature_names=result[9],
            num_features=result[10],
            train_metrics=json.loads(result[11]),
            validation_metrics=json.loads(result[12]),
            test_metrics=json.loads(result[13]),
            deployment_status=result[14],
            deployment_timestamp=result[15],
            deployment_environment=result[16],
            git_commit_hash=result[17],
            training_script_path=result[18],
            model_file_path=result[19]
        )
        
        # Load model file
        model_file_path = self.models_root / metadata.model_file_path
        
        if not model_file_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_file_path}")
        
        with open(model_file_path, 'rb') as f:
            model_file = f.read()
        
        log.info(f"Model retrieved: {metadata.model_name}")
        
        return metadata, model_file

    
    def list_models(
        self,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[ModelMetadata]:
        """
        List models with optional filters.
        
        Args:
            filters: Optional filters (e.g., {'model_type': 'XGBOOST', 'deployment_status': 'PRODUCTION'})
            
        Returns:
            List of ModelMetadata objects
        """
        log.info(f"Listing models with filters: {filters}")
        
        # Build query
        query = """
            SELECT 
                model_id, model_name, model_type, version, created_at,
                training_start_date, training_end_date, num_training_samples,
                hyperparameters, feature_names, num_features,
                train_metrics, validation_metrics, test_metrics,
                deployment_status, deployment_timestamp, deployment_environment,
                git_commit_hash, training_script_path, model_file_path
            FROM model_registry
        """
        
        params = []
        where_clauses = []
        
        if filters:
            if 'model_type' in filters:
                where_clauses.append("model_type = ?")
                params.append(filters['model_type'])
            
            if 'deployment_status' in filters:
                where_clauses.append("deployment_status = ?")
                params.append(filters['deployment_status'])
            
            if 'deployment_environment' in filters:
                where_clauses.append("deployment_environment = ?")
                params.append(filters['deployment_environment'])
            
            if 'model_name' in filters:
                where_clauses.append("model_name = ?")
                params.append(filters['model_name'])
        
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        query += " ORDER BY created_at DESC"
        
        # Execute query
        with self._lock:
            with duckdb.connect(str(self.db_path)) as con:
                results = con.execute(query, params).fetchall()
        
        # Parse results
        models = []
        for result in results:
            metadata = ModelMetadata(
                model_id=result[0],
                model_name=result[1],
                model_type=result[2],
                version=result[3],
                created_at=result[4],
                training_start_date=result[5],
                training_end_date=result[6],
                num_training_samples=result[7],
                hyperparameters=json.loads(result[8]),
                feature_names=result[9],
                num_features=result[10],
                train_metrics=json.loads(result[11]),
                validation_metrics=json.loads(result[12]),
                test_metrics=json.loads(result[13]),
                deployment_status=result[14],
                deployment_timestamp=result[15],
                deployment_environment=result[16],
                git_commit_hash=result[17],
                training_script_path=result[18],
                model_file_path=result[19]
            )
            models.append(metadata)
        
        log.info(f"Found {len(models)} models")
        
        return models
    
    def update_deployment_status(
        self,
        model_id: str,
        status: str,
        environment: Optional[str] = None
    ) -> None:
        """
        Update model deployment status and environment.
        
        Requirements: 14.5
        
        Args:
            model_id: Model ID (UUID)
            status: Deployment status (TRAINING, TESTING, PRODUCTION, RETIRED)
            environment: Optional deployment environment (PAPER, LIVE)
        """
        # Validate status
        if status not in [s.value for s in DeploymentStatus]:
            raise ValueError(f"Invalid deployment status: {status}")
        
        # Validate environment if provided
        if environment and environment not in [e.value for e in DeploymentEnvironment]:
            raise ValueError(f"Invalid deployment environment: {environment}")
        
        log.info(f"Updating deployment status for model {model_id}: {status} ({environment})")
        
        # Update database
        deployment_timestamp = datetime.now() if status in ['TESTING', 'PRODUCTION'] else None
        
        with self._lock:
            with duckdb.connect(str(self.db_path)) as con:
                con.execute("""
                    UPDATE model_registry
                    SET deployment_status = ?,
                        deployment_timestamp = ?,
                        deployment_environment = ?
                    WHERE model_id = ?
                """, (status, deployment_timestamp, environment, model_id))
        
        log.info(f"Deployment status updated successfully")
    
    def get_current_production_model(
        self,
        model_type: str
    ) -> Optional[ModelMetadata]:
        """
        Get currently deployed production model for a given type.
        
        Args:
            model_type: Model type (XGBOOST, LIGHTGBM, PPO)
            
        Returns:
            ModelMetadata if found, None otherwise
        """
        log.info(f"Getting current production model for type: {model_type}")
        
        with self._lock:
            with duckdb.connect(str(self.db_path)) as con:
                result = con.execute("""
                    SELECT 
                        model_id, model_name, model_type, version, created_at,
                        training_start_date, training_end_date, num_training_samples,
                        hyperparameters, feature_names, num_features,
                        train_metrics, validation_metrics, test_metrics,
                        deployment_status, deployment_timestamp, deployment_environment,
                        git_commit_hash, training_script_path, model_file_path
                    FROM model_registry
                    WHERE model_type = ?
                      AND deployment_status = 'PRODUCTION'
                    ORDER BY deployment_timestamp DESC
                    LIMIT 1
                """, (model_type,)).fetchone()
        
        if not result:
            log.info(f"No production model found for type: {model_type}")
            return None
        
        # Parse result
        metadata = ModelMetadata(
            model_id=result[0],
            model_name=result[1],
            model_type=result[2],
            version=result[3],
            created_at=result[4],
            training_start_date=result[5],
            training_end_date=result[6],
            num_training_samples=result[7],
            hyperparameters=json.loads(result[8]),
            feature_names=result[9],
            num_features=result[10],
            train_metrics=json.loads(result[11]),
            validation_metrics=json.loads(result[12]),
            test_metrics=json.loads(result[13]),
            deployment_status=result[14],
            deployment_timestamp=result[15],
            deployment_environment=result[16],
            git_commit_hash=result[17],
            training_script_path=result[18],
            model_file_path=result[19]
        )
        
        log.info(f"Found production model: {metadata.model_name} (ID: {metadata.model_id})")
        
        return metadata
    
    def get_model_history(
        self,
        model_name: str
    ) -> List[ModelMetadata]:
        """
        Get version history for a model by name.
        
        Args:
            model_name: Model name
            
        Returns:
            List of ModelMetadata objects ordered by version (newest first)
        """
        log.info(f"Getting version history for model: {model_name}")
        
        return self.list_models(filters={'model_name': model_name})
    
    def delete_model(
        self,
        model_id: str,
        delete_files: bool = True
    ) -> None:
        """
        Delete a model from the registry.
        
        Args:
            model_id: Model ID (UUID)
            delete_files: Whether to delete model files from disk (default: True)
        """
        log.info(f"Deleting model: {model_id}")
        
        # Get model metadata first
        try:
            metadata, _ = self.get_model(model_id)
        except (ValueError, FileNotFoundError):
            log.warning(f"Model not found: {model_id}")
            return
        
        # Delete from database
        with self._lock:
            with duckdb.connect(str(self.db_path)) as con:
                con.execute("DELETE FROM model_registry WHERE model_id = ?", (model_id,))
        
        # Delete files if requested
        if delete_files:
            model_file_path = self.models_root / metadata.model_file_path
            model_dir = model_file_path.parent
            
            if model_dir.exists():
                shutil.rmtree(model_dir)
                log.info(f"Deleted model files: {model_dir}")
        
        log.info(f"Model deleted successfully: {model_id}")
    
    def get_registry_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the model registry.
        
        Returns:
            Dictionary with registry statistics
        """
        stats = {
            'total_models': 0,
            'by_type': {},
            'by_status': {},
            'storage_size_mb': 0
        }
        
        with self._lock:
            with duckdb.connect(str(self.db_path)) as con:
                # Total models
                result = con.execute("SELECT COUNT(*) FROM model_registry").fetchone()
                stats['total_models'] = result[0]
                
                # By type
                results = con.execute("""
                    SELECT model_type, COUNT(*) 
                    FROM model_registry 
                    GROUP BY model_type
                """).fetchall()
                stats['by_type'] = {row[0]: row[1] for row in results}
                
                # By status
                results = con.execute("""
                    SELECT deployment_status, COUNT(*) 
                    FROM model_registry 
                    GROUP BY deployment_status
                """).fetchall()
                stats['by_status'] = {row[0]: row[1] for row in results}
        
        # Calculate storage size
        total_size = 0
        if self.models_root.exists():
            for file in self.models_root.rglob('*'):
                if file.is_file():
                    total_size += file.stat().st_size
        
        stats['storage_size_mb'] = total_size / (1024 * 1024)
        
        return stats
    
    def export_model_metadata(
        self,
        model_id: str,
        output_path: str
    ) -> None:
        """
        Export model metadata to JSON file.
        
        Args:
            model_id: Model ID (UUID)
            output_path: Path to output JSON file
        """
        metadata, _ = self.get_model(model_id)
        
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            json.dump(metadata.to_dict(), f, indent=2)
        
        log.info(f"Model metadata exported to: {output_file}")
    
    def import_model_metadata(
        self,
        metadata_path: str,
        model_file_path: str
    ) -> str:
        """
        Import model from metadata JSON and model file.
        
        Args:
            metadata_path: Path to metadata JSON file
            model_file_path: Path to model file
            
        Returns:
            model_id: Unique model ID
        """
        # Load metadata
        with open(metadata_path, 'r') as f:
            metadata_dict = json.load(f)
        
        metadata = ModelMetadata.from_dict(metadata_dict)
        
        # Load model file
        with open(model_file_path, 'rb') as f:
            model_file = f.read()
        
        # Register model
        model_id = self.register_model(metadata, model_file)
        
        log.info(f"Model imported successfully: {model_id}")
        
        return model_id
