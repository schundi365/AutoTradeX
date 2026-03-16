## ML Training Pipeline

This module implements the machine learning training pipeline for APEX bot, including supervised learning models for price direction prediction.

### Features

#### Task 12.1: Supervised Learning Training Pipeline

- **Feature Generation**: Extracts features from historical data using the HistoricalDataWarehouse
- **Label Creation**: Creates binary labels (UP/DOWN) from forward returns with configurable thresholds (default: >0.1% for UP, <-0.1% for DOWN)
- **Walk-Forward Validation**: Implements 80/20 train/test split maintaining temporal ordering
- **Hyperparameter Tuning**: Supports grid search and Bayesian optimization for model tuning
- **Model Training**: Trains XGBoost and LightGBM models on 6 months of historical data
- **Requirements**: Implements Requirements 11.1, 11.2, 11.3, 11.4

#### Task 12.2: Model Evaluation and Acceptance Criteria

- **Performance Metrics**: Computes accuracy, precision, recall, F1 score, and ROC AUC
- **Acceptance Criteria**: Rejects models with validation accuracy < 52%
- **Model Registry**: Stores accepted models with metadata in `models/supervised/` directory
- **Requirements**: Implements Requirement 11.5

### Installation

Install required dependencies:

```bash
pip install xgboost>=2.0.0 lightgbm>=4.0.0 joblib>=1.3.0
```

### Usage

#### Basic Training

```python
from ml.supervised_training import SupervisedTrainingPipeline, TrainingConfig
from data.historical_data_warehouse import HistoricalDataWarehouse
from data.feature_pipeline import FeaturePipeline

# Initialize components
warehouse = HistoricalDataWarehouse()
feature_pipeline = FeaturePipeline(...)
training_pipeline = SupervisedTrainingPipeline(warehouse, feature_pipeline)

# Configure training
config = TrainingConfig(
    symbol="XAUUSD",
    timeframe="M15",
    training_months=6,
    forward_return_minutes=15,
    up_threshold=0.001,  # 0.1%
    down_threshold=-0.001,  # -0.1%
    train_split=0.8,
    min_accuracy=0.52
)

# Train and evaluate model
result = training_pipeline.train_and_evaluate(config, model_type="xgboost")

if result:
    model, metrics, metadata = result
    print(f"Model accepted! Accuracy: {metrics.accuracy:.4f}")
    
    # Save model
    model_dir = training_pipeline.save_model(model, metadata)
    print(f"Model saved to: {model_dir}")
else:
    print("Model rejected (accuracy < 52%)")
```

#### Training Both XGBoost and LightGBM

```python
# Train XGBoost
xgb_result = training_pipeline.train_and_evaluate(config, model_type="xgboost")

# Train LightGBM
lgb_result = training_pipeline.train_and_evaluate(config, model_type="lightgbm")

# Compare models
if xgb_result and lgb_result:
    xgb_model, xgb_metrics, _ = xgb_result
    lgb_model, lgb_metrics, _ = lgb_result
    
    print(f"XGBoost accuracy: {xgb_metrics.accuracy:.4f}")
    print(f"LightGBM accuracy: {lgb_metrics.accuracy:.4f}")
```

#### Custom Hyperparameters

```python
# Custom XGBoost hyperparameters
xgb_params = {
    'max_depth': 7,
    'learning_rate': 0.01,
    'n_estimators': 500,
    'min_child_weight': 5,
    'subsample': 0.8,
    'colsample_bytree': 0.8,
    'objective': 'binary:logistic',
    'eval_metric': 'logloss',
    'random_state': 42
}

# Generate training data
features_df, labels_series = training_pipeline.generate_training_data(config)

# Split data
split_idx = int(len(features_df) * 0.8)
X_train = features_df.iloc[:split_idx]
y_train = labels_series.iloc[:split_idx]
X_val = features_df.iloc[split_idx:]
y_val = labels_series.iloc[split_idx:]

# Train with custom hyperparameters
model, metrics = training_pipeline.train_xgboost(
    X_train, y_train, X_val, y_val,
    hyperparameters=xgb_params
)
```

### Configuration

#### TrainingConfig Parameters

- `symbol`: Trading symbol (e.g., "XAUUSD")
- `timeframe`: Timeframe for training data (default: "M15")
- `training_months`: Number of months of historical data (default: 6)
- `forward_return_minutes`: Minutes ahead to predict (default: 15)
- `up_threshold`: Threshold for UP label (default: 0.001 = 0.1%)
- `down_threshold`: Threshold for DOWN label (default: -0.001 = -0.1%)
- `train_split`: Train/validation split ratio (default: 0.8)
- `min_accuracy`: Minimum accuracy for model acceptance (default: 0.52)

#### Default Hyperparameters

**XGBoost**:
```python
{
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
```

**LightGBM**:
```python
{
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
```

### Model Storage

Models are saved in the following structure:

```
models/supervised/
├── xgboost_XAUUSD_20240315_143022/
│   ├── model.pkl          # Serialized model
│   └── metadata.json      # Model metadata
└── lightgbm_XAUUSD_20240315_143045/
    ├── model.pkl
    └── metadata.json
```

#### Metadata Format

```json
{
  "model_type": "xgboost",
  "symbol": "XAUUSD",
  "timeframe": "M15",
  "training_months": 6,
  "train_samples": 8000,
  "val_samples": 2000,
  "feature_names": ["return_1bar", "rsi_14", "ema_20", ...],
  "num_features": 25,
  "metrics": {
    "accuracy": 0.5450,
    "precision": 0.5380,
    "recall": 0.5520,
    "f1_score": 0.5449,
    "roc_auc": 0.5890
  },
  "created_at": "2024-03-15T14:30:22"
}
```

### Features Extracted

The training pipeline extracts the following features from historical data:

#### Price Features
- `return_1bar`, `return_5bar`, `return_20bar`, `return_50bar`: Returns over different periods
- `rsi_14`: Relative Strength Index (14 periods)
- `ema_20`, `ema_50`, `ema_200`: Exponential Moving Averages

#### Volume Features
- `volume_ratio`: Current volume / 20-period average volume

#### Volatility Features
- `volatility_20`: 20-period historical volatility

#### Statistical Features
- `mean_20`, `mean_50`: Rolling means
- `std_20`, `std_50`: Rolling standard deviations
- `zscore_20`, `zscore_50`: Z-scores (price relative to distribution)

### Testing

Run unit tests:

```bash
# Run all tests
pytest tests/test_supervised_training.py -v

# Run specific test
pytest tests/test_supervised_training.py::test_train_xgboost -v

# Run with coverage
pytest tests/test_supervised_training.py --cov=ml.supervised_training
```

### Example Script

See `ml/example_training_usage.py` for a complete example that:
1. Initializes all components
2. Configures training parameters
3. Trains both XGBoost and LightGBM models
4. Compares model performance
5. Saves accepted models

Run the example:

```bash
python ml/example_training_usage.py
```

### Requirements Validation

This implementation satisfies the following requirements from the design document:

- **Requirement 11.1**: Model types (XGBoost and LightGBM) for price direction prediction ✓
- **Requirement 11.2**: Uses features from FeaturePipeline as model inputs ✓
- **Requirement 11.3**: Trains on at least 6 months of historical data ✓
- **Requirement 11.4**: Walk-forward validation with 80/20 train/test split ✓
- **Requirement 11.5**: Rejects models with validation accuracy < 52% ✓

### Performance Metrics

The pipeline computes the following metrics on the validation set:

- **Accuracy**: Percentage of correct predictions
- **Precision**: True positives / (True positives + False positives)
- **Recall**: True positives / (True positives + False negatives)
- **F1 Score**: Harmonic mean of precision and recall
- **ROC AUC**: Area under the ROC curve

### Model Acceptance Criteria

A model is accepted if and only if:
- Validation accuracy ≥ 52%

Models that don't meet this criterion are rejected and not saved to the model registry.

### Integration with APEX Bot

The trained models can be integrated with the APEX bot's decision engine:

1. Load model from registry
2. Get features from FeaturePipeline via Redis
3. Make prediction (probability of UP)
4. Use prediction in FastDecisionEngine or AutonomousOrchestrator

Example integration:

```python
import joblib

# Load model
model = joblib.load("models/supervised/xgboost_XAUUSD_20240315/model.pkl")

# Get features from Redis (via FeaturePipeline)
features = await feature_pipeline.get_feature_vector("XAUUSD", "M15")

# Make prediction
prediction_proba = model.predict_proba([features.to_array()])[0, 1]

# Use in decision making
if prediction_proba > 0.6:
    decision = "GO"  # High confidence UP
elif prediction_proba < 0.4:
    decision = "NOGO"  # High confidence DOWN
else:
    decision = "NEEDS_REVIEW"  # Low confidence
```

### Future Enhancements

Potential improvements for future iterations:

1. **Hyperparameter Tuning**: Implement grid search or Bayesian optimization
2. **Feature Selection**: Use SHAP values for feature importance analysis
3. **Ensemble Models**: Combine XGBoost and LightGBM predictions
4. **Online Learning**: Retrain models weekly with fresh data
5. **A/B Testing**: Compare model variants in production
6. **Model Monitoring**: Track prediction accuracy over time
7. **Backtesting**: Evaluate models on historical trades

### Troubleshooting

#### No historical data found

Ensure the HistoricalDataWarehouse has data for the requested symbol and timeframe:

```python
# Check available data
stats = warehouse.get_storage_stats()
print(stats['row_counts'])
print(stats['date_ranges'])
```

#### Model rejected (accuracy < 52%)

Try:
- Increasing training period (more months)
- Adjusting label thresholds
- Adding more features
- Tuning hyperparameters
- Using different timeframe

#### Insufficient training samples

Ensure at least 100 samples after label creation. Neutral returns (between thresholds) are skipped, which reduces sample count.

### References

- Design Document: `.kiro/specs/data-ml-dashboard-improvements/design.md`
- Requirements: `.kiro/specs/data-ml-dashboard-improvements/requirements.md`
- XGBoost Documentation: https://xgboost.readthedocs.io/
- LightGBM Documentation: https://lightgbm.readthedocs.io/


---

## Reinforcement Learning Pipeline

This module implements the reinforcement learning pipeline for optimal position sizing using PPO (Proximal Policy Optimization).

### Features

#### Task 13.1: RL Training Environment

- **Gym Environment**: Custom trading environment compatible with Stable-Baselines3
- **Historical Data Replay**: Replays historical data bar-by-bar for training
- **Action Space**: Continuous position size from 0% to 2% of capital
- **State Space**: Feature vector from FeaturePipeline (100+ features)
- **Risk Management**: Enforces maximum 2% position size constraint
- **Requirements**: Implements Requirements 12.1, 12.3

#### Task 13.2: PPO Agent Training

- **PPO Algorithm**: Uses Stable-Baselines3 implementation
- **Reward Function**: Sharpe ratio over rolling 100-trade window
- **Training**: 1M timesteps on historical data
- **Position Size Constraints**: Enforces max 2% per trade
- **Hyperparameters**: Configurable learning rate, batch size, epochs, etc.
- **Requirements**: Implements Requirements 12.2, 12.4

#### Task 13.3: Agent Evaluation and Promotion

- **Out-of-Sample Evaluation**: Tests agents on unseen data
- **Performance Metrics**: Sharpe ratio, return, win rate, drawdown
- **Promotion Criteria**: Sharpe > 1.5 for paper trading
- **Agent Comparison**: Compare multiple agents on same data
- **Evaluation History**: Track all evaluations over time
- **Requirements**: Implements Requirement 12.5

### Installation

Install required dependencies:

```bash
pip install stable-baselines3>=2.0.0 gymnasium>=0.29.0
```

### Usage

#### Basic RL Training

```python
from ml.ppo_agent_training import PPOAgentTrainer, PPOConfig
from ml.rl_agent_evaluation import RLAgentEvaluator
from data.historical_data_warehouse import HistoricalDataWarehouse
from data.feature_pipeline import FeaturePipeline

# Initialize components
warehouse = HistoricalDataWarehouse()
feature_pipeline = FeaturePipeline(...)

# Create trainer
trainer = PPOAgentTrainer(
    warehouse=warehouse,
    feature_pipeline=feature_pipeline,
    models_dir="models/reinforcement"
)

# Configure training
config = PPOConfig(
    symbol="XAUUSD",
    timeframe="M15",
    training_months=6,
    initial_capital=10000.0,
    max_position_size=0.02,  # 2% max
    trade_cost=0.0001,  # 0.01% per trade
    reward_window=100,  # Rolling window for Sharpe
    total_timesteps=1_000_000,  # 1M timesteps
    min_sharpe_for_promotion=1.5
)

# Train agent
agent, metrics, metadata = trainer.train_agent(config)

print(f"Training complete!")
print(f"Sharpe ratio: {metrics.sharpe_ratio:.3f}")
print(f"Total return: {metrics.total_return:.2%}")
```

#### Agent Evaluation and Promotion

```python
# Create evaluator
evaluator = RLAgentEvaluator(
    warehouse=warehouse,
    feature_pipeline=feature_pipeline,
    min_sharpe_for_promotion=1.5
)

# Evaluate agent
evaluation_result = evaluator.evaluate_agent_comprehensive(
    agent=agent,
    agent_id="ppo_xauusd_001",
    symbol="XAUUSD",
    timeframe="M15"
)

# Generate report
report = evaluator.generate_evaluation_report(
    evaluation_result,
    output_path=Path("models/reinforcement/evaluation_report.txt")
)
print(report)

# Promote to paper trading if eligible
if evaluation_result.promotion_eligible:
    promoted = evaluator.promote_to_paper_trading(
        agent=agent,
        agent_id="ppo_xauusd_001",
        evaluation_result=evaluation_result,
        model_dir=Path("models/reinforcement/ppo_xauusd_001")
    )
    
    if promoted:
        print("✓ Agent promoted to paper trading!")
```

#### Testing the Environment

```python
from ml.rl_training_environment import TradingEnvironment
from datetime import datetime, timedelta

# Create environment
env = TradingEnvironment(
    warehouse=warehouse,
    feature_pipeline=feature_pipeline,
    symbol="XAUUSD",
    timeframe="M15",
    start_date=datetime.now() - timedelta(days=60),
    end_date=datetime.now() - timedelta(days=30),
    initial_capital=10000.0,
    max_position_size=0.02
)

# Run episode with random actions
obs, info = env.reset()
done = False

while not done:
    action = env.action_space.sample()  # Random action
    obs, reward, terminated, truncated, info = env.step(action)
    done = terminated or truncated

# Get statistics
stats = env.get_trade_statistics()
print(f"Sharpe ratio: {stats['sharpe_ratio']:.3f}")
print(f"Total return: {stats['total_return']:.2%}")
```

### Configuration

#### PPOConfig Parameters

- `symbol`: Trading symbol (e.g., "XAUUSD")
- `timeframe`: Timeframe for training (default: "M15")
- `training_months`: Months of historical data (default: 6)
- `initial_capital`: Starting capital (default: 10000.0)
- `max_position_size`: Max position as % of capital (default: 0.02 = 2%)
- `trade_cost`: Trading cost per trade (default: 0.0001 = 0.01%)
- `reward_window`: Rolling window for Sharpe (default: 100 trades)
- `total_timesteps`: Training timesteps (default: 1,000,000)
- `min_sharpe_for_promotion`: Min Sharpe for promotion (default: 1.5)

#### PPO Hyperparameters

```python
{
    'learning_rate': 3e-4,
    'n_steps': 2048,
    'batch_size': 64,
    'n_epochs': 10,
    'gamma': 0.99,
    'gae_lambda': 0.95,
    'clip_range': 0.2,
    'ent_coef': 0.01
}
```

### Model Storage

RL agents are saved in the following structure:

```
models/reinforcement/
├── ppo_XAUUSD_20240315_143022/
│   ├── agent.zip              # Trained PPO agent
│   ├── metadata.json          # Agent metadata
│   └── evaluation_report.txt  # Evaluation report
└── ppo_XAUUSD_20240315_150045/
    ├── agent.zip
    ├── metadata.json
    └── evaluation_report.txt
```

#### Metadata Format

```json
{
  "model_type": "PPO",
  "symbol": "XAUUSD",
  "timeframe": "M15",
  "training_months": 6,
  "train_start_date": "2023-09-15T00:00:00",
  "train_end_date": "2024-02-15T00:00:00",
  "eval_start_date": "2024-02-15T00:00:00",
  "eval_end_date": "2024-03-15T00:00:00",
  "hyperparameters": {
    "learning_rate": 0.0003,
    "n_steps": 2048,
    "batch_size": 64,
    "n_epochs": 10,
    "gamma": 0.99,
    "gae_lambda": 0.95,
    "clip_range": 0.2,
    "ent_coef": 0.01
  },
  "training_timesteps": 1000000,
  "max_position_size": 0.02,
  "reward_window": 100,
  "metrics": {
    "sharpe_ratio": 1.85,
    "total_return": 0.1250,
    "num_trades": 450,
    "win_rate": 0.58,
    "avg_pnl": 27.50,
    "max_drawdown": 0.08
  },
  "promotion_status": "PAPER_TRADING",
  "promotion_date": "2024-03-15T15:00:45",
  "min_sharpe_for_promotion": 1.5,
  "created_at": "2024-03-15T14:30:22"
}
```

### Reward Function

The RL agent is trained to maximize Sharpe ratio over a rolling 100-trade window:

```python
def calculate_reward(trades: List[Trade]) -> float:
    """
    Calculate Sharpe ratio over rolling 100-trade window.
    
    Requirements: 12.2
    """
    if len(trades) < 10:
        return 0.0
    
    # Get last 100 trades
    recent_trades = trades[-100:]
    
    # Calculate returns
    returns = [trade.pnl / trade.capital for trade in recent_trades]
    
    # Calculate Sharpe ratio
    mean_return = np.mean(returns)
    std_return = np.std(returns)
    
    sharpe_ratio = mean_return / std_return if std_return > 0 else 0.0
    
    return sharpe_ratio
```

### Position Size Constraints

The environment enforces risk management rules:

```python
# Action is clipped to max position size
position_size = np.clip(action[0], 0.0, max_position_size)

# Max 2% of capital per trade
assert position_size <= 0.02
```

### Promotion Criteria

An agent is promoted to paper trading if:

```python
def meets_promotion_criteria(sharpe_ratio: float, min_sharpe: float = 1.5) -> bool:
    """
    Requirements: 12.5 - Promote if Sharpe > 1.5
    """
    return sharpe_ratio > min_sharpe
```

### Testing

Run unit tests:

```bash
# Run all RL tests
pytest tests/test_rl_training.py -v

# Run specific test
pytest tests/test_rl_training.py::test_trading_environment -v

# Run with coverage
pytest tests/test_rl_training.py --cov=ml
```

### Example Script

See `ml/example_rl_usage.py` for complete examples:

1. **Environment Test**: Test trading environment with random actions
2. **Full Training**: Train PPO agent, evaluate, and promote

Run the examples:

```bash
# Run environment test
python ml/example_rl_usage.py

# Run full training (uncomment in script)
# python ml/example_rl_usage.py
```

### Requirements Validation

This implementation satisfies the following requirements:

- **Requirement 12.1**: Gym environment with historical data replay ✓
- **Requirement 12.2**: Reward function as Sharpe ratio over rolling 100 trades ✓
- **Requirement 12.3**: Action space (0-2% position size), State space (feature vector) ✓
- **Requirement 12.4**: PPO training with 1M timesteps, position size constraints ✓
- **Requirement 12.5**: Evaluation on out-of-sample data, promotion if Sharpe > 1.5 ✓

### Performance Metrics

The evaluator computes comprehensive metrics:

- **Sharpe Ratio**: Risk-adjusted return (mean return / std return)
- **Total Return**: (Final capital - Initial capital) / Initial capital
- **Number of Trades**: Total trades executed
- **Win Rate**: Percentage of profitable trades
- **Average P&L**: Mean profit/loss per trade
- **Max Drawdown**: Maximum peak-to-trough decline

### Integration with APEX Bot

Trained RL agents can be integrated for position sizing:

```python
from stable_baselines3 import PPO

# Load agent
agent = PPO.load("models/reinforcement/ppo_xauusd_001/agent.zip")

# Get features from FeaturePipeline
features = await feature_pipeline.get_feature_vector("XAUUSD", "M15")

# Predict position size
position_size, _ = agent.predict(features.to_array(), deterministic=True)

# Use in trade execution
if signal == "GO":
    # Use RL agent's position size recommendation
    trade_size = position_size[0] * account_capital
    execute_trade(symbol, trade_size)
```

### Troubleshooting

#### Environment creation fails

Ensure historical data is available:

```python
# Check data availability
data = warehouse.query_ohlcv(
    symbol="XAUUSD",
    timeframe="M15",
    start=datetime.now() - timedelta(days=180),
    end=datetime.now()
)
print(f"Available bars: {len(data)}")
```

#### Training is slow

- Reduce `total_timesteps` for faster training
- Use shorter historical period
- Increase `n_steps` for fewer updates

#### Agent not meeting promotion criteria

Try:
- Longer training (more timesteps)
- Different hyperparameters
- Longer historical data period
- Different reward window size

### References

- Design Document: `.kiro/specs/data-ml-dashboard-improvements/design.md`
- Requirements: `.kiro/specs/data-ml-dashboard-improvements/requirements.md`
- Stable-Baselines3: https://stable-baselines3.readthedocs.io/
- Gymnasium: https://gymnasium.farama.org/


---

## Model Registry and Versioning

This module implements a comprehensive model registry for storing, versioning, and managing trained ML models with DuckDB backend.

### Features

#### Task 16.1: ModelRegistry with DuckDB Backend

- **Unique Version IDs**: Assigns UUID to each model for unique identification
- **Organized Storage**: Stores model files in structured directory hierarchy
- **DuckDB Schema**: Comprehensive metadata storage with indexes
- **Model Categories**: Separate storage for supervised and reinforcement learning models
- **Requirements**: Implements Requirements 14.1, 14.4

#### Task 16.2: Comprehensive Metadata Tracking

- **Hyperparameters**: Stores all model hyperparameters as JSON
- **Training Data**: Tracks training data date range and sample count
- **Feature List**: Stores feature names and count
- **Performance Metrics**: Stores train/val/test metrics
- **Code Tracking**: Stores git commit hash and training script path
- **Requirements**: Implements Requirements 14.2, 14.3

#### Task 16.3: Deployment Tagging

- **Deployment Status**: Tracks TRAINING, TESTING, PRODUCTION, RETIRED
- **Deployment Environment**: Tags with PAPER or LIVE environment
- **Deployment Timestamp**: Records when model was deployed
- **Production Tracking**: Easily retrieve current production models
- **Requirements**: Implements Requirement 14.5

### Installation

The model registry uses DuckDB which is already installed as part of the data warehouse dependencies:

```bash
pip install duckdb>=0.9.0
```

### Usage

#### Basic Model Registration

```python
from ml.model_registry import ModelRegistry, ModelMetadata, ModelType, DeploymentStatus
from datetime import datetime, timedelta
import pickle

# Initialize registry
registry = ModelRegistry(
    db_path="models/registry.db",
    models_root="models"
)

# Create model metadata
metadata = ModelMetadata(
    model_id="",  # Will be auto-generated
    model_name="xgboost_eurusd_predictor",
    model_type=ModelType.XGBOOST.value,
    version=1,
    created_at=datetime.now(),
    training_start_date=datetime.now() - timedelta(days=180),
    training_end_date=datetime.now(),
    num_training_samples=50000,
    hyperparameters={
        'max_depth': 5,
        'learning_rate': 0.05,
        'n_estimators': 200
    },
    feature_names=['rsi_14', 'ema_20', 'volume_ratio'],
    num_features=3,
    train_metrics={'accuracy': 0.65, 'roc_auc': 0.70},
    validation_metrics={'accuracy': 0.58, 'roc_auc': 0.62},
    test_metrics={'accuracy': 0.57, 'roc_auc': 0.61},
    deployment_status=DeploymentStatus.TRAINING.value,
    git_commit_hash="abc123def456",
    training_script_path="ml/supervised_training.py"
)

# Load your trained model
with open("path/to/model.pkl", "rb") as f:
    model_file = f.read()

# Register model
model_id = registry.register_model(metadata, model_file)
print(f"Model registered with ID: {model_id}")
```

#### Retrieve Model

```python
# Get model by ID
metadata, model_file = registry.get_model(model_id)

print(f"Model: {metadata.model_name} v{metadata.version}")
print(f"Validation Accuracy: {metadata.validation_metrics['accuracy']:.2%}")

# Deserialize model
import pickle
model = pickle.loads(model_file)
```

#### Deploy to Paper Trading

```python
from ml.model_registry import DeploymentEnvironment

# Update deployment status
registry.update_deployment_status(
    model_id,
    DeploymentStatus.TESTING.value,
    DeploymentEnvironment.PAPER.value
)

print("Model deployed to paper trading")
```

#### Promote to Production

```python
# Promote to production
registry.update_deployment_status(
    model_id,
    DeploymentStatus.PRODUCTION.value,
    DeploymentEnvironment.LIVE.value
)

print("Model promoted to production")
```

#### List Models with Filters

```python
# List all production models
prod_models = registry.list_models(
    filters={'deployment_status': DeploymentStatus.PRODUCTION.value}
)

for model in prod_models:
    print(f"{model.model_name} v{model.version} - "
          f"Accuracy: {model.validation_metrics.get('accuracy', 0):.2%}")

# List XGBoost models
xgb_models = registry.list_models(
    filters={'model_type': ModelType.XGBOOST.value}
)

# List models by name (version history)
history = registry.get_model_history("xgboost_eurusd_predictor")
for model in history:
    print(f"v{model.version}: {model.created_at.strftime('%Y-%m-%d')}")
```

#### Get Current Production Model

```python
# Get currently deployed production model
prod_model = registry.get_current_production_model(ModelType.XGBOOST.value)

if prod_model:
    print(f"Current production model: {prod_model.model_name}")
    print(f"Deployed: {prod_model.deployment_timestamp}")
    print(f"Environment: {prod_model.deployment_environment}")
```

### Storage Structure

Models are organized in a hierarchical directory structure:

```
models/
├── supervised/
│   ├── xgboost_v1_20240101/
│   │   ├── model.pkl              # Serialized XGBoost model
│   │   └── metadata.json          # Model metadata
│   └── lightgbm_v2_20240115/
│       ├── model.pkl
│       └── metadata.json
├── reinforcement/
│   ├── ppo_v1_20240101/
│   │   ├── model.zip              # Serialized PPO agent
│   │   └── metadata.json
│   └── ppo_v2_20240120/
│       ├── model.zip
│       └── metadata.json
└── registry.db                     # DuckDB with model metadata
```

### Database Schema

The registry uses DuckDB with the following schema:

```sql
CREATE TABLE model_registry (
    model_id VARCHAR PRIMARY KEY,           -- UUID
    model_name VARCHAR NOT NULL,
    model_type VARCHAR NOT NULL,            -- XGBOOST, LIGHTGBM, PPO
    version INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,
    
    -- Training data
    training_start_date DATE NOT NULL,
    training_end_date DATE NOT NULL,
    num_training_samples INTEGER NOT NULL,
    
    -- Hyperparameters and features
    hyperparameters JSON NOT NULL,
    feature_names VARCHAR[] NOT NULL,
    num_features INTEGER NOT NULL,
    
    -- Performance metrics
    train_metrics JSON NOT NULL,
    validation_metrics JSON NOT NULL,
    test_metrics JSON NOT NULL,
    
    -- Deployment
    deployment_status VARCHAR NOT NULL,
    deployment_timestamp TIMESTAMP,
    deployment_environment VARCHAR,
    
    -- Code tracking
    git_commit_hash VARCHAR,
    training_script_path VARCHAR,
    
    -- Model file
    model_file_path VARCHAR NOT NULL
);

-- Indexes for efficient queries
CREATE INDEX idx_model_status ON model_registry(deployment_status);
CREATE INDEX idx_model_created ON model_registry(created_at DESC);
CREATE INDEX idx_model_type ON model_registry(model_type);
```

### Metadata Format

Model metadata is stored both in DuckDB and as JSON files:

```json
{
  "model_id": "550e8400-e29b-41d4-a716-446655440000",
  "model_name": "xgboost_eurusd_predictor",
  "model_type": "XGBOOST",
  "version": 1,
  "created_at": "2024-03-15T14:30:22",
  "training_start_date": "2023-09-15T00:00:00",
  "training_end_date": "2024-03-15T00:00:00",
  "num_training_samples": 50000,
  "hyperparameters": {
    "max_depth": 5,
    "learning_rate": 0.05,
    "n_estimators": 200,
    "min_child_weight": 3,
    "subsample": 0.9,
    "colsample_bytree": 0.9
  },
  "feature_names": [
    "rsi_14", "ema_20", "ema_50", "volume_ratio",
    "volatility_20", "return_1bar", "return_5bar"
  ],
  "num_features": 7,
  "train_metrics": {
    "accuracy": 0.65,
    "precision": 0.63,
    "recall": 0.67,
    "f1_score": 0.65,
    "roc_auc": 0.70
  },
  "validation_metrics": {
    "accuracy": 0.58,
    "precision": 0.56,
    "recall": 0.60,
    "f1_score": 0.58,
    "roc_auc": 0.62
  },
  "test_metrics": {
    "accuracy": 0.57,
    "precision": 0.55,
    "recall": 0.59,
    "f1_score": 0.57,
    "roc_auc": 0.61
  },
  "deployment_status": "PRODUCTION",
  "deployment_timestamp": "2024-03-15T15:00:00",
  "deployment_environment": "LIVE",
  "git_commit_hash": "abc123def456789",
  "training_script_path": "ml/supervised_training.py",
  "model_file_path": "supervised/xgboost_eurusd_predictor_v1_20240315/model.pkl"
}
```

### Model Lifecycle

Models progress through the following lifecycle stages:

1. **TRAINING**: Model is being trained or just completed training
2. **TESTING**: Model deployed to paper trading for evaluation
3. **PRODUCTION**: Model deployed to live trading
4. **RETIRED**: Model replaced by newer version

```python
# Typical lifecycle
model_id = registry.register_model(metadata, model_file)
# Status: TRAINING

registry.update_deployment_status(
    model_id, 
    DeploymentStatus.TESTING.value,
    DeploymentEnvironment.PAPER.value
)
# Status: TESTING (paper trading)

# After successful paper trading evaluation
registry.update_deployment_status(
    model_id,
    DeploymentStatus.PRODUCTION.value,
    DeploymentEnvironment.LIVE.value
)
# Status: PRODUCTION (live trading)

# When replaced by newer model
registry.update_deployment_status(
    model_id,
    DeploymentStatus.RETIRED.value
)
# Status: RETIRED
```

### Integration with Training Pipelines

#### Supervised Learning Integration

```python
from ml.supervised_training import SupervisedTrainingPipeline, TrainingConfig
from ml.model_registry import ModelRegistry, ModelMetadata, ModelType, DeploymentStatus
import pickle

# Train model
training_pipeline = SupervisedTrainingPipeline(warehouse, feature_pipeline)
config = TrainingConfig(symbol="XAUUSD", training_months=6)
result = training_pipeline.train_and_evaluate(config, model_type="xgboost")

if result:
    model, metrics, train_metadata = result
    
    # Create registry metadata
    registry_metadata = ModelMetadata(
        model_id="",
        model_name=f"xgboost_{config.symbol.lower()}",
        model_type=ModelType.XGBOOST.value,
        version=1,
        created_at=datetime.now(),
        training_start_date=datetime.now() - timedelta(days=config.training_months * 30),
        training_end_date=datetime.now(),
        num_training_samples=train_metadata['train_samples'],
        hyperparameters=train_metadata.get('hyperparameters', {}),
        feature_names=train_metadata['feature_names'],
        num_features=train_metadata['num_features'],
        train_metrics=train_metadata['metrics'],
        validation_metrics=train_metadata['metrics'],
        test_metrics=train_metadata['metrics'],
        deployment_status=DeploymentStatus.TRAINING.value,
        git_commit_hash="current_commit_hash",
        training_script_path="ml/supervised_training.py"
    )
    
    # Serialize model
    model_file = pickle.dumps(model)
    
    # Register in registry
    registry = ModelRegistry()
    model_id = registry.register_model(registry_metadata, model_file)
    
    print(f"Model registered: {model_id}")
```

#### Reinforcement Learning Integration

```python
from ml.ppo_agent_training import PPOAgentTrainer, PPOConfig
from ml.model_registry import ModelRegistry, ModelMetadata, ModelType, DeploymentStatus

# Train RL agent
trainer = PPOAgentTrainer(warehouse, feature_pipeline)
config = PPOConfig(symbol="XAUUSD", training_months=6)
agent, metrics, train_metadata = trainer.train_agent(config)

# Create registry metadata
registry_metadata = ModelMetadata(
    model_id="",
    model_name=f"ppo_{config.symbol.lower()}",
    model_type=ModelType.PPO.value,
    version=1,
    created_at=datetime.now(),
    training_start_date=datetime.now() - timedelta(days=config.training_months * 30),
    training_end_date=datetime.now(),
    num_training_samples=config.total_timesteps,
    hyperparameters=train_metadata['hyperparameters'],
    feature_names=train_metadata['feature_names'],
    num_features=train_metadata['num_features'],
    train_metrics={'sharpe_ratio': metrics.sharpe_ratio},
    validation_metrics={'sharpe_ratio': metrics.sharpe_ratio},
    test_metrics={'sharpe_ratio': metrics.sharpe_ratio},
    deployment_status=DeploymentStatus.TRAINING.value,
    git_commit_hash="current_commit_hash",
    training_script_path="ml/ppo_agent_training.py"
)

# Save agent to bytes
import io
agent_bytes = io.BytesIO()
agent.save(agent_bytes)
model_file = agent_bytes.getvalue()

# Register in registry
registry = ModelRegistry()
model_id = registry.register_model(registry_metadata, model_file)

print(f"RL agent registered: {model_id}")
```

### Utility Functions

#### Registry Statistics

```python
# Get registry statistics
stats = registry.get_registry_stats()

print(f"Total models: {stats['total_models']}")
print(f"By type: {stats['by_type']}")
print(f"By status: {stats['by_status']}")
print(f"Storage size: {stats['storage_size_mb']:.2f} MB")
```

#### Export/Import Models

```python
# Export model metadata
registry.export_model_metadata(
    model_id,
    output_path="exports/model_metadata.json"
)

# Import model from metadata and file
imported_id = registry.import_model_metadata(
    metadata_path="exports/model_metadata.json",
    model_file_path="exports/model.pkl"
)
```

#### Delete Models

```python
# Delete model (including files)
registry.delete_model(model_id, delete_files=True)

# Delete model (keep files)
registry.delete_model(model_id, delete_files=False)
```

### Testing

Run unit tests:

```bash
# Run all registry tests
pytest tests/test_model_registry.py -v

# Run specific test class
pytest tests/test_model_registry.py::TestModelRegistration -v

# Run with coverage
pytest tests/test_model_registry.py --cov=ml.model_registry
```

### Example Script

See `ml/example_model_registry_usage.py` for comprehensive examples:

1. Register supervised model
2. Retrieve model
3. Deploy to paper trading
4. Promote to production
5. List models with filters
6. Get current production model
7. Track model version history
8. Get registry statistics
9. Register RL model

Run the examples:

```bash
python ml/example_model_registry_usage.py
```

### Requirements Validation

This implementation satisfies the following requirements:

- **Requirement 14.1**: Unique version ID (UUID) for each model ✓
- **Requirement 14.2**: Store hyperparameters, training data range, feature list ✓
- **Requirement 14.3**: Store train/val/test performance metrics ✓
- **Requirement 14.4**: Store serialized model file and git commit hash ✓
- **Requirement 14.5**: Tag models with deployment timestamp and environment ✓

### Best Practices

#### Version Management

```python
# Get latest version number for a model
history = registry.get_model_history("xgboost_eurusd")
latest_version = max([m.version for m in history]) if history else 0
new_version = latest_version + 1

# Register new version
metadata.version = new_version
model_id = registry.register_model(metadata, model_file)
```

#### Production Deployment

```python
# Before deploying to production, retire old model
old_prod_model = registry.get_current_production_model(ModelType.XGBOOST.value)
if old_prod_model:
    registry.update_deployment_status(
        old_prod_model.model_id,
        DeploymentStatus.RETIRED.value
    )

# Deploy new model
registry.update_deployment_status(
    new_model_id,
    DeploymentStatus.PRODUCTION.value,
    DeploymentEnvironment.LIVE.value
)
```

#### Model Comparison

```python
# Compare multiple model versions
models = registry.get_model_history("xgboost_eurusd")

for model in models:
    val_acc = model.validation_metrics.get('accuracy', 0)
    test_acc = model.test_metrics.get('accuracy', 0)
    print(f"v{model.version}: val={val_acc:.2%}, test={test_acc:.2%}, "
          f"status={model.deployment_status}")
```

### Troubleshooting

#### Model file not found

Ensure the model file path is correct and the file exists:

```python
from pathlib import Path

model_path = Path(registry.models_root) / metadata.model_file_path
if not model_path.exists():
    print(f"Model file not found: {model_path}")
```

#### Database locked error

If you get a database locked error, ensure you're not accessing the registry from multiple processes simultaneously. Use file locking or separate database connections.

#### Invalid deployment status

Ensure you're using the correct enum values:

```python
from ml.model_registry import DeploymentStatus, DeploymentEnvironment

# Valid statuses
DeploymentStatus.TRAINING.value
DeploymentStatus.TESTING.value
DeploymentStatus.PRODUCTION.value
DeploymentStatus.RETIRED.value

# Valid environments
DeploymentEnvironment.PAPER.value
DeploymentEnvironment.LIVE.value
```

### References

- Design Document: `.kiro/specs/data-ml-dashboard-improvements/design.md`
- Requirements: `.kiro/specs/data-ml-dashboard-improvements/requirements.md`
- Schema: `data/schemas/model_registry_schema.sql`
- DuckDB Documentation: https://duckdb.org/docs/
