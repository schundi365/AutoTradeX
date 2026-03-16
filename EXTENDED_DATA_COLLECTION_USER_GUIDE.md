# Extended Historical Data Collection - User Guide

## Quick Start

### One-Click Collection (Recommended)

1. Start the dashboard:
   ```powershell
   .\start-apex.ps1
   ```

2. Navigate to **Model Training** tab

3. Scroll to **"📊 EXTENDED DATA COLLECTION"** panel

4. Click **"🚀 COLLECT ALL (2 YEARS)"** for standard ML training

5. Wait 5-15 minutes for completion (progress bar shows status)

6. Verify data coverage in the table below

That's it! You now have 2 years of historical data ready for ML model training.

## Detailed Usage

### Understanding the Panel

The Extended Data Collection panel has three main sections:

#### 1. Quick Actions
- **COLLECT ALL (2 YEARS)**: Collects 2 years of data for all configured symbols (XAUUSD, BTCUSD, EURUSD, etc.)
- **COLLECT ALL (3 YEARS)**: Collects 3 years of data for more comprehensive training

#### 2. Custom Collection
- **Symbol**: Choose specific symbol to collect
- **Years**: Select 1-5 years of history
- **Timeframe**: Choose data granularity (15m, 30m, 1h, 2h, 4h, 1d)
- **COLLECT**: Start collection for selected parameters

#### 3. Data Coverage Status
- Shows current data availability for each symbol
- **Bars**: Number of data points collected
- **Coverage**: Time span in years
- **Status**: 
  - ✓ (Green) = Ready for ML training (10,000+ bars)
  - ⚠ (Amber) = Low data (5,000-10,000 bars)
  - ✗ (Red) = Insufficient data (<5,000 bars)

### Collection Strategies

#### Strategy 1: Quick Start (Recommended for Beginners)
```
1. Click "COLLECT ALL (2 YEARS)"
2. Wait for completion
3. Start training models
```
**Time**: 5-10 minutes  
**Data**: ~17,000 bars per symbol (1h timeframe)  
**Best for**: Getting started quickly

#### Strategy 2: Comprehensive Training (Recommended for Production)
```
1. Click "COLLECT ALL (3 YEARS)"
2. Wait for completion
3. Optionally collect 4h timeframe for longer-term strategies
4. Start training models
```
**Time**: 10-15 minutes  
**Data**: ~26,000 bars per symbol (1h timeframe)  
**Best for**: Production-ready models with better generalization

#### Strategy 3: Custom Per-Symbol
```
1. Select symbol (e.g., XAUUSD)
2. Choose years (e.g., 3)
3. Choose timeframe (e.g., 1h)
4. Click COLLECT
5. Repeat for other symbols as needed
```
**Time**: 2-3 minutes per symbol  
**Best for**: Targeted data collection or testing

### Timeframe Selection Guide

| Timeframe | Bars/Year | Use Case | Training Time |
|-----------|-----------|----------|---------------|
| 15m | ~35,000 | Scalping, high-frequency | Longer |
| 30m | ~17,500 | Intraday trading | Medium |
| **1h** | **~8,760** | **Day trading (recommended)** | **Fast** |
| 2h | ~4,380 | Swing trading | Fast |
| 4h | ~2,190 | Position trading | Very fast |
| 1d | ~365 | Long-term investing | Very fast |

**Recommendation**: Start with **1h timeframe** for best balance of data volume and training speed.

### Monitoring Progress

#### Progress Bar
- Shows real-time collection progress
- Updates every 5 seconds
- Displays current symbol being processed

#### Bot Logs
- Scroll down to "BOT LOGS" section
- Look for lines with `[AI]` tag
- Shows detailed collection status

#### Data Coverage Table
- Automatically refreshes after collection
- Click "↻ REFRESH" to manually update
- Shows bars collected and time coverage

### What Happens During Collection

1. **Daily Data Fetch**: Downloads daily OHLCV data for full history (no 60-day limit)
2. **Resampling**: Converts daily data to your chosen timeframe (e.g., 1h)
3. **Intraday Backfill**: Fetches recent intraday data (last 60 days) for accuracy
4. **Smart Merging**: Combines datasets, preferring intraday for recent data
5. **DuckDB Storage**: Saves to efficient columnar database
6. **Verification**: Checks data quality and coverage

### After Collection

#### Verify Data Coverage

Check the Data Coverage Status table:

```
Symbol    TF   Bars      Coverage    Status
XAUUSD    1h   17,520    2.0 years   ✓ Ready
BTCUSD    1h   15,840    1.8 years   ✓ Ready
EURUSD    1h   8,760     1.0 years   ⚠ Low
```

**What to do if status is ⚠ or ✗:**
1. Select the symbol in Custom Collection
2. Increase years to 2 or 3
3. Click COLLECT
4. Wait for completion

#### Next Steps

Once you have ✓ Ready status for your symbols:

1. **Export Training Data**:
   - Scroll to "3. EXPORT JSONL" section
   - Click "REPLAY" to generate training examples
   - Wait for completion

2. **Train Models**:
   - Navigate to "ML Training" section
   - Click "Train Supervised Model" or "Train RL Agent"
   - Monitor training progress

3. **Fine-tune LLM** (Optional):
   - Scroll to "4. FINE-TUNING" section
   - Click "⚡ LOCAL" or "☁ KAGGLE"
   - Wait for fine-tuning to complete

## Daily Incremental Updates (Coming Soon)

Future feature will allow:
- Automatic daily data collection at 00:00 UTC
- Only fetches new data since last collection (fast, <1 minute)
- Keeps training data fresh without manual intervention

## Troubleshooting

### "No data returned" Error

**Cause**: Symbol not available in yfinance or network issue

**Solution**:
1. Check internet connection
2. Try different symbol
3. Check `yfinance_symbols` mapping in config
4. Wait a few minutes and retry

### "Insufficient data" Warning

**Cause**: Less than 10,000 bars collected

**Solution**:
1. Increase years parameter (try 3 or 4 years)
2. Use longer timeframe (4h or 1d)
3. Check if symbol has limited history

### Collection Stuck or Slow

**Cause**: Network issues or rate limiting

**Solution**:
1. Wait patiently (can take 10-15 minutes for all symbols)
2. Check bot logs for errors
3. Try collecting symbols one at a time
4. Restart dashboard and retry

### Data Gaps in Coverage

**Cause**: Market closures (weekends, holidays)

**Solution**: This is normal behavior. ML models handle gaps automatically.

### Progress Bar Not Updating

**Cause**: Browser not polling status

**Solution**:
1. Check browser console for errors
2. Refresh the page
3. Check bot logs for actual progress
4. Collection may still be running in background

## Data Requirements for ML Training

### Minimum Requirements
- **Bars**: 10,000+ per symbol/timeframe
- **Time Coverage**: 1-2 years minimum
- **Timeframe**: 1h recommended

### Recommended for Best Results
- **Bars**: 15,000-20,000+ per symbol/timeframe
- **Time Coverage**: 2-3 years
- **Timeframe**: 1h or 4h

### Why More Data is Better

1. **Better Generalization**: Models learn from more market conditions
2. **Reduced Overfitting**: More diverse examples prevent memorization
3. **Regime Coverage**: Captures bull, bear, and sideways markets
4. **Event Coverage**: Includes various economic events and crises
5. **Statistical Significance**: More data = more reliable patterns

## Storage and Performance

### Storage Requirements
- **Per Symbol**: ~10MB per 10,000 bars
- **2 Years, 5 Symbols**: ~50-100MB total
- **3 Years, 10 Symbols**: ~150-200MB total

### Collection Speed
- **Single Symbol**: 2-3 minutes
- **All Symbols (2 years)**: 5-10 minutes
- **All Symbols (3 years)**: 10-15 minutes

### Query Performance
- **1 Year of Data**: <100ms
- **3 Years of Data**: <200ms
- **Full Dataset**: <500ms

## Advanced Usage

### Collecting Multiple Timeframes

For comprehensive strategies, collect multiple timeframes:

```
1. Collect 1h data (2 years) for all symbols
2. Collect 4h data (3 years) for all symbols
3. Collect 1d data (5 years) for all symbols
```

This allows:
- Multi-timeframe analysis
- Different trading strategies
- Better model ensemble

### Verifying Data Quality

After collection, verify data quality:

```powershell
# Check data coverage
python scripts/check_historical_data.py

# Check specific symbol
python scripts/check_historical_data.py --symbol XAUUSD

# Check database
python scripts/check_historical_data.py --db data/apex.db
```

### Manual Collection (Command Line)

For advanced users, collect data via command line:

```powershell
# Collect 2 years for all symbols
python scripts/collect_extended_historical_data.py --all-symbols --years 2 --timeframe 1h

# Collect 3 years for specific symbol
python scripts/collect_extended_historical_data.py --symbol XAUUSD --years 3 --timeframe 1h

# Collect with custom timeframe
python scripts/collect_extended_historical_data.py --symbol BTCUSD --years 2 --timeframe 4h
```

## Best Practices

### 1. Start with Standard Collection
- Use "COLLECT ALL (2 YEARS)" first
- Verify data coverage
- Start training models
- Collect more data if needed

### 2. Monitor Progress
- Watch progress bar
- Check bot logs
- Verify data coverage table

### 3. Verify Before Training
- Ensure all symbols have ✓ Ready status
- Check bars count (should be 10,000+)
- Verify time coverage (should be 1.5+ years)

### 4. Incremental Collection
- Collect basic data first (2 years, 1h)
- Add more years if model performance is poor
- Add different timeframes for multi-timeframe strategies

### 5. Regular Updates
- Re-collect data monthly to include recent market conditions
- Update training data before retraining models
- Keep data fresh for best model performance

## FAQ

**Q: How much data do I need for ML training?**  
A: Minimum 10,000 bars (1-2 years). Recommended 15,000-20,000 bars (2-3 years).

**Q: Which timeframe should I use?**  
A: Start with 1h for best balance. Use 4h for longer-term strategies.

**Q: How long does collection take?**  
A: 5-10 minutes for all symbols (2 years), 10-15 minutes for 3 years.

**Q: Can I collect data while bot is trading?**  
A: Yes, collection runs in background and doesn't affect trading.

**Q: What if collection fails?**  
A: Check bot logs for errors, verify internet connection, and retry.

**Q: Do I need to collect data for all symbols?**  
A: No, collect only for symbols you plan to trade.

**Q: How often should I update data?**  
A: Monthly updates recommended, or before retraining models.

**Q: Can I collect more than 3 years?**  
A: Yes, use Custom Collection and select up to 5 years.

**Q: What if a symbol shows ⚠ Low status?**  
A: Increase years to 2-3 or use longer timeframe (4h, 1d).

**Q: Is the data stored locally?**  
A: Yes, in `data/apex.db` (DuckDB) and `data/raw/` (CSV backups).

## Summary

The Extended Data Collection feature provides:

✅ One-click bulk collection  
✅ Custom symbol/timeframe selection  
✅ Real-time progress monitoring  
✅ Data coverage visualization  
✅ Efficient storage and fast queries  
✅ Ready for ML model training  

**Recommended Workflow**:
1. Click "COLLECT ALL (2 YEARS)"
2. Wait 5-10 minutes
3. Verify ✓ Ready status
4. Start training models

For questions or issues, check bot logs or refer to troubleshooting section above.
