"""Chọn repo Java/JVM để crawl mở rộng (US-31): thống kê GHARuns + metadata GitHub hiện tại.

Bước 1 (GHARuns, local): theo repo đếm run, run PR, số commit có CI, tỉ lệ fail.
Bước 2 (GitHub API, chỉ đọc, có cache): ngôn ngữ chính, fork, archived, số run hoàn tất trong 90 ngày gần nhất.
Bước 3: lọc theo tiêu chí và xếp hạng, giới hạn số repo mỗi tổ chức để đa dạng.

Tiêu chí (mặc định):
  - GHARuns: >= 1000 commit có CI, có run PR, tỉ lệ fail 5–60% (bỏ repo luôn xanh hoặc luôn đỏ)
  - ngôn ngữ chính Java / Kotlin / Groovy (bộ quy tắc gán nhãn viết cho Maven/Gradle)
  - không phải fork, không archived, >= 1000 run hoàn tất trong 90 ngày (log còn lấy được)
  - tối đa 25 repo / tổ chức

    uv run python -m project3.pipeline.select_repos --target 100 --out configs/repos_100.txt
"""
import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

from project3.crawl.github import GitHub, load_token

LANGS = {"Java", "Kotlin", "Groovy"}


def gharuns_stats(runs: Path, out: Path) -> None:
    con = duckdb.connect()
    con.sql("SET threads=4; SET memory_limit='3GB'")
    con.sql(f"""COPY (SELECT repository, count(*) runs,
          count(*) FILTER (WHERE event = 'pull_request') pr_runs, count(*) FILTER (WHERE event = 'push') push_runs,
          avg((conclusion = 'failure')::INT) fail_rate, count(DISTINCT path) n_wf, count(DISTINCT head_sha) n_sha,
          max(run_started_at) last_run
        FROM '{runs.as_posix()}' WHERE conclusion IN ('success', 'failure') GROUP BY 1)
        TO '{out.as_posix()}' (FORMAT parquet)""")


def graphql_meta(gh: GitHub, repos: list[str]) -> dict:
    """Ngôn ngữ chính, fork, archived cho tối đa 50 repo mỗi request (GraphQL)."""
    parts = []
    for i, r in enumerate(repos):
        owner, name = r.split("/", 1)
        parts.append(f'r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) '
                     "{ nameWithOwner primaryLanguage { name } isFork isArchived stargazerCount pushedAt }")
    for attempt in range(5):
        resp = gh.s.post("https://api.github.com/graphql", json={"query": "query {" + " ".join(parts) + "}"},
                         timeout=60)
        if resp.status_code < 500:
            break
    data = (resp.json().get("data") or {}) if resp.ok else {}
    out = {}
    for i, r in enumerate(repos):
        m = data.get(f"r{i}")
        out[r] = {"repository": r, "error": "không truy cập được"} if not m else {
            "repository": r, "language": (m["primaryLanguage"] or {}).get("name"), "fork": m["isFork"],
            "archived": m["isArchived"], "stars": m["stargazerCount"], "pushed_at": m["pushedAt"]}
    return out


def github_meta(repos: list[str], cache: Path, days: int) -> dict:
    """Metadata theo repo, lưu cache jsonl để chạy lại không gọi API lần nữa."""
    seen = {}
    if cache.exists():
        for line in cache.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            seen[r["repository"]] = r
    gh = GitHub(load_token())
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    todo = [r for r in repos if r not in seen]
    with cache.open("a", encoding="utf-8") as f:
        for k in range(0, len(todo), 50):
            for repo, row in graphql_meta(gh, todo[k:k + 50]).items():
                if row.get("language") in LANGS and not row.get("fork") and not row.get("archived"):
                    try:  # số run hoàn tất gần đây (API giới hạn total_count ở 2500)
                        runs = gh.get(f"/repos/{repo}/actions/runs", per_page=1, status="completed",
                                      created=f">={since}")
                        row["runs_recent"] = runs.get("total_count", 0)
                    except Exception as e:
                        row["error"] = str(e)[:120]
                seen[repo] = row
                f.write(json.dumps(row) + "\n")
            f.flush()
            print(f"  {min(k + 50, len(todo))}/{len(todo)} repo", flush=True)
    return seen


def main(a) -> None:
    stats = Path(a.stats)
    if not stats.exists():
        gharuns_stats(Path(a.runs), stats)
    con = duckdb.connect()
    cand = con.sql(f"""SELECT * FROM '{stats.as_posix()}' WHERE n_sha >= {a.min_sha} AND pr_runs > 0
        AND fail_rate BETWEEN {a.min_fail} AND {a.max_fail} ORDER BY n_sha DESC""").df()
    print(f"GHARuns: {len(cand)} repo qua tiêu chí bước 1", flush=True)
    meta = github_meta(list(cand.repository), Path(a.cache), a.days)
    existing = {line.strip() for p in a.existing for line in Path(p).read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")}
    rows = []
    for c in cand.itertuples():
        m = meta.get(c.repository, {})
        ok = (m.get("language") in LANGS and not m.get("fork") and not m.get("archived")
              and m.get("runs_recent", 0) >= a.min_recent_runs and c.repository not in a.exclude)
        rows.append({"repository": c.repository, "language": m.get("language"), "gharuns_commits": c.n_sha,
                     "gharuns_fail_rate": round(c.fail_rate, 3), "runs_90d": m.get("runs_recent"),
                     "stars": m.get("stars"), "already_crawled": c.repository in existing, "eligible": ok,
                     "reason": m.get("error") or ("" if ok else "loại thủ công" if c.repository in a.exclude
                                                  else "ngôn ngữ/fork/archived/ít run gần đây")})
    # chọn: repo đã crawl trước, rồi theo số run gần đây; giới hạn mỗi tổ chức
    eligible = sorted((r for r in rows if r["eligible"]), key=lambda r: (not r["already_crawled"], -r["runs_90d"]))
    per_org, chosen = {}, []
    for r in eligible:
        org = r["repository"].split("/")[0]
        if len(chosen) < a.target and (r["already_crawled"] or per_org.get(org, 0) < a.max_per_org):
            chosen.append(r)
            per_org[org] = per_org.get(org, 0) + 1
    for r in rows:
        r["selected"] = r in chosen
    with open(a.table, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(rows[0]))
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (not r["selected"], -(r["runs_90d"] or 0))))
    # repo ít commit trước: hết giờ crawl vẫn có nhiều repo nhất (số commit trên GHARuns là thước đo khối lượng)
    new = [r["repository"] for r in sorted(chosen, key=lambda r: r["gharuns_commits"]) if not r["already_crawled"]]
    Path(a.out).write_text(
        f"# {len(new)} repo mới cho crawl mở rộng, chọn bằng project3.pipeline.select_repos "
        f"({datetime.now():%d/%m/%Y}), xếp theo khối lượng tăng dần.\n# Tiêu chí và lý do từng repo: {a.table}\n" + "\n".join(new) + "\n",
        encoding="utf-8")
    print(f"đủ điều kiện {len(eligible)}, chọn {len(chosen)} (đã crawl {len(chosen) - len(new)}, mới {len(new)})")
    print("theo ngôn ngữ:", {k: sum(r["language"] == k for r in chosen) for k in LANGS})
    print("theo tổ chức:", dict(sorted(per_org.items(), key=lambda x: -x[1])[:10]))
    print(f"Đã lưu {a.out} và {a.table}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="data/gharuns/runs.parquet")
    ap.add_argument("--stats", default="data/processed/gharuns_repo_stats.parquet")
    ap.add_argument("--cache", default="data/processed/github_repo_meta.jsonl")
    ap.add_argument("--existing", nargs="*", default=["configs/repos_core.txt", "configs/repos_extra.txt"])
    ap.add_argument("--target", type=int, default=100, help="tổng số repo (kể cả repo đã crawl)")
    ap.add_argument("--min-sha", type=int, default=1000)
    ap.add_argument("--min-fail", type=float, default=0.05)
    ap.add_argument("--max-fail", type=float, default=0.60)
    ap.add_argument("--min-recent-runs", type=int, default=1000)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--max-per-org", type=int, default=25)
    ap.add_argument("--exclude", nargs="*", default=["microsoft/typespec"],
                    help="loại thủ công (vd. GitHub ghi Java nhưng thực chất là monorepo TypeScript)")
    ap.add_argument("--out", default="configs/repos_100.txt")
    ap.add_argument("--table", default="data/processed/repo_selection.csv")
    main(ap.parse_args())
