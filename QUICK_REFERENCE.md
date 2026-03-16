# APEX Trading Bot - Quick Reference Card

## 🚀 Deployment

### One-Command Deploy
```bash
# On your VPS
git clone YOUR_REPO_URL
cd apex-trading-bot
cp .env.example .env
nano .env  # Add your credentials
chmod +x deploy.sh
./deploy.sh
```

---

## 📊 Daily Operations

### Check Status
```bash
docker compose ps                    # Service status
curl http://localhost:8000/api/status  # API health
docker stats                         # Resource usage
```

### View Logs
```bash
docker compose logs -f apex_bot      # Follow bot logs
docker compose logs --tail=100       # Last 100 lines
docker compose logs | grep ERROR     # Filter errors
tail -f logs/apex_$(date +%Y-%m-%d).log  # Today's log file
```

### Restart Services
```bash
docker compose restart apex_bot      # Restart bot only
docker compose restart               # Restart all services
docker compose down && docker compose up -d  # Full restart
```

### Update Code
```bash
git pull origin main                 # Pull latest code
docker compose down                  # Stop services
docker compose build                 # Rebuild images
docker compose up -d                 # Start services
```

---

## 🔧 Maintenance

### Backup
```bash
./backup.sh                          # Manual backup
ls -lh backups/                      # List backups
```

### Restore
```bash
docker compose down
gunzip < backups/db_YYYYMMDD.sql.gz | docker compose exec -T postgres psql -U apex apex_bot
docker compose up -d
```

### Clean Up
```bash
docker system prune -a --volumes -f  # Clean Docker
rm -rf logs/*.log.gz                 # Clean old logs
sudo journalctl --vacuum-time=7d     # Clean system logs
```

### Monitor Resources
```bash
htop                                 # CPU/RAM usage
df -h                                # Disk space
du -sh logs/                         # Log size
ncdu /home/apex                      # Interactive disk usage
```

---

## 🐛 Troubleshooting

### Bot Not Starting
```bash
docker compose logs apex_bot         # Check logs
docker compose down                  # Stop all
docker compose up -d                 # Start all
```

### Database Issues
```bash
docker compose logs postgres         # Check DB logs
docker compose restart postgres      # Restart DB
docker compose exec postgres psql -U apex -d apex_bot  # Connect to DB
```

### High CPU/Memory
```bash
docker stats                         # Check usage
docker compose restart apex_bot      # Restart bot
htop                                 # System monitor
```

### API Not Responding
```bash
curl http://localhost:8000/api/status  # Test API
docker compose logs apex_bot | tail -50  # Recent logs
docker compose restart apex_bot      # Restart
```

### Ollama Issues
```bash
sudo systemctl status ollama         # Check Ollama
sudo systemctl restart ollama        # Restart Ollama
ollama list                          # List models
ollama run apex-trader "test"        # Test model
```

---

## 🔐 Security

### Check Firewall
```bash
sudo ufw status                      # Firewall status
sudo ufw allow 8000/tcp              # Open port
```

### Check Failed Login Attempts
```bash
sudo fail2ban-client status sshd     # SSH bans
sudo journalctl -u ssh | grep Failed  # Failed logins
```

### Update System
```bash
sudo apt update && sudo apt upgrade -y  # Update packages
sudo reboot                          # Reboot if needed
```

---

## 📈 Monitoring

### Access Dashboards
- **Trading Dashboard**: http://YOUR_IP:8000
- **Grafana**: http://YOUR_IP:3000 (admin/admin)
- **Prometheus**: http://YOUR_IP:9090

### Check Metrics
```bash
curl http://localhost:8000/api/analytics  # Trading metrics
docker compose exec postgres psql -U apex -d apex_bot -c "SELECT COUNT(*) FROM trades;"  # Trade count
```

---

## 🔄 Automation

### Cron Jobs
```bash
crontab -l                           # List cron jobs
crontab -e                           # Edit cron jobs
```

### Watchdog
```bash
./watchdog.sh                        # Manual health check
cat logs/watchdog.log                # Check watchdog logs
```

---

## 💰 Cost Tracking

### Monthly Costs
- **VPS**: $6-80/month (depending on specs)
- **Domain**: $1/month (optional)
- **LLM APIs**: $0-50/month (use Groq free tier)
- **Total**: ~$7-130/month

### Optimize Costs
```bash
# Use Groq free tier (100K tokens/day)
# Use Ollama locally (no API costs)
# Choose Hetzner for cheapest VPS ($6.50/month)
# Use DuckDB instead of PostgreSQL for analytics
```

---

## 📞 Emergency Contacts

### Stop Trading Immediately
```bash
docker compose stop apex_bot         # Stop bot, keep data
docker compose down                  # Stop everything
```

### Emergency Backup
```bash
./backup.sh                          # Quick backup
scp -r backups/ user@local:~/        # Copy to local machine
```

### Get Help
```bash
docker compose logs apex_bot > error.log  # Save logs
# Share error.log for support
```

---

## 🎯 Performance Tuning

### Reduce LLM Calls
```bash
# Edit .env
LLM_PRIMARY=ollama                   # Use local Ollama
# Or use Groq for fast, free API calls
```

### Optimize Database
```bash
docker compose exec postgres psql -U apex -d apex_bot -c "VACUUM ANALYZE;"
```

### Reduce Log Size
```bash
# Edit core/logger.py
LOG_LEVEL=WARNING                    # Less verbose
```

---

## 📚 Useful Links

- **Documentation**: `docs/` folder
- **Deployment Guide**: `CLOUD_DEPLOYMENT_PLAN.md`
- **API Docs**: http://YOUR_IP:8000/docs
- **Grafana Dashboards**: http://YOUR_IP:3000

---

## 🆘 Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| Port 8000 in use | `sudo lsof -i :8000` then kill process |
| Out of disk space | `docker system prune -a --volumes -f` |
| Database connection failed | `docker compose restart postgres` |
| Ollama not responding | `sudo systemctl restart ollama` |
| High memory usage | `docker compose restart apex_bot` |
| API timeout | Increase timeout in nginx config |
| SSL certificate expired | `sudo certbot renew` |

---

## 📝 Quick Checklist

### Daily
- [ ] Check dashboard for errors
- [ ] Review trading performance
- [ ] Check disk space: `df -h`

### Weekly
- [ ] Review logs: `docker compose logs`
- [ ] Check backups: `ls -lh backups/`
- [ ] Update system: `sudo apt update && sudo apt upgrade -y`
- [ ] Clean Docker: `docker system prune -f`

### Monthly
- [ ] Review trading strategy
- [ ] Retrain Ollama model
- [ ] Review cloud costs
- [ ] Test backup restoration
- [ ] Update API keys if expiring

---

## 🎓 Pro Tips

1. **Use tmux/screen** for persistent sessions
   ```bash
   tmux new -s apex
   # Detach: Ctrl+B, D
   # Reattach: tmux attach -t apex
   ```

2. **Set up aliases** in `~/.bashrc`
   ```bash
   alias apex-logs='docker compose logs -f apex_bot'
   alias apex-status='docker compose ps'
   alias apex-restart='docker compose restart apex_bot'
   ```

3. **Monitor with watch**
   ```bash
   watch -n 5 'docker compose ps'
   watch -n 10 'curl -s http://localhost:8000/api/status | jq'
   ```

4. **Use jq for JSON parsing**
   ```bash
   curl http://localhost:8000/api/status | jq .
   ```

5. **Set up Telegram alerts** for critical events
   ```bash
   # Add to .env
   TELEGRAM_BOT_TOKEN=your_token
   TELEGRAM_CHAT_ID=your_chat_id
   ```

---

## 📞 Support

- **Logs**: `docker compose logs apex_bot`
- **Status**: `docker compose ps`
- **Health**: `curl http://localhost:8000/api/status`
- **Docs**: `docs/` folder

**Remember**: Always test changes in paper trading mode first! 🛡️
