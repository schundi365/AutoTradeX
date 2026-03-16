# ML Pipeline Architecture

## Complete System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         APEX TRADING BOT ML PIPELINE                         │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. DATA COLLECTION & STORAGE                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Market Data Sources                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│  │   MT5    │  │  CCXT    │  │ yFinance │  │   FRED   │                   │
│  │  Broker  │  │  Crypto  │  │  Stocks  │  │  Macro   │                   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘                   │
│       │             │              │              │                          │
│       └─────────────┴──────────────┴──────────────┘                         │
│                            ↓                                                 │
│              ┌─────────────────────────────┐                                │
│              │ Historical Data Warehouse   │                                │
│              │  (DuckDB + Parquet)         │                                │
│              │  • OHLCV data               │                                │
│              │  • 6+ months history        │                                │
│              │  • Multiple timeframes      │                                │
│              └─────────────┬───────────────┘                                │
│                            │                                                 │
└────────────────────────────┼─────────────────────────────────────────────────┘
                             │
┌────────────────────────────┼─────────────────────────────────────────────────┐
│ 2. FEATURE ENGINEERING                                                       │
├────────────────────────────┼─────────────────────────────────────────────────┤
│                            ↓                                                 │
│              ┌─────────────────────────────┐                                │
│              │   Feature Pipeline          │                                │
│              │  • Technical indicators     │                                │
│              │  • Price patterns           │                                │
│              │  • Volume analysis          │                                │
│              │  • Volatility metrics       │                                │
│              │  • Statistical features     │                                │
│              └─────────────┬───────────────┘                                │
│                            │                                                 │
│                            ↓                                                 │
│              ┌─────────────────────────────┐                                │
│              │  Feature Vector (100+ dims) │                                │
│              │  [RSI, EMA, Volume, ATR,    │                                │
│              │   Returns, Volatility, ...]  │                                │
│              └─────────────┬───────────────┘                                │
│                            │                                                 │
└────────────────────────────┼─────────────────────────────────────────────────┘
                             │
┌────────────────────────────┼─────────────────────────────────────────────────┐
│ 3. MODEL TRAINING                                                            │
├────────────────────────────┼─────────────────────────────────────────────────┤
│                            │                                                 │
│         ┌──────────────────┴──────────────────┐                             │
│         │                                      │                             │
│         ↓                                      ↓                             │
│  ┌──────────────────┐              ┌──────────────────┐                     │
│  │ SUPERVISED       │              │ REINFORCEMENT    │                     │
│  │ LEARNING         │              │ LEARNING         │                     │
│  ├──────────────────┤              ├──────────────────┤                     │
│  │ • XGBoost        │              │ • PPO Agent      │                     │
│  │ • LightGBM       │              │ • Position Sizing│                     │
│  │ • Random Forest  │              │ • Risk Mgmt      │                     │
│  ├──────────────────┤              ├──────────────────┤                     │
│  │ Predicts:        │              │ Optimizes:       │                     │
│  │ • Price UP/DOWN  │              │ • Trade size     │                     │
│  │ • Confidence     │              │ • Sharpe ratio   │                     │
│  │   (0-1 prob)     │              │ • Drawdown       │                     │
│  └────────┬─────────┘              └────────┬─────────┘                     │
│           │                                  │                               │
│           └──────────────┬───────────────────┘                               │
│                          ↓                                                   │
│              ┌─────────────────────────────┐                                │
│              │   Model Evaluation          │                                │
│              │  • Accuracy > 52%           │                                │
│              │  • Sharpe > 1.5             │                                │
│              │  • Out-of-sample testing    │                                │
│              └─────────────┬───────────────┘                                │
│                            │                                                 │
│                            ↓                                                 │
│              ┌─────────────────────────────┐                                │
│              │   Model Registry            │                                │
│              │  • Version control          │                                │
│              │  • Metadata storage         │                                │
│              │  • Deployment tracking      │                                │
│              └─────────────┬───────────────┘                                │
│                            │                                                 │
└────────────────────────────┼─────────────────────────────────────────────────┘
                             │
┌────────────────────────────┼─────────────────────────────────────────────────┐
│ 4. MODEL VALIDATION & TESTING                                                │
├────────────────────────────┼─────────────────────────────────────────────────┤
│                            │                                                 │
│         ┌──────────────────┴──────────────────┐                             │
│         │                                      │                             │
│         ↓                                      ↓                             │
│  ┌──────────────────┐              ┌──────────────────┐                     │
│  │ Backtesting      │              │ A/B Testing      │                     │
│  │ Engine           │              │ Framework        │                     │
│  ├──────────────────┤              ├──────────────────┤                     │
│  │ • Historical     │              │ • Control vs     │                     │
│  │   simulation     │              │   Variant        │                     │
│  │ • Performance    │              │ • Traffic split  │                     │
│  │   metrics        │              │ • Statistical    │                     │
│  │ • Risk analysis  │              │   significance   │                     │
│  └────────┬─────────┘              └────────┬─────────┘                     │
│           │                                  │                               │
│           └──────────────┬───────────────────┘                               │
│                          ↓                                                   │
│              ┌─────────────────────────────┐                                │
│              │   Validation Results        │                                │
│              │  • Sharpe ratio             │                                │
│              │  • Win rate                 │                                │
│              │  • Max drawdown             │                                │
│              │  • Statistical tests        │                                │
│              └─────────────┬───────────────┘                                │
│                            │                                                 │
│                            ↓                                                 │
│                    ┌───────────────┐                                         │
│                    │ Pass? (Y/N)   │                                         │
│                    └───┬───────┬───┘                                         │
│                        │       │                                             │
│                     YES│       │NO                                           │
│                        │       └──→ Reject / Retrain                         │
│                        ↓                                                     │
└────────────────────────┼─────────────────────────────────────────────────────┘
                         │
┌────────────────────────┼─────────────────────────────────────────────────────┐
│ 5. PRODUCTION DEPLOYMENT                                                     │
├────────────────────────┼─────────────────────────────────────────────────────┤
│                        │                                                     │
│                        ↓                                                     │
│         ┌──────────────────────────────────┐                                │
│         │   Deployment Pipeline            │                                │
│         │  1. Paper Trading (1-2 weeks)    │                                │
│         │  2. A/B Test (20% traffic)       │                                │
│         │  3. Gradual Rollout (50%, 100%)  │                                │
│         └──────────────┬───────────────────┘                                │
│                        │                                                     │
│                        ↓                                                     │
│         ┌──────────────────────────────────┐                                │
│         │   Model Inference Service        │                                │
│         │  • Model loading & caching       │                                │
│         │  • Fast predictions (<10ms)      │                                │
│         │  • Batch processing              │                                │
│         │  • Performance monitoring        │                                │
│         └──────────────┬───────────────────┘                                │
│                        │                                                     │
└────────────────────────┼─────────────────────────────────────────────────────┘
                         │
┌────────────────────────┼─────────────────────────────────────────────────────┐
│ 6. LIVE TRADING                                                              │
├────────────────────────┼─────────────────────────────────────────────────────┤
│                        │                                                     │
│                        ↓                                                     │
│         ┌──────────────────────────────────┐                                │
│         │   Trading Decision Engine        │                                │
│         └──────────────┬───────────────────┘                                │
│                        │                                                     │
│         ┌──────────────┴───────────────┐                                    │
│         │                                │                                   │
│         ↓                                ↓                                   │
│  ┌──────────────┐              ┌──────────────┐                             │
│  │ Supervised   │              │ RL Agent     │                             │
│  │ Model        │              │ (PPO)        │                             │
│  ├──────────────┤              ├──────────────┤                             │
│  │ Input:       │              │ Input:       │                             │
│  │ • Features   │              │ • Features   │                             │
│  │              │              │ • Confidence │                             │
│  ├──────────────┤              ├──────────────┤                             │
│  │ Output:      │              │ Output:      │                             │
│  │ • Direction  │              │ • Position   │                             │
│  │ • Confidence │              │   size       │                             │
│  │   (0.72)     │              │   (1.5%)     │                             │
│  └──────┬───────┘              └──────┬───────┘                             │
│         │                              │                                     │
│         └──────────────┬───────────────┘                                     │
│                        ↓                                                     │
│         ┌──────────────────────────────────┐                                │
│         │   Risk Management                │                                │
│         │  • Position size limits (2% max) │                                │
│         │  • Stop loss / Take profit       │                                │
│         │  • Drawdown limits               │                                │
│         │  • Exposure limits               │                                │
│         └──────────────┬───────────────────┘                                │
│                        │                                                     │
│                        ↓                                                     │
│         ┌──────────────────────────────────┐                                │
│         │   Trade Execution                │                                │
│         │  • MT5 Broker                    │                                │
│         │  • Order placement               │                                │
│         │  • Position monitoring           │                                │
│         └──────────────┬───────────────────┘                                │
│                        │                                                     │
└────────────────────────┼─────────────────────────────────────────────────────┘
                         │
┌────────────────────────┼─────────────────────────────────────────────────────┐
│ 7. MONITORING & FEEDBACK                                                     │
├────────────────────────┼─────────────────────────────────────────────────────┤
│                        │                                                     │
│                        ↓                                                     │
│         ┌──────────────────────────────────┐                                │
│         │   Performance Monitoring         │                                │
│         │  • Prediction accuracy           │                                │
│         │  • Win rate                      │                                │
│         │  • Sharpe ratio                  │                                │
│         │  • Drawdown                      │                                │
│         │  • Inference latency             │                                │
│         └──────────────┬───────────────────┘                                │
│                        │                                                     │
│                        ↓                                                     │
│         ┌──────────────────────────────────┐                                │
│         │   Trade Journal                  │                                │
│         │  • Decision logging              │                                │
│         │  • Feature snapshots             │                                │
│         │  • Outcomes tracking             │                                │
│         │  • Model attribution             │                                │
│         └──────────────┬───────────────────┘                                │
│                        │                                                     │
│                        ↓                                                     │
│         ┌──────────────────────────────────┐                                │
│         │   Alerts & Triggers              │                                │
│         │  • Accuracy drop > 5%            │                                │
│         │  • Sharpe < 1.0                  │                                │
│         │  • Drawdown > 10%                │                                │
│         │  • Inference latency > 50ms      │                                │
│         └──────────────┬───────────────────┘                                │
│                        │                                                     │
│                        ↓                                                     │
│         ┌──────────────────────────────────┐                                │
│         │   Retraining Pipeline            │                                │
│         │  • Scheduled (weekly)            │                                │
│         │  • Triggered (performance drop)  │                                │
│         │  • Automatic deployment          │                                │
│         │  • Rollback on failure           │                                │
│         └──────────────┬───────────────────┘                                │
│                        │                                                     │
│                        └──────────────────────────────────────────────────┐  │
│                                                                            │  │
└────────────────────────────────────────────────────────────────────────────┼──┘
                                                                             │
                         ┌───────────────────────────────────────────────────┘
                         │
                         └──→ Back to Step 3 (Model Training)
```

---

## Data Flow Example

### Real Trading Scenario

```
Time: 10:00 AM
Symbol: EURUSD
Current Price: 1.0850

┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: Feature Extraction                                      │
└─────────────────────────────────────────────────────────────────┘
  Market Data → Feature Pipeline
  
  Output:
  {
    'rsi_14': 65.2,
    'ema_20': 1.0845,
    'ema_50': 1.0830,
    'volume_ratio': 1.35,
    'volatility_20': 0.0012,
    'return_1bar': 0.0002,
    'return_5bar': 0.0015,
    ... (100+ features)
  }

┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: Direction Prediction (Supervised Model)                 │
└─────────────────────────────────────────────────────────────────┘
  Features → XGBoost Model
  
  Output:
  {
    'prediction': 'UP',
    'probability': 0.72,
    'confidence': 'HIGH'
  }

┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: Confidence Check                                        │
└─────────────────────────────────────────────────────────────────┘
  Probability: 0.72 > 0.65 (MIN_CONFIDENCE)
  
  Decision: PROCEED with BUY signal

┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: Position Sizing (RL Agent)                              │
└─────────────────────────────────────────────────────────────────┘
  Features + Confidence → PPO Agent
  
  Output:
  {
    'position_size_pct': 0.015,  # 1.5% of capital
    'position_size_usd': 150,    # $10,000 * 0.015
    'reasoning': 'High confidence + low volatility'
  }

┌─────────────────────────────────────────────────────────────────┐
│ STEP 5: Risk Management                                         │
└─────────────────────────────────────────────────────────────────┘
  Calculate SL/TP:
  
  ATR = 0.0015
  Entry = 1.0850
  Stop Loss = 1.0850 - (2 * 0.0015) = 1.0820
  Take Profit = 1.0850 + (3 * 0.0015) = 1.0895
  Risk:Reward = 1:1.5

┌─────────────────────────────────────────────────────────────────┐
│ STEP 6: Execute Trade                                           │
└─────────────────────────────────────────────────────────────────┘
  Send to MT5:
  
  {
    'symbol': 'EURUSD',
    'direction': 'BUY',
    'lots': 0.015,
    'entry': 1.0850,
    'sl': 1.0820,
    'tp': 1.0895
  }
  
  Trade ID: #12345

┌─────────────────────────────────────────────────────────────────┐
│ STEP 7: Monitor & Log                                           │
└─────────────────────────────────────────────────────────────────┘
  Record to Trade Journal:
  
  {
    'trade_id': 12345,
    'timestamp': '2024-03-15 10:00:00',
    'model_prediction': 0.72,
    'position_size': 0.015,
    'model_version': 'xgboost_v2',
    'features': {...}
  }

┌─────────────────────────────────────────────────────────────────┐
│ STEP 8: Trade Closes (2 hours later)                            │
└─────────────────────────────────────────────────────────────────┘
  Time: 12:00 PM
  Exit Price: 1.0895 (Take Profit hit)
  
  Result:
  {
    'pnl': +$67.50,
    'return': +45%,
    'duration': '2 hours',
    'outcome': 'WIN'
  }

┌─────────────────────────────────────────────────────────────────┐
│ STEP 9: Update Model Performance                                │
└─────────────────────────────────────────────────────────────────┘
  Update metrics:
  
  Model: xgboost_v2
  - Accuracy: 58.2% → 58.3%
  - Win Rate: 57.5% → 57.6%
  - Sharpe: 1.65 → 1.66
  
  Status: ✓ Model performing well
```

---

## Component Interactions

```
┌──────────────┐
│  Dashboard   │ ← User Interface
└──────┬───────┘
       │
       ↓
┌──────────────┐
│  API Server  │ ← REST API + WebSocket
└──────┬───────┘
       │
       ├─────────────────────────────────────────┐
       │                                         │
       ↓                                         ↓
┌──────────────┐                         ┌──────────────┐
│ ML Endpoints │                         │ Bot Control  │
└──────┬───────┘                         └──────┬───────┘
       │                                         │
       ├──────────┬──────────┬──────────┐       │
       │          │          │          │       │
       ↓          ↓          ↓          ↓       ↓
┌──────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│Supervised│ │   RL   │ │ Model  │ │Backtest│ │Trading │
│ Training │ │Training│ │Registry│ │ Engine │ │ Engine │
└──────────┘ └────────┘ └────────┘ └────────┘ └────────┘
     │            │          │          │          │
     └────────────┴──────────┴──────────┴──────────┘
                         │
                         ↓
              ┌──────────────────┐
              │ Data Warehouse   │
              │ (DuckDB/Parquet) │
              └──────────────────┘
```

---

## Technology Stack

### Core ML Libraries
- **XGBoost**: Gradient boosting for classification
- **LightGBM**: Fast gradient boosting
- **Stable-Baselines3**: Reinforcement learning (PPO)
- **Scikit-learn**: Model evaluation metrics
- **SHAP**: Feature importance analysis

### Data Processing
- **Pandas**: Data manipulation
- **NumPy**: Numerical computations
- **DuckDB**: Analytical database
- **Parquet**: Columnar storage format

### Infrastructure
- **FastAPI**: REST API server
- **Redis**: Feature caching (optional)
- **Joblib**: Model serialization
- **Gymnasium**: RL environment

### Monitoring
- **Loguru**: Structured logging
- **Prometheus**: Metrics (optional)
- **Grafana**: Dashboards (optional)

---

## Performance Characteristics

### Training Time
- **Supervised Model**: 2-4 hours (6 months data)
- **RL Agent**: 8-12 hours (1M timesteps)
- **Backtesting**: 1-2 hours (3 months data)

### Inference Time
- **Single Prediction**: <10ms
- **Batch Prediction (10)**: <20ms
- **Feature Extraction**: <5ms

### Resource Usage
- **Training**: 4-8 GB RAM, 2-4 CPU cores
- **Inference**: 1-2 GB RAM, 1 CPU core
- **Storage**: 5-10 GB (models + data)

### Scalability
- **Symbols**: 20+ concurrent
- **Predictions/sec**: 100+
- **Models**: 10+ versions tracked

---

## Further Reading

- [How ML Models Help Trading](./HOW_ML_MODELS_HELP_TRADING.md)
- [Quick Reference](./QUICK_REFERENCE.md)
- [Full README](./README.md)
