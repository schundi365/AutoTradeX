# APEX Trading Bot Startup Script
# Starts both the trading bot (port 8000) and dashboard backend (port 8001)

Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 59) -ForegroundColor Cyan
Write-Host "  APEX TRADING BOT - UNIFIED STARTUP" -ForegroundColor Yellow
Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 59) -ForegroundColor Cyan
Write-Host ""

# Check if virtual environment exists
if (-not (Test-Path ".venv")) {
    Write-Host "ERROR: Virtual environment not found at .venv" -ForegroundColor Red
    Write-Host "Please create it first: python -m venv .venv" -ForegroundColor Yellow
    exit 1
}

# Activate virtual environment
Write-Host "[1/4] Activating virtual environment..." -ForegroundColor Cyan
& .\.venv\Scripts\Activate.ps1

# Check if MT5 is configured
Write-Host "[2/4] Checking configuration..." -ForegroundColor Cyan
if (-not (Test-Path ".env")) {
    Write-Host "WARNING: .env file not found. Using defaults." -ForegroundColor Yellow
} else {
    Write-Host "  Config file found: .env" -ForegroundColor Green
}

# Start Trading Bot (port 8000) with autostart
Write-Host "[3/4] Starting Trading Bot (port 8000)..." -ForegroundColor Cyan

# Check if port 8000 is already in use
$existingBot = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($existingBot) {
    Write-Host "  Trading bot already running on port 8000" -ForegroundColor Yellow
    $botProcess = Get-Process -Id $existingBot.OwningProcess -ErrorAction SilentlyContinue
} else {
    Write-Host "  Mode: FULL (API + Bot Loop)" -ForegroundColor White
    Write-Host "  Autostart: ENABLED" -ForegroundColor White
    Write-Host "  Cycle: Every 5 minutes" -ForegroundColor White
    Write-Host ""

    $botProcess = Start-Process -FilePath "python" -ArgumentList "main.py --mode full --autostart --port 8000" -PassThru -NoNewWindow
    Start-Sleep -Seconds 3
}

# Start Dashboard Backend (port 8001)
Write-Host "[4/4] Starting Dashboard Backend (port 8001)..." -ForegroundColor Cyan

# Check if port 8001 is already in use
$existingDashboard = Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue
if ($existingDashboard) {
    Write-Host "  Dashboard backend already running on port 8001" -ForegroundColor Yellow
    $dashboardProcess = Get-Process -Id $existingDashboard.OwningProcess -ErrorAction SilentlyContinue
} else {
    $dashboardProcess = Start-Process -FilePath "python" -ArgumentList "api/dashboard_backend.py" -PassThru -NoNewWindow
    Start-Sleep -Seconds 2
}

Write-Host ""
Write-Host "=" -NoNewline -ForegroundColor Green
Write-Host ("=" * 59) -ForegroundColor Green
Write-Host "  STARTUP COMPLETE" -ForegroundColor Yellow
Write-Host "=" -NoNewline -ForegroundColor Green
Write-Host ("=" * 59) -ForegroundColor Green
Write-Host ""
Write-Host "Services Running:" -ForegroundColor White
Write-Host "  Trading Bot API:     http://localhost:8000" -ForegroundColor Cyan
Write-Host "  Dashboard Backend:   http://localhost:8001" -ForegroundColor Cyan
Write-Host "  Dashboard Frontend:  http://localhost:3000 (start separately)" -ForegroundColor Yellow
Write-Host ""
Write-Host "Process IDs:" -ForegroundColor White
Write-Host "  Trading Bot:    PID $($botProcess.Id)" -ForegroundColor Gray
Write-Host "  Dashboard:      PID $($dashboardProcess.Id)" -ForegroundColor Gray
Write-Host ""
Write-Host "To start the frontend dashboard:" -ForegroundColor White
Write-Host "  cd frontend/dashboard" -ForegroundColor Cyan
Write-Host "  npm run dev" -ForegroundColor Cyan
Write-Host ""
Write-Host "To stop all services:" -ForegroundColor White
Write-Host "  .\stop-trading-bot.ps1" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop monitoring (services will continue running)" -ForegroundColor Yellow
Write-Host ""

# Monitor both processes
try {
    while ($true) {
        if ($botProcess.HasExited) {
            Write-Host "WARNING: Trading bot process exited!" -ForegroundColor Red
            break
        }
        if ($dashboardProcess.HasExited) {
            Write-Host "WARNING: Dashboard backend process exited!" -ForegroundColor Red
            break
        }
        Start-Sleep -Seconds 5
    }
} catch {
    Write-Host "Monitoring stopped." -ForegroundColor Yellow
}
