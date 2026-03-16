# APEX Trading System - Unified Startup

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  APEX TRADING SYSTEM" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check virtual environment
if (-not (Test-Path ".venv")) {
    Write-Host "ERROR: Virtual environment not found" -ForegroundColor Red
    Write-Host "Run: python -m venv .venv" -ForegroundColor Yellow
    exit 1
}

# Activate virtual environment
Write-Host "[1/2] Activating virtual environment..." -ForegroundColor Cyan
& .\.venv\Scripts\Activate.ps1
Write-Host "  OK - Activated" -ForegroundColor Green

# Check configuration
Write-Host ""
Write-Host "[2/2] Starting APEX Bot..." -ForegroundColor Cyan

# Kill any existing process on port 8000
$existing = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    $processId = $existing.OwningProcess | Select-Object -First 1
    Write-Host "  Stopping existing process (PID: $processId)..." -ForegroundColor Yellow
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

Write-Host "  Starting unified service on port 8000..." -ForegroundColor White
Write-Host ""

# Start the bot (this now includes dashboard API)
python main.py --mode full --autostart --port 8000

Write-Host ""
Write-Host "Bot stopped." -ForegroundColor Yellow
