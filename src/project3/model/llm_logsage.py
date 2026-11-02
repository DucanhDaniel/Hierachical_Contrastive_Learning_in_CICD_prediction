"""Baseline B3 (27/10/2026): LLM zero-shot với bước lọc log theo LogSage (arXiv 2506.03691, ASE 2025 Industry Showcase).
CHỈ để so sánh, không phải nguồn nhãn (C-02). Chuẩn bị ở máy local (cần data/run_dataset), LLM chạy trên Kaggle Benchmarks
(scripts/kaggle/llm_logsage/task.py).

Lọc log theo mục "Key log filtering" của LogSage:
  ứng viên = dòng chứa từ khoá lỗi của paper ∪ TAIL dòng cuối (paper không nêu số -> 50);
  trọng số: 3 nếu |ứng viên|/|log| ≤ 0.7 và |ứng viên| ≤ 500, ngược lại 1; dòng đánh dấu fail ("--- FAIL:", "Failures:")
  thêm 10, dòng từ khoá hoặc bắt đầu bằng '#' thêm 2, ứng viên khác thêm 1; ngưỡng θ = 1 nếu max = 1 hoặc ≤ 500 dòng có
  trọng số, ngược lại 3; mở rộng [i-4, i+6], gộp khối chồng nhau, xếp theo mật độ, lấy tham lam đến hết ngân sách.
Hai chỗ KHÁC paper (phải ghi khi báo cáo):
  - bỏ "log diff" với log run thành công (dữ liệu chỉ có run fail);
  - đầu ra là MỘT lá của cây nhãn (paper trả về báo cáo tự do); ngân sách BUDGET_CHARS ký tự thay cho 22.000 token.

Tập chấm: `human` = run có nhãn lá của người (vòng 161 + vòng mù 46, bỏ unclear/non_build), log nguyên vẹn;
`model` = PER_LEAF run/lá từ gói dữ liệu, log nguyên vẹn và đã che bằng chứng.
`--unknown` (02/11/2026): thay bằng 120 run quy tắc để `?` người gán (pipeline.unknown_review, vòng 1), chỉ lưu dự
đoán; nhãn người (gán mù / sau rà lại) chấm ở scripts/analysis/baseline_report.py.

    python -m project3.model.llm_logsage prepare --budget 40000   # -> data/results/llm_logsage/{sample.parquet, ds/}
    python -m project3.model.llm_logsage score DIR                # DIR = thư mục `kaggle b t download`
    python -m project3.model.llm_logsage prepare --unknown         # -> data/results/llm_logsage/unknown120/
    python -m project3.model.llm_logsage score DIR --unknown
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .config import PACK
from .abstain import UNK
from project3.pipeline.unknown_review import ITEMS
from .data import job_texts
from .labels import GROUP, PARENT
from .metrics import hier_scores
from .text import mask_text

OUT = Path("data/results/llm_logsage")
PER_LEAF, SEED, TAIL, M_BEFORE, N_AFTER = 25, 20261027, 50, 4, 6
# từ khoá của paper (mục Key Log Filtering)
KEYWORDS = re.compile(r"fatal|fail|panic|error|exit|kill|no such file|err:|err!|failures:|err |missing|exception|cannot",
                      re.I)
FAIL_MARK = re.compile(r"--- FAIL:|Failures:")
LEAVES = ["testfailure", "itestfailure", "compile", "buildconfig", "dependency", "quality", "doc", "license",
          "compatibility", "git", "crash", "androidsdk", "network", "flaky", "infra"]


def logsage_filter(text: str, budget: int) -> str:
    lines = text.splitlines()
    L = len(lines)
    if not L:
        return ""
    cand = {i for i, l in enumerate(lines) if KEYWORDS.search(l)} | set(range(max(0, L - TAIL), L))
    base = 3 if len(cand) / L <= 0.7 and len(cand) <= 500 else 1
    w = np.zeros(L)
    for i in cand:
        l = lines[i]
        w[i] = base + (10 if FAIL_MARK.search(l) else 2 if KEYWORDS.search(l) or l.startswith("#") else 1)
    theta = 1 if w.max() <= 1 or (w >= 1).sum() <= 500 else 3
    blocks = []
    for i in np.where(w >= theta)[0]:
        a, b = max(0, i - M_BEFORE), min(L, i + N_AFTER + 1)
        if blocks and a <= blocks[-1][1]:
            blocks[-1][1] = max(blocks[-1][1], b)
        else:
            blocks.append([a, b])
    ranked = sorted(blocks, key=lambda ab: -w[ab[0]:ab[1]].sum() / (ab[1] - ab[0]))
    keep, used = [], 0
    for a, b in ranked:
        size = sum(len(x) + 1 for x in lines[a:b])
        if used + size > budget:
            continue
        keep.append((a, b))
        used += size
    if not keep:  # khối dày nhất đã dài hơn ngân sách: giữ phần cuối của nó
        a, b = ranked[0]
        return "\n".join(lines[a:b])[-budget:]
    return "\n...\n".join("\n".join(lines[a:b]) for a, b in sorted(keep))


def human_labels() -> pd.DataFrame:
    """run_id -> lá người gán (vòng có gợi ý AI và vòng mù), bỏ unclear/non_build."""
    from openpyxl import load_workbook
    rows = []
    for d, xlsx, col in (("leaf_review", "docs/gan-la-2026-10-26.xlsx", "human_ai"),
                         ("leaf_review_blind", "docs/gan-la-mu-2026-10-26.xlsx", "human_blind")):
        key = {v["stt"]: int(k) for k, v in json.loads(Path(f"data/human_labels/{d}/key.json").read_text(
            encoding="utf-8")).items()}
        for r in load_workbook(xlsx).active.iter_rows(min_row=2, values_only=True):
            h = (r[7] or "").strip()
            if h in LEAVES:
                rows.append({"run_id": key[r[0]], "gold_leaf": h, "round": col})
    return pd.DataFrame(rows).drop_duplicates("run_id")


def prepare(budget: int, unknown: bool = False) -> None:
    out = OUT / "unknown120" if unknown else OUT
    (out / "ds").mkdir(parents=True, exist_ok=True)
    if unknown:
        runs = pd.read_parquet(UNK / "runs.parquet").drop_duplicates("run_id").set_index("run_id")
        ids = [it["run_id"] for it in map(json.loads, ITEMS.open(encoding="utf-8")) if it.get("round", 1) == 1]
        df = pd.DataFrame({"run_id": ids, "gold_leaf": "", "round": "", "set": "unknown", "test": "full", "key": ""})
    else:
        runs = pd.read_parquet(PACK / "runs.parquet").drop_duplicates("run_id").set_index("run_id")
        hum = human_labels()
        hum = hum[hum.run_id.isin(runs.index)].assign(set="human", test="full", key="")
        rng = np.random.default_rng(SEED)
        r = runs.reset_index()
        pick = pd.concat([g.iloc[rng.permutation(len(g))[:PER_LEAF]] for _, g in r.groupby("leaf")])
        model = pd.concat([pd.DataFrame({"run_id": pick.run_id, "gold_leaf": pick.leaf, "round": "", "set": "model",
                                         "test": t, "key": pick.key.fillna("")}) for t in ("full", "masked")])
        df = pd.concat([hum, model], ignore_index=True)
    jobs = job_texts(f"run_id IN ({','.join(map(str, df.run_id.unique()))})")
    df = df[df.run_id.isin(jobs)].copy()
    df["log"] = [logsage_filter("\n".join(mask_text(t, k) if s == "masked" else t for t in jobs[rid]), budget)
                 for rid, s, k in zip(df.run_id, df.test, df.key)]
    df["context"] = [f"workflow: {runs.workflow.get(x, '')} | job: {runs.failed_job_names.get(x, '')} | "
                     f"step: {runs.failed_steps.get(x, '')}" for x in df.run_id]
    df["row_id"] = [f"{s}|{t}|{x}" for s, t, x in zip(df["set"], df.test, df.run_id)]
    df.to_parquet(out / "sample.parquet", index=False)
    df[["row_id", "context", "log"]].to_json(out / "ds" / "sample.jsonl", orient="records", lines=True, force_ascii=False)
    slug = "p3-llm-unknown120" if unknown else "p3-llm-logsage"
    (out / "ds" / "dataset-metadata.json").write_text(json.dumps(
        {"title": slug, "id": f"ducanhpham2k5/{slug}", "licenses": [{"name": "other"}]}))
    chars = df.log.str.len() + df.context.str.len() + 3500  # + hướng dẫn trong prompt
    print(df.groupby(["set", "test"]).size().to_dict(), f"| {len(df)} lời gọi | ký tự log TB {int(df.log.str.len().mean())}"
          f" | ước tính token vào ~{int(chars.sum() / 3.5):,}")


def score(d: Path, unknown: bool = False) -> None:
    out = OUT / "unknown120" if unknown else OUT
    s = pd.read_parquet(out / "sample.parquet")
    pred = {}
    for f in d.rglob("*.run.json"):
        j = json.loads(f.read_text(encoding="utf-8"))
        rid = next((c["id"].rsplit("-", 1)[0] for c in j.get("conversations", []) if "|" in c["id"]), None)
        nr = (j.get("results") or [{}])[0].get("numericResult")
        v = None if nr is None else nr.get("value", 0)  # protobuf bỏ trường bằng 0 (= testfailure)
        if rid and v is not None:
            pred[rid] = LEAVES[int(v)] if 0 <= int(v) < len(LEAVES) else "unknown"
    s["pred"] = s.row_id.map(pred)
    print(f"có dự đoán: {s.pred.notna().sum()}/{len(s)}; unknown: {(s.pred == 'unknown').sum()}")
    s = s[s.pred.notna()]
    if unknown:  # chưa có nhãn trong sample: chỉ lưu dự đoán
        s.drop(columns=["log"]).to_parquet(out / "preds.parquet", index=False)
        print(s.pred.value_counts().to_dict())
        return
    rows = []
    for (st, t), g in s.groupby(["set", "test"]):
        sc = hier_scores(g.gold_leaf.tolist(), g.pred.tolist(), PARENT, GROUP)
        rows.append({"tập": st, "test": t, "n": len(g), "lá": sc["macroF1_l3"], "tầng 2": sc["macroF1_l2"],
                     "tầng 1": sc["macroF1_l1"], "acc lá": sc["acc_l3"]})
    res = pd.DataFrame(rows).round(3)
    (OUT / "score.md").write_text(res.to_string(index=False) + "\n", encoding="utf-8")
    s.to_parquet(OUT / "preds.parquet", index=False)
    print(res.to_string(index=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--budget", type=int, default=40_000, help="số ký tự tối đa sau lọc (paper: 22.000 token)")
    p.add_argument("--unknown", action="store_true", help="120 run `?` người gán thay cho tập chấm thường")
    q = sub.add_parser("score")
    q.add_argument("dir", type=Path)
    q.add_argument("--unknown", action="store_true")
    a = ap.parse_args()
    prepare(a.budget, a.unknown) if a.cmd == "prepare" else score(a.dir, a.unknown)
