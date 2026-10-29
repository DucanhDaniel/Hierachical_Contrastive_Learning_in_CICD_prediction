"""Chọn workflow cho đợt crawl 3 (22/10/2026): nhắm thẳng vào workflow chạy công cụ sinh ra lá tầng 3 hiếm.

Đợt 2 (probe_repos) lấy mẫu ngẫu nhiên 15 run fail/repo nên lá rất hiếm (compatibility, androidsdk, doc, flaky) gần như
không lộ ra. Ở đây tìm file workflow nhắc tới công cụ của từng lá bằng code search (`path:.github/workflows`), rồi đếm
run fail 90 ngày của chính workflow đó (1 request/workflow). Bước `sample` lấy vài run fail của workflow đứng đầu,
tải log 1 job và gán nhãn bằng chính bộ quy tắc để ước tính tỉ lệ lá hiếm thật.

    python -m project3.pipeline.probe_rare search          # -> data/processed/rare_search.jsonl
    python -m project3.pipeline.probe_rare count           # -> data/processed/rare_count.jsonl
    python -m project3.pipeline.probe_rare sample --top 150 --runs 6   # -> data/processed/rare_sample.jsonl
    python -m project3.pipeline.probe_rare select --out configs/targets_r3.jsonl
    # đợt android (25/10/2026): cùng các bước, tệp data/processed/android_*.jsonl
    python -m project3.pipeline.probe_rare --set android search | count
    python -m project3.pipeline.probe_rare --set android select --out configs/targets_android.jsonl --max-runs 200
"""
import argparse
import json
import random
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from project3.crawl.fine_labels import subtype
from project3.crawl.gha import AGG_JOB, EXCLUDE, error_context
from project3.crawl.github import GitHub, load_token
from project3.crawl.gold_labels import NON_BUILD_WF, gold_label

# lá -> từ khoá tìm trong file workflow. Chỉ công cụ mà bộ quy tắc hiện hành nhận ra được (vd. apiCheck của
# binary-compatibility-validator không khớp quy tắc compatibility nên không tìm).
QUERIES = {
    "compatibility": ["japicmp", "revapi", "metalava", "clirr"],
    "androidsdk": ["android-emulator-runner", "sdkmanager", "setup-android", "avdmanager"],
    "license": ["apache-rat", "rat:check", "license:check", "license-maven-plugin", "checkLicense", "licenseMain"],
    "doc": ["javadoc:javadoc", "javadoc:jar", "gradlew javadoc", "dokka", "doclint"],
    "flaky": ["rerunFailingTestsCount", "surefire.rerunFailingTestsCount"],
    "buildconfig": ["mvn validate", "validate-pom", "gradle/wrapper-validation-action", "help:effective-pom"],
    "git": ["submodules: recursive", "git push"],
}
# đợt android (25/10/2026, góp ý GVHD: chọn lọc dự án Android thay vì crawl ngẫu nhiên): workflow build/test app Android.
# Với nhãn 2 trục (crawl.stages), Android bù các ô env×setup (SDK, emulator), code×itest (instrumentation) và check (lint).
ANDROID = {"android": ["android-emulator-runner", "connectedAndroidTest", "connectedCheck", "connectedDebugAndroidTest",
                       "setup-android", "assembleDebug", "testDebugUnitTest", "lintDebug", "bundleRelease"]}
SETS = {"rare": QUERIES, "android": ANDROID}
RARE = ["androidsdk", "compatibility", "flaky", "doc", "git", "buildconfig", "license"]
# số run có nhãn trên 200 repo hiện có (data/run_dataset/manifest.json, 19/10/2026) -> trọng số sqrt(18295 / n)
CURRENT = {"androidsdk": 2, "compatibility": 44, "flaky": 65, "doc": 158, "git": 286, "buildconfig": 345,
           "license": 421, "network": 2434, "crash": 2936, "dependency": 3514, "itestfailure": 8580,
           "quality": 8677, "compile": 10962, "testfailure": 18295}
WEIGHT = {k: (18295 / v) ** 0.5 for k, v in CURRENT.items()}
OUT = Path("data/processed")
SEARCH, COUNT, SAMPLE = OUT / "rare_search.jsonl", OUT / "rare_count.jsonl", OUT / "rare_sample.jsonl"


def use_set(name: str) -> dict:
    """Bộ truy vấn + tệp kết quả riêng cho từng đợt (rare: đợt 3 giữ tên tệp cũ)."""
    global SEARCH, COUNT, SAMPLE
    if name != "rare":
        SEARCH, COUNT, SAMPLE = (OUT / f"{name}_{k}.jsonl" for k in ("search", "count", "sample"))
    return SETS[name]
LANGS = {"Java", "Kotlin"}


def lines(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.open(encoding="utf-8")] if path.exists() else []


def crawled() -> set[str]:
    return {d.name.replace("__", "/", 1) for root in (Path("data/crawl_pr"), Path("data/validate"))
            if root.exists() for d in root.iterdir() if d.is_dir()}


def search(gh: GitHub, queries: dict) -> None:
    """Code search: mọi (repo, file workflow) khớp từ khoá; tối đa 1000 kết quả/truy vấn, 10 truy vấn/phút."""
    done = {(r["leaf"], r["query"]) for r in lines(SEARCH)}
    with SEARCH.open("a", encoding="utf-8") as f:
        for leaf, qs in queries.items():
            for q in qs:
                if (leaf, q) in done:
                    continue
                hits = {}
                for page in range(1, 11):
                    data = gh.get("/search/code", q=f'"{q}" path:.github/workflows', per_page=100, page=page)
                    time.sleep(6.5)  # giới hạn code search 10 request/phút
                    for it in data["items"]:
                        hits[it["repository"]["full_name"], it["path"]] = it["repository"]["fork"]
                    if len(data["items"]) < 100:
                        break
                print(f"{leaf:13s} {q!r}: {len(hits)} file (total_count={data['total_count']})", flush=True)
                f.write(json.dumps({"leaf": leaf, "query": q, "hits": [[r, p, fork] for (r, p), fork in hits.items()]},
                                   ensure_ascii=False) + "\n")
                f.flush()


def count(gh: GitHub, days: int, workers: int) -> None:
    """Số run fail trong `days` ngày của từng workflow ứng viên + ngôn ngữ repo (bỏ fork, repo đã crawl)."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    have = crawled()
    leaves = defaultdict(set)
    for r in lines(SEARCH):
        for repo, path, fork in r["hits"]:
            if not fork:
                leaves[repo, path].add(r["leaf"])
    done = {(r["repository"], r["path"]) for r in lines(COUNT)}
    todo = [k for k in leaves if k not in done]
    repo_meta = repo_languages(gh, sorted({r for r, _ in todo}))
    keep = [k for k in todo if repo_meta.get(k[0], {}).get("language") in LANGS
            and not repo_meta[k[0]].get("archived")]
    print(f"count {len(keep)}/{len(todo)} workflow Java/Kotlin (đã có {len(done)}), còn {gh.remaining} request",
          flush=True)

    def one(key: tuple[str, str]) -> dict:
        repo, path = key
        row = {"repository": repo, "path": path, "leaves": sorted(leaves[key]), "crawled": repo in have,
               **repo_meta[repo]}
        try:
            # endpoint nhận thẳng tên file workflow; run đầu tiên cho biết id + tên workflow
            runs = gh.get(f"/repos/{repo}/actions/workflows/{Path(path).name}/runs", status="failure",
                          created=f">={since}", per_page=1)
            row["fail_runs"] = runs["total_count"]
            if runs["workflow_runs"]:
                r0 = runs["workflow_runs"][0]
                row.update(workflow_id=r0["workflow_id"], name=r0["name"])
                if EXCLUDE.search(r0["name"] + " " + path) or NON_BUILD_WF.search(r0["name"]):
                    row["skip"] = "excluded"
                    del row["fail_runs"]
        except Exception as e:
            row["error"] = str(e)[:120]
        return row

    with COUNT.open("a", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=workers) as ex:
        for i, row in enumerate(ex.map(one, keep), 1):
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            if i % 100 == 0 or i == len(keep):
                print(f"  {i}/{len(keep)} (còn {gh.remaining} request)", flush=True)


def repo_languages(gh: GitHub, repos: list[str], batch: int = 50) -> dict:
    """Ngôn ngữ chính / archived / sao của nhiều repo qua GraphQL (một truy vấn cho `batch` repo)."""
    out = {}
    for i in range(0, len(repos), batch):
        part = repos[i:i + batch]
        q = " ".join(f'r{k}: repository(owner: {json.dumps(r.split("/")[0])}, name: {json.dumps(r.split("/")[1])}) '
                     "{ primaryLanguage { name } isArchived stargazerCount }" for k, r in enumerate(part))
        for attempt in range(3):
            resp = gh.s.post("https://api.github.com/graphql", json={"query": "{" + q + "}"}, timeout=60)
            if resp.status_code == 200:
                break
            time.sleep(10 * (attempt + 1))
        data = (resp.json().get("data") or {}) if resp.status_code == 200 else {}
        for k, r in enumerate(part):
            m = data.get(f"r{k}")  # None: repo đổi tên / bị xoá
            if m:
                out[r] = {"language": (m["primaryLanguage"] or {}).get("name"), "archived": m["isArchived"],
                          "stars": m["stargazerCount"]}
        if i // batch % 20 == 0:
            print(f"  graphql {i + len(part)}/{len(repos)} repo", flush=True)
    return out


def leaf_of(gh: GitHub, repo: str, run: dict) -> str:
    """Lá tầng 3 của một run fail theo quy tắc (log 1 job fail, ưu tiên job có tên khớp lá hiếm)."""
    jobs = gh.get(f"/repos/{repo}/actions/runs/{run['id']}/jobs", per_page=100, filter="latest")["jobs"]
    fail = [j for j in jobs if j["conclusion"] == "failure" and not AGG_JOB.search(j["name"])]
    if not fail:
        return "(không có job fail)"
    text = gh.get_log_tail(f"/repos/{repo}/actions/jobs/{fail[0]['id']}/logs", tail_bytes=128_000)
    if text is None:
        return "(không có log)"
    label, ev = gold_label([error_context(text)])
    if label in ("?", "non_build"):
        return label
    return subtype(label, ev, run["name"] or "", " ".join(j["name"] for j in fail)) or label


def sample(gh: GitHub, top: int, n_runs: int, days: int, workers: int) -> None:
    """Gán nhãn vài run fail của `top` workflow có nhiều run fail nhất (mỗi lá hiếm xét riêng, chưa crawl)."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = [r for r in lines(COUNT) if r.get("fail_runs", 0) >= 5 and not r["crawled"]]
    done = {(r["repository"], r["path"]) for r in lines(SAMPLE)}
    picked, per_leaf = [], Counter()
    # chia đều suất theo lá: lá hiếm nhất được chọn trước, mỗi lá tối đa top/len(RARE) workflow
    for leaf in RARE:
        cand = sorted((r for r in rows if leaf in r["leaves"]), key=lambda r: -min(r["fail_runs"], 500))
        for r in cand:
            if per_leaf[leaf] >= top // len(RARE):
                break
            if (r["repository"], r["path"]) not in done and r not in picked:
                picked.append(r)
                per_leaf[leaf] += 1
    print(f"sample {len(picked)} workflow × {n_runs} run: {dict(per_leaf)}", flush=True)

    def one(row: dict) -> dict:
        out = {k: row[k] for k in ("repository", "path", "workflow_id", "name", "leaves", "fail_runs", "crawled")}
        try:
            runs = gh.get(f"/repos/{row['repository']}/actions/workflows/{row['workflow_id']}/runs",
                          status="failure", created=f">={since}", per_page=100)["workflow_runs"]
            got = Counter(leaf_of(gh, row["repository"], r)
                          for r in random.Random(row["path"]).sample(runs, min(n_runs, len(runs))))
            out["sampled_leaves"] = dict(got)
        except Exception as e:
            out["error"] = str(e)[:120]
        return out

    with SAMPLE.open("a", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=workers) as ex:
        for i, row in enumerate(ex.map(one, picked), 1):
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            if i % 10 == 0 or i == len(picked):
                print(f"  {i}/{len(picked)} {row['repository']} {row.get('sampled_leaves')} (còn {gh.remaining})",
                      flush=True)


def summary() -> None:
    rows = lines(COUNT)
    ok = [r for r in rows if "fail_runs" in r]
    print(f"{len(rows)} workflow ứng viên, {len(ok)} đạt (Java/Kotlin, active, CI), "
          f"{len({r['repository'] for r in ok})} repo ({sum(r['crawled'] for r in ok)} workflow thuộc repo đã crawl)")
    for leaf in RARE:
        sel = [r for r in ok if leaf in r["leaves"]]
        print(f"  {leaf:13s} {len(sel):4d} workflow, ≥5 run fail: {sum(r['fail_runs'] >= 5 for r in sel):4d}, "
              f"tổng run fail 90 ngày {sum(min(r['fail_runs'], 500) for r in sel):6d}")
    s = lines(SAMPLE)
    if s:
        hit = Counter()
        for r in s:
            for k, v in r.get("sampled_leaves", {}).items():
                hit[k] += v
        print(f"mẫu {len(s)} workflow, {sum(hit.values())} run:", dict(hit.most_common()))


def select_android(out: Path, max_runs: int, min_fail: int, per_repo: int, top: int, min_stars: int) -> None:
    """Đợt android: không lấy mẫu trước (đợt 3 cho thấy mẫu 6 run/workflow ước tính kém); chọn workflow CI còn hoạt động
    có nhiều run fail nhất, tối đa `per_repo` workflow/repo, mỗi workflow ≤ max_runs run. Phân bố thật đo sau khi crawl.
    Lọc repo ≥ min_stars sao: không lọc thì phần lớn là repo cá nhân 0 sao build APK fail liên tục (nhiễu, không đại diện)."""
    rows = [r for r in lines(COUNT) if r.get("fail_runs", 0) >= min_fail and not r["crawled"] and "workflow_id" in r
            and (r.get("stars") or 0) >= min_stars]
    rows.sort(key=lambda r: -min(r["fail_runs"], max_runs))
    chosen, per = [], Counter()
    for r in rows:
        if per[r["repository"]] < per_repo:
            chosen.append({**r, "est_runs": min(r["fail_runs"], max_runs)})
            per[r["repository"]] += 1
        if len(chosen) >= top:
            break
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in chosen), encoding="utf-8")
    print(f"{len(rows)} workflow đạt (≥{min_fail} run fail, chưa crawl); chọn {len(chosen)} workflow / "
          f"{len(per)} repo, ~{sum(r['est_runs'] for r in chosen)} run fail cần crawl -> {out}")


def select(out: Path, max_runs: int) -> None:
    """Workflow sẽ crawl: điểm = số run fail × tỉ lệ lá hiếm trong mẫu (có trọng số nghịch với số mẫu hiện có)."""
    chosen = []
    for r in lines(SAMPLE):
        got = r.get("sampled_leaves") or {}
        n = sum(got.values())
        if not n or r["crawled"]:  # repo đã crawl 90 ngày: run fail của workflow này phần lớn đã có
            continue
        rare = {k: v / n for k, v in got.items() if k in RARE}
        score = sum(WEIGHT[k] * v for k, v in rare.items()) * min(r["fail_runs"], max_runs)
        if rare:
            chosen.append({**r, "rare_share": rare, "score": round(score, 1),
                           "est_rare_runs": round(sum(rare.values()) * min(r["fail_runs"], max_runs))})
    chosen.sort(key=lambda r: -r["score"])
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in chosen), encoding="utf-8")
    est = Counter()
    for r in chosen:
        for k, v in r["rare_share"].items():
            est[k] += v * min(r["fail_runs"], max_runs)
    print(f"{len(chosen)} workflow ({len({r['repository'] for r in chosen})} repo), "
          f"{sum(min(r['fail_runs'], max_runs) for r in chosen)} run fail cần crawl")
    print("ước tính run lá hiếm thêm được:", {k: int(v) for k, v in est.most_common()})


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=list(SETS), default="rare", help="bộ truy vấn: rare (đợt 3) | android")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("search")
    c = sub.add_parser("count")
    c.add_argument("--days", type=int, default=90)
    c.add_argument("--workers", type=int, default=8)
    s = sub.add_parser("sample")
    s.add_argument("--top", type=int, default=140)
    s.add_argument("--runs", type=int, default=6)
    s.add_argument("--days", type=int, default=90)
    s.add_argument("--workers", type=int, default=12)
    sub.add_parser("summary")
    sel = sub.add_parser("select")
    sel.add_argument("--out", type=Path, default=Path("configs/targets_r3.jsonl"))
    sel.add_argument("--max-runs", type=int, default=400)
    sel.add_argument("--min-fail", type=int, default=20, help="(android) số run fail 90 ngày tối thiểu")
    sel.add_argument("--per-repo", type=int, default=2, help="(android) số workflow tối đa mỗi repo")
    sel.add_argument("--top", type=int, default=40, help="(android) số workflow tối đa")
    sel.add_argument("--min-stars", type=int, default=50, help="(android) số sao tối thiểu của repo")
    a = ap.parse_args()
    queries = use_set(a.set)
    if a.cmd == "summary":
        summary()
    elif a.cmd == "select":
        select_android(a.out, a.max_runs, a.min_fail, a.per_repo, a.top, a.min_stars) if a.set == "android" else select(a.out, a.max_runs)
    else:
        gh = GitHub(load_token())
        if a.cmd == "search":
            search(gh, queries)
        elif a.cmd == "count":
            count(gh, a.days, a.workers)
        else:
            sample(gh, a.top, a.runs, a.days, a.workers)
