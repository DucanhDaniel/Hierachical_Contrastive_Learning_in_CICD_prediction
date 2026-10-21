"""Chọn repo cho đợt crawl 2 (18/10/2026): ưu tiên repo nhiều nhãn tầng 3 hiếm để giảm lệch số mẫu.

Mỗi repo ứng viên lấy ~15 run fail gần đây, với mỗi run tải log 1 job fail (job giai đoạn sớm như crawler)
rồi gán lá tầng 3 bằng chính bộ quy tắc (gold_label + subtype): 1 + 2×15 request/repo.
`calibrate` cho thấy chỉ đọc tên job/step thì không đoán được lá hiếm (license, git, buildconfig gần như
không trùng), nên tên chỉ được lưu để tham khảo.

    python -m project3.pipeline.probe_repos calibrate
    python -m project3.pipeline.probe_repos probe --pool data/processed/repos_pool_r2.txt
    python -m project3.pipeline.probe_repos select --target 100 --out configs/repos_r2.txt
"""
import argparse
import json
import random
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

from project3.crawl.gha import AGG_JOB, error_context, pick_jobs
from project3.crawl.github import GitHub, load_token
from project3.crawl.gold_labels import NON_BUILD_WF, gold_label
from project3.pilot.fine_labels import subtype

# Lá hiếm (≤ ~1.200 commit trên 100 repo đầu) và từ khoá trong tên job / step fail. Thứ tự = ưu tiên.
HINTS = {
    "license": r"\brat\b|licen[cs]e|header|spdx|copyright",
    "compatibility": r"revapi|japicmp|compat|api[ -]?(check|dump|diff|compat)|metalava|binary|mima|clirr|breaking",
    "doc": r"javadoc|dokka|\bdocs?\b|documentation|\bsite\b|asciidoc",
    "androidsdk": r"android|emulator|\bavd\b|instrument",
    "dependency": r"dependenc|\bdeps?\b|resolve|bom\b|enforcer|convergence|owasp|vulnerab",
    "buildconfig": r"validate (pom|build)|wrapper|toolchain|gradle (config|validation)|pom",
    "git": r"checkout|\bgit\b|submodule|clone",
}
HINT_RE = {k: re.compile(v, re.I) for k, v in HINTS.items()}
# trọng số lá = sqrt(11.704 / số commit lá đó trên 100 repo đầu), testfailure = 1; lá không phải lỗi = 0
CURRENT = {"testfailure": 11704, "quality": 5593, "itestfailure": 4983, "compile": 4516, "crash": 1538,
           "dependency": 1146, "network": 1103, "license": 216, "buildconfig": 143, "git": 107, "flaky": 61,
           "doc": 52, "compatibility": 42, "androidsdk": 5}
WEIGHT = {k: (11704 / v) ** 0.5 for k, v in CURRENT.items()}
RARE = ["license", "compatibility", "doc", "androidsdk", "dependency", "buildconfig", "git", "flaky"]
CRAWLED = [Path("data/crawl_pr"), Path("data/validate")]
CACHE = Path("data/processed/repo_probe_r2.jsonl")


def hint(job: dict) -> str | None:
    """Lá hiếm đoán từ tên job và tên các step fail của job (None nếu không gợi ý gì)."""
    text = " ".join([job["name"]] + [s["name"] for s in job.get("steps", []) if s["conclusion"] == "failure"])
    return next((k for k, r in HINT_RE.items() if r.search(text)), None)


def run_hints(jobs: list[dict]) -> set[str]:
    return {h for j in jobs if j["conclusion"] == "failure" and (h := hint(j))}


def calibrate() -> None:
    """Trên repo đã crawl: tỉ lệ run fail có gợi ý từng lá so với số commit có lá đó thật (theo repo)."""
    real = duckdb.sql("""SELECT repository, label_l3, count(*) n FROM 'data/dataset/commits.parquet'
        WHERE label_l3 IS NOT NULL GROUP BY ALL""").fetchall()
    real_n = Counter()
    for repo, leaf, n in real:
        real_n[repo, leaf] += n
    rows = []
    for root in CRAWLED:
        for d in root.iterdir():
            f = d / "jobs.jsonl"
            if not f.exists():
                continue
            repo = d.name.replace("__", "/", 1)
            c, nfail = Counter(), 0
            for line in f.open(encoding="utf-8"):
                jobs = json.loads(line)["jobs"]
                if any(j["conclusion"] == "failure" for j in jobs):
                    nfail += 1
                    c.update(run_hints(jobs))
            rows.append((repo, nfail, c))
    by_repo = {}
    for repo, nfail, c in rows:
        a = by_repo.setdefault(repo, [0, Counter()])
        a[0] += nfail
        a[1].update(c)
    print(f"{len(by_repo)} repo đã crawl. Với từng lá: repo có gợi ý ≥ 2% run fail vs repo có ≥ 5 commit lá đó thật")
    for leaf in HINTS:
        pred = {r for r, (n, c) in by_repo.items() if n and c[leaf] / n >= 0.02}
        true = {r for r in by_repo if real_n[r, leaf] >= 5}
        tp = len(pred & true)
        yield_pred = sum(real_n[r, leaf] for r in pred)
        yield_rest = sum(real_n[r, leaf] for r in set(by_repo) - pred)
        print(f"  {leaf:14s} gợi ý {len(pred):3d} repo, thật {len(true):3d}, trùng {tp:3d} | "
              f"commit lá thật: repo có gợi ý {yield_pred / max(len(pred), 1):6.1f}/repo, "
              f"repo không {yield_rest / max(len(by_repo) - len(pred), 1):5.1f}/repo")


def probe_leaf(gh: GitHub, repo: str, run: dict) -> tuple[str, set[str]]:
    """Lá tầng 3 của một run fail theo quy tắc (từ log 1 job fail) và gợi ý từ tên."""
    jobs = gh.get(f"/repos/{repo}/actions/runs/{run['id']}/jobs", per_page=100, filter="latest")["jobs"]
    hints = run_hints(jobs)
    picked = pick_jobs(jobs, 1)
    if not picked:
        return "(không có job fail)", hints
    text = gh.get_log_tail(f"/repos/{repo}/actions/jobs/{picked[0]['id']}/logs", tail_bytes=128_000)
    if text is None:
        return "(không có log)", hints
    label, ev = gold_label([error_context(text)])
    if label in ("?", "non_build"):
        return label, hints
    names = " ".join(j["name"] for j in jobs if j["conclusion"] == "failure" and not AGG_JOB.search(j["name"]))
    return subtype(label, ev, run["name"] or "", names) or label, hints


def probe(pool: Path, n_runs: int, days: int, workers: int) -> None:
    repos = [l.strip() for l in pool.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    done = {json.loads(l)["repository"] for l in CACHE.open(encoding="utf-8")} if CACHE.exists() else set()
    gh = GitHub(load_token())
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    todo = [r for r in repos if r not in done]
    print(f"probe {len(todo)} repo (đã có {len(done)}), ~{len(todo) * (2 * n_runs + 1)} request", flush=True)

    def one(repo: str) -> dict:
        row = {"repository": repo}
        try:
            runs = gh.get(f"/repos/{repo}/actions/runs", per_page=100, status="failure", created=f">={since}")
            row["fail_runs_90d"] = runs.get("total_count", 0)
            build = [r for r in runs["workflow_runs"] if not NON_BUILD_WF.search(r["name"] or "")]
            sample = random.Random(repo).sample(build, min(n_runs, len(build)))
            leaves, c, wf = Counter(), Counter(), Counter()
            for r in sample:
                leaf, hints = probe_leaf(gh, repo, r)
                leaves[leaf] += 1
                c.update(hints)
                wf[r["name"]] += 1
            row.update(sampled=len(sample), leaves=dict(leaves), hints=dict(c), workflows=dict(wf.most_common(5)))
        except Exception as e:
            row["error"] = str(e)[:160]
        return row

    # log tải chậm (~5 s/job) nên chạy song song theo repo; giới hạn vẫn là 5.000 request/giờ của token
    with CACHE.open("a", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=workers) as ex:
        for i, row in enumerate(ex.map(one, todo), 1):
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            if i % 10 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)} {row['repository']} {row.get('leaves')} (còn {gh.remaining} request)",
                      flush=True)


def select(target: int, table: Path, out: Path, max_per_org: int) -> None:
    rows = [json.loads(l) for l in CACHE.open(encoding="utf-8")]
    meta = {r["repository"]: r for r in duckdb.sql(f"SELECT * FROM read_csv('{table.as_posix()}')").df()
            .to_dict("records")}
    scored = []
    for r in rows:
        if r.get("error") or r.get("sampled", 0) < 10:  # quá ít run mẫu thì tỉ lệ lá không tin được
            continue
        share = {k: v / r["sampled"] for k, v in r["leaves"].items()}
        fails = min(r["fail_runs_90d"], 3000)  # tránh repo khổng lồ lấn át
        # điểm = số run fail/90 ngày ước tính rơi vào từng lá, nhân trọng số nghịch với số commit lá đó đang có
        score = sum(WEIGHT.get(k, 0) * s for k, s in share.items()) * fails ** 0.5
        scored.append({**r, "score": round(score, 2), "share": {k: round(v, 2) for k, v in share.items()},
                       "language": meta.get(r["repository"], {}).get("language")})
    scored.sort(key=lambda r: -r["score"])
    per_org, chosen = Counter(), []
    for r in scored:
        org = r["repository"].split("/")[0]
        if len(chosen) < target and per_org[org] < max_per_org and r["fail_runs_90d"] >= 30:
            chosen.append(r)
            per_org[org] += 1
    Path(str(out) + ".csv").write_text("repository,score,fail_runs_90d,language,share\n" + "\n".join(
        f'{r["repository"]},{r["score"]},{r["fail_runs_90d"]},{r["language"]},"{json.dumps(r["share"])}"'
        for r in chosen) + "\n", encoding="utf-8")
    chosen.sort(key=lambda r: r["fail_runs_90d"])  # repo nhỏ trước: hết giờ vẫn được nhiều repo
    out.write_text(f"# Đợt crawl 2 ({datetime.now():%d/%m/%Y}): {len(chosen)} repo chọn bằng "
                   "project3.pipeline.probe_repos, ưu tiên lá tầng 3 hiếm. Điểm từng repo: " + out.name + ".csv\n"
                   + "\n".join(r["repository"] for r in chosen) + "\n", encoding="utf-8")
    tot = Counter()
    for r in chosen:
        for k, v in r["share"].items():
            tot[k] += v * min(r["fail_runs_90d"], 3000)
    print(f"chọn {len(chosen)}/{len(scored)} repo; run fail ước tính có gợi ý theo lá: "
          f"{ {k: int(v) for k, v in tot.most_common()} }")
    print("theo tổ chức:", dict(per_org.most_common(8)))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("calibrate")
    p = sub.add_parser("probe")
    p.add_argument("--pool", type=Path, default=Path("data/processed/repos_pool_r2.txt"))
    p.add_argument("--runs", type=int, default=15)
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--days", type=int, default=90)
    s = sub.add_parser("select")
    s.add_argument("--target", type=int, default=100)
    s.add_argument("--table", type=Path, default=Path("data/processed/repo_selection_r2.csv"))
    s.add_argument("--out", type=Path, default=Path("configs/repos_r2.txt"))
    s.add_argument("--max-per-org", type=int, default=10)
    a = ap.parse_args()
    if a.cmd == "calibrate":
        calibrate()
    elif a.cmd == "probe":
        probe(a.pool, a.runs, a.days, a.workers)
    else:
        select(a.target, a.table, a.out, a.max_per_org)
