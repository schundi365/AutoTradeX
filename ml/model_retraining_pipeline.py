"""
Model Retraining Pipeline

This module implements an automated model retraining pipeline that:
- Schedules weekly retraining with the most recent 6 months of data
- Evaluates retrained models on out-of-sample test data
- Promotes models if they outperform by ≥2% on test metrics
- Logs all retraining results

Requirements: 21.1, 21.2, 21.3, 21.4
"""

import json
import pickle
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

import numpy as np
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from core.logger import get_agent_logger
from ml.model_registry import ModelRegistry, ModelMetadata, ModelType, DeploymentStatus
from ml.supervised_training import SupervisedTrainingPipeline, TrainingConfig

# Optional import for RL training
try:
    from ml.ppo_agent_training import PPOAgentTraining
    HAS_RL_SUPPORT = True
except ImportError:
    HAS_RL_SUPPORT = False
    PPOAgentTraining = None

log = get_agent_logger("MODEL_RETRAINING")


class RetrainingStatus(str, Enum):
    """Retraining job status"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PromotionDecision(str, Enum):
    """Model promotion decision"""
    PROMOTED = "PROMOTED"
    KEPT_CURRENT = "KEPT_CURRENT"
    NO_CURRENT_MODEL = "NO_CURRENT_MODEL"


@dataclass
class RetrainingResult:
    """Result of a model retraining job"""
    job_id: str
    model_type: str
    timestamp: datetime
    status: str
    
    # Model IDs
    retrained_model_id: Optional[str] = None
    current_model_id: Optional[str] = None
    
    # Performance metrics
    retrained_metrics: Optional[Dict[str, float]] = None
    current_metrics: Optional[Dict[str, float]] = None
    
    # Promotion decision
    promotion_decision: Optional[str] = None
    performance_improvement_pct: Optional[float] = None
    
    # Error info
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = asdict(self)
        if isinstance(data['timestamp'], datetime):
            data['timestamp'] = data['timestamp'].isoformat()
        return data


class ModelRetrainingPipeline:
    """
    Automated model retraining pipeline with scheduling and promotion logic.
    
    Features:
    - Weekly scheduled retraining
    - Uses most recent 6 months of data
    - Out-of-sample evaluation
    - Automatic promotion if improvement ≥2%
    - Comprehensive logging of all retraining results
    - Support for both supervised and RL models
    - Manual triggering support
    
    Requirements: 21.1, 21.2, 21.3, 21.4
    """
    
    def __init__(
        self,
        model_registry: ModelRegistry,
        data_source_path: str = "data/historical",
        retraining_log_path: str = "models/retraining_log.jsonl",
        enable_scheduling: bool = True,
        schedule_day: str = "sunday",
        schedule_hour: int = 2,
        schedule_minute: int = 0
    ):
        """
        Initialize model retraining pipeline.
        
        Args:
            model_registry: ModelRegistry instance
            data_source_path: Path to historical data
            retraining_log_path: Path to retraining log file
            enable_scheduling: Whether to enable automatic scheduling
            schedule_day: Day of week for retraining (default: sunday)
            schedule_hour: Hour of day for retraining (default: 2 AM)
            schedule_minute: Minute of hour for retraining (default: 0)
        """
        self.model_registry = model_registry
        self.data_source_path = Path(data_source_path)
        self.retraining_log_path = Path(retraining_log_path)
        self._lock = threading.Lock()
        
        # Ensure log directory exists
        self.retraining_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize scheduler
        self.scheduler = None
        if enable_scheduling:
            self.scheduler = BackgroundScheduler()
            self._setup_schedule(schedule_day, schedule_hour, schedule_minute)
        
        log.info("Model Retraining Pipeline initialized")
        log.info(f"Data source: {self.data_source_path}")
        log.info(f"Retraining log: {self.retraining_log_path}")
        if enable_scheduling:
            log.info(f"Scheduled: Every {schedule_day} at {schedule_hour:02d}:{schedule_minute:02d}")
    
    def _setup_schedule(self, day: str, hour: int, minute: int):
        """Setup weekly retraining schedule"""
        # Map day names to cron day_of_week values
        day_map = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }
        
        day_of_week = day_map.get(day.lower(), 6)  # Default to Sunday
        
        # Create cron trigger for weekly execution
        trigger = CronTrigger(
            day_of_week=day_of_week,
            hour=hour,
            minute=minute
        )
        
        # Schedule retraining for all model types
        self.scheduler.add_job(
            func=self._scheduled_retraining_job,
            trigger=trigger,
            id='weekly_retraining',
            name='Weekly Model Retraining',
            replace_existing=True
        )
        
        log.info(f"Scheduled weekly retraining: {day} at {hour:02d}:{minute:02d}")
    
    def start_scheduler(self):
        """Start the retraining scheduler"""
        if self.scheduler and not self.scheduler.running:
            self.scheduler.start()
            log.info("Retraining scheduler started")
    
    def stop_scheduler(self):
        """Stop the retraining scheduler"""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown()
            log.info("Retraining scheduler stopped")
    
    def _scheduled_retraining_job(self):
        """Scheduled job that retrains all model types"""
        log.info("Starting scheduled retraining job")
        
        # Retrain supervised models
        for model_type in [ModelType.XGBOOST, ModelType.LIGHTGBM]:
            try:
                self.retrain_and_evaluate_model(model_type.value)
            except Exception as e:
                log.error(f"Failed to retrain {model_type.value}: {e}")
        
        # Retrain RL models
        try:
            self.retrain_and_evaluate_model(ModelType.PPO.value)
        except Exception as e:
            log.error(f"Failed to retrain PPO: {e}")
        
        log.info("Scheduled retraining job completed")
    
    def retrain_model(
        self,
        model_type: str,
        training_months: int = 6
    ) -> Tuple[str, Dict[str, float]]:
        """
        Retrain a model using the most recent N months of data.
        
        Requirements: 21.1
        
        Args:
            model_type: Model type (XGBOOST, LIGHTGBM, PPO)
            training_months: Number of months of data to use (default: 6)
            
        Returns:
            Tuple of (model_id, test_metrics)
        """
        log.info(f"Retraining {model_type} model with {training_months} months of data")
        
        # Calculate date range for training data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=training_months * 30)
        
        log.info(f"Training data range: {start_date.date()} to {end_date.date()}")
        
        # Retrain based on model type
        if model_type in [ModelType.XGBOOST.value, ModelType.LIGHTGBM.value]:
            return self._retrain_supervised_model(model_type, start_date, end_date)
        elif model_type == ModelType.PPO.value:
            return self._retrain_rl_model(start_date, end_date)
        else:
            raise ValueError(f"Unknown model type: {model_type}")
    
    def _retrain_supervised_model(
        self,
        model_type: str,
        start_date: datetime,
        end_date: datetime
    ) -> Tuple[str, Dict[str, float]]:
        """Retrain supervised learning model (XGBoost or LightGBM)"""
        log.info(f"Retraining supervised model: {model_type}")
        
        # Initialize training pipeline
        training_pipeline = SupervisedTrainingPipeline(
            model_registry=self.model_registry
        )
        
        # Generate training data
        log.info("Generating training data...")
        X_train, y_train, X_val, y_val, X_test, y_test, feature_names = \
            training_pipeline.generate_training_data(
                start_date=start_date,
                end_date=end_date,
                train_ratio=0.7,
                val_ratio=0.15,
                test_ratio=0.15
            )
        
        # Train model
        log.info(f"Training {model_type} model...")
        if model_type == ModelType.XGBOOST.value:
            model, train_metrics, val_metrics = training_pipeline.train_xgboost(
                X_train, y_train, X_val, y_val
            )
        else:  # LightGBM
            model, train_metrics, val_metrics = training_pipeline.train_lightgbm(
                X_train, y_train, X_val, y_val
            )
        
        # Evaluate on test set
        log.info("Evaluating on test set...")
        test_metrics = training_pipeline._evaluate_model(model, X_test, y_test)
        
        # Create metadata
        metadata = ModelMetadata(
            model_id="",  # Will be generated by registry
            model_name=f"{model_type.lower()}_retrained",
            model_type=model_type,
            version=1,
            created_at=datetime.now(),
            training_start_date=start_date,
            training_end_date=end_date,
            num_training_samples=len(X_train),
            hyperparameters=model.get_params() if hasattr(model, 'get_params') else {},
            feature_names=feature_names,
            num_features=len(feature_names),
            train_metrics=train_metrics.to_dict() if hasattr(train_metrics, 'to_dict') else train_metrics,
            validation_metrics=val_metrics.to_dict() if hasattr(val_metrics, 'to_dict') else val_metrics,
            test_metrics=test_metrics.to_dict() if hasattr(test_metrics, 'to_dict') else test_metrics,
            deployment_status=DeploymentStatus.TRAINING.value
        )
        
        # Serialize model
        model_bytes = pickle.dumps(model)
        
        # Register model
        model_id = self.model_registry.register_model(metadata, model_bytes)
        
        log.info(f"Model retrained successfully: {model_id}")
        log.info(f"Test metrics: {test_metrics}")
        
        return model_id, test_metrics.to_dict() if hasattr(test_metrics, 'to_dict') else test_metrics
    
    def _retrain_rl_model(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Tuple[str, Dict[str, float]]:
        """Retrain RL model (PPO)"""
        if not HAS_RL_SUPPORT:
            raise ImportError(
                "RL training requires stable_baselines3. "
                "Install with: pip install stable-baselines3"
            )
        
        log.info("Retraining RL model: PPO")
        
        # Initialize RL training
        rl_training = PPOAgentTraining(
            model_registry=self.model_registry
        )
        
        # Train PPO agent
        log.info("Training PPO agent...")
        model_id, metrics = rl_training.train_ppo_agent(
            start_date=start_date,
            end_date=end_date,
            total_timesteps=100000  # Reduced for retraining
        )
        
        log.info(f"RL model retrained successfully: {model_id}")
        log.info(f"Test metrics: {metrics}")
        
        return model_id, metrics
    
    def evaluate_model(
        self,
        model_id: str,
        test_data: Optional[Tuple[np.ndarray, np.ndarray]] = None
    ) -> Dict[str, float]:
        """
        Evaluate a model on out-of-sample test data.
        
        Requirements: 21.2
        
        Args:
            model_id: Model ID to evaluate
            test_data: Optional tuple of (X_test, y_test). If None, uses recent data.
            
        Returns:
            Dictionary of test metrics
        """
        log.info(f"Evaluating model: {model_id}")
        
        # Get model from registry
        metadata, model_bytes = self.model_registry.get_model(model_id)
        
        # Load model
        model = pickle.loads(model_bytes)
        
        # If no test data provided, generate from recent data
        if test_data is None:
            log.info("Generating test data from recent history...")
            # Use last 2 weeks as test data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=14)
            
            training_pipeline = SupervisedTrainingPipeline(
                model_registry=self.model_registry
            )
            
            # Generate test data only
            _, _, _, _, X_test, y_test, _ = training_pipeline.generate_training_data(
                start_date=start_date,
                end_date=end_date,
                train_ratio=0.0,
                val_ratio=0.0,
                test_ratio=1.0
            )
        else:
            X_test, y_test = test_data
        
        # Evaluate model
        if metadata.model_type in [ModelType.XGBOOST.value, ModelType.LIGHTGBM.value]:
            training_pipeline = SupervisedTrainingPipeline(
                model_registry=self.model_registry
            )
            metrics = training_pipeline._evaluate_model(model, X_test, y_test)
            metrics_dict = metrics.to_dict() if hasattr(metrics, 'to_dict') else metrics
        else:
            # For RL models, use Sharpe ratio as primary metric
            # This would require running the model in simulation
            metrics_dict = metadata.test_metrics
        
        log.info(f"Evaluation complete: {metrics_dict}")
        
        return metrics_dict
    
    def compare_models(
        self,
        retrained_model_id: str,
        current_model_id: str,
        primary_metric: str = "accuracy"
    ) -> Tuple[float, bool]:
        """
        Compare performance of retrained model vs current production model.
        
        Args:
            retrained_model_id: ID of retrained model
            current_model_id: ID of current production model
            primary_metric: Primary metric for comparison (default: accuracy)
            
        Returns:
            Tuple of (improvement_percentage, should_promote)
        """
        log.info(f"Comparing models: {retrained_model_id} vs {current_model_id}")
        
        # Get metrics for both models
        retrained_metadata, _ = self.model_registry.get_model(retrained_model_id)
        current_metadata, _ = self.model_registry.get_model(current_model_id)
        
        retrained_metrics = retrained_metadata.test_metrics
        current_metrics = current_metadata.test_metrics
        
        # Get primary metric values
        retrained_value = retrained_metrics.get(primary_metric, 0.0)
        current_value = current_metrics.get(primary_metric, 0.0)
        
        # Calculate improvement percentage
        if current_value > 0:
            improvement_pct = ((retrained_value - current_value) / current_value) * 100
        else:
            improvement_pct = 0.0
        
        # Determine if should promote (≥2% improvement)
        should_promote = improvement_pct >= 2.0
        
        log.info(f"Retrained {primary_metric}: {retrained_value:.4f}")
        log.info(f"Current {primary_metric}: {current_value:.4f}")
        log.info(f"Improvement: {improvement_pct:.2f}%")
        log.info(f"Should promote: {should_promote}")
        
        return improvement_pct, should_promote
    
    def promote_model(
        self,
        model_id: str,
        environment: str = "PAPER"
    ) -> None:
        """
        Promote a model to production.
        
        Args:
            model_id: Model ID to promote
            environment: Deployment environment (PAPER or LIVE)
        """
        log.info(f"Promoting model {model_id} to {environment}")
        
        # Update deployment status
        self.model_registry.update_deployment_status(
            model_id=model_id,
            status=DeploymentStatus.PRODUCTION.value,
            environment=environment
        )
        
        log.info(f"Model promoted successfully")
    
    def retrain_and_evaluate_model(
        self,
        model_type: str,
        auto_promote: bool = True,
        promotion_threshold_pct: float = 2.0,
        primary_metric: str = "accuracy"
    ) -> RetrainingResult:
        """
        Complete retraining workflow: retrain, evaluate, and optionally promote.
        
        Requirements: 21.1, 21.2, 21.3, 21.4
        
        Args:
            model_type: Model type to retrain
            auto_promote: Whether to automatically promote if criteria met
            promotion_threshold_pct: Minimum improvement % for promotion (default: 2.0)
            primary_metric: Primary metric for comparison
            
        Returns:
            RetrainingResult with complete job information
        """
        job_id = f"{model_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        result = RetrainingResult(
            job_id=job_id,
            model_type=model_type,
            timestamp=datetime.now(),
            status=RetrainingStatus.RUNNING.value
        )
        
        try:
            log.info(f"Starting retraining job: {job_id}")
            
            # Step 1: Retrain model
            retrained_model_id, retrained_metrics = self.retrain_model(model_type)
            result.retrained_model_id = retrained_model_id
            result.retrained_metrics = retrained_metrics
            
            # Step 2: Get current production model
            current_model = self.model_registry.get_current_production_model(model_type)
            
            if current_model is None:
                # No current production model, promote new model
                log.info("No current production model found, promoting new model")
                result.promotion_decision = PromotionDecision.NO_CURRENT_MODEL.value
                
                if auto_promote:
                    self.promote_model(retrained_model_id)
                
                result.status = RetrainingStatus.COMPLETED.value
            else:
                result.current_model_id = current_model.model_id
                result.current_metrics = current_model.test_metrics
                
                # Step 3: Compare models
                improvement_pct, should_promote = self.compare_models(
                    retrained_model_id=retrained_model_id,
                    current_model_id=current_model.model_id,
                    primary_metric=primary_metric
                )
                
                result.performance_improvement_pct = improvement_pct
                
                # Step 4: Make promotion decision
                if should_promote and improvement_pct >= promotion_threshold_pct:
                    log.info(f"Retrained model outperforms by {improvement_pct:.2f}%, promoting")
                    result.promotion_decision = PromotionDecision.PROMOTED.value
                    
                    if auto_promote:
                        # Retire current model
                        self.model_registry.update_deployment_status(
                            model_id=current_model.model_id,
                            status=DeploymentStatus.RETIRED.value
                        )
                        
                        # Promote new model
                        self.promote_model(retrained_model_id)
                else:
                    log.info(f"Retrained model improvement ({improvement_pct:.2f}%) below threshold, keeping current model")
                    result.promotion_decision = PromotionDecision.KEPT_CURRENT.value
                
                result.status = RetrainingStatus.COMPLETED.value
            
            # Log result
            self._log_retraining_result(result)
            
            log.info(f"Retraining job completed: {job_id}")
            
        except Exception as e:
            log.error(f"Retraining job failed: {e}")
            result.status = RetrainingStatus.FAILED.value
            result.error_message = str(e)
            self._log_retraining_result(result)
        
        return result
    
    def _log_retraining_result(self, result: RetrainingResult):
        """
        Log retraining result to file.
        
        Requirements: 21.4
        """
        with self._lock:
            with open(self.retraining_log_path, 'a') as f:
                f.write(json.dumps(result.to_dict()) + '\n')
        
        log.info(f"Retraining result logged: {result.job_id}")
    
    def get_retraining_history(
        self,
        model_type: Optional[str] = None,
        limit: int = 100
    ) -> List[RetrainingResult]:
        """
        Get retraining history from log file.
        
        Args:
            model_type: Optional filter by model type
            limit: Maximum number of results to return
            
        Returns:
            List of RetrainingResult objects
        """
        results = []
        
        if not self.retraining_log_path.exists():
            return results
        
        with open(self.retraining_log_path, 'r') as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    
                    # Filter by model type if specified
                    if model_type and data.get('model_type') != model_type:
                        continue
                    
                    # Convert timestamp string back to datetime
                    if 'timestamp' in data and isinstance(data['timestamp'], str):
                        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
                    
                    result = RetrainingResult(**data)
                    results.append(result)
                    
                    if len(results) >= limit:
                        break
                        
                except Exception as e:
                    log.warning(f"Failed to parse retraining log entry: {e}")
        
        # Return most recent first
        results.reverse()
        
        return results
    
    def trigger_manual_retraining(
        self,
        model_type: str,
        auto_promote: bool = False
    ) -> RetrainingResult:
        """
        Manually trigger retraining for a specific model type.
        
        Args:
            model_type: Model type to retrain
            auto_promote: Whether to automatically promote if criteria met
            
        Returns:
            RetrainingResult
        """
        log.info(f"Manual retraining triggered for {model_type}")
        
        return self.retrain_and_evaluate_model(
            model_type=model_type,
            auto_promote=auto_promote
        )
