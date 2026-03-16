# APEX Ollama Performance Optimization Script
# Applies quick fixes to reduce latency from 8s to <2s

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host " APEX Ollama Performance Optimization" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

# Check if Ollama is running
Write-Host "[1/5] Checking Ollama status..." -ForegroundColor Yellow
$ollamaRunning = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
if (-not $ollamaRunning) {
    Write-Host "[X] Ollama is not running!" -ForegroundColor Red
    Write-Host "  Start Ollama first: ollama serve" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Ollama is running" -ForegroundColor Green

# Check if model exists
Write-Host ""
Write-Host "[2/5] Checking apex-trader model..." -ForegroundColor Yellow
$modelCheck = ollama list | Select-String "apex-trader"
if (-not $modelCheck) {
    Write-Host "[X] apex-trader model not found!" -ForegroundColor Red
    Write-Host "  Available models:" -ForegroundColor Yellow
    ollama list
    exit 1
}
Write-Host "[OK] apex-trader model found" -ForegroundColor Green

# Load model into memory
Write-Host ""
Write-Host "[3/5] Loading model into memory (this may take 5-10 seconds)..." -ForegroundColor Yellow
$loadStart = Get-Date
ollama run apex-trader "test" | Out-Null
$loadTime = (Get-Date) - $loadStart
Write-Host "[OK] Model loaded in $($loadTime.TotalSeconds.ToString('F1'))s" -ForegroundColor Green

# Check if model is loaded
Write-Host ""
Write-Host "[4/5] Verifying model is in memory..." -ForegroundColor Yellow
$psOutput = ollama ps
Write-Host $psOutput
if ($psOutput -match "apex-trader") {
    Write-Host "[OK] Model is loaded and ready" -ForegroundColor Green
}
else {
    Write-Host "[!] Model may not be loaded properly" -ForegroundColor Yellow
}

# Create optimized Modelfile
Write-Host ""
Write-Host "[5/5] Creating optimized model configuration..." -ForegroundColor Yellow

$modelfile = @"
FROM apex-trader
PARAMETER num_ctx 2048
PARAMETER num_predict 512
PARAMETER temperature 0.1
PARAMETER repeat_penalty 1.1
"@

$modelfile | Out-File -FilePath "Modelfile.fast" -Encoding UTF8
Write-Host "[OK] Created Modelfile.fast" -ForegroundColor Green

Write-Host ""
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host " Optimization Complete!" -ForegroundColor Green
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. (Optional) Create faster model variant:" -ForegroundColor White
Write-Host "   ollama create apex-trader-fast -f Modelfile.fast" -ForegroundColor Cyan
Write-Host ""
Write-Host "2. (Optional) Update .env to use faster model:" -ForegroundColor White
Write-Host "   OLLAMA_MODEL=apex-trader-fast" -ForegroundColor Cyan
Write-Host ""
Write-Host "3. Keep model warm (prevents cold starts):" -ForegroundColor White
Write-Host "   python scripts/keep_ollama_warm.py" -ForegroundColor Cyan
Write-Host ""
Write-Host "4. Test latency in dashboard:" -ForegroundColor White
Write-Host "   http://localhost:8000 -> APEX Health tab" -ForegroundColor Cyan
Write-Host ""
Write-Host "Expected Results:" -ForegroundColor Yellow
Write-Host "  - First call after idle: 5-8 seconds (cold start)" -ForegroundColor White
Write-Host "  - Subsequent calls: 1-2 seconds (warm)" -ForegroundColor White
Write-Host "  - With keep-warm script: Always 1-2 seconds" -ForegroundColor White
Write-Host ""
