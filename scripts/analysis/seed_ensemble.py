"""Bảng 5 fold của một mô hình: từng seed, trung bình seed, gộp seed (trung bình log xác suất 3 tầng rồi giải mã theo cây).
Chỉ đọc *.preds.parquet (cột logp), không tải mô hình. Mỗi nhóm = tên:glob (nhiều glob nối bằng |) các file preds của mọi fold và seed.

    python scripts/analysis/seed_ensemble.py data/kaggle_log_ds \
        "v10:data/results/doc/**/results_fold*.preds.parquet" "C:data/results/c/**/C_s*_fold*.preds.parquet"
"""
import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from project3.model.labels import LabelTree
from project3.model.metrics import hier_scores
from project3.model.nn.net import decode


def fold_of(path: str) -> int:
    return int(Path(path).name.split("fold")[1][0])


def main(data: Path, groups: list) -> None:
    tree = LabelTree.load(data / "label_tree.json")
    leaf = pd.read_parquet(data / "runs.parquet", columns=["run_id", "leaf"]).drop_duplicates("run_id").set_index("run_id").leaf
    n1, n2 = len(tree.l1), len(tree.l2)
    rows = []
    for name, pat in (g.split(":", 1) for g in groups):
        files = sorted(f for x in pat.split("|") for f in glob.glob(x, recursive=True))
        p = pd.concat([pd.read_parquet(f, columns=["seed", "test", "run_id", "pred", "logp"]).assign(fold=fold_of(f))
                       for f in files])
        for (fold, test), d in p.groupby(["fold", "test"]):
            truth = leaf.loc[d.run_id.unique()]
            for seed, s in d.groupby("seed"):
                s = s.set_index("run_id").loc[truth.index]
                rows.append(dict(model=name, test=test, fold=fold, seed=str(seed),
                                 **hier_scores(truth.tolist(), s.pred.tolist(), tree.parent, tree.group)))
            lp = np.mean([np.stack(s.set_index("run_id").loc[truth.index].logp.to_numpy()).astype(np.float32)
                          for _, s in d.groupby("seed")], axis=0)
            o = [torch.from_numpy(x) for x in (lp[:, :n1], lp[:, n1:n1 + n2], lp[:, n1 + n2:])]
            pred, _ = decode(*o, tree)
            rows.append(dict(model=name, test=test, fold=fold, seed="gộp", n_seed=d.seed.nunique(),
                             **hier_scores(truth.tolist(), pred, tree.parent, tree.group)))
    r = pd.DataFrame(rows).drop(columns="F1_l3")
    cols = ["macroF1_l3", "macroF1_l2", "macroF1_l1"]
    print("== macro-F1 lá theo fold (full | masked)")
    print(r.pivot_table(index=["model", "seed"], columns=["test", "fold"], values="macroF1_l3").round(3).to_string())
    single = r[r.seed != "gộp"].groupby(["model", "test", "fold"])[cols].mean().reset_index().assign(seed="TB seed")
    allr = pd.concat([r, single])
    print("\n== trung bình 5 fold: lá / tầng 2 / tầng 1")
    print(allr.groupby(["model", "seed", "test"])[cols].mean().round(3).unstack("test").to_string())
    out = Path("data/results/c/seed_ensemble.csv")
    allr.to_csv(out, index=False)
    print("->", out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(Path(sys.argv[1]), sys.argv[2:])
