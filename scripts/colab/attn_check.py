"""Kiểm chứng attention của v10 (30/10/2026): đoạn log được chú ý nhiều nhất có chứa dòng bằng chứng của quy tắc không.

Đầu vào: results_fold{k}.preds.parquet chạy với --save-repr (cột attn = JSON [(job, đoạn, trọng số)] trên test full).
So với 3 cách chọn đoạn không học: ngẫu nhiên (kỳ vọng), đoạn cuối, đoạn nhiều dòng báo fail nhất (inputs.FAIL_LINE).
Chỉ chấm được run có dòng bằng chứng (nhãn quy tắc); run `?` không có bằng chứng để so.

    python scripts/colab/attn_check.py data/kaggle_log_ds data/results/attn/a/results_fold0.preds.parquet ...
"""
import json
import sys
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd

from project3.model.data import load_pack
from project3.model.inputs import FAIL_LINE, focus_window

clip = partial(focus_window, n=1600)  # đúng cửa sổ v10 dùng (--window 1600)


def main(data: Path, files: list) -> None:
    runs, chunks, _ = load_pack(data)
    runs = runs.drop_duplicates("run_id").set_index("run_id")
    p = pd.concat([pd.read_parquet(f) for f in files])
    p = p[p.test == "full"]
    rows = []
    for rid, pred, attn in zip(p.run_id, p.pred, p.attn):
        key = runs.key.get(rid) or ""
        if not key or rid not in chunks:
            continue
        att = [(ji, ci, w) for ji, ci, w in json.loads(attn) if ci >= 0]
        if not att:
            continue
        seen = {(ji, ci): clip(chunks[rid][ji][ci]) for ji, ci, _ in att}
        ev = {k: key in t for k, t in seen.items()}
        top = sorted(att, key=lambda x: -x[2])
        fails = max(seen, key=lambda k: (len(FAIL_LINE.findall(seen[k])), k))
        rows.append(dict(run_id=rid, leaf=runs.leaf[rid], correct=pred == runs.leaf[rid], n=len(att),
                         cover=any(ev.values()), top1=ev[top[0][:2]], top2=any(ev[t[:2]] for t in top[:2]),
                         rand=np.mean(list(ev.values())), last=ev[max(seen)], fail=ev[fails],
                         lines=seen[top[0][:2]].count("\n") + 1, w1=top[0][2]))
    d = pd.DataFrame(rows)
    print(f"{len(d)} run test có dòng bằng chứng; số đoạn mỗi run: trung vị {d.n.median():.0f}, "
          f"{(d.n >= 2).mean():.0%} run có ≥ 2 đoạn")
    print(f"dòng bằng chứng nằm trong các đoạn mô hình đọc: {d.cover.mean():.1%}")
    c = d[d.cover]
    for name, sub in (("mọi run có bằng chứng trong đoạn đọc", c), ("chỉ run có ≥ 2 đoạn", c[c.n >= 2]),
                      ("run ≥ 2 đoạn, mô hình đoán đúng", c[(c.n >= 2) & c.correct]),
                      ("run ≥ 2 đoạn, mô hình đoán sai", c[(c.n >= 2) & ~c.correct])):
        print(f"\n{name} ({len(sub)} run): đoạn chứa bằng chứng được chọn đúng")
        for col, lab in (("top1", "attention cao nhất"), ("top2", "attention top 2"), ("rand", "ngẫu nhiên (kỳ vọng)"),
                         ("last", "đoạn cuối"), ("fail", "đoạn nhiều dòng fail nhất")):
            print(f"  {lab:28s} {sub[col].mean():.1%}")
    print(f"\nsố dòng của đoạn attention cao nhất: trung vị {c.lines.median():.0f}, p90 {c.lines.quantile(.9):.0f}")
    m = c[c.n >= 2]
    print("\ntheo lá (run ≥ 2 đoạn): attention top1 / đoạn nhiều dòng fail nhất / ngẫu nhiên")
    print(m.groupby("leaf")[["top1", "fail", "rand"]].mean().join(m.leaf.value_counts().rename("n"))
          .sort_values("n", ascending=False).round(2).to_string())
    d.to_parquet(Path(files[0]).parent / "attn_check.parquet", index=False)


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2:])
