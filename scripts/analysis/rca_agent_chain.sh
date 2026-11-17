#!/usr/bin/env bash
# Chạy cả chuỗi đánh giá agent (prepare -> run A/B -> judge -> score), các bước đều tiếp tục được nếu bị ngắt.
# Khởi động độc lập, ưu tiên thấp (PowerShell):
#   $p = Start-Process D:\apps\Git\bin\bash.exe -ArgumentList '-c','"cd /d/projects/project3 && bash scripts/analysis/rca_agent_chain.sh"' -WindowStyle Hidden -PassThru; $p.PriorityClass = 'BelowNormal'
set -u
# bước chuẩn bị lỗi thì không chạy tiếp các bước sau với dữ liệu thiếu
export PYTHONPATH=src PYTHONIOENCODING=utf-8 PYTHONUTF8=1
S=scripts/analysis/rca_agent.py
L=data/logs/rca_agent_main.log
PY=.venv/Scripts/python
{
  echo "=== $(date '+%F %T') bắt đầu"
  $PY -X utf8 $S prepare || { echo "=== prepare lỗi, dừng"; exit 1; }
  echo "=== $(date '+%F %T') chạy agent"
  $PY -X utf8 $S run --cond A B
  echo "=== $(date '+%F %T') LLM chấm"
  $PY -X utf8 $S judge
  echo "=== $(date '+%F %T') tổng hợp"
  $PY -X utf8 $S score
  echo "=== $(date '+%F %T') XONG"
} >> "$L" 2>&1
