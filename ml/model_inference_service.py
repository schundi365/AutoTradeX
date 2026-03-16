"""
Model Inference Service

This module implements a low-latency model inference service that loads models
from the registry, caches them in memory, and serves predictions with <20ms latency.
Supports hot-reloading without downtime and integrates with Redis for feature serving.

Requirements: 11.1, 11.2
"""

import asyncio
import pickle
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from collections import deque

import numpy as np
import redis.asyncio as redis

from ml.model_registry import ModelRegistry, ModelMetadata, ModelType
from core.logger import get_agent_logger

log = get_agent_logger("MODEL_INFERENCE")


@dataclass
class Prediction:
    """
    Model prediction output.
    
    Requirements: 11.1
    """
    symbol: str
    timestamp: datetime
    model_id: str
    prediction: float  # Probability of UP (0.0 to 1.0) for supervised models
    confidence: float  # Model confidence (0.0 to 1.0)
    features_used: List[str]
    inference_time_ms: float


@dataclass
class InferenceMetrics:
    """Metrics for monitoring inference performance"""
    total_predictions: int = 0
    total_inference_time_ms: float = 0.0
    avg_inference_time_ms: float = 0.0
    max_inference_time_ms: float = 0.0
    min_inference_time_ms: float = float('inf')
    predictions_per_second: float = 0.0
    last_prediction_time: Optional[datetime] = None


class ModelInferenceService:
    """
    Low-latency model inference service.
    
    Features:
    - Loads models from registry on startup
    - Caches models in memory for fast inference (<20ms)
    - Supports hot-reloading without downtime
    - Batch predictions for efficiency
    - Tracks prediction latency and throughput
    - Integrates with Redis for feature serving
    
    Requirements: 11.1, 11.2
    """
    
    def __init__(
        self,
        model_registry: ModelRegistry,
        redis_url: str = "redis://localhost:6379",
        model_type: str = ModelType.XGBOOST.value,
        enable_redis: bool = True
    ):
        """
        Initialize model inference service.
        
        Args:
            model_registry: ModelRegistry instance
            redis_url: Redis connection URL for feature store
            model_type: Type of model to load (XGBOOST, LIGHTGBM, PPO)
            enable_redis: Whether to use Redis for predictions storage
        """
        self.model_registry = model_registry
        self.redis_url = redis_url
        self.model_type = model_type
        self.enable_redis = enable_redis
        
        # Model cache
        self.current_model: Optional[Any] = None
        self.current_metadata: Optional[ModelMetadata] = None
        self._model_lock = threading.Lock()
        
        # Redis connection
        self.redis_client: Optional[redis.Redis] = None
        
        # Metrics tracking
        self.metrics = InferenceMetrics()
        self._metrics_lock = threading.Lock()
        
        # Recent predictions for monitoring
        self._recent_predictions: deque = deque(maxlen=1000)
        
        # Batch prediction queue
        self._batch_queue: asyncio.Queue = asyncio.Queue()
        self._batch_size = 32
        self._batch_timeout_ms = 10  # 10ms max wait for batch
        
        log.info("Model Inference Service initialized")
        log.info(f"Model type: {model_type}")
        log.info(f"Redis enabled: {enable_redis}")
    
    async def start(self):
        """
        Start the inference service.
        
        - Loads current production model from registry
        - Connects to Redis
        - Starts batch processing task
        
        Requirements: 11.1
        """
        log.info("Starting Model Inference Service...")
        
        # Connect to Redis if enabled
        if self.enable_redis:
            try:
                self.redis_client = await redis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=False
                )
                await self.redis_client.ping()
                log.info("Connected to Redis feature store")
            except Exception as e:
                log.warning(f"Failed to connect to Redis: {e}")
                log.warning("Continuing without Redis integration")
                self.redis_client = None
        
        # Load current production model
        await self._load_production_model()
        
        log.info("Model Inference Service started successfully")
    
    async def stop(self):
        """Stop the inference service and cleanup resources"""
        log.info("Stopping Model Inference Service...")
        
        # Close Redis connection
        if self.redis_client:
            await self.redis_client.close()
            log.info("Redis connection closed")
        
        log.info("Model Inference Service stopped")
    
    async def _load_production_model(self):
        """
        Load current production model from registry.
        
        Requirements: 11.1
        """
        log.info(f"Loading production model of type: {self.model_type}")
        
        # Get current production model metadata
        metadata = self.model_registry.get_current_production_model(self.model_type)
        
        if not metadata:
            log.warning(f"No production model found for type: {self.model_type}")
            log.warning("Service will operate without ML predictions")
            return
        
        # Load model file
        try:
            _, model_bytes = self.model_registry.get_model(metadata.model_id)
            
            # Deserialize model
            model = pickle.loads(model_bytes)
            
            # Update cache
            with self._model_lock:
                self.current_model = model
                self.current_metadata = metadata
            
            log.info(f"Loaded model: {metadata.model_name} (ID: {metadata.model_id})")
            log.info(f"Model version: {metadata.version}")
            log.info(f"Training date range: {metadata.training_start_date} to {metadata.training_end_date}")
            log.info(f"Validation accuracy: {metadata.validation_metrics.get('accuracy', 'N/A')}")
            log.info(f"Number of features: {metadata.num_features}")
            
        except Exception as e:
            log.error(f"Failed to load model: {e}")
            raise
    
    async def reload_model(self, model_id: str):
        """
        Hot-reload a new model without downtime.
        
        The new model is loaded in the background and atomically swapped
        with the current model, ensuring no prediction requests are dropped.
        
        Requirements: 11.1
        
        Args:
            model_id: Model ID to load from registry
        """
        log.info(f"Hot-reloading model: {model_id}")
        
        try:
            # Load new model metadata and file
            metadata, model_bytes = self.model_registry.get_model(model_id)
            
            # Deserialize model
            new_model = pickle.loads(model_bytes)
            
            # Atomic swap
            with self._model_lock:
                old_model_id = self.current_metadata.model_id if self.current_metadata else None
                self.current_model = new_model
                self.current_metadata = metadata
            
            log.info(f"Model reloaded successfully: {metadata.model_name}")
            log.info(f"Old model ID: {old_model_id}")
            log.info(f"New model ID: {model_id}")
            
        except Exception as e:
            log.error(f"Failed to reload model: {e}")
            raise
    
    async def predict(
        self,
        symbol: str,
        features: Optional[Dict[str, float]] = None,
        feature_vector: Optional[np.ndarray] = None
    ) -> Optional[Prediction]:
        """
        Get prediction from deployed model.
        
        Features can be provided either as:
        - Dictionary of feature name -> value
        - Pre-computed numpy array
        - Neither (will fetch from Redis)
        
        Requirements: 11.1, 11.2
        
        Args:
            symbol: Trading symbol
            features: Optional feature dictionary
            feature_vector: Optional pre-computed feature vector
            
        Returns:
            Prediction object or None if model not available
        """
        start_time = time.perf_counter()
        
        # Check if model is loaded
        if not self.current_model or not self.current_metadata:
            log.warning("No model loaded, cannot make prediction")
            return None
        
        try:
            # Get feature vector
            if feature_vector is None:
                if features is None:
                    # Fetch from Redis
                    features = await self._fetch_features_from_redis(symbol)
                    if not features:
                        log.warning(f"No features available for {symbol}")
                        return None
                
                # Convert features dict to numpy array
                feature_vector = self._features_dict_to_array(features)
            
            # Ensure feature vector has correct shape
            if feature_vector.ndim == 1:
                feature_vector = feature_vector.reshape(1, -1)
            
            # Make prediction (thread-safe)
            with self._model_lock:
                model = self.current_model
                metadata = self.current_metadata
                
                # Get prediction
                if hasattr(model, 'predict_proba'):
                    # Classification model - get probability of UP class
                    proba = model.predict_proba(feature_vector)[0]
                    prediction_value = float(proba[1]) if len(proba) > 1 else float(proba[0])
                    confidence = float(max(proba))
                else:
                    # Regression model or other
                    prediction_value = float(model.predict(feature_vector)[0])
                    confidence = 0.5  # Default confidence for regression
            
            # Calculate inference time
            inference_time_ms = (time.perf_counter() - start_time) * 1000
            
            # Create prediction object
            prediction = Prediction(
                symbol=symbol,
                timestamp=datetime.now(),
                model_id=metadata.model_id,
                prediction=prediction_value,
                confidence=confidence,
                features_used=metadata.feature_names,
                inference_time_ms=inference_time_ms
            )
            
            # Update metrics
            self._update_metrics(inference_time_ms)
            
            # Store recent prediction
            self._recent_predictions.append(prediction)
            
            # Store prediction in Redis if enabled
            if self.redis_client:
                await self._store_prediction_in_redis(prediction)
            
            # Log slow predictions
            if inference_time_ms > 20:
                log.warning(
                    f"Slow prediction for {symbol}: {inference_time_ms:.2f}ms "
                    f"(target: <20ms)"
                )
            
            return prediction
            
        except Exception as e:
            log.error(f"Prediction failed for {symbol}: {e}")
            return None
    
    async def predict_batch(
        self,
        symbols: List[str],
        features_dict: Optional[Dict[str, Dict[str, float]]] = None
    ) -> Dict[str, Optional[Prediction]]:
        """
        Make predictions for multiple symbols efficiently.
        
        Batches predictions to improve throughput.
        
        Requirements: 11.1
        
        Args:
            symbols: List of trading symbols
            features_dict: Optional dict mapping symbol -> features
            
        Returns:
            Dictionary mapping symbol -> Prediction (or None if failed)
        """
        if not self.current_model or not self.current_metadata:
            log.warning("No model loaded, cannot make batch predictions")
            return {symbol: None for symbol in symbols}
        
        start_time = time.perf_counter()
        results = {}
        
        try:
            # Collect feature vectors for all symbols
            feature_vectors = []
            valid_symbols = []
            
            for symbol in symbols:
                if features_dict and symbol in features_dict:
                    features = features_dict[symbol]
                else:
                    features = await self._fetch_features_from_redis(symbol)
                
                if features:
                    feature_vector = self._features_dict_to_array(features)
                    feature_vectors.append(feature_vector)
                    valid_symbols.append(symbol)
                else:
                    results[symbol] = None
            
            if not feature_vectors:
                return results
            
            # Stack into batch
            batch_features = np.vstack(feature_vectors)
            
            # Make batch prediction
            with self._model_lock:
                model = self.current_model
                metadata = self.current_metadata
                
                if hasattr(model, 'predict_proba'):
                    probas = model.predict_proba(batch_features)
                    predictions = probas[:, 1] if probas.shape[1] > 1 else probas[:, 0]
                    confidences = np.max(probas, axis=1)
                else:
                    predictions = model.predict(batch_features)
                    confidences = np.full(len(predictions), 0.5)
            
            # Calculate total inference time
            total_inference_time_ms = (time.perf_counter() - start_time) * 1000
            avg_inference_time_ms = total_inference_time_ms / len(valid_symbols)
            
            # Create prediction objects
            for i, symbol in enumerate(valid_symbols):
                prediction = Prediction(
                    symbol=symbol,
                    timestamp=datetime.now(),
                    model_id=metadata.model_id,
                    prediction=float(predictions[i]),
                    confidence=float(confidences[i]),
                    features_used=metadata.feature_names,
                    inference_time_ms=avg_inference_time_ms
                )
                
                results[symbol] = prediction
                self._recent_predictions.append(prediction)
                
                # Store in Redis if enabled
                if self.redis_client:
                    await self._store_prediction_in_redis(prediction)
            
            # Update metrics
            for _ in valid_symbols:
                self._update_metrics(avg_inference_time_ms)
            
            log.info(
                f"Batch prediction completed: {len(valid_symbols)} symbols "
                f"in {total_inference_time_ms:.2f}ms "
                f"(avg: {avg_inference_time_ms:.2f}ms per symbol)"
            )
            
        except Exception as e:
            log.error(f"Batch prediction failed: {e}")
            for symbol in symbols:
                if symbol not in results:
                    results[symbol] = None
        
        return results
    
    def _features_dict_to_array(self, features: Dict[str, float]) -> np.ndarray:
        """
        Convert features dictionary to numpy array in correct order.
        
        Requirements: 11.2
        """
        if not self.current_metadata:
            raise ValueError("No model metadata available")
        
        # Extract features in the order expected by the model
        feature_values = []
        for feature_name in self.current_metadata.feature_names:
            value = features.get(feature_name, 0.0)  # Default to 0.0 if missing
            feature_values.append(value)
        
        return np.array(feature_values, dtype=np.float32)
    
    async def _fetch_features_from_redis(self, symbol: str) -> Optional[Dict[str, float]]:
        """
        Fetch features from Redis feature store.
        
        Requirements: 11.1
        """
        if not self.redis_client:
            return None
        
        try:
            # Key format: features:{symbol}:M15 (default timeframe)
            key = f"features:{symbol}:M15"
            
            # Get features from Redis
            data = await self.redis_client.get(key)
            
            if not data:
                return None
            
            # Deserialize features
            import json
            features = json.loads(data)
            
            return features.get('features', {})
            
        except Exception as e:
            log.error(f"Failed to fetch features from Redis for {symbol}: {e}")
            return None
    
    async def _store_prediction_in_redis(self, prediction: Prediction):
        """
        Store prediction in Redis for FastDecisionEngine.
        
        Requirements: 11.1
        """
        if not self.redis_client:
            return
        
        try:
            # Key format: prediction:{symbol}
            key = f"prediction:{prediction.symbol}"
            
            # Serialize prediction
            import json
            data = json.dumps({
                'symbol': prediction.symbol,
                'timestamp': prediction.timestamp.isoformat(),
                'model_id': prediction.model_id,
                'prediction': prediction.prediction,
                'confidence': prediction.confidence,
                'inference_time_ms': prediction.inference_time_ms
            })
            
            # Store with 1-hour TTL
            await self.redis_client.setex(key, 3600, data)
            
        except Exception as e:
            log.error(f"Failed to store prediction in Redis: {e}")
    
    def _update_metrics(self, inference_time_ms: float):
        """Update inference metrics"""
        with self._metrics_lock:
            self.metrics.total_predictions += 1
            self.metrics.total_inference_time_ms += inference_time_ms
            self.metrics.avg_inference_time_ms = (
                self.metrics.total_inference_time_ms / self.metrics.total_predictions
            )
            self.metrics.max_inference_time_ms = max(
                self.metrics.max_inference_time_ms,
                inference_time_ms
            )
            self.metrics.min_inference_time_ms = min(
                self.metrics.min_inference_time_ms,
                inference_time_ms
            )
            self.metrics.last_prediction_time = datetime.now()
            
            # Calculate predictions per second (over last 60 seconds)
            recent_count = sum(
                1 for p in self._recent_predictions
                if (datetime.now() - p.timestamp).total_seconds() < 60
            )
            self.metrics.predictions_per_second = recent_count / 60.0
    
    def get_model_info(self) -> Optional[ModelMetadata]:
        """
        Get metadata for currently deployed model.
        
        Requirements: 11.1
        
        Returns:
            ModelMetadata or None if no model loaded
        """
        with self._model_lock:
            return self.current_metadata
    
    def get_metrics(self) -> InferenceMetrics:
        """
        Get inference performance metrics.
        
        Returns:
            InferenceMetrics object with current statistics
        """
        with self._metrics_lock:
            return InferenceMetrics(
                total_predictions=self.metrics.total_predictions,
                total_inference_time_ms=self.metrics.total_inference_time_ms,
                avg_inference_time_ms=self.metrics.avg_inference_time_ms,
                max_inference_time_ms=self.metrics.max_inference_time_ms,
                min_inference_time_ms=self.metrics.min_inference_time_ms,
                predictions_per_second=self.metrics.predictions_per_second,
                last_prediction_time=self.metrics.last_prediction_time
            )
    
    def get_recent_predictions(self, limit: int = 100) -> List[Prediction]:
        """
        Get recent predictions for monitoring.
        
        Args:
            limit: Maximum number of predictions to return
            
        Returns:
            List of recent Prediction objects
        """
        return list(self._recent_predictions)[-limit:]
    
    def is_model_loaded(self) -> bool:
        """Check if a model is currently loaded"""
        with self._model_lock:
            return self.current_model is not None
