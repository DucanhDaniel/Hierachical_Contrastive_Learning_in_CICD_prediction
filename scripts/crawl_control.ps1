# Status / Pause / Resume cho hai worker; chỉ dừng cây tiến trình của repo này.
param([ValidateSet('Status', 'Pause', 'Resume')][string]$Action = 'Status')
$ErrorActionPreference = 'Stop'
$workspace = Split-Path $PSScriptRoot -Parent
Set-Location $workspace
$env:PYTHONIOENCODING = 'utf-8'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:UV_CACHE_DIR = Join-Path $workspace '.uv-cache'
$workers = @(
    @{ pid = 'data/crawl_expand.pid'; script = 'crawl_expand.ps1'; state = 'data/crawl_expand_state.json' },
    @{ pid = 'data/crawl_extra_push.pid'; script = 'crawl_extra_push.ps1'; state = 'data/crawl_extra_push_state.json' },
    @{ pid = 'data/crawl_finish.pid'; script = 'crawl_finish.ps1'; state = $null }
)
function Owned-Process($worker, $processes) {
    if (-not (Test-Path -LiteralPath $worker.pid)) { return $null }
    $workerId = [int](Get-Content -LiteralPath $worker.pid)
    $proc = $processes | Where-Object { $_.ProcessId -eq $workerId }
    $expected = Join-Path $workspace (Join-Path 'scripts' $worker.script)
    if ($proc -and $proc.CommandLine -like "*$expected*") { return $proc }
    return $null
}
function Stop-Tree($workerId, $processes) {
    foreach ($child in ($processes | Where-Object { $_.ParentProcessId -eq $workerId })) {
        Stop-Tree $child.ProcessId $processes
    }
    Stop-Process -Id $workerId -ErrorAction SilentlyContinue
}
function Start-Worker($worker, $extraArgs = @()) {
    $path = Join-Path $workspace (Join-Path 'scripts' $worker.script)
    $launchArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $path) + $extraArgs
    $proc = Start-Process powershell -WindowStyle Hidden -ArgumentList $launchArgs -WorkingDirectory $workspace -PassThru
    $proc.Id | Set-Content -LiteralPath $worker.pid
    Write-Output "$($worker.script): PID $($proc.Id)"
}
$processes = @(Get-CimInstance Win32_Process)
if ($Action -eq 'Pause') {
    $pausedAt = Get-Date
    $active = @($workers | Where-Object { $null -ne (Owned-Process $_ $processes) })
    # Worker đầu tiên đã chạy trước khi có cơ chế ghi log atomic: giữ bản sao các log mới ghi.
    foreach ($worker in $active) {
        $proc = Owned-Process $worker $processes
        Stop-Tree $proc.ProcessId $processes
        if ($worker.state -and (Test-Path -LiteralPath $worker.state)) {
            $state = Get-Content -Raw -Encoding utf8 $worker.state | ConvertFrom-Json
            $state.status = 'paused'
            $state.updated = Get-Date -Format o
            $state | ConvertTo-Json | Set-Content -Encoding utf8 -LiteralPath $worker.state
        }
    }
    $recent = @(Get-ChildItem data/crawl_pr,data/validate -Filter '*.txt' -Recurse -File |
        Where-Object { $_.Directory.Name -eq 'logs' -and $_.LastWriteTime -ge $pausedAt.AddSeconds(-10) })
    foreach ($file in $recent) {
        if (Test-Path -LiteralPath $file.FullName) {
            # Giữ dữ liệu thay vì xóa; crawler sẽ tải lại vài log có thể đang ghi lúc dừng.
            $backupPath = $file.FullName + '.interrupted.' + $pausedAt.ToUniversalTime().ToString('yyyyMMddTHHmmssfffffffZ')
            $resolvedSource = [System.IO.Path]::GetFullPath($file.FullName)
            $resolvedBackup = [System.IO.Path]::GetFullPath($backupPath)
            $dataPrefix = [System.IO.Path]::GetFullPath((Join-Path $workspace 'data')) + [System.IO.Path]::DirectorySeparatorChar
            if (-not $resolvedSource.StartsWith($dataPrefix, [System.StringComparison]::OrdinalIgnoreCase) -or
                -not $resolvedBackup.StartsWith($dataPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw 'Đường dẫn backup nằm ngoài data; không di chuyển file.'
            }
            Move-Item -LiteralPath $file.FullName -Destination $backupPath
        }
    }
    uv run --no-sync python -m project3.crawl.checkpoint --repair
    if ($LASTEXITCODE -ne 0) { throw 'Checkpoint cần kiểm tra trước khi resume' }
    Write-Output 'Đã tạm dừng; dữ liệu hoàn tất được giữ nguyên.'
} elseif ($Action -eq 'Resume') {
    if (@($workers | Where-Object { $null -ne (Owned-Process $_ $processes) }).Count -gt 0) {
        throw 'Còn worker đang chạy; dùng Status để kiểm tra, không khởi chạy trùng.'
    }
    uv run --no-sync python -m project3.crawl.checkpoint --repair
    if ($LASTEXITCODE -ne 0) { throw 'Checkpoint cần kiểm tra trước khi resume' }
    if (Test-Path data/crawl_expand_state.json) {
        $state = Get-Content -Raw -Encoding utf8 data/crawl_expand_state.json | ConvertFrom-Json
        $state.status = 'resuming'
        $state | ConvertTo-Json | Set-Content -Encoding utf8 data/crawl_expand_state.json
    }
    Start-Worker $workers[0]
    if (Test-Path data/crawl_extra_push_state.json) {
        $extraState = Get-Content -Raw -Encoding utf8 data/crawl_extra_push_state.json | ConvertFrom-Json
        if ($extraState.stage -eq 'T2-extra-push' -and $extraState.status -eq 'completed') {
            Start-Worker $workers[1] @('-CrawlEvent', 'pull_request')
        } elseif ($extraState.status -ne 'completed') {
            $nextEvent = if ($extraState.stage -eq 'T2-extra-pr') { 'pull_request' } else { 'push' }
            Start-Worker $workers[1] @('-CrawlEvent', $nextEvent)
        }
    }
    Start-Worker $workers[2]
} else {
    foreach ($worker in $workers) {
        $proc = Owned-Process $worker $processes
        Write-Output "$($worker.script): $(if ($proc) { 'running (PID ' + $proc.ProcessId + ')' } else { 'stopped' })"
        if ($worker.state -and (Test-Path -LiteralPath $worker.state)) { Get-Content -Encoding utf8 -LiteralPath $worker.state }
    }
    if (Test-Path data/crawl_checkpoint.json) { Get-Content -Encoding utf8 data/crawl_checkpoint.json }
}
