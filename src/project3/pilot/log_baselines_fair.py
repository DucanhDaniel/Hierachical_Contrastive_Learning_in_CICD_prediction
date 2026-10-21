"""TF-IDF so sánh công bằng với mô hình đọc log (log_hcl, kernel p3-log-hcl), 19/10/2026.

Cùng chia như log_hcl: test = repo_fold k, val = fold k+1 (bỏ, TF-IDF không chọn epoch), train = 3 fold còn lại;
train che bằng chứng 50% (cùng seed cách chọn khác nhau, cùng tỉ lệ). Ba cấu hình tách nguyên nhân chênh lệch:
  A  train 3 fold, đầu vào 30.000 ký tự cuối của mọi đoạn (như log_baselines)       -> ảnh hưởng của dữ liệu train
  B  train 3 fold, đầu vào = đúng 8 đoạn mô hình thấy, mỗi đoạn cắt như clip_chunk  -> ảnh hưởng của lượng log
  C  như B + chuỗi ngữ cảnh "workflow | job | step fail" như mô hình                 -> đúng thông tin mô hình có

    python -m project3.pilot.log_baselines_fair   # -> data/results/log_baselines/fair.json, fair.md
"""
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier

from project3.pilot.log_baselines import MAX_RUN_CHARS, OUT, SEED, load as load_all, mask_text, scores
from project3.pilot.log_hcl import clip_chunk, load as load_pack

PACK = Path("data/kaggle_log_ds")


def main() -> None:
    t0 = time.time()
    runs, chunks, _ = load_pack(PACK)
    _, jobs_all = load_all()
    ctx = {r: f"workflow: {w} | job: {j} | step: {s}" for r, w, j, s in
           zip(runs.run_id, runs.workflow.fillna(""), runs.failed_job_names.fillna(""), runs.failed_steps.fillna(""))}
    key = dict(zip(runs.run_id, runs.key.fillna("")))

    def text(r, cfg, masked):
        k = key[r] if masked else ""
        if cfg == "A":
            return "\n".join(mask_text(t, k) for t in jobs_all[r])[-MAX_RUN_CHARS:]
        body = "\n".join(clip_chunk(mask_text(t, k)) for job in chunks[r] for t in job)
        return body if cfg == "B" else ctx[r] + "\n" + body

    rng = random.Random(SEED)
    mix = {r: rng.random() < 0.5 for r in runs.run_id}
    res, rows = {}, []
    for cfg in ("A", "B", "C"):
        for k in range(5):
            te = runs[runs.repo_fold == k]
            tr = runs[~runs.repo_fold.isin([k, (k + 1) % 5])]
            vec = TfidfVectorizer(token_pattern=r"(?u)\b[A-Za-z_][A-Za-z0-9_]{1,40}\b", ngram_range=(1, 2), min_df=5,
                                  max_df=0.5, max_features=300_000, sublinear_tf=True, dtype=np.float32)
            X = vec.fit_transform([text(r, cfg, mix[r]) for r in tr.run_id])
            clf = SGDClassifier(loss="log_loss", alpha=2e-6, max_iter=30, tol=None, class_weight="balanced",
                                random_state=SEED, n_jobs=8).fit(X, tr.leaf)
            for t in ("full", "masked"):
                p = clf.predict(vec.transform([text(r, cfg, t == "masked") for r in te.run_id]))
                s = scores(te.leaf.tolist(), p.tolist())
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
    main()
