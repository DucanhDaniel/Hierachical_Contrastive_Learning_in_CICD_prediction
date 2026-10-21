# Chờ worker hiện tại xong, thử lại phần thiếu, rồi cập nhật nhãn/báo cáo.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUNBUFFERED = '1'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.uv-cache'
$logPath = 'data/crawl_overnight.log'
$statePath = 'data/crawl_overnight_state.json'
$started = Get-Date -Format o
function Save-State($stage, $status) {
    @{ started = $started; updated = (Get-Date -Format o); stage = $stage; status = $status; keep_awake = $true } |
        ConvertTo-Json | Set-Content -Encoding utf8 $statePath
}
function Run-Module($moduleArgs) {
    & uv run --no-sync python -m @moduleArgs 2>&1 | Out-File -Append -Encoding utf8 $logPath
    if ($LASTEXITCODE -ne 0) { throw "Module failed: $($moduleArgs[0])" }
}
Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
public static class CrawlAwake {
    [DllImport("kernel32.dll")]
    public static extern uint SetThreadExecutionState(uint flags);
}
'@
$awakeResult = [CrawlAwake]::SetThreadExecutionState(2147483649)
if ($awakeResult -eq 0) { throw 'Could not request system keep-awake' }
try {
    Save-State 'waiting-for-current-workers' 'running'
    while ($true) {
        $active = $false
        foreach ($pidPath in @('data/crawl_expand.pid','data/crawl_extra_push.pid')) {
            if (Test-Path $pidPath) {
                $workerId = [int](Get-Content $pidPath)
                if (Get-Process -Id $workerId -ErrorAction SilentlyContinue) { $active = $true }
            }
        }
        if (-not $active -and (Test-Path data/crawl_finish.pid)) {
            $finishId = [int](Get-Content data/crawl_finish.pid)
            $finishProc = Get-Process -Id $finishId -ErrorAction SilentlyContinue
            if ($finishProc) {
                $mainState = Get-Content -Raw -Encoding utf8 data/crawl_expand_state.json | ConvertFrom-Json
                if ($mainState.status -eq 'completed') { $active = $true }
                else {
                    # Watcher cũ chỉ chờ state, không được chặn phục hồi khi worker đã chết.
                    $owned = Get-CimInstance Win32_Process -Filter "ProcessId=$finishId"
                    $expected = Join-Path (Get-Location) 'scripts/crawl_finish.ps1'
                    if ($owned.CommandLine -like "*$expected*") { Stop-Process -Id $finishId -ErrorAction SilentlyContinue }
                    else { throw 'Unexpected process using finish PID' }
                }
            }
        }
        if (-not $active) { break }
        Save-State 'waiting-for-current-workers' 'running'
        Start-Sleep -Seconds 15
    }
    Run-Module @('project3.crawl.checkpoint', '--repair')
    for ($round = 1; $round -le 3; $round++) {
        Save-State "retry-round-$round" 'running'
        $planArgs = @('project3.crawl.retry_plan', '--prepare')
        if ($round -eq 1) { $planArgs += '--retry-missing' }
        $planJson = & uv run --no-sync python -m @planArgs
        if ($LASTEXITCODE -ne 0) { throw 'Retry plan failed' }
        $parsedPlans = $planJson | ConvertFrom-Json
        $plans = @($parsedPlans)
        if ($plans.Count -eq 0) { break }
        $activeRetries = @()
        $index = 0
        foreach ($plan in $plans) {
            $index++
            $cli = @('run','--no-sync','python','-m','project3.crawl.gha','--repos') + @($plan.repos) +
                @('--event',$plan.event,'--root',$plan.root,'--days','90','--max-logs','50000','--max-jobs-per-run',$plan.max_jobs_per_run)
            if ($plan.event -eq 'push') { $cli += @('--branches','master','main','trunk') }
            $proc = Start-Process uv -WindowStyle Hidden -ArgumentList $cli -PassThru `
                -RedirectStandardOutput "data/overnight_retry_${round}_${index}.log" `
                -RedirectStandardError "data/overnight_retry_${round}_${index}.err.log"
            $activeRetries += $proc
            if ($activeRetries.Count -eq 2) {
                foreach ($retryProc in $activeRetries) { $retryProc.WaitForExit() }
                $activeRetries = @()
            }
        }
        foreach ($retryProc in $activeRetries) { $retryProc.WaitForExit() }
    }
    Save-State 'labels-and-report' 'running'
    Run-Module @('project3.crawl.gold_labels','data/validate')
    Run-Module @('project3.crawl.gold_labels','data/crawl_pr')
    Run-Module @('project3.crawl.build_log_labels','data/validate','data/crawl_pr','--out','data/processed/commits_all.parquet')
    Run-Module @('project3.crawl.review_sample','data/validate','data/crawl_pr')
    Run-Module @('project3.crawl.checkpoint')
    Run-Module @('project3.crawl.crawl_report','data/validate','data/crawl_pr')
    $remainingJson = & uv run --no-sync python -m project3.crawl.retry_plan
    if ($LASTEXITCODE -ne 0) { throw 'Final retry check failed' }
    $remainingPlans = $remainingJson | ConvertFrom-Json
    if (@($remainingPlans).Count -gt 0) { Save-State 'download-gaps-remain' 'needs_attention' }
    else { Save-State 'downloads-processed-manual-review-pending' 'completed' }
} catch {
    Save-State 'overnight-error' 'failed'
    $_ | Out-File -Append -Encoding utf8 $logPath
    throw
} finally {
    [CrawlAwake]::SetThreadExecutionState(2147483648) | Out-Null
}
