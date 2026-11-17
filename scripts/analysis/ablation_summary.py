"""Tổng hợp mọi lượt ablation từ file chỉ số *.json của model.train (không cần GPU, không đọc nhãn lại).

Hai nhóm, mỗi nhóm so ghép cặp với bản cuối C cùng seed + cùng fold:
  pilot  (seed 1, fold 0 + 3; 30/10-01/11): thêm dần thành phần (A, B, C) + bỏ HCL / bỏ thông tin CI / bỏ thống kê diff.
         C chạy trên A100 (Colab), ablation bỏ thành phần chạy trên T4 (Kaggle) -> lẫn phần cứng.
  input  (seed 0, fold 0, 3, 4, T4; 04/11): bỏ thông tin CI (D) / bỏ thống kê diff (S) / chỉ đọc log (N).
v10 (bản trước, chỉ có trong numbers.json của baseline_report) lấy từ data/results/report_c/numbers.json.

    python scripts/analysis/ablation_summary.py   # -> data/results/ablation_summary/{per_fold,paired}.csv
"""
import glob
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("data/results/ablation_summary")
GROUPS = {
    "pilot": {
        "ref": "C: bản cuối",
        "configs": {
            "A: + cửa sổ chia đôi": "data/results/lines/*/A_fold*.json",
            "B: A + điểm từng dòng": "data/results/lines/*/B_fold*.json",
            "C: bản cuối": "data/results/lines/*/C_fold*.json",
            "C - học tương phản (HCL)": "data/results/abl/k*/A4_fold*.json",
            "C - thông tin CI": "data/results/abl/k*/A1_fold*.json",
            "C - thống kê diff": "data/results/abl/k*/A6_fold*.json",
        },
    },
    "input": {
        "ref": "C: bản cuối",
        "configs": {
            "C: bản cuối": "data/results/c/k*/C_s0_fold[034].json",
            "C - thông tin CI": "data/results/abl_in/*/D_s0_fold*.json",
            "C - thống kê diff": "data/results/abl_in/*/S_s0_fold*.json",
            "C - cả hai (chỉ log)": "data/results/abl_in/*/N_s0_fold*.json",
        },
    },
}
METRICS = {"macroF1_l3": "lá", "macroF1_l2": "tầng 2", "macroF1_l1": "tầng 1"}


def rows_of(path: str, group: str, config: str) -> list:
    d = json.load(open(path, encoding="utf-8"))
    res = next(v for k, v in d.items() if k not in ("args", "tree"))
    fold = int(os.path.basename(path).split("fold")[1][0])
    return [dict(group=group, config=config, fold=fold, test=t, **{n: res[t][m] for m, n in METRICS.items()})
            for t in ("full", "masked")]


def main() -> None:
    rows = []
    for g, spec in GROUPS.items():
        for name, pat in spec["configs"].items():
            for p in sorted(glob.glob(pat)):
                rows += rows_of(p, g, name)
    v10 = Path("data/results/report_c/numbers.json")
    if v10.exists():  # bản trước (v10) chỉ còn trong numbers.json; fold 0 + 3, seed 1
        for r in json.load(open(v10, encoding="utf-8"))["ablation"]:
            if r["config"].startswith("v10"):
                rows.append(dict(group="pilot", config="v10: bản trước", fold=r["fold"],
                                 test="full" if r["test"] in ("full", "nguyên vẹn") else "masked",
                                 **{"lá": r["leaf"], "tầng 2": r["t2"], "tầng 1": r["t1"]}))
    df = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "per_fold.csv", index=False, encoding="utf-8")

    paired = []
    for g, spec in GROUPS.items():
        ref = df[(df.group == g) & (df.config == spec["ref"])].set_index(["fold", "test"])
        for name, sub in df[df.group == g].groupby("config", sort=False):
            s = sub.set_index(["fold", "test"])
            common = s.index.intersection(ref.index)
            for t in ("full", "masked"):
                idx = [i for i in common if i[1] == t]
                if not idx:
                    continue
                dlt = s.loc[idx, list(METRICS.values())] - ref.loc[idx, list(METRICS.values())]
                paired.append(dict(group=g, config=name, test=t, folds=",".join(str(i[0]) for i in idx),
                                   **{n: s.loc[idx, n].mean() for n in METRICS.values()},
                                   **{f"Δ {n}": dlt[n].mean() for n in METRICS.values()},
                                   **{f"Δ {n} min": dlt[n].min() for n in METRICS.values()},
                                   **{f"Δ {n} max": dlt[n].max() for n in METRICS.values()}))
    pr = pd.DataFrame(paired)
    pr.to_csv(OUT / "paired.csv", index=False, encoding="utf-8")
    pd.set_option("display.width", 220)
    for g in GROUPS:
        print(f"\n== {g}: theo fold (lá)")
        print(df[df.group == g].pivot_table(index="config", columns=["test", "fold"], values="lá", sort=False)
              .round(3).to_string())
        print(f"== {g}: trung bình trên các fold có cả bản cuối")
        cols = ["config", "test", "folds", *METRICS.values(), *[f"Δ {n}" for n in METRICS.values()]]
        print(pr[pr.group == g][cols].round(3).to_string(index=False))
    boot = bootstrap_input()
    boot.to_csv(OUT / "bootstrap_input.csv", index=False, encoding="utf-8")
    print("\n== input: gộp dự đoán fold 0, 3, 4, macro-F1 trên 13 lá giữ lại; bootstrap theo repo")
    print(boot.round(3).to_string(index=False))
    print("->", OUT)


def macro_f1(y: np.ndarray, p: np.ndarray, k: int) -> float:
    """macro-F1 trên các lớp 0..k-1 có trong y (mã số nguyên), nhanh hơn sklearn khi lặp bootstrap."""
    tp = np.bincount(y[y == p], minlength=k)[:k]
    nt, npred = np.bincount(y, minlength=k + 1)[:k], np.bincount(p, minlength=k + 1)[:k]
    has = nt > 0
    return float(np.mean((2 * tp / np.maximum(nt + npred, 1))[has]))


def bootstrap_input(n_boot: int = 1000, data: str = "data/kaggle_log_ds") -> pd.DataFrame:
    """Chênh lệch so với C (seed 0, T4) trên dự đoán gộp 3 fold; lấy mẫu lại repo có hoàn lại (cùng repo cho mọi
    cấu hình). Lá ngoài cây (compatibility, flaky: quá ít mẫu, bị bỏ khi train) không tính vào macro-F1."""
    tree = json.load(open(f"{data}/label_tree.json", encoding="utf-8"))
    runs = pd.read_parquet(f"{data}/runs.parquet", columns=["run_id", "repository", "leaf"]).set_index("run_id")
    l3 = tree["l3"]
    l2 = tree["l2"]
    l1 = tree["l1"]
    m3 = {x: i for i, x in enumerate(l3)}
    to2 = np.array([l2.index(tree["parent"][x]) for x in l3] + [len(l2)])
    to1 = np.array([l1.index(tree["group"][x]) for x in l2] + [len(l1)])
    preds = {}
    for name, pat in GROUPS["input"]["configs"].items():
        fs = sorted(f.replace(".json", ".preds.parquet") for f in glob.glob(pat))
        preds[name] = pd.concat(pd.read_parquet(f, columns=["test", "run_id", "pred"]) for f in fs)
    out = []
    for t in ("full", "masked"):
        base = preds[GROUPS["input"]["ref"]]
        ids = base[base.test == t].run_id.values
        ids = ids[np.isin(runs.loc[ids, "leaf"].values, l3)]
        y3 = runs.loc[ids, "leaf"].map(m3).values
        reps, rep_idx = np.unique(runs.loc[ids, "repository"].values, return_inverse=True)
        rows_of_rep = [np.where(rep_idx == r)[0] for r in range(len(reps))]
        P = {}
        for name, df in preds.items():
            s = df[df.test == t].set_index("run_id").pred
            P[name] = s.reindex(ids).map(m3).fillna(len(l3)).astype(int).values

        def scores(idx, p3):
            y = y3[idx]
            q = p3[idx]
            return np.array([macro_f1(y, q, len(l3)), macro_f1(to2[y], to2[q], len(l2)),
                             macro_f1(to1[to2[y]], to1[to2[q]], len(l1))])

        rng = np.random.default_rng(0)
        samples = [np.concatenate([rows_of_rep[r] for r in rng.integers(0, len(reps), len(reps))])
                   for _ in range(n_boot)]
        allidx = np.arange(len(ids))
        ref = GROUPS["input"]["ref"]
        for name in preds:
            point = scores(allidx, P[name]) - scores(allidx, P[ref])
            d = np.array([scores(s, P[name]) - scores(s, P[ref]) for s in samples]) if name != ref else None
            row = dict(config=name, test=t, n=len(ids), repos=len(reps))
            for j, lv in enumerate(("lá", "tầng 2", "tầng 1")):
                row[lv] = scores(allidx, P[name])[j]
                row[f"Δ {lv}"] = point[j]
                if d is not None:
                    lo, hi = np.percentile(d[:, j], [2.5, 97.5])
                    row[f"Δ {lv} CI95"] = f"[{lo:+.3f}; {hi:+.3f}]"
            out.append(row)
    return pd.DataFrame(out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
