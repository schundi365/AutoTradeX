import duckdb
import pandas as pd
import pandas_ta as ta
import numpy as np
import os
import json
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score
from skl2onnx import to_onnx
from pathlib import Path
from core.logger import get_agent_logger

log = get_agent_logger("TRAINER")

class AIModelTrainer:
    """
    Automated trainer that pulls data from DuckDB, trains a model,
    and exports it to ONNX format.
    """
    def __init__(self, db_path: str = "data/market_data.duckdb", 
                 model_path: str = "models/trend_predictor.onnx",
                 metrics_path: str = "data/model_metrics.json"):
        self.db_path = Path(db_path)
        self.model_path = Path(model_path)
        self.metrics_path = Path(metrics_path)
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        self.metrics_path.parent.mkdir(parents=True, exist_ok=True)

    def train_daily_model(self):
        """Runs the complete training pipeline."""
        log.info("🚀 AI Trainer: Starting daily model retraining...")
        
        if not self.db_path.exists():
            log.warning("AI Trainer: Database not found at {}. Skipping.", self.db_path)
            return False

        try:
            # 1. Connect and Fetch
            conn = duckdb.connect(str(self.db_path))
            df = conn.execute(
                "SELECT * FROM ohlcv WHERE symbol='XAUUSD' AND timeframe='M15' ORDER BY timestamp ASC"
            ).df()
            conn.close()

            if len(df) < 500:
                log.info("AI Trainer: Insufficient data ({} bars). Need 500+.", len(df))
                return False

            # 2. Feature Engineering
            df.ta.rsi(length=14, append=True)
            df.ta.bbands(length=20, std=2, append=True)
            df.ta.atr(length=14, append=True)
            df['ema20'] = ta.ema(df['close'], length=20)
            df['dist_ema'] = (df['close'] - df['ema20']) / df['close']
            
            features = ['RSI_14', 'BBP_20_2.0_2.0', 'ATRr_14', 'dist_ema']
            
            # 3. Labeling
            df['target'] = (df['close'].shift(-10) > df['close']).astype(int)
            df = df.dropna(subset=features + ['target'])
            
            X = df[features].astype(np.float32)
            y = df['target']

            # 4. Train with Metrics
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)
            
            clf = RandomForestClassifier(n_estimators=100, max_depth=5)
            clf.fit(X_train, y_train)
            
            # Calculate metrics
            y_pred = clf.predict(X_test)
            acc = accuracy_score(y_test, y_pred)
            prec = precision_score(y_test, y_pred, zero_division=0)
            rec = recall_score(y_test, y_pred, zero_division=0)

            # 5. Export
            onx = to_onnx(clf, X[:1].values)
            with open(str(self.model_path), "wb") as f:
                f.write(onx.SerializeToString())
            
            # 6. Save Metrics
            self._save_run_metrics({
                "timestamp": datetime.now().isoformat(),
                "accuracy": round(float(acc), 4),
                "precision": round(float(prec), 4),
                "recall": round(float(rec), 4),
                "samples": len(df),
                "features": features,
                "status": "SUCCESS"
            })
            
            log.info("✅ AI Trainer: Daily model updated (Acc: {:.2%})", acc)
            return True

        except Exception as e:
            log.error("❌ AI Trainer: Failed with error: {}", e)
            self._save_run_metrics({
                "timestamp": datetime.now().isoformat(),
                "status": "FAILED",
                "error": str(e)
            })
            return False

    def _save_run_metrics(self, run_data: dict):
        """Appends metrics to history file."""
        history = []
        if self.metrics_path.exists():
            try:
                with open(self.metrics_path, "r") as f:
                    history = json.load(f)
            except: pass
        
        history.append(run_data)
        # Keep last 50 runs
        history = history[-50:]
        
        with open(self.metrics_path, "w") as f:
            json.dump(history, f, indent=2)

    def get_latest_metrics(self) -> dict:
        """Returns the most recent successful run metrics."""
        if not self.metrics_path.exists():
            return {}
        try:
            with open(self.metrics_path, "r") as f:
                history = json.load(f)
                for run in reversed(history):
                    if run["status"] == "SUCCESS":
                        return run
        except: pass
        return {}

    def get_history(self) -> list:
        if not self.metrics_path.exists(): return []
        try:
            with open(self.metrics_path, "r") as f:
                return json.load(f)
        except: return []

trainer = AIModelTrainer()
