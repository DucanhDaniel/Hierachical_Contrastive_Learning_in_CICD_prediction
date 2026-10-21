"""Mức trần "đọc và suy luận trên diff": cho LLM đọc diff của commit ở P3 (ngay sau commit pass) rồi đoán pass/fail + loại lỗi.

So trên cùng một mẫu với mô hình history và TF-IDF diff của pilot (cùng cách chia theo thời gian, train trên phần đầu).
Mẫu cân bằng (n_pass commit pass, n_fail commit fail; ưu tiên lấy đủ compile/lint) nên dùng ROC-AUC, không phụ
thuộc tỉ lệ fail. Phản hồi được cache tại data/processed/llm_probe/<sha>.json.

    uv run --group exp python -m project3.pilot.llm_probe --model qwen3.8-max
"""
import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sklearn.metrics import f1_score, roc_auc_score

from .experiment import HIST, SEED, STATS, Featurizer, fit_binary, load, lr

API = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"
DIFF_CHARS = 40_000
SYSTEM = """You are an expert Java build engineer. You review a code change to an Apache Java/JVM project before CI runs.
CI builds with Maven or Gradle and runs: compilation; static checks (checkstyle, spotless formatting, license headers/RAT,
API compatibility checks); then unit and integration tests. The previous commit in this branch passed CI.
Predict whether CI will fail on this change because of the code (ignore infrastructure/network problems).
Reason about the change itself: missing or mismatched symbols, signature changes without updating callers, imports,
formatting/style violations, license headers, behavior changes that break existing tests, new tests that look wrong.
Most changes pass, so only give a high probability when you see concrete evidence.
Answer with JSON only: {"p_fail": <0..1>, "type": "compile"|"lint"|"test", "evidence": "<one short sentence>"}
where "type" is the most likely failure type IF it fails."""


def api_key() -> str:
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("QWEN_API_KEY="):
            return line.split("=", 1)[1].strip().strip("'\"")
    raise SystemExit("thiếu QWEN_API_KEY trong .env")


def shorten(diff: str, limit: int) -> str:
    """Giữ đầu mỗi file theo tỉ lệ để diff lớn vẫn thấy được mọi file thay đổi."""
    if len(diff) <= limit:
        return diff
    files = re.split(r"(?=^diff --git )", diff, flags=re.M)
    per = max(800, limit // max(1, len(files)))
    return "".join(f if len(f) <= per else f[:per] + "\n... [truncated]\n" for f in files)[:limit]


def ask(row, model: str, key: str, cache: Path) -> dict:
    path = cache / f"{row.head_sha}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    diff = shorten(Path(row.path).read_text(encoding="utf-8", errors="ignore"), DIFF_CHARS)
    user = (f"Repository: {row.repository} ({'pull request' if row.is_pr else 'push to main branch'})\n"
            f"Files changed: {int(row.n_files)}, +{int(row.n_add)} -{int(row.n_del)}\n\n```diff\n{diff}\n```")
    for attempt in range(4):
        try:
            r = requests.post(API, headers={"Authorization": f"Bearer {key}"}, timeout=600, json={
                "model": model, "max_tokens": 8000,
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]})
            r.raise_for_status()
            j = r.json()
            text = j["choices"][0]["message"]["content"]
            m = re.search(r"\{.*\}", text, re.S)
            ans = json.loads(m.group(0)) if m else {}
            out = {"p_fail": float(ans.get("p_fail", np.nan)), "type": ans.get("type"), "evidence": ans.get("evidence"),
                   "usage": j.get("usage"), "raw": text[-500:]}
            path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
            return out
        except Exception as e:  # lỗi mạng, rate limit, JSON hỏng
            err = str(e)[:200]
    return {"p_fail": np.nan, "type": None, "error": err}


def auc_ci(y, a, b=None, n=2000):
    """ROC-AUC của a (và hiệu a - b nếu có b) với bootstrap theo cặp."""
    rng = np.random.default_rng(SEED)
    vals = []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        if 0 < y[i].sum() < len(i):
            vals.append(roc_auc_score(y[i], a[i]) - (roc_auc_score(y[i], b[i]) if b is not None else 0))
    point = roc_auc_score(y, a) - (roc_auc_score(y, b) if b is not None else 0)
    return round(point, 3), [round(float(np.percentile(vals, 2.5)), 3), round(float(np.percentile(vals, 97.5)), 3)]


def main(table, diffs_csv, repos, model, n_pass, n_fail, workers, out):
    df = load(table, diffs_csv, repos)
    cut = int(len(df) * 0.7)
    train, test = df.iloc[:cut], df.iloc[cut:].copy()
    rc = [f"repo_{r.split('/')[1]}" for r in repos]
    test["s_history"], _ = fit_binary(train, test, False, HIST + STATS, rc)
    test["s_diff"], _ = fit_binary(train, test, True, STATS, rc)

    # tầng 2 bằng TF-IDF, train trên commit fail của phần train
    ftr = train[train.y == 1].assign(lab=lambda x: x.label.replace({"dependency": "compile"}))
    ftr = ftr[ftr.lab.isin(["compile", "lint", "test"])]
    feat = Featurizer(True, STATS + rc)
    t2 = lr(1.0, multi=True).fit(feat.fit_transform(ftr), ftr.lab)

    p3 = test[test.prev_fail == 0]
    rng = np.random.default_rng(SEED)
    fails = p3[p3.y == 1].assign(lab=lambda x: x.label.replace({"dependency": "compile"}))
    pick = [fails[fails.lab == k] for k in ("compile", "lint")]
    pick = [g.sample(min(len(g), n_fail // 3), random_state=SEED) for g in pick]
    rest = fails[fails.lab == "test"].sample(n_fail - sum(map(len, pick)), random_state=SEED)
    passes = p3[p3.y == 0].sample(n_pass, random_state=SEED)
    sample = pd.concat([*pick, rest, passes]).sample(frac=1, random_state=SEED).reset_index(drop=True)
    sample["t2_tfidf"] = t2.predict(feat.transform(sample))
    print(f"mẫu {len(sample)}: pass {n_pass}, fail {sample.y.sum()} {sample[sample.y == 1].lab.value_counts().to_dict()}", flush=True)

    cache = Path("data/processed/llm_probe") / model
    cache.mkdir(parents=True, exist_ok=True)
    key = api_key()
    with ThreadPoolExecutor(workers) as ex:
        answers = list(ex.map(lambda r: ask(r, model, key, cache), sample.itertuples()))
    sample["s_llm"] = [a.get("p_fail", np.nan) for a in answers]
    sample["t2_llm"] = [a.get("type") for a in answers]
    ok = sample.s_llm.notna()
    s = sample[ok]
    y = s.y.values
    tokens = sum((a.get("usage") or {}).get("total_tokens", 0) for a in answers)
    res = {"model": model, "n": int(ok.sum()), "failed_calls": int((~ok).sum()), "tokens": tokens,
           "roc_auc": {k: auc_ci(y, s[c].values) for k, c in
                       (("llm", "s_llm"), ("history", "s_history"), ("diff_tfidf", "s_diff"))},
           "llm_minus_history": auc_ci(y, s.s_llm.values, s.s_history.values),
           "llm_minus_diff": auc_ci(y, s.s_llm.values, s.s_diff.values)}
    # LLM + history: trung bình hạng (không cần học thêm tham số)
    combo = (s.s_llm.rank() + s.s_history.rank()).values
    res["roc_auc"]["llm+history (rank avg)"] = auc_ci(y, combo)
    res["llm_p_fail_by_class"] = s.groupby(s.y.map({0: "pass", 1: "fail"})).s_llm.describe()[["mean", "50%"]].round(3).to_dict()
    f = s[s.y == 1]
    labels = sorted(f.lab.unique())
    res["tier2"] = {"counts": f.lab.value_counts().to_dict(),
                    "llm_macro_f1": round(f1_score(f.lab, f.t2_llm.fillna("test"), labels=labels, average="macro"), 3),
                    "tfidf_macro_f1": round(f1_score(f.lab, f.t2_tfidf, labels=labels, average="macro"), 3),
                    "llm_per_class": dict(zip(labels, np.round(f1_score(f.lab, f.t2_llm.fillna("test"), labels=labels, average=None), 3))),
                    "tfidf_per_class": dict(zip(labels, np.round(f1_score(f.lab, f.t2_tfidf, labels=labels, average=None), 3)))}
    sample.drop(columns=[c for c in sample.columns if c.startswith("txt_")]).to_csv(out.with_suffix(".csv"), index=False)
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", default="data/processed/commits_pilot.parquet")
    ap.add_argument("--diffs", default="data/processed/pilot_diffs.csv")
    ap.add_argument("--repos", nargs="+", default=["apache/druid", "apache/paimon"])
    ap.add_argument("--model", default="qwen3.8-max")
    ap.add_argument("--n-pass", type=int, default=100)
    ap.add_argument("--n-fail", type=int, default=100)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", type=Path, default=Path("data/processed/llm_probe_results.json"))
    a = ap.parse_args()
    main(Path(a.table), Path(a.diffs), a.repos, a.model, a.n_pass, a.n_fail, a.workers, a.out)
