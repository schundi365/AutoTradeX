# ═══════════════════════════════════════════════════════
#  APEX Bot — Ollama Auto-Start Script
#  Ensures Ollama service is running before starting the bot
# ═══════════════════════════════════════════════════════

Write-Host "🤖 APEX Bot - Ollama Startup Script" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan

# Check if Ollama is already running
$ollamaProcess = Get-Process -Name "ollama" -ErrorAction SilentlyContinue

if ($ollamaProcess) {
    Write-Host "✓ Ollama is already running (PID: $($ollamaProcess.Id))" -ForegroundColor Green
} else {
    Write-Host "⚠ Ollama is not running. Starting Ollama service..." -ForegroundColor Yellow
    
    # Try to start Ollama as a background process
    try {
        Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Seconds 3
        
        # Verify it started
        $ollamaProcess = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
        if ($ollamaProcess) {
            Write-Host "✓ Ollama started successfully (PID: $($ollamaProcess.Id))" -ForegroundColor Green
        } else {
            Write-Host "✗ Failed to start Ollama. Please start it manually with: ollama serve" -ForegroundColor Red
            exit 1
        }
    } catch {
        Write-Host "✗ Error starting Ollama: $_" -ForegroundColor Red
        Write-Host "Please ensure Ollama is installed and in your PATH" -ForegroundColor Yellow
        Write-Host "Install from: https://ollama.ai/download" -ForegroundColor Yellow
        exit 1
    }
}

# Check if the apex-trader model is available
Write-Host "`nChecking for apex-trader model..." -ForegroundColor Cyan
try {
    $models = ollama list 2>&1
    if ($models -match "apex-trader") {
        Write-Host "✓ apex-trader model is available" -ForegroundColor Green
    } else {
        Write-Host "⚠ apex-trader model not found. Available models:" -ForegroundColor Yellow
        Write-Host $models
        Write-Host "`nTo create the apex-trader model, run:" -ForegroundColor Yellow
        Write-Host "  ollama create apex-trader -f path/to/Modelfile" -ForegroundColor White
    }
} catch {
    Write-Host "⚠ Could not check models: $_" -ForegroundColor Yellow
}

# Test Ollama API endpoint
Write-Host "`nTesting Ollama API endpoint..." -ForegroundColor Cyan
try {
    $response = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get -TimeoutSec 5
    Write-Host "✓ Ollama API is responding" -ForegroundColor Green
} catch {
    Write-Host "✗ Ollama API is not responding: $_" -ForegroundColor Red
    Write-Host "Please check if Ollama is running on port 11434" -ForegroundColor Yellow
    exit 1
}

Write-Host "`n✓ Ollama is ready for APEX Bot" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
