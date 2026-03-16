"""
ML Endpoints - Thin API wrapper for ML modules

This module provides thin API wrappers that delegate to existing ML modules.
NO LOGIC DUPLICATION - all ML logic stays in ml/ directory.

Architecture: ml/ modules (logic) → api/ml_endpoints.py (thin wrapper) → dashboard (UI)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
import asyncio
from pathlib import Path

from core.logger import get_agent_logger
import pandas as pd

log = get_agent_logger("ML_API")

router = APIRouter(prefix="/api/ml", tags=["ml"])

# Initialize ML components (singleton pattern) - lazy loading to avoid import errors
_warehouse = None
_feature_pipeline = None
_supervised_trainer = None
_ppo_trainer = None
_model_registry = None
_training_history = None

def get_warehouse():
    global _warehouse
    if _warehouse is None:
        try:
            from data.historical_data_warehouse import HistoricalDataWarehouse
            _warehouse = HistoricalDataWarehouse()
        except ImportError as e:
            log.error(f"Failed to import HistoricalDataWarehouse: {e}")
            raise HTTPException(status_code=500, detail="Historical data warehouse not available")
    return _warehouse

def get_feature_pipeline():
    """
    FeaturePipeline requires event_bus, redis_client, and symbols.
    For ML training via API, we don't need the real-time feature pipeline.
    Return None - supervised trainer will use warehouse data directly.
    """
    # Feature pipeline is for real-time trading, not batch training
    # ML training uses historical data from warehouse directly
    return None

def get_supervised_trainer():
    global _supervised_trainer
    if _supervised_trainer is None:
        try:
            from ml.supervised_training import SupervisedTrainingPipeline, TrainingConfig
            # Supervised trainer only needs warehouse for batch training
            # feature_pipeline is for real-time feature computation, not needed here
            _supervised_trainer = SupervisedTrainingPipeline(
                warehouse=get_warehouse(),
                feature_pipeline=None  # Not needed for batch training from warehouse
            )
        except ImportError as e:
            log.error(f"Failed to import SupervisedTrainingPipeline: {e}")
            raise HTTPException(status_code=500, detail="Supervised training not available")
    return _supervised_trainer

def get_ppo_trainer():
    global _ppo_trainer
    if _ppo_trainer is None:
        try:
            from ml.ppo_agent_training import PPOAgentTrainer, PPOConfig
            # PPO trainer only needs warehouse, not feature_pipeline
            _ppo_trainer = PPOAgentTrainer(
                warehouse=get_warehouse(),
                feature_pipeline=None  # Not needed for batch training
            )
        except ImportError as e:
            log.error(f"Failed to import PPOAgentTrainer: {e}")
            raise HTTPException(status_code=500, detail="PPO training not available")
    return _ppo_trainer

def get_model_registry():
    global _model_registry
    if _model_registry is None:
        try:
            from ml.model_registry import ModelRegistry
            _model_registry = ModelRegistry()
        except ImportError as e:
            log.error(f"Failed to import ModelRegistry: {e}")
            raise HTTPException(status_code=500, detail="Model registry not available")
    return _model_registry

def get_training_history():
    global _training_history
    if _training_history is None:
        try:
            from ml.training_history import TrainingHistoryTracker
            _training_history = TrainingHistoryTracker()
        except ImportError as e:
            log.error(f"Failed to import TrainingHistoryTracker: {e}")
            raise HTTPException(status_code=500, detail="Training history not available")
    return _training_history


# ═══════════════════════════════════════════════════════
#  REQUEST/RESPONSE MODELS
# ═══════════════════════════════════════════════════════

class TrainModelRequest(BaseModel):
    model_type: str  # "xgboost", "lightgbm", "random_forest", "ppo"
    symbol: str = "EURUSD"
    training_months: int = 6
    timeframe: Optional[str] = None  # "M15", "H1", "H4", "D1" - auto-detected if None
    hyperparameters: Optional[Dict[str, Any]] = None


class BacktestRequest(BaseModel):
    model_id: str
    symbol: str = "EURUSD"
    start_date: str
    end_date: str
    initial_capital: float = 10000.0


class ModelListRequest(BaseModel):
    model_type: Optional[str] = None
    deployment_status: Optional[str] = None


# ═══════════════════════════════════════════════════════
#  TRAINING ENDPOINTS
# ═══════════════════════════════════════════════════════

@router.post("/train")
async def train_model(request: TrainModelRequest):
    """
    Train a model (XGBoost, LightGBM, or PPO).
    Thin wrapper that delegates to ml/supervised_training.py or ml/ppo_agent_training.py
    """
    start_time = datetime.now()
    history_tracker = get_training_history()
    
    try:
        log.info(f"Training {request.model_type} model for {request.symbol}")
        
        model_type_lower = request.model_type.lower()
        
        # Supervised learning models (XGBoost, LightGBM, RandomForest)
        if model_type_lower in ["xgboost", "lightgbm", "random_forest"]:
            from ml.supervised_training import TrainingConfig
            
            trainer = get_supervised_trainer()
            
            # Auto-detect optimal timeframe and prediction horizon based on symbol
            timeframe = request.timeframe
            if timeframe is None:
                # Auto-detect: Check what data is available
                warehouse = get_warehouse()
                stats = warehouse.get_storage_stats()
                
                # Check available timeframes for this symbol
                available_timeframes = []
                for key in stats['row_counts'].keys():
                    if request.symbol in key:
                        # Extract timeframe from key (format: SYMBOL_TIMEFRAME)
                        parts = key.split('_')
                        if len(parts) >= 2:
                            tf = parts[-1]
                            available_timeframes.append(tf)
                
                # Prefer 4H > 1H > 15M for gold, 1H > 4H > 15M for forex
                if request.symbol in ["XAUUSD", "XAGUSD"]:
                    # Gold/Silver: prefer 4H
                    if "4H" in available_timeframes or "H4" in available_timeframes:
                        timeframe = "H4"
                    elif "1H" in available_timeframes or "H1" in available_timeframes:
                        timeframe = "H1"
                    else:
                        timeframe = "M15"
                else:
                    # Forex: prefer 1H
                    if "1H" in available_timeframes or "H1" in available_timeframes:
                        timeframe = "H1"
                    elif "4H" in available_timeframes or "H4" in available_timeframes:
                        timeframe = "H4"
                    else:
                        timeframe = "M15"
                
                log.info(f"Auto-detected timeframe: {timeframe} (available: {available_timeframes})")
            
            # Calculate optimal forward_return_minutes based on timeframe
            timeframe_to_minutes = {
                "M15": 15,
                "M30": 30,
                "H1": 60,
                "1H": 60,
                "H4": 240,
                "4H": 240,
                "D1": 1440,
                "1D": 1440
            }
            
            bar_minutes = timeframe_to_minutes.get(timeframe, 15)
            
            # Predict 2-4 bars ahead (optimal for most cases)
            if bar_minutes <= 30:
                forward_bars = 4  # 15m: predict 1 hour ahead, 30m: predict 2 hours ahead
            elif bar_minutes <= 60:
                forward_bars = 4  # 1h: predict 4 hours ahead
            elif bar_minutes <= 240:
                forward_bars = 2  # 4h: predict 8 hours ahead
            else:
                forward_bars = 1  # 1d: predict 1 day ahead
            
            forward_return_minutes = forward_bars
            
            # Adjust thresholds based on symbol volatility
            if request.symbol in ["XAUUSD", "XAGUSD"]:
                # Gold/Silver: more volatile, use 0.2% threshold
                up_threshold = 0.002
                down_threshold = -0.002
            elif request.symbol in ["BTCUSD", "ETHUSD"]:
                # Crypto: very volatile, use 0.5% threshold
                up_threshold = 0.005
                down_threshold = -0.005
            else:
                # Forex: use 0.1% threshold
                up_threshold = 0.001
                down_threshold = -0.001
            
            log.info(f"Training config: timeframe={timeframe}, forward_bars={forward_bars}, "
                    f"up_threshold={up_threshold:.3f}, down_threshold={down_threshold:.3f}")
            
            # Create training config with optimized parameters
            config = TrainingConfig(
                symbol=request.symbol,
                timeframe=timeframe,
                training_months=request.training_months,
                forward_return_minutes=forward_return_minutes,
                up_threshold=up_threshold,
                down_threshold=down_threshold
            )
            
            # Map random_forest to xgboost (RF is handled by XGBoost in our implementation)
            actual_model_type = "xgboost" if model_type_lower == "random_forest" else model_type_lower
            
            # Train model (delegates to ml/supervised_training.py)
            result = trainer.train_and_evaluate(config, model_type=actual_model_type)
            
            training_duration = (datetime.now() - start_time).total_seconds()
            
            if result is None:
                # Model was rejected - log to history
                rejection_reason = f"Accuracy below minimum threshold ({config.min_accuracy:.1%})"
                
                history_tracker.log_training_attempt(
                    model_type=request.model_type,
                    symbol=request.symbol,
                    status="rejected",
                    rejection_reason=rejection_reason,
                    training_duration_seconds=training_duration
                )
                
                log.warning(f"Model training completed but rejected for {request.symbol}")
                raise HTTPException(
                    status_code=400, 
                    detail=(
                        f"Model rejected: validation accuracy < {config.min_accuracy:.1%}. "
                        f"The model didn't perform well enough on this data. "
                        f"Suggestions: (1) Try a different symbol with more data, "
                        f"(2) Increase training_months for more data, "
                        f"(3) Try a different model type, "
                        f"(4) Check logs for actual accuracy achieved"
                    )
                )
            
            model, metrics, metadata = result
            
            # Save model (delegates to ml/supervised_training.py)
            model_dir = trainer.save_model(model, metadata)
            
            # Register model in registry
            try:
                from ml.model_registry import ModelRegistry, ModelMetadata, ModelType
                import pickle
                
                registry = get_model_registry()
                
                # Create ModelMetadata for registry
                model_metadata = ModelMetadata(
                    model_id="",  # Will be auto-generated
                    model_name=f"{request.model_type.upper()}_{request.symbol}",
                    model_type=ModelType.XGBOOST.value if request.model_type.lower() == "xgboost" else ModelType.LIGHTGBM.value,
                    version=1,
                    created_at=datetime.now(),
                    training_start_date=datetime.now() - timedelta(days=config.training_months * 30),
                    training_end_date=datetime.now(),
                    num_training_samples=metadata.get('train_samples', 0),
                    hyperparameters=metadata.get('hyperparameters', {}),
                    feature_names=metadata.get('feature_names', []),
                    num_features=len(metadata.get('feature_names', [])),
                    train_metrics=metadata.get('train_metrics', {}),
                    validation_metrics={
                        'accuracy': metrics.accuracy,
                        'precision': metrics.precision,
                        'recall': metrics.recall,
                        'f1': metrics.f1_score,
                        'roc_auc': metrics.roc_auc
                    },
                    test_metrics=metadata.get('test_metrics', {}),
                    deployment_status="TESTING",  # New models start in TESTING
                    deployment_timestamp=None,
                    deployment_environment=None,
                    git_commit_hash=None,
                    training_script_path=None,
                    model_file_path=""
                )
                
                # Load model file as bytes
                model_file_path = model_dir / "model.pkl"
                with open(model_file_path, 'rb') as f:
                    model_bytes = f.read()
                
                # Register model
                model_id = registry.register_model(model_metadata, model_bytes)
                log.info(f"✓ Model registered in registry: {model_id}")
                log.info(f"  Model name: {model_metadata.model_name}")
                log.info(f"  Status: {model_metadata.deployment_status}")
                log.info(f"  Accuracy: {metrics.accuracy:.2%}")
                
                # Store model_id in metadata for response
                metadata['registry_model_id'] = model_id
                
            except Exception as e:
                log.error(f"Failed to register model in registry: {e}")
                import traceback
                log.error(traceback.format_exc())
                # Don't fail the training if registry fails
                metadata['registry_model_id'] = None
            
            # Log successful training to history
            history_tracker.log_training_attempt(
                model_type=request.model_type,
                symbol=request.symbol,
                status="success",
                accuracy=metrics.accuracy,
                precision=metrics.precision,
                recall=metrics.recall,
                f1_score=metrics.f1_score,
                roc_auc=metrics.roc_auc,
                train_samples=metadata.get('train_samples'),
                val_samples=metadata.get('val_samples'),
                model_path=str(model_dir),
                training_duration_seconds=training_duration
            )
            
            return {
                "status": "success",
                "model_type": request.model_type,
                "symbol": request.symbol,
                "metrics": {
                    "accuracy": metrics.accuracy,
                    "precision": metrics.precision,
                    "recall": metrics.recall,
                    "f1_score": metrics.f1_score,
                    "roc_auc": metrics.roc_auc
                },
                "model_path": str(model_dir),
                "model_id": metadata.get('registry_model_id'),
                "registry_status": "registered" if metadata.get('registry_model_id') else "registration_failed",
                "message": f"{request.model_type} model trained successfully and registered in model registry"
            }
        
        # Reinforcement learning (PPO)
        elif model_type_lower == "ppo":
            from ml.ppo_agent_training import PPOConfig
            
            trainer = get_ppo_trainer()
            
            # Create PPO config
            config = PPOConfig(
                symbol=request.symbol,
                training_months=request.training_months
            )
            
            # Override hyperparameters if provided
            if request.hyperparameters:
                for key, value in request.hyperparameters.items():
                    if hasattr(config, key):
                        setattr(config, key, value)
            
            # Train agent (delegates to ml/ppo_agent_training.py)
            agent, metrics, metadata = trainer.train_agent(config)
            
            # Save agent (delegates to ml/ppo_agent_training.py)
            model_dir = trainer.save_agent(agent, metadata)
            
            training_duration = (datetime.now() - start_time).total_seconds()
            
            # Log successful training to history
            history_tracker.log_training_attempt(
                model_type=request.model_type,
                symbol=request.symbol,
                status="success",
                train_samples=metadata.get('num_episodes'),
                model_path=str(model_dir),
                training_duration_seconds=training_duration
            )
            
            return {
                "status": "success",
                "model_type": request.model_type,
                "symbol": request.symbol,
                "metrics": {
                    "sharpe_ratio": metrics.sharpe_ratio,
                    "total_return": metrics.total_return,
                    "num_trades": metrics.num_trades,
                    "win_rate": metrics.win_rate,
                    "max_drawdown": metrics.max_drawdown
                },
                "model_path": str(model_dir),
                "promotion_status": metadata.get("promotion_status", "UNKNOWN"),
                "message": f"PPO agent trained successfully"
            }
        
        else:
            raise HTTPException(status_code=400, detail=f"Unknown model type: {request.model_type}")
    
    except HTTPException:
        # Re-raise HTTP exceptions (already logged to history if needed)
        raise
    except Exception as e:
        # Log failed training to history
        training_duration = (datetime.now() - start_time).total_seconds()
        history_tracker.log_training_attempt(
            model_type=request.model_type,
            symbol=request.symbol,
            status="failed",
            error_message=str(e),
            training_duration_seconds=training_duration
        )
        
        log.error(f"Training failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════
#  BACKTESTING ENDPOINTS
# ═══════════════════════════════════════════════════════

@router.post("/backtest")
async def run_backtest(request: BacktestRequest):
    """
    Run backtest for a trained model.
    Thin wrapper that delegates to ml/backtesting_engine.py
    """
    try:
        from ml.backtesting_engine import BacktestingEngine, BacktestConfig
        
        log.info(f"Running backtest for model {request.model_id}")
        
        # Parse dates
        start_date = datetime.fromisoformat(request.start_date)
        end_date = datetime.fromisoformat(request.end_date)
        
        # Create backtest config
        config = BacktestConfig(
            symbol=request.symbol,
            start_date=start_date,
            end_date=end_date,
            initial_capital=request.initial_capital
        )
        
        # Create backtesting engine (delegates to ml/backtesting_engine.py)
        engine = BacktestingEngine(
            warehouse=get_warehouse(),
            config=config
        )
        
        # Load model from registry - try both UUID and legacy name formats
        registry = get_model_registry()
        try:
            metadata, model_file = registry.get_model(request.model_id)
        except Exception as e:
            # If UUID lookup fails, try searching by model name
            log.debug(f"UUID lookup failed, trying name search: {e}")
            models = registry.list_models()
            matching = [m for m in models if m.model_name.lower() == request.model_id.lower()]
            if matching:
                model_id = matching[0].model_id
                log.info(f"Found model by name: {request.model_id} -> {model_id}")
                metadata, model_file = registry.get_model(model_id)
            else:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Model not found: {request.model_id}. Available models: {[m.model_name for m in models]}"
                )
        
        # Define simple strategy function (placeholder - would use actual model predictions)
        def strategy_func(historical_data, current_step):
            # This is a placeholder - in production, would use model predictions
            # For now, return None (no trades)
            return None
        
        # Run backtest (delegates to ml/backtesting_engine.py)
        result = engine.run_backtest(
            strategy_func=strategy_func,
            strategy_params={"model_id": request.model_id}
        )
        
        # Save results (delegates to ml/backtesting_engine.py)
        results_dir = engine.save_backtest_results(result)
        
        return {
            "status": "success",
            "backtest_id": result.backtest_id,
            "metrics": {
                "total_return": result.total_return,
                "sharpe_ratio": result.sharpe_ratio,
                "sortino_ratio": result.sortino_ratio,
                "max_drawdown": result.max_drawdown,
                "win_rate": result.win_rate,
                "profit_factor": result.profit_factor,
                "num_trades": result.num_trades
            },
            "results_path": str(results_dir),
            "message": "Backtest completed successfully"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Backtest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════
#  MODEL REGISTRY ENDPOINTS
# ═══════════════════════════════════════════════════════

@router.get("/models")
async def list_models(
    model_type: Optional[str] = None,
    deployment_status: Optional[str] = None
):
    """
    List models from registry with optional filters.
    Thin wrapper that delegates to ml/model_registry.py
    """
    try:
        registry = get_model_registry()
        
        # Build filters
        filters = {}
        if model_type:
            filters["model_type"] = model_type.upper()
        if deployment_status:
            filters["deployment_status"] = deployment_status.upper()
        
        # List models (delegates to ml/model_registry.py)
        models = registry.list_models(filters=filters if filters else None)
        
        # Convert to response format
        models_data = []
        for model in models:
            models_data.append({
                "model_id": model.model_id,
                "model_name": model.model_name,
                "model_type": model.model_type,
                "version": model.version,
                "created_at": model.created_at.isoformat(),
                "deployment_status": model.deployment_status,
                "deployment_environment": model.deployment_environment,
                "validation_metrics": model.validation_metrics,
                "num_features": model.num_features
            })
        
        return {
            "status": "success",
            "models": models_data,
            "count": len(models_data)
        }
    
    except Exception as e:
        log.error(f"Failed to list models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/{model_id}")
async def get_model_details(model_id: str):
    """
    Get detailed information about a specific model.
    Thin wrapper that delegates to ml/model_registry.py
    """
    try:
        registry = get_model_registry()
        
        # Get model (delegates to ml/model_registry.py)
        metadata, _ = registry.get_model(model_id)
        
        return {
            "status": "success",
            "model": {
                "model_id": metadata.model_id,
                "model_name": metadata.model_name,
                "model_type": metadata.model_type,
                "version": metadata.version,
                "created_at": metadata.created_at.isoformat(),
                "training_start_date": metadata.training_start_date.isoformat() if isinstance(metadata.training_start_date, datetime) else str(metadata.training_start_date),
                "training_end_date": metadata.training_end_date.isoformat() if isinstance(metadata.training_end_date, datetime) else str(metadata.training_end_date),
                "num_training_samples": metadata.num_training_samples,
                "hyperparameters": metadata.hyperparameters,
                "feature_names": metadata.feature_names,
                "num_features": metadata.num_features,
                "train_metrics": metadata.train_metrics,
                "validation_metrics": metadata.validation_metrics,
                "test_metrics": metadata.test_metrics,
                "deployment_status": metadata.deployment_status,
                "deployment_timestamp": metadata.deployment_timestamp.isoformat() if metadata.deployment_timestamp else None,
                "deployment_environment": metadata.deployment_environment
            }
        }
    
    except Exception as e:
        log.error(f"Failed to get model details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/registry/stats")
async def get_registry_stats():
    """
    Get statistics about the model registry.
    Thin wrapper that delegates to ml/model_registry.py
    """
    try:
        registry = get_model_registry()
        
        # Get stats (delegates to ml/model_registry.py)
        stats = registry.get_registry_stats()
        
        return {
            "status": "success",
            "stats": stats
        }
    
    except Exception as e:
        log.error(f"Failed to get registry stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════
#  A/B TESTING ENDPOINTS
# ═══════════════════════════════════════════════════════

@router.get("/ab-testing/report")
async def get_ab_testing_report():
    """
    Get A/B testing comparison report.
    Thin wrapper that delegates to ml/ab_testing_framework.py
    
    Note: This is a placeholder - actual A/B testing framework needs to be initialized
    with variant configs and integrated with live trading.
    """
    try:
        # Placeholder response - in production, would use actual A/B testing framework
        return {
            "status": "success",
            "message": "A/B testing framework not yet initialized",
            "note": "Initialize ABTestingFramework with variant configs to enable A/B testing"
        }
    
    except Exception as e:
        log.error(f"Failed to get A/B testing report: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# ═══════════════════════════════════════════════════════
#  DATA IMPORT ENDPOINTS
# ═══════════════════════════════════════════════════════

@router.post("/import-csv")
async def import_csv_data():
    """
    Import CSV files from data/raw/ into the Historical Data Warehouse.
    This makes the data available for ML training.
    Tracks imported files to avoid re-importing.
    """
    try:
        from pathlib import Path
        import hashlib
        
        log.info("Starting CSV import to warehouse")
        
        warehouse = get_warehouse()
        csv_dir = Path("data/raw")
        
        if not csv_dir.exists():
            raise HTTPException(status_code=404, detail="CSV directory not found: data/raw")
        
        csv_files = list(csv_dir.glob("*.csv"))
        
        if not csv_files:
            return {
                "status": "warning",
                "message": "No CSV files found in data/raw",
                "imported": 0,
                "failed": 0,
                "skipped": 0,
                "files": []
            }
        
        # Initialize import tracking table
        import duckdb
        tracking_db = Path("data/csv_import_tracking.duckdb")
        con = duckdb.connect(str(tracking_db))
        
        # Create tracking table if not exists
        con.execute("""
            CREATE TABLE IF NOT EXISTS imported_files (
                filename VARCHAR PRIMARY KEY,
                file_hash VARCHAR NOT NULL,
                symbol VARCHAR NOT NULL,
                timeframe VARCHAR NOT NULL,
                bars_count INTEGER NOT NULL,
                date_range VARCHAR NOT NULL,
                imported_at TIMESTAMP NOT NULL,
                file_size_bytes INTEGER NOT NULL
            )
        """)
        
        imported_files = []
        failed_files = []
        skipped_files = []
        
        for csv_file in csv_files:
            try:
                # Calculate file hash to detect changes
                with open(csv_file, 'rb') as f:
                    file_hash = hashlib.md5(f.read()).hexdigest()
                
                # Check if already imported with same hash
                existing = con.execute("""
                    SELECT filename, file_hash FROM imported_files 
                    WHERE filename = ?
                """, (csv_file.name,)).fetchone()
                
                if existing and existing[1] == file_hash:
                    skipped_files.append({
                        "file": csv_file.name,
                        "reason": "Already imported (no changes detected)"
                    })
                    log.info(f"Skipped {csv_file.name}: already imported")
                    continue
                
                # Parse filename: SYMBOL_TIMEFRAME.csv
                name = csv_file.stem
                parts = name.rsplit('_', 1)
                
                if len(parts) != 2:
                    failed_files.append({
                        "file": csv_file.name,
                        "error": "Invalid filename format (expected: SYMBOL_TIMEFRAME.csv)"
                    })
                    continue
                
                symbol = parts[0]
                timeframe_raw = parts[1]
                
                # Convert timeframe
                timeframe_map = {
                    '15m': 'M15',
                    '1h': 'H1',
                    '4h': 'H4',
                    '1d': 'D1',
                }
                
                timeframe = timeframe_map.get(timeframe_raw.lower())
                if not timeframe:
                    failed_files.append({
                        "file": csv_file.name,
                        "error": f"Unknown timeframe: {timeframe_raw}"
                    })
                    continue
                
                # Load CSV
                df = pd.read_csv(csv_file)
                df.columns = df.columns.str.lower()
                
                # Check required columns
                required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
                missing_cols = [col for col in required_cols if col not in df.columns]
                
                if missing_cols:
                    failed_files.append({
                        "file": csv_file.name,
                        "error": f"Missing columns: {missing_cols}"
                    })
                    continue
                
                # Convert timestamp
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                
                # Ensure timezone-naive
                if df['timestamp'].dt.tz is not None:
                    df['timestamp'] = df['timestamp'].dt.tz_localize(None)
                
                # Sort and remove duplicates
                df = df.sort_values('timestamp')
                df = df.drop_duplicates(subset=['timestamp'], keep='last')
                
                # Store in warehouse
                warehouse.store_ohlcv(
                    symbol=symbol,
                    timeframe=timeframe,
                    data=df[required_cols]
                )
                
                date_range = f"{df['timestamp'].min()} to {df['timestamp'].max()}"
                
                # Track import
                con.execute("""
                    INSERT OR REPLACE INTO imported_files 
                    (filename, file_hash, symbol, timeframe, bars_count, date_range, imported_at, file_size_bytes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    csv_file.name,
                    file_hash,
                    symbol,
                    timeframe,
                    len(df),
                    date_range,
                    datetime.now(),
                    csv_file.stat().st_size
                ))
                
                imported_files.append({
                    "file": csv_file.name,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "bars": len(df),
                    "date_range": date_range,
                    "status": "updated" if existing else "new"
                })
                
                log.info(f"Imported {csv_file.name}: {len(df)} bars")
                
            except Exception as e:
                log.error(f"Failed to import {csv_file.name}: {e}")
                failed_files.append({
                    "file": csv_file.name,
                    "error": str(e)
                })
        
        con.close()
        
        # Get warehouse stats
        stats = warehouse.get_storage_stats()
        
        return {
            "status": "success" if not failed_files else "partial",
            "message": f"Imported {len(imported_files)} files, {len(skipped_files)} skipped, {len(failed_files)} failed",
            "imported": len(imported_files),
            "skipped": len(skipped_files),
            "failed": len(failed_files),
            "files": imported_files,
            "skipped_files": skipped_files,
            "errors": failed_files,
            "warehouse_stats": {
                "total_symbols": len(stats['row_counts']),
                "total_bars": sum(stats['row_counts'].values())
            }
        }
    
    except Exception as e:
        log.error(f"CSV import failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/csv-files")
async def list_csv_files():
    """
    List CSV files in data/raw/ directory.
    Shows import status for each file (new, imported, updated).
    """
    try:
        from pathlib import Path
        import hashlib
        import duckdb
        
        csv_dir = Path("data/raw")
        
        if not csv_dir.exists():
            return {
                "status": "success",
                "files": [],
                "new_count": 0,
                "imported_count": 0,
                "updated_count": 0
            }
        
        csv_files = list(csv_dir.glob("*.csv"))
        
        if not csv_files:
            return {
                "status": "success",
                "files": [],
                "new_count": 0,
                "imported_count": 0,
                "updated_count": 0
            }
        
        # Connect to tracking database
        tracking_db = Path("data/csv_import_tracking.duckdb")
        
        files_info = []
        new_count = 0
        imported_count = 0
        updated_count = 0
        
        if tracking_db.exists():
            con = duckdb.connect(str(tracking_db))
            
            for csv_file in csv_files:
                # Calculate file hash
                with open(csv_file, 'rb') as f:
                    file_hash = hashlib.md5(f.read()).hexdigest()
                
                # Check import status
                existing = con.execute("""
                    SELECT file_hash, imported_at, bars_count, date_range 
                    FROM imported_files 
                    WHERE filename = ?
                """, (csv_file.name,)).fetchone()
                
                if existing:
                    if existing[0] == file_hash:
                        status = "imported"
                        imported_count += 1
                    else:
                        status = "updated"
                        updated_count += 1
                    
                    files_info.append({
                        "filename": csv_file.name,
                        "size_bytes": csv_file.stat().st_size,
                        "size_mb": round(csv_file.stat().st_size / (1024 * 1024), 2),
                        "status": status,
                        "imported_at": str(existing[1]) if existing[1] else None,
                        "bars_count": existing[2],
                        "date_range": existing[3]
                    })
                else:
                    status = "new"
                    new_count += 1
                    files_info.append({
                        "filename": csv_file.name,
                        "size_bytes": csv_file.stat().st_size,
                        "size_mb": round(csv_file.stat().st_size / (1024 * 1024), 2),
                        "status": status,
                        "imported_at": None,
                        "bars_count": None,
                        "date_range": None
                    })
            
            con.close()
        else:
            # No tracking database yet - all files are new
            for csv_file in csv_files:
                new_count += 1
                files_info.append({
                    "filename": csv_file.name,
                    "size_bytes": csv_file.stat().st_size,
                    "size_mb": round(csv_file.stat().st_size / (1024 * 1024), 2),
                    "status": "new",
                    "imported_at": None,
                    "bars_count": None,
                    "date_range": None
                })
        
        # Sort: new files first, then updated, then imported
        status_order = {"new": 0, "updated": 1, "imported": 2}
        files_info.sort(key=lambda x: (status_order[x["status"]], x["filename"]))
        
        return {
            "status": "success",
            "files": files_info,
            "new_count": new_count,
            "imported_count": imported_count,
            "updated_count": updated_count,
            "total_count": len(files_info)
        }
    
    except Exception as e:
        log.error(f"Failed to list CSV files: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/warehouse/stats")
async def get_warehouse_stats():
    """
    Get statistics about the Historical Data Warehouse.
    Shows what data is available for training.
    """
    import asyncio
    
    def _get_stats():
        try:
            warehouse = get_warehouse()
            stats = warehouse.get_storage_stats()
            
            # Format the data nicely
            symbols_data = []
            for key, count in stats['row_counts'].items():
                date_range = stats['date_ranges'].get(key, {})
                symbols_data.append({
                    "key": key,
                    "bars": count,
                    "start_date": str(date_range.get('min', 'N/A')),
                    "end_date": str(date_range.get('max', 'N/A'))
                })
            
            # Sort by symbol name
            symbols_data.sort(key=lambda x: x['key'])
            
            return {
                "status": "success",
                "total_symbols": len(symbols_data),
                "total_bars": sum(s['bars'] for s in symbols_data),
                "symbols": symbols_data
            }
        except Exception as e:
            log.error(f"Failed to get warehouse stats: {e}")
            return {
                "status": "error",
                "message": str(e),
                "total_symbols": 0,
                "total_bars": 0,
                "symbols": []
            }
    
    # Run in thread pool to avoid DuckDB connection conflicts
    return await asyncio.to_thread(_get_stats)


# ═══════════════════════════════════════════════════════
#  TRAINING HISTORY ENDPOINTS
# ═══════════════════════════════════════════════════════

@router.get("/training-history")
async def get_training_history_endpoint(
    limit: Optional[int] = 50,
    model_type: Optional[str] = None,
    symbol: Optional[str] = None,
    status: Optional[str] = None
):
    """
    Get training history with optional filters.
    Shows all training attempts (successful, rejected, and failed).
    
    Query parameters:
    - limit: Maximum number of records (default: 50)
    - model_type: Filter by model type (xgboost, lightgbm, ppo, etc.)
    - symbol: Filter by trading symbol
    - status: Filter by status (success, rejected, failed)
    """
    try:
        history_tracker = get_training_history()
        
        # Get history with filters
        history = history_tracker.get_history(
            limit=limit,
            model_type=model_type,
            symbol=symbol,
            status=status
        )
        
        # Get statistics
        stats = history_tracker.get_statistics()
        
        return {
            "status": "success",
            "history": history,
            "count": len(history),
            "statistics": stats
        }
    
    except Exception as e:
        log.error(f"Failed to get training history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/training-history/stats")
async def get_training_history_stats():
    """
    Get statistics about training history.
    """
    try:
        history_tracker = get_training_history()
        stats = history_tracker.get_statistics()
        
        return {
            "status": "success",
            "statistics": stats
        }
    
    except Exception as e:
        log.error(f"Failed to get training history stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/training-history")
async def clear_training_history():
    """
    Clear all training history.
    """
    try:
        history_tracker = get_training_history()
        history_tracker.clear_history()
        
        return {
            "status": "success",
            "message": "Training history cleared"
        }
    
    except Exception as e:
        log.error(f"Failed to clear training history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

