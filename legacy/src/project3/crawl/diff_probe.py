"""Thử lấy diff cho một mẫu commit fail của PR, trước khi lấy diff cho toàn bộ dữ liệu.

Commit của PR từ fork không có trong clone repo gốc và `pull_requests` rỗng, nên thử theo thứ tự:
  1. commit đã có sẵn trong clone (data/repos/<tên repo>);
  2. `git fetch origin <sha>` (GitHub cho fetch commit thuộc refs/pull/*/head);
  3. API `/repos/<repo>/commits/<sha>` (chỉ kiểm tra commit còn tồn tại, không lấy diff từ đây).
Mỗi commit lấy hai loại diff:
  - commit: `sha^..sha`, thay đổi của riêng commit;
  - pr:     `merge-base(origin/HEAD, sha)..sha`, toàn bộ PR so với nhánh gốc (CI của PR build bản đã ghép).
Ghi diff ra data/diffs/<repo>/<sha>.{commit,pr}.diff và bảng kết quả ra data/processed/diff_probe.csv.

    uv run python -m project3.crawl.diff_probe data/crawl_pr --per-cell 5
"""
import argparse
import csv
import json
import os
import random
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

from .build_log_labels import PRIORITY
from .gold_labels import NON_BUILD_WF
from .github import GitHub, load_token

LABELS = ("compile", "lint", "test")


def git(repo_dir: Path, *args: str, timeout: int = 600, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo_dir), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          env={**os.environ, **env} if env else None)


def has_commit(repo_dir: Path, sha: str) -> bool:
    # clone blob:none là partial clone: thiếu object thì git tự tải từ origin, nên tắt lazy fetch để kiểm tra thật
    return git(repo_dir, "cat-file", "-e", f"{sha}^{{commit}}", env={"GIT_NO_LAZY_FETCH": "1"}).returncode == 0


def fail_commits(root: Path) -> list[dict]:
    """Commit fail của PR có nhãn compile/lint/test (nguyên nhân sớm nhất trong các run fail)."""
    gold = {int(r["run_id"]): r["gold"] for r in csv.DictReader(open(root / "gold_labels.csv", encoding="utf-8-sig"))}
    out = []
    for d in sorted(p for p in root.iterdir() if p.is_dir() and (p / "runs.jsonl").exists()):
        repo = d.name.replace("__", "/")
        commits = defaultdict(lambda: {"labels": [], "start": None})
        for line in (d / "runs.jsonl").read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:  # dòng cuối đang được crawler ghi dở
                continue
            if not r["event"].startswith("pull_request") or NON_BUILD_WF.search(r["name"] or ""):
                continue
            c = commits[(r.get("head_repository") or repo, r["head_branch"], r["head_sha"])]
            c["start"] = min(c["start"] or r["created_at"], r["created_at"])
            if r["conclusion"] == "failure":
                c["labels"].append(gold.get(r["id"], "?"))
        for (head_repo, branch, sha), c in commits.items():
            known = [l for l in PRIORITY if l in c["labels"]]
            if known and known[0] in LABELS:
                out.append({"repo": repo, "head_repo": head_repo, "fork": head_repo != repo, "branch": branch,
                            "sha": sha, "label": known[0], "start": c["start"]})
    return out


def numstat(repo_dir: Path, a: str, b: str, path: Path) -> dict:
    t = time.time()
    p = git(repo_dir, "diff", "--no-color", "--no-renames", a, b)
    if p.returncode != 0:
        return {"ok": False, "err": p.stderr.strip()[:150]}
    path.write_text(p.stdout, encoding="utf-8")
    files = add = rem = 0
    for line in git(repo_dir, "diff", "--numstat", "--no-renames", a, b).stdout.splitlines():
        x, y, _ = line.split("\t", 2)
        files += 1
        add += int(x) if x.isdigit() else 0
        rem += int(y) if y.isdigit() else 0
    return {"ok": True, "files": files, "add": add, "del": rem, "bytes": len(p.stdout.encode()), "sec": round(time.time() - t, 1)}


def probe(c: dict, repos: Path, diffs: Path, gh: GitHub) -> dict:
    repo_dir = repos / c["repo"].split("/")[1]
    row = {**c, "method": "", "fetch_sec": 0.0, "err": ""}
    if not repo_dir.exists():
        return {**row, "method": "no_clone"}
    t = time.time()
    if has_commit(repo_dir, c["sha"]):
        row["method"] = "local"
    else:
        p = git(repo_dir, "fetch", "--quiet", "--no-tags", "--filter=blob:none", "origin", c["sha"])
        if p.returncode == 0 and has_commit(repo_dir, c["sha"]):
            row["method"] = "fetch_sha"
        else:
            row["err"] = p.stderr.strip()[:150]
            try:
                gh.get(f"/repos/{c['repo']}/commits/{c['sha']}")
                row["method"] = "api_only"
            except Exception as e:  # commit đã mất (force-push, xoá fork)
                row["method"] = "missing"
                row["err"] += f" | api: {str(e)[:100]}"
    row["fetch_sec"] = round(time.time() - t, 1)
    if row["method"] not in ("local", "fetch_sha"):
        return row
    out = diffs / c["repo"].replace("/", "__")
    out.mkdir(parents=True, exist_ok=True)
    for kind, base in (("commit", f"{c['sha']}^"),
                       ("pr", git(repo_dir, "merge-base", "origin/HEAD", c["sha"]).stdout.strip())):
        s = numstat(repo_dir, base, c["sha"], out / f"{c['sha']}.{kind}.diff") if base else {"ok": False, "err": "no merge-base"}
        for k, v in s.items():
            row[f"{kind}_{k}"] = v
    row["pr_commits"] = git(repo_dir, "rev-list", "--count", f"origin/HEAD..{c['sha']}").stdout.strip()
    return row


def main(root: Path, repos: Path, diffs: Path, out: Path, per_cell: int, seed: int) -> None:
    cells = defaultdict(list)
    for c in fail_commits(root):
        cells[(c["repo"], c["fork"], c["label"])].append(c)
    rng = random.Random(seed)
    sample = [c for k in sorted(cells) for c in rng.sample(cells[k], min(per_cell, len(cells[k])))]
    print(f"{len(sample)} commit mẫu từ {sum(map(len, cells.values()))} commit fail PR có nhãn {'/'.join(LABELS)}")
    for k in sorted(cells):
        print(f"  {k[0]:18} fork={k[1]!s:5} {k[2]:8} {len(cells[k])}")
    gh = GitHub(load_token())
    rows = []
    for i, c in enumerate(sample, 1):
        r = probe(c, repos, diffs, gh)
        rows.append(r)
        print(f"[{i}/{len(sample)}] {c['repo']} {c['sha'][:10]} fork={c['fork']} {c['label']}: {r['method']} "
              f"({r['fetch_sec']}s) commit={r.get('commit_files', '-')} file pr={r.get('pr_files', '-')} file", flush=True)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, keys)
        w.writeheader()
        w.writerows(rows)
    print(f"Đã lưu {out}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default="data/crawl_pr")
    ap.add_argument("--repos", default="data/repos")
    ap.add_argument("--diffs", default="data/diffs")
    ap.add_argument("--out", default="data/processed/diff_probe.csv")
    ap.add_argument("--per-cell", type=int, default=5)
    ap.add_argument("--seed", type=int, default=20261007)
    a = ap.parse_args()
    main(Path(a.root), Path(a.repos), Path(a.diffs), Path(a.out), a.per_cell, a.seed)
