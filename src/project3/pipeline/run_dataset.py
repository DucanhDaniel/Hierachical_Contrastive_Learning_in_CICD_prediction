"""Dữ liệu mức run cho hướng phân loại lỗi sau CI (docs/huong-moi-phan-loai-sau-ci.md, 18/10/2026).

Mỗi run fail (không phải non_build) một dòng, nhãn quy tắc hiện hành 3 tầng; log từng job fail cắt thành đoạn theo cấu
trúc (step GitHub Actions, goal Maven, task Gradle, rồi cửa sổ dòng), KHÔNG lọc theo chữ ERROR: nguyên nhân nhiều khi
không nằm ở dòng có từ khoá lỗi. Đánh dấu đoạn chứa dòng bằng chứng của quy tắc để che khi huấn luyện và đo attention.

    python -m project3.pipeline.run_dataset            # -> data/run_dataset/{runs,chunks}.parquet, manifest.json

Đầu vào: data/{crawl_pr,validate}/<repo>/{runs,jobs}.jsonl, logs/<job>.txt (.tail.txt.gz nếu có, từ crawl đợt 2),
gold_labels.csv (relabel hiện hành), data/dataset/commits.parquet (diff, repo_fold, split_time).
"""
import argparse
import csv
import gzip
import hashlib
import json
import re
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from project3.crawl.build_log_labels import GROUP
from project3.crawl.gold_labels import AGG_JOB, RULE_VERSION
from project3.pilot.fine_labels import subtype

ROOTS = {"data/crawl_pr": "pull_request", "data/validate": "push"}
OUT = Path("data/run_dataset")
MAX_LINES = 40         # đoạn dài hơn thì chia cửa sổ
OVERLAP = 5
MAX_CHUNK_CHARS = 4000  # cắt dòng quá dài (stack trace một dòng, JSON) để một đoạn không chiếm hết bộ nhớ

TS = re.compile(r"^\ufeff?\d{4}-\d\d-\d\dT[\d:.]+Z ")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
WORKSPACE = re.compile(r"/home/runner/work/[^/\s]+/[^/\s]+/|D:\\a\\[^\\\s]+\\[^\\\s]+\\|/Users/runner/work/[^/\s]+/[^/\s]+/")
STEP = re.compile(r"^##\[group\]Run (.*)")
# ranh giới bên trong một step: goal Maven, task Gradle, module trong Reactor
BOUNDARY = re.compile(r"^\[INFO\] --- \S+ .*@ \S+ ---|^> Task :\S+|^\[INFO\] -+< \S+ >-+|^\[INFO\] Reactor Summary")
# dòng khuôn mẫu không mang nguyên nhân: Maven bỏ qua module sau lỗi, dòng Reactor SUCCESS/SKIPPED, dòng kẻ, dòng trống.
# Chỉ bỏ mẫu đã biết; KHÔNG lọc theo có/không có chữ ERROR. Dòng FAILURE của Reactor được giữ (cho biết module lỗi).
NOISE = re.compile(r"^\[INFO\] (?:Skipping \S+$|This project has been banned from the build|"
                   r"\S.*?\s\.{2,}\s(?:SUCCESS|SKIPPED)\b|-{20,}$|\s*$)|^\[INFO\]$")
MIN_LINES = 12  # khối nhỏ hơn thì gộp với khối kế tiếp cùng step


def clean(line: str) -> str:
    line = ANSI.sub("", TS.sub("", line.rstrip("\r")))
    return WORKSPACE.sub("<ws>/", line)


def chunk_log(text: str) -> list[dict]:
    """Đoạn theo cấu trúc: step (##[group]Run, bỏ phần echo lệnh/env), trong step tách theo goal/task, rồi cửa sổ."""
    blocks, header, cur, echo = [], "", [], False
    for raw in text.splitlines():
        line = clean(raw)
        m = STEP.match(line)
        if m:
            if cur:
                blocks.append((header, cur))
            header, cur, echo = m.group(1)[:200], [], True
            continue
        if echo:
            if line.startswith("##[endgroup]"):
                echo = False
            continue
        if BOUNDARY.match(line) and len(cur) >= MIN_LINES:
            blocks.append((header, cur))
            cur = []
        if line.strip() and not NOISE.match(line):
            cur.append(line[:MAX_CHUNK_CHARS])
    if cur:
        blocks.append((header, cur))
    chunks = []
    for header, lines in blocks:
        kind = "maven" if lines[0].startswith("[INFO] ---") else "gradle" if lines[0].startswith("> Task") else "step"
        step = MAX_LINES - OVERLAP
        for start in range(0, max(1, len(lines) - OVERLAP), step) if len(lines) > MAX_LINES else [0]:
            chunks.append({"step": header, "kind": kind if start == 0 else kind + "+win",
                           "text": "\n".join(lines[start:start + MAX_LINES])})
    return chunks


def read_log(d: Path, job_id: int) -> tuple[str | None, str]:
    """Ưu tiên đuôi log dài (crawl đợt 2), không có thì đoạn error_context đã lưu."""
    tail = d / "logs" / f"{job_id}.tail.txt.gz"
    if tail.exists():
        return gzip.decompress(tail.read_bytes()).decode("utf-8", errors="ignore"), "tail"
    txt = d / "logs" / f"{job_id}.txt"
    if txt.exists():
        return txt.read_text(encoding="utf-8", errors="ignore"), "context"
    return None, ""


def process_repo(args) -> tuple[list[dict], list[dict]]:
    root, d, labels = args
    d = Path(d)
    runs = {}
    for line in (d / "runs.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        runs[r["id"]] = r
    rows, chunks = [], []
    for line in (d / "jobs.jsonl").open(encoding="utf-8"):
        row = json.loads(line)
        lab = labels.get(row["run_id"])
        run = runs.get(row["run_id"])
        if not lab or not run:
            continue
        failed = [j for j in row["jobs"] if j["conclusion"] == "failure" and not AGG_JOB.search(j["name"])]
        names = " ".join(j["name"] for j in failed)
        gold, ev = lab["gold"], lab["evidence"]
        leaf = subtype(gold, ev, run["name"] or "", names) if gold in GROUP else None
        n_chunks, sources = 0, Counter()
        ev_key = clean(ev)[:120].strip()
        for j in failed:
            text, src = read_log(d, j["id"])
            if text is None:
                continue
            sources[src] += 1
            fsteps = [s["name"] for s in j.get("steps", []) if s["conclusion"] == "failure"]
            for k, c in enumerate(chunk_log(text)):
                chunks.append({"run_id": row["run_id"], "job_id": j["id"], "job_name": j["name"][:200],
                               "failed_steps": " | ".join(fsteps)[:300], "chunk_idx": k, "n_lines": c["text"].count("\n") + 1,
                               "kind": c["kind"], "step_header": c["step"], "text": c["text"],
                               "has_evidence": bool(ev_key) and ev_key in c["text"], "source": src})
                n_chunks += 1
        rows.append({"repository": lab["repo"], "run_id": row["run_id"], "event": ROOTS[root], "workflow": run["name"],
                     "head_sha": run["head_sha"], "head_branch": run.get("head_branch"),
                     "created_at": run.get("created_at"), "run_attempt": run.get("run_attempt"),
                     "label_l2": gold, "label_l1": GROUP.get(gold), "label_l3": leaf, "evidence": ev,
                     "failed_jobs": len(failed), "failed_job_names": names[:500],
                     "log_jobs": sum(sources.values()), "log_source": "+".join(sorted(sources)) or None,
                     "n_chunks": n_chunks})
    return rows, chunks


def main(out: Path, workers: int) -> None:
    out.mkdir(parents=True, exist_ok=True)
    tasks, seen = [], set()
    for root in ROOTS:
        by_repo = {}
        for r in csv.DictReader(open(Path(root) / "gold_labels.csv", encoding="utf-8-sig")):
            key = (r["repo"], int(r["run_id"]))
            if r["non_build"] == "True" or key in seen:  # khử trùng (repo, run_id) giữa hai thư mục, giữ bản đầu
                continue
            seen.add(key)
            by_repo.setdefault(r["repo"], {})[int(r["run_id"])] = r
        for repo, labels in by_repo.items():
            d = Path(root) / repo.replace("/", "__")
            if (d / "jobs.jsonl").exists():
                tasks.append((root, str(d), labels))
    print(f"{len(tasks)} repo-event, {len(seen)} run fail (đã bỏ non_build)", flush=True)
    rows, n_chunks = [], 0
    chunk_path = out / "chunks.parquet"
    writer = None
    import pyarrow as pa
    import pyarrow.parquet as pq
    with ProcessPoolExecutor(workers) as ex:
        for k, (r, c) in enumerate(ex.map(process_repo, tasks), 1):
            rows += r
            if c:
                t = pa.Table.from_pylist(c)
                writer = writer or pq.ParquetWriter(chunk_path, t.schema, compression="zstd")
                writer.write_table(t.cast(writer.schema))
                n_chunks += len(c)
            if k % 20 == 0 or k == len(tasks):
                print(f"  {k}/{len(tasks)} repo-event, {len(rows)} run, {n_chunks} đoạn", flush=True)
    writer and writer.close()
    runs = pd.DataFrame(rows)
    # nối commit: diff, fold theo repo, chia theo thời gian (một commit có thể có nhiều run)
    con = duckdb.connect()
    con.register("runs", runs)
    runs = con.sql("""
        SELECT r.*, c.diff_path, coalesce(c.diff_ok, false) diff_ok, c.repo_fold, c.split_time, c.label_l2 commit_label_l2,
               c.first_failure
        FROM runs r LEFT JOIN (SELECT * FROM 'data/dataset/commits.parquet'
                               QUALIFY row_number() OVER (PARTITION BY repository, event, head_sha ORDER BY seq_idx) = 1) c
          ON c.repository = r.repository AND c.event = r.event AND c.head_sha = r.head_sha""").df()
    runs.to_parquet(out / "runs.parquet", index=False, compression="zstd")
    lab = runs[runs.label_l2.isin(list(GROUP))]
    stats = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rule_version": RULE_VERSION,
        "runs": len(runs), "labeled_runs": len(lab), "unknown_runs": int((runs.label_l2 == "?").sum()),
        "no_log_runs": int((runs.log_jobs == 0).sum()), "chunks": n_chunks,
        "label_l2": lab.label_l2.value_counts().to_dict(), "label_l3": lab.label_l3.value_counts(dropna=False).to_dict(),
        "with_diff": int(runs.diff_ok.sum()), "without_commit_match": int(runs.repo_fold.isna().sum()),
        "log_source": runs.log_source.value_counts(dropna=False).to_dict(),
        "gold_labels_sha256": {r: hashlib.sha256((Path(r) / "gold_labels.csv").read_bytes()).hexdigest() for r in ROOTS},
        "chunking": {"max_lines": MAX_LINES, "overlap": OVERLAP, "max_chars_per_line": MAX_CHUNK_CHARS,
                     "boundaries": "##[group]Run (step), Maven '--- goal @ module ---', Gradle '> Task', Reactor"},
    }
    (out / "manifest.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in stats.items() if k not in ("gold_labels_sha256", "chunking")},
                     ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    main(a.out, a.workers)
