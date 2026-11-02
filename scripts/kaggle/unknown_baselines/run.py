"""Kernel Kaggle (CPU): baseline TF-IDF trên 120 run quy tắc để `?` (người gán, 31/10/2026).
Với mỗi fold k có run `?`: huấn luyện như model.ladder (train = 3 fold, val = k+1, train che 50%) trên run có nhãn quy tắc
của gói p3-log-data, rồi dự đoán các run `?` thuộc repo fold k — giống cách mô hình HCL dự đoán run `?`.
Đầu ra (/kaggle/working): unknown120_preds.parquet (model, fold, run_id, pred).
    kaggle kernels push -p scripts/kaggle/unknown_baselines
"""
import glob
import os
import sys
import time
from pathlib import Path

import pandas as pd

src = os.path.dirname(glob.glob("/kaggle/input/**/label_tree.json", recursive=True)[0])
code = sorted(glob.glob("/kaggle/input/**/project3_code.pyz*", recursive=True), key=lambda p: not p.startswith(src))[-1]
sys.path.insert(0, code)
from project3.model.data import train_folds, val_fold  # noqa: E402
from project3.model.ladder import load, sklearn_model  # noqa: E402
from project3.model.text import ci_context  # noqa: E402

MODELS = ["tfidf", "tfidf_all"]  # B1 TF-IDF log; TF-IDF + thông tin CI + diff (baseline mạnh nhất)
T0 = time.time()
runs = load(Path(src))
unk = pd.read_parquet(glob.glob("/kaggle/input/**/unknown120.parquet", recursive=True)[0])
unk["ctx"] = [ci_context(w, j, s) for w, j, s in
              zip(unk.workflow.fillna(""), unk.failed_job_names.fillna(""), unk.failed_steps.fillna(""))]
print(f"{len(runs)} run có nhãn, {len(unk)} run `?`", flush=True)
parts = []
for k in sorted(unk.repo_fold.unique()):
    tr, va = runs[runs.repo_fold.isin(train_folds(k))], runs[runs.repo_fold == val_fold(k)]
    te = unk[unk.repo_fold == k].reset_index(drop=True)
    for m in MODELS:
        pred = sklearn_model(m, tr, te, va)["full"]
        parts.append(pd.DataFrame({"model": m, "fold": k, "run_id": te.run_id, "pred": pred}))
        print(f"fold {k} {m}: {len(te)} run, {(time.time() - T0) / 60:.1f} phút", flush=True)
    pd.concat(parts).to_parquet("/kaggle/working/unknown120_preds.parquet", index=False)
print("xong", flush=True)
