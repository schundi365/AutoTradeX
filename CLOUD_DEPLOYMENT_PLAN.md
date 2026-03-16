# APEX Trading Bot - Cloud Deployment Plan (24/7 Operation)

## Overview
Complete guide to deploy and run the APEX trading bot 24/7 on a cloud VPS with monitoring, auto-restart, and remote access.

---

## Table of Contents
1. [VPS Requirements](#vps-requirements)
2. [Recommended Cloud Providers](#recommended-cloud-providers)
3. [Pre-Deployment Checklist](#pre-deployment-checklist)
4. [Deployment Methods](#deployment-methods)
5. [Step-by-Step Deployment](#step-by-step-deployment)
6. [Monitoring & Maintenance](#monitoring--maintenance)
7. [Security Hardening](#security-hardening)
8. [Backup & Recovery](#backup--recovery)
9. [Cost Optimization](#cost-optimization)
10. [Troubleshooting](#troubleshooting)

---

## VPS Requirements

### Minimum Specs (Paper Trading)
- **CPU**: 2 vCPUs
- **RAM**: 4 GB
- **Storage**: 40 GB SSD
- **Bandwidth**: 1 TB/month
- **OS**: Ubuntu 22.04 LTS
- **Cost**: ~$12-20/month

### Recommended Specs (Live Trading + Ollama)
- **CPU**: 4 vCPUs (8 for Ollama with GPU)
- **RAM**: 8 GB (16 GB with Ollama)
- **Storage**: 80 GB SSD
- **Bandwidth**: 2 TB/month
- **GPU**: Optional (NVIDIA T4 for Ollama)
- **OS**: Ubuntu 22.04 LTS
- **Cost**: ~$40-80/month (GPU: $200-400/month)

### Why These Specs?
- **2-4 vCPUs**: Handle FastAPI, agents, data feeds, and background tasks
- **4-8 GB RAM**: Python processes, Redis, PostgreSQL, and LLM calls
- **40-80 GB SSD**: Logs, database, historical data, and Docker images
- **Ollama**: Requires 8GB+ RAM for 8B models, GPU optional but faster

---

## Recommended Cloud Providers

### 1. DigitalOcean (Easiest)
- **Droplet**: $24/month (4GB RAM, 2 vCPU, 80GB SSD)
- **Pros**: Simple UI, good docs, 1-click Docker, managed databases
- **Cons**: No free tier
- **Best For**: Beginners, quick setup
- **Link**: https://www.digitalocean.com/pricing/droplets

### 2. Hetzner (Best Value)
- **CX21**: €5.83/month (~$6.50) (4GB RAM, 2 vCPU, 40GB SSD)
- **CX31**: €10.52/month (~$11.50) (8GB RAM, 2 vCPU, 80GB SSD)
- **Pros**: Cheapest, excellent performance, EU data centers
- **Cons**: No managed services, manual setup
- **Best For**: Cost-conscious, experienced users
- **Link**: https://www.hetzner.com/cloud

### 3. AWS Lightsail (AWS Ecosystem)
- **$20/month**: 4GB RAM, 2 vCPU, 80GB SSD
- **Pros**: AWS integration, static IP, snapshots
- **Cons**: More expensive than Hetzner
- **Best For**: AWS users, enterprise
- **Link**: https://aws.amazon.com/lightsail/pricing/

### 4. Vultr (GPU Option)
- **Regular**: $18/month (4GB RAM, 2 vCPU, 80GB SSD)
- **GPU**: $90/month (NVIDIA GPU for Ollama)
- **Pros**: GPU instances, global locations
- **Cons**: Mid-range pricing
- **Best For**: GPU-accelerated Ollama
- **Link**: https://www.vultr.com/pricing/

### 5. Linode (Akamai)
- **Shared 4GB**: $24/month (4GB RAM, 2 vCPU, 80GB SSD)
- **Pros**: Reliable, good support, managed Kubernetes
- **Cons**: Pricier than Hetzner
- **Best For**: Reliability-focused
- **Link**: https://www.linode.com/pricing/

### Recommendation
- **Budget**: Hetzner CX21 ($6.50/month) - Best value
- **Ease**: DigitalOcean ($24/month) - Easiest setup
- **GPU**: Vultr GPU ($90/month) - For local Ollama

---

## Pre-Deployment Checklist

### 1. API Keys & Credentials
- [ ] MT5 login, password, server (if using MT5)
- [ ] Binance/Bybit API key + secret (if using crypto)
- [ ] Alpaca API key + secret (if using stocks)
- [ ] Anthropic/OpenAI/Groq API keys
- [ ] FRED API key (for macro data)
- [ ] News API key (optional)
- [ ] Telegram bot token + chat ID (for alerts)

### 2. Local Testing
- [ ] Bot runs successfully on local machine
- [ ] All API connections tested
- [ ] Ollama model working (if using local LLM)
- [ ] Dashboard accessible at http://localhost:8000
- [ ] No critical errors in logs

### 3. Configuration Files
- [ ] `.env` file with all credentials
- [ ] `config/asset_profiles.json` configured
- [ ] `data/training_config.json` set up
- [ ] Docker Compose tested locally

### 4. Domain & DNS (Optional)
- [ ] Domain name purchased (e.g., apex-bot.com)
- [ ] DNS A record pointing to VPS IP
- [ ] SSL certificate plan (Let's Encrypt)

---

## Deployment Methods

### Method 1: Docker Compose (Recommended)
**Pros**: Easy, isolated, reproducible, includes monitoring  
**Cons**: Requires Docker knowledge  
**Best For**: Most users

### Method 2: Systemd Service
**Pros**: Native Linux, no Docker overhead  
**Cons**: Manual dependency management  
**Best For**: Advanced users, minimal resource usage

### Method 3: Kubernetes (Overkill)
**Pros**: Auto-scaling, high availability  
**Cons**: Complex, expensive  
**Best For**: Enterprise, multi-region

**We'll use Method 1 (Docker Compose) in this guide.**

---

## Step-by-Step Deployment

### Phase 1: VPS Setup (30 minutes)

#### 1.1 Create VPS Instance
```bash
# Example: DigitalOcean Droplet
# - Choose Ubuntu 22.04 LTS
# - Select 4GB RAM / 2 vCPU plan
# - Add SSH key for secure access
# - Enable monitoring
# - Create droplet
```

#### 1.2 Initial Server Setup
```bash
# SSH into your VPS
ssh root@YOUR_VPS_IP

# Update system
apt update && apt upgrade -y

# Create non-root user
adduser apex
usermod -aG sudo apex
su - apex

# Set up firewall
sudo ufw allow OpenSSH
sudo ufw allow 8000/tcp  # API
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

#### 1.3 Install Docker & Docker Compose
```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker apex
newgrp docker

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Verify installation
docker --version
docker compose version
```

#### 1.4 Install Additional Tools
```bash
# Install monitoring tools
sudo apt install -y htop ncdu git curl wget nano

# Install Ollama (if using local LLM)
curl -fsSL https://ollama.com/install.sh | sh

# Verify Ollama
ollama --version
```

---

### Phase 2: Deploy Application (20 minutes)

#### 2.1 Clone Repository
```bash
# Clone your repo (replace with your Git URL)
cd ~
git clone https://github.com/yourusername/apex-trading-bot.git
cd apex-trading-bot

# Or upload via SCP if not using Git
# scp -r /local/path/apex-trading-bot apex@YOUR_VPS_IP:~/
```

#### 2.2 Configure Environment
```bash
# Copy example env file
cp .env.example .env

# Edit with your credentials
nano .env

# Required variables:
# - MT5_LOGIN, MT5_PASSWORD, MT5_SERVER
# - EXCHANGE_API_KEY, EXCHANGE_SECRET (if using crypto)
# - ANTHROPIC_API_KEY or GROQ_API_KEY
# - FRED_API_KEY
# - TELEGRAM_BOT_TOKEN (for alerts)
# - DATABASE_URL (use docker-compose defaults)
# - REDIS_URL (use docker-compose defaults)

# Save and exit (Ctrl+X, Y, Enter)
```

#### 2.3 Set Up Ollama Model (Optional)
```bash
# If using local fine-tuned model
# Pull base model
ollama pull llama3.1:8b

# Load your fine-tuned model
# (Assuming you have a Modelfile)
ollama create apex-trader -f Modelfile

# Test model
ollama run apex-trader "Test prompt"

# Update .env
# OLLAMA_BASE_URL=http://host.docker.internal:11434
# OLLAMA_MODEL=apex-trader
```

#### 2.4 Build and Start Services
```bash
# Build Docker images
docker compose build

# Start all services
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f apex_bot

# Wait for services to be healthy (2-3 minutes)
docker compose ps
```

#### 2.5 Verify Deployment
```bash
# Check API health
curl http://localhost:8000/api/status

# Should return: {"status": "online", ...}

# Check dashboard
curl -I http://localhost:8000

# Should return: HTTP/1.1 200 OK
```

---

### Phase 3: Configure Reverse Proxy (Optional, 15 minutes)

#### 3.1 Install Nginx
```bash
sudo apt install nginx -y
sudo systemctl enable nginx
```

#### 3.2 Configure Nginx
```bash
# Create config file
sudo nano /etc/nginx/sites-available/apex-bot

# Add this configuration:
```

```nginx
server {
    listen 80;
    server_name YOUR_DOMAIN_OR_IP;

    # Increase timeouts for long-running requests
    proxy_read_timeout 300;
    proxy_connect_timeout 300;
    proxy_send_timeout 300;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket support
    location /ws {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/apex-bot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

#### 3.3 Set Up SSL (Let's Encrypt)
```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Get SSL certificate
sudo certbot --nginx -d YOUR_DOMAIN

# Auto-renewal is configured automatically
sudo certbot renew --dry-run
```

---

### Phase 4: Monitoring Setup (10 minutes)

#### 4.1 Access Grafana
```bash
# Grafana is already running via docker-compose
# Access at: http://YOUR_VPS_IP:3000
# Default login: admin / admin (change immediately)

# Import APEX dashboard
# - Go to Dashboards > Import
# - Upload monitoring/grafana/dashboards/apex-dashboard.json
```

#### 4.2 Set Up Log Rotation
```bash
# Create logrotate config
sudo nano /etc/logrotate.d/apex-bot
```

```
/home/apex/apex-trading-bot/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0644 apex apex
}
```

#### 4.3 Set Up Monitoring Alerts
```bash
# Edit docker-compose.yml to add alerting
# Or use external services:
# - UptimeRobot (free, 5-min checks)
# - Healthchecks.io (free, cron monitoring)
# - BetterUptime (free tier)

# Example: Healthchecks.io
# Add to crontab:
crontab -e

# Add line:
*/5 * * * * curl -fsS -m 10 --retry 5 -o /dev/null https://hc-ping.com/YOUR_CHECK_ID
```

---

### Phase 5: Auto-Start & Recovery (5 minutes)

#### 5.1 Enable Docker Auto-Start
```bash
# Docker Compose services already have restart: unless-stopped
# Verify:
docker compose ps

# Test restart
sudo reboot

# After reboot, SSH back in and check:
docker compose ps
# All services should be running
```

#### 5.2 Set Up Watchdog Script
```bash
# Create watchdog script
nano ~/watchdog.sh
```

```bash
#!/bin/bash
# APEX Bot Watchdog - Restarts if unhealthy

cd /home/apex/apex-trading-bot

# Check if API is responding
if ! curl -f http://localhost:8000/api/status > /dev/null 2>&1; then
    echo "$(date): API unhealthy, restarting..." >> logs/watchdog.log
    docker compose restart apex_bot
    
    # Send alert
    curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_CHAT_ID}" \
        -d "text=⚠️ APEX Bot restarted due to health check failure"
fi
```

```bash
# Make executable
chmod +x ~/watchdog.sh

# Add to crontab (runs every 5 minutes)
crontab -e

# Add line:
*/5 * * * * /home/apex/watchdog.sh
```

---

## Monitoring & Maintenance

### Daily Checks
```bash
# Check service status
docker compose ps

# Check logs for errors
docker compose logs --tail=100 apex_bot | grep -i error

# Check disk space
df -h

# Check memory usage
free -h

# Check CPU usage
htop
```

### Weekly Maintenance
```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Clean Docker images
docker system prune -a --volumes -f

# Backup database
docker compose exec postgres pg_dump -U apex apex_bot > backup_$(date +%Y%m%d).sql

# Check log sizes
du -sh logs/

# Review trading performance
# Access dashboard at http://YOUR_DOMAIN
```

### Monthly Tasks
- Review and optimize trading strategies
- Retrain Ollama model if needed
- Review cloud costs
- Update API keys if expiring
- Test backup restoration

---

## Security Hardening

### 1. SSH Security
```bash
# Disable root login
sudo nano /etc/ssh/sshd_config

# Set:
# PermitRootLogin no
# PasswordAuthentication no
# PubkeyAuthentication yes

sudo systemctl restart sshd
```

### 2. Fail2Ban (Brute Force Protection)
```bash
sudo apt install fail2ban -y
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### 3. Environment Variables Security
```bash
# Never commit .env to Git
echo ".env" >> .gitignore

# Restrict .env permissions
chmod 600 .env

# Use secrets management for production
# Consider: HashiCorp Vault, AWS Secrets Manager
```

### 4. API Rate Limiting
```bash
# Already implemented in FastAPI
# Configure in core/config.py:
# - MAX_REQUESTS_PER_MINUTE
# - IP_WHITELIST
```

### 5. Database Security
```bash
# Change default passwords
# Edit docker-compose.yml:
# POSTGRES_PASSWORD=STRONG_RANDOM_PASSWORD

# Restrict database access
# Only allow from Docker network
```

---

## Backup & Recovery

### Automated Backup Script
```bash
# Create backup script
nano ~/backup.sh
```

```bash
#!/bin/bash
# APEX Bot Backup Script

BACKUP_DIR="/home/apex/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup database
docker compose exec -T postgres pg_dump -U apex apex_bot | gzip > $BACKUP_DIR/db_$DATE.sql.gz

# Backup config files
tar -czf $BACKUP_DIR/config_$DATE.tar.gz .env config/ data/training_config.json

# Backup logs (last 7 days)
tar -czf $BACKUP_DIR/logs_$DATE.tar.gz logs/

# Keep only last 30 days
find $BACKUP_DIR -name "*.gz" -mtime +30 -delete

echo "$(date): Backup completed" >> $BACKUP_DIR/backup.log
```

```bash
# Make executable
chmod +x ~/backup.sh

# Schedule daily backups
crontab -e

# Add line (runs at 2 AM daily):
0 2 * * * /home/apex/backup.sh
```

### Restore from Backup
```bash
# Stop services
docker compose down

# Restore database
gunzip < backups/db_YYYYMMDD_HHMMSS.sql.gz | docker compose exec -T postgres psql -U apex apex_bot

# Restore config
tar -xzf backups/config_YYYYMMDD_HHMMSS.tar.gz

# Restart services
docker compose up -d
```

---

## Cost Optimization

### 1. Choose Right VPS Size
- Start with minimum specs
- Monitor resource usage for 1 week
- Upgrade only if consistently >80% CPU/RAM

### 2. Use Spot/Preemptible Instances
- AWS Spot: 70% cheaper
- GCP Preemptible: 80% cheaper
- Risk: Can be terminated (use with auto-restart)

### 3. Optimize LLM Costs
- Use Groq (free tier: 100K tokens/day)
- Use Ollama locally (no API costs)
- Cache LLM responses
- Reduce unnecessary LLM calls

### 4. Data Transfer Optimization
- Use CloudFlare CDN (free)
- Compress API responses
- Limit historical data fetching

### 5. Database Optimization
- Use DuckDB for analytics (file-based, no server)
- PostgreSQL only for critical data
- Regular VACUUM and ANALYZE

### Monthly Cost Breakdown (Hetzner CX21)
- VPS: $6.50
- Domain: $1 (annual/12)
- Groq API: $0 (free tier)
- Telegram: $0
- **Total: ~$7.50/month**

---

## Troubleshooting

### Bot Not Starting
```bash
# Check logs
docker compose logs apex_bot

# Common issues:
# 1. Missing .env variables
# 2. Database connection failed
# 3. Port 8000 already in use

# Fix:
docker compose down
docker compose up -d
```

### High CPU Usage
```bash
# Check processes
docker stats

# Common causes:
# 1. Too many concurrent LLM calls
# 2. Infinite loop in agent
# 3. Memory leak

# Fix:
# - Reduce agent frequency
# - Add rate limiting
# - Restart service
```

### Database Connection Errors
```bash
# Check PostgreSQL
docker compose logs postgres

# Restart database
docker compose restart postgres

# Check connection
docker compose exec postgres psql -U apex -d apex_bot -c "SELECT 1;"
```

### Ollama Not Responding
```bash
# Check Ollama service
sudo systemctl status ollama

# Restart Ollama
sudo systemctl restart ollama

# Check model
ollama list

# Test model
ollama run apex-trader "test"
```

### Out of Disk Space
```bash
# Check disk usage
df -h
du -sh logs/
du -sh /var/lib/docker/

# Clean up
docker system prune -a --volumes -f
sudo journalctl --vacuum-time=7d
rm -rf logs/*.log.gz
```

---

## Quick Start Commands

### Deploy from Scratch
```bash
# 1. SSH into VPS
ssh apex@YOUR_VPS_IP

# 2. Clone repo
git clone YOUR_REPO_URL
cd apex-trading-bot

# 3. Configure
cp .env.example .env
nano .env  # Add your credentials

# 4. Deploy
docker compose up -d

# 5. Check status
docker compose ps
curl http://localhost:8000/api/status

# 6. Access dashboard
# Open browser: http://YOUR_VPS_IP:8000
```

### Update Deployment
```bash
# Pull latest code
git pull origin main

# Rebuild and restart
docker compose down
docker compose build
docker compose up -d

# Check logs
docker compose logs -f apex_bot
```

### Emergency Stop
```bash
# Stop all services
docker compose down

# Stop trading only (keep data)
docker compose stop apex_bot

# Restart
docker compose up -d
```

---

## Next Steps

1. ✅ Deploy to VPS using this guide
2. ✅ Monitor for 24 hours to ensure stability
3. ✅ Set up alerts (Telegram/Slack)
4. ✅ Configure automated backups
5. ✅ Test with paper trading for 1 week
6. ✅ Gradually increase position sizes
7. ✅ Set up Grafana dashboards
8. ✅ Document your custom configurations

---

## Support & Resources

- **Documentation**: `docs/` folder
- **Issues**: GitHub Issues
- **Community**: Discord/Telegram
- **Monitoring**: Grafana at port 3000
- **Logs**: `logs/apex_*.log`

---

## Summary

This deployment plan provides:
- ✅ 24/7 uptime with auto-restart
- ✅ Monitoring and alerting
- ✅ Automated backups
- ✅ Security hardening
- ✅ Cost optimization
- ✅ Easy maintenance

**Estimated Setup Time**: 1-2 hours  
**Monthly Cost**: $7-80 depending on specs  
**Maintenance**: 30 minutes/week

Good luck with your deployment! 🚀
