import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from skl2onnx import to_onnx
from pathlib import Path

# 1. Setup paths
models_dir = Path("../models")
models_dir.mkdir(exist_ok=True)
model_path = models_dir / "trend_predictor.onnx"

print("🚀 Starting baseline model training...")

# 2. Generate/Load Data (Synthetic for demonstration)
# In production, you would pull this from your DuckDB storage
def generate_dummy_data(n_samples=1000):
    # Features: [RSI, ADX, VolatilityRatio, Momentum]
    X = np.random.rand(n_samples, 4).astype(np.float32)
    X[:, 0] *= 100  # RSI 0-100
    X[:, 1] *= 50   # ADX 0-50
    X[:, 2] *= 3    # Volatility 0-3
    X[:, 3] = (X[:, 3] - 0.5) * 0.1 # Momentum -0.05 to 0.05
    
    # Target: 1 if Momentum is positive and RSI is not overbought
    y = ((X[:, 3] > 0) & (X[:, 0] < 70)).astype(int)
    return X, y

X, y = generate_dummy_data()

# 3. Train a Random Forest
clf = RandomForestClassifier(n_estimators=100, max_depth=5)
clf.fit(X, y)
print("✅ Model trained.")

# 4. Convert to ONNX
# We need to specify the input type and shape
# Here: 1 row, 4 features
onx = to_onnx(clf, X[:1])

with open(str(model_path), "wb") as f:
    f.write(onx.SerializeToString())

print(f"📦 Model exported successfully to: {model_path}")
print("💡 You can now use this model in your OnnxRunner!")
