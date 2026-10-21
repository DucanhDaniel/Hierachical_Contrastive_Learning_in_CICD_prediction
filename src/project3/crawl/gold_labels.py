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

from .validate_labels import step_label

RULE_VERSION = "2026-10-18-dependency-q1q3"
FALLBACK_RULES_PATH = Path(__file__).resolve().parents[3] / "configs" / "label_rules.json"


def load_fallback_rules():
    """(label, regex, guard) của lớp dự phòng và (regex, guard) của lớp Q3 (`layer: q3_override`, 18/10/2026)."""
    data = json.loads(FALLBACK_RULES_PATH.read_text(encoding="utf-8"))
    if data["rule_version"] != RULE_VERSION:
        raise ValueError("Fallback rule version mismatch")
    rules = [r for r in sorted(data["rules"], key=lambda r: r["priority"]) if r.get("enabled", True)]
    return ([(r["label"], re.compile(r["regex"], re.M), r.get("guard")) for r in rules if r.get("layer") != "q3_override"],
            [(re.compile(r["regex"], re.M), r.get("guard")) for r in rules if r.get("layer") == "q3_override"])


FALLBACK_RULES, Q3_RULES = load_fallback_rules()

AGG_JOB = re.compile(r"CI result|checks? completed|-required|required checks", re.I)
# Workflow không phải build/test của code (tự động cherry-pick, cập nhật catalog...) -> loại khỏi dữ liệu
NON_BUILD_WF = re.compile(r"cherry-pick|backport|test catalog|catalog update|docker official image|publish|release|"
                          r"Pinot Dependencies|CVE|Trivy|security scan|Security Analysis|zizmor|PR Title|title check|"
                          r"labeler|size label|first.?interaction|greetings|benchmark|PR labels|dependency review|Dependency Submission", re.I)

# Lỗi javadoc có cùng dạng `Foo.java:42: error: ...` như javac nhưng là kiểm tra tài liệu (Rausch: doc) -> lint (15/10/2026,
# người duyệt). Các thông báo dưới đây chỉ javadoc in ra; trước đó 76 run javadoc bị gán compile.
DOC_KINDS = (r"reference not found|unknown tag|malformed HTML|unexpected end tag|self-closing element|element not closed|"
             r"unexpected text|exception not thrown|@param name not found|unterminated inline tag|heading used out of sequence|"
             r"invalid use of @return|semicolon missing|bad HTML entity|bad use of")
GOLD_RULES = [
    # buildconfig (Rausch: cấu hình build sai, vd. pom.xml lỗi) là giai đoạn sớm nhất: Maven/Gradle đọc cấu hình trước mọi
    # bước khác. Chỉ tín hiệu chắc chắn; dòng tổng kết "The build could not read N project" không đủ (15/10/2026, người duyệt).
    ("buildconfig", r"\[ERROR\]\s+'(?:dependencies\.dependency|build\.plugins\.plugin|dependencyManagement\.dependencies\.dependency)"
                    r"\.[\w().:]{1,60}' (?:for \S{1,200} is missing|must be unique|must be a valid version)|"
                    r"Non-parseable POM|Malformed POM|Non-readable POM|Could not find the selected project in the reactor|"
                    r"Could not compile (?:build|settings) file|Script compilation errors?:"),
    ("compile", r"COMPILATION ERROR|Compilation failure|Compilation failed|error: cannot find symbol|"
                r"\.java:\[?\d+[,\]:](?! error: (?:" + DOC_KINDS + r")).*error|error: (incompatible types|method does not override)|"
                r"error TS\d+|SyntaxError: invalid syntax|"
                r"^.*\[(?:ERROR|Error)\].*\.scala:\d+:|^.*e: (?:file://)?\S+\.kt:\d+:\d+"),
    ("lint", r"\.java:\d+: error: (?:" + DOC_KINDS + r")|You have [1-9]\d* Checkstyle violations?|spotless\w*Check FAILED|Spotless.*violations|"
             r"The following files had format violations|Too many files with unapproved license|Unapproved: [1-9]|"
             r"Rat check failed|(flake8|mypy|ruff|isort|black) checks\.\.\. \[FAILED\]|would reformat|"
             r"Found [1-9]\d* errors?\b.*ruff|Counter\(s\) UNAPPROVED exceeded|"
             r"Execution failed for task ':[^']*(?:checkstyle\w*|spotless\w*Check)'|"
             r"License header (?:is missing|missing|mismatch)|"
             r"(?:revapi|japicmp)[^\n]*(?:API changes|incompatible|compatibility check failed)|"
             r"(?:API|Binary|binary) (?:incompatibilities|incompatibility) (?:found|detected)|"
             r"E: There is at least one incompatibility:"),
    # Resolve thất bại chưa chứng minh lỗi mạng hay artifact không tồn tại.
    ("resolution", r"Non-resolvable (parent|import) POM|Could not transfer artifact|Could not resolve dependencies|"
                   r"Could not resolve all (files|dependencies)|Failed to read artifact descriptor|could not be resolved|"
                   r"Unresolveable build extension"),
    ("infra", r"Failed to download|has timed out after|"
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
    ("dependency", r"Could not find artifact|Could not find [\w.\-]+:[\w.\-]+:[\w.\-]+|"
                   r"was not found in https?://|No plugin found for prefix"),
    # Hạ tầng "yếu": lỗi kết nối chỉ tính khi log không có dấu hiệu test fail.
    ("infra", r"Connection reset|Connection refused|Read timed out|Connection timed out"),
]


# Lỗi tải thư viện do mạng / repo (Maven Central 429, 503, mất kết nối) -> infra.
# Còn "Could not find artifact" (404, artifact không tồn tại, vd. commit nâng lên version chưa phát hành) -> dependency.
NETWORK = re.compile(r"(?:status code[: ]+|error code[: ]+|HTTP[/\d.]*\s+)(?:401|403|408|429|50[0-9])\b|"
                     r"Connection (reset|refused|timed out)|Read timed out|Unknown host|"
                     r"Transfer failed|PKIX|Too Many Requests|Service Unavailable|Bad Gateway|"
                     r"Premature end of Content-Length|SSLHandshakeException|Remote host terminated the handshake")
MISSING_ARTIFACT = re.compile(r"Could not find artifact|Could not find [\w.\-]+:[\w.\-]+:[\w.\-]+|"
                              r"was not found in https?://|No plugin found for prefix")


def diagnostic_text(text: str) -> str:
    """Bỏ phần Actions echo lệnh/env; nội dung grep trong script không phải lỗi thật."""
    text = re.sub(r'\x1b\[[0-9;]*m', '', text)
    lines, command = [], False
    for line in text.splitlines():
        line = re.sub(r"^\S+Z ", "", line)
        if line.startswith("##[group]Run "):
            command = True
        elif command and line.startswith("##[endgroup]"):
            command = False
        elif not command:
            lines.append(line)
    return "\n".join(lines)


def evidence_line(text: str, match: re.Match) -> str:
    end = text.find("\n", match.end())
    return text[max(0, text.rfind("\n", 0, match.start()) + 1):
                end if end >= 0 else len(text)].strip()[:200]


def resolution_context(text: str, match: re.Match) -> str:
    # Maven in nguyên nhân dưới summary, kết thúc tại [Help]; Gradle in cây cause.
    lines = text[match.start():].splitlines()[:30]
    context = []
    for line in lines:
        if re.search(r"\[Help \d+\]|^\[ERROR\]\s*$|^\s*\* Try:", line):
            break
        context.append(line)
    return "\n".join(context)


def _base(jobs: list[str]) -> tuple[str, str, int | None]:
    """Nhãn lõi kèm chỉ số job quyết định (None khi `?`)."""
    unresolved = ""
    for lab, pat in GOLD_RULES:
        for j, text in enumerate(jobs):
            for m in re.finditer(pat, text, re.M):
                if lab == "resolution":
                    context = resolution_context(text, m)
                    network = NETWORK.search(context)
                    missing = MISSING_ARTIFACT.search(context)
                    if network:
                        return "infra", evidence_line(context, network), j
                    if missing:
                        return "dependency", evidence_line(context, missing), j
                    unresolved = unresolved or evidence_line(text, m)
                    continue
                if lab == "dependency":
                    context = resolution_context(text, m)
                    network = NETWORK.search(context)
                    if network:
                        return "infra", evidence_line(context, network), j
                return lab, evidence_line(text, m), j
    return "?", unresolved, None


def base_gold_label(texts: list[str]) -> tuple[str, str]:
    # Giữ nguyên ưu tiên run, nhưng không ghép nguyên nhân của hai job khác nhau.
    label, evidence, _ = _base([diagnostic_text(text) for text in texts])
    return label, evidence


def guard_ok(guard: str | None, text: str, match: re.Match) -> bool:
    """Điều kiện kèm quy tắc (rà soát dependency 18/10/2026, docs/codex/ra-soat-dependency-2026-10-18.md)."""
    if not guard:
        return True
    context = resolution_context(text, match)
    if guard == "no_network":
        return not NETWORK.search(context)
    if guard == "network_context":
        return bool(NETWORK.search(context))
    if guard == "missing_artifact_context":
        return not NETWORK.search(context) and "Searched in the following locations" in context
    if guard == "plugin_missing_context":
        return not NETWORK.search(context) and bool(re.search(
            r"Could not find|Searched in the following locations|(?:status code[: ]{1,8}|HTTP[/\d.]{0,10}\s{1,8})404\b", context))
    if guard == "missing_class_failure":
        # NoClassDefFoundError -> ClassNotFoundException cùng lớp là nguyên nhân cuối, ngay trước BUILD FAILED / test lỗi
        following = "\n".join(text[match.start():].splitlines()[:60])
        cause = re.search(r"Caused by: java\.lang\.ClassNotFoundException: " + re.escape(match.group(1).replace("/", "."))
                          + r"(?:\s|$)", following)
        if not cause:
            return False
        tail = "\n".join(following[cause.end():].splitlines()[:30])
        return "Caused by:" not in tail and bool(re.search(r"BUILD FAILED|<<< (?:ERROR|FAILURE)!", tail))
    if guard == "failure_context":
        before = "\n".join(text[:match.start()].splitlines()[-20:])
        return bool(re.search(r"Exception in thread|<<< (?:ERROR|FAILURE)!|Failed to execute goal|Execution failed for task|"
                              r"FAILURE: Build failed", before + context))
    raise ValueError(f"guard không hỗ trợ: {guard}")


def first_match(pattern: re.Pattern, guard: str | None, text: str) -> re.Match | None:
    for m in (pattern.finditer(text) if guard else [pattern.search(text)]):
        if m and guard_ok(guard, text, m):
            return m
    return None


def gold_label(texts: list[str]) -> tuple[str, str]:
    jobs = [diagnostic_text(text) for text in texts]
    label, evidence, job = _base(jobs)
    if label == "?":
        for lab, pattern, guard in FALLBACK_RULES:
            hit = next(((j, m) for j, text in enumerate(jobs) if (m := first_match(pattern, guard, text))), None)
            if hit:
                label, evidence, job = lab, evidence_line(jobs[hit[0]], hit[1]), hit[0]
                break
    # Q3 (người duyệt 18/10/2026): lệch phiên bản JDK / xung đột thư viện là dependency theo nguyên nhân gốc. Chỉ ghi đè
    # compile/test khi chính job quyết định có tín hiệu, hoặc `?` khi job bất kỳ có; mọi nhãn khác giữ nguyên.
    if label in ("compile", "test", "?"):
        indices = range(len(jobs)) if label == "?" else [job]
        for pattern, guard in Q3_RULES:
            for j in indices:
                if m := first_match(pattern, guard, jobs[j]):
                    return "dependency", evidence_line(jobs[j], m)
    return label, evidence


SLOW_RUN_SECONDS = 10  # một run lâu hơn mức này thì in cảnh báo kèm run_id


def main(root: Path) -> None:
    import faulthandler
    import time
    rows = []
    dirs = sorted(p for p in root.iterdir() if p.is_dir() and (p / "jobs.jsonl").exists())
    t_root = time.time()
    for k, d in enumerate(dirs, 1):
        t_repo, n_before = time.time(), len(rows)
        print(f"[{time.strftime('%H:%M:%S')}] {root} {k}/{len(dirs)} {d.name} ...", flush=True)
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
            # regex kẹt (backtracking) giữ GIL nên chỉ faulthandler (luồng C) in được: cứ 60s in stack ra stderr
            faulthandler.dump_traceback_later(60, repeat=True, file=sys.__stderr__)
            t_run = time.time()
            try:
                g, ev = gold_label(texts) if texts else ("(không có log)", "")
            finally:
                faulthandler.cancel_dump_traceback_later()
            if time.time() - t_run > SLOW_RUN_SECONDS:
                print(f"    CHẬM: run {row['run_id']} mất {time.time() - t_run:.0f}s "
                      f"({sum(map(len, texts)) // 1024} KB log)", flush=True)
            non_build = non_build or g == "non_build"
            s, tier = step_label(row["jobs"])
            rows.append({"repo": d.name.replace("__", "/"), "run_id": row["run_id"], "workflow": run["name"],
                         "non_build": non_build, "step_label": s, "gold": g, "evidence": ev})
        print(f"    {len(rows) - n_before} run fail, {time.time() - t_repo:.0f}s "
              f"(tổng {(time.time() - t_root) / 60:.1f} phút)", flush=True)
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
