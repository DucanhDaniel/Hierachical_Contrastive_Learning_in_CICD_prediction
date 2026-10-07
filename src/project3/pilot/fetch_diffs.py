"""Lấy diff cho các commit của thí nghiệm pilot (pass + fail do code), chạy song song.

Diff dùng làm input là phần CI thực sự build:
  push: `sha^..sha`;
  PR:   `merge-base(origin/HEAD, sha)..sha` (CI của PR build bản đã ghép vào nhánh gốc).
Commit thiếu được fetch theo lô bằng `git fetch origin <sha>...`; blob được git tự tải khi chạy diff.
Kết quả: data/diffs/<repo>/<sha>.<kind>.diff và data/processed/pilot_diffs.csv.

    uv run --group exp python -m project3.pilot.fetch_diffs --repos apache/druid apache/paimon
"""
import argparse
import csv
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb

from project3.crawl.diff_probe import git, has_commit

MAX_BYTES = 2_000_000


def fetch_missing(repo_dir: Path, shas: list[str], chunk: int = 100) -> None:
    missing = [s for s in shas if not has_commit(repo_dir, s)]
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
    path = out / f"{sha}.{kind}.diff"
    row = {"head_sha": sha, "kind": kind, "path": path.as_posix(), "ok": False, "err": ""}
    if not has_commit(repo_dir, sha):
        return {**row, "err": "missing"}
    base = git(repo_dir, "merge-base", "origin/HEAD", sha).stdout.strip() if kind == "pr" else f"{sha}^"
    if not base:
        return {**row, "err": "no merge-base"}
    if not path.exists():
        try:
            p = git(repo_dir, "diff", "--no-color", "--no-renames", base, sha, timeout=180)
        except subprocess.TimeoutExpired:  # PR dựa trên nhánh cũ: diff khổng lồ, bỏ qua
            return {**row, "err": "timeout"}
        if p.returncode != 0:
            return {**row, "err": p.stderr.strip()[:150]}
        path.write_text(p.stdout[:MAX_BYTES], encoding="utf-8")
    return {**row, "ok": True}


def main(table: Path, repos: list[str], clones: Path, diffs: Path, out: Path, workers: int) -> None:
    con = duckdb.connect()
    rows = con.sql(f"""SELECT DISTINCT repository, event, head_sha FROM '{table.as_posix()}'
        WHERE repository IN ({','.join(f"'{r}'" for r in repos)}) AND (outcome = 'pass' OR cause = 'code')""").fetchall()
    print(f"{len(rows)} commit")
    result = []
    for repo in repos:
        repo_dir = clones / repo.split("/")[1]
        mine = [(sha, ev) for r, ev, sha in rows if r == repo]
        fetch_missing(repo_dir, sorted({s for s, _ in mine}))
        d = diffs / repo.replace("/", "__")
        d.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(workers) as ex:
            for i, r in enumerate(ex.map(lambda x: one(repo_dir, d, *x), mine), 1):
                result.append({"repository": repo, **r})
                if i % 250 == 0:
                    print(f"  {repo}: {i}/{len(mine)}", flush=True)
        print(f"  {repo}: ok {sum(r['ok'] for r in result if r['repository'] == repo)}/{len(mine)}", flush=True)
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
    a = ap.parse_args()
    main(Path(a.table), a.repos, Path(a.clones), Path(a.diffs), Path(a.out), a.workers)
