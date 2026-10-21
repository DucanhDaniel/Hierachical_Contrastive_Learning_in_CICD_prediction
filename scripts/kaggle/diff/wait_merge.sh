#!/usr/bin/env bash
# Chờ 3 kernel p3-diff-{0,1,2} xong -> tải output -> merge vào data/diffs + diffs_all.csv -> export_dataset -> run_dataset.
# Chạy độc lập (Git Bash), log: data/logs/kaggle_diff_wait.log
#   bash scripts/kaggle/diff/wait_merge.sh
set -uo pipefail
cd "$(dirname "$0")/../../.."
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
export KAGGLE_API_TOKEN=$(grep "^KAGGLE_API_TOKEN=" .env | cut -d= -f2- | tr -d '\r')
PY=.venv/Scripts/python.exe
log() { echo "$(date '+%m-%d %H:%M') $*"; }
out="data/kaggle_diff_out/$(date +%m%d_%H%M)_allfail"
for k in 0 1 2; do
  while s=$(uvx kaggle kernels status ducanhpham2k5/p3-diff-$k 2>&1 | tail -1); echo "$s" | grep -qE "RUNNING|QUEUED"; do sleep 300; done
  log "p3-diff-$k: $s"
  mkdir -p "$out/s$k"
  uvx kaggle kernels output ducanhpham2k5/p3-diff-$k -p "$(cygpath -w "$PWD/$out/s$k")" > /dev/null 2>&1
  $PY -m project3.pipeline.kaggle_diff merge "$out/s$k" | tail -2
done
log "export_dataset"
$PY -m project3.pipeline.export_dataset 2>&1 | tail -2
log "run_dataset"
$PY -m project3.pipeline.run_dataset 2>&1 | grep -E '"with_diff"|"runs"'
log "XONG"
