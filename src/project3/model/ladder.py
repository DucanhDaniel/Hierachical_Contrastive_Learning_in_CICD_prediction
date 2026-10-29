"""Bậc thang baseline theo cây 3 tầng (27/10/2026; docs/cay-nhan-3-tang-2026-10-25.md). Chỉ đọc gói dữ liệu (model.pack),
nên chạy được trên Kaggle. Cùng cách chia như model.train: test = fold k, val = k+1, train = 3 fold còn lại; train che
50% run (mix50), chấm trên test nguyên vẹn (full) và đã che dòng bằng chứng (masked).

  majority  lá phổ biến nhất của train                                                   (mức sàn)
  ctx       TF-IDF + LR chỉ trên ngữ cảnh CI: tên workflow, job fail, step fail             (mức sàn: chỉ metadata)
  tfidf     TF-IDF + LR trên 30.000 ký tự cuối của log (tfidf_text.parquet)                 (mức sàn cổ điển)
  feat      LR chỉ trên đặc trưng có cấu trúc (giai đoạn/công cụ fail + tóm tắt diff; model.inputs)   (kiểm tra đầu vào)
  tfidf_struct / tfidf_all   TF-IDF + đặc trưng giai đoạn/công cụ fail / + cả tóm tắt diff     (kiểm tra đầu vào, 27/10)
  bert      BERT fine-tune phân loại phẳng các lá, 512 token cuối của log                   (ICSE 2024 poster: "Applying
            Transformer Models for Automatic Build Errors Classification of Java-Based Open Source Projects")

    python -m project3.model.ladder --data DIR --out DIR --models majority ctx tfidf      # CPU
    python -m project3.model.ladder --data DIR --out DIR --models bert --folds 0 1        # GPU
-> ladder_preds_<model>.parquet (model, test, fold, run_id, leaf, pred) và ladder_<model>.md (macro-F1 TB 5 fold).
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .config import SEED
from .data import mix50, train_folds, val_fold
from .labels import GROUP, PARENT
from .metrics import hier_scores
from .text import ci_context
from .tfidf import make_classifier, make_vectorizer

BERT = "bert-base-uncased"
BERT_CHARS = 6000  # đủ dư cho 512 token cuối; cắt trước khi tokenize cho nhanh


def load(data: Path) -> pd.DataFrame:
    runs = pd.read_parquet(data / "runs.parquet").drop_duplicates("run_id")
    txt = pd.read_parquet(data / "tfidf_text.parquet").drop_duplicates("run_id")
    runs = runs.merge(txt, on="run_id", how="inner")
    f = data / "features.parquet"
    if f.exists():
        runs = runs.merge(pd.read_parquet(f).drop_duplicates("run_id"), on="run_id", how="left")
    runs["ctx"] = [ci_context(w, j, s) for w, j, s in
                   zip(runs.workflow.fillna(""), runs.failed_job_names.fillna(""), runs.failed_steps.fillna(""))]
    return runs.reset_index(drop=True)


def train_text(runs: pd.DataFrame) -> list:
    mix = mix50(runs.run_id)
    return [m if mix[r] else f for r, f, m in zip(runs.run_id, runs.full, runs.masked)]


def sklearn_model(name: str, tr: pd.DataFrame, te: pd.DataFrame, va: pd.DataFrame = None) -> dict:
    """test -> dự đoán lá cho các run của te."""
    if name == "majority":
        top = tr.leaf.value_counts().idxmax()
        return {t: [top] * len(te) for t in ("full", "masked")}
    if name.startswith("feat") or name.startswith("tfidf_"):
        return feature_model(name, tr, te, va)
    vec = make_vectorizer()
    if name == "ctx":  # ngữ cảnh CI không chứa dòng bằng chứng -> full và masked như nhau
        clf = make_classifier().fit(vec.fit_transform(tr.ctx), tr.leaf)
        p = clf.predict(vec.transform(te.ctx)).tolist()
        return {"full": p, "masked": p}
    clf = make_classifier().fit(vec.fit_transform(train_text(tr)), tr.leaf)
    return {t: clf.predict(vec.transform(te[t])).tolist() for t in ("full", "masked")}


def feats(df: pd.DataFrame, which: str, masked) -> np.ndarray:
    """Ma trận đặc trưng; masked: bool hoặc mảng bool từng run (struct lấy bản tính trên log đã che)."""
    masked = np.broadcast_to(np.asarray(masked), len(df))
    parts = []
    if which in ("struct", "all"):
        parts.append(np.stack([m if k else f for f, m, k in zip(df.struct_full, df.struct_masked, masked)]))
    if which in ("diff", "all"):
        parts.append(np.stack(df["diff"].values))
    return np.concatenate(parts, 1).astype(np.float32)


FEAT_SCALES = (0.03, 0.1, 0.3, 1.0)  # hệ số nhân đặc trưng dày (đã chuẩn hoá) khi ghép với TF-IDF, chọn trên fold val


def feature_model(name: str, tr: pd.DataFrame, te: pd.DataFrame, va: pd.DataFrame) -> dict:
    from scipy.sparse import csr_matrix, hstack
    from sklearn.metrics import f1_score
    from sklearn.preprocessing import StandardScaler
    which = "all" if name in ("feat", "tfidf_all") else "struct"
    mix = mix50(tr.run_id)
    sc = StandardScaler().fit(feats(tr, which, [mix[r] for r in tr.run_id]))
    if name == "feat":
        clf = make_classifier().fit(sc.transform(feats(tr, which, [mix[r] for r in tr.run_id])), tr.leaf)
        return {t: clf.predict(sc.transform(feats(te, which, t == "masked"))).tolist() for t in ("full", "masked")}
    vec = make_vectorizer()
    Xt = vec.fit_transform(train_text(tr))
    Ft = sc.transform(feats(tr, which, [mix[r] for r in tr.run_id]))
    X = lambda df, t, w: hstack([vec.transform(df[t]), csr_matrix(w * sc.transform(feats(df, which, t == "masked")))]).tocsr()
    best = None
    for w in FEAT_SCALES:
        clf = make_classifier().fit(hstack([Xt, csr_matrix(w * Ft)]).tocsr(), tr.leaf)
        f = f1_score(va.leaf, clf.predict(X(va, "full", w)), average="macro")
        print(f"    {name} hệ số {w}: val macro-F1 lá {f:.3f}", flush=True)
        if best is None or f > best[0]:
            best = (f, w, clf)
    _, w, clf = best
    return {t: clf.predict(X(te, t, w)).tolist() for t in ("full", "masked")}


def bert_model(tr: pd.DataFrame, va: pd.DataFrame, te: pd.DataFrame, epochs: int, batch: int, lr: float) -> dict:
    import torch
    from torch.utils.data import DataLoader
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup
    from sklearn.metrics import f1_score

    torch.manual_seed(SEED)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    classes = sorted(tr.leaf.unique())
    idx = {c: i for i, c in enumerate(classes)}
    tok = AutoTokenizer.from_pretrained(BERT)
    tok.truncation_side = "left"  # giữ phần cuối log (nơi có lỗi)

    def enc(texts):
        return tok([t[-BERT_CHARS:] for t in texts], truncation=True, max_length=512, padding="max_length",
                   return_tensors="pt")

    def loader(texts, labels=None, shuffle=False):
        e = enc(texts)
        items = [e["input_ids"], e["attention_mask"]] + ([torch.tensor(labels)] if labels is not None else [])
        return DataLoader(torch.utils.data.TensorDataset(*items), batch_size=batch if shuffle else batch * 4,
                          shuffle=shuffle)

    model = AutoModelForSequenceClassification.from_pretrained(BERT, num_labels=len(classes),
                                                               ignore_mismatched_sizes=True).to(dev)
    train_dl = loader(train_text(tr), [idx[x] for x in tr.leaf], shuffle=True)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    sched = get_linear_schedule_with_warmup(opt, int(0.06 * epochs * len(train_dl)), epochs * len(train_dl))
    scaler = torch.amp.GradScaler(enabled=dev == "cuda")

    @torch.no_grad()
    def predict(texts):
        model.eval()
        out = []
        for ids, mask in loader(texts):
            with torch.autocast(dev, enabled=dev == "cuda"):
                out.append(model(input_ids=ids.to(dev), attention_mask=mask.to(dev)).logits.argmax(-1).cpu())
        return [classes[i] for i in torch.cat(out).tolist()]

    best, best_state = -1.0, None
    for ep in range(epochs):
        model.train()
        t0 = time.time()
        for ids, mask, y in train_dl:
            opt.zero_grad()
            with torch.autocast(dev, enabled=dev == "cuda"):
                loss = model(input_ids=ids.to(dev), attention_mask=mask.to(dev), labels=y.to(dev)).loss
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt)
            scaler.update()
            sched.step()
        f1 = f1_score(va.leaf, predict(va.full.tolist()), average="macro", zero_division=0)
        print(f"    epoch {ep + 1}: val macro-F1 lá {f1:.3f} ({time.time() - t0:.0f}s)", flush=True)
        if f1 > best:
            best, best_state = f1, {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    return {t: predict(te[t].tolist()) for t in ("full", "masked")}


def summarize(preds: pd.DataFrame, out: Path, name: str) -> None:
    rows = []
    for (m, t, k), g in preds.groupby(["model", "test", "fold"]):
        s = hier_scores(g.leaf.tolist(), g.pred.tolist(), PARENT, GROUP)
        rows.append({"model": m, "test": t, "fold": k, "lá": s["macroF1_l3"], "tầng 2": s["macroF1_l2"],
                     "tầng 1": s["macroF1_l1"], "acc lá": s["acc_l3"]})
    df = pd.DataFrame(rows)
    mean = df.groupby(["model", "test"])[["lá", "tầng 2", "tầng 1", "acc lá"]].mean().round(3)
    n = df.groupby(["model", "test"]).fold.nunique().rename("số fold")
    text = f"macro-F1 theo cây 3 tầng (TB các fold chéo repo)\n\n{mean.join(n).to_string()}\n"
    (out / f"ladder_{name}.md").write_text(text, encoding="utf-8")
    print(text, flush=True)


def main(data: Path, out: Path, models: list, folds: list, epochs: int, batch: int, lr: float) -> None:
    out.mkdir(parents=True, exist_ok=True)
    runs = load(data)
    print(f"{len(runs)} run, {runs.leaf.nunique()} lá", flush=True)
    for name in models:
        parts, t0 = [], time.time()
        for k in folds:
            tr = runs[runs.repo_fold.isin(train_folds(k))]
            te = runs[runs.repo_fold == k]
            if name == "bert":
                pred = bert_model(tr, runs[runs.repo_fold == val_fold(k)], te, epochs, batch, lr)
            else:
                pred = sklearn_model(name, tr, te, runs[runs.repo_fold == val_fold(k)])
            for t, p in pred.items():
                parts.append(pd.DataFrame({"model": name, "test": t, "fold": k, "run_id": te.run_id.values,
                                           "leaf": te.leaf.values, "pred": p}))
            print(f"  {name} fold {k} xong ({time.time() - t0:.0f}s)", flush=True)
            preds = pd.concat(parts)
            preds.to_parquet(out / f"ladder_preds_{name}.parquet", index=False)  # lưu sau mỗi fold
        summarize(preds, out, name)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--models", nargs="+", default=["majority", "ctx", "tfidf"],
                    choices=["majority", "ctx", "tfidf", "feat", "tfidf_struct", "tfidf_all", "bert"])
    ap.add_argument("--folds", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-5)
    a = ap.parse_args()
    main(a.data, a.out, a.models, a.folds, a.epochs, a.batch, a.lr)
