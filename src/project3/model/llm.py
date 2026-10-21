"""Baseline LLM phân loại lỗi CI từ log (20/10/2026, docs/ket-qua-baseline-llm-2026-10-20.md): CHỈ để so sánh,
không phải nguồn nhãn (C-02). Chạy ở máy local; LLM chạy trên Kaggle Benchmarks (scripts/kaggle/llm_baseline/task*.py).

Hai tập chấm:
  human  ~200 run vòng gán mù 10/10 (nhãn người tầng 2 sau phân xử, bỏ 'unclear'), log nguyên vẹn
  model  PER_LEAF run mỗi lá lấy từ gói dữ liệu (nhãn quy tắc), cả log nguyên vẹn và log đã che bằng chứng;
         so trực tiếp với dự đoán của quy tắc / TF-IDF A / mô hình lai trên đúng các run đó (fold test của run)
Đầu vào cho LLM: ngữ cảnh CI + MAX_CHARS ký tự cuối của các đoạn log (như mô hình đọc), không lọc theo chữ ERROR.

    python -m project3.model.llm prepare     # -> data/results/llm_baseline/sample.parquet + ds/sample.jsonl (dataset p3-llm-sample)
    python -m project3.model.llm score DIR   # DIR = thư mục `kaggle b t download`
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

from .config import BASELINE_OUT, HUMAN_LABELS, LLM_OUT as OUT, LOG_MODEL_OUT, PACK, RUN_DATASET
from .data import job_texts
from .labels import LabelTree
from .text import mask_text

MAX_CHARS, PER_LEAF, SEED = 12_000, 25, 20261020
# chỉ số lá LLM trả về; phải trùng LEAVES trong scripts/kaggle/llm_baseline/task*.py (tests/test_model.py kiểm tra)
LEAVES = ["testfailure", "itestfailure", "compile", "buildconfig", "dependency", "quality", "doc", "license",
          "compatibility", "git", "crash", "androidsdk", "network", "flaky", "infra"]
# mô hình so cùng LLM trên tập model: (tên, thư mục trong LOG_MODEL_OUT, biến thể)
COMPARE = (("lai CE", "v3_tfidf", "ce"), ("lai + sampler HCL", "v4_rare", "hcl"))


def run_texts(run_ids) -> dict:
    jobs = job_texts(f"run_id IN ({','.join(map(str, run_ids))})")
    return {k: "\n".join(v) for k, v in jobs.items()}


def prepare() -> None:
    import duckdb
    (OUT / "ds").mkdir(parents=True, exist_ok=True)
    meta = duckdb.sql(f"SELECT run_id, repository, workflow, failed_job_names FROM '{RUN_DATASET / 'runs.parquet'}'").df()
    meta = meta.drop_duplicates("run_id").set_index("run_id")
    # tập human: nhãn mù, ghi đè bằng kết quả phân xử
    lab = {}
    for f in ("labels.jsonl", "adjudication.jsonl"):
        for l in open(HUMAN_LABELS / f, encoding="utf-8"):
            d = json.loads(l)
            lab[d["run_id"]] = d["label"]
    human = pd.DataFrame({"run_id": list(lab), "gold_l2": list(lab.values())})
    human = human[(human.gold_l2 != "unclear") & human.run_id.isin(meta.index)]
    human["set"], human["test"], human["gold_leaf"], human["key"] = "human", "full", "", ""
    # tập model: phân tầng theo lá từ dữ liệu đã đóng gói
    runs = pd.read_parquet(PACK / "runs.parquet").drop_duplicates("run_id")
    rng = np.random.default_rng(SEED)
    pick = pd.concat([g.iloc[rng.permutation(len(g))[:PER_LEAF]] for _, g in runs.groupby("leaf")])
    model = pd.concat([pick.assign(test=t) for t in ("full", "masked")])
    model = pd.DataFrame({"run_id": model.run_id, "gold_l2": model.label_l2, "set": "model", "test": model.test,
                          "gold_leaf": model.leaf, "key": model.key.fillna(""), "steps": model.failed_steps.fillna("")})
    df = pd.concat([human, model], ignore_index=True)
    texts = run_texts(df.run_id.unique())
    df = df[df.run_id.isin(texts)].copy()
    df["log"] = [(mask_text(texts[r], k) if t == "masked" else texts[r])[-MAX_CHARS:]
                 for r, t, k in zip(df.run_id, df.test, df.key)]
    df["context"] = [f"workflow: {meta.workflow.get(r, '')} | job: {meta.failed_job_names.get(r, '')}"
                     + (f" | step: {s}" if isinstance(s, str) and s else "") for r, s in zip(df.run_id, df.get("steps"))]
    df["row_id"] = [f"{s}|{t}|{r}" for s, t, r in zip(df["set"], df.test, df.run_id)]
    cols = ["row_id", "set", "test", "run_id", "gold_l2", "gold_leaf", "context", "log"]
    df[cols].to_parquet(OUT / "sample.parquet", index=False)  # đủ cột, để chấm
    # Kaggle Benchmarks không có pyarrow -> dataset dùng JSONL
    df[["row_id", "context", "log"]].to_json(OUT / "ds" / "sample.jsonl", orient="records", lines=True, force_ascii=False)
    (OUT / "ds" / "dataset-metadata.json").write_text(json.dumps(
        {"title": "p3-llm-sample", "id": "ducanhpham2k5/p3-llm-sample", "licenses": [{"name": "other"}]}))
    print(df.groupby(["set", "test"]).size().to_dict(), "| ký tự log TB", int(df.log.str.len().mean()))


def model_preds(run_ids) -> pd.DataFrame:
    """Dự đoán của các mô hình khác trên cùng run (fold test của run): quy tắc, TF-IDF A, các mô hình trong COMPARE."""
    runs = pd.read_parquet(PACK / "runs.parquet").drop_duplicates("run_id").set_index("run_id")
    classes = sorted(runs.leaf.unique())  # cùng thứ tự cột như model.tfidf
    rows = []
    b = pd.read_parquet(BASELINE_OUT / "preds.parquet")
    b = b[(b.model == "rule") & b.split.str.startswith("repo_fold") & b.run_id.isin(run_ids)]
    rows += [("quy tắc", t, r, p) for t, r, p in zip(b.test, b.run_id, b.pred)]
    for k in range(5):
        f = pd.read_parquet(PACK / f"tfidf_fold{k}.parquet").drop_duplicates("run_id").set_index("run_id")
        te = [r for r in run_ids if r in runs.index and runs.repo_fold[r] == k]
        for t in ("full", "masked"):
            rows += [("TF-IDF A", t, r, classes[int(np.argmax(f[t][r]))]) for r in te]
        for name, d, v in COMPARE:
            q = pd.read_parquet(LOG_MODEL_OUT / d / f"results_fold{k}.preds.parquet")
            q = q[(q.variant == v) & q.run_id.isin(te)]
            rows += [(name, t, r, p) for t, r, p in zip(q.test, q.run_id, q.pred)]
    return pd.DataFrame(rows, columns=["model", "test", "run_id", "pred"]).drop_duplicates(["model", "test", "run_id"])


def metrics(y, p, par) -> dict:
    y2, p2 = [par.get(x, x) for x in y], [par.get(x, x) for x in p]
    return {"n": len(y), "acc_lá": np.mean(np.array(y) == np.array(p)),
            "F1_lá": f1_score(y, p, labels=sorted(set(y)), average="macro", zero_division=0),
            "acc_t2": np.mean(np.array(y2) == np.array(p2)),
            "F1_t2": f1_score(y2, p2, labels=sorted(set(y2)), average="macro", zero_division=0)}


def score(d: Path) -> None:
    """Gộp kết quả `kaggle b t download` (mỗi *.run.json một dòng: chỉ số lá, -1 = unknown) và so với nhãn + mô hình."""
    import duckdb
    s = pd.read_parquet(OUT / "sample.parquet")
    tree = LabelTree.load(PACK / "label_tree.json")
    par = {**tree.parent, "infra": "infra", "unknown": "unknown"}
    pred = {}
    for f in d.rglob("*.run.json"):
        j = json.loads(f.read_text(encoding="utf-8"))
        rid = next((c["id"].rsplit("-", 1)[0] for c in j.get("conversations", []) if "|" in c["id"]), None)
        res = j.get("results") or [{}]
        nr = res[0].get("numericResult")
        v = None if nr is None else nr.get("value", 0)  # protobuf bỏ trường bằng 0 (= testfailure)
        if rid and v is not None:
            pred[rid] = LEAVES[int(v)] if 0 <= int(v) < len(LEAVES) else "unknown"
    s["llm"] = s.row_id.map(pred)
    print(f"có dự đoán LLM: {s.llm.notna().sum()}/{len(s)}; unknown: {(s.llm == 'unknown').sum()}")
    s = s[s.llm.notna()]
    out = []
    h = s[s["set"] == "human"]
    rule = duckdb.sql(f"SELECT run_id, coalesce(label_l2, '?') l2 FROM '{RUN_DATASET / 'runs.parquet'}' "
                      f"WHERE run_id IN ({','.join(map(str, h.run_id))})").df().drop_duplicates("run_id").set_index("run_id").l2
    for name, p2 in (("LLM", [par.get(x, x) for x in h.llm]), ("quy tắc", h.run_id.map(rule).fillna("?").tolist())):
        y = h.gold_l2.tolist()
        out.append({"tập": "người gán (tầng 2)", "test": "full", "mô hình": name, "n": len(y),
                    "acc_t2": np.mean(np.array(y) == np.array(p2)),
                    "F1_t2": f1_score(y, p2, labels=sorted(set(y)), average="macro", zero_division=0)})
    m = s[s["set"] == "model"]
    other = model_preds(m.run_id.unique())
    for t in ("full", "masked"):
        mt = m[m.test == t]
        if mt.empty:
            continue
        out.append({"tập": "nhãn quy tắc", "test": t, "mô hình": "LLM", **metrics(mt.gold_leaf.tolist(), mt.llm.tolist(), par)})
        for name, g in other[other.test == t].groupby("model"):
            g = g.merge(mt[["run_id", "gold_leaf"]], on="run_id")
            out.append({"tập": "nhãn quy tắc", "test": t, "mô hình": name, **metrics(g.gold_leaf.tolist(), g.pred.tolist(), par)})
    r = pd.DataFrame(out)
    print(r.round(3).to_string(index=False))
    s.to_parquet(OUT / "llm_preds.parquet", index=False)
    r.to_csv(OUT / "scores.csv", index=False)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare")
    sub.add_parser("score").add_argument("dir", type=Path)
    a = ap.parse_args()
    prepare() if a.cmd == "prepare" else score(a.dir)
