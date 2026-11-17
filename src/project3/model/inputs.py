"""Đầu vào mô hình theo cây nhãn (27/10/2026, góp ý GVHD 23/10: cách chia đầu vào phải gắn với tầng nhãn):

  khối log lỗi  -> tầng 3 (loại lỗi):    chọn đoạn theo dấu hiệu fail (goal/task fail, dòng lỗi), không theo vị trí cuối log
  thông tin CI  -> tầng 2 (khi nào sửa):  giai đoạn của công cụ fail (goal Maven / task Gradle) và của tên step fail
  tóm tắt diff  -> tầng 1 (dự án / môi trường CI): commit đổi loại file nào, bao nhiêu

Mọi đặc trưng ở đây KHÔNG dùng nhãn hay dòng bằng chứng của quy tắc (khác crawl.stages.run_axes, vốn lấy giai đoạn từ lá).
Đặc trưng log tính trên văn bản đã che (`mask_text`) cho bản test che, nên không rò dòng bằng chứng.
"""
import gzip
import math
import re

import numpy as np

STAGES = ("setup", "prepare", "compile", "check", "test", "itest", "package")  # = crawl.stages.STAGES

# dòng có dấu hiệu lỗi, không phụ thuộc loại lỗi (gần với từ khoá của LogSage)
ERR = re.compile(r"error|fail|exception|cannot|could not|unable to|not found|denied|timed? ?out|killed|refused|"
                 r"What went wrong|Caused by|BUILD FAILURE|\bFAILED\b|^e: ", re.I | re.M)
FAIL_LINE = re.compile(r"Failed to execute goal|Execution failed for task|^> Task \S+ FAILED|BUILD FAILURE|"
                       r"What went wrong|COMPILATION ERROR|Tests run: \d+.*FAIL|tests completed, \d+ failed|"
                       r"##\[error\]", re.M)

STAGE_SLOTS = list(STAGES) + ["none"]
STRUCT_NAMES = ([f"tool_{s}" for s in STAGE_SLOTS] + [f"step_{s}" for s in STAGE_SLOTS]
                + ["tool_maven", "tool_gradle", "n_tools", "n_failed_jobs", "governance", "fail_lines"])

DIFF_KINDS = ["main", "test", "build", "ci", "doc", "other"]
DIFF_NAMES = [f"diff_{k}" for k in DIFF_KINDS] + ["diff_files", "diff_added", "diff_deleted", "has_diff", "is_pr"]

_TEST = re.compile(r"(?:^|/)(?:src/)?(?:test|tests|androidTest|testFixtures|integration-?tests?|it|e2e)(?:/|$)|"
                   r"Tests?\.(?:java|kt|scala|groovy)$|IT\.(?:java|kt)$|Spec\.(?:groovy|kt)$", re.I)
_BUILD = re.compile(r"(?:^|/)(?:pom\.xml|build\.gradle(?:\.kts)?|settings\.gradle(?:\.kts)?|gradle\.properties|"
                    r"[\w.\-]*\.versions\.toml|gradle-wrapper\.properties|gradlew(?:\.bat)?|mvnw(?:\.cmd)?|"
                    r"build\.sbt|Makefile|Dockerfile|proguard[\w.\-]*\.(?:pro|txt)|lint\.xml)$|(?:^|/)(?:\.mvn|buildSrc|"
                    r"build-logic|gradle)/", re.I)
_CI = re.compile(r"^\.github/|^\.circleci/|\.gitlab-ci\.yml$|^Jenkinsfile|^\.travis\.yml$|^azure-pipelines", re.I)
_DOC = re.compile(r"\.(?:md|rst|adoc|txt|html?)$|(?:^|/)(?:docs?|site|website)/|^(?:LICENSE|NOTICE|CHANGELOG)", re.I)
_CODE = re.compile(r"\.(?:java|kt|kts|scala|groovy|aidl|proto|xml|properties|ya?ml|json|sql|js|ts|py|sh|c|cc|cpp|h)$",
                   re.I)


def chunk_score(text: str, last_in_job: bool) -> float:
    """Điểm chọn đoạn (văn bản đã che): dòng báo fail của công cụ > mật độ dòng lỗi > vị trí cuối job."""
    fail = len(FAIL_LINE.findall(text))
    err = len(ERR.findall(text))
    return 5.0 * min(fail, 2) + 2.0 * min(err, 6) / 6 + 1.0 * last_in_job


def select_chunks(scores_by_job: list, max_chunks: int) -> list:
    """Chọn (job, đoạn): mỗi job lấy đoạn điểm cao nhất (job có điểm cao trước), phần còn lại lấy theo điểm toàn run.
    Hoà điểm thì ưu tiên đoạn sau (gần cuối log). Trả về theo thứ tự gốc."""
    best = [(s[c], c, j) for j, s in enumerate(scores_by_job) if s for c in [max(range(len(s)), key=lambda c: (s[c], c))]]
    picked = {(j, c) for _, c, j in sorted(best, reverse=True)[:max_chunks]}
    rest = sorted(((s[c], c, j) for j, s in enumerate(scores_by_job) for c in range(len(s)) if (j, c) not in picked),
                  reverse=True)
    picked |= {(j, c) for _, c, j in rest[: max_chunks - len(picked)]}
    return sorted(picked)


def focus_window(text: str, n: int = 1600, mode: str = "last") -> str:
    """Dòng đầu (ranh giới goal/task) + cửa sổ n ký tự quanh dòng báo lỗi của đoạn; không có dòng lỗi thì lấy phần cuối
    như clip_chunk. Log ≈ 3,1 ký tự/token UniXcoder: n = 1600 dùng với 512 token.
    mode `last`: quanh dòng lỗi CUỐI (lùi 2/3 về trước; 28/10, giữ dòng bằng chứng ở 83% run).
    mode `split` (30/10): Maven/Gradle in lỗi thật TRƯỚC dòng tổng kết cuối (BUILD FAILURE, Failed to execute goal), nên
    lấy nửa quanh dòng lỗi ĐẦU + nửa quanh dòng lỗi cuối; hai dòng đủ gần thì một cửa sổ liền từ dòng đầu (90%)."""
    first, _, rest = text.partition("\n")
    head = first[:200] + "\n"
    if len(rest) <= n:
        return first[:200] + ("\n" + rest if rest else "")
    hits = [m.start() for m in FAIL_LINE.finditer(rest)] or [m.start() for m in ERR.finditer(rest)]
    if not hits:
        return head + rest[-n:]
    cut = lambda c, m, before: rest[max(0, min(c - before, len(rest) - m)):][:m]
    if mode == "last":
        return head + cut(hits[-1], n, 2 * n // 3)
    if hits[-1] - hits[0] <= n - n // 3:
        return head + cut(hits[0], n, n // 3)
    return head + cut(hits[0], n // 2, n // 6) + "\n" + cut(hits[-1], n // 2, n // 3)


def _onehot(stage):
    v = [0.0] * len(STAGE_SLOTS)
    v[STAGE_SLOTS.index(stage) if stage in STAGE_SLOTS else -1] = 1.0
    return v


def struct_features(texts: list, step_names: list, kinds: list, n_failed_jobs: int) -> list:
    """Đặc trưng "hỏng ở bước nào" của một run, từ các đoạn log (đã che nếu là bản che) và tên step fail.
    Chỉ chạy ở máy local lúc đóng gói (cần project3.crawl, không có trong project3_code.pyz)."""
    from project3.crawl.stages import GOVERNANCE, earliest, failed_tools, step_stage
    tools = [t for x in texts for t in failed_tools(x)]
    names = [n for n in step_names if n]
    kind = " ".join(kinds)
    return (_onehot(earliest(s for _, s in tools)) + _onehot(step_stage(names))
            + [float("maven" in kind), float("gradle" in kind), math.log1p(len(tools)), math.log1p(n_failed_jobs),
               float(any(GOVERNANCE.search(n) for n in names)),
               math.log1p(sum(len(FAIL_LINE.findall(x)) for x in texts))])


def file_kind(path: str) -> str:
    if _CI.search(path):
        return "ci"
    if _BUILD.search(path):
        return "build"
    if _DOC.search(path):
        return "doc"
    if _TEST.search(path):
        return "test"
    return "main" if _CODE.search(path) else "other"


def diff_features(path, event: str) -> list:
    """Tóm tắt diff: tỉ lệ file theo loại, log(1+số file / dòng thêm / dòng xoá), có diff, PR hay push."""
    files, add, rem = [], 0, 0
    if path:
        try:
            with gzip.open(path, "rt", encoding="utf-8", errors="replace") if str(path).endswith(".gz") \
                    else open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.startswith("diff --git "):
                        files.append(line.rstrip("\n").split(" b/", 1)[-1])
                    elif line.startswith("+") and not line.startswith("+++"):
                        add += 1
                    elif line.startswith("-") and not line.startswith("---"):
                        rem += 1
        except OSError:
            files = []
    n = len(files)
    cnt = {k: 0 for k in DIFF_KINDS}
    for p in files:
        cnt[file_kind(p)] += 1
    return ([cnt[k] / n if n else 0.0 for k in DIFF_KINDS]
            + [math.log1p(n), math.log1p(add), math.log1p(rem), float(n > 0), float(event == "pull_request")])


def as_matrix(rows) -> np.ndarray:
    return np.asarray(list(rows), dtype=np.float32)


# ---- dòng nguyên nhân (15/11/2026, người dùng duyệt): nhãn cho đầu dòng nguyên nhân (train --cause-loss) ----
# Lá test (testfailure, itestfailure, flaky): dòng ngoại lệ / assert của test lỗi + dòng `Caused by` CUỐI mỗi chuỗi
# (nguyên nhân gốc). Lá khác: dòng bằng chứng của quy tắc nếu nó không phải dòng tổng kết của công cụ.
# Chỉ xét các dòng nằm trong đầu vào của mô hình (đoạn đã cắt cửa sổ).
CAUSE_TEST_LEAVES = {"testfailure", "itestfailure", "flaky"}
SUMMARY = re.compile(r"BUILD FAILURE|BUILD FAILED|Failed to execute goal|Execution failed for task|What went wrong|"
                     r"##\[error\]Process completed|There were failing tests|Tests run:|tests completed, \d+ failed|"
                     r"> Task \S+ FAILED|COMPILATION ERROR|Re-run Maven|for more information about the errors|"
                     r"See the report at|Run with --(?:stacktrace|scan|info)|\[Help 1\]|Tests in error|"
                     r"\[ERROR\] (?:Failures|Errors):\s*$")
EXC_LINE = re.compile(r"^\s*(?:##\[error\])?\s*(?:(?:[a-zA-Z_$][\w$]*\.)+[A-Z][\w$]*(?:Exception|Error|Failure|Failed|"
                      r"Throwable)\b|\w*(?:Error|Exception): |E\s{2,}\S)|expected:?\s*<.*>\s*but was|expected .+ but was")
# danh sách test lỗi cuối lượt Maven surefire: "[ERROR]   Lớp.phươngthức:89->assertX:37 <thông báo>" / "Run 2: ... » Lỗi"
SUREFIRE_ITEM = re.compile(r"^\[ERROR\]\s{2,}(?:Run \d+: )?\S+[.>#]\S+:\d+\S*\s+\S")
CAUSED_BY = re.compile(r"^\s*Caused by: ")
TRACE_CONT = re.compile(r"^\s+at |^\s+\.\.\. \d+ more|^\s*$")


def cause_line_ids(lines: list, leaf: str, ev_key: str = "") -> list:
    """Chỉ số các dòng nguyên nhân trong một đoạn log (danh sách dòng)."""
    if leaf in CAUSE_TEST_LEAVES:
        out, pending = [], None
        for i, ln in enumerate(lines):
            if CAUSED_BY.match(ln):
                pending = i  # giữ Caused by cuối của chuỗi
            elif TRACE_CONT.match(ln):
                continue
            else:
                if pending is not None:
                    out.append(pending)
                    pending = None
                if (EXC_LINE.search(ln) or SUREFIRE_ITEM.match(ln)) and not SUMMARY.search(ln):
                    out.append(i)
        if pending is not None:
            out.append(pending)
        return out
    if ev_key and not SUMMARY.search(ev_key):
        return [i for i, ln in enumerate(lines) if ev_key in ln]
    return []
