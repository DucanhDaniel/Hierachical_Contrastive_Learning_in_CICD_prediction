"""Gói 120 run `?` đã gán tay (data/human_labels/unknown_review) cho kernel baseline TF-IDF trên Kaggle (CPU).
Văn bản = 30.000 ký tự cuối log như model.tfidf.export_text (run `?` không có dòng bằng chứng nên bản che = bản gốc);
đặc trưng giai đoạn/diff lấy từ gói run `?` (data/kaggle_unknown_ds). Không chứa nhãn người.

    python scripts/kaggle/unknown_baselines/prepare.py     # -> data/kaggle_unknown120/ (dataset p3-unknown120)
"""
import json
import sys
from pathlib import Path

import pandas as pd

from project3.model.config import MAX_RUN_CHARS
from project3.model.data import job_texts

OUT = Path("data/kaggle_unknown120")
ITEMS = Path("data/human_labels/unknown_review/items.jsonl")
PACK = Path("data/kaggle_unknown_ds")


def main() -> None:
    ids = [json.loads(l)["run_id"] for l in ITEMS.open(encoding="utf-8")]
    runs = pd.read_parquet(PACK / "runs.parquet").drop_duplicates("run_id").set_index("run_id").loc[ids].reset_index()
    feats = pd.read_parquet(PACK / "features.parquet").drop_duplicates("run_id").set_index("run_id").loc[ids].reset_index()
    jobs = job_texts(f"run_id IN ({','.join(map(str, ids))})")
    text = ["\n".join(jobs[r])[-MAX_RUN_CHARS:] for r in runs.run_id]
    df = runs[["run_id", "repository", "repo_fold", "workflow", "failed_job_names", "failed_steps"]].assign(
        full=text, masked=text).merge(feats, on="run_id")
    df["struct_masked"] = df.struct_full
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT / "unknown120.parquet", index=False, compression="zstd")
    (OUT / "dataset-metadata.json").write_text(json.dumps(
        {"title": "p3-unknown120", "id": "ducanhpham2k5/p3-unknown120", "licenses": [{"name": "other"}]}), encoding="utf-8")
    print(f"{len(df)} run, theo fold {df.repo_fold.value_counts().sort_index().to_dict()}, "
          f"{sum(len(t) == 0 for t in text)} run không có log -> {OUT}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
