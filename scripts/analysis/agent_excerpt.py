"""Đoạn trích log cho agent truy vết (14/11/2026): cắt từ LOG ĐẦY ĐỦ thay vì từ error_context.

Dữ liệu huấn luyện chỉ lưu error_context (crawl/gha.py: 80 dòng trước ##[error] đầu .. 5 dòng sau ##[error] cuối), nên
thông báo gốc nằm xa hơn (vd ERR_PNPM_OUTDATED_LOCKFILE trước stack trace Maven) bị mất trước cả bước chọn đoạn.
Khi dùng thật luôn có log đầy đủ -> đoạn trích cho agent tách khỏi đầu vào mô hình phân loại (không huấn luyện lại).

Cách mới = đúng bộ cắt + chọn hiện có (run_dataset.chunk_log, inputs.chunk_score/select_chunks/focus_window 'split',
pack.MAX_CHUNKS = 8), chỉ đổi nguồn: log đầy đủ (data/results/rca_agent/ctx/<run>/A/log.txt) thay error_context.

Đo (CPU, không gọi API): "chuỗi then chốt" = đoạn trong backtick ở nguyên nhân của câu trả lời được LLM chấm "đúng"
(cách 1 và 3), dài >= 8 ký tự và có trong log đầy đủ. Tỉ lệ chuỗi then chốt có trong đoạn trích cũ / mới.

    python scripts/analysis/agent_excerpt.py   # -> data/results/rca_agent/excerpt_v2/
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd

from project3.model.inputs import chunk_score, focus_window, select_chunks
from project3.model.pack import MAX_CHUNKS
from project3.pipeline.run_dataset import chunk_log, clean

OUT = Path("data/results/rca_agent")
JOB = re.compile(r"^===== job: (.*) \(id (\d+)\) =====$", re.M)
TICK = re.compile(r"`([^`\n]{8,200})`")


def split_jobs(log: str) -> list:
    """log.txt của agent = các job lỗi nối nhau, mỗi job mở đầu bằng dòng '===== job: ... ====='."""
    heads = list(JOB.finditer(log))
    return [log[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(log)] for i, h in enumerate(heads)] or [log]


# Quy tắc riêng cho lỗi test (người dùng duyệt 14/11/2026): thêm stack trace của tối đa MAX_TESTS test lỗi đầu tiên,
# mỗi trace tối đa TRACE_LINES dòng, luôn giữ chuỗi `Caused by` tới nguyên nhân gốc.
# Chi tiết em tự đặt thêm: giữ AT_TOP dòng `at` đầu của ngoại lệ ngoài cùng, 1 dòng `at` sau mỗi `Caused by`;
# quá TRACE_LINES dòng thì bỏ dòng ở giữa (giữ phần đầu + phần cuối, nơi có nguyên nhân gốc).
MAX_TESTS, TRACE_LINES, AT_TOP = 3, 15, 3
# Maven surefire/failsafe: "<Class>.<method> -- Time elapsed ... <<< ERROR!" hoặc "<method>(<Class>) ... <<< FAILURE!"
# (bỏ dòng tổng kết "Tests run: ..."); Gradle: "<Class> > <method>() FAILED";
# Gradle test lồng nhau (JUnit5 @Nested, Kotest): dòng thụt đầu kết thúc bằng FAILED; Android: "... FAILED " (dấu cách cuối)
# Python unittest: "FAIL: test_x (mod.Class...)"; pytest: "____ Class.test_x ____"
# Bảng tổng hợp của action báo cáo test: "<path>.kt:340 | <ngoại lệ>" (mỗi dòng là một test, không có trace)
# (bổ sung 14/11 sau khi kiểm tra 214 run / 113 repo ngoài mẫu agent: data/results/agent_excerpt_holdout)
_HEAD = re.compile(r"^(?:\[ERROR\] )?\S.*<<< (?:FAILURE|ERROR)!|^\S.* > .*\bFAILED\s*$|^\s+\S.*\sFAILED\s*$")
REPORT = re.compile(r"^\S+\.(?:java|kt|kts|scala|groovy):\d+ \| \S")
PY_UNIT = re.compile(r"^(?:FAIL|ERROR): \S+ \(")
PY_TEST = re.compile(r"^_{3,} \S.* _{3,}$")
PY_SEP = re.compile(r"^(?:={5,}|-{5,})")
PY_KEEP = re.compile(r"^E |^>|^\S+\.py:\d+: ")  # pytest: dòng lỗi E, dòng code gây lỗi >, vị trí file:dòng


def head_kind(line: str):
    # "> Task :x FAILED" là task Gradle, không phải test (có thể bị fastlane thêm tiền tố "[giờ]: ▸ "; sửa 14/11 sau
    # vòng 2 vì là nhận nhầm, chỉ làm giảm số khối test; các dạng còn sót ở vòng 2 KHÔNG thêm để giữ vòng 2 độc lập)
    if _HEAD.search(line) and "Tests run:" not in line and "> Task :" not in line:
        return "jvm"
    if REPORT.match(line):
        return "report"
    if PY_UNIT.match(line):
        return "unittest"
    if PY_TEST.match(line):
        return "pytest"
    return None


def is_head(line: str) -> bool:
    return head_kind(line) is not None


AT = re.compile(r"^\s+at |^\s+\.\.\. \d+ more")
CAUSE = re.compile(r"^\s*(?:Caused by|Suppressed): ")
STOP = re.compile(r"^\[(?:INFO|WARNING|ERROR)\]|^##\[|^> Task |^\s*\S.* (?:STARTED|PASSED|SKIPPED)\s*$")  # dòng trống: bỏ qua (có log xen dòng trống)


def test_traces(lines: list) -> list:
    """[(dòng tiêu đề, [dòng trace đã rút gọn])] cho tối đa MAX_TESTS test lỗi đầu tiên (lines đã clean)."""
    out, i = [], 0
    while i < len(lines) and len(out) < MAX_TESTS:
        if not is_head(lines[i]):
            i += 1
            continue
        head, kind, body, j = lines[i], head_kind(lines[i]), [], i + 1
        if kind == "report":  # một dòng đã đủ: file:dòng | ngoại lệ
            out.append((head, []))
            i = j
            continue
        while j < len(lines) and len(body) < 400:
            ln = lines[j]
            if not ln.strip():
                j += 1
                continue
            if is_head(ln):
                break
            if kind == "jvm" and STOP.match(ln) and not CAUSE.match(ln):
                break
            if kind != "jvm" and PY_SEP.match(ln):
                if body:  # unittest: "-----" ngay sau tiêu đề thì bỏ qua; gặp lại thì hết test
                    break
                j += 1
                continue
            body.append(ln)
            j += 1
        if kind == "pytest":
            keep = [ln for ln in body if PY_KEEP.match(ln)]
        elif kind == "unittest":  # Traceback Python: nguyên nhân ở CUỐI -> giữ hết, cắt giữa nếu dài
            keep = body
        else:
            keep, at_left = [], AT_TOP
            for ln in body:
                if CAUSE.match(ln):
                    keep.append(ln)
                    at_left = 1
                elif AT.match(ln):
                    if at_left > 0 and not ln.strip().startswith("..."):
                        keep.append(ln)
                        at_left -= 1
                else:  # dòng ngoại lệ / thông báo (assert expected/actual)
                    keep.append(ln)
        if len(keep) > TRACE_LINES:
            keep = keep[:TRACE_LINES // 2] + ["    [...]"] + keep[-(TRACE_LINES - TRACE_LINES // 2 - 1):]
        out.append((head, keep))
        i = j
    return out


def _select(texts: list) -> list:
    """[(job, step, đoạn đã cắt focus_window)] theo bộ chọn của mô hình (8 đoạn, cửa sổ 1600 ký tự)."""
    jobs = [chunk_log(t) for t in texts]
    scores = [[chunk_score(c["text"], ci == len(j) - 1) for ci, c in enumerate(j)] for j in jobs]
    return [(ji, jobs[ji][ci]["step"], focus_window(jobs[ji][ci]["text"], 1600, "split"))
            for ji, ci in select_chunks(scores, MAX_CHUNKS)]


def excerpt_v2(log: str, tests: bool = True) -> str:
    """Đoạn trích cho agent = (a) đúng phần mô hình phân loại đọc (error_context -> chọn đoạn), (b) đoạn chọn thêm từ
    log đầy đủ mà (a) chưa có, (c) stack trace test lỗi. (a) đứng đầu nên không bao giờ kém đoạn trích cũ
    (14/11: chỉ dùng (b) làm mất dòng bằng chứng ở 12/214 run của repo ngoài mẫu)."""
    from project3.crawl.gha import error_context
    texts = split_jobs(log)
    keep = [k for k, t in enumerate(texts) if chunk_log(t)]
    texts = [texts[k] for k in keep]
    old = _select([error_context(t) for t in texts])
    seen = " ".join(norm(x) for _, _, x in old)
    extra = [(ji, st, x) for ji, st, x in _select(texts) if norm(x).strip() not in seen]
    parts = [f"===== excerpt {k + 1} (job {ji + 1}, step: {st[:120]}) =====\n{x}" for k, (ji, st, x) in enumerate(old)]
    parts += [f"===== more from full log {k + 1} (job {ji + 1}, step: {st[:120]}) =====\n{x}"
              for k, (ji, st, x) in enumerate(extra)]
    if tests:
        for n, k in enumerate(keep):
            tr = test_traces([clean(x) for x in texts[k].splitlines()])
            if tr:
                parts.append(f"===== failing tests (job {n + 1}): first {len(tr)} =====\n" +
                             "\n\n".join(h + "\n" + "\n".join(b) for h, b in tr))
    return "\n\n".join(parts)


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", "\n".join(clean(x) for x in t.splitlines()))


def main() -> None:
    s = pd.read_csv(OUT / "scores.csv").drop_duplicates(["run_id", "cond"])
    (OUT / "excerpt_v2").mkdir(exist_ok=True)
    rows = []
    for rid, g in s.groupby("run_id"):
        base = OUT / "ctx" / str(rid)
        full = (base / "A" / "log.txt").read_text(encoding="utf-8")
        old = (base / "B" / "log_excerpt.txt").read_text(encoding="utf-8")
        new = excerpt_v2(full)
        (OUT / "excerpt_v2" / f"{rid}.txt").write_text(new, encoding="utf-8")
        nf, no, nn = norm(full), norm(old), norm(new)
        keys = set()
        for cond in ("A", "C"):
            if (g[g.cond == cond].judge == "correct").any():
                rec = json.loads((OUT / "runs" / f"{rid}_{cond}.json").read_text(encoding="utf-8"))
                txt = ((rec.get("out") or {}).get("structured_output") or {}).get("root_cause", "")
                keys |= {k for k in (norm(x).strip() for x in TICK.findall(txt)) if len(k) >= 8 and k in nf}
        rows.append(dict(run_id=rid, leaf=g.leaf.iloc[0], full_k=len(full) / 1e3, old_k=len(old) / 1e3,
                         new_k=len(new) / 1e3, n_key=len(keys), old_hit=sum(k in no for k in keys),
                         new_hit=sum(k in nn for k in keys)))
    d = pd.DataFrame(rows)
    d.to_csv(OUT / "excerpt_v2" / "coverage.csv", index=False)
    k = d[d.n_key > 0]
    print(f"run có chuỗi then chốt: {len(k)}/{len(d)}; tổng chuỗi {k.n_key.sum()}")
    print(f"độ dài đoạn trích (nghìn ký tự, trung vị): cũ {d.old_k.median():.1f}  mới {d.new_k.median():.1f}")
    print(f"chuỗi then chốt có trong đoạn trích: cũ {k.old_hit.sum() / k.n_key.sum():.1%}  mới {k.new_hit.sum() / k.n_key.sum():.1%}")
    print(f"run có ít nhất 1 chuỗi: cũ {(k.old_hit > 0).mean():.1%}  mới {(k.new_hit > 0).mean():.1%}")
    k = k.assign(old_r=k.old_hit / k.n_key, new_r=k.new_hit / k.n_key)
    print(k.groupby("leaf")[["n_key", "old_r", "new_r"]].agg({"n_key": "sum", "old_r": "mean", "new_r": "mean"}).round(2))
    print(k.sort_values("new_r")[["run_id", "leaf", "n_key", "old_hit", "new_hit", "old_k", "new_k"]].head(15).to_string())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
