"""Tên step fail trong GHARuns (2–6/2026) còn xuất hiện trong dữ liệu kiểm chứng gần đây bao nhiêu.

    uv run python -m project3.crawl.step_overlap data/validate
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import duckdb

REPOS = ("apache/paimon", "apache/pinot", "apache/gravitino", "apache/druid", "apache/iceberg", "apache/kafka")


def main(root: Path) -> None:
    con = duckdb.connect()
    old = con.sql(f"""SELECT r.repository, s.name step, count(DISTINCT r.id) n FROM 'data/gharuns/runs.parquet' r
        JOIN 'data/gharuns/jobs.parquet' j USING (check_suite_id) JOIN 'data/gharuns/steps.parquet' s ON s.job_id = j.id
        WHERE r.repository IN {REPOS} AND r.event = 'push' AND r.head_branch IN ('master','main','trunk')
          AND r.conclusion = 'failure' AND upper(j.conclusion) = 'FAILURE' AND upper(s.conclusion) = 'FAILURE'
        GROUP BY 1, 2""").fetchall()
    new = defaultdict(set)
    for d in root.iterdir():
        f = d / "jobs.jsonl"
        if f.exists():
            repo = d.name.replace("__", "/")
            for line in f.read_text(encoding="utf-8").splitlines():
                for j in json.loads(line)["jobs"]:
                    new[repo] |= {s["name"] for s in j["steps"]}
    tot = sum(n for *_, n in old)
    hit = sum(n for r, s, n in old if s in new[r])
    print(f"Run fail GHARuns (tính theo step fail): {tot}; tên step còn xuất hiện gần đây: {hit} ({hit / tot:.0%})")
    per = defaultdict(lambda: [0, 0])
    for r, s, n in old:
        per[r][0] += n
        per[r][1] += n if s in new[r] else 0
    for r, (a, b) in sorted(per.items()):
        print(f"   {r:18s} {b:4d}/{a:4d} ({b / a:.0%})" + ("" if new[r] else "  (chưa có dữ liệu gần đây)"))
    print("Top step fail trong GHARuns:")
    for r, s, n in sorted(old, key=lambda x: -x[2])[:12]:
        print(f"   {n:4d} {r:16s} {s[:45]:45s} {'còn' if s in new[r] else 'KHÔNG còn'}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "data/validate"))
