"""Chẩn đoán sau pilot HCL: embedding UniXcoder đóng băng có chứa tín hiệu không, hay mạng nơ-ron overfit?

Linear probe (ít tham số, khó overfit): embedding commit = trung bình embedding hunk -> PCA(k) -> LR, C chọn trên
validation (20% cuối của train) theo PR-AUC, rồi fit lại trên toàn bộ train.
  history        : LR trên feature lịch sử + thống kê diff (như pilot)
  emb k          : chỉ embedding (PCA k)
  history+emb k  : ghép cả hai
So hiệu PR-AUC (history+emb) - history bằng bootstrap theo cặp trên test và tập con P3.
Tầng 2: LR trên embedding (PCA k) phân loại compile/lint/test trong commit fail; đối chiếu TF-IDF của pilot (0,481).

    uv run --group exp python -m project3.pilot.hcl_probe --emb data/processed/hcl_pilot/emb.npz
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

from .experiment import HIST, SEED, STATS

TYPES = ["compile", "lint", "test"]


def commit_emb(npz: Path, shas: list[str]) -> np.ndarray:
    z = np.load(npz)
    emb, hf, fc = z["emb"].astype(np.float32), z["hunk_file"], z["file_commit"]
    hc = fc[hf]  # commit của từng hunk
    n = len(z["shas"])
    s = np.zeros((n, emb.shape[1]), np.float32)
    np.add.at(s, hc, emb)
    s /= np.maximum(np.bincount(hc, minlength=n), 1)[:, None]
    pos = {sha: i for i, sha in enumerate(z["shas"])}
    return s[[pos[x] for x in shas]]


def fit_lr(Xtr, ytr, Xva, yva, Xall, cs=(0.003, 0.01, 0.03, 0.1, 0.3, 1.0)):
    best = max(cs, key=lambda c: average_precision_score(
        yva, LogisticRegression(C=c, class_weight="balanced", max_iter=5000).fit(Xtr, ytr).predict_proba(Xva)[:, 1]))
    return best


def paired(y, a, b, n=2000):
    rng = np.random.default_rng(SEED)
    d = []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        if y[i].sum():
            d.append(average_precision_score(y[i], a[i]) - average_precision_score(y[i], b[i]))
    point = average_precision_score(y, a) - average_precision_score(y, b)
    return round(point, 4), [round(float(np.percentile(d, 2.5)), 4), round(float(np.percentile(d, 97.5)), 4)]


def main(meta: Path, npz: Path, out: Path, ks: list[int]):
    df = pd.read_parquet(meta)
    cut = int(len(df) * 0.7)
    df["split"] = np.where(np.arange(len(df)) < cut, "train", "test")
    have = set(np.load(npz)["shas"])
    df = df[df.head_sha.isin(have)].reset_index(drop=True)
    tr_all = np.where(df.split == "train")[0]
    tr, va = tr_all[:int(len(tr_all) * 0.8)], tr_all[int(len(tr_all) * 0.8):]
    te = np.where(df.split == "test")[0]
    y = df.y.values.astype(int)
    p3 = df.prev_fail.values[te] == 0
    rc = [c for c in df.columns if c.startswith("repo_")]
    H = np.log1p(np.clip(df[HIST + STATS + rc].astype(float).values, 0, None))
    H = StandardScaler().fit(H[tr_all]).transform(H)
    E = commit_emb(npz, list(df.head_sha))
    E = StandardScaler().fit(E[tr_all]).transform(E)

    res = {"binary": {}, "delta_vs_history": {}, "tier2": {}}
    scores = {}

    def evaluate(name, X):
        c = fit_lr(X[tr], y[tr], X[va], y[va], X)
        m = LogisticRegression(C=c, class_weight="balanced", max_iter=5000).fit(X[tr_all], y[tr_all])
        p = m.predict_proba(X[te])[:, 1]
        scores[name] = p
        yt = y[te]
        res["binary"][name] = {"C": c, "pr_auc": round(average_precision_score(yt, p), 4),
                               "roc_auc": round(roc_auc_score(yt, p), 4),
                               "p3_pr_auc": round(average_precision_score(yt[p3], p[p3]), 4),
                               "p3_roc_auc": round(roc_auc_score(yt[p3], p[p3]), 4)}
        print(name, res["binary"][name], flush=True)

    evaluate("history", H)
    for k in ks:
        pca = PCA(k, random_state=SEED).fit(E[tr_all])
        P = StandardScaler().fit(pca.transform(E[tr_all])).transform(pca.transform(E))
        evaluate(f"emb{k}", P)
        evaluate(f"history+emb{k}", np.hstack([H, P]))
        yt = y[te]
        res["delta_vs_history"][f"emb{k}"] = {
            "all": paired(yt, scores[f"history+emb{k}"], scores["history"]),
            "p3": paired(yt[p3], scores[f"history+emb{k}"][p3], scores["history"][p3])}
        print(f"  history+emb{k} - history: {res['delta_vs_history'][f'emb{k}']}", flush=True)
        # tầng 2
        lab = df.label.replace({"dependency": "compile", "buildconfig": "compile"}).values
        ftr = tr_all[(y[tr_all] == 1) & np.isin(lab[tr_all], TYPES)]
        fte = te[(y[te] == 1) & np.isin(lab[te], TYPES)]
        Z = np.hstack([P, df[rc].values])
        m = LogisticRegression(C=0.1, class_weight="balanced", max_iter=5000).fit(Z[ftr], lab[ftr])
        res["tier2"][f"emb{k}"] = {"macro_f1": round(f1_score(lab[fte], m.predict(Z[fte]), average="macro"), 4),
                                   "per_class": dict(zip(TYPES, np.round(f1_score(lab[fte], m.predict(Z[fte]), labels=TYPES, average=None), 3).tolist())),
                                   "n_test": pd.Series(lab[fte]).value_counts().to_dict()}
        print(f"  tầng 2 emb{k}: {res['tier2'][f'emb{k}']}", flush=True)
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
    print(f"Đã lưu {out}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--meta", type=Path, default=Path("data/processed/hcl_pilot/meta.parquet"))
    ap.add_argument("--emb", type=Path, default=Path("data/processed/hcl_pilot/emb.npz"))
    ap.add_argument("--out", type=Path, default=Path("data/processed/hcl_pilot/probe.json"))
    ap.add_argument("--ks", type=int, nargs="+", default=[16, 64, 256])
    a = ap.parse_args()
    main(a.meta, a.emb, a.out, a.ks)
