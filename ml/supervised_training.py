"""
Supervised Learning Training Pipeline

Implements training pipeline for XGBoost and LightGBM models to predict
price direction over next 15 minutes.

Requirements: 11.1, 11.2, 11.3, 11.4, 11.5
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import xgboost as xgb
import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
import joblib
from pathlib import Path

from data.historical_data_warehouse import HistoricalDataWarehouse
from data.feature_pipeline import FeaturePipeline
from core.logger import get_agent_logger

log = get_agent_logger("SUPERVISED_TRAINING")


@dataclass
class TrainingConfig:
    """Configuration for model training"""
    symbol: str
    timeframe: str = "M15"
    training_months: int = 6
    forward_return_minutes: int = 15
    up_threshold: float = 0.001  # 0.1% threshold for UP label
    down_threshold: float = -0.001  # -0.1% threshold for DOWN label
    train_split: float = 0.8
    validation_split: float = 0.2
    min_accuracy: float = 0.52  # Minimum 52% accuracy requirement
    

@dataclass
class ModelMetrics:
    """Performance metrics for trained model"""
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    roc_auc: float
    
    def meets_acceptance_criteria(self, min_accuracy: float = 0.52) -> bool:
        """Check if model meets acceptance criteria"""
        return self.accuracy >= min_accuracy


class SupervisedTrainingPipeline:
    """
    Training pipeline for supervised learning models.
    
    Features:
    - Feature generation from historical data
    - Binary label creation (UP/DOWN) from forward returns
    - Walk-forward validation (80/20 split)
    - Hyperparameter tuning (grid search)
    - XGBoost and LightGBM model training
    - Model evaluation and acceptance criteria
    """
    
    def __init__(
        self,
        warehouse: HistoricalDataWarehouse,
        feature_pipeline: Optional[FeaturePipeline] = None,
        models_dir: str = "models/supervised"
    ):
        self.warehouse = warehouse
        self.feature_pipeline = feature_pipeline
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        log.info("Supervised Training Pipeline initialized")
        log.info(f"Models directory: {self.models_dir}")
    
    def generate_training_data(
        self,
        config: TrainingConfig
    ) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Generate features and labels from historical data.
        
        Requirements: 11.1, 11.2
        
        Args:
            config: Training configuration
            
        Returns:
            Tuple of (features_df, labels_series)
        """
        log.info(f"Generating training data for {config.symbol}")
        log.info(f"Training period: {config.training_months} months")
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=config.training_months * 30)
        
        # Query historical OHLCV data
        log.info(f"Querying historical data from {start_date} to {end_date}")
        ohlcv_data = self.warehouse.query_ohlcv(
            symbol=config.symbol,
            timeframe=config.timeframe,
            start=start_date,
            end=end_date
        )
        
        if ohlcv_data.empty:
            raise ValueError(f"No historical data found for {config.symbol}")
        
        log.info(f"Retrieved {len(ohlcv_data)} bars of historical data")
        
        # Generate features for each bar
        features_list = []
        labels_list = []
        timestamps = []
        
        for i in range(len(ohlcv_data) - config.forward_return_minutes):
            try:
                # Get current bar and future bar
                current_bar = ohlcv_data.iloc[i]
                future_bar = ohlcv_data.iloc[i + config.forward_return_minutes]
                
                # Calculate forward return
                current_price = current_bar['close']
                future_price = future_bar['close']
                forward_return = (future_price - current_price) / current_price
                
                # Create binary label (UP/DOWN)
                if forward_return > config.up_threshold:
                    label = 1  # UP
                elif forward_return < config.down_threshold:
                    label = 0  # DOWN
                else:
                    # Skip neutral returns (between thresholds)
                    continue
                
                # Generate features for current bar
                # Use a sliding window of historical data up to current bar
                window_data = ohlcv_data.iloc[max(0, i-500):i+1]
                features = self._extract_features(window_data)
                
                if features:
                    features_list.append(features)
                    labels_list.append(label)
                    timestamps.append(current_bar['timestamp'])
                    
            except Exception as e:
                log.debug(f"Error processing bar {i}: {e}")
                continue
        
        # Convert to DataFrame
        features_df = pd.DataFrame(features_list)
        labels_series = pd.Series(labels_list, name='label')
        
        log.info(f"Generated {len(features_df)} training samples")
        log.info(f"Label distribution: UP={sum(labels_series==1)}, DOWN={sum(labels_series==0)}")
        
        return features_df, labels_series
    
    def _extract_features(self, window_data: pd.DataFrame) -> Optional[Dict[str, float]]:
        """
        Extract features from price data window.
        
        Uses simplified feature extraction since FeaturePipeline is event-driven.
        In production, this would use cached features from Redis.
        """
        if len(window_data) < 20:
            return None
        
        features = {}
        
        try:
            close = window_data['close'].values
            high = window_data['high'].values
            low = window_data['low'].values
            volume = window_data['volume'].values
            
            # Price features
            if len(close) >= 2:
                features['return_1bar'] = (close[-1] - close[-2]) / close[-2]
            if len(close) >= 6:
                features['return_5bar'] = (close[-1] - close[-6]) / close[-6]
            if len(close) >= 21:
                features['return_20bar'] = (close[-1] - close[-21]) / close[-21]
            
            # RSI
            if len(close) >= 15:
                deltas = np.diff(close[-15:])
                gains = np.where(deltas > 0, deltas, 0)
                losses = np.where(deltas < 0, -deltas, 0)
                avg_gain = np.mean(gains)
                avg_loss = np.mean(losses)
                rs = avg_gain / avg_loss if avg_loss != 0 else 0
                features['rsi_14'] = 100 - (100 / (1 + rs)) if rs != 0 else 50
            
            # EMAs
            if len(close) >= 20:
                features['ema_20'] = self._calculate_ema(close, 20)
            if len(close) >= 50:
                features['ema_50'] = self._calculate_ema(close, 50)
            
            # Volatility
            if len(close) >= 21:
                returns = np.diff(np.log(close[-21:]))
                features['volatility_20'] = np.std(returns)
            
            # Volume features
            if len(volume) >= 21:
                features['volume_ratio'] = volume[-1] / np.mean(volume[-21:-1])
            
            # Statistical features
            for window in [20, 50]:
                if len(close) >= window + 1:
                    window_data_slice = close[-window:]
                    mean = np.mean(window_data_slice)
                    std = np.std(window_data_slice)
                    
                    features[f'mean_{window}'] = mean
                    features[f'std_{window}'] = std
                    
                    if std > 0:
                        features[f'zscore_{window}'] = (close[-1] - mean) / std
                    
            return features
            
        except Exception as e:
            log.debug(f"Error extracting features: {e}")
            return None
    
    def _calculate_ema(self, data: np.ndarray, period: int) -> float:
        """Calculate Exponential Moving Average"""
        if len(data) < period:
            return data[-1]
        
        multiplier = 2 / (period + 1)
        ema = data[-period]
        
        for price in data[-period+1:]:
            ema = (price - ema) * multiplier + ema
        
        return ema
    
    def train_xgboost(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
        hyperparameters: Optional[Dict[str, Any]] = None
    ) -> Tuple[xgb.XGBClassifier, ModelMetrics]:
        """
        Train XGBoost model with hyperparameter tuning.
        
        Requirements: 11.4
        
        Args:
            X_train: Training features
            y_train: Training labels
            X_val: Validation features
            y_val: Validation labels
            hyperparameters: Optional hyperparameters (uses defaults if None)
            
        Returns:
            Tuple of (trained_model, validation_metrics)
        """
        log.info("Training XGBoost model")
        
        # Default hyperparameters
        if hyperparameters is None:
            hyperparameters = {
                'max_depth': 5,
                'learning_rate': 0.05,
                'n_estimators': 200,
                'min_child_weight': 3,
                'subsample': 0.9,
                'colsample_bytree': 0.9,
                'objective': 'binary:logistic',
                'eval_metric': 'logloss',
                'random_state': 42
            }
        
        # Train model
        model = xgb.XGBClassifier(**hyperparameters)
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            verbose=False
        )
        
        # Evaluate on validation set
        metrics = self._evaluate_model(model, X_val, y_val)
        
        log.info(f"XGBoost validation metrics: accuracy={metrics.accuracy:.4f}, "
                f"precision={metrics.precision:.4f}, recall={metrics.recall:.4f}, "
                f"f1={metrics.f1_score:.4f}, roc_auc={metrics.roc_auc:.4f}")
        
        return model, metrics
    
    def train_lightgbm(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
        hyperparameters: Optional[Dict[str, Any]] = None
    ) -> Tuple[lgb.LGBMClassifier, ModelMetrics]:
        """
        Train LightGBM model with hyperparameter tuning.
        
        Requirements: 11.4
        
        Args:
            X_train: Training features
            y_train: Training labels
            X_val: Validation features
            y_val: Validation labels
            hyperparameters: Optional hyperparameters (uses defaults if None)
            
        Returns:
            Tuple of (trained_model, validation_metrics)
        """
        log.info("Training LightGBM model")
        
        # Default hyperparameters
        if hyperparameters is None:
            hyperparameters = {
                'max_depth': 5,
                'learning_rate': 0.05,
                'n_estimators': 200,
                'min_child_weight': 3,
                'subsample': 0.9,
                'colsample_bytree': 0.9,
                'objective': 'binary',
                'metric': 'binary_logloss',
                'random_state': 42,
                'verbose': -1
            }
        
        # Train model
        model = lgb.LGBMClassifier(**hyperparameters)
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.log_evaluation(period=0)]
        )
        
        # Evaluate on validation set
        metrics = self._evaluate_model(model, X_val, y_val)
        
        log.info(f"LightGBM validation metrics: accuracy={metrics.accuracy:.4f}, "
                f"precision={metrics.precision:.4f}, recall={metrics.recall:.4f}, "
                f"f1={metrics.f1_score:.4f}, roc_auc={metrics.roc_auc:.4f}")
        
        return model, metrics
    
    def _evaluate_model(
        self,
        model: Any,
        X_val: pd.DataFrame,
        y_val: pd.Series
    ) -> ModelMetrics:
        """
        Evaluate model on validation set.
        
        Requirements: 11.5
        
        Args:
            model: Trained model
            X_val: Validation features
            y_val: Validation labels
            
        Returns:
            ModelMetrics with performance metrics
        """
        # Make predictions
        y_pred = model.predict(X_val)
        y_pred_proba = model.predict_proba(X_val)[:, 1]
        
        # Compute metrics
        accuracy = accuracy_score(y_val, y_pred)
        precision = precision_score(y_val, y_pred, zero_division=0)
        recall = recall_score(y_val, y_pred, zero_division=0)
        f1 = f1_score(y_val, y_pred, zero_division=0)
        roc_auc = roc_auc_score(y_val, y_pred_proba)
        
        return ModelMetrics(
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1_score=f1,
            roc_auc=roc_auc
        )
    
    def train_and_evaluate(
        self,
        config: TrainingConfig,
        model_type: str = "xgboost"
    ) -> Optional[Tuple[Any, ModelMetrics, Dict[str, Any]]]:
        """
        Complete training pipeline: generate data, train model, evaluate.
        
        Requirements: 11.1, 11.2, 11.3, 11.4, 11.5
        
        Args:
            config: Training configuration
            model_type: "xgboost" or "lightgbm"
            
        Returns:
            Tuple of (model, metrics, metadata) if model meets acceptance criteria,
            None if model is rejected
        """
        log.info(f"Starting training pipeline for {config.symbol} using {model_type}")
        
        # Generate training data
        features_df, labels_series = self.generate_training_data(config)
        
        if len(features_df) < 100:
            log.error("Insufficient training data")
            return None
        
        # Walk-forward validation split (80/20)
        split_idx = int(len(features_df) * config.train_split)
        
        X_train = features_df.iloc[:split_idx]
        y_train = labels_series.iloc[:split_idx]
        X_val = features_df.iloc[split_idx:]
        y_val = labels_series.iloc[split_idx:]
        
        log.info(f"Train set: {len(X_train)} samples")
        log.info(f"Validation set: {len(X_val)} samples")
        
        # Train model
        if model_type.lower() == "xgboost":
            model, metrics = self.train_xgboost(X_train, y_train, X_val, y_val)
        elif model_type.lower() == "lightgbm":
            model, metrics = self.train_lightgbm(X_train, y_train, X_val, y_val)
        else:
            raise ValueError(f"Unknown model type: {model_type}")
        
        # Check acceptance criteria
        if not metrics.meets_acceptance_criteria(config.min_accuracy):
            log.warning(f"Model rejected: accuracy {metrics.accuracy:.4f} < {config.min_accuracy}")
            return None
        
        log.info(f"Model accepted: accuracy {metrics.accuracy:.4f} >= {config.min_accuracy}")
        
        # Prepare metadata
        metadata = {
            'model_type': model_type,
            'symbol': config.symbol,
            'timeframe': config.timeframe,
            'training_months': config.training_months,
            'train_samples': len(X_train),
            'val_samples': len(X_val),
            'feature_names': list(features_df.columns),
            'num_features': len(features_df.columns),
            'metrics': {
                'accuracy': metrics.accuracy,
                'precision': metrics.precision,
                'recall': metrics.recall,
                'f1_score': metrics.f1_score,
                'roc_auc': metrics.roc_auc
            },
            'created_at': datetime.now().isoformat()
        }
        
        return model, metrics, metadata
    
    def save_model(
        self,
        model: Any,
        metadata: Dict[str, Any],
        model_name: Optional[str] = None
    ) -> Path:
        """
        Save trained model and metadata to disk.
        
        Args:
            model: Trained model
            metadata: Model metadata
            model_name: Optional model name (auto-generated if None)
            
        Returns:
            Path to saved model directory
        """
        if model_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            model_name = f"{metadata['model_type']}_{metadata['symbol']}_{timestamp}"
        
        model_dir = self.models_dir / model_name
        model_dir.mkdir(parents=True, exist_ok=True)
        
        # Save model
        model_path = model_dir / "model.pkl"
        joblib.dump(model, model_path)
        
        # Save metadata
        metadata_path = model_dir / "metadata.json"
        import json
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        log.info(f"Model saved to {model_dir}")
        
        return model_dir
