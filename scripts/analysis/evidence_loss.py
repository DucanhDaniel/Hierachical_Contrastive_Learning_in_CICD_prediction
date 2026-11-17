"""Dòng bằng chứng bị mất ở bước nào của đường ống đầu vào hiện tại (10/11/2026, chuẩn bị đổi cách cắt log).

Bước: (0) log đã lưu có chứa dòng bằng chứng không -> (1) có nằm trong 8 đoạn được chọn không -> (2) có còn sau khi
cắt mỗi đoạn xuống cửa sổ 1600 ký tự (focus_window, chế độ split, giống cấu hình C) không. Chỉ CPU, chạy lại đúng
code của model.pack / model.inputs; không dùng tokenizer (1600 ký tự ≈ 512 token theo ước lượng 3,1 ký tự/token).

    PYTHONPATH=src python scripts/analysis/evidence_loss.py [--n 15000]
"""
import argparse
from collections import defaultdict
from pathlib import Path

import duckdb
import pandas as pd

from project3.model.inputs import chunk_score, focus_window, select_chunks
from project3.model.pack import MAX_CHUNKS
from project3.model.text import mask_text

OUT = Path("data/results/chunking")


def main(n: int) -> None:
    runs = pd.read_parquet("data/kaggle_log_ds/runs.parquet", columns=["run_id", "leaf", "key", "repository"])
    runs = runs[runs.key.fillna("") != ""]
    runs = pd.concat([g.sample(min(len(g), max(n // runs.leaf.nunique(), 1)), random_state=0)
                      for _, g in runs.groupby("leaf")])
    ids = runs[["run_id"]]
    ch = duckdb.sql("""SELECT run_id, job_id, chunk_idx, kind, text, has_evidence
                       FROM 'data/run_dataset/chunks.parquet' JOIN ids USING (run_id)
                       ORDER BY run_id, job_id, chunk_idx""").df()
    by_run = defaultdict(lambda: defaultdict(list))
    for r in ch.itertuples(index=False):
        by_run[r.run_id][r.job_id].append(r)
    key = dict(zip(runs.run_id, runs.key))
    rows = []
    for run_id, jobs in by_run.items():
        jobs = [v for _, v in sorted(jobs.items())]
        k = key[run_id]
        scores = [[chunk_score(mask_text(c.text, k), ci == len(job) - 1) for ci, c in enumerate(job)] for job in jobs]
        picked = [jobs[j][c] for j, c in select_chunks(scores, MAX_CHUNKS)]
        ev_chunks = [c for job in jobs for c in job if c.has_evidence]
        rows.append({"run_id": run_id, "n_chunks": sum(map(len, jobs)),
                     "s0_in_log": bool(ev_chunks),
                     "s1_in_picked": any(c.has_evidence for c in picked),
                     "s2_in_window": any(k in focus_window(c.text, 1600, "split") for c in picked),
                     "ev_in_window_chunk": any(c.has_evidence and c.kind.endswith("+win") for c in ev_chunks)})
    d = pd.DataFrame(rows).merge(runs[["run_id", "leaf"]], on="run_id")
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_parquet(OUT / "evidence_loss.parquet", index=False)
    cols = ["s0_in_log", "s1_in_picked", "s2_in_window"]
    print(f"{len(d)} run có khoá bằng chứng")
    print(d[cols].mean().round(3).to_string())
    print(d.groupby("leaf")[cols].mean().round(2).to_string())
    lost = d[d.s0_in_log & ~d.s2_in_window]
    print(f"mất ở bước chọn đoạn: {(d.s0_in_log & ~d.s1_in_picked).mean():.3f}; "
          f"mất ở bước cắt cửa sổ: {(d.s1_in_picked & ~d.s2_in_window).mean():.3f}; "
          f"trong số run bị mất, bằng chứng nằm trong cửa sổ 40 dòng: {lost.ev_in_window_chunk.mean():.3f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=15000)
    main(ap.parse_args().n)
