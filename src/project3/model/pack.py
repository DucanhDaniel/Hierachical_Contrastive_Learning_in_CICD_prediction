"""Đóng gói dữ liệu + mã cho mô hình đọc log (dataset Kaggle ducanhpham2k5/p3-log-data; dùng được cho Colab).

Dữ liệu (27/10/2026, model.inputs): chọn tối đa MAX_CHUNKS đoạn mỗi run theo dấu hiệu fail (chấm trên log đã che, không
dùng nhãn) -> chunks.parquet; bản cũ (luân phiên job, lấy từ CUỐI log) -> chunks_tail.parquet cho ablation. features.parquet:
đặc trưng giai đoạn/công cụ fail (bản nguyên vẹn và bản che) + tóm tắt diff; coverage.json: tỉ lệ run giữ được bằng chứng.
Ghi kèm cây nhãn và dòng bằng chứng để che khi huấn luyện.
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


def tail_select(n_by_job: list, max_chunks: int) -> list:
    """Cách chọn cũ (trước 27/10, ablation A2): luân phiên các job, mỗi lượt lấy đoạn cuối còn lại."""
    queues = [list(range(n)) for n in n_by_job]
    picked = []
    while len(picked) < max_chunks and any(queues):
        for j, q in enumerate(queues):
            if q and len(picked) < max_chunks:
                picked.append((j, q.pop()))
    return sorted(picked)


def _diff_row(args):
    from .inputs import diff_features
    return diff_features(*args)


def build_data(ds: Path) -> None:
    import duckdb
    from concurrent.futures import ProcessPoolExecutor
    from project3.crawl.build_log_labels import GROUP as RULE_GROUP
    from project3.pipeline.run_dataset import clean
    from .inputs import DIFF_NAMES, STRUCT_NAMES, chunk_score, focus_window, select_chunks, struct_features
    from .labels import GROUP, PARENT
    from .text import clip_chunk, mask_text
    runs = duckdb.sql(f"""SELECT run_id, repository, repo_fold, split_time, workflow, failed_job_names, label_l2, label_l3,
                                 evidence, diff_ok, diff_path, event, failed_jobs FROM '{RUN_DATASET / "runs.parquet"}'
                          WHERE label_l2 IN ({",".join(repr(k) for k in RULE_GROUP)}) AND log_jobs > 0""").df()
    runs = runs.drop_duplicates("run_id").reset_index(drop=True)
    runs["key"] = [clean(e)[:120].strip() for e in runs.evidence.fillna("")]
    key = dict(zip(runs.run_id, runs.key))
    ch = duckdb.sql(f"""SELECT c.run_id, c.job_id, c.chunk_idx, c.failed_steps, c.has_evidence, c.kind, c.text
                        FROM '{RUN_DATASET / "chunks.parquet"}' c JOIN runs USING (run_id)
                        ORDER BY c.run_id, c.job_id, c.chunk_idx""").df()
    by_run = defaultdict(lambda: defaultdict(list))
    for r in ch.itertuples(index=False):
        by_run[r.run_id][r.job_id].append(r)
    del ch
    keep = {"error": [], "tail": []}
    steps, sf_full, sf_masked = {}, {}, {}
    cover = {m: [0, 0] for m in keep}  # [run có đoạn chứa bằng chứng, run có bằng chứng trong cửa sổ mô hình đọc]
    nfj = dict(zip(runs.run_id, runs.failed_jobs.fillna(1)))
    for run_id, jobs in by_run.items():
        jobs = [v for _, v in sorted(jobs.items())]
        k = key.get(run_id, "")
        masked = [[mask_text(c.text, k) for c in job] for job in jobs]
        scores = [[chunk_score(t, ci == len(job) - 1) for ci, t in enumerate(job)] for job in masked]
        names = list(dict.fromkeys(s for job in jobs for c in job for s in c.failed_steps.split(" | ") if s))
        kinds = list({c.kind for job in jobs for c in job})
        sf_full[run_id] = struct_features([c.text for job in jobs for c in job], names, kinds, nfj[run_id])
        sf_masked[run_id] = struct_features([t for job in masked for t in job], names, kinds, nfj[run_id])
        steps[run_id] = " | ".join(names)[:300]
        for mode, picked, clip in (("error", select_chunks(scores, MAX_CHUNKS), focus_window),
                                   ("tail", tail_select([len(j) for j in jobs], MAX_CHUNKS), clip_chunk)):
            rows = [jobs[j][c] for j, c in picked]
            cover[mode][0] += any(r.has_evidence for r in rows)
            cover[mode][1] += bool(k) and any(k in clip(r.text) for r in rows)
            keep[mode] += [{"run_id": run_id, "job_id": r.job_id, "chunk_idx": r.chunk_idx,
                            "text": r.text[-MAX_CHUNK_CHARS:]} for r in rows]
    runs["failed_steps"] = runs.run_id.map(steps).fillna("")
    runs["leaf"] = [leaf_of(a, b) for a, b in zip(runs.label_l3, runs.label_l2)]
    with ProcessPoolExecutor(8) as ex:
        diff = list(ex.map(_diff_row, [(p if ok else None, e) for p, ok, e in zip(runs.diff_path, runs.diff_ok, runs.event)],
                           chunksize=200))
    pd.DataFrame({"run_id": runs.run_id, "struct_full": [sf_full.get(r, [0.0] * len(STRUCT_NAMES)) for r in runs.run_id],
                  "struct_masked": [sf_masked.get(r, [0.0] * len(STRUCT_NAMES)) for r in runs.run_id],
                  "diff": diff}).to_parquet(ds / "features.parquet", index=False)
    (ds / "features.json").write_text(json.dumps({"struct": STRUCT_NAMES, "diff": DIFF_NAMES}), encoding="utf-8")
    tree = LabelTree.build(GROUP, PARENT, runs.leaf.value_counts().to_dict(), MIN_LEAF)
    runs.drop(columns=["evidence", "label_l3", "diff_path"]).to_parquet(ds / "runs.parquet", index=False)
    pd.DataFrame(keep["error"]).to_parquet(ds / "chunks.parquet", index=False, compression="zstd")
    pd.DataFrame(keep["tail"]).to_parquet(ds / "chunks_tail.parquet", index=False, compression="zstd")
    (ds / "label_tree.json").write_text(json.dumps(tree.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    n, nk = len(runs), int((runs.key != "").sum())
    cov = {m: {"đoạn có bằng chứng": round(a / n, 4), "bằng chứng trong cửa sổ đọc": round(b / max(nk, 1), 4)}
           for m, (a, b) in cover.items()}
    (ds / "coverage.json").write_text(json.dumps(cov, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{n} run; ≤{MAX_CHUNKS} đoạn/run; lá tầng 3: {tree.l3}; bỏ: {tree.extra['dropped_leaves']}")
    print("tỉ lệ run giữ được bằng chứng:", json.dumps(cov, ensure_ascii=False))


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
