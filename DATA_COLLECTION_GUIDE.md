# Historical Data Collection Guide

## Problem: Insufficient Data for ML Training

Yahoo Finance limits intraday data:
- **15m/30m data**: Last 60 days only (~3,600 bars)
- **1h data**: Last 730 days (~17,500 bars)
- **Daily data**: Unlimited history

For ML training, you need **10,000+ bars** (ideally 1-2 years of history).

## Solution: Extended Data Collector

The extended collector solves this by:
1. Fetching daily data for full history (2+ years)
2. Resampling to your target timeframe (15m, 1h, etc.)
3. Fetching recent intraday data for accuracy
4. Merging both datasets

### Quick Start

```powershell
# Collect 2 years of XAUUSD data at 15m timeframe
python scripts/collect_extended_historical_data.py --symbol XAUUSD --years 2 --timeframe 15m

# Collect for all configured symbols
python scripts/collect_extended_historical_data.py --all-symbols --years 2 --timeframe 15m

# Use 1h timeframe (more accurate, more data available)
python scripts/collect_extended_historical_data.py --symbol XAUUSD --years 2 --timeframe 1h
```

### Expected Results

**15m timeframe (2 years)**:
- ~35,000 bars (resampled from daily + recent intraday)
- Sufficient for training XGBoost/LightGBM models
- Sufficient for RL training (1M timesteps)

**1h timeframe (2 years)**:
- ~17,500 bars (actual intraday data from Yahoo)
- Higher quality data (not resampled)
- Recommended for production models

### Verify Data Coverage

```powershell
# Check all collected data
python scripts/check_historical_data.py

# Check specific symbol
python scripts/check_historical_data.py --symbol XAUUSD

# Check DuckDB only
python scripts/check_historical_data.py --skip-csv
```

## Data Collection Options

### Option 1: Extended Collector (Recommended)

**Best for**: 15m/30m timeframes where Yahoo limits apply

```powershell
python scripts/collect_extended_historical_data.py --symbol XAUUSD --years 2 --timeframe 15m
```

**Pros**:
- Gets 2+ years of data
- Combines daily resampling + recent intraday
- Sufficient for ML training

**Cons**:
- Resampled data (less accurate than true intraday)
- Daily bars resampled to 15m may miss intraday volatility

### Option 2: Standard Collector with 1h Timeframe

**Best for**: When you can use 1h or 4h timeframes

```powershell
python scripts/collect_historical_data.py --source yfinance --tf 1h
```

**Pros**:
- True intraday data (not resampled)
- 2 years of actual 1h bars available
- Higher quality for ML training

**Cons**:
- Limited to 1h or longer timeframes
- Can't get 15m/30m data beyond 60 days

### Option 3: Crypto via CCXT (Binance)

**Best for**: Crypto symbols (BTC, ETH, etc.)

```powershell
python scripts/collect_historical_data.py --source ccxt --symbol BTC/USDT --tf 15m
```

**Pros**:
- Full history available (years of 15m data)
- True intraday data
- No Yahoo Finance limitations

**Cons**:
- Only works for crypto
- Requires exchange API access

## Recommended Workflow

### For Forex/Metals (XAUUSD, EURUSD, etc.)

```powershell
# Step 1: Collect extended data (2 years, 1h timeframe recommended)
python scripts/collect_extended_historical_data.py --symbol XAUUSD --years 2 --timeframe 1h

# Step 2: Verify coverage
python scripts/check_historical_data.py --symbol XAUUSD

# Step 3: Train models
python ml/example_training_usage.py
```

### For Crypto (BTC, ETH, etc.)

```powershell
# Step 1: Collect via CCXT (full history available)
python scripts/collect_historical_data.py --source ccxt --symbol BTC/USDT --tf 15m

# Step 2: Verify coverage
python scripts/check_historical_data.py --symbol BTCUSDT

# Step 3: Train models
python ml/example_training_usage.py
```

### For All Symbols

```powershell
# Collect 2 years for all configured symbols
python scripts/collect_extended_historical_data.py --all-symbols --years 2 --timeframe 1h

# Verify all
python scripts/check_historical_data.py

# Train models
python ml/example_training_usage.py
```

## Training Configuration

Update `core/config.py` or `.env` to match your collected data:

```python
# In TrainingConfig
yfinance_timeframe: str = "1h"  # Match your collected timeframe
training_months: int = 24        # 2 years = 24 months
```

## Troubleshooting

### "No data returned for symbol"

**Cause**: Invalid ticker or symbol not in yfinance_symbols config

**Solution**: Check `core/config.py` → `TrainingConfig.yfinance_symbols`

### "Insufficient data for training"

**Cause**: Less than 10,000 bars collected

**Solution**: 
- Increase `--years` parameter (try 3 years)
- Use longer timeframe (1h instead of 15m)
- For crypto, use CCXT collector

### "Error resampling data"

**Cause**: Invalid timeframe specified

**Solution**: Use supported timeframes: 15m, 30m, 1h, 2h, 4h, 1d

### Data has gaps

**Cause**: Market closed periods (weekends, holidays)

**Solution**: This is normal. ML models handle gaps automatically.

## Data Quality Tips

1. **Use 1h timeframe when possible**: More accurate than resampled 15m
2. **Collect 2+ years**: More data = better model performance
3. **Verify before training**: Always run `check_historical_data.py`
4. **Update regularly**: Re-collect data monthly to include recent market conditions
5. **Test on recent data**: Use last 20% for validation (walk-forward)

## Next Steps

After collecting sufficient data:

1. **Verify coverage**: `python scripts/check_historical_data.py`
2. **Train supervised models**: `python ml/example_training_usage.py`
3. **Train RL agents**: `python ml/example_rl_usage.py`
4. **Monitor model performance**: Check dashboard → Model Training tab
