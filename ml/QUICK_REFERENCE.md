# ML Models Quick Reference

## At a Glance

| Model | Purpose | Input | Output | When to Use |
|-------|---------|-------|--------|-------------|
| **XGBoost/LightGBM** | Price direction prediction | Market features (RSI, EMA, volume, etc.) | Probability of UP (0-1) | Every trade decision |
| **PPO Agent** | Position sizing | Market features + model confidence | Position size (0-2% of capital) | Every trade execution |
| **Model Inference** | Fast predictions | Features + model | Prediction in <10ms | Real-time trading |
| **Feature Importance** | Model interpretation | Model + features | Feature contributions | Model debugging |
| **A/B Testing** | Model comparison | Two models + traffic split | Statistical comparison | New model deployment |
| **Retraining Pipeline** | Model updates | Historical data | Updated model | Weekly/on-demand |
| **Backtesting** | Strategy validation | Strategy + historical data | Performance metrics | Before live trading |

---

## Decision Flow

```
Market Data
    ↓
Feature Extraction (100+ features)
    ↓
Supervised Model (XGBoost/LightGBM)
    ↓
Confidence Check (>65% or <35%)
    ↓
RL Agent (PPO) - Position Sizing
    ↓
Risk Management (SL/TP)
    ↓
Execute Trade
    ↓
Monitor & Learn
```

---

## Model Performance Targets

### Supervised Models (XGBoost/LightGBM)
- **Minimum Accuracy**: 52% (better than random)
- **Target Accuracy**: 58%+
- **Minimum ROC AUC**: 0.55
- **Target ROC AUC**: 0.65+

### RL Agent (PPO)
- **Minimum Sharpe Ratio**: 1.0
- **Target Sharpe Ratio**: 1.5+
- **Promotion Threshold**: 1.5
- **Maximum Drawdown**: <15%

### Production Metrics
- **Inference Latency**: <10ms
- **Win Rate**: 55-60%
- **Sharpe Ratio**: 1.5-2.0
- **Max Drawdown**: <10%

---

## Training Schedule

| Task | Frequency | Duration | Purpose |
|------|-----------|----------|---------|
| Supervised Model Retraining | Weekly | 2-4 hours | Adapt to market changes |
| RL Agent Retraining | Monthly | 8-12 hours | Update position sizing strategy |
| A/B Testing | Continuous | 1-2 weeks | Validate new models |
| Backtesting | Before deployment | 1-2 hours | Validate strategies |
| Performance Review | Daily | 10 minutes | Monitor model health |

---

## Common Commands

### Train Supervised Model
```python
from ml.supervised_training import SupervisedTrainingPipeline, TrainingConfig

config = TrainingConfig(symbol="EURUSD", training_months=6)
result = pipeline.train_and_evaluate(config, model_type="xgboost")
```

### Train RL Agent
```python
from ml.ppo_agent_training import PPOAgentTrainer, PPOConfig

config = PPOConfig(symbol="EURUSD", total_timesteps=1_000_000)
agent, metrics, metadata = trainer.train_agent(config)
```

### Run Backtest
```python
from ml.backtesting_engine import BacktestingEngine

results = engine.run_backtest(
    strategy_func=my_strategy,
    symbol="EURUSD",
    start_date="2024-01-01",
    end_date="2024-03-31"
)
```

### Deploy Model
```python
from ml.model_registry import ModelRegistry

registry.update_deployment_status(
    model_id,
    DeploymentStatus.PRODUCTION.value,
    DeploymentEnvironment.LIVE.value
)
```

---

## Troubleshooting

### Model Accuracy Too Low (<52%)
- ✅ Increase training data (more months)
- ✅ Add more features
- ✅ Tune hyperparameters
- ✅ Check data quality

### RL Agent Not Meeting Sharpe Target (<1.5)
- ✅ Increase training timesteps
- ✅ Adjust reward window
- ✅ Tune PPO hyperparameters
- ✅ Check environment setup

### Inference Too Slow (>50ms)
- ✅ Enable model caching
- ✅ Use batch predictions
- ✅ Reduce feature count
- ✅ Optimize feature extraction

### Model Performance Degrading
- ✅ Trigger immediate retraining
- ✅ Check for market regime change
- ✅ Review recent predictions
- ✅ Analyze feature importance

---

## Key Metrics to Monitor

### Daily
- Prediction accuracy
- Win rate
- Sharpe ratio
- Inference latency

### Weekly
- Model performance vs baseline
- Feature importance changes
- A/B test results
- Retraining triggers

### Monthly
- Long-term Sharpe ratio
- Maximum drawdown
- Model version history
- Production incidents

---

## Best Practices

### Training
1. Always use walk-forward validation (no look-ahead bias)
2. Train on at least 6 months of data
3. Validate on out-of-sample data
4. Check for overfitting (train vs validation gap)

### Deployment
1. Start with paper trading (1-2 weeks)
2. Use A/B testing (20% traffic initially)
3. Monitor for 1 week before full rollout
4. Keep previous model version for rollback

### Monitoring
1. Track prediction accuracy daily
2. Set alerts for performance degradation
3. Review feature importance weekly
4. Retrain when accuracy drops >5%

### Risk Management
1. Never exceed 2% position size
2. Always use stop losses
3. Limit daily drawdown to 5%
4. Pause trading if Sharpe < 0.5

---

## File Locations

```
ml/
├── supervised_training.py          # XGBoost/LightGBM training
├── ppo_agent_training.py           # RL agent training
├── model_inference_service.py      # Real-time predictions
├── feature_importance.py           # SHAP analysis
├── ab_testing_framework.py         # A/B testing
├── model_retraining_pipeline.py    # Automatic retraining
├── backtesting_engine.py           # Strategy validation
├── model_registry.py               # Model versioning
└── rl_training_environment.py      # RL environment

models/
├── supervised/                     # Supervised models
│   ├── xgboost_EURUSD_v1/
│   └── lightgbm_EURUSD_v1/
├── reinforcement/                  # RL agents
│   └── ppo_EURUSD_v1/
└── registry.db                     # Model metadata

data/
├── historical_data_warehouse.py    # Historical data
└── feature_pipeline.py             # Real-time features
```

---

## Quick Links

- [Detailed Guide](./HOW_ML_MODELS_HELP_TRADING.md)
- [Full README](./README.md)
- [A/B Testing Guide](./AB_TESTING_README.md)
- [Backtesting Guide](./BACKTESTING_README.md)
- [Example Scripts](./example_training_usage.py)
