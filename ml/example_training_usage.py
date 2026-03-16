"""
Example usage of Supervised Learning Training Pipeline

This script demonstrates how to train and evaluate ML models for price direction prediction.
"""

import asyncio
from datetime import datetime
from pathlib import Path

from ml.supervised_training import SupervisedTrainingPipeline, TrainingConfig
from data.historical_data_warehouse import HistoricalDataWarehouse
from data.feature_pipeline import FeaturePipeline
from data.event_bus import EventBus
from core.logger import get_agent_logger

log = get_agent_logger("TRAINING_EXAMPLE")


async def main():
    """Example training workflow"""
    
    log.info("=" * 60)
    log.info("ML Model Training Pipeline Example")
    log.info("=" * 60)
    
    # Initialize components
    log.info("\n1. Initializing components...")
    
    warehouse = HistoricalDataWarehouse(
        db_path="data/market_data.duckdb",
        parquet_root="data/parquet"
    )
    
    event_bus = EventBus(max_queue_size=1000)
    
    # Mock Redis for example (in production, use real Redis)
    class MockRedis:
        async def get(self, key):
            return None
        async def setex(self, key, ttl, value):
            pass
    
    feature_pipeline = FeaturePipeline(
        event_bus=event_bus,
        redis_client=MockRedis(),
        symbols=["XAUUSD", "EURUSD"],
        timeframes=["M15"]
    )
    
    training_pipeline = SupervisedTrainingPipeline(
        warehouse=warehouse,
        feature_pipeline=feature_pipeline,
        models_dir="models/supervised"
    )
    
    log.info("✓ Components initialized")
    
    # Configure training
    log.info("\n2. Configuring training...")
    
    config = TrainingConfig(
        symbol="XAUUSD",
        timeframe="M15",
        training_months=6,
        forward_return_minutes=15,
        up_threshold=0.001,  # 0.1% threshold for UP
        down_threshold=-0.001,  # -0.1% threshold for DOWN
        train_split=0.8,
        min_accuracy=0.52
    )
    
    log.info(f"Symbol: {config.symbol}")
    log.info(f"Timeframe: {config.timeframe}")
    log.info(f"Training period: {config.training_months} months")
    log.info(f"Forward return window: {config.forward_return_minutes} minutes")
    log.info(f"UP threshold: {config.up_threshold * 100}%")
    log.info(f"DOWN threshold: {config.down_threshold * 100}%")
    log.info(f"Train/Val split: {config.train_split}/{1-config.train_split}")
    log.info(f"Minimum accuracy: {config.min_accuracy * 100}%")
    
    # Train XGBoost model
    log.info("\n3. Training XGBoost model...")
    log.info("-" * 60)
    
    xgb_result = training_pipeline.train_and_evaluate(
        config=config,
        model_type="xgboost"
    )
    
    if xgb_result is None:
        log.warning("✗ XGBoost model rejected (accuracy < 52%)")
    else:
        xgb_model, xgb_metrics, xgb_metadata = xgb_result
        
        log.info("✓ XGBoost model accepted!")
        log.info(f"  Accuracy:  {xgb_metrics.accuracy:.4f}")
        log.info(f"  Precision: {xgb_metrics.precision:.4f}")
        log.info(f"  Recall:    {xgb_metrics.recall:.4f}")
        log.info(f"  F1 Score:  {xgb_metrics.f1_score:.4f}")
        log.info(f"  ROC AUC:   {xgb_metrics.roc_auc:.4f}")
        
        # Save model
        model_dir = training_pipeline.save_model(
            xgb_model,
            xgb_metadata,
            model_name=f"xgboost_{config.symbol}_{datetime.now().strftime('%Y%m%d')}"
        )
        log.info(f"  Model saved to: {model_dir}")
    
    # Train LightGBM model
    log.info("\n4. Training LightGBM model...")
    log.info("-" * 60)
    
    lgb_result = training_pipeline.train_and_evaluate(
        config=config,
        model_type="lightgbm"
    )
    
    if lgb_result is None:
        log.warning("✗ LightGBM model rejected (accuracy < 52%)")
    else:
        lgb_model, lgb_metrics, lgb_metadata = lgb_result
        
        log.info("✓ LightGBM model accepted!")
        log.info(f"  Accuracy:  {lgb_metrics.accuracy:.4f}")
        log.info(f"  Precision: {lgb_metrics.precision:.4f}")
        log.info(f"  Recall:    {lgb_metrics.recall:.4f}")
        log.info(f"  F1 Score:  {lgb_metrics.f1_score:.4f}")
        log.info(f"  ROC AUC:   {lgb_metrics.roc_auc:.4f}")
        
        # Save model
        model_dir = training_pipeline.save_model(
            lgb_model,
            lgb_metadata,
            model_name=f"lightgbm_{config.symbol}_{datetime.now().strftime('%Y%m%d')}"
        )
        log.info(f"  Model saved to: {model_dir}")
    
    # Compare models
    if xgb_result and lgb_result:
        log.info("\n5. Model Comparison")
        log.info("-" * 60)
        
        xgb_model, xgb_metrics, xgb_metadata = xgb_result
        lgb_model, lgb_metrics, lgb_metadata = lgb_result
        
        log.info(f"{'Metric':<15} {'XGBoost':<12} {'LightGBM':<12} {'Winner':<10}")
        log.info("-" * 60)
        
        metrics_to_compare = [
            ('Accuracy', xgb_metrics.accuracy, lgb_metrics.accuracy),
            ('Precision', xgb_metrics.precision, lgb_metrics.precision),
            ('Recall', xgb_metrics.recall, lgb_metrics.recall),
            ('F1 Score', xgb_metrics.f1_score, lgb_metrics.f1_score),
            ('ROC AUC', xgb_metrics.roc_auc, lgb_metrics.roc_auc),
        ]
        
        for metric_name, xgb_val, lgb_val in metrics_to_compare:
            winner = "XGBoost" if xgb_val > lgb_val else "LightGBM" if lgb_val > xgb_val else "Tie"
            log.info(f"{metric_name:<15} {xgb_val:<12.4f} {lgb_val:<12.4f} {winner:<10}")
    
    log.info("\n" + "=" * 60)
    log.info("Training pipeline completed!")
    log.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
