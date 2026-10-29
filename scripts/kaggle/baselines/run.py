"""Kernel Kaggle cho bậc thang baseline (project3.model.ladder, 27/10/2026). Dùng chung cho kernel CPU và GPU:
CONFIG chọn mô hình/fold; `p3-baselines-cpu` (majority, ctx, tfidf) và `p3-baselines-bert` (bert, GPU).
Dữ liệu + mã: dataset ducanhpham2k5/p3-log-data (model.pack). Đầu ra /kaggle/working: ladder_preds_*.parquet, ladder_*.md.
"""
import glob
import os
import shutil
import subprocess
import sys

CONFIG = {"models": ["majority", "ctx", "tfidf"], "folds": [0, 1, 2, 3, 4], "extra": []}

src = os.path.dirname(glob.glob("/kaggle/input/**/label_tree.json", recursive=True)[0])
code = glob.glob(os.path.join(src, "project3_code.pyz*"))[0]
env = {**os.environ, "PYTHONPATH": code, "PYTHONIOENCODING": "utf-8"}
if shutil.which("nvidia-smi"):
    subprocess.run(["nvidia-smi"], check=False)
cmd = [sys.executable, "-m", "project3.model.ladder", "--data", src, "--out", "/kaggle/working",
       "--models", *CONFIG["models"], "--folds", *map(str, CONFIG["folds"]), *CONFIG["extra"]]
print("$", " ".join(cmd), flush=True)
sys.exit(subprocess.run(cmd, env=env).returncode)
