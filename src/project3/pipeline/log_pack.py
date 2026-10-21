"""Đóng gói dữ liệu cho kernel Kaggle huấn luyện mô hình đọc log (bước 3, docs/huong-moi-phan-loai-sau-ci.md).

Chọn tối đa MAX_CHUNKS đoạn mỗi run từ data/run_dataset: luân phiên giữa các job fail, lấy từ CUỐI log ngược lên
(giới hạn độ dài, không lọc theo chữ ERROR), giữ thứ tự gốc. Ghi kèm cây nhãn và dòng bằng chứng để che khi huấn luyện.

    python -m project3.pipeline.log_pack            # -> data/kaggle_log_ds/ (dataset ducanhpham2k5/p3-log-data)
"""
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import duckdb
import pandas as pd

from project3.crawl.build_log_labels import GROUP
from project3.pilot.fine_labels import PARENT
from project3.pipeline.run_dataset import clean

DS = Path("data/kaggle_log_ds")
MAX_CHUNKS = 8
MAX_CHUNK_CHARS = 6000  # đủ dư cho 256 token; cắt tiếp lúc huấn luyện sau khi che
MIN_LEAF = 50           # lá ít hơn thì không học ở tầng 3 (nhãn -1), chỉ học tầng 1–2


def main() -> None:
    if DS.exists():
        shutil.rmtree(DS)
    DS.mkdir(parents=True)
    runs = duckdb.sql(f"""SELECT run_id, repository, repo_fold, split_time, workflow, failed_job_names, label_l2, label_l3,
                                 evidence, diff_ok FROM 'data/run_dataset/runs.parquet'
                          WHERE label_l2 IN ({",".join(repr(k) for k in GROUP)}) AND log_jobs > 0""").df()
    ch = duckdb.sql("""SELECT c.run_id, c.job_id, c.chunk_idx, c.failed_steps, c.has_evidence, c.text
                       FROM 'data/run_dataset/chunks.parquet' c JOIN runs USING (run_id)
                       ORDER BY c.run_id, c.job_id, c.chunk_idx""").df()
    by_run = defaultdict(lambda: defaultdict(list))
    for r in ch.itertuples(index=False):
        by_run[r.run_id][r.job_id].append(r)
    keep, steps, ev_kept = [], {}, 0
    for run_id, jobs in by_run.items():
        queues = [list(v) for _, v in sorted(jobs.items())]
        picked = []
        while len(picked) < MAX_CHUNKS and any(queues):
            for q in queues:  # luân phiên các job, mỗi lượt lấy đoạn cuối còn lại
                if q and len(picked) < MAX_CHUNKS:
                    picked.append(q.pop())
        picked.sort(key=lambda r: (r.job_id, r.chunk_idx))
        ev_kept += any(r.has_evidence for r in picked)
        steps[run_id] = " | ".join(dict.fromkeys(s for r in picked for s in r.failed_steps.split(" | ") if s))[:300]
        keep += [{"run_id": run_id, "job_id": r.job_id, "chunk_idx": r.chunk_idx, "text": r.text[-MAX_CHUNK_CHARS:]}
                 for r in picked]
    runs["failed_steps"] = runs.run_id.map(steps).fillna("")
    runs["leaf"] = [l if isinstance(l, str) else l2 for l, l2 in zip(runs.label_l3, runs.label_l2)]  # infra không lá -> 'infra'
    runs["key"] = [clean(e)[:120].strip() for e in runs.evidence.fillna("")]
    counts = runs.leaf.value_counts()
    leaves = sorted(l for l, n in counts.items() if n >= MIN_LEAF)
    tree = {"l1": ["build", "test", "env"], "l2": list(GROUP), "group": GROUP, "l3": leaves,
            "parent": {l: PARENT.get(l, l) for l in counts.index}, "min_leaf": MIN_LEAF,
            "dropped_leaves": {l: int(n) for l, n in counts.items() if n < MIN_LEAF}}
    runs.drop(columns=["evidence", "label_l3"]).to_parquet(DS / "runs.parquet", index=False)
    pd.DataFrame(keep).to_parquet(DS / "chunks.parquet", index=False, compression="zstd")
    (DS / "label_tree.json").write_text(json.dumps(tree, ensure_ascii=False, indent=1), encoding="utf-8")
    for f in ("log_hcl.py", "tfidf_feats.py"):  # tự chứa, không import module khác của project
        shutil.copy(f"src/project3/pilot/{f}", DS)
    (DS / "dataset-metadata.json").write_text(json.dumps(
        {"title": "p3-log-data", "id": "ducanhpham2k5/p3-log-data", "licenses": [{"name": "other"}]}))
    print(f"{len(runs)} run, {len(keep)} đoạn (≤{MAX_CHUNKS}/run); run giữ được đoạn chứa bằng chứng: "
          f"{ev_kept}/{len(runs)} ({ev_kept / len(runs):.1%}); lá tầng 3: {leaves}; bỏ: {tree['dropped_leaves']}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
