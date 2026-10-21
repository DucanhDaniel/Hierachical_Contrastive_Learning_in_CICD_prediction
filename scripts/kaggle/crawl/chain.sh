#!/usr/bin/env bash
# Tự nối các phiên crawl trên Kaggle (Git Bash): chờ kernel p3-crawl xong -> tải output -> merge -> prepare ->
# version dataset p3-crawl-state -> push phiên mới. Dừng khi xong mọi repo-event, chạm hạn, hoặc kernel lỗi.
# Chỉ chạy khi máy bật; tắt máy giữa chừng thì phiên Kaggle vẫn chạy hết, lần sau chạy lại script là nối tiếp.
#   bash scripts/kaggle/crawl/chain.sh                       # đợt 1 (configs/repos_100.txt)
#   REPOS=configs/repos_r2.txt DEADLINE_AT="2026-10-24 22:00:00 +0700" bash scripts/kaggle/crawl/chain.sh  # đợt 2
set -uo pipefail
cd "$(dirname "$0")/../../.."
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
export KAGGLE_API_TOKEN=$(grep "^KAGGLE_API_TOKEN=" .env | cut -d= -f2- | tr -d '\r')
PY=.venv/Scripts/python.exe
KERNEL=ducanhpham2k5/p3-crawl
REPOS=${REPOS:-configs/repos_100.txt}
DEADLINE_AT=${DEADLINE_AT:-2026-10-14 22:00:00 +0700}
DEADLINE=$(date -d "$DEADLINE_AT" +%s)
DEADLINE_ISO=$(date -d "$DEADLINE_AT" --iso-8601=seconds)
log() { echo "$(date '+%m-%d %H:%M') $*"; }
status() { uvx kaggle kernels status $KERNEL 2>&1 | tail -1; }

while true; do
  # lỗi mạng (dòng không có "has status") coi như chưa xong, thử lại sau
  while s=$(status); echo "$s" | grep -qE "RUNNING|QUEUED" || ! echo "$s" | grep -q "has status"; do sleep 300; done
  log "kernel: $s"
  out="data/kaggle_crawl_out/$(date +%Y%m%d_%H%M)"
  mkdir -p "$out"
  uvx kaggle kernels output $KERNEL -p "$(cygpath -w "$PWD/$out")" > /dev/null 2>&1
  if [ ! -f "$out/crawl_out.tar.gz" ]; then
    log "LỖI: phiên không có output (xem $out/p3-crawl.log), dừng nối phiên"; exit 1
  fi
  $PY -m project3.pipeline.kaggle_crawl merge "$out" --repos-file "$REPOS" | head -1
  left=$(( (DEADLINE - $(date +%s)) / 60 - 20 ))
  remaining=$($PY -c "
import json; from project3.pipeline.kaggle_crawl import repo_list
r = json.load(open('data/crawl_100_results.json', encoding='utf-8'))
print(sum(r.get(f'{e}|{x}', {}).get('status') != 'completed' for e in ('pull_request', 'push') for x in repo_list('$REPOS')))")
  if [ "$remaining" -eq 0 ]; then log "XONG: đã crawl hết mọi repo-event"; exit 0; fi
  if [ "$left" -lt 30 ]; then log "Chạm hạn chót, còn $remaining repo-event chưa xong"; exit 0; fi
  budget=$(( left < 660 ? left : 660 ))
  $PY -m project3.pipeline.kaggle_crawl prepare --budget-min $budget --repos-file "$REPOS" --deadline "$DEADLINE_ISO" | tail -1
  want=$(stat -c %s data/kaggle_crawl_ds/results.json)
  uvx kaggle datasets version -p "$(cygpath -w "$PWD/data/kaggle_crawl_ds")" -m "auto $(date +%m%d_%H%M)" > /dev/null 2>&1
  # đợi Kaggle xử lý xong version mới rồi mới push (nếu không kernel đọc bản cũ)
  for i in $(seq 1 40); do
    uvx kaggle datasets files ducanhpham2k5/p3-crawl-state 2>&1 | grep -qE "^results.json +$want " && break
    sleep 30
  done
  uvx kaggle kernels push -p "$(cygpath -w "$PWD/scripts/kaggle/crawl")" 2>&1 | tail -1
  log "đã push phiên mới, budget=${budget} phút, còn $remaining repo-event"
  sleep 120
done
