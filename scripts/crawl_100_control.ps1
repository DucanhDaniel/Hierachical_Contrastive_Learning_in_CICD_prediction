# Điều khiển riêng task 85 repo mới; chạy vài giờ mỗi phiên rồi tiếp tục từ checkpoint.
param([ValidateSet('Status', 'Pause', 'Resume')][string]$Action = 'Status')
$ErrorActionPreference = 'Stop'
$workspace = Split-Path $PSScriptRoot -Parent
Set-Location $workspace
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUNBUFFERED = '1'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$statePath = Join-Path $workspace 'data/crawl_100_state.json'
$state = $null
# File .part hợp lệ có thể mới hơn khi atomic replace bị reader giữ khóa.
$snapshots = @(Get-Item -LiteralPath $statePath, "$statePath.part" -ErrorAction SilentlyContinue | Sort-Object LastWriteTimeUtc -Descending)
foreach ($snapshot in $snapshots) {
    try {
        $state = Get-Content -Raw -Encoding utf8 -LiteralPath $snapshot.FullName | ConvertFrom-Json
        break
    } catch { Write-Warning "Không đọc được snapshot $($snapshot.Name); thử bản còn lại." }
}
$owned = $null
$child = $null
if ($state) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($state.pid)"
    if ($proc -and $proc.CommandLine -like '*project3.pipeline.crawl_100*') { $owned = $proc }
    if ($state.child_pid) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($state.child_pid)"
        if ($proc -and $proc.CommandLine -like '*project3.crawl.gha*') { $child = $proc }
    }
}
if ($Action -eq 'Status') {
    Write-Output "Task 100 repo: $(if ($owned) { 'running, PID ' + $owned.ProcessId } else { 'stopped' })"
    if ($child -and -not $owned) { Write-Output "Crawler con còn chạy: PID $($child.ProcessId); dùng Pause trước khi Resume." }
    if ($state) { $state | ConvertTo-Json }
} elseif ($Action -eq 'Pause') {
    # Chỉ kill cây PID có command line đã xác nhận thuộc worker task này.
    foreach ($proc in @($owned, $child)) {
        if ($proc -and (Get-Process -Id $proc.ProcessId -ErrorAction SilentlyContinue)) {
            & taskkill /PID $proc.ProcessId /T /F | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'Could not stop task process tree' }
        }
    }
    if ($state) {
        $state.status = 'paused'
        $state.updated = [DateTimeOffset]::UtcNow.ToString('o')
        $state.child_pid = $null
        $state.keep_awake = $false
        $state | ConvertTo-Json | Set-Content -Encoding utf8 -LiteralPath $statePath
    }
    & .venv/Scripts/python.exe -m project3.crawl.checkpoint --repair
    if ($LASTEXITCODE -ne 0) { throw 'Checkpoint cần kiểm tra trước khi Resume' }
    Write-Output 'Đã tạm dừng. Run/jobs/log hoàn tất và kết quả từng repo được giữ để tiếp tục lần sau.'
} else {
    if ($owned -or $child) { throw 'Task còn chạy; không khởi chạy trùng. Dùng Status hoặc Pause.' }
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $worker = Start-Process -FilePath (Join-Path $workspace '.venv/Scripts/python.exe') `
        -ArgumentList '-u', '-m', 'project3.pipeline.crawl_100' -WorkingDirectory $workspace -WindowStyle Hidden `
        -RedirectStandardOutput "data/logs/crawl_100_runner_$stamp.log" `
        -RedirectStandardError "data/logs/crawl_100_runner_$stamp.err.log" -PassThru
    Write-Output "Đã tiếp tục task, launcher PID $($worker.Id). State: data/crawl_100_state.json"
}
