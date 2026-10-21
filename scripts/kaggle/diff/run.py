"""Kernel Kaggle lấy diff cho một shard (danh sách commit ở /kaggle/input/p3-diff-input/todo.csv).

Clone đầy đủ (không --filter) vì trên Kaggle mạng/đĩa dư, tránh mỗi lần diff lại tải blob lẻ.
Diff giống pilot/fetch_diffs.py: push `sha^..sha`, PR `merge-base(origin/HEAD, sha)..sha`, cắt 2 MB, nén gzip.
Repo có nhiều commit fail làm trước; hết ngân sách thời gian thì dừng, phần chưa làm để phiên sau.
Đầu ra: /kaggle/working/diffs_<shard>.tar (diffs/<repo__>/<sha>.<kind>.diff.gz) + index_<shard>.csv + summary_<shard>.json
"""
import csv
import gzip
import json
import shutil
import subprocess
import sys
import tarfile
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SHARD = 0  # prepare ghi số shard vào đây
BUDGET_MIN = 660
MAX_BYTES = 2_000_000
WORKERS = 8
T0 = time.time()
INP = next(Path("/kaggle/input").rglob("todo.csv"))
CLONES, OUT, WORK = Path("/tmp/clones"), Path("/tmp/out"), Path("/kaggle/working")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')} +{(time.time() - T0) / 60:.0f}m] {msg}", flush=True)


def git(d, *args, timeout=600):
    return subprocess.run(["git", "-C", str(d), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def left_min():
    return BUDGET_MIN - (time.time() - T0) / 60


def prepare(repo, d):
    # clone đầy đủ nhanh nhất cho diff; lỗi (repo quá lớn, mạng) thì thử partial clone như pilot/fetch_diffs.py
    for extra in ([], ["--filter=blob:none"]):
        shutil.rmtree(d, ignore_errors=True)
        try:
            p = subprocess.run(["git", "clone", "--quiet", "--no-checkout", *extra, f"https://github.com/{repo}.git",
                                str(d)], timeout=3600, capture_output=True, text=True)
        except subprocess.TimeoutExpired:
            log(f"  clone {extra or 'đầy đủ'} quá 60 phút")
            continue
        if p.returncode == 0:
            return
        log(f"  clone {extra or 'đầy đủ'} lỗi: {p.stderr.strip()[-300:]}")
    raise RuntimeError("clone thất bại cả hai cách")


def fetch_missing(d, shas):
    p = subprocess.run(["git", "-C", str(d), "cat-file", "--batch-check"],
                       input="".join(f"{s}^{{commit}}\n" for s in shas), capture_output=True, text=True)
    missing = [s for s, line in zip(shas, p.stdout.splitlines()) if line.endswith("missing")]
    log(f"  {len(missing)}/{len(shas)} commit cần fetch thêm")
    for i in range(0, len(missing), 100):
        part = missing[i:i + 100]
        if git(d, "fetch", "--quiet", "--no-tags", "--no-write-fetch-head", "origin", *part, timeout=3600).returncode:
            for s in part:  # một sha hỏng (force-push, fork đã xoá) làm hỏng cả lô
                try:
                    git(d, "fetch", "--quiet", "--no-tags", "--no-write-fetch-head", "origin", s, timeout=300)
                except subprocess.TimeoutExpired:
                    pass


def one(d, out, repo, sha, kind):
    path = out / f"{sha}.{kind}.diff.gz"
    row = {"repository": repo, "head_sha": sha, "kind": kind,
           "path": f"data/diffs/{repo.replace('/', '__')}/{path.name}", "ok": False, "err": ""}
    if path.exists():
        return {**row, "ok": True}
    if git(d, "cat-file", "-e", f"{sha}^{{commit}}").returncode:
        return {**row, "err": "missing"}
    base = git(d, "merge-base", "origin/HEAD", sha).stdout.strip() if kind == "pr" else f"{sha}^"
    if not base:
        return {**row, "err": "no merge-base"}
    try:
        p = git(d, "diff", "--no-color", "--no-renames", base, sha, timeout=180)
    except subprocess.TimeoutExpired:
        return {**row, "err": "timeout"}
    if p.returncode:
        return {**row, "err": p.stderr.strip()[:150]}
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(p.stdout[:MAX_BYTES])
    return {**row, "ok": True}


def main():
    todo = defaultdict(list)
    nfail = defaultdict(int)
    for r in csv.DictReader(INP.open(encoding="utf-8")):
        if int(r["shard"]) == SHARD:
            kind = "pr" if r["event"] == "pull_request" else "commit"
            todo[r["repository"]].append((r["head_sha"], kind, r["outcome"]))
            nfail[r["repository"]] += r["outcome"] == "fail"
    repos = sorted(todo, key=lambda r: -nfail[r])
    log(f"shard {SHARD}: {len(repos)} repo, {sum(map(len, todo.values()))} commit, ngân sách {BUDGET_MIN} phút")
    rows, summary = [], {"shard": SHARD, "done": [], "partial": [], "not_started": [], "errors": {}}
    for i, repo in enumerate(repos, 1):
        if left_min() < 30:
            summary["not_started"] = repos[i - 1:]
            log(f"hết ngân sách, còn {len(repos) - i + 1} repo chưa làm")
            break
        d, out = CLONES / repo.replace("/", "__"), OUT / "diffs" / repo.replace("/", "__")
        out.mkdir(parents=True, exist_ok=True)
        # fail trước để nếu phải dừng giữa repo vẫn giữ phần quý nhất
        items = sorted(set((s, k) for s, k, o in todo[repo] if o == "fail")) + \
            sorted(set((s, k) for s, k, o in todo[repo] if o != "fail"))
        log(f"[{i}/{len(repos)}] {repo}: {len(items)} commit ({nfail[repo]} fail)")
        try:
            t = time.time()
            prepare(repo, d)
            log(f"  clone {(time.time() - t) / 60:.1f} phút")
            fetch_missing(d, sorted({s for s, _ in items}))
        except Exception as e:  # repo xoá/đổi tên/clone quá lâu: ghi lỗi, sang repo khác
            summary["errors"][repo] = str(e)[:300]
            log(f"  LỖI {e!s:.200}")
            shutil.rmtree(d, ignore_errors=True)
            continue
        mine, stopped = [], False
        for k in range(0, len(items), 1000):
            if left_min() < 20:
                stopped = True
                break
            with ThreadPoolExecutor(WORKERS) as ex:
                mine += ex.map(lambda x: one(d, out, repo, *x), items[k:k + 1000])
            log(f"  {len(mine)}/{len(items)}, ok {sum(r['ok'] for r in mine)}")
        rows += mine
        (summary["partial"] if stopped else summary["done"]).append(repo)
        errs = defaultdict(int)
        for r in mine:
            if not r["ok"]:
                errs[r["err"][:40]] += 1
        log(f"  xong: ok {sum(r['ok'] for r in mine)}/{len(items)}, lỗi {dict(errs) or 0}")
        shutil.rmtree(d, ignore_errors=True)
        if stopped:
            summary["not_started"] = repos[i:]
            break
    with (WORK / f"index_{SHARD}.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["repository", "head_sha", "kind", "path", "ok", "err"])
        w.writeheader()
        w.writerows(rows)
    summary.update(n=len(rows), ok=sum(r["ok"] for r in rows), minutes=round((time.time() - T0) / 60))
    (WORK / f"summary_{SHARD}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    with tarfile.open(WORK / f"diffs_{SHARD}.tar", "w") as tar:  # Kaggle giới hạn số file output -> gói một tar
        tar.add(OUT / "diffs", arcname="diffs")
    log(f"XONG shard {SHARD}: {summary['ok']}/{summary['n']} diff, done {len(summary['done'])}, "
        f"partial {summary['partial']}, chưa làm {len(summary['not_started'])}, lỗi {list(summary['errors'])}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
