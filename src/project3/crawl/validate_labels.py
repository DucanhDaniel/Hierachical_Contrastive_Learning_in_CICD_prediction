"""Kiểm chứng nhãn gán theo tên step (cách dùng cho GHARuns) bằng log thật của run mới.

So nhãn theo tên step/job với nhãn suy từ các dòng lỗi trong log, xuất bảng đối chiếu và file mẫu để xem tay.

    uv run python -m project3.crawl.validate_labels data/validate
"""
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

from .analyze import AGGREGATOR
from .gharuns_label import INFRA_STEP, rule_label

# Dấu hiệu lỗi trong log (Maven/Gradle/Java, Python). Xét theo thứ tự: hạ tầng/dependency → compile → lint → test.
# Dòng chung chung "Process completed with exit code N" không đủ để kết luận -> "?".
LOG_RULES = [
    ("infra", r"ETIMEDOUT|ECONNRESET|Connection (reset|refused|timed out)|Could not (resolve|transfer|collect) "
              r"(artifact|dependencies)|Failed to read artifact descriptor|could not be resolved|Could not acquire shared lock|"
              r"Read timed out|No space left on device|runner has received a shutdown|The operation was canceled|"
              r"rate limit|503 Service Unavailable|TLS handshake timeout|Unable to download|Failed to download|"
              r"Could not GET|lost communication with the server|exit code 137|OutOfMemoryError: Java heap|"
              r"problems were encountered while processing the POMs"),
    ("compile", r"COMPILATION ERROR|Compilation failure|cannot find symbol|error: \S+ is not|incompatible types|"
                r"Execution failed for task ':[^']*compile|does not override|package \S+ does not exist|"
                r"error: cannot access|SyntaxError|error TS\d+|Could not compile"),
    ("lint", r"maven-checkstyle-plugin.*violation|You have \d+ Checkstyle violation|spotless:check|Spotless.*violations|"
             r"apache-rat.*(Too many|unapproved)|Rat check|license header|\bruff\b.*(error|Found)|flake8|pylint|mypy.*error|"
             r"would reformat|ktlint|scalastyle|scalafmt|forbiddenapis|PMD Failure|spotbugs.*BugInstance"),
    ("test", r"Tests run:.*(Failures: [1-9]|Errors: [1-9])|There (are|were) test failures|tests? (failed|FAILED)|"
             r"FAILED \S+Test|AssertionError|AssertionFailedError|expected:<|Test Suites: \d+ failed|\d+ failed,|"
             r"Execution failed for task ':[^']*test"),
]


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def step_label(jobs: list[dict]) -> tuple[str, str]:
    """Nhãn theo tên step fail rồi tên job fail – giống gharuns_label."""
    fjobs = [j for j in jobs if j["conclusion"] == "failure"]
    steps = [(j["name"], s["name"]) for j in fjobs for s in j["steps"] if s["conclusion"] == "failure"]
    steps = [(j, s) for j, s in steps if not AGGREGATOR.search(s) and not AGGREGATOR.search(j)] or steps
    if steps:
        labs = {rule_label(s) for _, s in steps if not INFRA_STEP.search(s)} - {None}
        if not labs:
            labs = {rule_label(j) for j, s in steps if not INFRA_STEP.search(s)} - {None}
        if labs:
            return ("+".join(sorted(labs)) if len(labs) > 1 else next(iter(labs))), "step"
        if any(INFRA_STEP.search(s) for _, s in steps):
            return "infra", "step"
    names = [j["name"] for j in fjobs if not AGGREGATOR.search(j["name"])] or [j["name"] for j in fjobs]
    labs = {rule_label(n) for n in names} - {None}
    if labs:
        return ("+".join(sorted(labs)) if len(labs) > 1 else next(iter(labs))), "job"
    return "?", "none"


def log_label(texts: list[str]) -> tuple[str, str]:
    """Nhãn theo dòng lỗi trong log; trả kèm 3 dòng ##[error] / dòng lỗi đầu tiên để xem tay."""
    joined = "\n".join(texts)
    errors = [re.sub(r"^\S+Z ", "", l).strip() for l in joined.splitlines() if "##[error]" in l or "[ERROR]" in l]
    for lab, pat in LOG_RULES:
        if re.search(pat, joined, re.M):
            return lab, " | ".join(errors[:3])[:300]
    return "?", " | ".join(errors[:3])[:300]


def main(root: Path) -> None:
    rows = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        runs = {r["id"]: r for r in load_jsonl(d / "runs.jsonl")}
        for row in load_jsonl(d / "jobs.jsonl"):
            run = runs.get(row["run_id"])
            if not run or run["conclusion"] != "failure":
                continue
            s_lab, tier = step_label(row["jobs"])
            texts = [(d / "logs" / f"{j['id']}.txt").read_text(encoding="utf-8", errors="ignore")
                     for j in row["jobs"] if j["conclusion"] == "failure" and (d / "logs" / f"{j['id']}.txt").exists()]
            l_lab, err = log_label(texts) if texts else ("(không có log)", "")
            fstep = next((f"{j['name']} › {s['name']}" for j in row["jobs"] if j["conclusion"] == "failure"
                          for s in j["steps"] if s["conclusion"] == "failure"), "")
            rows.append({"repo": d.name.replace("__", "/"), "run_id": row["run_id"], "workflow": run["name"],
                         "failed_step": fstep[:120], "step_label": s_lab, "tier": tier, "log_label": l_lab,
                         "agree": s_lab.split("+")[0] == l_lab if l_lab not in ("?", "(không có log)") else None,
                         "error_lines": err})
    print(f"Run fail: {len(rows)}")
    print("Nhãn theo step:", dict(Counter(r["step_label"] for r in rows).most_common()))
    print("Nhãn theo log :", dict(Counter(r["log_label"] for r in rows).most_common()))
    cmp_rows = [r for r in rows if r["agree"] is not None]
    if cmp_rows:
        agree = sum(r["agree"] for r in cmp_rows)
        print(f"Trùng khớp (trên {len(cmp_rows)} run có nhãn từ log): {agree} ({agree / len(cmp_rows):.0%})")
        conf = Counter((r["step_label"], r["log_label"]) for r in cmp_rows)
        print("Bảng đối chiếu (step → log):")
        for (a, b), n in conf.most_common():
            print(f"   {a:12s} → {b:10s} {n}")
    out = root / "label_check.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) + ["nhan_dung_tay"])
        w.writeheader()
        for r in rows:
            w.writerow({**r, "nhan_dung_tay": ""})
    print(f"Đã lưu {out} (cột nhan_dung_tay để điền khi xem tay)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "data/validate"))
