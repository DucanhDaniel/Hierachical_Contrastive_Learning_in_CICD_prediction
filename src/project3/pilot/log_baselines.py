"""Baseline phân loại lỗi CI từ log (bước 2, docs/huong-moi-phan-loai-sau-ci.md), trên data/run_dataset.

So sánh trên run fail có nhãn quy tắc, chia chéo repo (5 fold theo repo_fold) và theo thời gian (split_time):
  - rule:   bộ quy tắc gold_label chạy lại trên đoạn log đã cắt (sanity) và trên log đã CHE dòng bằng chứng
  - tfidf:  TF-IDF (từ + cặp từ) + hồi quy logistic (SGD, log-loss, class_weight=balanced) ở mức lá tầng 3,
            suy ngược tầng 2 / tầng 1; hai cách train: log nguyên vẹn, hoặc che bằng chứng ở 50% mẫu train
Đo trên test nguyên vẹn và test đã che. Test đã che mô phỏng run mà quy tắc không bắt được (nhóm `?`):
xoá mọi dòng chứa dòng bằng chứng của quy tắc, phần còn lại của log giữ nguyên.

    python -m project3.pilot.log_baselines         # -> data/results/log_baselines/{results.json,report.md,preds.parquet}
"""
import argparse
import json
import random
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import f1_score

from project3.crawl.build_log_labels import GROUP
from project3.pilot.fine_labels import PARENT, subtype
from project3.pipeline.run_dataset import clean

DS = Path("data/run_dataset")
OUT = Path("data/results/log_baselines")
MAX_RUN_CHARS = 30_000  # giữ phần cuối log của run (giới hạn độ dài, không lọc theo từ khoá)
SEED = 20261018


def leaf_of(row) -> str:
    return row.label_l3 if isinstance(row.label_l3, str) else row.label_l2  # infra không có lá -> 'infra'


def tier2(leaf: str) -> str:
    return PARENT.get(leaf, leaf)


def mask_text(text: str, key: str) -> str:
    return "\n".join(l for l in text.splitlines() if key not in l) if key else text


def load() -> tuple[pd.DataFrame, dict]:
    runs = duckdb.sql(f"""SELECT run_id, repository, workflow, failed_job_names, label_l2, label_l3, evidence,
                                 repo_fold, split_time FROM '{DS / "runs.parquet"}'
                          WHERE label_l2 IN ({",".join(repr(k) for k in GROUP)}) AND log_jobs > 0""").df()
    ch = duckdb.sql(f"""SELECT run_id, job_id, string_agg(text, chr(10) ORDER BY chunk_idx) txt
                        FROM '{DS / "chunks.parquet"}' WHERE run_id IN (SELECT run_id FROM runs)
                        GROUP BY run_id, job_id ORDER BY run_id, job_id""").df()
    jobs = defaultdict(list)
    for r in ch.itertuples():
        jobs[r.run_id].append(r.txt)
    runs["leaf"] = [leaf_of(r) for r in runs.itertuples()]
    runs["key"] = [clean(e)[:120].strip() for e in runs.evidence.fillna("")]
    return runs, jobs


def rule_one(args):
    from project3.crawl.gold_labels import gold_label
    run_id, texts, key, workflow, names = args
    out = {}
    for name, ts in (("full", texts), ("masked", [mask_text(t, key) for t in texts])):
        lab, ev = gold_label(ts)
        out[name] = (subtype(lab, ev, workflow or "", names or "") or lab) if lab in GROUP else lab
    return run_id, out


def scores(y_true_leaf, y_pred_leaf) -> dict:
    t2 = [tier2(x) for x in y_true_leaf]
    p2 = [tier2(x) if x in PARENT or x in GROUP else "?" for x in y_pred_leaf]
    t1 = [GROUP[x] for x in t2]
    p1 = [GROUP.get(x, "?") for x in p2]
    labels3 = sorted(set(y_true_leaf))
    return {"n": len(y_true_leaf),
            "acc_l3": float(np.mean(np.array(y_true_leaf) == np.array(y_pred_leaf))),
            "macroF1_l3": f1_score(y_true_leaf, y_pred_leaf, labels=labels3, average="macro", zero_division=0),
            "macroF1_l2": f1_score(t2, p2, labels=sorted(set(t2)), average="macro", zero_division=0),
            "macroF1_l1": f1_score(t1, p1, labels=sorted(set(t1)), average="macro", zero_division=0),
            "F1_l3": dict(zip(labels3, map(float, f1_score(y_true_leaf, y_pred_leaf, labels=labels3, average=None,
                                                            zero_division=0))))}


def tail(s: str) -> str:
    return s[-MAX_RUN_CHARS:]


def main(workers: int) -> None:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    runs, jobs = load()
    print(f"{len(runs)} run có nhãn ({time.time() - t0:.0f}s)", flush=True)
    full = {r: "\n".join(jobs[r]) for r in runs.run_id}
    masked = {r: "\n".join(mask_text(t, k) for t in jobs[r]) for r, k in zip(runs.run_id, runs.key)}
    removed = np.mean([len(masked[r]) < len(full[r]) for r in runs.run_id])
    print(f"che bằng chứng: {removed:.1%} run bị xoá ít nhất một dòng", flush=True)

    # quy tắc trên đoạn log đã cắt (sanity) và trên log đã che
    with ProcessPoolExecutor(workers) as ex:
        rule = dict(ex.map(rule_one, ((r.run_id, jobs[r.run_id], r.key, r.workflow, r.failed_job_names)
                                      for r in runs.itertuples()), chunksize=200))
    runs["rule_full"] = [rule[r]["full"] for r in runs.run_id]
    runs["rule_masked"] = [rule[r]["masked"] for r in runs.run_id]
    print(f"quy tắc xong ({time.time() - t0:.0f}s)", flush=True)

    rng = random.Random(SEED)
    mix = {r: rng.random() < 0.5 for r in runs.run_id}
    splits = [(f"repo_fold={k}", runs.repo_fold != k, runs.repo_fold == k) for k in range(5)]
    splits.append(("time", runs.split_time == "train", runs.split_time == "test"))
    preds = []
    for name, tr, te in splits:
        tr_ids, te_ids = runs.run_id[tr].tolist(), runs.run_id[te].tolist()
        y_tr = runs.leaf[tr].tolist()
        for variant in ("full", "mix50"):
            docs = [tail(masked[r] if variant == "mix50" and mix[r] else full[r]) for r in tr_ids]
            vec = TfidfVectorizer(token_pattern=r"(?u)\b[A-Za-z_][A-Za-z0-9_]{1,40}\b", ngram_range=(1, 2),
                                  min_df=5, max_df=0.5, max_features=300_000, sublinear_tf=True, dtype=np.float32)
            X = vec.fit_transform(docs)
            clf = SGDClassifier(loss="log_loss", alpha=2e-6, max_iter=30, tol=None, class_weight="balanced",
                                random_state=SEED, n_jobs=workers).fit(X, y_tr)
            for test_kind, src in (("full", full), ("masked", masked)):
                p = clf.predict(vec.transform([tail(src[r]) for r in te_ids]))
                preds.append(pd.DataFrame({"split": name, "model": f"tfidf_{variant}", "test": test_kind,
                                           "run_id": te_ids, "pred": p}))
            print(f"  {name} tfidf_{variant} ({time.time() - t0:.0f}s)", flush=True)
        for test_kind in ("full", "masked"):
            preds.append(pd.DataFrame({"split": name, "model": "rule", "test": test_kind, "run_id": te_ids,
                                       "pred": runs[f"rule_{test_kind}"][te].tolist()}))
    P = pd.concat(preds).merge(runs[["run_id", "leaf", "repository"]], on="run_id")
    P.to_parquet(OUT / "preds.parquet", index=False)

    results = {}
    for (scheme, model, test), g in P.assign(scheme=P.split.str.startswith("repo").map({True: "cross_repo", False: "time"})) \
            .groupby(["scheme", "model", "test"]):
        results[f"{scheme}|{model}|{test}"] = scores(g.leaf.tolist(), g.pred.tolist())  # gộp dự đoán 5 fold
    meta = {"runs": len(runs), "masked_runs_share": float(removed), "max_run_chars": MAX_RUN_CHARS, "seed": SEED,
            "leaf_counts": runs.leaf.value_counts().to_dict(), "minutes": round((time.time() - t0) / 60, 1)}
    (OUT / "results.json").write_text(json.dumps({"meta": meta, "results": results}, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    lines = ["| Chia | Mô hình | Test | acc lá | macro-F1 lá | macro-F1 tầng 2 | macro-F1 tầng 1 |", "|---|---|---|---:|---:|---:|---:|"]
    for k, v in results.items():
        s, m, t = k.split("|")
        lines.append(f"| {s} | {m} | {t} | {v['acc_l3']:.3f} | {v['macroF1_l3']:.3f} | {v['macroF1_l2']:.3f} | {v['macroF1_l1']:.3f} |")
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(json.dumps(meta, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    main(ap.parse_args().workers)
