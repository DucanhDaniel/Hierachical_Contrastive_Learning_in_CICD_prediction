#!/usr/bin/env bash
# Dữ liệu crawl đợt 2 (19/10/2026): gán nhãn lại -> commit -> nhãn chi tiết -> export -> diff trên Kaggle (3 shard,
# --all-fail) -> merge + export + run_dataset (wait_merge.sh). Chạy độc lập (Git Bash), log: data/logs/r2_pipeline.log
#   bash scripts/kaggle/r2_pipeline.sh
set -uo pipefail
cd "$(dirname "$0")/../.."
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
export KAGGLE_API_TOKEN=$(grep "^KAGGLE_API_TOKEN=" .env | cut -d= -f2- | tr -d '\r')
PY=.venv/Scripts/python.exe
log() { echo "$(date '+%m-%d %H:%M') $*"; }
die() { log "LỖI: $*"; exit 1; }

log "nhãn + commit + nhãn chi tiết + export (200 repo)"
cat configs/repos_100.txt configs/repos_r2.txt > data/processed/repos_200.txt
$PY -m project3.pipeline.run --repos-file data/processed/repos_200.txt --only labels commits fine export 2>&1 \
  | grep -E "pipeline|Bước lỗi|rule|commit" | tail -25 || true
[ data/dataset/commits.parquet -nt data/processed/repos_200.txt ] || die "export không ra commits.parquet mới"

log "chuẩn bị diff còn thiếu"
$PY -m project3.pipeline.kaggle_diff prepare --shards 3 --all-fail | tail -2 || die "kaggle_diff prepare"
want=$(stat -c %s data/kaggle_diff_ds/todo.csv)
uvx kaggle datasets version -p "$(cygpath -w "$PWD/data/kaggle_diff_ds")" -m "r2 $(date +%m%d_%H%M)" > /dev/null 2>&1
for i in $(seq 1 40); do
  uvx kaggle datasets files ducanhpham2k5/p3-diff-input 2>&1 | grep -qE "^todo.csv +$want " && break
  sleep 30
done
for k in 0 1 2; do
  uvx kaggle kernels push -p "$(cygpath -w "$PWD/data/kaggle_diff_kernels/shard$k")" 2>&1 | tail -1
done
log "đã push 3 kernel diff"
sleep 180
bash scripts/kaggle/diff/wait_merge.sh
log "XONG r2_pipeline"
