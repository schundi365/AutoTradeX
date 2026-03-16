# Ollama Fine-Tuned Model Setup Guide

## Current Configuration ✅

Your LLM fallback chain is correctly configured:

```
1. 🥇 Ollama (Local Fine-Tuned) - PRIMARY
   ↓ (only if fails)
2. 🥈 Groq (Fast Cloud)
   ↓ (only if fails)
3. 🥉 DeepSeek (Backup Cloud)
   ↓ (only if fails)
4. 🏅 Claude Haiku (Final Fallback)
```

## Verification Steps

### 1. Check Your Environment Variables

Make sure your `.env` file has:

```bash
# Local Ollama (PRIMARY)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=apex-trader

# Backup APIs (only used if Ollama fails)
GROQ_API_KEY=gsk_your_key_here
DEEPSEEK_API_KEY=sk_your_key_here
ANTHROPIC_API_KEY=sk-ant_your_key_here
```

### 2. Verify Ollama is Running

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# If not running, start it
ollama serve
```

### 3. Verify Your Model is Loaded

```bash
# List available models
ollama list

# Should show something like:
# NAME            ID              SIZE    MODIFIED
# apex-trader     abc123def456    4.7 GB  2 hours ago

# If not listed, load it
ollama run apex-trader
```

### 4. Run the Test Script

```bash
python test_ollama_connection.py
```

This will:
- ✅ Check Ollama server connection
- ✅ Verify your model exists
- ✅ Test inference speed and quality
- ✅ Test the LLM client integration

## Expected Test Output

```
============================================================
APEX Trading Bot - Ollama Connection Test
============================================================

📋 Configuration:
   Ollama URL: http://localhost:11434
   Model Name: apex-trader

🔍 Test 1: Checking Ollama server...
   ✅ Ollama server is running
   📦 Available models: 3
      - apex-trader (4.70 GB)
      - llama3:latest (4.66 GB)
      - mistral:latest (4.11 GB)

🔍 Test 2: Checking for model 'apex-trader'...
   ✅ Model 'apex-trader' found!

🔍 Test 3: Testing inference with 'apex-trader'...
   ⏳ Sending test prompt...
   ✅ Inference successful!
   📊 Performance:
      - Tokens generated: 156
      - Time taken: 2.34s
      - Speed: 66.7 tokens/sec

   📝 Model Response:
   --------------------------------------------------------
   SIGNAL: BUY
   
   REASONING:
   - Strong bullish momentum confirmed by RSI at 68
   - MACD bullish crossover indicates trend continuation
   - Uptrend alignment across H1 and H4 timeframes
   - Above-average volume supports the move
   
   ENTRY: 2650.50
   SL: 2642.00 (ATR-based)
   TP: 2665.00 (R:R 1.8:1)
   --------------------------------------------------------

🔍 Test 4: Testing APEX LLM Client...
   ✅ LLM Client working!
   📝 Response: I am APEX, a professional trading analyst...

============================================================
Test Summary:
============================================================
   Ollama Connection: ✅ PASS
   LLM Client:        ✅ PASS

🎉 All tests passed! Your fine-tuned model is ready.
```

## How the Fallback Works

### Normal Operation (Ollama Working):
```python
# Every LLM call tries Ollama first
result = await call_llm(
    system="You are a trading analyst",
    user="Analyze XAUUSD",
    agent="market_analyst"
)

# Log output:
# [market_analyst] 🤖 LLM Tier 1 (Ollama/apex-trader) ✓
```

### When Ollama is Down:
```python
# Automatically falls back to Groq
# Log output:
# [market_analyst] Ollama unavailable (Connection refused) → falling back to Groq
# [market_analyst] 🤖 LLM Tier 2 (Groq) ✓
```

### When Groq is Rate Limited:
```python
# Skips Groq, goes to DeepSeek
# Log output:
# [market_analyst] Groq rate limited, skipping to DeepSeek
# [market_analyst] 🤖 LLM Tier 3 (DeepSeek) ✓
```

## Performance Optimization

### 1. Keep Model in Memory
```bash
# Load model into memory (stays loaded)
ollama run apex-trader

# Or set in Ollama config to keep loaded
# ~/.ollama/config.json
{
  "keep_alive": "24h"
}
```

### 2. Adjust Timeout if Needed
If your model is slower, increase timeout in `llm/client.py`:

```python
# Current setting
OLLAMA_TIMEOUT = float(getattr(settings, "llm_timeout_seconds", 8))

# In your .env, add:
LLM_TIMEOUT_SECONDS=15  # Increase if needed
```

### 3. Monitor Performance
Watch logs for inference times:
```bash
tail -f logs/apex_*.log | grep "LLM Tier"
```

## Troubleshooting

### Issue: "Ollama unavailable (Connection refused)"

**Solution:**
```bash
# Start Ollama server
ollama serve

# Or on Windows, start Ollama app
# It should run in system tray
```

### Issue: "Model 'apex-trader' not found"

**Solution:**
```bash
# Check available models
ollama list

# If model exists with different name, update .env:
OLLAMA_MODEL=your-actual-model-name

# If model doesn't exist, you need to create/import it
# See "Creating Your Fine-Tuned Model" section below
```

### Issue: "Inference timeout (8s)"

**Solution:**
```bash
# Option 1: Increase timeout in .env
LLM_TIMEOUT_SECONDS=15

# Option 2: Use smaller/faster model
# Option 3: Use GPU acceleration (if available)
```

### Issue: Bot using Groq instead of Ollama

**Check logs for reason:**
```bash
grep "Ollama" logs/apex_*.log

# Common reasons:
# - Ollama not running
# - Model not loaded
# - Timeout too short
# - Wrong model name in .env
```

## Creating Your Fine-Tuned Model

If you haven't created your fine-tuned model yet:

### Option 1: From GGUF File
```bash
# If you have apex-trader.gguf file
ollama create apex-trader -f models/apex-trader.Modelfile

# Modelfile content:
# FROM ./apex-trader.gguf
# PARAMETER temperature 0.1
# PARAMETER num_predict 512
```

### Option 2: From Training Pipeline
```bash
# Run the training pipeline
python -m training.pipeline

# This will:
# 1. Collect training data
# 2. Fine-tune the model
# 3. Convert to GGUF
# 4. Import to Ollama
```

### Option 3: From HuggingFace
```bash
# If you have model on HuggingFace
ollama pull your-username/apex-trader
```

## Monitoring in Production

### Check Which Tier is Being Used
```bash
# Real-time monitoring
tail -f logs/apex_*.log | grep "LLM Tier"

# Count usage by tier
grep "LLM Tier" logs/apex_*.log | sort | uniq -c

# Example output:
#  1247 [agent] 🤖 LLM Tier 1 (Ollama/apex-trader) ✓
#    12 [agent] 🤖 LLM Tier 2 (Groq) ✓
#     3 [agent] 🤖 LLM Tier 3 (DeepSeek) ✓
```

### Performance Metrics
```bash
# Check Ollama stats
curl http://localhost:11434/api/ps

# Monitor system resources
# CPU/RAM usage when Ollama is running
```

## Best Practices

### 1. Always Keep Ollama as Primary ✅
- Fastest response time (no network latency)
- No API costs
- No rate limits
- Your fine-tuned model knows your trading style

### 2. Keep Backup APIs Configured ✅
- Ensures zero downtime
- Handles edge cases (Ollama crash, system restart)
- Automatic recovery

### 3. Monitor Tier Usage ✅
- Should see 95%+ Tier 1 (Ollama) usage
- If seeing lots of Tier 2/3, investigate why Ollama is failing

### 4. Regular Model Updates ✅
- Retrain model weekly/monthly with new data
- Test new model before deploying
- Keep previous version as backup

## Configuration Summary

Your current setup is **CORRECT** ✅

```python
# llm/client.py - Tier order
1. Ollama (PRIMARY) - 8s timeout
2. Groq (BACKUP)    - 10s timeout  
3. DeepSeek (BACKUP) - 12s timeout
4. Claude (FINAL)    - 15s timeout

# .env configuration
OLLAMA_BASE_URL=http://localhost:11434  ✅
OLLAMA_MODEL=apex-trader                ✅
GROQ_API_KEY=gsk_...                    ✅ (backup)
DEEPSEEK_API_KEY=sk_...                 ✅ (backup)
ANTHROPIC_API_KEY=sk-ant_...            ✅ (backup)
```

## Next Steps

1. **Run the test script:**
   ```bash
   python test_ollama_connection.py
   ```

2. **Start the bot:**
   ```bash
   python main.py
   ```

3. **Monitor logs:**
   ```bash
   tail -f logs/apex_*.log | grep "LLM Tier"
   ```

4. **Verify Ollama is primary:**
   - Should see: `[agent] 🤖 LLM Tier 1 (Ollama/apex-trader) ✓`
   - Should NOT see Tier 2/3/4 unless Ollama fails

Your fine-tuned model is correctly configured as the primary LLM! 🎉
