"""Pipeline dữ liệu một lệnh (US-30): danh sách repo -> crawl -> gán nhãn -> gộp commit -> nhãn chi tiết -> diff -> dataset.

    # demo 1-2 repo trong thư mục riêng (không đụng dữ liệu chính)
    python -m project3.pipeline.run --repos dataease/dataease --days 14 --workdir data/demo
    # dữ liệu chính, bỏ crawl (đã crawl trên Kaggle), clone để ở ổ C
    python -m project3.pipeline.run --repos-file configs/repos_100.txt --skip crawl --clones C:/p3data/repos
    # cập nhật định kỳ: crawl phần mới của mọi repo đang có, gán nhãn lại bằng bộ quy tắc hiện hành, xuất dataset mới
    python -m project3.pipeline.run --update --clones C:/p3data/repos

--update: dừng lúc nào cũng được (Ctrl+C), chạy lại cùng lệnh thì làm tiếp, không tải lại cái đã có:
  - một "lượt cập nhật" ghi ở data/processed/update_round.json; repo đã crawl xong trong lượt này được bỏ qua;
  - crawl cộng dồn: mỗi workflow liệt kê run từ mốc đã liệt kê (crawl_state.json) lùi 2 ngày; run/job/log đã có
    không tải lại (loại trùng theo id / file);
  - diff: commit đã có trong diffs_all.csv không lấy lại, repo không có commit mới không clone;
  - dataset cũ (data/dataset, data/run_dataset) được chuyển vào data/snapshots/ trước khi xuất bản mới.
Repo của các đợt crawl nhắm mục tiêu (scope targeted-r3, targeted-android) không thuộc danh sách cập nhật.

Mọi đường dẫn tương đối nằm trong --workdir (data/crawl_pr, data/validate, data/processed, data/diffs, data/dataset).
Chạy lại cùng lệnh: repo đã crawl xong và bước có đầu ra mới hơn đầu vào được bỏ qua (AC-30.2).
Bước nặng (crawl, diff) chạy được trên Kaggle bằng cùng module; xem docs/ke-hoach-pipeline-kaggle.md.
"""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from project3.crawl.github import load_token

STEPS = ["crawl", "labels", "commits", "fine", "diffs", "export", "runs"]
ROOTS = {"pull_request": Path("data/crawl_pr"), "push": Path("data/validate")}
PROJECT = Path(__file__).resolve().parents[3]
RULE_FILES = [PROJECT / "configs" / "label_rules.json", PROJECT / "src" / "project3" / "crawl" / "gold_labels.py"]
ROUND = Path("data/processed/update_round.json")
EXCLUDED_SCOPES = {"targeted-r3", "targeted-android"}


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


def status(d: Path) -> dict:
    st = d / "crawl_status.json"
    return json.loads(st.read_text(encoding="utf-8")) if st.exists() else {}


def existing_repos():
    """Repo đang có dữ liệu (theo thư mục crawl), trừ các đợt crawl nhắm mục tiêu riêng."""
    repos = set()
    for root in ROOTS.values():
        for d in root.iterdir() if root.exists() else []:
            if (d / "runs.jsonl").exists() and status(d).get("scope") not in EXCLUDED_SCOPES:
                repos.add(d.name.replace("__", "/", 1))  # tên user GitHub không có "_" nên tách ở "__" đầu tiên
    return sorted(repos)


def start_round():
    """Lượt cập nhật đang dở thì làm tiếp; đã xong (hoặc chưa có) thì mở lượt mới."""
    r = json.loads(ROUND.read_text(encoding="utf-8")) if ROUND.exists() else {}
    if r and not r.get("finished"):
        log(f"tiếp tục lượt cập nhật bắt đầu {r['started']}")
        return r
    r = {"started": datetime.now(timezone.utc).isoformat(), "finished": None}
    ROUND.write_text(json.dumps(r, indent=1), encoding="utf-8")
    log(f"mở lượt cập nhật mới {r['started']}")
    return r


def count_runs(repos):
    paths = [d / "runs.jsonl" for root in ROOTS.values() for d in repo_dirs(root, repos)]
    return sum(sum(1 for _ in p.open(encoding="utf-8")) for p in paths if p.exists())


def crawl(repos, days, steplog, update_since=None):
    """update_since: chế độ cập nhật; repo coi là xong nếu crawl completed sau mốc này (đầu lượt cập nhật)."""
    if update_since:  # dòng JSONL cuối bị cắt khi dừng cứng -> sửa trước khi đọc lại
        sh("project3.crawl.checkpoint", *[r for r in ROOTS.values() if r.exists()], "--repair", logfile=steplog)
    for event, root in ROOTS.items():
        todo = []
        for r in repos:
            d = root / r.replace("/", "__")
            st = status(d)
            if update_since:
                if not (d / "runs.jsonl").exists():
                    continue  # chỉ cập nhật event mà repo đã có dữ liệu
                done = st.get("status") == "completed" and st.get("updated_at", "") >= update_since
            else:
                done = st.get("status") == "completed"
            if not done:
                todo.append(r)
        log(f"crawl {event}: {len(repos) - len(todo)} repo đã xong/bỏ qua, cần crawl {len(todo)}")
        if not todo:
            continue
        extra = ["--max-jobs-per-run", "2"] if event == "pull_request" else ["--branches", "master", "main", "trunk", "develop"]
        if update_since:
            extra.append("--incremental")
        sh("project3.crawl.gha", "--repos", *todo, "--event", event, "--root", root, "--days", days,
           "--max-logs", "50000", *extra, logfile=steplog)


def snapshot(path: Path, before: str):
    """Chuyển bản xuất cũ (tạo trước lượt cập nhật) vào data/snapshots/ để thí nghiệm cũ vẫn tái lập được."""
    m = path / "manifest.json"
    if not m.exists():
        return
    created = datetime.fromisoformat(json.loads(m.read_text(encoding="utf-8"))["created_utc"])
    if created >= datetime.fromisoformat(before):
        return
    dest = Path("data/snapshots") / f"{path.name}_{created:%Y%m%dT%H%M}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(path, dest)
    log(f"bản cũ {path} -> {dest}")


def merge_diffs(new: Path, index: Path):
    """Ghép chỉ mục diff của lượt này vào chỉ mục chung: dòng mới thay dòng cũ cùng (repo, sha, kind)."""
    def key(r):
        return r["repository"], r["head_sha"], r["kind"]
    with new.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    old = []
    if index.exists():
        with index.open(encoding="utf-8") as f:
            old = list(csv.DictReader(f))
    fresh = {key(r) for r in rows}
    partial = index.with_suffix(".csv.part")
    with partial.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["repository", "head_sha", "kind", "path", "ok", "err"], extrasaction="ignore")
        w.writeheader()
        w.writerows([r for r in old if key(r) not in fresh] + rows)
    partial.replace(index)
    new.unlink()
    log(f"diffs: +{len(rows)} dòng vào {index}")


def main(repos, workdir, days, skip, clones, force, diff_workers, update=False):
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
    rnd = start_round() if update else None
    if update and not repos:
        repos = existing_repos()
    if not repos:
        raise SystemExit("Cần --repos, --repos-file hoặc --update")
    log(f"{len(repos)} repo, workdir={workdir.resolve()}, bỏ qua: {sorted(skip) or '—'}")

    def want(step):
        return step not in skip

    def steplog(step):
        return Path(f"data/logs/pipeline_{step}.log")

    if want("crawl"):
        before = count_runs(repos)
        crawl(repos, days, steplog("crawl"), rnd and rnd["started"])
        log(f"crawl: {before} -> {count_runs(repos)} run")
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
            sh("project3.crawl.fine_labels", "--commits", commits, "--out", fine, logfile=steplog("fine"))
        else:
            log("fine: bỏ qua (đã mới)")
    if want("diffs"):
        index = processed / "diffs_all.csv"
        run_out = processed / "diffs_run.csv"
        todo = force or run_out.exists() or stale([index], [commits])
        if run_out.exists():  # lần trước bị dừng giữa bước diff: giữ phần đã làm rồi làm tiếp
            merge_diffs(run_out, index)
        if todo:
            sh("project3.pipeline.fetch_diffs", "--table", commits, "--repos", *repos, "--clones", clones,
               "--diffs", "data/diffs", "--out", run_out, "--workers", diff_workers, "--cleanup", "--all-fail",
               "--skip-index", index, logfile=steplog("diffs"))
            if run_out.exists():
                merge_diffs(run_out, index)
            else:
                index.touch()  # không có commit mới cần diff: đánh dấu bước đã chạy
        else:
            log("diffs: bỏ qua (đã mới)")
    dataset, run_ds = Path("data/dataset"), Path("data/run_dataset")
    if want("export"):
        if force or stale([dataset / "manifest.json"], [commits, fine, processed / "diffs_all.csv"]):
            if update:
                snapshot(dataset, rnd["started"])
            sh("project3.pipeline.export_dataset", "--out", dataset, logfile=steplog("export"))
        else:
            log("export: bỏ qua (đã mới)")
    if want("runs"):
        gold = [r / "gold_labels.csv" for r in roots if (r / "gold_labels.csv").exists()]
        if force or stale([run_ds / "manifest.json"], [dataset / "commits.parquet", *gold]):
            if update:
                snapshot(run_ds, rnd["started"])
            sh("project3.pipeline.run_dataset", "--out", run_ds, "--dataset", dataset, logfile=steplog("runs"))
        else:
            log("runs: bỏ qua (đã mới)")
    if update and not skip:
        rnd["finished"] = datetime.now(timezone.utc).isoformat()
        ROUND.write_text(json.dumps(rnd, indent=1), encoding="utf-8")
    log(f"xong sau {(time.time() - t0) / 60:.1f} phút. Dataset: {dataset.resolve()}, {run_ds.resolve()}")


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
    ap.add_argument("--update", action="store_true",
                    help="cập nhật định kỳ mọi repo đang có: crawl cộng dồn, gán nhãn lại, xuất dataset mới")
    a = ap.parse_args()
    repos = list(a.repos)
    if a.repos_file:
        repos += [l.strip() for l in a.repos_file.read_text(encoding="utf-8").splitlines()
                  if l.strip() and not l.startswith("#")]
    skip = set(a.skip) | (set(STEPS) - set(a.only) if a.only else set())
    main(repos, a.workdir.resolve(), a.days, skip, a.clones, a.force, a.diff_workers, a.update)
