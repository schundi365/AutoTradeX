# APEX Trading Bot - Pre-Deployment Checklist

## 📋 Complete this checklist before deploying to production

---

## 1. API Keys & Credentials ✓

### Trading Accounts
- [ ] **MT5 Account** (if using Forex/Metals)
  - [ ] Login ID
  - [ ] Password
  - [ ] Server name
  - [ ] Tested connection locally
  
- [ ] **Crypto Exchange** (if using Crypto)
  - [ ] Exchange selected (Binance/Bybit/Kraken)
  - [ ] API Key generated
  - [ ] API Secret saved
  - [ ] Testnet/Sandbox enabled for testing
  - [ ] Withdrawal disabled on API key
  - [ ] IP whitelist configured (optional)
  
- [ ] **Stock Broker** (if using Stocks)
  - [ ] Alpaca API Key
  - [ ] Alpaca Secret Key
  - [ ] Paper trading URL configured

### AI/LLM Services
- [ ] **Primary LLM**
  - [ ] Anthropic API Key (Claude)
  - [ ] OR OpenAI API Key (GPT)
  - [ ] OR Groq API Key (Free tier)
  - [ ] OR Ollama installed locally
  - [ ] Tested API connection
  - [ ] Rate limits understood

- [ ] **Fallback LLM** (recommended)
  - [ ] Secondary API key configured
  - [ ] Tested fallback mechanism

### Data Feeds
- [ ] **FRED API Key** (Macro data)
  - [ ] Key obtained from https://fred.stlouisfed.org
  - [ ] Tested API connection
  
- [ ] **News API** (Optional)
  - [ ] News API key (if using)
  - [ ] Alternative news source configured

### Notifications
- [ ] **Telegram Bot** (Recommended)
  - [ ] Bot created via @BotFather
  - [ ] Bot token saved
  - [ ] Chat ID obtained
  - [ ] Test message sent successfully
  
- [ ] **Slack** (Optional)
  - [ ] Webhook URL configured
  - [ ] Test message sent

---

## 2. Local Testing ✓

### Bot Functionality
- [ ] Bot starts without errors
- [ ] Dashboard accessible at http://localhost:8000
- [ ] All tabs load correctly (Dashboard, Trades, Analytics, etc.)
- [ ] WebSocket connection working
- [ ] No critical errors in logs

### Trading Connections
- [ ] Broker connection successful
- [ ] Can fetch market data
- [ ] Can place test orders (paper trading)
- [ ] Can close test positions
- [ ] Order execution logs correctly

### LLM Integration
- [ ] LLM responds to test prompts
- [ ] Fallback chain works (Ollama → Groq → DeepSeek → Claude)
- [ ] Rate limit handling tested
- [ ] Response times acceptable (<5 seconds)

### Data Collection
- [ ] Historical data downloads successfully
- [ ] Real-time quotes updating
- [ ] News feed working
- [ ] Economic calendar loading
- [ ] Macro data fetching (FRED)

### Database
- [ ] DuckDB file created
- [ ] Tables initialized
- [ ] Data persisting correctly
- [ ] No corruption errors

---

## 3. Configuration Files ✓

### Environment Variables (.env)
- [ ] `.env` file created from `.env.example`
- [ ] All required variables filled
- [ ] No placeholder values remaining
- [ ] Sensitive data not committed to Git
- [ ] `.env` in `.gitignore`

### Trading Configuration
- [ ] `config/asset_profiles.json` configured
  - [ ] Asset classes enabled/disabled
  - [ ] Position sizes set
  - [ ] Risk limits defined
  
- [ ] Risk parameters reviewed
  - [ ] Max position size
  - [ ] Max open trades
  - [ ] Max daily loss
  - [ ] Max drawdown

### Training Configuration
- [ ] `data/training_config.json` exists
- [ ] Ollama model name correct
- [ ] Training parameters set
- [ ] Data collection settings configured

---

## 4. VPS Selection ✓

### Provider Chosen
- [ ] Cloud provider selected
  - [ ] DigitalOcean (easiest)
  - [ ] Hetzner (cheapest)
  - [ ] AWS Lightsail (AWS ecosystem)
  - [ ] Vultr (GPU option)
  - [ ] Linode (reliable)

### VPS Specs
- [ ] **Minimum**: 2 vCPU, 4GB RAM, 40GB SSD
- [ ] **Recommended**: 4 vCPU, 8GB RAM, 80GB SSD
- [ ] **With Ollama**: 8GB+ RAM, GPU optional
- [ ] Ubuntu 22.04 LTS selected
- [ ] SSH key added for secure access

### Networking
- [ ] Static IP assigned
- [ ] Firewall rules planned
  - [ ] Port 22 (SSH)
  - [ ] Port 8000 (API)
  - [ ] Port 80 (HTTP)
  - [ ] Port 443 (HTTPS)

---

## 5. Domain & SSL (Optional) ✓

### Domain Setup
- [ ] Domain purchased (e.g., apex-bot.com)
- [ ] DNS A record created pointing to VPS IP
- [ ] DNS propagation verified (24-48 hours)

### SSL Certificate
- [ ] Let's Encrypt Certbot plan
- [ ] Auto-renewal configured
- [ ] HTTPS redirect enabled

---

## 6. Monitoring & Alerts ✓

### Monitoring Tools
- [ ] Grafana dashboard planned
- [ ] Prometheus metrics configured
- [ ] Log rotation set up
- [ ] Disk space monitoring

### Alerting
- [ ] Telegram alerts configured
- [ ] Critical error notifications
- [ ] Daily performance summary
- [ ] Uptime monitoring (UptimeRobot/Healthchecks.io)

---

## 7. Backup Strategy ✓

### Backup Plan
- [ ] Automated daily backups scheduled
- [ ] Backup script tested
- [ ] Backup retention policy (30 days)
- [ ] Off-site backup location (optional)

### Recovery Plan
- [ ] Restore procedure documented
- [ ] Restore tested successfully
- [ ] RTO (Recovery Time Objective) defined
- [ ] RPO (Recovery Point Objective) defined

---

## 8. Security Hardening ✓

### SSH Security
- [ ] SSH key authentication enabled
- [ ] Password authentication disabled
- [ ] Root login disabled
- [ ] Fail2Ban installed

### Application Security
- [ ] Strong passwords used
- [ ] API keys secured
- [ ] `.env` file permissions restricted (chmod 600)
- [ ] Database passwords changed from defaults
- [ ] Firewall configured (UFW)

### Network Security
- [ ] Only necessary ports open
- [ ] IP whitelist configured (if applicable)
- [ ] Rate limiting enabled
- [ ] DDoS protection (CloudFlare)

---

## 9. Cost Planning ✓

### Monthly Budget
- [ ] VPS cost calculated: $______/month
- [ ] Domain cost: $______/month
- [ ] LLM API costs estimated: $______/month
- [ ] Total monthly cost: $______/month
- [ ] Budget approved

### Cost Optimization
- [ ] Using free tier LLMs (Groq)
- [ ] Using Ollama locally (no API costs)
- [ ] Cheapest VPS provider selected
- [ ] Unnecessary services disabled

---

## 10. Trading Strategy ✓

### Strategy Configuration
- [ ] Trading strategy defined
- [ ] Asset classes selected
- [ ] Timeframes configured
- [ ] Risk/reward ratios set

### Risk Management
- [ ] Position sizing rules
- [ ] Stop loss strategy
- [ ] Take profit strategy
- [ ] Max drawdown limits
- [ ] Correlation checks enabled

### Testing
- [ ] Backtested on historical data
- [ ] Paper traded for 1+ week
- [ ] Performance metrics reviewed
- [ ] Win rate acceptable (>60%)
- [ ] Risk/reward ratio acceptable (>1.5:1)

---

## 11. Documentation ✓

### Documentation Complete
- [ ] Deployment guide read
- [ ] Quick reference card reviewed
- [ ] Troubleshooting guide understood
- [ ] API documentation reviewed

### Team Knowledge
- [ ] Team trained on dashboard
- [ ] Emergency procedures documented
- [ ] Contact information updated
- [ ] Escalation path defined

---

## 12. Legal & Compliance ✓

### Regulatory Compliance
- [ ] Trading regulations reviewed for your jurisdiction
- [ ] Broker terms of service accepted
- [ ] API usage terms understood
- [ ] Tax implications considered

### Risk Disclosure
- [ ] Understand trading risks
- [ ] Only trading with risk capital
- [ ] Stop loss mechanisms in place
- [ ] Emergency shutdown procedure defined

---

## 13. Final Checks ✓

### Pre-Launch
- [ ] All checklist items completed
- [ ] Team ready for launch
- [ ] Monitoring dashboards open
- [ ] Emergency contacts available
- [ ] Paper trading successful for 1+ week

### Launch Day
- [ ] Start with small position sizes
- [ ] Monitor closely for first 24 hours
- [ ] Check logs every hour
- [ ] Verify trades executing correctly
- [ ] Confirm P&L tracking accurate

### Post-Launch (First Week)
- [ ] Daily performance review
- [ ] Log analysis for errors
- [ ] Strategy adjustments if needed
- [ ] Gradually increase position sizes
- [ ] Document lessons learned

---

## 🚦 Deployment Readiness Score

Count your checkmarks:

- **90-100%**: ✅ Ready to deploy
- **70-89%**: ⚠️ Almost ready, complete remaining items
- **50-69%**: ⏸️ Not ready, significant work needed
- **<50%**: 🛑 Do not deploy, complete checklist first

---

## 📝 Sign-Off

### Deployment Approval

**Prepared by**: ___________________  
**Date**: ___________________  
**Deployment Date**: ___________________  
**Initial Position Size**: ___________________  
**Max Daily Risk**: ___________________  

**Approved by**: ___________________  
**Date**: ___________________  

---

## 🆘 Emergency Contacts

**Primary Contact**: ___________________  
**Phone**: ___________________  
**Email**: ___________________  

**Secondary Contact**: ___________________  
**Phone**: ___________________  
**Email**: ___________________  

**VPS Provider Support**: ___________________  
**Broker Support**: ___________________  

---

## 📞 Emergency Shutdown

If something goes wrong:

```bash
# SSH into VPS
ssh apex@YOUR_VPS_IP

# Stop trading immediately
docker compose stop apex_bot

# Or stop everything
docker compose down

# Check what happened
docker compose logs apex_bot | tail -100

# Backup current state
./backup.sh
```

---

## ✅ Final Reminder

**DO NOT SKIP THIS CHECKLIST!**

Taking shortcuts can lead to:
- Lost funds
- Security breaches
- Data loss
- Downtime
- Regulatory issues

**Take your time. Do it right. Trade safely.** 🛡️

---

## 🎯 Next Steps After Checklist

1. ✅ Complete this checklist
2. 📖 Read `CLOUD_DEPLOYMENT_PLAN.md`
3. 🚀 Run `deploy.sh` on your VPS
4. 📊 Monitor for 24 hours
5. 📈 Start with paper trading
6. 💰 Gradually move to live trading

Good luck! 🚀
