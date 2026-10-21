"""Đóng gói dữ liệu + mã cho mô hình đọc log (dataset Kaggle ducanhpham2k5/p3-log-data; dùng được cho Colab).

Dữ liệu: chọn tối đa MAX_CHUNKS đoạn mỗi run từ data/run_dataset, luân phiên giữa các job fail, lấy từ CUỐI log ngược lên
(giới hạn độ dài, không lọc theo chữ ERROR), giữ thứ tự gốc. Ghi kèm cây nhãn và dòng bằng chứng để che khi huấn luyện.
Mã: cả package project3.model nén thành project3_code.pyz (zip import được); trên Kaggle/Colab đặt PYTHONPATH tới file
này rồi chạy `python -m project3.model.train ...`.

    python -m project3.model.pack              # -> data/kaggle_log_ds/ (xoá và tạo lại; sau đó chạy model.tfidf --export-text)
    python -m project3.model.pack --code-only  # chỉ cập nhật project3_code.pyz, giữ dữ liệu
"""
import argparse
import json
import shutil
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

import pandas as pd

from .config import PACK, RUN_DATASET
from .labels import LabelTree, leaf_of

MAX_CHUNKS = 8
MAX_CHUNK_CHARS = 6000  # đủ dư cho 256 token; cắt tiếp lúc huấn luyện sau khi che
MIN_LEAF = 50           # lá ít hơn thì không học ở tầng 3 (nhãn -1), chỉ học tầng 1–2
CODE = "project3_code.pyz"


def bundle_code(dst: Path) -> Path:
    """Nén project3/__init__.py (rỗng) + project3/model/**/*.py thành dst/project3_code.pyz."""
    src = Path(__file__).resolve().parent
    out = Path(dst) / CODE
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("project3/__init__.py", "")
        for f in sorted(src.rglob("*.py")):
            z.write(f, "project3/model/" + f.relative_to(src).as_posix())
    return out


def build_data(ds: Path) -> None:
    import duckdb
    from project3.crawl.build_log_labels import GROUP
    from project3.crawl.fine_labels import PARENT
    from project3.pipeline.run_dataset import clean
    runs = duckdb.sql(f"""SELECT run_id, repository, repo_fold, split_time, workflow, failed_job_names, label_l2, label_l3,
                                 evidence, diff_ok FROM '{RUN_DATASET / "runs.parquet"}'
                          WHERE label_l2 IN ({",".join(repr(k) for k in GROUP)}) AND log_jobs > 0""").df()
    ch = duckdb.sql(f"""SELECT c.run_id, c.job_id, c.chunk_idx, c.failed_steps, c.has_evidence, c.text
                        FROM '{RUN_DATASET / "chunks.parquet"}' c JOIN runs USING (run_id)
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
    runs["leaf"] = [leaf_of(a, b) for a, b in zip(runs.label_l3, runs.label_l2)]
    runs["key"] = [clean(e)[:120].strip() for e in runs.evidence.fillna("")]
    tree = LabelTree.build(GROUP, PARENT, runs.leaf.value_counts().to_dict(), MIN_LEAF)
    runs.drop(columns=["evidence", "label_l3"]).to_parquet(ds / "runs.parquet", index=False)
    pd.DataFrame(keep).to_parquet(ds / "chunks.parquet", index=False, compression="zstd")
    (ds / "label_tree.json").write_text(json.dumps(tree.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(runs)} run, {len(keep)} đoạn (≤{MAX_CHUNKS}/run); run giữ được đoạn chứa bằng chứng: "
          f"{ev_kept}/{len(runs)} ({ev_kept / len(runs):.1%}); lá tầng 3: {tree.l3}; bỏ: {tree.extra['dropped_leaves']}")


def main(ds: Path = PACK, code_only: bool = False) -> None:
    if not code_only:
        if ds.exists():
            shutil.rmtree(ds)
        ds.mkdir(parents=True)
        build_data(ds)
        (ds / "dataset-metadata.json").write_text(json.dumps(
            {"title": "p3-log-data", "id": "ducanhpham2k5/p3-log-data", "licenses": [{"name": "other"}]}))
    for old in ("log_hcl.py", "tfidf_feats.py"):  # mã cũ (trước 21/10) chép từng file
        (ds / old).unlink(missing_ok=True)
    print(f"mã -> {bundle_code(ds)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=PACK)
    ap.add_argument("--code-only", action="store_true")
    a = ap.parse_args()
    main(a.out, a.code_only)
