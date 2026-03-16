# Start ONLY the trading bot (port 8000)
# Dashboard backend should already be running on port 8001

Write-Host "Starting APEX Trading Bot..." -ForegroundColor Cyan

# Check if virtual environment exists
if (-not (Test-Path ".venv")) {
    Write-Host "ERROR: Virtual environment not found" -ForegroundColor Red
    exit 1
}

# Activate virtual environment
& .\.venv\Scripts\Activate.ps1

# Check if port 8000 is already in use
$port8000 = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($port8000) {
    Write-Host "Port 8000 is already in use. Stopping existing process..." -ForegroundColor Yellow
    $pid = $port8000.OwningProcess | Select-Object -First 1
    Stop-Process -Id $pid -Force
    Start-Sleep -Seconds 2
}

Write-Host "Starting trading bot on port 8000..." -ForegroundColor Green
Write-Host "  Mode: FULL (API + Bot Loop)" -ForegroundColor White
Write-Host "  Autostart: ENABLED" -ForegroundColor White
Write-Host "  Cycle: Every 5 minutes" -ForegroundColor White
Write-Host ""

# Start the bot
python main.py --mode full --autostart --port 8000

Write-Host ""
Write-Host "Bot stopped or failed to start." -ForegroundColor Yellow
Write-Host "Check the output above for errors." -ForegroundColor Yellow
