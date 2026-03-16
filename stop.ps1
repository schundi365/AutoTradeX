# APEX Trading System - Stop

Write-Host "Stopping APEX..." -ForegroundColor Yellow

$conn = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    $pid = $conn.OwningProcess
    Stop-Process -Id $pid -Force
    Write-Host "APEX stopped (PID: $pid)" -ForegroundColor Green
} else {
    Write-Host "APEX is not running" -ForegroundColor Yellow
}
