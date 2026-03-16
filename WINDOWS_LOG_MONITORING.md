# Windows PowerShell Log Monitoring Commands

## Quick Reference

### Monitor Logs in Real-Time (like `tail -f`)

```powershell
# Monitor latest log file in real-time
Get-Content logs\apex_*.log -Wait -Tail 20

# Filter for LLM Tier messages
Get-Content logs\apex_*.log -Wait -Tail 50 | Select-String "LLM Tier"

# Filter for specific agent
Get-Content logs\apex_*.log -Wait -Tail 50 | Select-String "market_analyst"

# Filter for errors
Get-Content logs\apex_*.log -Wait -Tail 50 | Select-String "ERROR|WARN"
```

### View Last N Lines (like `tail`)

```powershell
# Last 20 lines
Get-Content logs\apex_*.log -Tail 20

# Last 50 lines
Get-Content logs\apex_*.log -Tail 50

# Last 100 lines with LLM Tier info
Get-Content logs\apex_*.log -Tail 100 | Select-String "LLM Tier"
```

### Search Logs (like `grep`)

```powershell
# Search for "LLM Tier" in all logs
Select-String -Path "logs\apex_*.log" -Pattern "LLM Tier"

# Search for Ollama usage
Select-String -Path "logs\apex_*.log" -Pattern "Ollama"

# Search for errors
Select-String -Path "logs\apex_*.log" -Pattern "ERROR"

# Search with context (2 lines before and after)
Select-String -Path "logs\apex_*.log" -Pattern "LLM Tier" -Context 2,2
```

### Count LLM Tier Usage

```powershell
# Count which tier is used most
Select-String -Path "logs\apex_*.log" -Pattern "LLM Tier" | 
    Group-Object Line | 
    Sort-Object Count -Descending | 
    Select-Object Count, Name

# Simpler count
(Select-String -Path "logs\apex_*.log" -Pattern "Tier 1.*Ollama").Count
(Select-String -Path "logs\apex_*.log" -Pattern "Tier 2.*Groq").Count
(Select-String -Path "logs\apex_*.log" -Pattern "Tier 3.*DeepSeek").Count
```

### View Today's Log

```powershell
# Get today's date in format YYYY-MM-DD
$today = Get-Date -Format "yyyy-MM-dd"

# View today's log
Get-Content "logs\apex_$today.log" -Tail 50

# Monitor today's log in real-time
Get-Content "logs\apex_$today.log" -Wait -Tail 20
```

### View Latest Log File

```powershell
# Get the most recent log file
$latestLog = Get-ChildItem logs\apex_*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1

# View it
Get-Content $latestLog.FullName -Tail 50

# Monitor it in real-time
Get-Content $latestLog.FullName -Wait -Tail 20
```

## Common Monitoring Tasks

### 1. Monitor Bot Startup

```powershell
# Watch for startup messages
Get-Content logs\apex_*.log -Wait -Tail 50 | Select-String "APEX|Starting|Initialized"
```

### 2. Monitor LLM Usage

```powershell
# Real-time LLM tier monitoring
Get-Content logs\apex_*.log -Wait -Tail 50 | Select-String "LLM Tier|Ollama|Groq|DeepSeek|Claude"
```

### 3. Monitor Trading Signals

```powershell
# Watch for trade signals
Get-Content logs\apex_*.log -Wait -Tail 50 | Select-String "SIGNAL|TRADE|BUY|SELL"
```

### 4. Monitor Errors and Warnings

```powershell
# Watch for problems
Get-Content logs\apex_*.log -Wait -Tail 50 | Select-String "ERROR|WARN|FAIL"
```

### 5. Monitor Specific Agent

```powershell
# Watch Market Analyst
Get-Content logs\apex_*.log -Wait -Tail 50 | Select-String "market_analyst"

# Watch Risk Manager
Get-Content logs\apex_*.log -Wait -Tail 50 | Select-String "risk_manager"
```

## Advanced Filtering

### Multiple Patterns (OR)

```powershell
# Match any of these patterns
Get-Content logs\apex_*.log -Wait -Tail 50 | Select-String "ERROR|WARN|FAIL|TIMEOUT"
```

### Exclude Patterns

```powershell
# Show all except INFO messages
Get-Content logs\apex_*.log -Tail 100 | Select-String -Pattern "INFO" -NotMatch
```

### Case-Sensitive Search

```powershell
# Case-sensitive search
Select-String -Path "logs\apex_*.log" -Pattern "ERROR" -CaseSensitive
```

### With Timestamps

```powershell
# Show with line numbers
Select-String -Path "logs\apex_*.log" -Pattern "LLM Tier" | 
    Select-Object LineNumber, Line
```

## Useful Aliases

Add these to your PowerShell profile for quick access:

```powershell
# Edit profile
notepad $PROFILE

# Add these functions:
function Watch-ApexLog {
    Get-Content logs\apex_*.log -Wait -Tail 20
}

function Watch-LLM {
    Get-Content logs\apex_*.log -Wait -Tail 50 | Select-String "LLM Tier"
}

function Watch-Errors {
    Get-Content logs\apex_*.log -Wait -Tail 50 | Select-String "ERROR|WARN"
}

function Count-LLMTiers {
    Write-Host "Tier 1 (Ollama):" (Select-String -Path "logs\apex_*.log" -Pattern "Tier 1.*Ollama").Count
    Write-Host "Tier 2 (Groq):" (Select-String -Path "logs\apex_*.log" -Pattern "Tier 2.*Groq").Count
    Write-Host "Tier 3 (DeepSeek):" (Select-String -Path "logs\apex_*.log" -Pattern "Tier 3.*DeepSeek").Count
    Write-Host "Tier 4 (Claude):" (Select-String -Path "logs\apex_*.log" -Pattern "Tier 4.*Claude").Count
}

# Then use like:
# Watch-ApexLog
# Watch-LLM
# Count-LLMTiers
```

## Color Output (Optional)

```powershell
# Highlight errors in red
Get-Content logs\apex_*.log -Tail 50 | ForEach-Object {
    if ($_ -match "ERROR") {
        Write-Host $_ -ForegroundColor Red
    } elseif ($_ -match "WARN") {
        Write-Host $_ -ForegroundColor Yellow
    } elseif ($_ -match "LLM Tier 1") {
        Write-Host $_ -ForegroundColor Green
    } else {
        Write-Host $_
    }
}
```

## Export to File

```powershell
# Save LLM usage to file
Select-String -Path "logs\apex_*.log" -Pattern "LLM Tier" | 
    Out-File "llm_usage_report.txt"

# Save errors to file
Select-String -Path "logs\apex_*.log" -Pattern "ERROR|WARN" | 
    Out-File "errors_report.txt"
```

## Quick Commands for Your Use Case

### Check if Ollama is Primary

```powershell
# Count Ollama usage
$ollama = (Select-String -Path "logs\apex_*.log" -Pattern "Tier 1.*Ollama").Count
$total = (Select-String -Path "logs\apex_*.log" -Pattern "LLM Tier").Count
$percentage = [math]::Round(($ollama / $total) * 100, 2)
Write-Host "Ollama usage: $ollama / $total ($percentage%)"
```

### Monitor Bot in Real-Time

```powershell
# Open in new window and monitor
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Get-Content logs\apex_*.log -Wait -Tail 20"
```

### View Last Hour of Activity

```powershell
# Get logs from last hour
$oneHourAgo = (Get-Date).AddHours(-1)
Get-Content logs\apex_*.log | Where-Object {
    $_ -match "\d{2}:\d{2}:\d{2}" -and 
    [datetime]::ParseExact($matches[0], "HH:mm:ss", $null) -gt $oneHourAgo
}
```

## Comparison: Linux vs Windows

| Linux Command | Windows PowerShell Equivalent |
|--------------|-------------------------------|
| `tail -f file.log` | `Get-Content file.log -Wait -Tail 20` |
| `tail -n 50 file.log` | `Get-Content file.log -Tail 50` |
| `grep "pattern" file.log` | `Select-String -Path file.log -Pattern "pattern"` |
| `grep -i "pattern"` | `Select-String -Pattern "pattern"` (case-insensitive by default) |
| `grep -v "pattern"` | `Select-String -Pattern "pattern" -NotMatch` |
| `wc -l` | `Measure-Object -Line` |
| `cat file.log` | `Get-Content file.log` |
| `head -n 20` | `Get-Content file.log -TotalCount 20` |

## Tips

1. **Use Tab Completion**: Type `Get-Content logs\apex` and press Tab to auto-complete

2. **Stop Monitoring**: Press `Ctrl+C` to stop `-Wait` commands

3. **Multiple Windows**: Open multiple PowerShell windows to monitor different things simultaneously

4. **Save Commands**: Create `.ps1` scripts for frequently used commands

5. **Aliases**: PowerShell has built-in aliases:
   - `gc` = `Get-Content`
   - `select` = `Select-Object`
   - `where` = `Where-Object`

## Example Monitoring Session

```powershell
# Terminal 1: Monitor all logs
Get-Content logs\apex_*.log -Wait -Tail 20

# Terminal 2: Monitor LLM usage
Get-Content logs\apex_*.log -Wait -Tail 50 | Select-String "LLM Tier"

# Terminal 3: Monitor errors
Get-Content logs\apex_*.log -Wait -Tail 50 | Select-String "ERROR|WARN"

# Terminal 4: Check LLM tier distribution
while ($true) {
    Clear-Host
    Write-Host "=== LLM Tier Usage ===" -ForegroundColor Cyan
    $t1 = (Select-String -Path "logs\apex_*.log" -Pattern "Tier 1.*Ollama").Count
    $t2 = (Select-String -Path "logs\apex_*.log" -Pattern "Tier 2.*Groq").Count
    $t3 = (Select-String -Path "logs\apex_*.log" -Pattern "Tier 3.*DeepSeek").Count
    $t4 = (Select-String -Path "logs\apex_*.log" -Pattern "Tier 4.*Claude").Count
    Write-Host "Tier 1 (Ollama):  $t1" -ForegroundColor Green
    Write-Host "Tier 2 (Groq):    $t2" -ForegroundColor Yellow
    Write-Host "Tier 3 (DeepSeek): $t3" -ForegroundColor Cyan
    Write-Host "Tier 4 (Claude):  $t4" -ForegroundColor Magenta
    Start-Sleep -Seconds 5
}
```

## Quick Start

**To monitor your bot right now:**

```powershell
# 1. Open PowerShell in your project directory
cd C:\path\to\your\apex\bot

# 2. Monitor logs in real-time
Get-Content logs\apex_*.log -Wait -Tail 20

# 3. In another PowerShell window, monitor LLM usage
Get-Content logs\apex_*.log -Wait -Tail 50 | Select-String "LLM Tier"
```

That's it! You're now monitoring your bot on Windows. 🎉
