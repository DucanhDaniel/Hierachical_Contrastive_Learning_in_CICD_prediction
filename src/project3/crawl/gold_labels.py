"""Nhãn chuẩn (gold) từ log thật cho dữ liệu kiểm chứng, và so với nhãn gán theo tên step.

Luật đọc log được viết sau khi xem log thật của 6 repo (Druid, Gravitino, Kafka, Paimon, Pinot, Iceberg).
Thứ tự nguyên nhân gốc: compile → lint → infra → flaky → test. Job tổng hợp (CI result, Check ... Outcomes) bị bỏ qua.

    uv run python -m project3.crawl.gold_labels data/validate
"""
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

from .analyze import AGGREGATOR
from .validate_labels import step_label

AGG_JOB = re.compile(r"CI result|checks? completed|-required|required checks", re.I)
# Workflow không phải build/test của code (tự động cherry-pick, cập nhật catalog...) -> loại khỏi dữ liệu
NON_BUILD_WF = re.compile(r"cherry-pick|backport|test catalog|catalog update|docker official image|publish|release|"
                          r"Pinot Dependencies|CVE|Trivy|security scan|Security Analysis|zizmor|PR Title|title check|"
                          r"labeler|size label|first.?interaction|greetings|benchmark|PR labels|dependency review|Dependency Submission", re.I)

GOLD_RULES = [
    ("compile", r"COMPILATION ERROR|Compilation failure|Compilation failed|error: cannot find symbol|"
                r"\.java:\[?\d+[,\]:].*error|error: (incompatible types|method does not override)|"
                r"error TS\d+|SyntaxError: invalid syntax|"
                r"^.*\[(?:ERROR|Error)\].*\.scala:\d+:|^.*e: (?:file://)?\S+\.kt:\d+:\d+"),
    ("lint", r"You have [1-9]\d* Checkstyle violations?|spotless\w*Check FAILED|Spotless.*violations|"
             r"The following files had format violations|Too many files with unapproved license|Unapproved: [1-9]|"
             r"Rat check failed|(flake8|mypy|ruff|isort|black) checks\.\.\. \[FAILED\]|would reformat|"
             r"Found [1-9]\d* errors?\b.*ruff|Counter\(s\) UNAPPROVED exceeded|"
             r"Execution failed for task ':[^']*(?:checkstyle\w*|spotless\w*Check)'|"
             r"License header (?:is missing|missing|mismatch)|"
             r"(?:revapi|japicmp)[^\n]*(?:API changes|incompatible|compatibility check failed)|"
             r"(?:API|Binary|binary) (?:incompatibilities|incompatibility) (?:found|detected)|"
             r"E: There is at least one incompatibility:"),
    # Hạ tầng "mạnh": build/test chưa thể chạy (không tải được dependency/plugin, runner tắt, action timeout...)
    ("infra", r"Non-resolvable (parent|import) POM|Could not transfer artifact|Could not resolve dependencies|"
              r"Could not resolve all (files|dependencies)|Failed to read artifact descriptor|could not be resolved|"
              r"Unresolveable build extension|Failed to download|has timed out after|"
              r"No space left on device|lost communication with the server|runner has received a shutdown|"
              r"unable to access 'https://github.com|failed to push some refs|Could not acquire shared lock|"
              r"exit code 137|The operation was canceled|DevelocityException|Internal error in \S+ Maven extension|"
              r"Unable to download artifact|Artifact download failed|"
              r"Java setup process failed due to: error code: (?:429|50[234])|"
              r"Failed to resolve action download info|Gradle task had a timeout|"
              r"A fatal error has been detected by the Java Runtime Environment"),
    ("flaky", r"\b0 FAILED\b.*[1-9]\d* FLAKY|Flakes: [1-9]"),
    ("test", r"There are test failures|There were failing tests|Tests reported [1-9]\d* failures?|"
             r"\d+ tests completed, [1-9]\d* failed|=+ [1-9]\d* failed|FAILED \S+::|Test Suites: [1-9]\d* failed|"
             r"Tests run:.*(Failures: [1-9]|Errors: [1-9])|pytest checks\.\.\. \[FAILED\]|FAILED \(errors=[1-9]|"
             r"Execution failed for task ':[^']*([tT]est|integrationTest)'|Quickstart failed|\b[1-9]\d* FAILED\b|Found [1-9]\d* test failures|"
             r"Some tests completed with an Error|\d+ tests, \d+ passed, [1-9]\d* failed|"
             r"ERROR: Test execution of \S+ is FAILED"),
    # Artifact không tồn tại được xét riêng khi chưa có nguyên nhân test rõ ràng.
    ("dependency", r"Could not find artifact|was not found in https?://|No plugin found for prefix"),
    # Hạ tầng "yếu": lỗi kết nối chỉ tính khi log không có dấu hiệu test fail.
    ("infra", r"Connection reset|Connection refused|Read timed out|Connection timed out"),
]


# Lỗi tải thư viện do mạng / repo (Maven Central 429, 503, mất kết nối) -> infra.
# Còn "Could not find artifact" (404, artifact không tồn tại, vd. commit nâng lên version chưa phát hành) -> dependency.
NETWORK = re.compile(r"\b(429|50[234])\b|Connection (reset|refused|timed out)|Read timed out|Unknown host|"
                     r"Transfer failed|PKIX|Too Many Requests|Service Unavailable|Bad Gateway|"
                     r"Premature end of Content-Length|SSLHandshakeException|Remote host terminated the handshake")
MISSING_ARTIFACT = re.compile(r"Could not find artifact|was not found in https?://")


def gold_label(texts: list[str]) -> tuple[str, str]:
    joined = re.sub(r'\x1b\[[0-9;]*m', '', "\n".join(texts))
    for lab, pat in GOLD_RULES:
        m = re.search(pat, joined, re.M)
        if m:
            if lab == "infra" and MISSING_ARTIFACT.search(joined) and not NETWORK.search(joined):
                lab = "dependency"
            if lab == "dependency" and NETWORK.search(joined):
                lab = "infra"
            end = joined.find("\n", m.end())
            line = joined[max(0, joined.rfind("\n", 0, m.start()) + 1): end if end >= 0 else len(joined)]
            return lab, re.sub(r"^\S+Z ", "", line).strip()[:200]
    return "?", ""


def main(root: Path) -> None:
    rows = []
    for d in sorted(p for p in root.iterdir() if p.is_dir() and (p / "jobs.jsonl").exists()):
        runs = {r["id"]: r for r in map(json.loads, (d / "runs.jsonl").read_text(encoding="utf-8").splitlines())}
        for line in (d / "jobs.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            run = runs.get(row["run_id"])
            if not run or run["conclusion"] != "failure":
                continue
            non_build = bool(NON_BUILD_WF.search(run["name"] or ""))
            jobs = [j for j in row["jobs"] if j["conclusion"] == "failure" and not AGG_JOB.search(j["name"])]
            texts = [(d / "logs" / f"{j['id']}.txt").read_text(encoding="utf-8", errors="ignore")
                     for j in jobs if (d / "logs" / f"{j['id']}.txt").exists()]
            g, ev = gold_label(texts) if texts else ("(không có log)", "")
            s, tier = step_label(row["jobs"])
            rows.append({"repo": d.name.replace("__", "/"), "run_id": row["run_id"], "workflow": run["name"],
                         "non_build": non_build, "step_label": s, "gold": g, "evidence": ev})
    build = [r for r in rows if not r["non_build"]]
    print(f"Run fail: {len(rows)} (loại {len(rows) - len(build)} run của workflow không phải build)")
    print("Nhãn chuẩn từ log:", dict(Counter(r["gold"] for r in build).most_common()))
    ev = [r for r in build if r["gold"] not in ("?", "(không có log)")]
    norm = lambda s: s.split("+")[0] if s not in ("compile+test", "compile+lint") else "compile"
    ok = sum(norm(r["step_label"]) == r["gold"] for r in ev)
    print(f"Nhãn theo tên step đúng: {ok}/{len(ev)} ({ok / max(1, len(ev)):.0%})")
    print("Đối chiếu (theo tên step → nhãn chuẩn):")
    for (a, b), n in Counter((norm(r["step_label"]), r["gold"]) for r in ev).most_common():
        print(f"   {a:12s} → {b:8s} {n}{'' if a == b else '   ✘'}")
    out = root / "gold_labels.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["repo", "run_id", "workflow", "non_build", "step_label", "gold", "evidence"])
        w.writeheader()
        w.writerows(rows)
    print(f"Đã lưu {out}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "data/validate"))
