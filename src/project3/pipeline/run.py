"""Pipeline dữ liệu một lệnh (US-30): danh sách repo -> crawl -> gán nhãn -> gộp commit -> nhãn chi tiết -> diff -> dataset.

    # demo 1-2 repo trong thư mục riêng (không đụng dữ liệu chính)
    python -m project3.pipeline.run --repos dataease/dataease --days 14 --workdir data/demo
    # dữ liệu chính, bỏ crawl (đã crawl trên Kaggle), clone để ở ổ C
    python -m project3.pipeline.run --repos-file configs/repos_100.txt --skip crawl --clones C:/p3data/repos

Mọi đường dẫn tương đối nằm trong --workdir (data/crawl_pr, data/validate, data/processed, data/diffs, data/dataset).
Chạy lại cùng lệnh: repo đã crawl xong và bước có đầu ra mới hơn đầu vào được bỏ qua (AC-30.2).
Bước nặng (crawl, diff) chạy được trên Kaggle bằng cùng module; xem docs/ke-hoach-pipeline-kaggle.md.
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from project3.crawl.github import load_token

STEPS = ["crawl", "labels", "commits", "fine", "diffs", "export"]
ROOTS = {"pull_request": Path("data/crawl_pr"), "push": Path("data/validate")}
PROJECT = Path(__file__).resolve().parents[3]
RULE_FILES = [PROJECT / "configs" / "label_rules.json", PROJECT / "src" / "project3" / "crawl" / "gold_labels.py"]


def log(msg):
    print(f"[pipeline {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sh(module, *args, logfile=None):
    """Chạy một module con, in đầu ra ra màn hình và ghi vào log của bước."""
    cmd = [sys.executable, "-u", "-m", module, *map(str, args)]
    log("$ " + " ".join(cmd[2:]))
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                          errors="replace") as p, open(logfile or os.devnull, "a", encoding="utf-8") as f:
        for line in p.stdout:
            print("    " + line, end="", flush=True)
            f.write(line)
    if p.returncode:
        raise SystemExit(f"Bước lỗi ({module}, exit {p.returncode}); xem {logfile}")


def mtime(paths):
    """Mốc mới nhất trong các đường dẫn (thư mục tính cả mtime của chính nó: tăng khi thêm file log)."""
    return max((p.stat().st_mtime for p in paths if p.exists()), default=0)


def stale(outputs, inputs):
    outs = [Path(o) for o in outputs]
    return not all(o.exists() for o in outs) or min(o.stat().st_mtime for o in outs) < mtime(inputs)


def repo_dirs(root, repos):
    return [root / r.replace("/", "__") for r in repos if (root / r.replace("/", "__")).exists()]


def crawl(repos, days, steplog):
    for event, root in ROOTS.items():
        todo = []
        for r in repos:
            st = root / r.replace("/", "__") / "crawl_status.json"
            done = st.exists() and json.loads(st.read_text(encoding="utf-8")).get("status") == "completed"
            if not done:
                todo.append(r)
        log(f"crawl {event}: {len(repos) - len(todo)} repo đã xong, cần crawl {len(todo)}")
        if not todo:
            continue
        extra = ["--max-jobs-per-run", "2"] if event == "pull_request" else ["--branches", "master", "main", "trunk", "develop"]
        sh("project3.crawl.gha", "--repos", *todo, "--event", event, "--root", root, "--days", days,
           "--max-logs", "50000", *extra, logfile=steplog)


def merge_diffs(new: Path, index: Path):
    """Ghép chỉ mục diff của lượt này vào chỉ mục chung: thay các dòng của repo vừa chạy."""
    rows = list(csv.DictReader(new.open(encoding="utf-8")))
    repos = {r["repository"] for r in rows}
    old = list(csv.DictReader(index.open(encoding="utf-8"))) if index.exists() else []
    keep = [r for r in old if r.get("repository") not in repos]
    fields = list(rows[0]) if rows else (list(old[0]) if old else ["repository"])
    with index.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(keep + rows)
    new.unlink()


def main(repos, workdir, days, skip, clones, force, diff_workers):
    token = load_token(PROJECT / ".env")
    if token:  # crawler đọc token từ biến môi trường khi chạy trong workdir khác thư mục dự án
        os.environ["GITHUB_ACCESS_TOKEN"] = token
    os.environ["PYTHONIOENCODING"] = "utf-8"
    workdir.mkdir(parents=True, exist_ok=True)
    os.chdir(workdir)
    for p in ("data/processed", "data/logs"):
        Path(p).mkdir(parents=True, exist_ok=True)
    processed = Path("data/processed")
    commits, fine = processed / "commits_all.parquet", processed / "fine_labels.parquet"
    roots = [r for r in ROOTS.values()]
    t0 = time.time()
    log(f"{len(repos)} repo, workdir={workdir.resolve()}, bỏ qua: {sorted(skip) or '—'}")

    def want(step):
        return step not in skip

    def steplog(step):
        return Path(f"data/logs/pipeline_{step}.log")

    if want("crawl"):
        crawl(repos, days, steplog("crawl"))
    if want("labels"):
        for root in roots:
            if not root.exists():
                continue
            dirs = [d for d in root.iterdir() if (d / "runs.jsonl").exists()]
            inputs = RULE_FILES + [p for d in dirs for p in (d / "runs.jsonl", d / "jobs.jsonl", d / "logs")]
            if force or stale([root / "gold_labels.csv"], inputs):
                sh("project3.crawl.gold_labels", root, logfile=steplog("labels"))
            else:
                log(f"labels {root}: đầu ra mới hơn đầu vào, bỏ qua")
    if want("commits"):
        gold = [r / "gold_labels.csv" for r in roots if (r / "gold_labels.csv").exists()]
        if force or stale([commits], gold):
            sh("project3.crawl.build_log_labels", *[r for r in roots if r.exists()], "--out", commits,
               logfile=steplog("commits"))
        else:
            log("commits: bỏ qua (đã mới)")
    if want("fine"):
        if force or stale([fine], [commits]):
            sh("project3.pilot.fine_labels", "--commits", commits, "--out", fine, logfile=steplog("fine"))
        else:
            log("fine: bỏ qua (đã mới)")
    if want("diffs"):
        index = processed / "diffs_all.csv"
        if force or stale([index], [commits]):
            run_out = processed / "diffs_run.csv"
            sh("project3.pilot.fetch_diffs", "--table", commits, "--repos", *repos, "--clones", clones,
               "--diffs", "data/diffs", "--out", run_out, "--workers", diff_workers, "--cleanup",
               logfile=steplog("diffs"))
            merge_diffs(run_out, index)
        else:
            log("diffs: bỏ qua (đã mới)")
    if want("export"):
        sh("project3.pipeline.export_dataset", logfile=steplog("export"))
    log(f"xong sau {(time.time() - t0) / 60:.1f} phút. Dataset: {(workdir / 'data/dataset').resolve()}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos", nargs="*", default=[])
    ap.add_argument("--repos-file", type=Path)
    ap.add_argument("--workdir", type=Path, default=Path("."))
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--skip", nargs="*", default=[], choices=STEPS, help="bỏ qua các bước này")
    ap.add_argument("--only", nargs="*", choices=STEPS, help="chỉ chạy các bước này")
    ap.add_argument("--clones", default="data/repos", help="nơi clone tạm khi lấy diff (xoá sau mỗi repo)")
    ap.add_argument("--diff-workers", type=int, default=8)
    ap.add_argument("--force", action="store_true", help="chạy lại cả bước đã mới")
    a = ap.parse_args()
    repos = list(a.repos)
    if a.repos_file:
        repos += [l.strip() for l in a.repos_file.read_text(encoding="utf-8").splitlines()
                  if l.strip() and not l.startswith("#")]
    if not repos:
        raise SystemExit("Cần --repos hoặc --repos-file")
    skip = set(a.skip) | (set(STEPS) - set(a.only) if a.only else set())
    main(repos, a.workdir.resolve(), a.days, skip, a.clones, a.force, a.diff_workers)
