import onnxruntime as ort
import numpy as np
import pandas as pd
from pathlib import Path
from core.logger import get_agent_logger

log = get_agent_logger("ONNX")

class OnnxRunner:
    """
    Executes pre-trained .onnx models for trend prediction.
    Hot-reloads if the model file is updated on disk.
    """
    def __init__(self, model_path: str = "models/trend_predictor.onnx"):
        self.model_path = Path(model_path)
        self.session = None
        self.last_mtime = 0
        self._load_model()

    def _load_model(self):
        """Loads or reloads the ONNX model."""
        if self.model_path.exists():
            try:
                self.session = ort.InferenceSession(str(self.model_path))
                self.last_mtime = self.model_path.stat().st_mtime
                log.info("ONNX: Model loaded/reloaded from {}", self.model_path)
            except Exception as e:
                log.error("ONNX: Failed to load model: {}", e)
        else:
            log.warning("ONNX: Model file {} not found.", self.model_path)

    def _check_reload(self):
        """Checks if the model file has been updated on disk."""
        if self.model_path.exists():
            mtime = self.model_path.stat().st_mtime
            if mtime > self.last_mtime:
                log.info("ONNX: New model detected, hot-reloading...")
                self._load_model()

    def predict_trend(self, df: pd.DataFrame) -> float:
        """
        Expects a DataFrame with specific features.
        Returns a probability score (0.0 to 1.0).
        """
        self._check_reload()
        
        if self.session is None:
            return 0.5  # Neutral

        try:
            # Note: In production, preprocess DF into model's input shape
            # input_name = self.session.get_inputs()[0].name
            # pred = self.session.run(None, {input_name: features})
            
            # Simulated inference for demonstration
            log.debug("ONNX: Running inference on latest {} bars", len(df))
            return 0.65 
        except Exception as e:
            log.warning("ONNX: Prediction error: {}", e)
            return 0.5

onnx_runner = OnnxRunner()
