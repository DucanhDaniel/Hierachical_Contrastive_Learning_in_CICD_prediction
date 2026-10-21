"""Lấy diff trên Kaggle: chia commit còn thiếu diff thành nhiều shard, mỗi shard một kernel chạy song song.

    python -m project3.pipeline.kaggle_diff prepare --shards 3   # data/kaggle_diff_ds (dataset) + data/kaggle_diff_kernels/shard*/
    python -m project3.pipeline.kaggle_diff merge data/kaggle_diff_out/<thư mục output>   # giải nén vào data/diffs, gộp chỉ mục

Commit cần diff = pass hoặc fail do code (như export_dataset.needs_diff) mà chưa có dòng ok trong data/processed/diffs_all.csv;
`--all-fail` (18/10/2026, hướng phân loại sau CI): thêm mọi commit fail, kể cả `?` và env (diff là nhánh thứ hai của mô hình).
Không cần token: git clone repo công khai không tính vào giới hạn REST API.
"""
import argparse
import csv
import json
import sys
import tarfile
from pathlib import Path

import duckdb

DS, KERNELS = Path("data/kaggle_diff_ds"), Path("data/kaggle_diff_kernels")
INDEX = Path("data/processed/diffs_all.csv")
FIELDS = ["repository", "head_sha", "kind", "path", "ok", "err"]
OWNER = "ducanhpham2k5"


def read_index() -> dict:
    if not INDEX.exists():
        return {}
    return {(r["repository"], r["head_sha"], r["kind"]): r for r in csv.DictReader(INDEX.open(encoding="utf-8"))}


def prepare(shards: int, budget_min: int, commits: Path, all_fail: bool = False) -> None:
    ok = {k for k, r in read_index().items() if r["ok"] == "True"}
    rows = duckdb.sql(f"""SELECT DISTINCT repository, event, head_sha, outcome FROM '{commits.as_posix()}'
        WHERE outcome = 'pass' OR {"outcome = 'fail'" if all_fail else "cause = 'code'"}""").fetchall()
    todo = [r for r in rows if (r[0], r[2], "pr" if r[1] == "pull_request" else "commit") not in ok]
    per = {}
    for r in todo:
        per.setdefault(r[0], []).append(r)
    load, shard_of = [0] * shards, {}
    for repo in sorted(per, key=lambda x: -len(per[x])):  # chia tham lam theo số commit
        k = load.index(min(load))
        shard_of[repo], load[k] = k, load[k] + len(per[repo])
    DS.mkdir(parents=True, exist_ok=True)
    with (DS / "todo.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["repository", "event", "head_sha", "outcome", "shard"])
        w.writerows([*r, shard_of[r[0]]] for r in todo)
    (DS / "dataset-metadata.json").write_text(json.dumps(
        {"title": "p3-diff-input", "id": f"{OWNER}/p3-diff-input", "licenses": [{"name": "CC0-1.0"}]}))
    src = Path("scripts/kaggle/diff/run.py").read_text(encoding="utf-8")
    for k in range(shards):
        d = KERNELS / f"shard{k}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "run.py").write_text(src.replace("SHARD = 0 ", f"SHARD = {k} ").replace(
            "BUDGET_MIN = 660", f"BUDGET_MIN = {budget_min}"), encoding="utf-8")
        (d / "kernel-metadata.json").write_text(json.dumps({
            "id": f"{OWNER}/p3-diff-{k}", "title": f"p3-diff-{k}", "code_file": "run.py", "language": "python",
            "kernel_type": "script", "is_private": True, "enable_gpu": False, "enable_internet": True,
            "dataset_sources": [f"{OWNER}/p3-diff-input"], "competition_sources": [], "kernel_sources": []}, indent=1))
    print(f"{len(todo)} commit thiếu diff, {len(per)} repo; shard: {load}")


def merge(out_dir: Path) -> None:
    index = read_index()
    n_new = 0
    for tar in sorted(out_dir.rglob("diffs_*.tar")):
        with tarfile.open(tar) as t:
            t.extractall("data", filter="data")  # diffs/<repo>/... -> data/diffs/<repo>/...
        print(f"giải nén {tar}")
    for f in sorted(out_dir.rglob("index_*.csv")):
        for r in csv.DictReader(f.open(encoding="utf-8")):
            key = (r["repository"], r["head_sha"], r["kind"])
            if index.get(key, {}).get("ok") != "True":  # không ghi đè diff đã có bằng lỗi
                index[key] = {**r, "ok": str(r["ok"] == "True")}
                n_new += r["ok"] == "True"
    with INDEX.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(index.values())
    for s in sorted(out_dir.rglob("summary_*.json")):
        x = json.loads(s.read_text(encoding="utf-8"))
        print(f"shard {x['shard']}: ok {x['ok']}/{x['n']}, xong {len(x['done'])} repo, dở {x['partial']}, "
              f"chưa làm {len(x['not_started'])}, lỗi {list(x['errors'])}")
    print(f"+{n_new} diff mới; chỉ mục {INDEX}: {sum(r['ok'] == 'True' for r in index.values())} ok")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--shards", type=int, default=3)
    p.add_argument("--budget-min", type=int, default=660)
    p.add_argument("--commits", type=Path, default=Path("data/dataset/commits.parquet"))
    p.add_argument("--all-fail", action="store_true", help="lấy diff cho mọi commit fail (kể cả ? và env)")
    m = sub.add_parser("merge")
    m.add_argument("out_dir", type=Path)
    a = ap.parse_args()
    prepare(a.shards, a.budget_min, a.commits, a.all_fail) if a.cmd == "prepare" else merge(a.out_dir)
