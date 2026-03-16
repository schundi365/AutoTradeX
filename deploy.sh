#!/bin/bash
# ═══════════════════════════════════════════════════════
#  APEX Trading Bot - Quick Deployment Script
#  Run this on your VPS to set up everything automatically
# ═══════════════════════════════════════════════════════

set -e  # Exit on error

echo "╔════════════════════════════════════════════════════╗"
echo "║   APEX Trading Bot - Cloud Deployment Script      ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
print_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
    print_error "Please do not run as root. Run as regular user with sudo privileges."
    exit 1
fi

# ── STEP 1: System Update ──────────────────────────────
print_step "Updating system packages..."
sudo apt update && sudo apt upgrade -y
print_success "System updated"

# ── STEP 2: Install Docker ────────────────────────────
print_step "Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
    print_success "Docker installed"
else
    print_success "Docker already installed"
fi

# ── STEP 3: Install Docker Compose ────────────────────
print_step "Installing Docker Compose..."
if ! command -v docker compose &> /dev/null; then
    sudo apt install docker-compose-plugin -y
    print_success "Docker Compose installed"
else
    print_success "Docker Compose already installed"
fi

# ── STEP 4: Install Additional Tools ──────────────────
print_step "Installing additional tools..."
sudo apt install -y htop ncdu git curl wget nano ufw fail2ban
print_success "Additional tools installed"

# ── STEP 5: Configure Firewall ────────────────────────
print_step "Configuring firewall..."
sudo ufw --force enable
sudo ufw allow OpenSSH
sudo ufw allow 8000/tcp  # API
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
print_success "Firewall configured"

# ── STEP 6: Check for .env File ───────────────────────
print_step "Checking configuration..."
if [ ! -f .env ]; then
    print_warning ".env file not found"
    if [ -f .env.example ]; then
        cp .env.example .env
        print_warning "Created .env from .env.example"
        print_warning "Please edit .env with your credentials before continuing"
        echo ""
        echo "Run: nano .env"
        echo "Then run this script again"
        exit 0
    else
        print_error ".env.example not found. Cannot create .env"
        exit 1
    fi
else
    print_success ".env file found"
fi

# ── STEP 7: Install Ollama (Optional) ─────────────────
read -p "Do you want to install Ollama for local LLM? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_step "Installing Ollama..."
    if ! command -v ollama &> /dev/null; then
        curl -fsSL https://ollama.com/install.sh | sh
        print_success "Ollama installed"
        
        # Pull base model
        print_step "Pulling Llama 3.1 8B model (this may take a while)..."
        ollama pull llama3.1:8b
        print_success "Base model downloaded"
    else
        print_success "Ollama already installed"
    fi
fi

# ── STEP 8: Create Directories ────────────────────────
print_step "Creating directories..."
mkdir -p logs backups monitoring/grafana/dashboards
print_success "Directories created"

# ── STEP 9: Build Docker Images ───────────────────────
print_step "Building Docker images (this may take a few minutes)..."
docker compose build
print_success "Docker images built"

# ── STEP 10: Start Services ───────────────────────────
print_step "Starting services..."
docker compose up -d
print_success "Services started"

# ── STEP 11: Wait for Services ────────────────────────
print_step "Waiting for services to be healthy (30 seconds)..."
sleep 30

# ── STEP 12: Check Service Status ─────────────────────
print_step "Checking service status..."
docker compose ps

# ── STEP 13: Test API ─────────────────────────────────
print_step "Testing API endpoint..."
if curl -f http://localhost:8000/api/status > /dev/null 2>&1; then
    print_success "API is responding"
else
    print_warning "API not responding yet. Check logs with: docker compose logs apex_bot"
fi

# ── STEP 14: Set Up Log Rotation ──────────────────────
print_step "Setting up log rotation..."
sudo tee /etc/logrotate.d/apex-bot > /dev/null <<EOF
$(pwd)/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0644 $USER $USER
}
EOF
print_success "Log rotation configured"

# ── STEP 15: Create Watchdog Script ───────────────────
print_step "Creating watchdog script..."
cat > watchdog.sh <<'EOF'
#!/bin/bash
# APEX Bot Watchdog - Restarts if unhealthy

cd $(dirname $0)

# Check if API is responding
if ! curl -f http://localhost:8000/api/status > /dev/null 2>&1; then
    echo "$(date): API unhealthy, restarting..." >> logs/watchdog.log
    docker compose restart apex_bot
fi
EOF
chmod +x watchdog.sh
print_success "Watchdog script created"

# ── STEP 16: Set Up Cron Jobs ─────────────────────────
print_step "Setting up cron jobs..."
(crontab -l 2>/dev/null; echo "*/5 * * * * $(pwd)/watchdog.sh") | crontab -
(crontab -l 2>/dev/null; echo "0 2 * * * $(pwd)/backup.sh") | crontab -
print_success "Cron jobs configured"

# ── STEP 17: Create Backup Script ─────────────────────
print_step "Creating backup script..."
cat > backup.sh <<EOF
#!/bin/bash
# APEX Bot Backup Script

BACKUP_DIR="$(pwd)/backups"
DATE=\$(date +%Y%m%d_%H%M%S)

mkdir -p \$BACKUP_DIR

# Backup database
docker compose exec -T postgres pg_dump -U apex apex_bot | gzip > \$BACKUP_DIR/db_\$DATE.sql.gz

# Backup config files
tar -czf \$BACKUP_DIR/config_\$DATE.tar.gz .env config/ data/training_config.json

# Keep only last 30 days
find \$BACKUP_DIR -name "*.gz" -mtime +30 -delete

echo "\$(date): Backup completed" >> \$BACKUP_DIR/backup.log
EOF
chmod +x backup.sh
print_success "Backup script created"

# ── STEP 18: Display Summary ──────────────────────────
echo ""
echo "╔════════════════════════════════════════════════════╗"
echo "║           Deployment Complete! 🚀                  ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""
print_success "APEX Trading Bot is now running!"
echo ""
echo "📊 Dashboard: http://$(curl -s ifconfig.me):8000"
echo "📈 Grafana:   http://$(curl -s ifconfig.me):3000 (admin/admin)"
echo "📋 Logs:      docker compose logs -f apex_bot"
echo "🔍 Status:    docker compose ps"
echo ""
echo "Next Steps:"
echo "1. Access the dashboard in your browser"
echo "2. Check logs for any errors"
echo "3. Configure Telegram alerts in .env"
echo "4. Set up domain and SSL (optional)"
echo "5. Monitor for 24 hours before live trading"
echo ""
echo "Useful Commands:"
echo "  docker compose ps              # Check status"
echo "  docker compose logs -f         # View logs"
echo "  docker compose restart         # Restart services"
echo "  docker compose down            # Stop services"
echo "  ./watchdog.sh                  # Manual health check"
echo "  ./backup.sh                    # Manual backup"
echo ""
print_warning "Remember to secure your .env file and never commit it to Git!"
echo ""
