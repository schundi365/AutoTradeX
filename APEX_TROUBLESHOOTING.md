# APEX Bot - Troubleshooting Matrix

## Quick Diagnostic Commands

### Check if bot is running:
```powershell
curl http://localhost:8000/api/status
```

### Check recent logs:
```powershell
Get-Content logs\apex_*.log -Wait -Tail 50
```

### Check for errors:
```powershell
Select-String -Path logs\apex_*.log -Pattern "ERROR" | Select-Object -Last 20
```

---

## Common Issues & Solutions

### ISSUE: Bot not starting

**Symptoms:**
- Dashboard shows "Bot Status: STOPPED"
- No logs being generated
- API returns bot_running: false

**Diagnostic Steps:**
1. Check if API server is running:
   ```powershell
   curl http://localhost:8000/api/status
   ```

2. Check for startup errors:
   ```powershell
   Select-String -Path logs\apex_*.log -Pattern "ERROR|CRITICAL" | Select-Object -Last 10
   ```

3. Check .env file has all required keys:
   ```powershell
   Get-Content .env | Select-String -Pattern "MT5_LOGIN|GROQ_API_KEY|OLLAMA"
   ```

**Solutions:**
- Verify .env has MT5_LOGIN, MT5_PASSWORD, MT5_SERVER
- Check Ollama is running: curl http://localhost:11434/api/tags
- Restart API server: python main.py
- Check MT5 terminal is installed and path is correct

---

### ISSUE: No trades executing

**Symptoms:**
- Bot running but no trades placed
- Signals generated but rejected
- Dashboard shows 0 open trades

**Diagnostic Steps:**
1. Check if signals are being generated:
   ```powershell
   Select-String -Path logs\apex_*.log -Pattern "\[ANALYST\].*signals" | Select-Object -Last 5
   ```

2. Check risk manager rejections:
   ```powershell
   Select-String -Path logs\apex_*.log -Pattern "\[RISK\] REJECTED" | Select-Object -Last 10
   ```

3. Check orchestrator decisions:
   ```powershell
   Select-String -Path logs\apex_*.log -Pattern "\[ORCHESTRATOR\].*NOGO" | Select-Object -Last 10
   ```

4. Check news blackout status:
   ```powershell
   Select-String -Path logs\apex_*.log -Pattern "BLACKOUT" | Select-Object -Last 5
   ```

**Solutions:**
- **If no signals generated**: Lower min_signal_score in config (default 6.5)
- **If rejected by G1-G10 gates**: Check which gate is failing, adjust thresholds
  - G1: Lower min_signal_score
  - G2: Lower min_confidence (default 0.65)
  - G3: Lower min_risk_reward (default 1.8)
  - G4: Lower min_adx (default 20.0)
  - G5: Adjust min_atr_ratio/max_atr_ratio
  - G6: Lower min_volume_ratio
  - G7: Wait for news blackout to end
  - G8: Check macro regime (DXY spike?)
  - G9: Daily drawdown limit reached
  - G10: Max open trades reached
- **If NOGO from orchestrator**: Check LLM reasoning in logs
- **If news blackout**: Wait for high-impact event to pass

---

### ISSUE: LLM errors / timeouts

**Symptoms:**
- Logs show "LLM Tier X failed"
- "All LLM providers failed"
- Orchestrator skipping decisions

**Diagnostic Steps:**
1. Check which tier is failing:
   ```powershell
   Select-String -Path logs\apex_*.log -Pattern "LLM Tier" | Select-Object -Last 20
   ```

2. Check Ollama status:
   ```powershell
   curl http://localhost:11434/api/tags
   ```

3. Check Groq rate limits:
   ```powershell
   Select-String -Path logs\apex_*.log -Pattern "Groq.*rate" | Select-Object -Last 5
   ```

4. Check API keys:
   ```powershell
   Get-Content .env | Select-String -Pattern "GROQ_API_KEY|DEEPSEEK_API_KEY|ANTHROPIC_API_KEY"
   ```

**Solutions:**
- **Ollama timeout**: Increase OLLAMA_TIMEOUT in llm/client.py (default 8s)
- **Ollama not running**: Start Ollama service
- **Groq rate limited**: Wait for rate limit to expire (check logs for retry_after)
- **Missing API keys**: Add keys to .env
- **All tiers failing**: Check internet connection, verify API keys are valid

---

### ISSUE: Dashboard not loading data

**Symptoms:**
- Dashboard shows "Loading..." forever
- Empty tables/charts
- Browser console errors

**Diagnostic Steps:**
1. Check API server is running:
   ```powershell
   curl http://localhost:8000/api/status
   ```

2. Check browser console (F12):
   - Look for 404 errors
   - Look for CORS errors
   - Look for JavaScript errors

3. Check API endpoints manually:
   ```powershell
   curl http://localhost:8000/api/trades/open
   curl http://localhost:8000/api/analytics
   ```

4. Check WebSocket connection:
   ```powershell
   Select-String -Path logs\apex_*.log -Pattern "WebSocket" | Select-Object -Last 5
   ```

**Solutions:**
- **API not running**: Start with python main.py
- **404 errors**: Check endpoint paths in apex-api-client.js
- **CORS errors**: Verify CORSMiddleware in api/server.py
- **JavaScript errors**: Check browser console, fix syntax errors
- **WebSocket not connecting**: Check firewall, verify port 8000 is open

---

### ISSUE: Database errors

**Symptoms:**
- "Table does not exist" errors
- "DuckDB read/write error"
- Analytics showing 0 trades despite executions

**Diagnostic Steps:**
1. Check if database file exists:
   ```powershell
   Test-Path data\apex.db
   ```

2. Check database errors in logs:
   ```powershell
   Select-String -Path logs\apex_*.log -Pattern "DuckDB.*error" | Select-Object -Last 10
   ```

3. Check table existence:
   ```python
   import duckdb
   con = duckdb.connect('data/apex.db')
   print(con.execute("SHOW TABLES").fetchall())
   ```

**Solutions:**
- **Database doesn't exist**: Run python scripts/init_apex_health_tables.py
- **Tables missing**: Run init script or check memory/duckdb_store.py::init_schema()
- **Write errors**: Check disk space, verify write permissions
- **Read errors**: Check if database is locked by another process

---

### ISSUE: Broker connection failures

**Symptoms:**
- "MT5 connection failed"
- "Broker unavailable"
- Using mock data instead of live

**Diagnostic Steps:**
1. Check MT5 credentials in .env:
   ```powershell
   Get-Content .env | Select-String -Pattern "MT5_"
   ```

2. Check MT5 terminal is running:
   - Open MetaTrader 5
   - Check if logged in
   - Verify server name matches .env

3. Check broker connection logs:
   ```powershell
   Select-String -Path logs\apex_*.log -Pattern "MT5.*connect" | Select-Object -Last 10
   ```

**Solutions:**
- **Wrong credentials**: Update MT5_LOGIN, MT5_PASSWORD, MT5_SERVER in .env
- **MT5 not installed**: Install MetaTrader 5, update MT5_PATH in .env
- **Server name mismatch**: Check exact server name in MT5 terminal
- **Firewall blocking**: Allow MT5 through firewall
- **Demo account expired**: Use live account or renew demo

---

### ISSUE: Trades closed unexpectedly

**Symptoms:**
- Trades disappearing from open positions
- Closed trades not in history
- P&L not matching expectations

**Diagnostic Steps:**
1. Check sync logs:
   ```powershell
   Select-String -Path logs\apex_*.log -Pattern "SYNC.*CLOSED" | Select-Object -Last 10
   ```

2. Check MT5 terminal for manual closures

3. Check SL/TP hit:
   ```powershell
   Select-String -Path logs\apex_*.log -Pattern "SL|TP" | Select-Object -Last 10
   ```

4. Check closed_trades table:
   ```python
   import duckdb
   con = duckdb.connect('data/apex.db')
   print(con.execute("SELECT * FROM closed_trades ORDER BY close_time DESC LIMIT 5").fetchall())
   ```

**Solutions:**
- **SL/TP hit**: Normal behavior, check if levels were too tight
- **Manual closure**: Check MT5 terminal history
- **Broker closure**: Check broker notifications for margin calls
- **Not in history**: Check storage.store_trade() is being called

---

### ISSUE: Analytics showing wrong numbers

**Symptoms:**
- Win rate doesn't match reality
- Profit factor incorrect
- Equity curve missing data

**Diagnostic Steps:**
1. Check closed_trades table:
   ```python
   import duckdb
   con = duckdb.connect('data/apex.db')
   df = con.execute("SELECT * FROM closed_trades").df()
   print(df)
   ```

2. Check analytics calculation:
   ```powershell
   curl http://localhost:8000/api/analytics
   ```

3. Check if MT5 history is being merged:
   ```powershell
   Select-String -Path logs\apex_*.log -Pattern "MT5 deal history" | Select-Object -Last 5
   ```

**Solutions:**
- **Missing trades**: Check if storage.store_trade() is being called
- **Wrong calculations**: Check data/storage.py::get_analytics()
- **MT5 history not merging**: Check _get_comprehensive_analytics() in api/server.py
- **NaN/Inf values**: Check _clean_val() is being applied

---

### ISSUE: Apex Health not showing data

**Symptoms:**
- Apex Health section shows "No data"
- Latency/decision metrics are 0
- Retrain recommendation not appearing

**Diagnostic Steps:**
1. Check if tables exist:
   ```python
   import duckdb
   con = duckdb.connect('data/apex.db')
   print(con.execute("SHOW TABLES").fetchall())
   ```

2. Check if data is being logged:
   ```powershell
   Select-String -Path logs\apex_*.log -Pattern "llm_calls|bot_decisions" | Select-Object -Last 10
   ```

3. Check API endpoint:
   ```powershell
   curl http://localhost:8000/api/ai/apex-health
   ```

**Solutions:**
- **Tables don't exist**: Run python scripts/init_apex_health_tables.py
- **No data logged**: Bot needs to run for at least one cycle
- **API error**: Check logs for DuckDB errors
- **Frontend not loading**: Check browser console for errors

---

## Performance Issues

### ISSUE: Bot cycle taking too long

**Symptoms:**
- Cycles taking >60 seconds
- Timeouts in logs
- Dashboard laggy

**Diagnostic Steps:**
1. Check cycle duration:
   ```powershell
   Select-String -Path logs\apex_*.log -Pattern "Cycle.*complete" | Select-Object -Last 10
   ```

2. Check which agent is slow:
   ```powershell
   Select-String -Path logs\apex_*.log -Pattern "\[.*\].*took" | Select-Object -Last 20
   ```

**Solutions:**
- **LLM timeouts**: Reduce max_tokens, increase timeouts
- **Too many symbols**: Reduce assets.all_symbols in config
- **News feed slow**: Reduce news fetch limit
- **Database slow**: Add indexes, optimize queries

---

### ISSUE: High memory usage

**Symptoms:**
- Python process using >2GB RAM
- System slowing down
- Out of memory errors

**Diagnostic Steps:**
1. Check process memory:
   ```powershell
   Get-Process python | Select-Object Name, @{Name="Memory(MB)";Expression={[math]::Round(.WS/1MB,2)}}
   ```

2. Check for memory leaks:
   - Look for growing lists in BotState
   - Check if old trades are being cleared

**Solutions:**
- **Too many open trades**: Increase max_open_trades limit
- **Large OHLCV cache**: Limit bars fetched
- **Memory leak**: Restart bot periodically
- **Too many logs**: Rotate logs more frequently

---

## Emergency Procedures

### EMERGENCY: Stop all trading immediately

```powershell
# Stop bot
curl -X POST http://localhost:8000/api/bot/stop

# Close all positions manually in MT5 terminal
# OR via API:
curl http://localhost:8000/api/trades/open
# Then close each trade manually
```

### EMERGENCY: Reset database

```powershell
# Backup first!
Copy-Item data\apex.db data\apex.db.backup

# Delete and reinitialize
Remove-Item data\apex.db
python scripts/init_apex_health_tables.py
```

### EMERGENCY: Reset configuration

```powershell
# Backup first!
Copy-Item .env .env.backup

# Edit .env with safe defaults
# Restart bot
python main.py
```

---

**END OF TROUBLESHOOTING MATRIX**
