# Người dùng tự chạy (một lần): đưa GITHUB_ACCESS_TOKEN trong .env lên dataset PRIVATE ducanhpham2k5/p3-gh-token
# để kernel p3-crawl push bằng CLI đọc được (Kaggle Secrets chỉ cấp cho bản chạy từ web).
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/kaggle/crawl/upload_token.ps1
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '../../..')
$envLines = Get-Content .env
function Get-EnvValue($key) {
    $line = $envLines | Where-Object { $_ -match "^$key=" } | Select-Object -First 1
    if (-not $line) { throw "Không thấy $key trong .env" }
    return ($line -replace "^$key=", '').Trim().Trim('"', "'")
}
$dir = Join-Path ([IO.Path]::GetTempPath()) ("p3-gh-token-" + [guid]::NewGuid())
New-Item -ItemType Directory $dir | Out-Null
try {
    [IO.File]::WriteAllText((Join-Path $dir 'gh_token.txt'), (Get-EnvValue 'GITHUB_ACCESS_TOKEN'))
    [IO.File]::WriteAllText((Join-Path $dir 'dataset-metadata.json'),
        '{"title": "p3-gh-token", "id": "ducanhpham2k5/p3-gh-token", "licenses": [{"name": "other"}]}')
    $env:KAGGLE_API_TOKEN = Get-EnvValue 'KAGGLE_API_TOKEN'
    $env:PYTHONUTF8 = '1'; $env:PYTHONIOENCODING = 'utf-8'
    uvx kaggle datasets create -p $dir   # mặc định private
} finally {
    Remove-Item -Recurse -Force $dir
}
