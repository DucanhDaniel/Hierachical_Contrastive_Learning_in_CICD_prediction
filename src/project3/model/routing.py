"""Đánh giá vai trò định tuyến của mô hình (20/10/2026, docs/ket-qua-dinh-tuyen-2026-10-20.md, hướng kết hợp với LLM).

E2  attention chỉ đúng chỗ: đoạn log được chú ý nhiều nhất có chứa dòng bằng chứng của quy tắc không (hit@1, hit@3),
    so với lấy đoạn cuối / ngẫu nhiên. Chỉ tính run có ít nhất một đoạn chứa bằng chứng (key = 120 ký tự đầu dòng bằng chứng).
E4  định tuyến theo độ tin cậy: AUROC phát hiện dự đoán sai (mức lá) và đường cong "giữ lại x% run tự tin nhất -> độ đúng";
    tín hiệu: (a) xác suất của mô hình (logp), (b) kNN trên z (độ tương đồng TB tới 10 láng giềng train, tỉ lệ láng giềng
    đồng ý với dự đoán). Ước tính độ đúng cả hệ thống nếu run bị chuyển sang LLM đạt LLM_ACC (đo ở model.llm).

Cần output của model.train --save-repr.
    python -m project3.model.routing data/results/log_model/v5_repr
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from .config import PACK
from .data import read_fold_outputs
from .labels import LabelTree

LLM_ACC = 0.724  # độ đúng mức lá của LLM bản 1 trên mẫu nhãn quy tắc (log nguyên vẹn), thay khi có số tốt hơn


def e2(p: pd.DataFrame, runs: pd.DataFrame, ch: pd.DataFrame) -> list:
    key = runs.key.fillna("").to_dict()
    text = {(r, j, c): t for r, j, c, t in zip(ch.run_id, ch.job_rank, ch.chunk_rank, ch.text)}
    out = []
    for (v,), g in p[p.test == "full"].groupby(["variant"]):
        hit1 = hit3 = last = rnd = n = 0
        rng = np.random.default_rng(0)
        for r, a in zip(g.run_id, g.attn):
            k = key.get(r, "")
            a = [x for x in json.loads(a) if x[1] >= 0]
            ev = [k and k in text.get((r, j, c), "") for j, c, _ in a]
            if not k or not any(ev):
                continue
            n += 1
            order = np.argsort([-w for _, _, w in a])
            hit1 += ev[order[0]]
            hit3 += any(ev[i] for i in order[:3])
            last += ev[-1]
            rnd += ev[rng.integers(len(ev))]
        out.append({"variant": v, "n": n, "hit@1": hit1 / n, "hit@3": hit3 / n, "đoạn cuối": last / n, "ngẫu nhiên": rnd / n})
    return out


def e4(p: pd.DataFrame, tr: pd.DataFrame, runs: pd.DataFrame, n_leaves: int) -> list:
    out = []
    for (v, fold), g in p[p.test == "full"].groupby(["variant", "fold"]):
        y = g.run_id.map(runs.leaf).values
        ok = np.asarray(g.pred, dtype=object) == np.asarray(y, dtype=object)
        lp = np.stack(g.logp.values).astype(np.float32)
        conf_p = lp[:, -n_leaves:].max(1)  # log xác suất lá cao nhất (đầu tầng 3)
        t = tr[(tr.variant == v) & (tr.fold == fold)]
        Z = np.stack(t.z.values).astype(np.float32)
        Z /= np.linalg.norm(Z, axis=1, keepdims=True) + 1e-6
        Q = np.stack(g.z.values).astype(np.float32)
        Q /= np.linalg.norm(Q, axis=1, keepdims=True) + 1e-6
        sim = Q @ Z.T
        nn = np.argsort(-sim, 1)[:, :10]
        top = np.take_along_axis(sim, nn, 1)
        tp, gp = np.asarray(t.pred, dtype=object), np.asarray(g.pred, dtype=object)
        agree = (tp[nn] == gp[:, None]).mean(1)
        sig = {"xác suất": conf_p, "kNN tương đồng": top.mean(1), "kNN đồng ý": agree,
               "xác suất + kNN": conf_p / (np.abs(conf_p).max() + 1e-6) + top.mean(1) + agree}
        for name, s in sig.items():
            row = {"variant": v, "fold": fold, "tín hiệu": name, "acc": ok.mean(),
                   "AUROC sai": roc_auc_score(~ok, -s) if 0 < ok.mean() < 1 else np.nan}
            order = np.argsort(-s)
            for keep in (0.9, 0.8, 0.7, 0.5):
                kept = order[: int(len(order) * keep)]
                row[f"acc giữ {int(keep * 100)}%"] = ok[kept].mean()
                row[f"hệ thống, gửi LLM {100 - int(keep * 100)}%"] = (ok[kept].sum() + LLM_ACC * (len(ok) - len(kept))) / len(ok)
            out.append(row)
    return out


def main(d: Path, pack: Path = PACK) -> None:
    runs = pd.read_parquet(pack / "runs.parquet").drop_duplicates("run_id").set_index("run_id")
    n_leaves = len(LabelTree.load(pack / "label_tree.json").l3)
    p = read_fold_outputs(d, "results_fold*.preds.parquet")
    tr = read_fold_outputs(d, "results_fold*.train_*.parquet")
    ch = pd.read_parquet(pack / "chunks.parquet").sort_values(["run_id", "job_id", "chunk_idx"])
    ch = ch[ch.run_id.isin(set(p.run_id))]
    ch["job_rank"] = ch.groupby("run_id").job_id.rank(method="dense").astype(int) - 1  # cùng thứ tự với data.load_pack
    ch["chunk_rank"] = ch.groupby(["run_id", "job_id"]).cumcount()
    r2 = pd.DataFrame(e2(p, runs, ch))
    r4 = pd.DataFrame(e4(p, tr, runs, n_leaves))
    pd.set_option("display.width", 250)
    print("E2 — attention chỉ đúng đoạn chứa bằng chứng\n", r2.round(3).to_string(index=False))
    print("\nE4 — định tuyến theo độ tin cậy (TB các fold)\n",
          r4.drop(columns="fold").groupby(["variant", "tín hiệu"]).mean().round(3).to_string())
    r2.to_csv(d / "e2.csv", index=False)
    r4.to_csv(d / "e4.csv", index=False)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(Path(sys.argv[1]))
