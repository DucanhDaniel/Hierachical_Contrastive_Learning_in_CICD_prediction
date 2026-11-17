"""Cắt log theo đơn vị ngữ nghĩa + chọn đoạn ưu tiên dòng lỗi đầu (10/11/2026, góp ý GVHD 05/11: không cắt đều).

Đầu vào là các đoạn của pipeline.run_dataset (đã tách theo step / goal Maven / task Gradle, khối dài bị chia cửa sổ 40
dòng chồng 5 dòng). Ở đây dựng lại khối gốc rồi:
  - khối vừa BUDGET ký tự thì giữ nguyên;
  - khối dài hơn thì cắt theo đơn vị: test case lỗi | stack trace (ngoại lệ + `at ...` + `Caused by:`) | mục lỗi của
    công cụ (`* What went wrong:`, `Failed to execute goal`, khối lỗi biên dịch) | phần còn lại theo khuôn dòng;
  - đơn vị < MIN_LINES dòng gộp với đơn vị kề; đơn vị dài hơn BUDGET cắt ở ranh giới bên trong, mảnh sau giữ HEAD dòng
    đầu của đơn vị; mỗi đoạn mở đầu bằng PRE dòng ngay trước nó.
Chọn đoạn: mỗi job lỗi luôn có đoạn chứa dòng báo lỗi đầu tiên (FAIL_LINE), còn chỗ thì theo điểm như select_chunks.

Giá trị tự đặt, người dùng duyệt 10/11: MIN_LINES 12 (= run_dataset.MIN_LINES), BUDGET 1600 ký tự (= cửa sổ mô hình
đọc), HEAD 3, PRE 5. Phép đo trên 9.804 run (scripts/analysis/semantic_chunking.py): dòng bằng chứng trong phần mô
hình đọc 91,1% -> 93,5% (lấy đều theo lá), lợi ở buildconfig/compatibility/dependency/network, ngữ cảnh ít hơn.

    python -m project3.model.semantic build   # data/kaggle_log_ds -> data/kaggle_log_ds_sem (chỉ thay chunks.parquet)
"""
import argparse
import json
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

from .inputs import FAIL_LINE, chunk_score, focus_window

MIN_LINES, BUDGET, HEAD, OVERLAP, PRE = 12, 1600, 3, 5, 5
MAX_CHUNK_CHARS = 4000  # = pack.MAX_CHUNK_CHARS

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


def size(lines: list) -> int:
    return sum(len(s) + 1 for s in lines)


def blocks_of(job) -> list:
    """Đoạn của run_dataset (kind, step_header, text) theo thứ tự -> [(step, [dòng])] khối gốc."""
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
        elif kind == "test":
            pass  # thân của test case (thông báo assert, log của test) tới khi gặp đơn vị khác
        elif kind != "other" or (cur and tmpl(ln) != tmpl(cur[-1]) and len(cur) >= MIN_LINES):
            push("other")
        cur.append(ln)
    push(None)
    return units


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


def rechunk(job) -> list:
    """Một job (đoạn của run_dataset) -> danh sách đoạn mới (văn bản)."""
    out = []
    for _, lines in blocks_of(job):
        if size(lines) <= BUDGET:
            out.append("\n".join(lines))
            continue
        groups, cur, start = [], [], 0
        for kind, u in units_of(lines):
            pre = lines[max(0, start - PRE):start]
            start += len(u)
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


def select_first_fail(masked: list, scores: list, max_chunks: int) -> list:
    """Mỗi job lỗi luôn có đoạn chứa dòng báo lỗi ĐẦU TIÊN (FAIL_LINE, trên văn bản đã che) — Maven/Gradle in lỗi thật
    trước dòng tổng kết; job không có dòng như vậy thì lấy đoạn điểm cao nhất. Còn chỗ thì theo điểm toàn run (hoà điểm
    ưu tiên đoạn sau). Trả về [(job, đoạn)] theo thứ tự gốc."""
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


def build(src: Path, out: Path, run_dataset: Path, max_chunks: int, dataset_id: str) -> None:
    """Gói dữ liệu giống src (runs, features, label_tree, mã) nhưng chunks.parquet theo cách cắt + chọn mới."""
    import duckdb
    import pandas as pd

    from .text import mask_text
    out.mkdir(parents=True, exist_ok=True)
    for f in src.iterdir():
        if f.name not in ("chunks.parquet", "chunks_tail.parquet", "tfidf_text.parquet", "dataset-metadata.json",
                          "coverage.json"):
            shutil.copy2(f, out / f.name)
    runs = pd.read_parquet(src / "runs.parquet", columns=["run_id", "key"])
    key = dict(zip(runs.run_id, runs.key.fillna("")))
    ids = runs[["run_id"]]
    ch = duckdb.sql(f"""SELECT run_id, job_id, chunk_idx, kind, step_header, text FROM '{run_dataset / "chunks.parquet"}'
                        JOIN ids USING (run_id) ORDER BY run_id, job_id, chunk_idx""").df()
    by_run = defaultdict(lambda: defaultdict(list))
    for r in ch.itertuples(index=False):
        by_run[r.run_id][r.job_id].append(r)
    del ch
    rows, cover = [], [0, 0, 0]  # [run có khoá, run có bằng chứng trong đoạn chọn, ... trong cửa sổ mô hình đọc]
    for run_id, jobs in by_run.items():
        job_ids = sorted(jobs)
        texts = [rechunk(jobs[j]) for j in job_ids]
        k = key.get(run_id, "")
        masked = [[mask_text(t, k) for t in job] for job in texts]
        scores = [[chunk_score(t, ci == len(job) - 1) for ci, t in enumerate(job)] for job in masked]
        picked = select_first_fail(masked, scores, max_chunks)
        sel = [texts[j][c] for j, c in picked]
        if k:
            cover[0] += 1
            cover[1] += any(k in t for t in sel)
            cover[2] += any(k in focus_window(t, BUDGET, "split") for t in sel)
        rows += [{"run_id": run_id, "job_id": job_ids[j], "chunk_idx": c, "text": texts[j][c][-MAX_CHUNK_CHARS:]}
                 for j, c in picked]
    pd.DataFrame(rows).to_parquet(out / "chunks.parquet", index=False, compression="zstd")
    cov = {"runs_with_key": cover[0], "evidence_in_picked": cover[1] / max(cover[0], 1),
           "evidence_in_window": cover[2] / max(cover[0], 1), "chunking": "semantic-v2+first-fail 2026-11-10",
           "MIN_LINES": MIN_LINES, "BUDGET": BUDGET, "HEAD": HEAD, "PRE": PRE, "max_chunks": max_chunks}
    (out / "coverage.json").write_text(json.dumps(cov, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "dataset-metadata.json").write_text(json.dumps(
        {"title": dataset_id.split("/")[-1], "id": dataset_id, "licenses": [{"name": "other"}]}), encoding="utf-8")
    print(f"-> {out}: {len(rows)} đoạn, {len(by_run)} run; {json.dumps(cov, ensure_ascii=False)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--src", type=Path, default=Path("data/kaggle_log_ds"))
    b.add_argument("--out", type=Path, default=Path("data/kaggle_log_ds_sem"))
    b.add_argument("--run-dataset", type=Path, default=Path("data/run_dataset"))
    b.add_argument("--max-chunks", type=int, default=8)
    b.add_argument("--dataset-id", default="ducanhpham2k5/p3-log-data-sem")
    a = ap.parse_args()
    build(a.src, a.out, a.run_dataset, a.max_chunks, a.dataset_id)
