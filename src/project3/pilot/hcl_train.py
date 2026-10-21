"""Bước 2 của pilot HCL: so sánh hàm loss trên cùng kiến trúc (encoder đóng băng, attention hunk → file → commit).

Biến thể (giống hệt nhau trừ loss/đầu vào):
  hist_only : chỉ feature lịch sử + thống kê diff, BCE           (code embedding có giúp không?)
  bce       : + embedding code, BCE pass/fail                    (mốc)
  bce+type  : + CE loại lỗi trên commit fail (multi-task)        (lợi ích do nhãn loại lỗi hay do contrastive?)
  supcon1   : BCE + λ1·SupCon(pass/fail)                         (contrastive một tầng)
  hcl       : BCE + λ1·SupCon(pass/fail) + λ2·SupCon(loại lỗi)   (phương pháp đề tài)
Chia theo thời gian như pilot: 70% đầu train (80% fit, 20% cuối chọn epoch), 30% sau test.
λ1 = λ2 = 0.5, τ = 0.1 cố định trước, không tinh chỉnh trên test.
Loại lỗi đánh giá bằng linear probe (LR) trên embedding z của commit fail tập train, áp dụng như nhau cho mọi biến thể.

    uv run --group exp python -m project3.pilot.hcl_train --seeds 5
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

from .experiment import HIST, STATS, load

TYPES = ["compile", "lint", "test"]
VARIANTS = ["hist_only", "bce", "bce+type", "supcon1", "hcl"]
LAMBDA1, LAMBDA2, TAU = 0.5, 0.5, 0.1


def meta(table: Path, diffs: Path, repos: list[str], cache: Path) -> pd.DataFrame:
    if cache.exists():
        return pd.read_parquet(cache)
    df = load(table, diffs, repos)
    df = df.drop(columns=[c for c in df.columns if c.startswith("txt_")])
    df.to_parquet(cache)
    return df


def seg_softmax_pool(x, score, seg, n):
    """Attention pooling theo đoạn: x [m,d], score [m], seg [m] -> [n,d]."""
    x, score = x.float(), score.float()  # dưới autocast, Linear trả về fp16
    mx =torch.full((n,), -1e9, device=x.device).scatter_reduce(0, seg, score, "amax")
    e = torch.exp(score - mx[seg])
    s = torch.zeros(n, device=x.device).index_add(0, seg, e)
    w = (e / s[seg]).unsqueeze(1)
    return torch.zeros(n, x.shape[1], device=x.device).index_add(0, seg, w * x)


class Net(nn.Module):
    def __init__(self, n_num, use_code=True, d=256):
        super().__init__()
        self.use_code = use_code
        self.proj = nn.Sequential(nn.Linear(768, d), nn.GELU(), nn.Dropout(0.2))
        self.att_h, self.att_f = nn.Linear(d, 1), nn.Linear(d, 1)
        self.num = nn.Sequential(nn.Linear(n_num, 64), nn.GELU())
        self.body = nn.Sequential(nn.Linear((d if use_code else 0) + 64, 256), nn.GELU(), nn.Dropout(0.2), nn.Linear(256, 128))
        self.head_bin, self.head_type = nn.Linear(128, 1), nn.Linear(128, len(TYPES))
        self.head_con = nn.Sequential(nn.Linear(128, 128), nn.GELU(), nn.Linear(128, 64))

    def forward(self, hunks, hunk_file, file_commit, num):
        parts = [self.num(num)]
        if self.use_code:
            h = self.proj(hunks)
            f = seg_softmax_pool(h, self.att_h(h).squeeze(1), hunk_file, len(file_commit))
            c = seg_softmax_pool(f, self.att_f(f).squeeze(1), file_commit, num.shape[0])
            parts.insert(0, c)
        z = self.body(torch.cat(parts, 1))
        return self.head_bin(z).squeeze(1), self.head_type(z), F.normalize(self.head_con(z), dim=1), z


def supcon(feat, labels):
    """Supervised contrastive loss (Khosla 2020); bỏ anchor không có positive."""
    if len(labels) < 2:
        return feat.sum() * 0
    sim = feat @ feat.T / TAU
    eye = torch.eye(len(labels), device=feat.device, dtype=torch.bool)
    sim = sim.masked_fill(eye, -1e9)
    logp = sim - torch.logsumexp(sim, 1, keepdim=True)
    pos = (labels[:, None] == labels[None, :]) & ~eye
    n = pos.sum(1)
    ok = n > 0
    if not ok.any():
        return feat.sum() * 0
    return -((logp * pos).sum(1)[ok] / n[ok]).mean()


class Data:
    """Giữ embedding hunk trên GPU, ghép batch commit thành (hunks, hunk_file cục bộ, file_commit cục bộ)."""

    def __init__(self, npz: Path, shas: list[str]):
        z = np.load(npz)
        self.emb = torch.from_numpy(z["emb"]).cuda()
        hf, fc, all_shas = z["hunk_file"], z["file_commit"], list(z["shas"])
        pos = {s: i for i, s in enumerate(all_shas)}
        self.h0 = np.searchsorted(fc[hf], np.arange(len(all_shas) + 1))  # hunk liền nhau theo commit
        self.f0 = np.searchsorted(fc, np.arange(len(all_shas) + 1))
        self.hf = hf
        self.idx = np.array([pos[s] for s in shas])

    def batch(self, rows):
        cs = self.idx[rows]
        hunk_ids = np.concatenate([np.arange(self.h0[c], self.h0[c + 1]) for c in cs])
        files = [np.arange(self.f0[c], self.f0[c + 1]) for c in cs]
        file_local = {f: i for i, f in enumerate(np.concatenate(files))}
        file_commit = np.concatenate([np.full(len(fs), k) for k, fs in enumerate(files)])
        hunk_file = np.array([file_local[f] for f in self.hf[hunk_ids]])
        t = lambda a: torch.as_tensor(a, device="cuda")
        return self.emb[t(hunk_ids)].float(), t(hunk_file), t(file_commit)


def run(variant, seed, data, X, y, typ, tr, va, te, epochs=40, bs=256, patience=6):
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    net = Net(X.shape[1], use_code=variant != "hist_only").cuda()
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3, weight_decay=1e-4)
    Xt, yt, tt = (torch.as_tensor(a, device="cuda") for a in (X, y.astype(np.float32), typ))
    pos_w = torch.tensor((y[tr] == 0).sum() / max(1, (y[tr] == 1).sum()), device="cuda")
    # lấy mẫu để mỗi batch có ~40% fail (SupCon cần đủ positive)
    w = np.where(y[tr] == 1, 0.4 / (y[tr] == 1).sum(), 0.6 / (y[tr] == 0).sum())

    def predict(rows):
        net.eval()
        out_p, out_z = [], []
        with torch.no_grad():
            for i in range(0, len(rows), 512):
                r = rows[i:i + 512]
                logit, _, _, z = net(*data.batch(r), Xt[r])
                out_p.append(torch.sigmoid(logit).cpu().numpy())
                out_z.append(z.cpu().numpy())
        return np.concatenate(out_p), np.concatenate(out_z)

    best, best_state, bad = -1, None, 0
    for ep in range(epochs):
        net.train()
        for _ in range(max(1, len(tr) // bs)):
            r = rng.choice(tr, bs, p=w / w.sum())
            logit, tlog, feat, _ = net(*data.batch(r), Xt[r])
            yb, tb = yt[r], tt[r]
            # pos_weight trả lại tỉ lệ thật vì batch đã được lấy mẫu lệch về fail
            loss = F.binary_cross_entropy_with_logits(logit, yb, pos_weight=pos_w * 0.6 / 0.4)
            fail = tb >= 0
            if variant == "bce+type" and fail.any():
                loss = loss + F.cross_entropy(tlog[fail], tb[fail])
            if variant in ("supcon1", "hcl"):
                loss = loss + LAMBDA1 * supcon(feat, yb.long())
            if variant == "hcl" and fail.sum() > 1:
                loss = loss + LAMBDA2 * supcon(feat[fail], tb[fail])
            opt.zero_grad()
            loss.backward()
            opt.step()
        p, _ = predict(va)
        score = average_precision_score(y[va], p)
        if score > best:
            best, bad = score, 0
            best_state = {k: v.detach().clone() for k, v in net.state_dict().items()}
        else:
            bad += 1
            if bad >= patience:
                break
    net.load_state_dict(best_state)
    p_te, z_te = predict(te)
    _, z_tr = predict(tr)
    return p_te, z_tr, z_te, ep + 1


def metrics(y, p, p3):
    return {"pr_auc": average_precision_score(y, p), "roc_auc": roc_auc_score(y, p),
            "p3_pr_auc": average_precision_score(y[p3], p[p3]), "p3_roc_auc": roc_auc_score(y[p3], p[p3])}


def type_probe(z_tr, z_te, typ, tr, te):
    a, b = tr[typ[tr] >= 0], te[typ[te] >= 0]
    sc = StandardScaler().fit(z_tr[typ[tr] >= 0])
    m = LogisticRegression(class_weight="balanced", max_iter=3000).fit(sc.transform(z_tr[typ[tr] >= 0]), typ[a])
    return f1_score(typ[b], m.predict(sc.transform(z_te[typ[te] >= 0])), average="macro")


def main(a):
    df = meta(a.table, a.diffs, a.repos, a.meta)
    cut = int(len(df) * 0.7)
    z = np.load(a.emb)
    have = set(z["shas"])
    df["split"] = np.where(np.arange(len(df)) < cut, "train", "test")
    df = df[df.head_sha.isin(have)].reset_index(drop=True)
    tr_all = np.where(df.split == "train")[0]
    tr, va = tr_all[:int(len(tr_all) * 0.8)], tr_all[int(len(tr_all) * 0.8):]
    te = np.where(df.split == "test")[0]
    rc = [c for c in df.columns if c.startswith("repo_")]
    cols = HIST + STATS + rc
    X = np.log1p(np.clip(df[cols].astype(float).values, 0, None))
    X = StandardScaler().fit(X[tr]).transform(X).astype(np.float32)
    y = df.y.values.astype(int)
    lab = df.label.replace({"dependency": "compile", "buildconfig": "compile"})
    typ = np.where(y == 1, lab.map({t: i for i, t in enumerate(TYPES)}).fillna(-1), -1).astype(int)
    p3 = df.prev_fail.values[te] == 0
    data = Data(a.emb, list(df.head_sha))
    print(f"train {len(tr)} | val {len(va)} | test {len(te)} (P3 {p3.sum()}); fail test {y[te].sum()}", flush=True)

    res = {"baselines": {}, "runs": []}
    res["baselines"]["Parrot"] = metrics(y[te], df.prev_fail.values[te].astype(float), p3)
    lr = LogisticRegression(class_weight="balanced", max_iter=3000).fit(X[tr], y[tr])
    res["baselines"]["LR history"] = metrics(y[te], lr.predict_proba(X[te])[:, 1], p3)
    res["baselines"]["LR history"]["type_macro_f1"] = type_probe(X[tr], X[te], typ, tr, te)
    for name, m in res["baselines"].items():
        print(f"{name:12} " + " ".join(f"{k} {v:.3f}" for k, v in m.items()), flush=True)
    preds = {}
    for v in a.variants:
        for s in range(a.seeds):
            p, z_tr, z_te, ep = run(v, s, data, X, y, typ, tr, va, te)
            m = {**metrics(y[te], p, p3), "type_macro_f1": type_probe(z_tr, z_te, typ, tr, te), "epochs": ep}
            res["runs"].append({"variant": v, "seed": s, **m})
            preds[(v, s)] = p
            print(f"{v:9} seed {s}: " + " ".join(f"{k} {val:.3f}" for k, val in m.items()), flush=True)
    runs = pd.DataFrame(res["runs"])
    keys = ["pr_auc", "roc_auc", "p3_pr_auc", "p3_roc_auc", "type_macro_f1"]
    summary = runs.groupby("variant")[keys].agg(["mean", "std"]).round(3).reindex(a.variants)
    print("\n" + summary.to_string())
    # so sánh theo cặp cùng seed: hcl - bce, hcl - bce+type
    for other in ("bce", "bce+type", "supcon1"):
        if "hcl" in a.variants and other in a.variants:
            d = runs[runs.variant == "hcl"].set_index("seed")[keys] - runs[runs.variant == other].set_index("seed")[keys]
            res[f"hcl_minus_{other}"] = {k: {"mean": round(d[k].mean(), 4), "wins": int((d[k] > 0).sum()), "n": len(d)}
                                         for k in keys}
            print(f"hcl - {other}: " + " | ".join(f"{k} {d[k].mean():+.3f} ({(d[k] > 0).sum()}/{len(d)})" for k in keys))
    res["summary"] = json.loads(summary.to_json())
    a.out.write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")
    print(f"Đã lưu {a.out}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", type=Path, default=Path("data/processed/commits_pilot.parquet"))
    ap.add_argument("--diffs", type=Path, default=Path("data/processed/pilot_diffs.csv"))
    ap.add_argument("--repos", nargs="+", default=["apache/druid", "apache/paimon"])
    ap.add_argument("--meta", type=Path, default=Path("data/processed/hcl_pilot/meta.parquet"))
    ap.add_argument("--emb", type=Path, default=Path("data/processed/hcl_pilot/emb.npz"))
    ap.add_argument("--variants", nargs="+", default=VARIANTS)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--out", type=Path, default=Path("data/processed/hcl_pilot/results.json"))
    main(ap.parse_args())
