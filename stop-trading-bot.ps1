# Stop APEX Trading Bot and Dashboard Backend

Write-Host "Stopping APEX Trading Bot services..." -ForegroundColor Yellow

# Stop Python processes on ports 8000 and 8001
$processes = Get-NetTCPConnection -LocalPort 8000,8001 -ErrorAction SilentlyContinue | 
    Select-Object -ExpandProperty OwningProcess -Unique

if ($processes) {
    foreach ($pid in $processes) {
        try {
            $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
            if ($proc) {
                Write-Host "  Stopping process: $($proc.ProcessName) (PID: $pid)" -ForegroundColor Cyan
                Stop-Process -Id $pid -Force
            }
        } catch {
            Write-Host "  Could not stop PID $pid" -ForegroundColor Red
        }
    }
    Write-Host "All services stopped." -ForegroundColor Green
} else {
    Write-Host "No services found running on ports 8000 or 8001." -ForegroundColor Yellow
}
