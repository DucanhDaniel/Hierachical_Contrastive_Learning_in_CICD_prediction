"""TF-IDF (từ + cặp từ) + hồi quy logistic (SGD) ở mức lá; dùng cho baseline và đặc trưng stacking của mô hình lai.

Đặc trưng stacking (cấu hình A: 30.000 ký tự cuối, train che 50%): với fold test k (val k+1, train T = 3 fold còn lại),
run trong T lấy log xác suất out-of-fold (fit trên 2 fold kia của T, chia theo repo), run val/test lấy từ mô hình fit
trên cả T. Mỗi run có bản log nguyên vẹn và bản đã che.

    python -m project3.model.tfidf --export-text                     # máy local: -> data/kaggle_log_ds/tfidf_text.parquet
    python -m project3.model.tfidf --data DIR --out DIR --folds 3 4   # -> tfidf_fold{k}.parquet (chạy được trên Kaggle)
(chạy lại --export-text sau model.pack, vì pack xoá thư mục)
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier

from .config import MAX_RUN_CHARS, PACK, SEED
from .data import mix50, train_folds, val_fold
from .text import mask_text


def make_vectorizer() -> TfidfVectorizer:
    return TfidfVectorizer(token_pattern=r"(?u)\b[A-Za-z_][A-Za-z0-9_]{1,40}\b", ngram_range=(1, 2), min_df=5,
                           max_df=0.5, max_features=300_000, sublinear_tf=True, dtype=np.float32)


def make_classifier(n_jobs: int = -1) -> SGDClassifier:
    return SGDClassifier(loss="log_loss", alpha=2e-6, max_iter=30, tol=None, class_weight="balanced",
                         random_state=SEED, n_jobs=n_jobs)


def export_text(pack: Path = PACK) -> None:
    """30.000 ký tự cuối của run (nguyên vẹn / đã che) cho các run trong gói, đọc từ run_dataset."""
    from .data import load_run_logs
    runs, jobs = load_run_logs()
    runs = runs.drop_duplicates("run_id")
    pd.DataFrame({"run_id": runs.run_id,
                  "full": ["\n".join(jobs[r])[-MAX_RUN_CHARS:] for r in runs.run_id],
                  "masked": ["\n".join(mask_text(t, k) for t in jobs[r])[-MAX_RUN_CHARS:]
                             for r, k in zip(runs.run_id, runs.key)]}
                 ).to_parquet(pack / "tfidf_text.parquet", index=False, compression="zstd")
    print(f"{len(runs)} run -> {pack / 'tfidf_text.parquet'}")


def stacking_features(data: Path, out: Path, folds: list) -> None:
    t0 = time.time()
    runs = pd.read_parquet(data / "runs.parquet").drop_duplicates("run_id")
    txt = pd.read_parquet(data / "tfidf_text.parquet").set_index("run_id")
    TXT = {False: txt.full.to_dict(), True: txt.masked.to_dict()}
    classes = sorted(runs.leaf.unique())
    mix = mix50(runs.run_id)

    def fit_predict(fit_ids, fit_y, pred_ids):
        vec = make_vectorizer()
        X = vec.fit_transform([TXT[mix[r]][r] for r in fit_ids])
        clf = make_classifier().fit(X, fit_y)
        res = {}
        for m in (False, True):
            p = np.zeros((len(pred_ids), len(classes)), dtype=np.float32)
            p[:, [classes.index(c) for c in clf.classes_]] = clf.predict_proba(vec.transform([TXT[m][r] for r in pred_ids]))
            res[m] = np.log(np.clip(p, 1e-4, 1)).astype(np.float32)
        return res

    for k in folds:
        T = train_folds(k)
        parts = []
        for j in T:  # out-of-fold cho train
            fit = runs[runs.repo_fold.isin([f for f in T if f != j])]
            ids = runs.run_id[runs.repo_fold == j].tolist()
            parts.append((ids, fit_predict(fit.run_id.tolist(), fit.leaf.tolist(), ids)))
        fit = runs[runs.repo_fold.isin(T)]
        ids = runs.run_id[runs.repo_fold.isin([k, val_fold(k)])].tolist()
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
    export_text() if a.export_text else stacking_features(a.data, a.out, a.folds)
