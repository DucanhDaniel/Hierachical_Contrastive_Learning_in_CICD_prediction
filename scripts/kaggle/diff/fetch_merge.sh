#!/usr/bin/env bash
# Tải output 3 kernel p3-diff-{0,1,2} (đã COMPLETE) có thử lại khi mạng đứt (tar ~500 MB), kiểm tra tar đọc được
# rồi merge -> export_dataset -> run_dataset. Chạy độc lập (Git Bash), log: data/logs/kaggle_diff_fetch.log
#   bash scripts/kaggle/diff/fetch_merge.sh
set -uo pipefail
cd "$(dirname "$0")/../../.."
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
export KAGGLE_API_TOKEN=$(grep "^KAGGLE_API_TOKEN=" .env | cut -d= -f2- | tr -d '\r')
PY=.venv/Scripts/python.exe
log() { echo "$(date '+%m-%d %H:%M') $*"; }
out="data/kaggle_diff_out/$(date +%m%d_%H%M)_allfail"
for k in 0 1 2; do
  ok=0
  for try in $(seq 1 30); do
    rm -rf "$out/s$k"; mkdir -p "$out/s$k"
    uvx kaggle kernels output ducanhpham2k5/p3-diff-$k -p "$(cygpath -w "$PWD/$out/s$k")" > /dev/null 2>&1
    if [ -s "$out/s$k/summary_$k.json" ] && $PY -c "
import sys, tarfile; t = tarfile.open(sys.argv[1]); sum(1 for _ in t)" "$out/s$k/diffs_$k.tar" 2>/dev/null; then
      ok=1; break
    fi
    log "p3-diff-$k: tải lỗi lần $try, thử lại sau 2 phút"; sleep 120
  done
  [ $ok = 1 ] || { log "LỖI: không tải được p3-diff-$k"; exit 1; }
  log "p3-diff-$k: tải xong ($(du -h "$out/s$k/diffs_$k.tar" | cut -f1))"
  $PY -m project3.pipeline.kaggle_diff merge "$out/s$k" | tail -2
done
log "export_dataset"
$PY -m project3.pipeline.export_dataset 2>&1 | tail -2
log "run_dataset"
$PY -m project3.pipeline.run_dataset 2>&1 | grep -E '"with_diff"|"runs"'
log "XONG"
