"""Đặc trưng TF-IDF cho mô hình lai (log_hcl --tfidf), 19/10/2026.

TF-IDF cấu hình A của log_baselines_fair (30.000 ký tự cuối, train che 50%) -> log xác suất từng lá, theo kiểu stacking:
với fold test k (val k+1, train T = 3 fold còn lại), run trong T lấy xác suất out-of-fold (fit trên 2 fold kia của T,
chia theo repo), run val/test lấy xác suất từ mô hình fit trên cả T. Mỗi run có bản log nguyên vẹn và bản đã che.

Tự chứa (chạy được trên Kaggle, chỉ cần runs.parquet + tfidf_text.parquet trong --data):
    python -m project3.pilot.tfidf_feats --export-text          # máy local: -> data/kaggle_log_ds/tfidf_text.parquet
    python -m project3.pilot.tfidf_feats --data DIR --out DIR --folds 3 4   # -> tfidf_fold{k}.parquet
(chạy lại --export-text sau log_pack, vì log_pack xoá thư mục)
"""
import argparse
import random
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier

PACK = Path("data/kaggle_log_ds")
MAX_RUN_CHARS, SEED = 30_000, 20261018  # như log_baselines


def export_text() -> None:
    from project3.pilot.log_baselines import load as load_all, mask_text
    runs, jobs = load_all()
    runs = runs.drop_duplicates("run_id")
    pd.DataFrame({"run_id": runs.run_id,
                  "full": ["\n".join(jobs[r])[-MAX_RUN_CHARS:] for r in runs.run_id],
                  "masked": ["\n".join(mask_text(t, k) for t in jobs[r])[-MAX_RUN_CHARS:]
                             for r, k in zip(runs.run_id, runs.key)]}
                 ).to_parquet(PACK / "tfidf_text.parquet", index=False, compression="zstd")
    print(f"{len(runs)} run -> {PACK / 'tfidf_text.parquet'}")


def main(data: Path, out: Path, folds: list[int]) -> None:
    t0 = time.time()
    runs = pd.read_parquet(data / "runs.parquet").drop_duplicates("run_id")
    txt = pd.read_parquet(data / "tfidf_text.parquet").set_index("run_id")
    TXT = {False: txt.full.to_dict(), True: txt.masked.to_dict()}
    classes = sorted(runs.leaf.unique())
    rng = random.Random(SEED)
    mix = {r: rng.random() < 0.5 for r in runs.run_id}

    def fit_predict(fit_ids, fit_y, pred_ids):
        vec = TfidfVectorizer(token_pattern=r"(?u)\b[A-Za-z_][A-Za-z0-9_]{1,40}\b", ngram_range=(1, 2), min_df=5,
                              max_df=0.5, max_features=300_000, sublinear_tf=True, dtype=np.float32)
        X = vec.fit_transform([TXT[mix[r]][r] for r in fit_ids])
        clf = SGDClassifier(loss="log_loss", alpha=2e-6, max_iter=30, tol=None, class_weight="balanced",
                            random_state=SEED, n_jobs=-1).fit(X, fit_y)
        res = {}
        for m in (False, True):
            p = np.zeros((len(pred_ids), len(classes)), dtype=np.float32)
            p[:, [classes.index(c) for c in clf.classes_]] = clf.predict_proba(vec.transform([TXT[m][r] for r in pred_ids]))
            res[m] = np.log(np.clip(p, 1e-4, 1)).astype(np.float32)
        return res

    for k in folds:
        T = [f for f in range(5) if f not in (k, (k + 1) % 5)]
        parts = []
        for j in T:  # out-of-fold cho train
            fit = runs[runs.repo_fold.isin([f for f in T if f != j])]
            ids = runs.run_id[runs.repo_fold == j].tolist()
            parts.append((ids, fit_predict(fit.run_id.tolist(), fit.leaf.tolist(), ids)))
        fit = runs[runs.repo_fold.isin(T)]
        ids = runs.run_id[runs.repo_fold.isin([k, (k + 1) % 5])].tolist()
        parts.append((ids, fit_predict(fit.run_id.tolist(), fit.leaf.tolist(), ids)))
        df = pd.concat([pd.DataFrame({"run_id": ids, "full": list(o[False]), "masked": list(o[True])}) for ids, o in parts])
        df.to_parquet(out / f"tfidf_fold{k}.parquet", index=False)
        print(f"  tfidf fold {k}: {len(df)} run ({time.time() - t0:.0f}s)", flush=True)
    (out / "tfidf_classes.txt").write_text("\n".join(classes), encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--export-text", action="store_true")
    ap.add_argument("--data", type=Path, default=PACK)
    ap.add_argument("--out", type=Path, default=PACK)
    ap.add_argument("--folds", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    a = ap.parse_args()
    export_text() if a.export_text else main(a.data, a.out, a.folds)
