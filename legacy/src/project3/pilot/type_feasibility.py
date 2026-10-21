"""Thí nghiệm khả thi cho bài toán dự đoán loại lỗi build trước khi chạy CI (pass | compile | lint | test).

Dữ liệu: meta.parquet + hunks.json.gz của pilot HCL (Druid, Paimon); bỏ fail do môi trường và chưa gán nhãn.
Chia theo thời gian như pilot: 70% đầu train (20% cuối của phần này là validation), 30% sau test.

Phân loại loại lỗi (trên commit fail do code, 3 lớp compile/lint/test; dependency gộp vào compile):
  majority, prior        : mức sàn
  type_parrot            : lặp lại loại lỗi của lần fail gần nhất trong cùng chuỗi (nhánh chính / một PR)
  lr_meta                : LR trên lịch sử (kể cả loại lỗi lần trước) + thống kê diff, không đọc nội dung
  tfidf (JITLine-style)  : LR trên TF-IDF dòng thêm/xoá + đường dẫn file + thống kê diff
  ce / hcl / hcl3        : fine-tune UniXcoder, attention hunk -> file -> commit, 4 lớp pass/compile/lint/test
                           hcl  = ce + λ1·SupCon(pass/fail) + λ2·SupCon(loại lỗi trên commit fail)
                           hcl3 = hcl + λ3·SupCon(lỗi cụ thể: subtype, xem fine_labels) + λ4·SupCon(module lỗi),
                                  (hcl3_nopair: như hcl3 nhưng không thêm commit sửa vào batch)
                                  khoá so sánh gồm cả bộ nhớ đặc trưng của các batch trước (XBM, Wang 2020)
Lấy mẫu (--sampler): mỗi commit fail đi cùng một commit pass ngẫu nhiên (CE học trên đúng phân bố này); với mixed,
biến thể hcl* thêm commit sửa nó (commit kế tiếp trong chuỗi, pass) vào batch chỉ cho loss contrastive (cặp âm khó).
Lấy commit sửa làm commit pass của CE (pair) làm lệch phân bố pass và hạ mọi mô hình (lần chạy 2).
Độ đo: macro-F1 và F1 từng lớp trên commit fail (toàn bộ test; P3 = sau commit pass; new = chuỗi chưa từng fail), top-2 accuracy
(giai đoạn thật nằm trong 2 giai đoạn rủi ro nhất), AUC theo từng giai đoạn trên toàn bộ commit test.

    uv run --group exp python -m project3.pilot.type_feasibility --meta ... --hunks ... --seeds 3
"""
import argparse
import gzip
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

from .experiment import HIST, IDENT, SEED, STATS

TYPES = ["compile", "lint", "test"]
PREV = [f"prev_{t}" for t in TYPES]
CLASSES = ["pass", *TYPES]
LAMBDA1, LAMBDA2, LAMBDA3, LAMBDA4, TAU = 0.5, 0.5, 0.5, 0.25, 0.1
MEMORY, MEMORY_WARMUP = 512, 50  # số đặc trưng giữ lại; số bước trước khi dùng bộ nhớ


# ---------------------------------------------------------------- dữ liệu
def load(meta: Path, hunks: Path, max_hunks: int, fine: Path | None = None):
    df = pd.read_parquet(meta).sort_values("t").reset_index(drop=True)
    if fine is not None and fine.exists():
        df = df.merge(pd.read_parquet(fine)[["repository", "head_sha", "subtype", "module"]],
                      on=["repository", "head_sha"], how="left")
    else:
        df["subtype"], df["module"] = None, None
    h = json.loads(gzip.decompress(hunks.read_bytes()))
    fc, hf = np.array(h["file_commit"]), np.array(h["hunk_file"])
    by_commit = defaultdict(lambda: defaultdict(list))
    for text, f in zip(h["texts"], hf):
        by_commit[h["shas"][fc[f]]][f].append(text)
    commits = {}
    for sha, files in by_commit.items():  # chọn lại tối đa max_hunks, chia vòng tròn giữa các file
        groups, out, depth = list(files.values()), [], 0
        while len(out) < max_hunks and any(depth < len(g) for g in groups):
            for fi, g in enumerate(groups):
                if depth < len(g) and len(out) < max_hunks:
                    out.append((fi, g[depth]))
            depth += 1
        commits[sha] = sorted(out, key=lambda x: x[0])
    cut = int(len(df) * 0.7)
    df["split"] = np.where(np.arange(len(df)) < cut, "train", "test")
    df = df[df.head_sha.isin(commits)].reset_index(drop=True)
    lab = df.label.replace({"dependency": "compile", "buildconfig": "compile"})
    df["cls"] = np.where(df.y == 0, "pass", lab)
    df = df[df.cls.isin(CLASSES)].reset_index(drop=True)
    df["c"] = df.cls.map({c: i for i, c in enumerate(CLASSES)})
    # loại lỗi của lần fail gần nhất trước đó trong cùng chuỗi
    last, prev_type = {}, []
    for _, r in df.iterrows():
        k = (r.repository, r.sequence)
        prev_type.append(last.get(k))
        if r.cls != "pass":
            last[k] = r.cls
    df["prev_type"] = prev_type
    for t in TYPES:
        df[f"prev_{t}"] = (df.prev_type == t).astype(int)
    df["text"] = ["\n".join(t for _, t in commits[s]) for s in df.head_sha]
    # nhãn tầng 3 chỉ có ở commit fail; -1 = không có
    fail = (df.cls != "pass").values
    st = df.subtype.where(fail)
    df["sub"] = st.map({v: i for i, v in enumerate(sorted(st.dropna().unique()))}).fillna(-1).astype(int)
    md = (df.repository + ":" + df.module.fillna("").astype(str)).where(fail & df.module.notna())
    df["mod"] = md.map({v: i for i, v in enumerate(sorted(md.dropna().unique()))}).fillna(-1).astype(int)
    # commit sửa lỗi: commit kế tiếp trong cùng chuỗi, nếu nó pass
    partner = np.full(len(df), -1)
    for idx in df.groupby(["repository", "sequence"]).indices.values():
        idx = np.sort(idx)
        for i, j in zip(idx[:-1], idx[1:]):
            if fail[i] and not fail[j]:
                partner[i] = j
    df["partner"] = partner
    return df, commits


def split_idx(df):
    tr_all = np.where(df.split == "train")[0]
    cut = int(len(tr_all) * 0.8)
    return tr_all, tr_all[:cut], tr_all[cut:], np.where(df.split == "test")[0]


# ---------------------------------------------------------------- độ đo
def type_metrics(true, pred, top2=None):
    out = {"macro_f1": round(f1_score(true, pred, labels=TYPES, average="macro", zero_division=0), 4),
           **{f"f1_{t}": round(v, 3) for t, v in
              zip(TYPES, f1_score(true, pred, labels=TYPES, average=None, zero_division=0))}}
    if top2 is not None:
        out["top2_acc"] = round(float(np.mean([t in s for t, s in zip(true, top2)])), 4)
    return out


def evaluate(df, te, type_scores, name, res, stage_scores=None):
    """type_scores: [len(te), 3] điểm cho compile/lint/test; chỉ đánh giá trên commit fail."""
    fail = df.cls.values[te] != "pass"
    p3 = df.prev_fail.values[te] == 0
    true = df.cls.values[te]
    pred = np.array(TYPES)[type_scores.argmax(1)]
    top2 = [set(np.array(TYPES)[np.argsort(-s)[:2]]) for s in type_scores]
    new = pd.isna(df.prev_type.values[te])  # chưa từng fail trong chuỗi: Parrot không có gì để chép
    r = {sub: type_metrics(true[fail & m], pred[fail & m], [top2[i] for i in np.where(fail & m)[0]])
         for sub, m in (("all", np.ones_like(fail)), ("p3", p3), ("new", new))}
    if stage_scores is not None:  # [len(te), 4] xác suất pass/compile/lint/test trên toàn bộ commit
        r["stage_auc"] = {c: round(roc_auc_score(true == c, stage_scores[:, i]), 4) for i, c in enumerate(CLASSES)}
    res.setdefault(name, []).append(r)
    print(f"{name:12} " + " | ".join(f"{k} {r[k]['macro_f1']}" for k in ("all", "p3", "new"))
          + (f" | auc {r['stage_auc']}" if stage_scores is not None else ""), flush=True)


# ---------------------------------------------------------------- baseline CPU
def baselines(df, res):
    tr_all, tr, va, te = split_idx(df)
    ftr = tr_all[df.cls.values[tr_all] != "pass"]
    ytr = df.cls.values[ftr]
    prior = pd.Series(ytr).value_counts(normalize=True).reindex(TYPES).fillna(0).values
    evaluate(df, te, np.tile(prior, (len(te), 1)), "majority", res)
    rng = np.random.default_rng(SEED)
    for _ in range(20):
        evaluate(df, te, rng.random((len(te), 3)) * prior, "prior", res)
    # Parrot loại lỗi: chép loại lỗi lần trước; chưa từng fail thì theo tỉ lệ
    pt = df.prev_type.values[te]
    evaluate(df, te, np.array([[1.0 * (p == t) for t in TYPES] if p in TYPES else prior for p in pt]) + prior * 1e-3,
             "type_parrot", res)
    rc = [c for c in df.columns if c.startswith("repo_")]
    num = np.log1p(np.clip(df[HIST + STATS + PREV + rc].astype(float).values, 0, None))
    sc = StandardScaler().fit(num[tr_all])
    X = csr_matrix(sc.transform(num))
    m = LogisticRegression(C=0.3, class_weight="balanced", max_iter=5000).fit(X[ftr], ytr)
    evaluate(df, te, m.predict_proba(X[te])[:, [list(m.classes_).index(t) for t in TYPES]], "lr_meta", res)
    added = df.text.str.findall(r"^\+.*$", flags=re.M).str.join("\n")
    removed = df.text.str.findall(r"^-.*$", flags=re.M).str.join("\n")
    paths = df.text.str.findall(r"^[^\n@+\- ][^\n]*$", flags=re.M).str.join(" ").str.replace(r"[/._-]", " ", regex=True)
    vecs = [TfidfVectorizer(token_pattern=IDENT.pattern, lowercase=False, min_df=3, max_df=0.5, max_features=30000,
                            sublinear_tf=True).fit(s.values[tr_all]) for s in (added, removed, paths)]
    T = hstack([X] + [v.transform(s.values) for v, s in zip(vecs, (added, removed, paths))]).tocsr()
    m = LogisticRegression(C=1.0, class_weight="balanced", max_iter=5000).fit(T[ftr], ytr)
    evaluate(df, te, m.predict_proba(T[te])[:, [list(m.classes_).index(t) for t in TYPES]], "tfidf", res)


# ---------------------------------------------------------------- fine-tune
def finetune(df, commits, variant, seed, res, a, preds):
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from transformers import AutoModel, AutoTokenizer

    from .hcl_train import seg_softmax_pool, supcon

    def supcon_mem(feat, lab, mfeat, mlab):
        """SupCon với khoá = batch + bộ nhớ; nhãn -1 bị loại khỏi cả anchor lẫn khoá."""
        keys, kl = torch.cat([feat, mfeat]), torch.cat([lab, mlab])
        n = len(lab)
        sim = feat @ keys.T / TAU
        self_ = torch.zeros_like(sim, dtype=torch.bool)
        self_[:, :n] = torch.eye(n, dtype=torch.bool, device=feat.device)
        sim = sim.masked_fill(self_ | (kl < 0)[None, :], -1e9)
        logp = sim - torch.logsumexp(sim, 1, keepdim=True)
        pos = (lab[:, None] == kl[None, :]) & (kl >= 0)[None, :] & ~self_
        ok = (lab >= 0) & (pos.sum(1) > 0)
        if not ok.any():
            return feat.sum() * 0
        return -((logp * pos).sum(1)[ok] / pos.sum(1)[ok]).mean()

    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    tr_all, tr, va, te = split_idx(df)
    if a.smoke:  # kiểm tra nhanh đường chạy fine-tune: ít dữ liệu, 1 epoch
        tr, va, te = tr[-400:], va[:48], te[:96]
    rc = [c for c in df.columns if c.startswith("repo_")]
    num = np.log1p(np.clip(df[HIST + STATS + PREV + rc].astype(float).values, 0, None))
    num = torch.tensor(StandardScaler().fit(num[tr]).transform(num), dtype=torch.float32, device="cuda")
    y = torch.tensor(df.c.values, device="cuda")
    sub = torch.tensor(df["sub"].values, device="cuda")
    mod = torch.tensor(df["mod"].values, device="cuda")
    tok = AutoTokenizer.from_pretrained("microsoft/unixcoder-base")

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.enc = AutoModel.from_pretrained("microsoft/unixcoder-base")
            for p in self.enc.embeddings.parameters():
                p.requires_grad = False
            for layer in self.enc.encoder.layer[:a.freeze_layers]:
                for p in layer.parameters():
                    p.requires_grad = False
            d = self.enc.config.hidden_size
            self.att_h, self.att_f = nn.Linear(d, 1), nn.Linear(d, 1)
            self.num = nn.Sequential(nn.Linear(num.shape[1], 64), nn.GELU())
            self.body = nn.Sequential(nn.Dropout(0.1), nn.Linear(d + 64, 256), nn.GELU(), nn.Dropout(0.1))
            self.head = nn.Linear(256, len(CLASSES))
            self.con = nn.Sequential(nn.Linear(256, 128), nn.GELU(), nn.Linear(128, 64))

        def forward(self, rows):
            texts, hunk_file, file_commit = [], [], []
            for k, r in enumerate(rows):
                local = {}
                for fi, t in commits[df.head_sha.values[r]]:
                    if fi not in local:
                        local[fi] = len(file_commit)
                        file_commit.append(k)
                    hunk_file.append(local[fi])
                    texts.append(t)
            enc = tok(texts, padding=True, truncation=True, max_length=a.max_tokens, return_tensors="pt").to("cuda")
            h = self.enc(**enc).last_hidden_state
            m = enc["attention_mask"].unsqueeze(-1).to(h.dtype)
            h = ((h * m).sum(1) / m.sum(1)).float()
            hf, fc = torch.tensor(hunk_file, device="cuda"), torch.tensor(file_commit, device="cuda")
            f = seg_softmax_pool(h, self.att_h(h).squeeze(1), hf, len(file_commit))
            c = seg_softmax_pool(f, self.att_f(f).squeeze(1), fc, len(rows))
            z = self.body(torch.cat([c, self.num(num[rows])], 1))
            return self.head(z), F.normalize(self.con(z), dim=1)

    net = Net().cuda()
    enc_params = [p for p in net.enc.parameters() if p.requires_grad]
    head_params = [p for n, p in net.named_parameters() if not n.startswith("enc.")]
    opt = torch.optim.AdamW([{"params": enc_params, "lr": a.lr_enc}, {"params": head_params, "lr": 1e-3}], weight_decay=0.01)
    scaler = torch.amp.GradScaler()
    # trọng số lớp cho CE (đếm trên phần train đã cân bằng pass:fail = 1:1)
    fails, passes = tr[df.c.values[tr] > 0], tr[df.c.values[tr] == 0]
    cnt = np.bincount(df.c.values[fails], minlength=4).astype(float)
    cnt[0] = len(fails)
    w = torch.tensor(cnt.sum() / (4 * np.maximum(cnt, 1)), dtype=torch.float32, device="cuda")

    def predict(rows):
        net.eval()
        out = []
        with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16):
            for i in range(0, len(rows), a.eval_batch):
                out.append(torch.softmax(net(rows[i:i + a.eval_batch])[0].float(), 1).cpu().numpy())
        return np.concatenate(out)

    in_tr = np.zeros(len(df), bool)
    in_tr[tr] = True
    partner = df.partner.values
    n_pair = int(sum(partner[f] >= 0 and in_tr[partner[f]] for f in fails))
    print(f"  {len(fails)} fail train, {n_pair} có commit sửa đi cặp", flush=True)
    mem = {"feat": torch.zeros(0, 64, device="cuda"), "lab": torch.zeros(0, 4, dtype=torch.long, device="cuda")}
    has_mate = (partner >= 0) & in_tr[np.maximum(partner, 0)]

    def epoch_batches():
        """Danh sách (rows, ce_mask). Mỗi nhóm = commit fail + commit pass; commit sửa (nếu dùng) chỉ vào loss contrastive.
        random: pass ngẫu nhiên; pair: pass = commit sửa nếu có; mixed: pass ngẫu nhiên + commit sửa cho biến thể hcl*."""
        order = rng.permutation(fails)
        rand = rng.choice(passes, len(fails), replace=False)
        groups = []
        for f, p in zip(order, rand):
            if a.sampler == "pair":
                groups.append([(f, True), (partner[f] if has_mate[f] else p, True)])
            else:
                g = [(f, True), (p, True)]
                if a.sampler == "mixed" and variant in ("hcl", "hcl3") and has_mate[f]:
                    g.append((partner[f], False))
                groups.append(g)
        out, cur = [], []
        for g in groups:  # gói nhóm vào batch tối đa a.batch commit, không cắt đôi nhóm
            if len(cur) + len(g) > a.batch:
                out.append(cur)
                cur = []
            cur += g
        out.append(cur)
        return [(np.array([x for x, _ in b]), torch.tensor([m for _, m in b], device="cuda")) for b in out]

    best, best_state, t0, step = -1, None, time.time(), 0
    for ep in range(a.epochs):
        net.train()
        for r, cem in epoch_batches():
            with torch.autocast("cuda", dtype=torch.float16):
                logits, feat = net(r)
            logits, feat = logits.float(), feat.float()
            yb = y[r]
            loss = F.cross_entropy(logits[cem], yb[cem], weight=w)
            if variant == "hcl":
                loss = loss + LAMBDA1 * supcon(feat, (yb > 0).long())
                fb = yb > 0
                if fb.sum() > 1:
                    loss = loss + LAMBDA2 * supcon(feat[fb], yb[fb])
            elif variant.startswith("hcl3"):  # hcl3_nopair: cùng loss, không thêm commit sửa
                fb = yb > 0
                # các tầng: pass/fail, loại lỗi, lỗi cụ thể, module; các tầng dưới chỉ xét commit fail
                lab = torch.stack([fb.long(), torch.where(fb, yb, -1), torch.where(fb, sub[r], -1),
                                   torch.where(fb, mod[r], -1)], 1)
                k = len(mem["feat"]) if step >= MEMORY_WARMUP else 0
                for lv, lam in enumerate((LAMBDA1, LAMBDA2, LAMBDA3, LAMBDA4)):
                    loss = loss + lam * supcon_mem(feat, lab[:, lv], mem["feat"][:k], mem["lab"][:k, lv])
                mem["feat"] = torch.cat([feat.detach(), mem["feat"]])[:MEMORY]
                mem["lab"] = torch.cat([lab, mem["lab"]])[:MEMORY]
            step += 1
            opt.zero_grad()
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
        pv = predict(va)
        fv = df.c.values[va] > 0
        score = f1_score(df.cls.values[va][fv], np.array(TYPES)[pv[fv][:, 1:].argmax(1)], labels=TYPES, average="macro")
        print(f"  {variant} seed {seed} epoch {ep + 1}: val macro-F1 {score:.3f} ({time.time() - t0:.0f}s)", flush=True)
        if score > best:
            best = score
            best_state = {k: v.detach().to("cpu", copy=True) for k, v in net.state_dict().items()}
    net.load_state_dict(best_state)
    pt = predict(te)
    evaluate(df, te, pt[:, 1:], variant, res, stage_scores=pt)
    preds[f"{variant}_{seed}"] = pt
    del net, opt
    torch.cuda.empty_cache()


def summarize(res):
    rows = []
    for name, runs in res.items():
        for sub in ("all", "p3", "new"):
            vals = pd.DataFrame([r[sub] for r in runs])
            rows.append({"model": name, "subset": sub, "n_runs": len(runs),
                         **{k: f"{vals[k].mean():.3f}" + (f" ± {vals[k].std():.3f}" if len(runs) > 1 else "")
                            for k in vals.columns}})
    return pd.DataFrame(rows)


def main(a):
    df, commits = load(a.meta, a.hunks, a.max_hunks, a.fine)
    if a.holdout:  # P2: test = toàn bộ commit của repo chưa thấy; train/val = các repo còn lại (val = 20% cuối theo thời gian)
        df["split"] = np.where(df.repository.isin(a.holdout), "test", "train")
    if a.label_frac < 1:  # ít nhãn: chỉ giữ một phần commit fail có nhãn loại lỗi trong train, commit pass giữ nguyên
        ftr = np.where((df.split == "train") & (df.cls != "pass"))[0]
        drop = np.random.default_rng(SEED).permutation(ftr)[int(len(ftr) * a.label_frac):]
        df.loc[drop, "split"] = "unused"
    tr_all, tr, va, te = split_idx(df)
    info = {s: df.cls.values[idx][df.cls.values[idx] != "pass"].tolist() for s, idx in (("train", tr_all), ("test", te))}
    print({s: pd.Series(v).value_counts().to_dict() for s, v in info.items()}, flush=True)
    ftr = tr_all[df.cls.values[tr_all] != "pass"]
    print(f"tầng 3 trên fail train: subtype {(df['sub'].values[ftr] >= 0).mean():.2f}, "
          f"module {(df['mod'].values[ftr] >= 0).mean():.2f}; {df['sub'].max() + 1} subtype, {df['mod'].max() + 1} module",
          flush=True)
    res, preds = {}, {}

    def save():  # ghi sau mỗi lượt chạy: hết giờ giữa chừng vẫn giữ được kết quả đã có
        summary = summarize(res)
        a.out.write_text(json.dumps({"runs": res, "summary": summary.to_dict("records"), "config": {
            k: str(v) for k, v in vars(a).items()}}, indent=1, ensure_ascii=False), encoding="utf-8")
        np.savez_compressed(a.out.with_suffix(".preds.npz"), test_sha=df.head_sha.values[te].astype("U40"),
                            **{k: v.astype(np.float16) for k, v in preds.items()})
        return summary

    if not a.smoke:
        baselines(df, res)
        save()
    if not a.cpu_only:
        for seed in range(a.seeds):  # xen kẽ biến thể theo seed: dừng sớm vẫn so sánh được
            for variant in a.variants:
                finetune(df, commits, variant, seed, res, a, preds)
                save()
    print("\n" + save().to_string(index=False))
    print(f"Đã lưu {a.out}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--meta", type=Path, default=Path("data/processed/hcl_pilot/meta.parquet"))
    ap.add_argument("--hunks", type=Path, default=Path("data/processed/hcl_pilot/kaggle_ds/hunks.json.gz"))
    ap.add_argument("--out", type=Path, default=Path("data/processed/hcl_pilot/type_feasibility.json"))
    ap.add_argument("--fine", type=Path, default=None, help="fine_labels.parquet (nhãn tầng 3 cho hcl3)")
    ap.add_argument("--variants", nargs="+", default=["ce", "hcl", "hcl3"])
    ap.add_argument("--holdout", nargs="*", default=[], help="repo dùng làm test (P2, leave-repo-out)")
    ap.add_argument("--label-frac", type=float, default=1.0, help="tỉ lệ commit fail có nhãn được giữ trong train")
    ap.add_argument("--sampler", choices=["random", "pair", "mixed"], default="mixed",
                    help="random: như lần chạy 1; pair: như lần chạy 2; mixed: random cho CE + commit sửa cho contrastive")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--max-hunks", type=int, default=8)
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--freeze-layers", type=int, default=6)
    ap.add_argument("--batch", type=int, default=12)
    ap.add_argument("--eval-batch", type=int, default=32)
    ap.add_argument("--lr-enc", type=float, default=2e-5)
    ap.add_argument("--cpu-only", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="chạy thử fine-tune trên vài batch")
    main(ap.parse_args())
