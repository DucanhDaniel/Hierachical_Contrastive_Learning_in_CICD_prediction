"""Thống kê dữ liệu crawl + thử gán nhãn loại lỗi (tên step → tên job → regex log).

    uv run python -m project3.crawl.analyze data/raw/apache__superset data/raw/apache__airflow
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

LABELS = ["compile", "test", "lint", "dependency", "infra"]

# Tầng 1-2: tên step / tên job
NAME_RULES = [
    ("lint", r"lint|pre-commit|prettier|eslint|ruff|mypy|static.?check|checkstyle|spotless|format|type.?check|spell|"
             r"license|rudolint|openrewrite"),
    # test đứng trước compile: "build / JUnit tests" là lỗi test, không phải compile
    ("test", r"test|junit|pytest|jest|spec\b|e2e|cypress|playwright|coverage|integration"),
    ("compile", r"\bbuild\b|compil|tsc|webpack|bundle|image build|docker build|packaging"),
    ("dependency", r"install|dependenc|requirement|npm ci|pip |uv sync|poetry|setup (python|node)|constraints"),
    ("infra", r"checkout|upload|artifact|login|cache|set up job|complete job|post "),
]
# Job/step chỉ tổng hợp kết quả của job khác, không phải nguyên nhân gốc
AGGREGATOR = re.compile(r"checks? completed|-required$|required checks|result$|all checks|ci success|gate$", re.I)
# Tầng 3: regex trên phần cuối log
LOG_RULES = [
    ("infra", r"ETIMEDOUT|ECONNRESET|Connection reset|rate limit|No space left on device|runner has received a shutdown|"
              r"The operation was canceled|Could not connect|503 Service Unavailable|TLS handshake timeout"),
    ("dependency", r"Could not resolve dependencies|npm ERR! (code )?(E404|ERESOLVE)|No matching distribution|"
                   r"ResolutionImpossible|ModuleNotFoundError|Cannot find module|version solving failed"),
    ("compile", r"error TS\d+|SyntaxError|COMPILATION ERROR|error: cannot find symbol|Failed to compile|ImportError"),
    ("lint", r"would reformat|Found \d+ errors?|eslint|prettier|ruff|mypy|pre-commit hook|Failed\s*$|- hook id:"),
    ("test", r"\d+ failed|FAILED |AssertionError|Tests:\s+\d+ failed|Test Suites: \d+ failed|Error: expect\("),
]


def by_rules(text: str, rules) -> str | None:
    t = text.lower() if rules is NAME_RULES else text
    for lab, pat in rules:
        if re.search(pat, t, 0 if rules is NAME_RULES else re.M):
            return lab
    return None


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def analyze(d: Path) -> None:
    runs = load_jsonl(d / "runs.jsonl")
    jobs = {row["run_id"]: row["jobs"] for row in load_jsonl(d / "jobs.jsonl")}
    wf_names = {w["id"]: w["name"] for w in json.loads((d / "workflows.json").read_text(encoding="utf-8"))}
    log_dir = d / "logs"
    print(f"\n######## {d.name}: {len(runs)} run")
    if not runs:
        return
    print("conclusion:", dict(Counter(r["conclusion"] for r in runs).most_common()))
    print("event     :", dict(Counter(r["event"] for r in runs).most_common()))
    pf = [r for r in runs if r["conclusion"] in ("success", "failure")]
    fail = [r for r in pf if r["conclusion"] == "failure"]
    print(f"pass/fail: {len(pf)} run, fail {len(fail)} ({len(fail)/max(1,len(pf)):.1%}); chạy lại (attempt>1): "
          f"{sum(1 for r in runs if (r['run_attempt'] or 1) > 1)}")

    # Theo workflow
    per_wf = defaultdict(Counter)
    for r in pf:
        per_wf[wf_names.get(r["workflow_id"], r["name"])][r["conclusion"]] += 1
    print("Top workflow (success/failure):")
    for name, c in sorted(per_wf.items(), key=lambda x: -sum(x[1].values()))[:10]:
        print(f"   {name[:50]:50s} {c['success']:5d} / {c['failure']:4d}")

    # Parrot: theo (workflow, branch) và theo (workflow) trên nhánh mặc định push
    def parrot(key):
        seqs = defaultdict(list)
        for r in sorted(pf, key=lambda r: r["created_at"]):
            k = key(r)
            if k:
                seqs[k].append(r["conclusion"])
        pairs = [(a, b) for s in seqs.values() for a, b in zip(s, s[1:])]
        if not pairs:
            return "không đủ cặp"
        same = sum(a == b for a, b in pairs)
        first = sum(a == "success" and b == "failure" for a, b in pairs)
        nfail = sum(b == "failure" for _, b in pairs)
        return (f"{len(pairs)} cặp, giống lần trước {same/len(pairs):.0%}, lần fail đầu (pass→fail) {first}"
                f" / {nfail} fail ({first/max(1,nfail):.0%})")
    print("Parrot (workflow+branch):", parrot(lambda r: (r["workflow_id"], r["head_branch"])))
    print("Parrot (workflow, chỉ push):", parrot(lambda r: r["workflow_id"] if r["event"] == "push" else None))

    # Gán nhãn loại lỗi cho từng run fail
    tiers = Counter()
    labels = Counter()
    failed_steps = Counter()
    failed_jobs = Counter()
    have_log = missing_log = 0
    for r in fail:
        js = [j for j in jobs.get(r["id"], []) if j["conclusion"] == "failure"]
        lab = tier = None
        for j in js:
            failed_jobs[j["name"][:55]] += 1
            for s in j["steps"]:
                if s["conclusion"] == "failure":
                    failed_steps[s["name"][:55]] += 1
                    lab = lab or by_rules(s["name"], NAME_RULES)
                    if lab and not tier:
                        tier = "1-step"
        if not lab:
            for j in js:
                lab = lab or by_rules(j["name"], NAME_RULES)
            tier = "2-job" if lab else None
        if not lab:
            for j in js:
                f = log_dir / f"{j['id']}.txt"
                if f.exists():
                    lab = lab or by_rules(f.read_text(encoding="utf-8", errors="ignore"), LOG_RULES)
            tier = "3-log" if lab else None
        for j in js:
            have_log += (log_dir / f"{j['id']}.txt").exists()
            missing_log += (log_dir / f"{j['id']}.missing").exists()
        if not js:
            tier = "không có job fail" if r["id"] in jobs else "chưa crawl job"
        tiers[tier or "chưa gán được"] += 1
        labels[lab or "?"] += 1
    print(f"Gán nhãn {len(fail)} run fail theo tầng:", dict(tiers.most_common()))
    print("Phân bố nhãn:", dict(labels.most_common()))
    print(f"Log job fail: có {have_log}, đã hết hạn {missing_log}")
    print("Step fail hay gặp:", failed_steps.most_common(8))
    print("Job fail hay gặp :", failed_jobs.most_common(8))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for p in sys.argv[1:]:
        analyze(Path(p))
