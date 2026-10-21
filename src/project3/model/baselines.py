"""Baseline phân loại lỗi CI từ log (bước 2, docs/ket-qua-baseline-log-2026-10-18.md). Chạy ở máy local.

`all` — trên data/run_dataset, chia chéo repo (5 fold, train = 4 fold còn lại) và theo thời gian (split_time):
  rule   bộ quy tắc gold_label chạy lại trên đoạn log đã cắt (sanity) và trên log đã CHE dòng bằng chứng
  tfidf  TF-IDF + hồi quy logistic ở mức lá, suy ngược tầng 2 / tầng 1; train log nguyên vẹn (full) hoặc che 50% (mix50)
  -> results.json, report.md, preds.parquet
`fair` — so sánh công bằng với model.train: cùng chia (test k, val k+1 bỏ, train 3 fold), train che 50%; ba cấu hình
  A  30.000 ký tự cuối của mọi đoạn                       -> ảnh hưởng của dữ liệu train
  B  đúng 8 đoạn mô hình thấy, mỗi đoạn cắt như clip_chunk -> ảnh hưởng của lượng log
  C  như B + ngữ cảnh CI như mô hình                       -> đúng thông tin mô hình có
  -> fair.json, fair.md
Test nguyên vẹn và test đã che (xoá mọi dòng chứa dòng bằng chứng; mô phỏng run quy tắc không bắt được).

    python -m project3.model.baselines all --workers 8
    python -m project3.model.baselines fair
"""
import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from .config import BASELINE_OUT as OUT, MAX_RUN_CHARS, PACK, SEED
from .data import load_pack, load_run_logs, mix50, train_folds
from .metrics import hier_scores
from .text import ci_context, clip_chunk, mask_text
from .tfidf import make_classifier, make_vectorizer


def label_maps():
    """(parent, group) của bộ quy tắc hiện hành: lá -> loại tầng 2, loại tầng 2 -> nhóm tầng 1."""
    from project3.crawl.build_log_labels import GROUP
    from project3.crawl.fine_labels import PARENT
    return PARENT, GROUP


def rule_one(args):
    from project3.crawl.fine_labels import subtype
    from project3.crawl.gold_labels import gold_label
    _, group = label_maps()
    run_id, texts, key, workflow, names = args
    out = {}
    for name, ts in (("full", texts), ("masked", [mask_text(t, key) for t in texts])):
        lab, ev = gold_label(ts)
        out[name] = (subtype(lab, ev, workflow or "", names or "") or lab) if lab in group else lab
    return run_id, out


def tail(s: str) -> str:
    return s[-MAX_RUN_CHARS:]


def run_all(workers: int) -> None:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    parent, group = label_maps()
    runs, jobs = load_run_logs()
    print(f"{len(runs)} run có nhãn ({time.time() - t0:.0f}s)", flush=True)
    full = {r: "\n".join(jobs[r]) for r in runs.run_id}
    masked = {r: "\n".join(mask_text(t, k) for t in jobs[r]) for r, k in zip(runs.run_id, runs.key)}
    removed = np.mean([len(masked[r]) < len(full[r]) for r in runs.run_id])
    print(f"che bằng chứng: {removed:.1%} run bị xoá ít nhất một dòng", flush=True)

    with ProcessPoolExecutor(workers) as ex:
        rule = dict(ex.map(rule_one, ((r.run_id, jobs[r.run_id], r.key, r.workflow, r.failed_job_names)
                                      for r in runs.itertuples()), chunksize=200))
    runs["rule_full"] = [rule[r]["full"] for r in runs.run_id]
    runs["rule_masked"] = [rule[r]["masked"] for r in runs.run_id]
    print(f"quy tắc xong ({time.time() - t0:.0f}s)", flush=True)

    mix = mix50(runs.run_id)
    splits = [(f"repo_fold={k}", runs.repo_fold != k, runs.repo_fold == k) for k in range(5)]
    splits.append(("time", runs.split_time == "train", runs.split_time == "test"))
    preds = []
    for name, tr, te in splits:
        tr_ids, te_ids = runs.run_id[tr].tolist(), runs.run_id[te].tolist()
        y_tr = runs.leaf[tr].tolist()
        for variant in ("full", "mix50"):
            docs = [tail(masked[r] if variant == "mix50" and mix[r] else full[r]) for r in tr_ids]
            vec = make_vectorizer()
            clf = make_classifier(workers).fit(vec.fit_transform(docs), y_tr)
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
        results[f"{scheme}|{model}|{test}"] = hier_scores(g.leaf.tolist(), g.pred.tolist(), parent, group)  # gộp 5 fold
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


def run_fair() -> None:
    t0 = time.time()
    parent, group = label_maps()
    runs, chunks, _ = load_pack(PACK)
    _, jobs_all = load_run_logs()
    ctx = {r: ci_context(w, j, s) for r, w, j, s in
           zip(runs.run_id, runs.workflow.fillna(""), runs.failed_job_names.fillna(""), runs.failed_steps.fillna(""))}
    key = dict(zip(runs.run_id, runs.key.fillna("")))

    def text(r, cfg, masked):
        k = key[r] if masked else ""
        if cfg == "A":
            return "\n".join(mask_text(t, k) for t in jobs_all[r])[-MAX_RUN_CHARS:]
        body = "\n".join(clip_chunk(mask_text(t, k)) for job in chunks[r] for t in job)
        return body if cfg == "B" else ctx[r] + "\n" + body

    mix = mix50(runs.run_id)
    res, rows = {}, []
    for cfg in ("A", "B", "C"):
        for k in range(5):
            te = runs[runs.repo_fold == k]
            tr = runs[runs.repo_fold.isin(train_folds(k))]
            vec = make_vectorizer()
            clf = make_classifier(8).fit(vec.fit_transform([text(r, cfg, mix[r]) for r in tr.run_id]), tr.leaf)
            for t in ("full", "masked"):
                p = clf.predict(vec.transform([text(r, cfg, t == "masked") for r in te.run_id]))
                s = hier_scores(te.leaf.tolist(), p.tolist(), parent, group)
                res[f"{cfg}|fold{k}|{t}"] = s
                rows.append({"cfg": cfg, "fold": k, "test": t, "l3": s["macroF1_l3"], "l2": s["macroF1_l2"],
                             "l1": s["macroF1_l1"]})
            print(f"  {cfg} fold {k} ({time.time() - t0:.0f}s)", flush=True)
    df = pd.DataFrame(rows)
    (OUT / "fair.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    piv = df.pivot_table(index=["cfg", "test"], columns="fold", values="l2")
    piv["TB"] = piv.mean(axis=1)
    (OUT / "fair.md").write_text("macro-F1 tầng 2\n\n" + piv.round(3).to_string() + "\n\nmacro-F1 lá (TB 5 fold)\n\n"
                                 + df.groupby(["cfg", "test"])[["l3", "l2", "l1"]].mean().round(3).to_string() + "\n",
                                 encoding="utf-8")
    print((OUT / "fair.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("all").add_argument("--workers", type=int, default=8)
    sub.add_parser("fair")
    a = ap.parse_args()
    run_all(a.workers) if a.cmd == "all" else run_fair()
