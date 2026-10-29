"""Kiểm chứng trục giai đoạn (crawl.stages, 25/10/2026) bằng người gán MÙ: bảng không hiện giai đoạn quy tắc đề xuất.

Mẫu phân tầng theo (giai đoạn quy tắc × nguồn): nguồn `leaf` (suy thẳng từ loại lỗi đã kiểm chứng) lấy ít, các nguồn
tool/evidence/context/step và run `?` lấy nhiều hơn vì đó là phần quy tắc mới. Đáp án lưu riêng ở stage_key.json.

    uv run --with openpyxl python -m project3.pipeline.stage_review sample   # -> docs/gan-giai-doan-2026-10-25.xlsx
    uv run --with openpyxl python -m project3.pipeline.stage_review eval     # đọc cột "giai đoạn (người)" đã điền
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from project3.crawl.stages import STAGES

AXES = Path("data/run_dataset/axes.parquet")
RUN_DATASET = Path("data/run_dataset")
XLSX = Path("docs/gan-giai-doan-2026-10-25.xlsx")
KEY = Path("data/human_labels/stage_key.json")
PER_CELL = {"leaf": 4, "tool": 6, "evidence": 5, "context": 3, "step": 6}
HELP = {"setup": "chuẩn bị môi trường: checkout, cài JDK/SDK, cache, tải action, kéo image, runner",
        "prepare": "chuẩn bị build: đọc cấu hình Maven/Gradle, enforcer, tải phụ thuộc",
        "compile": "biên dịch, sinh mã, xử lý resource",
        "check": "kiểm tra tĩnh: format, checkstyle, lint, javadoc, license, API, phân tích phụ thuộc",
        "test": "test đơn vị", "itest": "test tích hợp / e2e / chức năng / instrumentation",
        "package": "đóng gói, phát hành, triển khai", "unclear": "không xác định được từ log"}


def excerpt(chunks: pd.DataFrame, key: str, limit: int = 3000) -> str:
    """Đoạn chứa bằng chứng (hoặc 2 đoạn cuối của job fail), cắt quanh dòng bằng chứng."""
    ev = chunks[chunks.has_evidence]
    picked = ev.head(1) if len(ev) else chunks.tail(2)
    text = "\n---\n".join(f"[step: {r.step_header}]\n{r.text}" for r in picked.itertuples())
    pos = text.find(key) if key else -1
    if pos < 0:
        return text[-limit:]
    start = max(0, pos - limit * 2 // 3)
    return text[start:start + limit]


def sample(seed: int) -> None:
    import duckdb
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from project3.pipeline.run_dataset import clean

    a = pd.read_parquet(AXES)
    a = a[a.stage.notna()]
    picked = []
    for (st, src), g in a.groupby(["stage", "stage_src"]):
        picked.append(g.sample(min(len(g), PER_CELL.get(src, 3)), random_state=seed))
    s = pd.concat(picked).sample(frac=1, random_state=seed).reset_index(drop=True)
    runs = pd.read_parquet(RUN_DATASET / "runs.parquet", columns=["run_id", "repository", "workflow", "evidence"])
    s = s.merge(runs, on="run_id", how="left")
    ids = ",".join(str(i) for i in s.run_id)
    ch = duckdb.sql(f"""SELECT run_id, job_id, chunk_idx, job_name, failed_steps, step_header, has_evidence, text
                        FROM '{(RUN_DATASET / "chunks.parquet").as_posix()}' WHERE run_id IN ({ids})
                        ORDER BY run_id, job_id, chunk_idx""").df()
    wb = Workbook()
    ws = wb.active
    ws.title = "gan"
    cols = ["stt", "repo", "run", "workflow", "job fail", "step fail", "dòng bằng chứng", "trích log",
            "giai đoạn (người)", "ghi chú"]
    ws.append(cols)
    key = {}
    for i, r in enumerate(s.itertuples(), 1):
        c = ch[ch.run_id == r.run_id]
        ev = r.evidence if isinstance(r.evidence, str) else ""
        ws.append([i, r.repository, f"https://github.com/{r.repository}/actions/runs/{r.run_id}", r.workflow,
                   " | ".join(dict.fromkeys(c.job_name))[:300], " | ".join(dict.fromkeys(c.failed_steps))[:300],
                   ev[:500], excerpt(c, clean(ev)[:120].strip()), None, None])
        key[str(r.run_id)] = {"stt": i, "stage": r.stage, "stage_src": r.stage_src, "leaf": r.leaf,
                              "location": r.location, "failed_tool": r.failed_tool}
    for col, w in zip("ABCDEFGHIJ", (5, 22, 18, 22, 25, 25, 45, 100, 16, 25)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.freeze_panes = "B2"
    h = wb.create_sheet("huong-dan")
    h.append(["Điền cột 'giai đoạn (người)' bằng MỘT giá trị dưới đây: lỗi làm run fail phát sinh ở giai đoạn nào."])
    h.append(["Không cần đoán loại lỗi; nếu log không đủ để biết thì ghi unclear. Bảng KHÔNG hiện đề xuất của quy tắc."])
    for k, v in HELP.items():
        h.append([k, v])
    h.column_dimensions["A"].width = 12
    h.column_dimensions["B"].width = 90
    XLSX.parent.mkdir(parents=True, exist_ok=True)
    wb.save(XLSX)
    KEY.write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(s)} run -> {XLSX} (đáp án {KEY})")
    print(pd.crosstab(s.stage, s.stage_src).to_string())


def evaluate() -> None:
    from openpyxl import load_workbook
    key = json.loads(KEY.read_text(encoding="utf-8"))
    by_stt = {v["stt"]: v for v in key.values()}
    rows = []
    for r in load_workbook(XLSX).active.iter_rows(min_row=2, values_only=True):
        human = (r[8] or "").strip().lower()
        if human:
            if human not in STAGES and human != "unclear":
                raise SystemExit(f"dòng {r[0]}: giá trị lạ {human!r}")
            rows.append({**by_stt[r[0]], "human": human})
    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("chưa có dòng nào được điền")
    clear = df[df.human != "unclear"]
    ok = clear.stage == clear.human
    print(f"{len(df)} dòng đã gán, {len(df) - len(clear)} unclear; khớp trên phần rõ: {ok.mean():.3f} ({ok.sum()}/{len(clear)})")
    print("precision theo giai đoạn quy tắc:", ok.groupby(clear.stage).mean().round(3).to_dict())
    print("theo nguồn:", ok.groupby(clear.stage_src).mean().round(3).to_dict())
    try:
        from sklearn.metrics import cohen_kappa_score
        print(f"kappa (gồm unclear): {cohen_kappa_score(df.stage, df.human):.3f}")
    except ImportError:
        pass
    print(pd.crosstab(clear.stage, clear.human, margins=True).to_string())
    out = Path("data/human_labels/stage_eval.json")
    out.write_text(json.dumps({"n": len(df), "unclear": int(len(df) - len(clear)), "accuracy": float(ok.mean()),
                               "per_stage": ok.groupby(clear.stage).mean().to_dict(),
                               "per_source": ok.groupby(clear.stage_src).mean().to_dict()}, ensure_ascii=False, indent=1),
                   encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["sample", "eval"])
    ap.add_argument("--seed", type=int, default=25)
    a = ap.parse_args()
    sample(a.seed) if a.cmd == "sample" else evaluate()
