# APEX Dashboard Stop Script (PowerShell)
# Stops both backend and frontend servers

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Stopping APEX Trading Dashboard" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Function to kill processes on a specific port
function Stop-ProcessOnPort {
    param(
        [int]$Port,
        [string]$Name
    )
    
    Write-Host "Stopping $Name (Port $Port)..." -ForegroundColor Yellow
    
    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }
    
    if ($connections) {
        $stopped = 0
        foreach ($conn in $connections) {
            $processId = $conn.OwningProcess
            if ($processId -gt 0) {
                try {
                    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
                    if ($process) {
                        Write-Host "   Stopping process (PID: $processId)..." -ForegroundColor Gray
                        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
                        $stopped++
                    }
                } catch {
                    # Process might have already stopped
                }
            }
        }
        
        if ($stopped -gt 0) {
            Write-Host "   Stopped $stopped process(es)" -ForegroundColor Green
        } else {
            Write-Host "   No processes found" -ForegroundColor Gray
        }
    } else {
        Write-Host "   No processes running on port $Port" -ForegroundColor Gray
    }
    Write-Host ""
}

# Stop backend
Stop-ProcessOnPort -Port 8001 -Name "Backend Server"

# Stop frontend
Stop-ProcessOnPort -Port 3000 -Name "Frontend Server"

# Also kill any Python processes running dashboard_backend
Write-Host "Checking for dashboard_backend processes..." -ForegroundColor Yellow
$dashboardProcesses = Get-WmiObject Win32_Process -Filter "name='python.exe' OR name='python3.exe' OR name='python3.12.exe'" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*dashboard_backend*"
}

if ($dashboardProcesses) {
    foreach ($proc in $dashboardProcesses) {
        Write-Host "   Stopping dashboard_backend (PID: $($proc.ProcessId))..." -ForegroundColor Gray
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Write-Host "   Stopped $($dashboardProcesses.Count) dashboard_backend process(es)" -ForegroundColor Green
} else {
    Write-Host "   No dashboard_backend processes found" -ForegroundColor Gray
}
Write-Host ""

# Also kill any node processes running vite
Write-Host "Checking for Vite dev server processes..." -ForegroundColor Yellow
$viteProcesses = Get-WmiObject Win32_Process -Filter "name='node.exe'" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*vite*"
}

if ($viteProcesses) {
    foreach ($proc in $viteProcesses) {
        Write-Host "   Stopping Vite server (PID: $($proc.ProcessId))..." -ForegroundColor Gray
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Write-Host "   Stopped $($viteProcesses.Count) Vite process(es)" -ForegroundColor Green
} else {
    Write-Host "   No Vite processes found" -ForegroundColor Gray
}
Write-Host ""

Write-Host "========================================" -ForegroundColor Green
Write-Host "  Dashboard Stopped Successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

Read-Host "Press Enter to close this window"
