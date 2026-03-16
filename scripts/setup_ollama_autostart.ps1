# ═══════════════════════════════════════════════════════
#  APEX Bot — Setup Ollama Auto-Start on Windows
#  Creates a scheduled task to start Ollama on system boot
# ═══════════════════════════════════════════════════════

Write-Host "🤖 APEX Bot - Ollama Auto-Start Setup" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "✗ This script requires Administrator privileges" -ForegroundColor Red
    Write-Host "Please run PowerShell as Administrator and try again" -ForegroundColor Yellow
    exit 1
}

# Check if Ollama is installed
$ollamaPath = (Get-Command ollama -ErrorAction SilentlyContinue).Source
if (-not $ollamaPath) {
    Write-Host "✗ Ollama is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Please install Ollama from: https://ollama.ai/download" -ForegroundColor Yellow
    exit 1
}

Write-Host "✓ Found Ollama at: $ollamaPath" -ForegroundColor Green

# Task name
$taskName = "OllamaAutoStart"

# Check if task already exists
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($existingTask) {
    Write-Host "⚠ Task '$taskName' already exists" -ForegroundColor Yellow
    $response = Read-Host "Do you want to recreate it? (y/n)"
    if ($response -ne "y") {
        Write-Host "Setup cancelled" -ForegroundColor Yellow
        exit 0
    }
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "✓ Removed existing task" -ForegroundColor Green
}

# Create scheduled task action
$action = New-ScheduledTaskAction -Execute "ollama" -Argument "serve"

# Create trigger (at system startup)
$trigger = New-ScheduledTaskTrigger -AtStartup

# Create settings
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

# Create principal (run as SYSTEM with highest privileges)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# Register the task
try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Auto-start Ollama service for APEX Trading Bot" | Out-Null
    
    Write-Host "✓ Scheduled task created successfully" -ForegroundColor Green
    Write-Host "`nTask Details:" -ForegroundColor Cyan
    Write-Host "  Name: $taskName" -ForegroundColor White
    Write-Host "  Trigger: At system startup" -ForegroundColor White
    Write-Host "  Action: ollama serve" -ForegroundColor White
    Write-Host "  Run as: SYSTEM" -ForegroundColor White
    
    # Start the task now
    Write-Host "`nStarting Ollama now..." -ForegroundColor Cyan
    Start-ScheduledTask -TaskName $taskName
    Start-Sleep -Seconds 3
    
    # Verify Ollama is running
    $ollamaProcess = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
    if ($ollamaProcess) {
        Write-Host "✓ Ollama is now running (PID: $($ollamaProcess.Id))" -ForegroundColor Green
    } else {
        Write-Host "⚠ Ollama task started but process not detected" -ForegroundColor Yellow
        Write-Host "Check Task Scheduler for errors" -ForegroundColor Yellow
    }
    
    Write-Host "`n✓ Setup complete! Ollama will now start automatically on system boot" -ForegroundColor Green
    Write-Host "`nTo manage the task:" -ForegroundColor Cyan
    Write-Host "  View: Get-ScheduledTask -TaskName '$taskName'" -ForegroundColor White
    Write-Host "  Start: Start-ScheduledTask -TaskName '$taskName'" -ForegroundColor White
    Write-Host "  Stop: Stop-ScheduledTask -TaskName '$taskName'" -ForegroundColor White
    Write-Host "  Remove: Unregister-ScheduledTask -TaskName '$taskName'" -ForegroundColor White
    
} catch {
    Write-Host "✗ Failed to create scheduled task: $_" -ForegroundColor Red
    exit 1
}

Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
