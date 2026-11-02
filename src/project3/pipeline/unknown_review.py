"""Gán mù các run quy tắc để `?` (31/10/2026): đo mô hình ở đúng chỗ quy tắc không làm được (lá + dòng lỗi).

Mẫu: run `?` có log, chưa từng gán, tối đa 2 run/repo, rút ngẫu nhiên theo run (giữ phân bố thật của `?`). Trích log
KHÔNG lấy từ mô hình: 2 đoạn điểm cao nhất theo dấu hiệu fail (inputs.chunk_score), mỗi đoạn cửa sổ chia đôi rộng hơn
cửa sổ mô hình đọc; các dòng được đánh số để người gán ghi số dòng lỗi. Không có nhãn quy tắc (vì là `?`), không có gợi ý
AI hay dự đoán mô hình (C-02: người gán quyết định).

    python -m project3.pipeline.unknown_review sample --n 120      # -> data/human_labels/unknown_review/items.jsonl
    python -m project3.pipeline.unknown_review sample2 --n 120 --non-build 30   # vòng 2 (02/11), nối vào items.jsonl
    uv run --with openpyxl python -m project3.pipeline.unknown_review sheet   # -> docs/gan-run-chua-nhan-2026-10-31.xlsx
    python -m project3.pipeline.unknown_review serve   # giao diện web http://localhost:8766 thay cho xlsx (unknown_review.html)
    uv run --with openpyxl python -m project3.pipeline.unknown_review eval "data/results/unknown/**/*.unknown.parquet"
"""
import argparse
import glob
import json
import sys
from pathlib import Path

import pandas as pd

from project3.pipeline.leaf_review import CHOICES, HELP, LEAVES, batch_map

RUN_DATASET = Path("data/run_dataset")
DIR = Path("data/human_labels/unknown_review")
ITEMS = DIR / "items.jsonl"
LABELS = DIR / "labels.jsonl"
XLSX = Path("docs/gan-run-chua-nhan-2026-10-31.xlsx")
HUMAN = Path("data/human_labels")
TOP = {"git": "moi_truong", "androidsdk": "moi_truong", "infra": "moi_truong", "network": "moi_truong",
       "crash": "moi_truong"}  # còn lại: du_an


def labelled_before() -> set:
    done = {json.loads(l)["run_id"] for l in open(HUMAN / "labels.jsonl", encoding="utf-8")}
    for f in ("blind3/key.json", "leaf_review/key.json", "leaf_review_blind/key.json", "key.json"):
        p = HUMAN / f
        if p.exists():
            done |= {int(k) for k in json.loads(p.read_text(encoding="utf-8"))}
    return done


def excerpt(chunks: pd.DataFrame, n_chunks: int = 2, window: int = 2400) -> list:
    """Dòng log đưa cho người gán: n_chunks đoạn điểm fail cao nhất (theo thứ tự log), cửa sổ chia đôi `window` ký tự."""
    from project3.model.inputs import chunk_score, focus_window
    last = chunks.groupby("job_id").chunk_idx.transform("max")
    sc = [chunk_score(t, ci == m) for t, ci, m in zip(chunks.text, chunks.chunk_idx, last)]
    picked = chunks.assign(score=sc).sort_values(["score", "job_id", "chunk_idx"], ascending=[False, True, True])
    picked = picked.head(n_chunks).sort_values(["job_id", "chunk_idx"])
    lines = []
    for r in picked.itertuples():
        lines.append(f"===== job: {r.job_name} | step: {r.step_header}")
        lines += focus_window(r.text, window, "split").split("\n")
    return lines


def sample(n: int, seed: int) -> None:
    import duckdb
    runs = pd.read_parquet(RUN_DATASET / "runs.parquet",
                           columns=["run_id", "repository", "workflow", "label_l2", "log_jobs", "repo_fold", "event"])
    runs = runs[(runs.label_l2 == "?") & (runs.log_jobs > 0) & ~runs.run_id.isin(labelled_before())]
    runs = runs.drop_duplicates("run_id")
    s = runs.sample(frac=1, random_state=seed).groupby("repository").head(2).head(n).reset_index(drop=True)
    s["batch"] = s.repository.map(batch_map(s.repository.unique()))
    ids = ",".join(str(i) for i in s.run_id)
    ch = duckdb.sql(f"""SELECT run_id, job_id, chunk_idx, job_name, failed_steps, step_header, text
                        FROM '{(RUN_DATASET / "chunks.parquet").as_posix()}' WHERE run_id IN ({ids})
                        ORDER BY run_id, job_id, chunk_idx""").df()
    DIR.mkdir(parents=True, exist_ok=True)
    with ITEMS.open("w", encoding="utf-8") as f:
        for i, r in enumerate(s.itertuples(), 1):
            c = ch[ch.run_id == r.run_id]
            item = {"stt": i, "run_id": int(r.run_id), "repo": r.repository, "workflow": r.workflow, "fold": int(r.repo_fold),
                    "batch": r.batch, "event": r.event, "jobs": " | ".join(dict.fromkeys(c.job_name))[:300],
                    "failed_steps": " | ".join(dict.fromkeys(x for v in c.failed_steps for x in v.split(" | ") if x))[:300],
                    "lines": excerpt(c) if len(c) else []}
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"{len(s)} run `?` từ {s.repository.nunique()} repo -> {ITEMS}")
    print(s.batch.value_counts().to_dict(), s.event.value_counts().to_dict())


def sample2(n: int, n_nb: int, seed: int) -> None:
    """Vòng 2 (02/11/2026): thêm n run `?` rút như vòng 1 (thêm nhãn để đo ngưỡng / MC Dropout chắc hơn) + n_nb run mà bộ
    lọc non_build (model.abstain) bắt (kiểm tra bộ lọc có bắt nhầm lỗi build thật không). Hai phần trộn ngẫu nhiên, nối
    tiếp stt của vòng 1; phần nào được rút vì bộ lọc chỉ ghi ở round2_key.json (giao diện không đọc) để người gán vẫn mù."""
    import duckdb
    import numpy as np
    from project3.model.abstain import UNK, non_build
    old = [json.loads(l) for l in ITEMS.open(encoding="utf-8")]
    assert not any(it.get("round") == 2 for it in old), "đã có vòng 2"
    runs = pd.read_parquet(RUN_DATASET / "runs.parquet",
                           columns=["run_id", "repository", "workflow", "label_l2", "log_jobs", "repo_fold", "event"])
    meta = pd.read_parquet(UNK / "runs.parquet").drop_duplicates("run_id").set_index("run_id")  # run `?` có dự đoán mô hình
    runs = runs[(runs.label_l2 == "?") & (runs.log_jobs > 0) & runs.run_id.isin(meta.index)
                & ~runs.run_id.isin(labelled_before() | {it["run_id"] for it in old})].drop_duplicates("run_id")
    m = meta.reindex(runs.run_id)
    runs["nb"] = [non_build(j, s, k) for j, s, k in zip(m.failed_job_names, m.failed_steps, m.failed_jobs.fillna(1))]
    rnd = runs.sample(frac=1, random_state=seed).groupby("repository").head(2).head(n)
    rest = runs[(runs.nb != "") & ~runs.run_id.isin(rnd.run_id)]
    nb = rest.sample(frac=1, random_state=seed + 1).groupby("repository").head(2).head(n_nb)
    s = pd.concat([rnd.assign(pick="random"), nb.assign(pick="non_build")]).sample(frac=1, random_state=seed + 2)
    s = s.reset_index(drop=True)
    s["batch"] = s.repository.map(batch_map(s.repository.unique()))
    ids = ",".join(str(i) for i in s.run_id)
    ch = duckdb.sql(f"""SELECT run_id, job_id, chunk_idx, job_name, failed_steps, step_header, text
                        FROM '{(RUN_DATASET / "chunks.parquet").as_posix()}' WHERE run_id IN ({ids})
                        ORDER BY run_id, job_id, chunk_idx""").df()
    start = max(it["stt"] for it in old) + 1
    key = {}
    with ITEMS.open("a", encoding="utf-8") as f:
        for i, r in enumerate(s.itertuples(), start):
            c = ch[ch.run_id == r.run_id]
            item = {"stt": i, "run_id": int(r.run_id), "repo": r.repository, "workflow": r.workflow, "fold": int(r.repo_fold),
                    "batch": r.batch, "event": r.event, "jobs": " | ".join(dict.fromkeys(c.job_name))[:300],
                    "failed_steps": " | ".join(dict.fromkeys(x for v in c.failed_steps for x in v.split(" | ") if x))[:300],
                    "lines": excerpt(c) if len(c) else [], "round": 2}
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
            key[i] = {"pick": r.pick, "non_build_rule": r.nb}
    (DIR / "round2_key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"vòng 2: {len(s)} run (ngẫu nhiên {len(rnd)}, trong đó bộ lọc bắt {int((rnd.nb != '').sum())}; "
          f"rút vì bộ lọc {len(nb)}) từ {s.repository.nunique()} repo, stt {start}–{start + len(s) - 1}")
    print(s.batch.value_counts().to_dict(), nb.nb.value_counts().to_dict(), f"pool bộ lọc {len(rest)} run")


def sheet() -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    items = [json.loads(l) for l in ITEMS.open(encoding="utf-8")]
    wb = Workbook()
    ws = wb.active
    ws.title = "gan"
    ws.append(["stt", "repo", "run", "workflow", "job fail", "step fail", "trích log (số dòng ở đầu)", "loại lỗi (người)",
               "dòng lỗi (số)", "ghi chú"])
    for it in items:
        log = "\n".join(f"{k:>3}| {t}" for k, t in enumerate(it["lines"], 1))
        ws.append([it["stt"], it["repo"], f"https://github.com/{it['repo']}/actions/runs/{it['run_id']}", it["workflow"],
                   it["jobs"], it["failed_steps"], log[:32000], None, None, None])
    dv = DataValidation(type="list", formula1='"' + ",".join(CHOICES) + '"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"H2:H{len(items) + 1}")
    for col, w in zip("ABCDEFGHIJ", (5, 22, 18, 20, 24, 24, 110, 16, 12, 24)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for cell in ws["H"][1:] + ws["I"][1:]:
        cell.fill = PatternFill("solid", fgColor="FFF2CC")
    ws.freeze_panes = "B2"
    h = wb.create_sheet("huong-dan")
    for line in ["Các run này bộ quy tắc KHÔNG gán được (`?`). Không có gợi ý nào; tự đọc log (và link GitHub nếu cần).",
                 "Cột H: MỘT loại lỗi (danh sách thả xuống) = nguyên nhân gốc. Không đủ thông tin thì ghi unclear.",
                 "Cột I: số thứ tự dòng (số ở đầu dòng trong cột G) cho thấy rõ nhất nguyên nhân; nhiều dòng thì cách nhau "
                 "dấu phẩy, dòng quan trọng nhất ghi trước. Để trống nếu dòng lỗi không nằm trong trích log.",
                 "Nhiều lỗi cùng lúc: chọn lỗi xảy ra SỚM nhất (nguyên nhân gốc).", ""]:
        h.append([line])
    for k in CHOICES:
        h.append([k, HELP[k]])
    h.column_dimensions["A"].width = 16
    h.column_dimensions["B"].width = 100
    wb.save(XLSX)
    print(f"{len(items)} dòng -> {XLSX}")


def current_labels() -> dict:
    """stt -> bản ghi gán cuối cùng trong labels.jsonl (giao diện web)."""
    out = {}
    if LABELS.exists():
        for line in LABELS.open(encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                out[r["stt"]] = r
    return out


def serve(port: int, browser: bool = True) -> None:
    """Giao diện gán trên máy: log đủ dòng (chữ đều), bấm dòng để đánh dấu dòng lỗi, chọn loại lỗi; mỗi lần lưu ghi thêm
    một dòng vào labels.jsonl (lần cuối được tính)."""
    import time
    import webbrowser
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    items = [json.loads(l) for l in ITEMS.open(encoding="utf-8")]
    page = (Path(__file__).with_suffix(".html").read_text(encoding="utf-8")
            .replace("__CHOICES__", json.dumps(CHOICES)).replace("__HELP__", json.dumps(HELP, ensure_ascii=False)))

    class Handler(BaseHTTPRequestHandler):
        def reply(self, body: str, ctype: str) -> None:
            b = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if self.path.startswith("/api"):
                self.reply(json.dumps({"items": items, "labels": current_labels()}, ensure_ascii=False), "application/json")
            else:
                self.reply(page, "text/html")

        def do_POST(self):
            r = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if r.get("leaf") not in CHOICES:
                self.send_error(400)
                return
            r["time"] = time.strftime("%Y-%m-%d %H:%M:%S")
            with LABELS.open("a", encoding="utf-8") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            self.reply("{}", "application/json")

        def log_message(self, *args):
            pass

    url = f"http://localhost:{port}"
    print(f"{len(items)} run, đã gán {len(current_labels())} -> {url} (Ctrl+C để dừng; nhãn ghi vào {LABELS})", flush=True)
    if browser:
        webbrowser.open(url)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


def evaluate(pattern: str) -> None:
    """So nhãn người với dự đoán mô hình (gộp seed nếu có nhiều) và dòng lỗi người chọn với 5 dòng điểm cao nhất.
    Nhãn lấy từ labels.jsonl (giao diện web), chưa có thì từ bảng xlsx."""
    items = {json.loads(l)["stt"]: json.loads(l) for l in ITEMS.open(encoding="utf-8")}
    if LABELS.exists():
        given = [(k, v["leaf"], ",".join(map(str, v["lines"]))) for k, v in current_labels().items()]
    else:
        from openpyxl import load_workbook
        given = [(r[0], r[7], r[8]) for r in load_workbook(XLSX).active.iter_rows(min_row=2, values_only=True)]
    rows = []
    for stt, human, lines in given:
        human = (human or "").strip().lower()
        if not human:
            continue
        if human not in CHOICES:
            raise SystemExit(f"dòng {stt}: giá trị lạ {human!r}")
        it = items[stt]
        nums = [int(x) for x in str(lines or "").replace(";", ",").split(",") if x.strip().isdigit()]
        ev = [it["lines"][k - 1].strip() for k in nums if 0 < k <= len(it["lines"])]
        rows.append({"run_id": it["run_id"], "human": human, "ev": ev, "batch": it["batch"]})
    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("chưa có dòng nào được điền")
    print(f"{len(df)} run đã gán: {df.human.value_counts().to_dict()}")
    p = pd.concat([pd.read_parquet(f) for f in glob.glob(pattern, recursive=True)])
    p = p[p.run_id.isin(df.run_id)]
    pred = p.groupby("run_id").pred.agg(lambda x: x.mode().iloc[0])  # nhiều seed: lấy nhãn chiếm đa số
    df["model"] = df.run_id.map(pred)
    clear = df[df.human.isin(LEAVES) & df.model.notna()]
    print(f"mô hình đúng lá: {(clear.model == clear.human).mean():.3f} trên {len(clear)} run rõ "
          f"(bỏ unclear/non_build, {df.model.isna().sum()} run chưa có dự đoán)")
    top = lambda x: TOP.get(x, "du_an")
    print(f"mô hình đúng tầng 1 (dự án / môi trường CI): {(clear.model.map(top) == clear.human.map(top)).mean():.3f}")
    print(pd.crosstab(clear.human, clear.model).to_string())
    if "lines" in p:
        hits = []
        for rid, ev in zip(df.run_id, df.ev):
            if not ev:
                continue
            for x in p[p.run_id == rid].lines.dropna():
                top5 = [t.strip() for *_, t in json.loads(x)]
                hit = [any(t and (t[:120] in e or e[:120] in t) for e in ev) for t in top5]
                hits.append({"run_id": rid, "top1": any(hit[:1]), "top3": any(hit[:3])})
        h = pd.DataFrame(hits)
        if len(h):
            print(f"dòng lỗi người chọn: mô hình top1 {h.top1.mean():.3f}, top3 {h.top3.mean():.3f} "
                  f"({h.run_id.nunique()} run có dòng người chọn)")
    df.to_csv(DIR / "eval.csv", index=False)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["sample", "sample2", "sheet", "serve", "eval"])
    ap.add_argument("preds", nargs="?", default="data/results/unknown/**/*.unknown.parquet")
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--non-build", type=int, default=30, help="sample2: số run rút vì bộ lọc non_build")
    ap.add_argument("--seed", type=int, default=31)
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    {"sample": lambda: sample(a.n, a.seed), "sample2": lambda: sample2(a.n, a.non_build, a.seed), "sheet": sheet, "serve": lambda: serve(a.port, not a.no_browser),
     "eval": lambda: evaluate(a.preds)}[a.cmd]()
