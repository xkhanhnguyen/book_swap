# ============================================================
#  Registers a Windows Task Scheduler job that runs
#  fetch_books every other Friday at 3:00 AM.
#
#  Run once (as Administrator) in PowerShell:
#    .\bin\setup_task_scheduler.ps1
# ============================================================

$taskName   = "BookSwap_FetchBooks"
$batFile    = "C:\Users\KhanhNguyen\projects\book_swap\bin\schedule_fetch_books.bat"
$logDir     = "C:\Users\KhanhNguyen\projects\book_swap\logs"

# Create logs directory if it doesn't exist
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
    Write-Host "Created logs directory: $logDir"
}

# Remove existing task if present
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Removed existing task: $taskName"
}

$action  = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$batFile`""

# Every other Friday at 3:00 AM (WeeksInterval 2 = bi-weekly)
$trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 2 -DaysOfWeek Friday -At "03:00"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -RunLevel Highest `
    -Description "Fetches new books from Open Library API into BookSwap database (every other Friday)" | Out-Null

Write-Host "Task '$taskName' registered. Runs every other Friday at 03:00 AM."
Write-Host "Logs: $logDir\fetch_books.log"
Write-Host ""
Write-Host "To run it now manually:"
Write-Host "  Start-ScheduledTask -TaskName '$taskName'"
