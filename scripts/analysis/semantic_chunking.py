"""Thử cách cắt log theo đơn vị ngữ nghĩa (10/11/2026, góp ý GVHD 05/11: không cắt đều) — chỉ đo, không đổi pipeline.

Dựng lại từng khối (step / goal Maven / task Gradle) từ data/run_dataset/chunks.parquet (cửa sổ 40 dòng chồng 5 dòng
-> bỏ 5 dòng đầu của mỗi cửa sổ sau), rồi cắt lại khối theo đơn vị:
  test case lỗi | stack trace (ngoại lệ + `at ...` + `Caused by:`) | mục lỗi của công cụ | phần còn lại theo khuôn dòng.
Giá trị tự đặt (đã báo người dùng 10/11): gộp đơn vị < MIN_LINES dòng với đơn vị kề trong cùng khối; mỗi đoạn tối đa
BUDGET ký tự (= cửa sổ mô hình đọc hiện nay); đơn vị dài hơn thì cắt ở ranh giới bên trong, mỗi mảnh sau giữ HEAD dòng
đầu của đơn vị. Biến thể `fill`: gộp tiếp tới khi đầy BUDGET (không cắt ngang đơn vị) — chỉ để đối chiếu.
Bản v2 (rechunk_v2): chỉ cắt lại khối dài hơn BUDGET, mỗi đoạn kèm PRE dòng trước nó.
Chọn đoạn giữ nguyên (chunk_score + select_chunks, 8 đoạn, focus_window 1600 split) để so sánh chỉ khác ở cách cắt.

    PYTHONPATH=src python scripts/analysis/semantic_chunking.py

Bản dùng để huấn luyện: project3.model.semantic (rechunk = rechunk_v2 ở đây, đã so 408 job: giống hệt;
select_first_fail giống hệt). Sửa cách cắt thì sửa ở đó.
"""
import re
from collections import defaultdict
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from project3.model.inputs import FAIL_LINE, chunk_score, focus_window, select_chunks
from project3.model.pack import MAX_CHUNKS
from project3.model.text import mask_text

OUT = Path("data/results/chunking")
MIN_LINES, BUDGET, HEAD, OVERLAP, PRE = 12, 1600, 3, 5, 5

TEST = re.compile(r"^\[ERROR\] Tests run: .*(?:FAILURE|ERROR)|^\[ERROR\]\s+[\w$.]+\.[\w$]+:\d+|^\S.* > .*\bFAILED$|"
                  r"^\[INFO\] Running [\w$.]+$|^Running [\w$.]+$|^\s*[✘×✗] |^FAIL\b")
EXC = re.compile(r"^(?:Exception in thread|[\w$.]+(?:Exception|Error|Throwable)\b(?::|$))")
CONT = re.compile(r"^\s+at |^\s*\.\.\. \d+ (?:more|common frames)|^\s*Caused by:|^\s*Suppressed:|^\s+[\w$.]+(?:Exception|Error)")
INNER = re.compile(r"^\s*Caused by:|^\s*Suppressed:")
TOOL = re.compile(r"^\* What went wrong:|^\[ERROR\] Failed to execute goal|COMPILATION ERROR|^FAILURE: Build failed|"
                  r"^\[ERROR\] Some problems were encountered|^e: |^Execution failed for task|^\[ERROR\] Errors?:\s*$|"
                  r"^\[ERROR\] Failures?:\s*$")
TOOL_END = re.compile(r"^\* Try:|\[Help \d+\]|^BUILD FAILED in|^\[INFO\] BUILD FAILURE")
TEMPLATE = re.compile(r"<ws>/\S*|https?://\S+|0x[0-9a-f]+|[0-9a-f]{12,}|\d+")


def blocks_of(job) -> list:
    """[(step, [dòng])] theo đúng thứ tự gốc."""
    out = []
    for c in job:
        lines = c.text.split("\n")
        if c.kind.endswith("+win") and out:
            out[-1][1].extend(lines[OVERLAP:])
        else:
            out.append((c.step_header, lines))
    return out


def units_of(lines: list) -> list:
    """Cắt một khối thành đơn vị ngữ nghĩa: [(kiểu, [dòng])]."""
    units, cur, kind = [], [], None
    tmpl = lambda s: TEMPLATE.sub("#", s)[:40]

    def push(new_kind):
        nonlocal cur, kind
        if cur:
            units.append((kind, cur))
        cur, kind = [], new_kind

    for ln in lines:
        if kind == "trace" and CONT.match(ln):
            cur.append(ln)
            continue
        if kind == "tool" and not TEST.match(ln) and not EXC.match(ln):
            cur.append(ln)
            if TOOL_END.search(ln):
                push(None)
            continue
        if TEST.match(ln):
            push("test")
        elif EXC.match(ln):
            push("trace")
        elif TOOL.search(ln):
            push("tool")
        elif kind == "test" and not EXC.match(ln):
            pass  # thân của test case (thông báo assert, log của test) tới khi gặp đơn vị khác
        elif kind != "other" or (cur and tmpl(ln) != tmpl(cur[-1]) and len(cur) >= MIN_LINES):
            push("other")
        cur.append(ln)
    push(None)
    return units


def size(lines):
    return sum(len(s) + 1 for s in lines)


def split_long(lines: list) -> list:
    """Đơn vị dài hơn BUDGET: cắt ở ranh giới bên trong (Caused by / Suppressed), không có thì theo dòng; mảnh sau giữ
    HEAD dòng đầu của đơn vị."""
    head = lines[:HEAD]
    pieces, cur = [], []
    for i, ln in enumerate(lines):
        if cur and (size(cur + [ln]) > BUDGET or (INNER.match(ln) and size(cur) > BUDGET // 2)):
            pieces.append(cur)
            cur = list(head) if i >= HEAD else []
        cur.append(ln)
    if cur:
        pieces.append(cur)
    return pieces


def pack_units(units: list, fill: bool) -> list:
    """Gộp đơn vị ngắn (< MIN_LINES dòng) với đơn vị kề, không vượt BUDGET; fill=True gộp tới khi đầy BUDGET."""
    out, cur = [], []
    for _, u in units:
        for piece in (split_long(u) if size(u) > BUDGET else [u]):
            if cur and size(cur + piece) <= BUDGET and (fill or len(cur) < MIN_LINES or len(piece) < MIN_LINES):
                cur = cur + piece
            else:
                if cur:
                    out.append(cur)
                cur = list(piece)
    if cur:
        out.append(cur)
    return out


def units_idx(lines: list) -> list:
    """Như units_of nhưng trả về vị trí bắt đầu của từng đơn vị trong khối: [(start, [dòng])]."""
    out, i = [], 0
    for _, u in units_of(lines):
        out.append((i, u))
        i += len(u)
    return out


def rechunk_v2(job) -> list:
    """Bản chỉnh 10/11 (người dùng duyệt): khối vừa BUDGET thì giữ nguyên; khối dài hơn mới cắt theo đơn vị ngữ nghĩa,
    và mỗi đoạn mở đầu bằng PRE dòng ngay trước nó (ngữ cảnh: đang chạy goal/test nào)."""
    out = []
    for step, lines in blocks_of(job):
        if size(lines) <= BUDGET:
            out.append("\n".join(lines))
            continue
        groups, cur = [], []
        for s0, u in units_idx(lines):
            pre = lines[max(0, s0 - PRE):s0]
            for k, piece in enumerate(split_long(u) if size(pre + u) > BUDGET else [u]):
                if cur and size(cur + piece) <= BUDGET and (len(cur) < MIN_LINES or len(piece) < MIN_LINES):
                    cur = cur + piece
                    continue
                if cur:
                    groups.append(cur)
                p0 = pre if k == 0 else []
                cur = (p0 + piece) if size(p0 + piece) <= BUDGET else list(piece)
        if cur:
            groups.append(cur)
        out += ["\n".join(g) for g in groups]
    return out


def rechunk(job, fill: bool) -> list:
    out = []
    for step, lines in blocks_of(job):
        for piece in pack_units(units_of(lines), fill):
            out.append("\n".join(piece))
    return out


def select_first_fail(masked: list, scores: list, max_chunks: int) -> list:
    """Hướng 1 (người dùng duyệt 10/11): mỗi job lỗi luôn có đoạn chứa dòng báo lỗi ĐẦU TIÊN (FAIL_LINE, trên văn bản
    đã che như select_chunks) — Maven/Gradle in lỗi thật trước dòng tổng kết. Job không có dòng như vậy thì lấy đoạn
    điểm cao nhất như cũ. Còn chỗ thì lấy theo điểm toàn run. Job nhiều hơn max_chunks: ưu tiên job có điểm cao."""
    forced = []
    for j, job in enumerate(masked):
        if not job:
            continue
        c = next((ci for ci, t in enumerate(job) if FAIL_LINE.search(t)), None)
        if c is None:
            c = max(range(len(job)), key=lambda ci: (scores[j][ci], ci))
        forced.append((scores[j][c], c, j))
    picked = {(j, c) for _, c, j in sorted(forced, reverse=True)[:max_chunks]}
    rest = sorted(((s[c], c, j) for j, s in enumerate(scores) for c in range(len(s)) if (j, c) not in picked),
                  reverse=True)
    picked |= {(j, c) for _, c, j in rest[: max_chunks - len(picked)]}
    return sorted(picked)


def measure(texts_by_job: list, k: str, first_fail: bool = False) -> dict:
    masked = [[mask_text(t, k) for t in job] for job in texts_by_job]
    scores = [[chunk_score(t, ci == len(job) - 1) for ci, t in enumerate(job)] for job in masked]
    sel = select_first_fail(masked, scores, MAX_CHUNKS) if first_fail else select_chunks(scores, MAX_CHUNKS)
    picked = [texts_by_job[j][c] for j, c in sel]
    read = [focus_window(t, BUDGET, "split") for t in picked]
    ctx = []
    for t in read:
        ls = t.split("\n")
        for i, ln in enumerate(ls):
            if k in ln:
                ctx.append((i, len(ls) - 1 - i))
                break
    best = max(ctx, key=lambda c: min(c), default=None)
    return {"ev": bool(ctx), "before": best[0] if best else np.nan, "after": best[1] if best else np.nan,
            "chars_read": sum(map(len, read)), "n_chunks": sum(map(len, texts_by_job)),
            "cut": sum(len(r) < len(p) for r, p in zip(read, picked))}


def main() -> None:
    base = pd.read_parquet(OUT / "evidence_loss.parquet", columns=["run_id", "leaf"])  # cùng mẫu với evidence_loss.py
    runs = pd.read_parquet("data/kaggle_log_ds/runs.parquet", columns=["run_id", "key"]).merge(base, on="run_id")
    ids = runs[["run_id"]]
    ch = duckdb.sql("""SELECT run_id, job_id, chunk_idx, kind, step_header, text
                       FROM 'data/run_dataset/chunks.parquet' JOIN ids USING (run_id)
                       ORDER BY run_id, job_id, chunk_idx""").df()
    by_run = defaultdict(lambda: defaultdict(list))
    for r in ch.itertuples(index=False):
        by_run[r.run_id][r.job_id].append(r)
    key = dict(zip(runs.run_id, runs.key))
    rows = []
    for run_id, jobs in by_run.items():
        jobs = [v for _, v in sorted(jobs.items())]
        k = key[run_id]
        cur, v2 = [[c.text for c in job] for job in jobs], [rechunk_v2(job) for job in jobs]
        for name, texts, ff in (("hiện tại", cur, False), ("hiện tại + chọn lỗi đầu", cur, True),
                                ("v2", v2, False), ("v2 + chọn lỗi đầu", v2, True)):
            rows.append({"run_id": run_id, "cách": name, **measure(texts, k, ff)})
    d = pd.DataFrame(rows).merge(runs[["run_id", "leaf"]], on="run_id")
    d.to_parquet(OUT / "semantic_chunking.parquet", index=False)
    order = ["hiện tại", "hiện tại + chọn lỗi đầu", "v2", "v2 + chọn lỗi đầu"]
    s = d.groupby("cách").agg(con_bang_chung=("ev", "mean"), dong_truoc_tv=("before", "median"),
                              dong_sau_tv=("after", "median"), ky_tu_doc_tb=("chars_read", "mean"),
                              so_doan_tb=("n_chunks", "mean"), doan_bi_cat_tb=("cut", "mean")).loc[order]
    print(f"{d.run_id.nunique()} run"); print(s.round(3).to_string())
    ctx = d[d.ev].assign(it=lambda x: (x.before < 3) | (x.after < 3)).groupby("cách").it.mean().loc[order]
    print("ngữ cảnh trung bình (dòng trước / sau):")
    print(d[d.ev].groupby("cách")[["before", "after"]].mean().loc[order].round(1).to_string())
    print("tỉ lệ run có bằng chứng nhưng < 3 dòng ngữ cảnh ở một phía:"); print(ctx.round(3).to_string())
    print(d.pivot_table(index="leaf", columns="cách", values="ev", aggfunc="mean")[order].round(2).to_string())


if __name__ == "__main__":
    main()
