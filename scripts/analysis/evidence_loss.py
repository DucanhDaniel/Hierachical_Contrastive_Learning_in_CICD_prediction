"""Vì sao run mất dòng bằng chứng trước khi tới mô hình (30/10/2026): phân rã theo bước + thử cách đặt cửa sổ khác (không dùng nhãn).

    PYTHONPATH=src python scripts/analysis/evidence_loss.py   # đọc data/run_dataset/chunks.parquet, data/kaggle_log_ds/runs.parquet
"""
import sys
from collections import Counter

import pandas as pd

from project3.model.inputs import ERR, FAIL_LINE, chunk_score, focus_window, select_chunks
from project3.model.text import mask_text

N = 1600
runs = pd.read_parquet("data/kaggle_log_ds/runs.parquet").drop_duplicates("run_id").set_index("run_id")
KEY = {r: k for r, k in runs.key.fillna("").items() if k}
LEAF = runs.leaf.to_dict()


def win(text, mode):
    """Cửa sổ N ký tự; mode: last (hiện tại) | first | last90 | split | firstlast."""
    first, _, rest = text.partition("\n")
    head = first[:200] + "\n"
    if len(rest) <= N:
        return head + rest
    hits = [m.start() for m in FAIL_LINE.finditer(rest)] or [m.start() for m in ERR.finditer(rest)]
    if not hits:
        return head + rest[-N:]
    cut = lambda c, n, before: rest[max(0, min(c - before, len(rest) - n)):][:n]
    if mode == "last":
        return head + cut(hits[-1], N, 2 * N // 3)
    if mode == "first":
        return head + cut(hits[0], N, N // 3)
    if mode == "last90":
        return head + cut(hits[-1], N, 9 * N // 10)
    if mode == "split":  # nửa quanh dòng lỗi đầu, nửa quanh dòng lỗi cuối
        return head + cut(hits[0], N // 2, N // 6) + "\n" + cut(hits[-1], N // 2, N // 3)
    raise ValueError(mode)


MODES = ["last", "first", "last90", "split"]
stage = Counter()
by_leaf = Counter()
alt = Counter()
gap = []
n_runs = 0


def process(rid, rows):
    global n_runs
    k = KEY.get(rid)
    if not k:
        return
    n_runs += 1
    jobs = {}
    for j, c, t in rows:
        jobs.setdefault(j, []).append((c, t))
    jobs = [[t for _, t in sorted(v)] for _, v in sorted(jobs.items())]
    scores = [[chunk_score(mask_text(t, k), ci == len(job) - 1) for ci, t in enumerate(job)] for job in jobs]
    picked = [jobs[j][c] for j, c in select_chunks(scores, 8)]
    kept = [t[-6000:] for t in picked]
    if not any(k in t for job in jobs for t in job):
        s = "1. không có trong log đã lưu"
    elif not any(k in t for t in picked):
        s = "2. khối chứa bằng chứng không được chọn"
    elif not any(k in t for t in kept):
        s = "3. bị cắt khi giữ 6.000 ký tự cuối khối"
    elif not any(k in win(t, "last") for t in kept):
        s = "4. bị cắt khi lấy cửa sổ 1.600 ký tự"
        t = next(t for t in kept if k in t)
        rest = t.partition("\n")[2]
        hits = [m.start() for m in FAIL_LINE.finditer(rest)] or [m.start() for m in ERR.finditer(rest)]
        e = rest.find(k)
        if hits and e >= 0:
            gap.append(hits[-1] - e)  # >0: bằng chứng nằm TRƯỚC dòng lỗi cuối
    else:
        s = "5. còn trong cửa sổ mô hình đọc"
    stage[s] += 1
    by_leaf[(LEAF.get(rid), s[:1])] += 1
    for m in MODES:
        alt[m] += any(k in win(t, m) for t in kept)


import duckdb
con = duckdb.connect()
con.execute("SET memory_limit='2GB'")
for part in range(8):
    q = con.execute("SELECT run_id, job_id, chunk_idx, text FROM 'data/run_dataset/chunks.parquet' "
                    f"WHERE run_id % 8 = {part} ORDER BY run_id, job_id, chunk_idx")
    cur, buf = None, []
    while True:
        rows = q.fetchmany(20000)
        if not rows:
            break
        for rid, j, c, t in rows:
            if rid != cur:
                if cur is not None:
                    process(cur, buf)
                cur, buf = rid, []
            buf.append((j, c, t or ""))
    if cur is not None:
        process(cur, buf)
    print(f"nhóm {part}: {n_runs} run", flush=True)

print(f"{n_runs} run có dòng bằng chứng")
for s, v in sorted(stage.items()):
    print(f"  {s:45s} {v:6d}  {v / n_runs:.1%}")
g = pd.Series(gap)
print(f"\nnhóm 4: bằng chứng nằm trước dòng lỗi cuối {(g > 0).mean():.0%}; khoảng cách (ký tự) trung vị {g.median():.0f}, "
      f"p75 {g.quantile(.75):.0f}")
print("\ncách đặt cửa sổ 1.600 ký tự (cùng số token) -> tỉ lệ run giữ được bằng chứng:")
for m in MODES:
    print(f"  {m:8s} {alt[m] / n_runs:.1%}")
t = pd.Series(by_leaf).unstack(fill_value=0)
t = t.div(t.sum(1), axis=0).round(2)
t["n"] = pd.Series(by_leaf).unstack(fill_value=0).sum(1)
print("\ntheo lá (tỉ lệ từng nhóm):")
print(t.sort_values("n", ascending=False).to_string())
