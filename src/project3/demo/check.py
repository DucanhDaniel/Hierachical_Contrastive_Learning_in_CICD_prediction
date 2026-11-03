"""Kiểm tra tiền xử lý của demo khớp dữ liệu huấn luyện (03/11/2026), chỉ CPU, không chạy mô hình.

Dựng lại bản ghi run từ dữ liệu crawl ở máy (data/{crawl_pr,validate}/<repo>/{runs,jobs}.jsonl, logs/) rồi so đầu ra của
demo.predict.preprocess với gói run `?` (data/kaggle_unknown_ds: đoạn đã chọn, đặc trưng giai đoạn/công cụ, ngữ cảnh CI)
và nhãn quy tắc (`?`). Diff không so (demo lấy qua API, dữ liệu huấn luyện lấy bằng git).

    python -m project3.demo.check --n 300
"""
import argparse
import gzip
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from project3.model.text import ci_context
from project3.pipeline.run_dataset import ROOTS
from .predict import preprocess

UNK = Path("data/kaggle_unknown_ds")


def local_record(repo: str, run_id: int, event: str) -> dict | None:
    d = Path(next(r for r, e in ROOTS.items() if e == event)) / repo.replace("/", "__")
    if not (d / "jobs.jsonl").exists():
        return None
    run = next((json.loads(l) for l in (d / "runs.jsonl").open(encoding="utf-8") if f'"id": {run_id},' in l), None)
    row = next((json.loads(l) for l in (d / "jobs.jsonl").open(encoding="utf-8") if f'"run_id": {run_id},' in l), None)
    if not run or not row:
        return None
    jobs = []
    for j in row["jobs"]:
        tail, txt = d / "logs" / f"{j['id']}.tail.txt.gz", d / "logs" / f"{j['id']}.txt"
        log = gzip.decompress(tail.read_bytes()).decode("utf-8", errors="ignore") if tail.exists() else \
            txt.read_text(encoding="utf-8", errors="ignore") if txt.exists() else None
        jobs.append({**j, "log": log, "rule_text": txt.read_text(encoding="utf-8", errors="ignore") if txt.exists() else None})
    return {"repo": repo, "run_id": run_id, "workflow": run["name"], "event": event, "jobs": jobs,
            "diff": {"vector": [0.0] * 11}}


def main(n: int, seed: int) -> None:
    runs = pd.read_parquet(UNK / "runs.parquet").drop_duplicates("run_id")
    ch = pd.read_parquet(UNK / "chunks.parquet").sort_values(["run_id", "job_id", "chunk_idx"])
    feats = pd.read_parquet(UNK / "features.parquet").drop_duplicates("run_id").set_index("run_id")
    pick = runs.sample(n, random_state=seed)
    ok = {"đoạn": 0, "đặc trưng": 0, "ngữ cảnh CI": 0, "quy tắc ?": 0}
    done, bad = 0, []
    for r in pick.itertuples():
        rec = local_record(r.repository, int(r.run_id), r.event)
        if rec is None:
            continue
        x = preprocess(rec)
        g = ch[ch.run_id == r.run_id]
        ref = [grp.text.tolist() for _, grp in g.groupby("job_id", sort=False)]
        ctx = ci_context(r.workflow or "", r.failed_job_names or "", r.failed_steps or "")[:400]
        res = {"đoạn": x["chunks"] == ref,
               "đặc trưng": x["struct"] is not None and np.allclose(x["struct"], feats.struct_full[r.run_id], atol=1e-5),
               "ngữ cảnh CI": x["ctx"] == ctx,
               "quy tắc ?": x["rule"]["leaf"] is None}
        for k, v in res.items():
            ok[k] += bool(v)
        if not all(res.values()):
            bad.append((int(r.run_id), [k for k, v in res.items() if not v]))
        done += 1
    print(f"{done} run so được (trên {n} rút ngẫu nhiên):", {k: f"{v}/{done}" for k, v in ok.items()})
    for rid, ks in bad[:15]:
        print("  lệch:", rid, ks)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    main(a.n, a.seed)
