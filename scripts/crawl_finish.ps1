# Cập nhật báo cáo sau pipeline nền; mẫu mới luôn cần đánh giá thủ công.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONIOENCODING = 'utf-8'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.uv-cache'
while ($true) {
    $state = Get-Content -Raw -Encoding utf8 data/crawl_expand_state.json | ConvertFrom-Json
    if ($state.status -eq 'failed') { throw "Pipeline failed at $($state.stage)" }
    if ($state.status -eq 'completed') { break }
    Start-Sleep -Seconds 30
}
uv run python -m project3.crawl.review_sample data/validate data/crawl_pr *>> data/crawl_expand.log
if ($LASTEXITCODE -ne 0) { throw 'Review export failed' }
uv run python -m project3.crawl.crawl_report data/validate data/crawl_pr *>> data/crawl_expand.log
if ($LASTEXITCODE -ne 0) { throw 'Report failed' }
