import duckdb
import pandas as pd
import pandas_ta as ta
from sklearn.ensemble import RandomForestClassifier
from skl2onnx import to_onnx
from pathlib import Path
import numpy as np

# 1. Configuration
DB_PATH = "../data/market_data.duckdb"
MODEL_PATH = "../models/trend_predictor.onnx"
SYMBOL = "XAUUSD"
TIMEFRAME = "M15"

def train_from_duckdb():
    if not Path(DB_PATH).exists():
        print(f"❌ Database not found at {DB_PATH}. Run the bot first to collect data!")
        return

    # 2. Data Collection
    print(f"📡 Extracting {SYMBOL} {TIMEFRAME} data from DuckDB...")
    conn = duckdb.connect(DB_PATH)
    table_name = f"{SYMBOL.lower()}_{TIMEFRAME.lower()}"
    df = conn.execute(f"SELECT * FROM {table_name} ORDER BY timestamp ASC").df()
    
    if len(df) < 500:
        print("⚠️ Not enough data (need >500 bars). Using synthetic data for demo...")
        return # In reality, wait for bot to collect more

    # 3. Feature Engineering
    print("🛠️ Engineering features...")
    df.ta.rsi(length=14, append=True)
    df.ta.bbands(length=20, std=2, append=True)
    df.ta.atr(length=14, append=True)
    
    # Custom feature: Distance from EMA
    df['ema20'] = ta.ema(df['close'], length=20)
    df['dist_ema'] = (df['close'] - df['ema20']) / df['close']
    
    # 4. Labeling (Fixed Horizon 10 bars)
    print("🏷️ Labeling data (Fixed Horizon)...")
    df['target'] = (df['close'].shift(-10) > df['close']).astype(int)
    
    # 5. Prepare Payload
    # Features: [RSI_14, BBP_20_2.0, ATR_14, dist_ema]
    features = ['RSI_14', 'BBP_20_2.0', 'ATRr_14', 'dist_ema']
    df = df.dropna(subset=features + ['target'])
    
    X = df[features].astype(np.float32)
    y = df['target']
    
    # 6. Train Model
    print("🚀 Training Random Forest...")
    clf = RandomForestClassifier(n_estimators=100)
    clf.fit(X, y)
    
    # 7. Export to ONNX
    print("📦 Exporting to ONNX...")
    onx = to_onnx(clf, X[:1].values)
    with open(MODEL_PATH, "wb") as f:
        f.write(onx.SerializeToString())
    
    print(f"✅ Success! Local AI model saved to {MODEL_PATH}")

if __name__ == "__main__":
    train_from_duckdb()
