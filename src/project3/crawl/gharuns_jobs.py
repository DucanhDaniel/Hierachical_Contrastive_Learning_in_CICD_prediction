"""Job fail của các build push lên nhánh chính (GHARuns) + thử gán loại lỗi theo tên job.

    uv run python -m project3.crawl.gharuns_jobs apache/paimon apache/pinot apache/gravitino apache/druid apache/iceberg
"""
import re
import sys
from collections import Counter

import duckdb

from .analyze import AGGREGATOR, NAME_RULES

RUNS, JOBS = "data/gharuns/runs.parquet", "data/gharuns/jobs.parquet"


def label(name: str) -> str | None:
    n = name.lower()
    for lab, pat in NAME_RULES:
        if re.search(pat, n):
            return lab
    return None


def main(repos: list[str]) -> None:
    con = duckdb.connect()
    repo_list = ", ".join(f"'{r}'" for r in repos)
    con.sql(f"""CREATE TABLE fr AS SELECT id run_id, check_suite_id, repository, path FROM '{RUNS}'
        WHERE repository IN ({repo_list}) AND event='push' AND head_branch IN ('master','main','trunk')
          AND conclusion='failure'""")
    con.sql(f"""CREATE TABLE fj AS SELECT fr.*, j.name job, j.conclusion FROM fr
        LEFT JOIN '{JOBS}' j USING (check_suite_id)""")
    print(con.sql("""SELECT repository, count(DISTINCT run_id) run_fail,
        count(DISTINCT run_id) FILTER (WHERE job IS NOT NULL) co_job,
        count(DISTINCT run_id) FILTER (WHERE upper(conclusion)='FAILURE') co_job_fail FROM fj GROUP BY 1 ORDER BY 2 DESC"""))
    rows = con.sql("SELECT repository, run_id, job FROM fj WHERE upper(conclusion)='FAILURE'").fetchall()
    per_run = {}
    jobs_c = Counter()
    by_run = {}
    for repo, rid, job in rows:
        jobs_c[(repo, job)] += 1
        by_run.setdefault((repo, rid), []).append(job)
    for key, jobs in by_run.items():
        real = [j for j in jobs if not AGGREGATOR.search(j)] or jobs  # bỏ job tổng hợp nếu có job thật
        per_run[key] = {label(j) or "?" for j in real}
    labs = Counter()
    for (repo, _), ls in per_run.items():
        labs[(repo, "+".join(sorted(ls)) if len(ls) > 1 else next(iter(ls)))] += 1
    total = Counter()
    for (repo, lab), n in labs.items():
        total[lab if "+" not in lab else "nhiều loại"] += n
    print("Nhãn theo tên job (mỗi run fail):", dict(total.most_common()))
    unl = sum(n for (r, l), n in labs.items() if l == "?")
    print(f"Gán được: {len(per_run) - unl}/{len(per_run)} run ({1 - unl / max(1, len(per_run)):.0%})")
    print("Job fail hay gặp:")
    for (repo, job), n in jobs_c.most_common(25):
        print(f"   {n:4d}  {repo:18s} {job[:70]:70s} -> {label(job) or '?'}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
