# APEX Bot - Clean Restart Script
# Kills all processes, clears locks, and starts fresh

Write-Host "🧹 APEX Clean Restart" -ForegroundColor Cyan
Write-Host "=====================" -ForegroundColor Cyan
Write-Host ""

# 1. Kill all Python processes
Write-Host "1. Stopping all Python processes..." -ForegroundColor Yellow
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# 2. Clear Python cache
Write-Host "2. Clearing Python cache..." -ForegroundColor Yellow
Get-ChildItem -Path . -Include __pycache__ -Recurse -Force | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path . -Filter "*.pyc" -Recurse -Force | Remove-Item -Force -ErrorAction SilentlyContinue

# 3. Remove DuckDB lock files
Write-Host "3. Removing database locks..." -ForegroundColor Yellow
Remove-Item -Path "data/*.duckdb.wal" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "data/*.duckdb-shm" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "data/*.duckdb-wal" -Force -ErrorAction SilentlyContinue

# 4. Check port 8000
Write-Host "4. Checking port 8000..." -ForegroundColor Yellow
$port8000 = netstat -ano | Select-String ":8000.*LISTENING"
if ($port8000) {
    $pid = ($port8000 -split '\s+')[-1]
    Write-Host "   Killing process $pid on port 8000..." -ForegroundColor Red
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# 5. Verify clean state
Write-Host "5. Verifying clean state..." -ForegroundColor Yellow
$pythonProcs = Get-Process python -ErrorAction SilentlyContinue
if ($pythonProcs) {
    Write-Host "   ⚠️  Warning: Python processes still running:" -ForegroundColor Red
    $pythonProcs | Select-Object Id, ProcessName | Format-Table
} else {
    Write-Host "   ✓ No Python processes running" -ForegroundColor Green
}

$port8000Check = netstat -ano | Select-String ":8000.*LISTENING"
if ($port8000Check) {
    Write-Host "   ⚠️  Warning: Port 8000 still in use" -ForegroundColor Red
} else {
    Write-Host "   ✓ Port 8000 is free" -ForegroundColor Green
}

Write-Host ""
Write-Host "6. Starting APEX Bot..." -ForegroundColor Yellow
Write-Host ""

# Start the bot
python main.py --mode paper --port 8000

Write-Host ""
Write-Host "✓ APEX Bot started" -ForegroundColor Green
Write-Host "  Dashboard: http://localhost:8000" -ForegroundColor Cyan
