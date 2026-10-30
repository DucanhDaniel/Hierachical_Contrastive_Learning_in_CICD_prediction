"""Chấm việc chỉ dòng lỗi của v10 --line-attn (30/10/2026): dòng mô hình cho điểm cao nhất có phải dòng bằng chứng của
quy tắc không; so với cách chọn dòng không học trên cùng các đoạn mô hình đọc (cửa sổ chia đôi).

Đầu vào: {A,B,C}_fold{k}.preds.parquet chạy với --save-repr (cột attn = [(job, đoạn, trọng số)], cột lines = top 5
[(job, đoạn, dòng, trọng số, văn bản)] khi --line-attn) + bản tham chiếu cửa sổ cũ (data/results/attn, mode last).
Chỉ chạy CPU, không tải mô hình.

    python scripts/colab/line_check.py data/kaggle_log_ds data/results/lines data/results/attn
"""
import json
import sys
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd

from project3.model.data import load_pack
from project3.model.inputs import ERR, FAIL_LINE, focus_window

CLIP = {m: partial(focus_window, n=1600, mode=m) for m in ("last", "split")}


def baselines(lines: list, key: str) -> dict:
    """lines = [(job, đoạn, dòng, văn bản)] theo thứ tự log; chọn dòng theo dấu hiệu lỗi, không học."""
    fail = [x for x in lines if FAIL_LINE.search(x[3])]
    err = [x for x in lines if ERR.search(x[3])]
    hit = lambda xs: [key in x[3] for x in xs]
    return {"fail_dau@1": any(hit(fail[:1])), "fail_dau@3": any(hit(fail[:3])),
            "fail_cuoi@1": any(hit(fail[-1:])), "fail_cuoi@3": any(hit(fail[-3:])),
            "loi_dau@1": any(hit(err[:1])), "loi_dau@3": any(hit(err[:3])),
            "ngau_nhien@1": np.mean(hit(lines)) if lines else 0.0}


def score(f: Path, runs, chunks, mode: str) -> pd.DataFrame:
    p = pd.read_parquet(f)
    p = p[p.test == "full"]
    has_lines = "lines" in p and p.lines.notna().any()
    rows = []
    for rid, pred, attn, top in zip(p.run_id, p.pred, p.attn, p.lines if has_lines else [None] * len(p)):
        key = runs.key.get(rid) or ""
        if not key or rid not in chunks:
            continue
        att = [(ji, ci, w) for ji, ci, w in json.loads(attn) if ci >= 0]
        if not att:
            continue
        seen = {(ji, ci): CLIP[mode](chunks[rid][ji][ci]) for ji, ci, _ in sorted(att)}
        lines = [(ji, ci, n, t) for (ji, ci), x in seen.items() for n, t in enumerate(x.split("\n"))]
        cover = any(key in t for *_, t in lines)
        c1 = max(att, key=lambda x: x[2])[:2]
        r = dict(run_id=rid, leaf=runs.leaf[rid], correct=pred == runs.leaf[rid], n_chunks=len(att), cover=cover,
                 doan_top1=key in seen[c1])
        if has_lines:
            top = json.loads(top)
            full = {(ji, ci, n): t for ji, ci, n, t in lines}
            hit = [key in full.get((ji, ci, n), t) for ji, ci, n, _, t in top]
            r.update({"mo_hinh@1": any(hit[:1]), "mo_hinh@3": any(hit[:3]), "mo_hinh@5": any(hit),
                      "w1": top[0][3] if top else 0.0})
        r.update(baselines(lines, key))
        rows.append(r)
    return pd.DataFrame(rows)


def main(data: Path, lines_dir: Path, ref_dir: Path) -> None:
    runs, chunks, _ = load_pack(data)
    runs = runs.drop_duplicates("run_id").set_index("run_id")
    res = {}
    for cfg in "ABC":
        res[cfg] = pd.concat([score(f, runs, chunks, "split") for f in sorted(lines_dir.glob(f"*/{cfg}_fold*.preds.parquet"))])
    res["cũ"] = pd.concat([score(f, runs, chunks, "last") for f in sorted(ref_dir.glob("*/results_fold*.preds.parquet"))])

    print("== Phân loại (macro-F1 lá, test full / che) theo fold")
    for f in sorted(lines_dir.glob("*/[ABC]_fold*.json")):
        r = json.loads(f.read_text(encoding="utf-8"))["soft_seed1"]
        print(f"  {f.stem:10s} " + " | ".join(f"{t} " + " / ".join(f"{r[t][f'macroF1_l{i}']:.3f}" for i in (3, 2, 1))
                                             for t in ("full", "masked")))

    print("\n== Đoạn: bằng chứng nằm trong phần mô hình đọc; đoạn attention cao nhất chứa bằng chứng (run ≥ 2 đoạn)")
    for cfg, d in res.items():
        m = d[d.cover & (d.n_chunks >= 2)]
        print(f"  {cfg:3s} {len(d):5d} run | có trong phần đọc {d.cover.mean():.1%} | đoạn top1 {m.doan_top1.mean():.1%}")

    cols = ["mo_hinh@1", "mo_hinh@3", "mo_hinh@5", "fail_dau@1", "fail_dau@3", "fail_cuoi@1", "fail_cuoi@3",
            "loi_dau@1", "loi_dau@3", "ngau_nhien@1"]
    for cfg in "BC":
        d = res[cfg]
        c = d[d.cover]
        print(f"\n== Dòng, cấu hình {cfg}: {len(c)} run có bằng chứng trong phần đọc "
              f"(số dòng ứng viên: cả cửa sổ, chưa trừ phần quá 512 token)")
        for name, sub in (("tất cả", c), ("mô hình đoán đúng lá", c[c.correct]), ("đoán sai", c[~c.correct])):
            print(f"  {name:22s} ({len(sub):5d}) " + "  ".join(f"{x} {sub[x].mean():.1%}" for x in cols))
        g = c.groupby("leaf")[["mo_hinh@1", "mo_hinh@3", "fail_dau@1", "loi_dau@1"]].mean()
        print(g.join(c.leaf.value_counts().rename("n")).sort_values("n", ascending=False).round(2).to_string())
        d.to_parquet(lines_dir / f"line_check_{cfg}.parquet", index=False)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
