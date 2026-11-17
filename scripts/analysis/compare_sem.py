"""So ghép cặp cách cắt log mới (semantic v2 + chọn lỗi đầu, kernel p3-sem-k1) với mô hình hiện tại C, cùng fold 0,
seed 0, T4, cùng mã (p3-code 04/11) và cùng --extra; chỉ khác chunks.parquet (10/11/2026).

Macro-F1 trên 13 lá (bỏ compatibility, flaky như mọi bảng khác), tầng 2, tầng 1; log đầy đủ và log che dòng bằng chứng.
Khoảng tin cậy 95%: lấy mẫu lại repo có hoàn lại (1000 lần), cùng mẫu cho cả hai mô hình (giống ablation_summary).

    python scripts/analysis/compare_sem.py   # -> data/results/sem/compare_fold0.csv, per_leaf_fold0.csv
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from ablation_summary import macro_f1  # noqa: E402

DATA = Path("data/kaggle_log_ds")
REF, NEW = "data/results/c/k1/C_s0_fold0.preds.parquet", "data/results/sem/k1/SEM_s0_fold0.preds.parquet"
OUT = Path("data/results/sem")


def main(n_boot: int = 1000) -> None:
    tree = json.load(open(DATA / "label_tree.json", encoding="utf-8"))
    l3, l2, l1 = tree["l3"], tree["l2"], tree["l1"]
    m3 = {x: i for i, x in enumerate(l3)}
    to2 = np.array([l2.index(tree["parent"][x]) for x in l3] + [len(l2)])
    to1 = np.array([l1.index(tree["group"][x]) for x in l2] + [len(l1)])
    runs = pd.read_parquet(DATA / "runs.parquet", columns=["run_id", "repository", "leaf"]).set_index("run_id")
    P = {n: pd.read_parquet(f, columns=["test", "run_id", "pred"]) for n, f in (("hiện tại", REF), ("cắt mới", NEW))}
    rows, leaf_rows = [], []
    for t in ("full", "masked"):
        ids = np.intersect1d(*(p[p.test == t].run_id.values for p in P.values()))
        ids = ids[np.isin(runs.loc[ids, "leaf"].values, l3)]
        y = runs.loc[ids, "leaf"].map(m3).values
        pr = {n: p[p.test == t].set_index("run_id").pred.reindex(ids).map(m3).fillna(len(l3)).astype(int).values
              for n, p in P.items()}
        reps, ri = np.unique(runs.loc[ids, "repository"].values, return_inverse=True)
        by_rep = [np.where(ri == r)[0] for r in range(len(reps))]
        sc = lambda idx, q: np.array([macro_f1(y[idx], q[idx], len(l3)), macro_f1(to2[y[idx]], to2[q[idx]], len(l2)),
                                      macro_f1(to1[to2[y[idx]]], to1[to2[q[idx]]], len(l1))])
        rng = np.random.default_rng(0)
        boots = [np.concatenate([by_rep[r] for r in rng.integers(0, len(reps), len(reps))]) for _ in range(n_boot)]
        a = np.arange(len(ids))
        base, new = sc(a, pr["hiện tại"]), sc(a, pr["cắt mới"])
        d = np.array([sc(b, pr["cắt mới"]) - sc(b, pr["hiện tại"]) for b in boots])
        for j, lv in enumerate(("lá", "tầng 2", "tầng 1")):
            lo, hi = np.percentile(d[:, j], [2.5, 97.5])
            rows.append(dict(test=t, tầng=lv, n=len(ids), repos=len(reps), hiện_tại=base[j], cắt_mới=new[j],
                             chênh=new[j] - base[j], CI95=f"[{lo:+.3f}; {hi:+.3f}]"))
        for i, leaf in enumerate(l3):
            f = lambda q: 2 * ((y == i) & (q == i)).sum() / max((y == i).sum() + (q == i).sum(), 1)
            leaf_rows.append(dict(test=t, lá=leaf, n=int((y == i).sum()), hiện_tại=f(pr["hiện tại"]),
                                  cắt_mới=f(pr["cắt mới"]), chênh=f(pr["cắt mới"]) - f(pr["hiện tại"])))
    OUT.mkdir(parents=True, exist_ok=True)
    r, lr = pd.DataFrame(rows), pd.DataFrame(leaf_rows)
    r.to_csv(OUT / "compare_fold0.csv", index=False)
    lr.to_csv(OUT / "per_leaf_fold0.csv", index=False)
    print(r.round(3).to_string(index=False))
    print(lr.pivot_table(index="lá", columns="test", values=["hiện_tại", "cắt_mới", "chênh"]).round(3).to_string())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
