"""Tập nhãn cuối từ dữ liệu crawl kèm log: gộp theo commit (push lên nhánh chính hoặc commit trong PR).

- Commit fail nếu có ít nhất một workflow build fail (bỏ workflow không phải build: cherry-pick, quét CVE...).
- Loại lỗi của commit = nguyên nhân sớm nhất trong các run fail: compile → dependency → lint → test → flaky → infra.
- Nhóm nhãn theo cây: pass | fail → code {test, build = compile/lint/dependency} | env {infra, flaky}.
- Lần fail đầu:
    push: commit fail mà commit liền trước trên nhánh chính (theo thời gian, cùng repo) pass;
    PR:   commit fail mà commit liền trước trong cùng PR pass, hoặc là commit đầu tiên của PR
          (coi như nhánh gốc đang pass).

    uv run python -m project3.crawl.build_log_labels data/validate
    uv run python -m project3.crawl.build_log_labels data/validate data/crawl_pr --out data/processed/commits_all.parquet
Mỗi root cần có gold_labels.csv (chạy gold_labels trước).
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import duckdb

from .gold_labels import NON_BUILD_WF

PRIORITY = ["buildconfig", "compile", "dependency", "lint", "test", "flaky", "infra"]
GROUP = {"buildconfig": "build", "compile": "build", "dependency": "build", "lint": "build", "test": "test", "flaky": "env", "infra": "env"}
CAUSE = {"build": "code", "test": "code", "env": "env"}


def load_commits(root: Path, commits: dict) -> None:
    with (root / "gold_labels.csv").open(encoding="utf-8-sig") as f:
        labels = {int(r["run_id"]): r for r in csv.DictReader(f)}
    gold = {rid: r["gold"] for rid, r in labels.items()}
    excluded = {rid for rid, r in labels.items()
                if r.get("non_build", "").lower() == "true" or r["gold"] == "non_build"}
    for d in sorted(p for p in root.iterdir() if p.is_dir() and (p / "runs.jsonl").exists()):
        repo = d.name.replace("__", "/")
        for line in (d / "runs.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if (r["id"] in excluded or r["conclusion"] not in ("success", "failure")
                    or NON_BUILD_WF.search(r["name"] or "")):
                continue
            pr = r["event"].startswith("pull_request")
            # chuỗi commit: nhánh chính (push) hoặc một PR = (repo nguồn, nhánh nguồn)
            seq = f"pr:{r.get('head_repository') or repo}:{r['head_branch']}" if pr else "push"
            c = commits[(repo, seq, r["head_sha"])]
            c["runs"] += 1
            c["start"] = min(c["start"] or r["created_at"], r["created_at"])
            c["pr"] = c["pr"] or (r.get("pull_requests") or [None])[0]
            if r["conclusion"] == "failure":
                c["fail"] += 1
                c["labels"].append(gold.get(r["id"], "?"))


def main(roots: list[Path], out: Path) -> None:
    commits = defaultdict(lambda: {"runs": 0, "fail": 0, "labels": [], "start": None, "pr": None})
    for root in roots:
        load_commits(root, commits)
    seqs = defaultdict(list)
    for (repo, seq, sha), c in commits.items():
        seqs[(repo, seq)].append((c["start"], sha, c))
    rows = []
    for (repo, seq), lst in seqs.items():
        lst.sort(key=lambda x: x[0])
        prev = False if seq != "push" else None  # PR: commit đầu so với nhánh gốc (giả định pass)
        for start, sha, c in lst:
            failed = c["fail"] > 0
            known = [l for l in PRIORITY if l in c["labels"]]
            label = "pass" if not failed else (known[0] if known else "?")
            group = GROUP.get(label, label)
            rows.append((repo, "push" if seq == "push" else "pull_request", seq, c["pr"], sha, start, c["runs"],
                         c["fail"], "fail" if failed else "pass", CAUSE.get(group, group), group, label,
                         ",".join(sorted(set(c["labels"]))), failed and prev is False))
            prev = failed
    con = duckdb.connect()
    con.sql("CREATE TABLE commits (repository VARCHAR, event VARCHAR, sequence VARCHAR, pr_number BIGINT, "
            "head_sha VARCHAR, first_run_at VARCHAR, n_runs INT, n_fail INT, outcome VARCHAR, cause VARCHAR, "
            "label_group VARCHAR, label VARCHAR, run_labels VARCHAR, first_failure BOOLEAN)")
    con.executemany("INSERT INTO commits VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    con.sql(f"COPY commits TO '{out.as_posix()}' (FORMAT parquet)")
    print(con.sql("""SELECT repository, event, count(*) commits, sum((outcome='fail')::int) fail,
        round(100*avg((outcome='fail')::int),1) pct_fail, sum(first_failure::int) lan_fail_dau,
        min(first_run_at)[:10] tu, max(first_run_at)[:10] den FROM commits GROUP BY 1, 2 ORDER BY 3 DESC"""))
    print(con.sql("""SELECT cause, label_group, label, count(*) n_fail, round(100*count(*)/sum(count(*)) OVER (),1) pct,
        sum(first_failure::int) n_lan_fail_dau FROM commits WHERE outcome='fail' GROUP BY ALL ORDER BY 1, 2, 4 DESC"""))
    print(f"Đã lưu {out}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("roots", nargs="*", default=["data/validate"])
    ap.add_argument("--out", default="data/processed/commits_logs90.parquet")
    a = ap.parse_args()
    main([Path(r) for r in a.roots], Path(a.out))
