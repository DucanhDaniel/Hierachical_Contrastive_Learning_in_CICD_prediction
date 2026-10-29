"""Kiểm chứng LÁ (tầng 3) của bộ quy tắc bằng người gán, 26/10/2026. Cây 3 tầng (docs/cay-nhan-3-tang-2026-10-25.md):
mỗi lá có đúng một cha, nên lá đúng thì artifact và thời điểm cần sửa cũng đúng. Precision lá chưa từng được đo
(trước đây chỉ đo ở 7 loại cũ).

Mẫu phân tầng theo lá (lá hiếm lấy nhiều hơn tỉ lệ), trộn các đợt crawl (base / targeted-r3 / targeted-android), thêm
một ít run `?` để xem quy tắc bỏ sót gì. Bỏ run đã có trong vòng gán 10/10. Bảng KHÔNG hiện nhãn quy tắc; đáp án ở key.
Cột "gợi ý AI" do Claude đọc cùng trích log (không thấy nhãn quy tắc) điền vào. Gợi ý AI không phải nhãn (C-02);
người gán quyết định. Khi báo cáo phải ghi là người gán có thấy gợi ý AI.

    python -m project3.pipeline.leaf_review sample              # -> data/human_labels/leaf_review/{items.jsonl,key.json}
    # (Claude điền data/human_labels/leaf_review/ai_suggest.jsonl)
    uv run --with openpyxl python -m project3.pipeline.leaf_review sheet   # -> docs/gan-la-2026-10-26.xlsx
    uv run --with openpyxl --group exp python -m project3.pipeline.leaf_review eval

Vòng MÙ (26/10, sau khi sửa 9 quy tắc từ vòng trên): mẫu mới ~3 run/lá, bỏ mọi run đã gán, KHÔNG có gợi ý AI; ngoài
precision từng lá còn tính precision có trọng số theo phân bố lá thật (đại diện cho toàn bộ dữ liệu):
    python -m project3.pipeline.leaf_review --blind sample --per-leaf 3
    uv run --with openpyxl python -m project3.pipeline.leaf_review --blind sheet   # -> docs/gan-la-mu-2026-10-26.xlsx
    uv run --with openpyxl --group exp python -m project3.pipeline.leaf_review --blind eval
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from project3.pipeline.stage_review import excerpt

RUN_DATASET = Path("data/run_dataset")
DIR = Path("data/human_labels/leaf_review")
ITEMS, KEY, AI = DIR / "items.jsonl", DIR / "key.json", DIR / "ai_suggest.jsonl"
XLSX = Path("docs/gan-la-2026-10-26.xlsx")
BLIND = False


def use_blind() -> None:
    global DIR, ITEMS, KEY, AI, XLSX, BLIND
    DIR, BLIND = Path("data/human_labels/leaf_review_blind"), True
    ITEMS, KEY, AI, XLSX = DIR / "items.jsonl", DIR / "key.json", DIR / "ai_none.jsonl", Path("docs/gan-la-mu-2026-10-26.xlsx")
# số run mỗi lá trong mẫu: lá test và môi trường lấy nhiều vì nghi sai nhiều nhất (test/itest theo tên workflow)
PER_LEAF = {"testfailure": 15, "itestfailure": 15, "compile": 10, "quality": 10, "doc": 8, "license": 8,
            "compatibility": 8, "buildconfig": 8, "dependency": 12, "flaky": 10, "git": 10, "androidsdk": 3,
            "infra": 12, "network": 12, "crash": 12, "?": 12}
LEAVES = ["compile", "quality", "doc", "license", "compatibility", "testfailure", "itestfailure", "flaky",
          "buildconfig", "dependency", "git", "androidsdk", "infra", "network", "crash"]
CHOICES = LEAVES + ["unclear", "non_build"]
HELP = {
    "compile": "biên dịch mã nguồn/mã test thất bại (javac, kotlinc, scalac…)",
    "quality": "vi phạm quy tắc kiểm tra code: format (spotless, ktlint), checkstyle, pmd, spotbugs, detekt, lint…",
    "doc": "lỗi tài liệu: javadoc, dokka",
    "license": "thiếu/sai header license, RAT, kiểm tra license phụ thuộc",
    "compatibility": "không tương thích API/ABI: revapi, japicmp, metalava, apiCheck",
    "testfailure": "test tự động (unit) không đạt",
    "itestfailure": "test tích hợp / e2e / chức năng / instrumentation (emulator) không đạt",
    "flaky": "test không ổn định: báo FLAKY, chạy lại thì qua",
    "buildconfig": "cấu hình build sai: pom.xml/build.gradle/settings sai cú pháp, khai báo trùng/thiếu",
    "dependency": "không resolve được phụ thuộc, xung đột/lệch phiên bản (kể cả JDK), thiếu class bên ngoài",
    "git": "lỗi tương tác git: clone/fetch/push, submodule, lock",
    "androidsdk": "lỗi Android SDK/emulator: tải SDK, license SDK chưa chấp nhận, emulator không khởi động",
    "infra": "hạ tầng khác: xác thực/secret, dịch vụ/container ngoài không lên, cấu hình runner",
    "network": "lỗi mạng: timeout, 5xx, không tải được artifact/image, DNS, rate limit",
    "crash": "môi trường sập: runner shutdown, OOM, hết đĩa, quá thời gian, VM crash",
    "unclear": "log không đủ để biết",
    "non_build": "không phải lỗi build/test (thủ tục PR, changelog, Jira, release…)",
}


def batch_map(repos) -> dict:
    out = {}
    for root in ("data/crawl_pr", "data/validate"):
        for d in Path(root).iterdir():
            st = d / "crawl_status.json"
            repo = d.name.replace("__", "/", 1)
            if st.exists() and repo not in out:
                out[repo] = json.loads(st.read_text(encoding="utf-8")).get("scope") or "base"
    return {r: out.get(r, "base") for r in repos}


def sample(seed: int, per_leaf: int | None = None) -> None:
    import duckdb
    from project3.crawl.build_log_labels import GROUP
    from project3.model.labels import leaf_of
    from project3.pipeline.run_dataset import clean

    runs = pd.read_parquet(RUN_DATASET / "runs.parquet",
                           columns=["run_id", "repository", "workflow", "label_l2", "label_l3", "evidence", "log_jobs"])
    runs = runs[runs.log_jobs > 0]
    runs["leaf"] = [leaf_of(a, b) if b in GROUP else ("?" if b == "?" else None) for a, b in zip(runs.label_l3, runs.label_l2)]
    runs = runs[runs.leaf.notna()]
    done = {json.loads(l)["run_id"] for l in open("data/human_labels/labels.jsonl", encoding="utf-8")}
    prev = Path("data/human_labels/leaf_review/key.json")
    if BLIND and prev.exists():  # vòng mù: bỏ cả 161 run của vòng có gợi ý AI
        done |= {int(k) for k in json.loads(prev.read_text(encoding="utf-8"))}
    runs = runs[~runs.run_id.isin(done)]
    runs["batch"] = runs.repository.map(batch_map(runs.repository.unique()))
    picked = []
    plan = {l: per_leaf for l in [*LEAVES, "?"]} if per_leaf else PER_LEAF
    for leaf, n in plan.items():
        g = runs[runs.leaf == leaf]
        if leaf == "?" and not per_leaf:  # `?` của đợt android chiếm 41% run của đợt -> lấy nửa từ đó
            g = pd.concat([g[g.batch == "targeted-android"].sample(min(n // 2, (g.batch == "targeted-android").sum()),
                                                                    random_state=seed),
                           g[g.batch != "targeted-android"].sample(n - n // 2, random_state=seed)])
            picked.append(g)
            continue
        # tối đa 2 run/repo để mẫu không bị một repo chiếm
        g = g.sample(frac=1, random_state=seed).groupby("repository").head(2)
        picked.append(g.head(n))
    s = pd.concat(picked).sample(frac=1, random_state=seed).reset_index(drop=True)
    ids = ",".join(str(i) for i in s.run_id)
    ch = duckdb.sql(f"""SELECT run_id, job_id, chunk_idx, job_name, failed_steps, step_header, has_evidence, text
                        FROM '{(RUN_DATASET / "chunks.parquet").as_posix()}' WHERE run_id IN ({ids})
                        ORDER BY run_id, job_id, chunk_idx""").df()
    DIR.mkdir(parents=True, exist_ok=True)
    key = {}
    with ITEMS.open("w", encoding="utf-8") as f:
        for i, r in enumerate(s.itertuples(), 1):
            c = ch[ch.run_id == r.run_id]
            ev = r.evidence if isinstance(r.evidence, str) else ""
            item = {"stt": i, "run_id": int(r.run_id), "repo": r.repository, "workflow": r.workflow,
                    "jobs": " | ".join(dict.fromkeys(c.job_name))[:300],
                    "failed_steps": " | ".join(dict.fromkeys(s for x in c.failed_steps for s in x.split(" | ") if s))[:300],
                    "log": excerpt(c, clean(ev)[:120].strip()) if len(c) else ""}
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
            key[str(r.run_id)] = {"stt": i, "rule_leaf": r.leaf, "batch": r.batch, "evidence": ev[:300]}
    KEY.write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(s)} run -> {ITEMS}, đáp án {KEY}")
    print(pd.crosstab(s.leaf, s.batch, margins=True).to_string())


def sheet() -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    items = [json.loads(l) for l in ITEMS.open(encoding="utf-8")]
    ai = {}
    if AI.exists():
        for l in AI.open(encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                ai[int(r["stt"])] = r
    wb = Workbook()
    ws = wb.active
    ws.title = "gan"
    ws.append(["stt", "repo", "run", "workflow", "job fail", "step fail", "trích log", "loại lỗi (người)", "ghi chú"]
              + ([] if BLIND else ["gợi ý AI", "lý do AI"]))
    for it in items:
        a = ai.get(it["stt"], {})
        ws.append([it["stt"], it["repo"], f"https://github.com/{it['repo']}/actions/runs/{it['run_id']}", it["workflow"],
                   it["jobs"], it["failed_steps"], it["log"], None, None]
                  + ([] if BLIND else [a.get("leaf"), a.get("reason")]))
    dv = DataValidation(type="list", formula1='"' + ",".join(CHOICES) + '"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"H2:H{len(items) + 1}")
    for col, w in zip("ABCDEFGHIJK", (5, 22, 18, 20, 24, 24, 100, 16, 22, 14, 40)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for cell in ws["H"][1:]:
        cell.fill = PatternFill("solid", fgColor="FFF2CC")
    for cell in ws["J"][1:] + ws["K"][1:]:
        cell.font = Font(color="808080")
    ws.freeze_panes = "B2"
    h = wb.create_sheet("huong-dan")
    for line in ["Điền cột H 'loại lỗi (người)' bằng MỘT giá trị (có danh sách thả xuống): nguyên nhân gốc làm run fail.",
                 *(["Vòng MÙ: không có gợi ý nào; tự đọc log và quyết định. Không chắc thì ghi unclear."] if BLIND else
                   ["Nên tự đọc log và quyết định TRƯỚC, rồi mới nhìn cột J/K (gợi ý AI, chữ xám) để đối chiếu.",
                    "Gợi ý AI chỉ là tham khảo, có thể sai; AI không thấy nhãn của bộ quy tắc. Không chắc thì ghi unclear."]),
                 "Nhiều lỗi cùng lúc: chọn lỗi xảy ra SỚM nhất (nguyên nhân gốc), vd. compile fail kéo theo test fail -> compile.",
                 ""]:
        h.append([line])
    for k in CHOICES:
        h.append([k, HELP[k]])
    h.column_dimensions["A"].width = 16
    h.column_dimensions["B"].width = 100
    wb.save(XLSX)
    print(f"{len(items)} dòng, {len(ai)} gợi ý AI -> {XLSX}")


def evaluate() -> None:
    from openpyxl import load_workbook
    from sklearn.metrics import cohen_kappa_score
    from project3.model.labels import PARENT
    key = {v["stt"]: v for v in json.loads(KEY.read_text(encoding="utf-8")).values()}
    rows = []
    for r in load_workbook(XLSX).active.iter_rows(min_row=2, values_only=True):
        human = (r[7] or "").strip().lower()
        if human:
            if human not in CHOICES:
                raise SystemExit(f"dòng {r[0]}: giá trị lạ {human!r}")
            rows.append({**key[r[0]], "human": human, "ai": None if BLIND else r[9]})
    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("chưa có dòng nào được điền")
    lab = df[df.rule_leaf != "?"]
    ok = lab.rule_leaf == lab.human
    print(f"{len(df)} dòng đã gán ({len(lab)} có lá quy tắc). Precision lá của quy tắc: {ok.mean():.3f} ({ok.sum()}/{len(lab)})")
    print("theo lá:", ok.groupby(lab.rule_leaf).mean().round(2).to_dict())
    print("theo đợt:", ok.groupby(lab.batch).mean().round(2).to_dict())
    top = {"compile": "du_an", "testfailure": "du_an", "itestfailure": "du_an", "quality": "du_an", "doc": "du_an",
           "license": "du_an", "compatibility": "du_an", "flaky": "du_an", "buildconfig": "du_an", "dependency": "du_an",
           "git": "moi_truong", "androidsdk": "moi_truong", "infra": "moi_truong", "network": "moi_truong",
           "crash": "moi_truong"}
    clear = lab[lab.human.isin(LEAVES)]
    print(f"tầng 1 (artifact) khớp: {(clear.rule_leaf.map(top) == clear.human.map(top)).mean():.3f} trên {len(clear)} run rõ")
    print(f"kappa người–quy tắc (lá): {cohen_kappa_score(lab.rule_leaf, lab.human):.3f}")
    # precision có trọng số theo phân bố lá thật (mẫu phân tầng đều theo lá không đại diện cho dữ liệu)
    from project3.crawl.build_log_labels import GROUP as RULE_GROUP
    from project3.model.labels import leaf_of
    runs = pd.read_parquet(RUN_DATASET / "runs.parquet", columns=["label_l2", "label_l3", "log_jobs"])
    runs = runs[(runs.log_jobs > 0) & runs.label_l2.isin(list(RULE_GROUP))]
    share = pd.Series([leaf_of(a, b) for a, b in zip(runs.label_l3, runs.label_l2)]).value_counts(normalize=True)
    per = ok.groupby(lab.rule_leaf).mean()
    w = share.reindex(per.index).fillna(0)
    print(f"precision có trọng số theo phân bố lá thật: {(per * w).sum() / w.sum():.3f} "
          f"(phủ {w.sum():.1%} số run có nhãn)")
    a = df[df.ai.notna()] if "ai" in df else df.iloc[:0]
    if len(a):
        print(f"người khớp gợi ý AI: {(a.human == a.ai).mean():.3f}; AI khớp quy tắc: {(lab.ai == lab.rule_leaf).mean():.3f} "
              "(người thấy gợi ý AI -> có thể bị neo theo AI)")
    print("`?` theo người:", df[df.rule_leaf == "?"].human.value_counts().to_dict())
    print(pd.crosstab(lab.rule_leaf, lab.human).to_string())
    (DIR / "eval.json").write_text(json.dumps({"n": len(df), "precision": float(ok.mean()),
                                               "per_leaf": ok.groupby(lab.rule_leaf).mean().to_dict()},
                                              ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--blind", action="store_true", help="vòng mù: thư mục/bảng riêng, không gợi ý AI")
    ap.add_argument("cmd", choices=["sample", "sheet", "eval"])
    ap.add_argument("--per-leaf", type=int, default=None, help="số run mỗi lá (mặc định theo PER_LEAF)")
    ap.add_argument("--seed", type=int, default=26)
    a = ap.parse_args()
    if a.blind:
        use_blind()
    {"sample": lambda: sample(a.seed, a.per_leaf), "sheet": sheet, "eval": evaluate}[a.cmd]()
