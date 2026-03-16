# APEX Trading System - Unified Startup Script
param(
    [switch]$StopFirst,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

# ═══════════════════════════════════════════════════════
#  HELP
# ═══════════════════════════════════════════════════════
if ($Help) {
    Write-Host ""
    Write-Host "APEX TRADING SYSTEM - STARTUP SCRIPT" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "USAGE:" -ForegroundColor Cyan
    Write-Host "  .\start-apex.ps1              Start APEX system"
    Write-Host "  .\start-apex.ps1 -StopFirst   Stop existing services before starting"
    Write-Host "  .\start-apex.ps1 -Help        Show this help message"
    Write-Host ""
    Write-Host "SERVICES:" -ForegroundColor Cyan
    Write-Host "  - Bot API (port 8000)"
    Write-Host "  - Dashboard (port 8001)"
    Write-Host "  - Ollama (port 11434)"
    Write-Host ""
    exit 0
}

# ═══════════════════════════════════════════════════════
#  STOP SERVICES FUNCTION
# ═══════════════════════════════════════════════════════
function Stop-ApexServices {
    Write-Host ""
    Write-Host "STOPPING APEX SERVICES" -ForegroundColor Yellow
    Write-Host ""
    
    # Stop processes on ports 8000 and 8001
    Write-Host "[1/3] Stopping API services..." -ForegroundColor Cyan
    $ports = @(8000, 8001)
    $stopped = 0
    foreach ($port in $ports) {
        $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if ($conn) {
            $processId = $conn.OwningProcess | Select-Object -First 1
            try {
                Stop-Process -Id $processId -Force -ErrorAction Stop
                Write-Host "  Stopped process on port $port (PID: $processId)" -ForegroundColor Green
                $stopped++
            } catch {
                Write-Host "  Failed to stop process on port $port" -ForegroundColor Red
            }
        }
    }
    if ($stopped -eq 0) {
        Write-Host "  No services running on ports 8000/8001" -ForegroundColor Gray
    }
    
    # Stop Python processes running main.py or dashboard_backend
    Write-Host "[2/3] Stopping Python processes..." -ForegroundColor Cyan
    $pythonProcs = Get-Process -Name "python*" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*main.py*" -or $_.CommandLine -like "*dashboard_backend*"
    }
    if ($pythonProcs) {
        $pythonProcs | ForEach-Object {
            try {
                Stop-Process -Id $_.Id -Force -ErrorAction Stop
                Write-Host "  Stopped Python process (PID: $($_.Id))" -ForegroundColor Green
            } catch {
                Write-Host "  Failed to stop Python process (PID: $($_.Id))" -ForegroundColor Red
            }
        }
    } else {
        Write-Host "  No APEX Python processes running" -ForegroundColor Gray
    }
    
    # Stop background jobs
    Write-Host "[3/3] Stopping background jobs..." -ForegroundColor Cyan
    $jobs = Get-Job -ErrorAction SilentlyContinue
    if ($jobs) {
        $jobs | Stop-Job -ErrorAction SilentlyContinue
        $jobs | Remove-Job -Force -ErrorAction SilentlyContinue
        Write-Host "  Stopped $($jobs.Count) background job(s)" -ForegroundColor Green
    } else {
        Write-Host "  No background jobs running" -ForegroundColor Gray
    }
    
    Write-Host ""
    Write-Host "Services stopped" -ForegroundColor Green
    Start-Sleep -Seconds 1
}

# ═══════════════════════════════════════════════════════
#  STOP SERVICES IF REQUESTED
# ═══════════════════════════════════════════════════════
if ($StopFirst) {
    Stop-ApexServices
}

# ═══════════════════════════════════════════════════════
#  START SERVICES
# ═══════════════════════════════════════════════════════

Write-Host ""
Write-Host "APEX TRADING SYSTEM - STARTUP" -ForegroundColor Yellow
Write-Host ""

if (-not (Test-Path ".venv")) {
    Write-Host "Virtual environment not found" -ForegroundColor Red
    exit 1
}

Write-Host "[1/4] Activating virtual environment..." -ForegroundColor Cyan
& .\.venv\Scripts\Activate.ps1

Write-Host "[2/4] Checking configuration..." -ForegroundColor Cyan
if (Test-Path ".env") { Write-Host "  OK" -ForegroundColor Green }

Write-Host "[3/4] Checking Ollama..." -ForegroundColor Cyan
$ollama = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
if ($ollama) {
    Write-Host "  Ollama running" -ForegroundColor Green
} else {
    Write-Host "  Starting Ollama..." -ForegroundColor Yellow
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

Write-Host "[4/4] Starting services..." -ForegroundColor Cyan
$ports = @(8000, 8001)
foreach ($port in $ports) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conn) {
        Stop-Process -Id ($conn.OwningProcess | Select-Object -First 1) -Force -ErrorAction SilentlyContinue
    }
}

$botJob = Start-Job -ScriptBlock {
    param($v, $d)
    Set-Location $d
    & "$v\Scripts\python.exe" main.py --mode full --autostart --port 8000
} -ArgumentList (Resolve-Path ".venv"), (Get-Location)

Start-Sleep -Seconds 3

$dashJob = Start-Job -ScriptBlock {
    param($v, $d)
    Set-Location $d
    & "$v\Scripts\python.exe" -m api.dashboard_backend
} -ArgumentList (Resolve-Path ".venv"), (Get-Location)

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "APEX SYSTEM READY" -ForegroundColor Green
Write-Host "  Bot:       http://localhost:8000" -ForegroundColor Cyan
Write-Host "  Dashboard: http://localhost:8001" -ForegroundColor Cyan
Write-Host ""