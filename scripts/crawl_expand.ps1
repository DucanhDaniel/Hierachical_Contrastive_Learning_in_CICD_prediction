# Crawl lần đầu 90 ngày; chạy tuần tự để không ghi đồng thời vào cùng root.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUNBUFFERED = '1'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.uv-cache'
New-Item -ItemType Directory -Force data | Out-Null
$state = 'data/crawl_expand_state.json'
$started = Get-Date -Format o
function Save-State($stage, $status, $code = $null) {
    @{ started = $started; updated = (Get-Date -Format o); stage = $stage; status = $status; exit_code = $code } |
        ConvertTo-Json | Set-Content -Encoding utf8 $state
}
function Run-Stage($stage, $log, $cliArgs) {
    Save-State $stage 'running'
    & uv run python -m @cliArgs 2>&1 | Out-File -Append -Encoding utf8 $log
    if ($LASTEXITCODE -ne 0) {
        Save-State $stage 'failed' $LASTEXITCODE
        throw "Stage $stage failed: $LASTEXITCODE"
    }
}
try {
    Run-Stage 'T1-core-pr' 'data/crawl_pr.log' @('project3.crawl.gha', '--repos-file', 'configs/repos_core.txt', '--event', 'pull_request', '--days', '90', '--max-jobs-per-run', '2', '--max-logs', '50000', '--root', 'data/crawl_pr')
    Run-Stage 'T2-extra-push' 'data/crawl_extra.log' @('project3.crawl.gha', '--repos-file', 'configs/repos_extra.txt', '--event', 'push', '--branches', 'master', 'main', 'trunk', '--days', '90', '--max-logs', '50000', '--root', 'data/validate')
    Run-Stage 'T2-extra-pr' 'data/crawl_extra.log' @('project3.crawl.gha', '--repos-file', 'configs/repos_extra.txt', '--event', 'pull_request', '--days', '90', '--max-jobs-per-run', '2', '--max-logs', '50000', '--root', 'data/crawl_pr')
    # Chờ worker phụ ngừng ghi dữ liệu trước khi gán nhãn/gộp.
    while (Test-Path data/crawl_extra_push_state.json) {
        $extraState = Get-Content -Raw -Encoding utf8 data/crawl_extra_push_state.json | ConvertFrom-Json
        if ($extraState.status -eq 'completed') { break }
        Save-State 'wait-extra-worker' 'running'
        if ($extraState.status -eq 'failed' -or -not (Get-Process -Id ([int](Get-Content data/crawl_extra_push.pid)) -ErrorAction SilentlyContinue)) {
            Save-State 'wait-extra-worker' 'failed' 1
            throw 'Extra worker stopped before completion; resume required'
        }
        Start-Sleep -Seconds 5
    }
    Run-Stage 'T3-label-push' 'data/crawl_expand.log' @('project3.crawl.gold_labels', 'data/validate')
    Run-Stage 'T3-label-pr' 'data/crawl_expand.log' @('project3.crawl.gold_labels', 'data/crawl_pr')
    Run-Stage 'T4-commits' 'data/crawl_expand.log' @('project3.crawl.build_log_labels', 'data/validate', 'data/crawl_pr', '--out', 'data/processed/commits_all.parquet')
    Save-State 'crawl-and-labels' 'completed' 0
} catch {
    $_ | Out-File -Append -Encoding utf8 'data/crawl_expand.log'
    throw
}
