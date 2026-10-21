"""Lấy diff cho các commit (pass + fail do code; tuỳ chọn cả fail chưa gán nhãn), chạy song song.

Diff dùng làm input là phần CI thực sự build:
  push: `sha^..sha`;
  PR:   `merge-base(origin/HEAD, sha)..sha` (CI của PR build bản đã ghép vào nhánh gốc).
Repo chưa có thì clone partial (blob:none, không checkout); nhánh chính được fetch lại trước khi tính merge-base.
Commit thiếu được fetch theo lô bằng `git fetch origin <sha>...`; blob được git tự tải khi chạy diff.
Kết quả: data/diffs/<repo>/<sha>.<kind>.diff.gz (nén để vừa ổ đĩa khi mở rộng ~100 repo; file .diff cũ vẫn dùng được)
và data/processed/pilot_diffs.csv. Đọc bằng `experiment.read_diff()`.

    uv run --group exp python -m project3.pilot.fetch_diffs --repos apache/druid apache/paimon
    uv run --group exp python -m project3.pilot.fetch_diffs --table data/processed/commits_all.parquet
        --repos apache/pinot apache/ozone ... --include-unlabeled --out data/processed/diffs_extra.csv
    # 100 repo: clone và diff ở ổ C, xoá clone sau mỗi repo
    ... --clones C:/p3data/repos --diffs C:/p3data/diffs --cleanup
"""
import argparse
import csv
import gzip
import os
import shutil
import stat
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb

from project3.crawl.diff_probe import git, has_commit

MAX_BYTES = 2_000_000
REPACK_EVERY = 500


def present(repo_dir: Path, shas: list[str]) -> set[str]:
    """Kiểm tra theo lô bằng một tiến trình cat-file (tắt lazy fetch của partial clone)."""
    p = subprocess.run(["git", "-C", str(repo_dir), "cat-file", "--batch-check"],
                       input="".join(f"{s}^{{commit}}\n" for s in shas),
                       capture_output=True, text=True, env={**os.environ, "GIT_NO_LAZY_FETCH": "1"})
    return {s for s, line in zip(shas, p.stdout.splitlines()) if not line.endswith("missing")}


def fetch_missing(repo_dir: Path, shas: list[str], chunk: int = 100) -> None:
    have = present(repo_dir, shas)
    missing = [s for s in shas if s not in have]
    print(f"  {repo_dir.name}: {len(missing)}/{len(shas)} commit cần fetch", flush=True)
    for i in range(0, len(missing), chunk):
        part = missing[i:i + chunk]
        p = git(repo_dir, "fetch", "--quiet", "--no-tags", "--no-write-fetch-head", "--filter=blob:none", "origin", *part,
                timeout=1800)
        if p.returncode != 0:  # một sha hỏng làm hỏng cả lô -> thử từng cái
            for s in part:
                git(repo_dir, "fetch", "--quiet", "--no-tags", "--no-write-fetch-head", "--filter=blob:none", "origin", s)


def one(repo_dir: Path, out: Path, sha: str, event: str) -> dict:
    kind = "pr" if event == "pull_request" else "commit"
    old, path = out / f"{sha}.{kind}.diff", out / f"{sha}.{kind}.diff.gz"
    if old.exists():  # bản không nén từ các lần chạy trước
        return {"head_sha": sha, "kind": kind, "path": old.as_posix(), "ok": True, "err": ""}
    row = {"head_sha": sha, "kind": kind, "path": path.as_posix(), "ok": False, "err": ""}
    if path.exists():
        return {**row, "ok": True}
    if not has_commit(repo_dir, sha):
        return {**row, "err": "missing"}
    base = git(repo_dir, "merge-base", "origin/HEAD", sha).stdout.strip() if kind == "pr" else f"{sha}^"
    if not base:
        return {**row, "err": "no merge-base"}
    try:
        p = git(repo_dir, "diff", "--no-color", "--no-renames", base, sha, timeout=180)
    except subprocess.TimeoutExpired:  # PR dựa trên nhánh cũ: diff khổng lồ, bỏ qua
        return {**row, "err": "timeout"}
    if p.returncode != 0:
        return {**row, "err": p.stderr.strip()[:150]}
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(p.stdout[:MAX_BYTES])
    return {**row, "ok": True}


def prepare(repo: str, repo_dir: Path) -> None:
    """Clone (partial, không checkout) nếu chưa có; cập nhật nhánh chính để merge-base của PR không dùng mốc cũ."""
    if not repo_dir.exists():
        print(f"  clone {repo}", flush=True)
        subprocess.run(["git", "clone", "--quiet", "--filter=blob:none", "--no-checkout",
                        f"https://github.com/{repo}.git", str(repo_dir)], check=True, timeout=3600)
    branch = git(repo_dir, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").stdout.strip().split("/", 1)[-1]
    git(repo_dir, "fetch", "--quiet", "--no-tags", "--filter=blob:none", "origin",
        f"+refs/heads/{branch}:refs/remotes/origin/{branch}", timeout=1800)


def remove_clone(repo_dir: Path) -> None:
    """Xoá clone (file pack của git là read-only trên Windows nên bỏ cờ đó trước)."""
    shutil.rmtree(repo_dir, onexc=lambda f, path, _: (os.chmod(path, stat.S_IWRITE), f(path)))


def main(table: Path, repos: list[str], clones: Path, diffs: Path, out: Path, workers: int, unlabeled: bool,
         cleanup: bool = False) -> None:
    con = duckdb.connect()
    keep = "outcome = 'pass' OR cause = 'code'" + (" OR (outcome = 'fail' AND cause = '?')" if unlabeled else "")
    rows = con.sql(f"""SELECT DISTINCT repository, event, head_sha FROM '{table.as_posix()}'
        WHERE repository IN ({','.join(f"'{r}'" for r in repos)}) AND ({keep})""").fetchall()
    print(f"{len(rows)} commit")
    result = []
    for repo in repos:
        repo_dir = clones / repo.split("/")[1]
        mine = [(sha, ev) for r, ev, sha in rows if r == repo]
        prepare(repo, repo_dir)
        fetch_missing(repo_dir, sorted({s for s, _ in mine}))
        d = diffs / repo.replace("/", "__")
        d.mkdir(parents=True, exist_ok=True)
        # mỗi lần git tự tải blob tạo một packfile; hàng nghìn pack làm mọi lệnh git chậm hẳn -> gộp sau mỗi đợt
        for k in range(0, len(mine), REPACK_EVERY):
            with ThreadPoolExecutor(workers) as ex:
                for r in ex.map(lambda x: one(repo_dir, d, *x), mine[k:k + REPACK_EVERY]):
                    result.append({"repository": repo, **r})
            git(repo_dir, "repack", "-a", "-d", "-q", timeout=1800)
            print(f"  {repo}: {min(k + REPACK_EVERY, len(mine))}/{len(mine)}", flush=True)
        print(f"  {repo}: ok {sum(r['ok'] for r in result if r['repository'] == repo)}/{len(mine)}", flush=True)
        if cleanup:  # diff đã lưu (nén); clone chỉ cần lúc tính diff, xoá để đĩa chỉ chứa một clone tại một thời điểm
            remove_clone(repo_dir)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(result[0]))
        w.writeheader()
        w.writerows(result)
    print(f"Đã lưu {out}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", default="data/processed/commits_pilot.parquet")
    ap.add_argument("--repos", nargs="+", default=["apache/druid", "apache/paimon"])
    ap.add_argument("--clones", default="data/repos")
    ap.add_argument("--diffs", default="data/diffs")
    ap.add_argument("--out", default="data/processed/pilot_diffs.csv")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--cleanup", action="store_true", help="xoá clone của mỗi repo sau khi lấy xong diff")
    ap.add_argument("--include-unlabeled", action="store_true", help="lấy cả commit fail chưa gán nhãn (cause = '?')")
    a = ap.parse_args()
    main(Path(a.table), a.repos, Path(a.clones), Path(a.diffs), Path(a.out), a.workers, a.include_unlabeled, a.cleanup)
