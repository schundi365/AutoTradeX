"""
Training History Tracker

Tracks all model training attempts (successful and failed) for dashboard display.
Stores training history in a simple JSON file for easy access.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
from core.logger import get_agent_logger

log = get_agent_logger("TRAINING_HISTORY")


@dataclass
class TrainingRecord:
    """Record of a single training attempt"""
    timestamp: str
    model_type: str
    symbol: str
    status: str  # "success", "rejected", "failed"
    accuracy: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1_score: Optional[float] = None
    roc_auc: Optional[float] = None
    train_samples: Optional[int] = None
    val_samples: Optional[int] = None
    error_message: Optional[str] = None
    rejection_reason: Optional[str] = None
    model_path: Optional[str] = None
    training_duration_seconds: Optional[float] = None


class TrainingHistoryTracker:
    """
    Tracks all model training attempts for dashboard display.
    
    Features:
    - Logs successful and failed training attempts
    - Stores in JSON file for persistence
    - Provides query interface for dashboard
    - Automatic cleanup of old records (keeps last 100)
    """
    
    def __init__(self, history_file: str = "data/training_history.json"):
        self.history_file = Path(history_file)
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize file if it doesn't exist
        if not self.history_file.exists():
            self._save_history([])
            log.info(f"Created training history file: {self.history_file}")
        
        log.info(f"Training history tracker initialized: {self.history_file}")
    
    def log_training_attempt(
        self,
        model_type: str,
        symbol: str,
        status: str,
        accuracy: Optional[float] = None,
        precision: Optional[float] = None,
        recall: Optional[float] = None,
        f1_score: Optional[float] = None,
        roc_auc: Optional[float] = None,
        train_samples: Optional[int] = None,
        val_samples: Optional[int] = None,
        error_message: Optional[str] = None,
        rejection_reason: Optional[str] = None,
        model_path: Optional[str] = None,
        training_duration_seconds: Optional[float] = None
    ) -> None:
        """
        Log a training attempt (successful or failed).
        
        Args:
            model_type: Type of model (xgboost, lightgbm, ppo, etc.)
            symbol: Trading symbol
            status: "success", "rejected", or "failed"
            accuracy: Model accuracy (if available)
            precision: Model precision (if available)
            recall: Model recall (if available)
            f1_score: Model F1 score (if available)
            roc_auc: Model ROC AUC (if available)
            train_samples: Number of training samples
            val_samples: Number of validation samples
            error_message: Error message (if failed)
            rejection_reason: Reason for rejection (if rejected)
            model_path: Path to saved model (if successful)
            training_duration_seconds: Training duration in seconds
        """
        record = TrainingRecord(
            timestamp=datetime.now().isoformat(),
            model_type=model_type,
            symbol=symbol,
            status=status,
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1_score=f1_score,
            roc_auc=roc_auc,
            train_samples=train_samples,
            val_samples=val_samples,
            error_message=error_message,
            rejection_reason=rejection_reason,
            model_path=model_path,
            training_duration_seconds=training_duration_seconds
        )
        
        # Load existing history
        history = self._load_history()
        
        # Add new record at the beginning (most recent first)
        history.insert(0, asdict(record))
        
        # Keep only last 100 records
        history = history[:100]
        
        # Save updated history
        self._save_history(history)
        
        log.info(f"Logged training attempt: {model_type} {symbol} - {status}")
    
    def get_history(
        self,
        limit: Optional[int] = None,
        model_type: Optional[str] = None,
        symbol: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get training history with optional filters.
        
        Args:
            limit: Maximum number of records to return
            model_type: Filter by model type
            symbol: Filter by symbol
            status: Filter by status (success, rejected, failed)
            
        Returns:
            List of training records (most recent first)
        """
        history = self._load_history()
        
        # Apply filters
        if model_type:
            history = [r for r in history if r.get('model_type', '').lower() == model_type.lower()]
        
        if symbol:
            history = [r for r in history if r.get('symbol', '').upper() == symbol.upper()]
        
        if status:
            history = [r for r in history if r.get('status', '').lower() == status.lower()]
        
        # Apply limit
        if limit:
            history = history[:limit]
        
        return history
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about training history.
        
        Returns:
            Dictionary with statistics
        """
        history = self._load_history()
        
        if not history:
            return {
                "total_attempts": 0,
                "successful": 0,
                "rejected": 0,
                "failed": 0,
                "success_rate": 0.0,
                "avg_accuracy": None,
                "most_trained_symbol": None,
                "most_used_model_type": None
            }
        
        # Count by status
        successful = sum(1 for r in history if r.get('status') == 'success')
        rejected = sum(1 for r in history if r.get('status') == 'rejected')
        failed = sum(1 for r in history if r.get('status') == 'failed')
        
        # Calculate average accuracy (only for successful models)
        accuracies = [r.get('accuracy') for r in history if r.get('status') == 'success' and r.get('accuracy') is not None]
        avg_accuracy = sum(accuracies) / len(accuracies) if accuracies else None
        
        # Most trained symbol
        symbols = [r.get('symbol') for r in history if r.get('symbol')]
        most_trained_symbol = max(set(symbols), key=symbols.count) if symbols else None
        
        # Most used model type
        model_types = [r.get('model_type') for r in history if r.get('model_type')]
        most_used_model_type = max(set(model_types), key=model_types.count) if model_types else None
        
        return {
            "total_attempts": len(history),
            "successful": successful,
            "rejected": rejected,
            "failed": failed,
            "success_rate": successful / len(history) if history else 0.0,
            "avg_accuracy": avg_accuracy,
            "most_trained_symbol": most_trained_symbol,
            "most_used_model_type": most_used_model_type
        }
    
    def clear_history(self) -> None:
        """Clear all training history."""
        self._save_history([])
        log.info("Training history cleared")
    
    def _load_history(self) -> List[Dict[str, Any]]:
        """Load history from JSON file."""
        try:
            with open(self.history_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Failed to load training history: {e}")
            return []
    
    def _save_history(self, history: List[Dict[str, Any]]) -> None:
        """Save history to JSON file."""
        try:
            with open(self.history_file, 'w') as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            log.error(f"Failed to save training history: {e}")
