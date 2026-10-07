"""Thí nghiệm pilot: mô hình đọc diff có vượt Parrot không, và diff có phân biệt được loại lỗi không.

Dữ liệu: commit pass + commit fail do code (bỏ fail do env và chưa gán nhãn) của các repo có diff.
Chia theo thời gian: 70% commit đầu train (20% cuối của phần này để chọn ngưỡng), 30% sau test.
  Parrot      : đoán fail nếu commit liền trước trong cùng chuỗi (nhánh chính / một PR) fail.
  history     : LR trên lịch sử (Parrot, vị trí trong chuỗi, tỉ lệ fail gần đây của repo) + metadata.
  diff        : LR trên TF-IDF (dòng thêm, dòng xoá, đường dẫn file) + thống kê diff, không có lịch sử.
  diff+history: cả hai.
Đánh giá trên toàn tập test và tập con "sau commit pass" (P3: fail ở đây là lần fail đầu, Parrot luôn đoán pass).
Tầng 2: trong commit fail, phân loại compile/lint/test từ diff.

    uv run --group exp python -m project3.pilot.experiment
"""
import argparse
import bisect
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, classification_report, confusion_matrix, f1_score,
                             precision_score, recall_score, roc_auc_score)
from sklearn.preprocessing import StandardScaler

TEXT_CAP = 200_000
SEED = 20261007
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,40}")
FILE_KINDS = {
    "java_test": re.compile(r"(/test/|/tests?/|Test\w*\.java$|IT\.java$)"),
    "java": re.compile(r"\.(java|scala|kt)$"),
    "build": re.compile(r"(pom\.xml|\.gradle(\.kts)?|build\.sbt|gradle\.properties)$"),
    "doc": re.compile(r"(\.md|\.rst|\.txt|\.html|/docs?/)"),
    "python": re.compile(r"\.py$"),
    "web": re.compile(r"\.(js|ts|tsx|jsx|css|scss)$"),
    "config": re.compile(r"\.(ya?ml|json|properties|xml|conf|toml)$"),
}


def parse_diff(path: str) -> dict:
    files, added, removed, hunks = [], [], [], 0
    try:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    for line in text.splitlines():
        if line.startswith("diff --git "):
            files.append(line.split(" b/", 1)[-1])
        elif line.startswith("@@"):
            hunks += 1
        elif line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            removed.append(line[1:])
    kinds = defaultdict(int)
    for f in files:
        k = next((k for k, rx in FILE_KINDS.items() if rx.search(f)), "other")
        kinds[k] += 1
    return {
        "n_files": len(files), "n_add": len(added), "n_del": len(removed), "n_hunks": hunks,
        "n_modules": len({f.split("/")[0] for f in files}), **{f"f_{k}": kinds[k] for k in [*FILE_KINDS, "other"]},
        "only_test": int(bool(files) and kinds["java_test"] == len(files)),
        "has_test": int(kinds["java_test"] > 0),
        "txt_add": "\n".join(added)[:TEXT_CAP], "txt_del": "\n".join(removed)[:TEXT_CAP],
        "txt_path": " ".join(re.sub(r"[/._-]", " ", f) for f in files),
    }


def load(table: Path, diffs_csv: Path, repos: list[str]) -> pd.DataFrame:
    con = duckdb.connect()
    df = con.sql(f"SELECT * FROM '{table.as_posix()}' WHERE repository IN ({','.join(f'{chr(39)}{r}{chr(39)}' for r in repos)})").df()
    df = df.sort_values("first_run_at").reset_index(drop=True)
    # lịch sử tính trên toàn bộ commit (kể cả fail do env/chưa gán) trước khi lọc
    df["prev_fail"], df["seq_idx"], df["seq_prev_fails"] = 0, 0, 0
    state = {}
    for i, r in df.iterrows():
        k = (r.repository, r.sequence)
        n, fails, last = state.get(k, (0, 0, None))
        df.at[i, "prev_fail"] = int(last == "fail")
        df.at[i, "seq_idx"], df.at[i, "seq_prev_fails"] = n, fails
        state[k] = (n + 1, fails + (r.outcome == "fail"), r.outcome)
    # tỉ lệ fail của 50 commit gần nhất trong repo đã chạy xong ít nhất 3 giờ trước (tránh dùng kết quả chưa có)
    df["t"] = pd.to_datetime(df.first_run_at)
    df["repo_recent_fail"] = 0.0
    for repo, g in df.groupby("repository"):
        ts, ys = g.t.values, (g.outcome == "fail").values.astype(float)
        cs = np.concatenate([[0], np.cumsum(ys)])
        for i, t in zip(g.index, ts):
            j = bisect.bisect_left(ts, t - np.timedelta64(3, "h"))
            lo = max(0, j - 50)
            df.at[i, "repo_recent_fail"] = (cs[j] - cs[lo]) / (j - lo) if j > lo else 0.0
    df = df[(df.outcome == "pass") | (df.cause == "code")].copy()
    d = pd.read_csv(diffs_csv)
    d = d[d.ok.astype(str) == "True"].drop_duplicates("head_sha")
    df = df.merge(d[["repository", "head_sha", "path"]], on=["repository", "head_sha"], how="inner")
    feats = pd.DataFrame([parse_diff(p) for p in df.path])
    df = pd.concat([df.reset_index(drop=True), feats], axis=1)
    df = df[df.n_files.fillna(0) > 0].reset_index(drop=True)
    df["y"] = (df.outcome == "fail").astype(int)
    df["is_pr"] = (df.event == "pull_request").astype(int)
    df["is_first"] = (df.seq_idx == 0).astype(int)
    for r in repos:
        df[f"repo_{r.split('/')[1]}"] = (df.repository == r).astype(int)
    return df.sort_values("t").reset_index(drop=True)


HIST = ["prev_fail", "seq_idx", "seq_prev_fails", "repo_recent_fail", "is_pr", "is_first"]
STATS = ["n_files", "n_add", "n_del", "n_hunks", "n_modules", "only_test", "has_test",
         *[f"f_{k}" for k in [*FILE_KINDS, "other"]]]


class Featurizer:
    def __init__(self, text: bool, cols: list[str]):
        self.text, self.cols = text, cols
        self.scaler = StandardScaler()
        self.vecs = {c: TfidfVectorizer(token_pattern=IDENT.pattern, lowercase=False, min_df=3, max_df=0.5,
                                        max_features=30000, sublinear_tf=True, dtype=np.float32)
                     for c in ("txt_add", "txt_del", "txt_path")} if text else {}

    def _num(self, df):
        x = df[self.cols].astype(float).values
        return np.log1p(np.clip(x, 0, None))

    def fit_transform(self, df):
        parts = [csr_matrix(self.scaler.fit_transform(self._num(df)))]
        parts += [v.fit_transform(df[c]) for c, v in self.vecs.items()]
        return hstack(parts).tocsr()

    def transform(self, df):
        parts = [csr_matrix(self.scaler.transform(self._num(df)))]
        parts += [v.transform(df[c]) for c, v in self.vecs.items()]
        return hstack(parts).tocsr()


def lr(c=1.0, multi=False):
    return LogisticRegression(C=c, class_weight="balanced", max_iter=3000, solver="lbfgs" if multi else "liblinear",
                              random_state=SEED)


def best_threshold(y, p):
    grid = np.unique(np.quantile(p, np.linspace(0.02, 0.98, 97)))
    return max(grid, key=lambda t: f1_score(y, p >= t, zero_division=0))


def fit_binary(train, test, text, cols, repos_cols):
    cut = int(len(train) * 0.8)
    tr, va = train.iloc[:cut], train.iloc[cut:]
    f = Featurizer(text, cols + repos_cols)
    m = lr(0.5).fit(f.fit_transform(tr), tr.y)
    thr = best_threshold(va.y.values, m.predict_proba(f.transform(va))[:, 1])
    f = Featurizer(text, cols + repos_cols)
    m = lr(0.5).fit(f.fit_transform(train), train.y)
    return m.predict_proba(f.transform(test))[:, 1], thr


def metrics(y, score, pred):
    out = {"n": int(len(y)), "fail": int(y.sum()), "base_rate": round(float(y.mean()), 3),
           "precision": precision_score(y, pred, zero_division=0), "recall": recall_score(y, pred, zero_division=0),
           "f1": f1_score(y, pred, zero_division=0),
           "pr_auc": average_precision_score(y, score) if y.sum() else float("nan"),
           "roc_auc": roc_auc_score(y, score) if 0 < y.sum() < len(y) else float("nan"),
           "skip_rate": float((pred == 0).mean()), "missed_fail": float(((pred == 0) & (y == 1)).sum() / max(1, y.sum()))}
    return {k: round(v, 3) if isinstance(v, float) else v for k, v in out.items()}


def bootstrap_f1(y, pred, n=1000, seed=SEED):
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(y), (n, len(y)))
    s = [f1_score(y[i], pred[i], zero_division=0) for i in idx]
    return [round(float(np.percentile(s, 2.5)), 3), round(float(np.percentile(s, 97.5)), 3)]


def run_binary(df, repos):
    cut = int(len(df) * 0.7)
    train, test = df.iloc[:cut], df.iloc[cut:]
    rc = [f"repo_{r.split('/')[1]}" for r in repos]
    preds = {"always_fail": (np.ones(len(test)), 0.5), "Parrot": (test.prev_fail.values.astype(float), 0.5)}
    preds["history"] = fit_binary(train, test, False, HIST + STATS, rc)
    preds["diff"] = fit_binary(train, test, True, STATS, rc)
    preds["diff+history"] = fit_binary(train, test, True, HIST + STATS, rc)
    subsets = {"all": np.ones(len(test), bool), "after_pass (P3)": test.prev_fail.values == 0,
               "after_fail": test.prev_fail.values == 1}
    for r in repos:
        subsets[f"after_pass {r.split('/')[1]}"] = (test.prev_fail.values == 0) & (test.repository.values == r)
    res = {"split": {"train": [str(train.t.min())[:10], str(train.t.max())[:10], len(train)],
                     "test": [str(test.t.min())[:10], str(test.t.max())[:10], len(test)]}, "results": {}}
    y = test.y.values
    for name, (score, thr) in preds.items():
        pred = (score >= thr).astype(int)
        for sname, mask in subsets.items():
            m = metrics(y[mask], score[mask], pred[mask])
            if sname in ("all", "after_pass (P3)"):
                m["f1_ci95"] = bootstrap_f1(y[mask], pred[mask])
            res["results"].setdefault(sname, {})[name] = m
    return res


def run_tier2(df):
    f = df[df.y == 1].copy()
    f["lab"] = f.label.replace({"dependency": "compile"})
    f = f[f.lab.isin(["compile", "lint", "test"])].reset_index(drop=True)
    cut = int(len(f) * 0.7)
    # lớp quá ít mẫu train làm class_weight=balanced gán trọng số cực lớn -> bỏ
    keep = [k for k, v in f.iloc[:cut].lab.value_counts().items() if v >= 20]
    f = f[f.lab.isin(keep)].reset_index(drop=True)
    cut = int(len(f) * 0.7)
    train, test = f.iloc[:cut], f.iloc[cut:]
    out = {"train_counts": train.lab.value_counts().to_dict(), "test_counts": test.lab.value_counts().to_dict()}
    feat = Featurizer(True, STATS + [c for c in f.columns if c.startswith("repo_")])
    m = lr(1.0, multi=True).fit(feat.fit_transform(train), train.lab)
    pred = m.predict(feat.transform(test))
    labels = sorted(keep)
    out["labels"] = labels
    out["diff_lr"] = {"macro_f1": round(f1_score(test.lab, pred, average="macro"), 3),
                      "report": classification_report(test.lab, pred, labels=labels, output_dict=True, zero_division=0),
                      "confusion": confusion_matrix(test.lab, pred, labels=labels).tolist()}
    majority = train.lab.value_counts().idxmax()
    out["majority"] = {"label": majority, "macro_f1": round(f1_score(test.lab, [majority] * len(test), average="macro"), 3)}
    rng = np.random.default_rng(SEED)
    prior = train.lab.value_counts(normalize=True)
    rand = [f1_score(test.lab, rng.choice(prior.index, len(test), p=prior.values), average="macro") for _ in range(200)]
    out["random_prior"] = {"macro_f1": round(float(np.mean(rand)), 3), "p97_5": round(float(np.percentile(rand, 97.5)), 3)}
    # chỉ dùng thống kê diff (không TF-IDF) để biết bao nhiêu tín hiệu đến từ loại file đơn thuần
    feat2 = Featurizer(False, STATS + [c for c in f.columns if c.startswith("repo_")])
    m2 = lr(1.0, multi=True).fit(feat2.fit_transform(train), train.lab)
    out["stats_lr"] = {"macro_f1": round(f1_score(test.lab, m2.predict(feat2.transform(test)), average="macro"), 3)}
    return out


def main(table, diffs_csv, repos, out):
    df = load(table, diffs_csv, repos)
    print(f"{len(df)} commit có diff; fail do code {int(df.y.sum())} ({df.y.mean():.1%})", flush=True)
    res = {"repos": repos, "n": len(df), **run_binary(df, repos), "tier2": run_tier2(df)}
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"split: {res['split']}")
    cols = ["n", "fail", "precision", "recall", "f1", "f1_ci95", "pr_auc", "roc_auc", "skip_rate", "missed_fail"]
    for sname, models in res["results"].items():
        print(f"\n## {sname}")
        print(pd.DataFrame(models).T.reindex(columns=cols).to_string())
    t2 = res["tier2"]
    print(f"\n## Tầng 2 (test {t2['test_counts']}, train {t2['train_counts']})")
    print(f"diff LR macro-F1 {t2['diff_lr']['macro_f1']} | chỉ thống kê diff {t2['stats_lr']['macro_f1']} | "
          f"đa số ({t2['majority']['label']}) {t2['majority']['macro_f1']} | ngẫu nhiên theo tỉ lệ {t2['random_prior']}")
    for k in t2["labels"]:
        r = t2["diff_lr"]["report"][k]
        print(f"  {k:8} P {r['precision']:.2f} R {r['recall']:.2f} F1 {r['f1-score']:.2f} n {int(r['support'])}")
    print(f"confusion (hàng = thật, cột = đoán; {', '.join(t2['labels'])}):", t2["diff_lr"]["confusion"])
    print(f"Đã lưu {out}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", default="data/processed/commits_pilot.parquet")
    ap.add_argument("--diffs", default="data/processed/pilot_diffs.csv")
    ap.add_argument("--repos", nargs="+", default=["apache/druid", "apache/paimon"])
    ap.add_argument("--out", default="data/processed/pilot_results.json")
    a = ap.parse_args()
    main(Path(a.table), Path(a.diffs), a.repos, Path(a.out))
