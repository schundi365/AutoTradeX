# APEX Dashboard Startup Script (PowerShell)
# Starts both backend (port 8001) and frontend (port 3000) servers

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Starting APEX Trading Dashboard" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get the script directory (project root)
$ProjectRoot = $PSScriptRoot

# Function to kill processes on a specific port
function Stop-ProcessOnPort {
    param([int]$Port)
    
    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }
    
    if ($connections) {
        foreach ($conn in $connections) {
            $processId = $conn.OwningProcess
            if ($processId -gt 0) {
                try {
                    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
                    if ($process) {
                        Write-Host "   Stopping existing process on port $Port (PID: $processId)..." -ForegroundColor Yellow
                        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
                        Start-Sleep -Seconds 1
                    }
                } catch {
                    # Process might have already stopped
                }
            }
        }
    }
}

# Check and stop existing instances
Write-Host "[0/3] Checking for existing instances..." -ForegroundColor Yellow
Stop-ProcessOnPort -Port 8001
Stop-ProcessOnPort -Port 3000
Write-Host "   Cleanup complete" -ForegroundColor Gray
Write-Host ""

# Check if virtual environment exists
$VenvPath = Join-Path $ProjectRoot ".venv"
if (-Not (Test-Path $VenvPath)) {
    Write-Host "ERROR: Virtual environment not found at $VenvPath" -ForegroundColor Red
    Write-Host "Please create it first: python -m venv .venv" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if node_modules exists
$NodeModulesPath = Join-Path $ProjectRoot "frontend\dashboard\node_modules"
if (-Not (Test-Path $NodeModulesPath)) {
    Write-Host "WARNING: Node modules not found. Installing..." -ForegroundColor Yellow
    Set-Location (Join-Path $ProjectRoot "frontend\dashboard")
    npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to install npm dependencies" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
    Set-Location $ProjectRoot
}

Write-Host "[1/3] Starting Backend Server (Port 8001)..." -ForegroundColor Green

# Start Backend in new window
$BackendScript = @"
`$Host.UI.RawUI.WindowTitle = 'APEX Backend (Port 8001)'
Write-Host '========================================' -ForegroundColor Cyan
Write-Host '  APEX Backend Server' -ForegroundColor Cyan
Write-Host '  Port: 8001' -ForegroundColor Cyan
Write-Host '  API Docs: http://localhost:8001/docs' -ForegroundColor Cyan
Write-Host '========================================' -ForegroundColor Cyan
Write-Host ''
Set-Location '$ProjectRoot'
& '$VenvPath\Scripts\Activate.ps1'
python -m api.dashboard_backend
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $BackendScript

Write-Host "   Backend starting..." -ForegroundColor Gray
Write-Host ""

# Wait for backend to start
Write-Host "[2/3] Waiting for backend to be ready..." -ForegroundColor Green
Start-Sleep -Seconds 5

Write-Host "[3/3] Starting Frontend Server (Port 3000)..." -ForegroundColor Green

# Start Frontend in new window
$FrontendScript = @"
`$Host.UI.RawUI.WindowTitle = 'APEX Frontend (Port 3000)'
Write-Host '========================================' -ForegroundColor Cyan
Write-Host '  APEX Frontend Server' -ForegroundColor Cyan
Write-Host '  Port: 3000' -ForegroundColor Cyan
Write-Host '  Dashboard: http://localhost:3000' -ForegroundColor Cyan
Write-Host '========================================' -ForegroundColor Cyan
Write-Host ''
Set-Location '$ProjectRoot\frontend\dashboard'
npm run dev
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $FrontendScript

Write-Host "   Frontend starting..." -ForegroundColor Gray
Write-Host ""

# Wait for frontend to start
Write-Host "Waiting for servers to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Dashboard Started Successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Backend:  http://localhost:8001" -ForegroundColor Cyan
Write-Host "API Docs: http://localhost:8001/docs" -ForegroundColor Cyan
Write-Host "Frontend: http://localhost:3000" -ForegroundColor Cyan
Write-Host ""
Write-Host "Opening dashboard in browser..." -ForegroundColor Yellow
Start-Sleep -Seconds 2

# Open browser
Start-Process "http://localhost:3000"

Write-Host ""
Write-Host "Dashboard is running!" -ForegroundColor Green
Write-Host "Close the backend and frontend terminal windows to stop." -ForegroundColor Gray
Write-Host ""
Read-Host "Press Enter to close this window"
