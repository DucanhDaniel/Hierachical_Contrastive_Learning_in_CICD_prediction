"""Thống kê bảng runs của GHARuns cho vài repo: phạm vi, tỉ lệ fail, chuỗi build, Parrot, lần fail đầu.

    uv run python -m project3.crawl.gharuns_runs apache/superset apache/airflow
"""
import sys

import duckdb

RUNS = "data/gharuns/runs.parquet"


def main(repos: list[str]) -> None:
    con = duckdb.connect()
    print(con.sql(f"SELECT count(*) runs, count(DISTINCT repository) repos, min(run_started_at) tu, max(run_started_at) den "
                  f"FROM '{RUNS}'"))
    repo_list = ", ".join(f"'{r}'" for r in repos)
    con.sql(f"CREATE TABLE r AS SELECT * FROM '{RUNS}' WHERE repository IN ({repo_list})")
    print(con.sql("SELECT repository, count(*) runs, count(DISTINCT path) workflows, "
                  "min(run_started_at) tu, max(run_started_at) den FROM r GROUP BY 1"))
    print(con.sql("SELECT repository, event, count(*) n, "
                  "round(100*avg((conclusion='failure')::int),1) pct_fail FROM r GROUP BY 1,2 "
                  "QUALIFY row_number() OVER (PARTITION BY repository ORDER BY n DESC) <= 5 ORDER BY 1, n DESC"))

    # Chuỗi build trên nhánh mặc định (push), theo từng workflow
    con.sql("""CREATE TABLE seq AS
        SELECT repository, path, head_branch, head_sha, run_started_at, conclusion, run_attempt,
               lag(conclusion) OVER (PARTITION BY repository, path ORDER BY run_started_at) prev
        FROM r WHERE event = 'push' AND head_branch IN ('master', 'main') AND conclusion IN ('success', 'failure')""")
    print("Push lên master/main, theo workflow:")
    print(con.sql("""SELECT repository, count(*) builds, count(DISTINCT head_sha) commits, count(DISTINCT path) workflows,
               sum((conclusion='failure')::int) fails,
               round(100*avg((conclusion='failure')::int),1) pct_fail,
               round(100*avg((conclusion=prev)::int) FILTER (WHERE prev IS NOT NULL),1) parrot_dung_pct,
               sum((prev='success' AND conclusion='failure')::int) lan_fail_dau,
               sum((run_attempt>1)::int) chay_lai
        FROM seq GROUP BY 1"""))
    print("Top workflow có nhiều lần fail đầu (push master/main):")
    print(con.sql("""SELECT repository, path, count(*) builds, sum((conclusion='failure')::int) fails,
               sum((prev='success' AND conclusion='failure')::int) lan_fail_dau
        FROM seq GROUP BY 1,2 ORDER BY lan_fail_dau DESC LIMIT 12"""))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
