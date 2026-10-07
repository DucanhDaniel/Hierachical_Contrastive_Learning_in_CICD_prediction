"""Khảo sát GHARuns trực tiếp trên Zenodo (DuckDB đọc Parquet qua HTTP range, không tải toàn bộ).

    uv run python -m project3.crawl.gharuns_probe apache/superset apache/airflow
"""
import sys

import duckdb

BASE = "https://zenodo.org/records/20427454/files"
RUNS, JOBS, STEPS = (f"{BASE}/{n}.parquet?download=1" for n in ("runs", "jobs", "steps"))


def main(repos: list[str]) -> None:
    con = duckdb.connect()
    con.sql("INSTALL httpfs; LOAD httpfs;")
    print(con.sql(f"DESCRIBE SELECT * FROM read_parquet('{RUNS}')"))
    print(con.sql(f"SELECT count(*) AS runs, count(DISTINCT repository) AS repos, min(run_started_at), max(run_started_at) "
                  f"FROM read_parquet('{RUNS}')"))
    repo_list = ", ".join(f"'{r}'" for r in repos)
    con.sql(f"CREATE TABLE r AS SELECT * FROM read_parquet('{RUNS}') WHERE repository IN ({repo_list})")
    print(con.sql("SELECT repository, count(*) runs, min(run_started_at) tu, max(run_started_at) den FROM r GROUP BY 1"))
    print(con.sql("SELECT repository, event, conclusion, count(*) n FROM r GROUP BY ALL ORDER BY repository, n DESC LIMIT 40"))
    con.sql("COPY r TO 'data/gharuns_runs_sample.parquet' (FORMAT parquet)")
    print("đã lưu data/gharuns_runs_sample.parquet")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
