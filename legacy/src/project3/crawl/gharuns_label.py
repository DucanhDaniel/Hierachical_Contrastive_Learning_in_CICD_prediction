"""Gán nhãn loại lỗi cho build trên nhánh chính (GHARuns) và gộp theo commit.

Thứ tự gán nhãn cho mỗi run fail:
  1. tên step fail (bỏ step/job tổng hợp)    2. tên job fail    3. không gán được -> "?"
Step thuộc nhóm setup/hạ tầng (Set up job, checkout, setup-java, cache, download...) -> "infra".
Đợt fail hàng loạt: cùng một step fail ở >= 3 workflow của cùng repo trong 2 giờ -> "infra".

    uv run python -m project3.crawl.gharuns_label apache/paimon apache/pinot apache/gravitino apache/druid apache/iceberg apache/kafka
"""
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import duckdb

from .analyze import AGGREGATOR, NAME_RULES

RUNS, JOBS, STEPS = (f"data/gharuns/{n}.parquet" for n in ("runs", "jobs", "steps"))
OUT = Path("data/processed")
MAIN = ("master", "main", "trunk")
INFRA_STEP = re.compile(r"^set up job$|checkout|setup[- ](java|jdk|python|node|gradle|maven|go|uv)|set up (jdk|java|python|node)|"
                        r"cache|download|free (up )?disk|docker login|login to|upload|post |complete job", re.I)


def rule_label(name: str) -> str | None:
    n = name.lower()
    for lab, pat in NAME_RULES:
        if re.search(pat, n):
            return lab
    return None


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def main(repos: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    repo_list = ", ".join(f"'{r}'" for r in repos)
    con.sql(f"""CREATE TABLE runs AS SELECT id run_id, check_suite_id, repository, path, head_sha, run_attempt,
                   conclusion, run_started_at FROM '{RUNS}'
        WHERE repository IN ({repo_list}) AND event='push' AND head_branch IN {MAIN}
          AND conclusion IN ('success','failure')""")
    con.sql(f"""CREATE TABLE fjobs AS SELECT r.run_id, j.id job_id, j.name job FROM runs r
        JOIN '{JOBS}' j USING (check_suite_id) WHERE r.conclusion='failure' AND upper(j.conclusion)='FAILURE'""")
    con.sql(f"""CREATE TABLE fsteps AS SELECT f.run_id, f.job_id, f.job, s.step_number, s.name step FROM fjobs f
        JOIN '{STEPS}' s USING (job_id) WHERE upper(s.conclusion)='FAILURE'""")
    n_fail_runs = con.sql("SELECT count(*) FROM runs WHERE conclusion='failure'").fetchone()[0]
    n_jobs = con.sql("SELECT count(DISTINCT run_id) FROM fjobs").fetchone()[0]
    n_steps = con.sql("SELECT count(DISTINCT run_id) FROM fsteps").fetchone()[0]
    print(f"Run fail: {n_fail_runs} | có job fail: {n_jobs} | có step fail: {n_steps}")

    runs = {r[0]: r for r in con.sql("SELECT run_id, repository, path, head_sha, run_attempt, conclusion, run_started_at "
                                      "FROM runs").fetchall()}
    steps_by_run = defaultdict(list)
    for rid, _, job, _, step in con.sql("SELECT * FROM fsteps").fetchall():
        steps_by_run[rid].append((job, step))
    jobs_by_run = defaultdict(list)
    for rid, _, job in con.sql("SELECT * FROM fjobs").fetchall():
        jobs_by_run[rid].append(job)

    # 1-2) gán nhãn từng run fail
    run_label, run_tier, run_key_step = {}, {}, {}
    for rid, (_, repo, path, sha, att, concl, start) in runs.items():
        if concl != "failure":
            continue
        lab = tier = None
        steps = [(j, s) for j, s in steps_by_run.get(rid, []) if not AGGREGATOR.search(s) and not AGGREGATOR.search(j)] \
            or steps_by_run.get(rid, [])
        if steps:
            infra = [s for _, s in steps if INFRA_STEP.search(s)]
            labs = {rule_label(s) for _, s in steps if not INFRA_STEP.search(s)} - {None}
            if not labs:  # step chung chung (vd "Run ./gradlew ...") -> thử tên job của step đó
                labs = {rule_label(j) for j, s in steps if not INFRA_STEP.search(s)} - {None}
            if labs:
                lab, tier = (next(iter(labs)) if len(labs) == 1 else "+".join(sorted(labs))), "step"
            elif infra:
                lab, tier = "infra", "step"
            run_key_step[rid] = steps[0][1]
        if not lab:
            jobs = [j for j in jobs_by_run.get(rid, []) if not AGGREGATOR.search(j)] or jobs_by_run.get(rid, [])
            labs = {rule_label(j) for j in jobs} - {None}
            if labs:
                lab, tier = (next(iter(labs)) if len(labs) == 1 else "+".join(sorted(labs))), "job"
        run_label[rid], run_tier[rid] = lab or "?", tier or "none"

    # 3) đợt fail bất thường: >= 5 commit khác nhau cùng fail ở một step trong 1 giờ -> đánh dấu loại bỏ
    #    (một commit hỏng thì fail ở nhiều workflow cùng lúc là bình thường, nên không xét theo số workflow)
    by_step = defaultdict(list)
    for rid, step in run_key_step.items():
        _, repo, path, sha, *_, start = runs[rid]
        by_step[(repo, step)].append((ts(start), sha, rid))
    burst = set()
    for evs in by_step.values():
        evs.sort()
        for i, (t0, _, _) in enumerate(evs):
            win = [e for e in evs[i:] if e[0] - t0 <= timedelta(hours=1)]
            if len({s for _, s, _ in win}) >= 5:
                burst |= {rid for _, _, rid in win}

    # Thống kê mức run
    fails = [rid for rid in run_label]
    print("Tầng gán nhãn (run):", dict(Counter(run_tier[r] for r in fails).most_common()))
    norm = lambda l: "nhiều loại" if "+" in l else l
    print("Nhãn (run):", dict(Counter(norm(run_label[r]) for r in fails).most_common()))
    print(f"Run thuộc đợt fail bất thường (đánh dấu loại): {len(burst)}")
    print("Step fail hay gặp:", Counter(s for r in fails for _, s in steps_by_run.get(r, [])[:1]).most_common(12))
    succ_rerun = sum(1 for r in runs.values() if r[5] == "success" and (r[4] or 1) > 1)
    print(f"Run success ở lần chạy lại (dấu hiệu flaky): {succ_rerun}")

    # Gộp theo commit: fail nếu có workflow fail; nhãn = tập nhãn của các run fail
    commits = defaultdict(lambda: {"runs": 0, "fail": 0, "labels": set(), "start": None, "burst": False})
    for rid, (_, repo, path, sha, att, concl, start) in runs.items():
        c = commits[(repo, sha)]
        c["runs"] += 1
        c["start"] = min(c["start"] or start, start)
        if concl == "failure":
            c["fail"] += 1
            for l in run_label[rid].split("+"):
                c["labels"].add(l)
            c["burst"] |= rid in burst
    rows = []
    per_repo = defaultdict(list)
    for (repo, sha), c in commits.items():
        per_repo[repo].append((c["start"], sha, c))
    stats = []
    for repo, lst in per_repo.items():
        lst.sort()
        prev_fail = None
        n_first = n_fail = 0
        for start, sha, c in lst:
            failed = c["fail"] > 0
            labs = sorted(l for l in c["labels"])
            real = [l for l in labs if l not in ("infra", "?")]
            # nhiều loại lỗi trong một commit -> lấy giai đoạn sớm nhất (compile hỏng thì test cũng không chạy)
            prio = [l for l in ("compile", "dependency", "lint", "test") if l in real]
            main_lab = "pass" if not failed else (prio[0] if prio else ("infra" if "infra" in labs else "?"))
            first = failed and prev_fail is False
            n_first += first
            n_fail += failed
            rows.append((repo, sha, start, c["runs"], c["fail"], "fail" if failed else "pass", main_lab, ",".join(labs), first,
                         c["burst"]))
            prev_fail = failed
        stats.append((repo, len(lst), n_fail, n_first))
    con.sql("CREATE TABLE commits (repository VARCHAR, head_sha VARCHAR, first_run_at VARCHAR, n_runs INT, n_fail INT, "
            "outcome VARCHAR, label VARCHAR, all_labels VARCHAR, first_failure BOOLEAN, burst BOOLEAN)")
    con.executemany("INSERT INTO commits VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    con.sql(f"COPY commits TO '{OUT / 'commits.parquet'}' (FORMAT parquet)")
    print("\nMức commit (push lên nhánh chính):")
    print(con.sql("""SELECT repository, count(*) commits, sum((outcome='fail')::int) fail,
        round(100*avg((outcome='fail')::int),1) pct_fail, sum(first_failure::int) lan_fail_dau,
        sum(burst::int) bat_thuong FROM commits GROUP BY 1 ORDER BY 2 DESC"""))
    print(con.sql("""SELECT label, count(*) n_fail, sum(first_failure::int) n_lan_fail_dau FROM commits
        WHERE outcome='fail' AND NOT burst GROUP BY 1 ORDER BY 2 DESC"""))
    print(f"Đã lưu {OUT / 'commits.parquet'}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
