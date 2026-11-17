#!/usr/bin/env bash
# Cách D (14/11): đoạn trích cắt từ log đầy đủ + stack trace test lỗi, kèm nhãn -> chạy agent, chấm lại 4 cách cùng lúc
# (thư mục judge4, giữ nguyên judge 3 cách cũ), tổng hợp. Khởi động như rca_agent_chain.sh.
set -u
export PYTHONPATH=src PYTHONIOENCODING=utf-8 PYTHONUTF8=1
S=scripts/analysis/rca_agent.py
L=data/logs/rca_agent_d.log
PY=.venv/Scripts/python
{
  echo "=== $(date '+%F %T') chạy agent cách D"
  $PY -X utf8 -u $S run --cond D
  echo "=== $(date '+%F %T') LLM chấm 4 cách"
  $PY -X utf8 -u $S judge --conds A B C D --dir judge4
  echo "=== $(date '+%F %T') tổng hợp"
  $PY -X utf8 -u $S score --dir judge4
  echo "=== $(date '+%F %T') XONG"
} >> "$L" 2>&1
