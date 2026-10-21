"""Đọc dữ liệu, chia fold theo repo, chọn run che bằng chứng."""
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from .config import N_FOLDS, RUN_DATASET, SEED
from .labels import LabelTree, leaf_of


def load_pack(data: Path):
    """Gói dữ liệu của model.pack -> (runs, chunks, tree). chunks[run_id] = [[đoạn của job 1], [đoạn của job 2], ...],
    job theo job_id tăng dần, đoạn theo chunk_idx."""
    data = Path(data)
    runs = pd.read_parquet(data / "runs.parquet")
    ch = pd.read_parquet(data / "chunks.parquet").sort_values(["run_id", "job_id", "chunk_idx"])
    chunks = {}
    for (rid, jid), g in ch.groupby(["run_id", "job_id"], sort=False):
        chunks.setdefault(rid, []).append(g.text.tolist())
    return runs, chunks, LabelTree.load(data / "label_tree.json")


def val_fold(k: int) -> int:
    return (k + 1) % N_FOLDS


def train_folds(k: int) -> list:
    """Fold train khi test = k: bỏ k và fold val k+1."""
    return [f for f in range(N_FOLDS) if f not in (k, val_fold(k))]


def fold_split(folds: np.ndarray, k: int):
    """Chỉ số (train, val, test) theo repo_fold: test = k, val = k+1, train = 3 fold còn lại."""
    te = np.where(folds == k)[0]
    va = np.where(folds == val_fold(k))[0]
    tr = np.where((folds != k) & (folds != val_fold(k)))[0]
    return tr, va, te


def mix50(run_ids, seed: int = SEED) -> dict:
    """run_id -> True nếu che bằng chứng khi train (50% run, theo thứ tự run_ids)."""
    rng = random.Random(seed)
    return {r: rng.random() < 0.5 for r in run_ids}


def job_texts(where: str, ds: Path = RUN_DATASET) -> dict:
    """run_id -> [log của từng job] (ghép các đoạn theo chunk_idx, job theo job_id) từ run_dataset.
    `where` là điều kiện SQL trên run_id; có thể tham chiếu DataFrame cục bộ của người gọi (duckdb)."""
    import duckdb
    ch = duckdb.sql(f"""SELECT run_id, job_id, string_agg(text, chr(10) ORDER BY chunk_idx) txt
                        FROM '{Path(ds) / "chunks.parquet"}' WHERE {where}
                        GROUP BY run_id, job_id ORDER BY run_id, job_id""").df()
    jobs = defaultdict(list)
    for r in ch.itertuples():
        jobs[r.run_id].append(r.txt)
    return jobs


def load_run_logs(ds: Path = RUN_DATASET):
    """Run fail có nhãn quy tắc + log đầy đủ từng job, từ run_dataset (chỉ chạy ở máy local)."""
    import duckdb
    from project3.crawl.build_log_labels import GROUP
    from project3.pipeline.run_dataset import clean
    runs = duckdb.sql(f"""SELECT run_id, repository, workflow, failed_job_names, label_l2, label_l3, evidence,
                                 repo_fold, split_time FROM '{Path(ds) / "runs.parquet"}'
                          WHERE label_l2 IN ({",".join(repr(k) for k in GROUP)}) AND log_jobs > 0""").df()
    jobs = job_texts("run_id IN (SELECT run_id FROM runs)", ds)
    runs["leaf"] = [leaf_of(a, b) for a, b in zip(runs.label_l3, runs.label_l2)]
    runs["key"] = [clean(e)[:120].strip() for e in runs.evidence.fillna("")]
    return runs, jobs


def read_fold_outputs(d: Path, pattern: str) -> pd.DataFrame:
    """Ghép các file output theo fold (results_fold{k}...) của một lượt chạy, thêm cột fold."""
    return pd.concat([pd.read_parquet(f).assign(fold=int(f.name.split("fold")[1][0])) for f in sorted(Path(d).glob(pattern))])
