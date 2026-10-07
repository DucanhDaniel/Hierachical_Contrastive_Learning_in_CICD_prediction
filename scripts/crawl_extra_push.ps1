# Worker thứ hai: push repo mở rộng, song song với PR repo lõi.
param([ValidateSet('push', 'pull_request')][string]$CrawlEvent = 'push')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUNBUFFERED = '1'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.uv-cache'
$started = Get-Date -Format o
$stage = if ($CrawlEvent -eq 'push') { 'T2-extra-push' } else { 'T2-extra-pr' }
$logPath = if ($CrawlEvent -eq 'push') { 'data/crawl_extra_push.log' } else { 'data/crawl_extra_pr.log' }
function Save-State($status, $code = $null) {
    @{ started = $started; updated = (Get-Date -Format o); stage = $stage; status = $status; exit_code = $code } |
        ConvertTo-Json | Set-Content -Encoding utf8 data/crawl_extra_push_state.json
}
Save-State 'running'
try {
    $crawlArgs = @('--repos-file', 'configs/repos_extra.txt', '--event', $CrawlEvent, '--days', '90', '--max-logs', '50000')
    if ($CrawlEvent -eq 'push') { $crawlArgs += @('--branches', 'master', 'main', 'trunk', '--root', 'data/validate') }
    else { $crawlArgs += @('--max-jobs-per-run', '2', '--root', 'data/crawl_pr') }
    uv run python -m project3.crawl.gha @crawlArgs 2>&1 | Out-File -Append -Encoding utf8 $logPath
    if ($LASTEXITCODE -ne 0) { throw "Crawler exited with code $LASTEXITCODE" }
    Save-State 'completed' 0
} catch {
    Save-State 'failed' 1
    $_ | Out-File -Append -Encoding utf8 $logPath
    throw
}
