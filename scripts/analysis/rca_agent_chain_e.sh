#!/bin/bash
# Cách E (15/11): nhãn + dòng nguyên nhân của mô hình k2 -> chạy agent (chỉ run có dự đoán k2) -> chấm cùng A/B/C -> điểm
cd /d/projects/project3
export PYTHONIOENCODING=utf-8 PYTHONUTF8=1
uv run python scripts/analysis/rca_agent.py run --cond E
uv run python scripts/analysis/rca_agent.py judge --conds A B C E --dir judge_e
uv run python scripts/analysis/rca_agent.py score --dir judge_e > data/results/rca_agent/score_e.txt
echo DONE
