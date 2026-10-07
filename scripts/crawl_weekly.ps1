# Crawl định kỳ (mỗi tuần): GitHub chỉ giữ log 90 ngày nên phải lấy dần để dữ liệu tích lũy quá 90 ngày.
# Crawler bỏ qua run/log đã có, nên lấy chồng 21 ngày cho chắc chắn không sót.
#   powershell -ExecutionPolicy Bypass -File scripts\crawl_weekly.ps1            # lấy 21 ngày gần nhất
#   powershell -ExecutionPolicy Bypass -File scripts\crawl_weekly.ps1 -Days 90   # lần đầu
param([int]$Days = 21)
$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONIOENCODING = "utf-8"
$log = "data\crawl_weekly.log"
New-Item -ItemType Directory -Force data | Out-Null
"===== $(Get-Date -Format s) start (days=$Days) =====" | Out-File -Append -Encoding utf8 $log

$common = @("--days", $Days, "--max-logs", "50000", "--max-pages", "10")
# 1) push lên nhánh chính: tất cả job fail (cần đủ để ưu tiên nguyên nhân gốc)
uv run python -m project3.crawl.gha --repos-file configs\repos_core.txt --repos-file configs\repos_extra.txt `
    --event push --branches master main trunk --root data\validate @common *>> $log
# 2) pull request: tối đa 2 job fail mỗi run (ưu tiên job compile/lint) cho nhanh
uv run python -m project3.crawl.gha --repos-file configs\repos_core.txt --event pull_request `
    --max-jobs-per-run 2 --root data\crawl_pr @common *>> $log
uv run python -m project3.crawl.gha --repos-file configs\repos_extra.txt --event pull_request `
    --max-jobs-per-run 2 --root data\crawl_pr @common *>> $log

# 3) gán nhãn từ log rồi gộp theo commit
uv run python -m project3.crawl.gold_labels data\validate *>> $log
uv run python -m project3.crawl.gold_labels data\crawl_pr *>> $log
uv run python -m project3.crawl.build_log_labels data\validate data\crawl_pr --out data\processed\commits_all.parquet *>> $log
"===== $(Get-Date -Format s) done =====" | Out-File -Append -Encoding utf8 $log
