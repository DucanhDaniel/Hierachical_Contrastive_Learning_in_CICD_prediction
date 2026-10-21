"""Mô hình đọc log phân loại lỗi CI theo cây nhãn 3 tầng (bước 3, slide Phụ lục A, docs/huong-moi-phan-loai-sau-ci.md).

Mỗi run fail: các đoạn log (≤8, đã chọn ở log_pack) -> UniXcoder (đóng băng embeddings + 6 lớp dưới), trung bình token
-> attention đoạn -> job -> run (vector r); ngữ cảnh CI "workflow | job | step fail" mã hoá cùng encoder -> 64 số;
ghép -> MLP -> z (256). Ba đầu phân loại (tầng 1: build/test/env, tầng 2: 7 loại, tầng 3: lá đủ mẫu) dùng khi dự đoán;
đầu so sánh (64 chiều) chỉ dùng khi huấn luyện, SupCon theo từng tầng + bộ nhớ đặc trưng (biến thể `hcl`).
Biến thể lai (--tfidf): thêm log xác suất lá của TF-IDF (stacking, tfidf_fold{k}.parquet do tfidf_feats tạo)
-> 64 số, ghép cùng r và ngữ cảnh trước MLP.
Lá hiếm (20/10): --sampler mpc lấy batch = batch/2 lá x 2 run (lá chọn theo xác suất ~ căn bậc hai số mẫu, bỏ trọng số
lớp trong CE) để SupCon luôn có cặp dương; --share-parent: trọng số đầu lá = trọng số loại cha ở đầu tầng 2 + độ lệch
(phạt L2 SHARE_L2), lá hiếm mượn biểu diễn của lá anh em cùng cha.
Biến thể loss (20/10, sửa "anh em bị kéo quá gần" đo trên z): `soft` = một SupCon với cặp dương mềm theo cây (cùng lá 1,
anh em SIB_W, khác cha 0); `proxy` = contrastive theo nguyên mẫu phân cấp (nguyên mẫu lá = nguyên mẫu cha + độ lệch, mỗi run
kéo về nguyên mẫu lá của mình, không cần cặp dương trong batch).
Che bằng chứng: với xác suất --mask-p, xoá mọi dòng chứa dòng bằng chứng của quy tắc trước khi mã hoá.
Dự đoán nhất quán theo cây: tầng 2 = argmax log p1(nhóm) + log p2(loại); lá = argmax p3 trong các con của loại đó.
Đánh giá trên test nguyên vẹn và test đã che (cùng định nghĩa với log_baselines).

    python -m project3.pilot.log_hcl --data data/kaggle_log_ds --fold 0 --variants ce hcl --out results.json
"""
import argparse
import json
import random
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

TAU, LAMBDA, MEMORY, MEMORY_WARMUP, SHARE_L2 = 0.1, 0.5, 512, 50, 1e-3
SIB_W, PROXY_PARENT_W = 0.4, 0.3  # 20/10: trọng số cặp anh em (soft), trọng số loss nguyên mẫu cha (proxy); chốt trước, không dò


def mask_text(text: str, key: str) -> str:
    return "\n".join(l for l in text.splitlines() if key not in l) if key else text


def clip_chunk(text: str, n: int = 1100) -> str:
    """Giữ dòng đầu (ranh giới goal/task) + phần cuối đoạn; đủ dư cho 256 token."""
    first, _, rest = text.partition("\n")
    return first[:200] + ("\n" + rest[-n:] if rest else "")


def load(data: Path):
    runs = pd.read_parquet(data / "runs.parquet")
    ch = pd.read_parquet(data / "chunks.parquet").sort_values(["run_id", "job_id", "chunk_idx"])
    tree = json.loads((data / "label_tree.json").read_text(encoding="utf-8"))
    chunks = {}
    for (rid, jid), g in ch.groupby(["run_id", "job_id"], sort=False):
        chunks.setdefault(rid, []).append(g.text.tolist())
    return runs, chunks, tree


def scores(true_leaf, pred_leaf, parent, group) -> dict:
    t2 = [parent.get(x, x) for x in true_leaf]
    p2 = [parent.get(x, x) for x in pred_leaf]
    t1, p1 = [group[x] for x in t2], [group.get(x, "?") for x in p2]
    labels3 = sorted(set(true_leaf))
    return {"n": len(true_leaf), "acc_l3": float(np.mean(np.array(true_leaf) == np.array(pred_leaf))),
            "macroF1_l3": f1_score(true_leaf, pred_leaf, labels=labels3, average="macro", zero_division=0),
            "macroF1_l2": f1_score(t2, p2, labels=sorted(set(t2)), average="macro", zero_division=0),
            "macroF1_l1": f1_score(t1, p1, labels=sorted(set(t1)), average="macro", zero_division=0),
            "F1_l3": dict(zip(labels3, map(float, f1_score(true_leaf, pred_leaf, labels=labels3, average=None,
                                                            zero_division=0))))}


def run_variant(runs, chunks, tree, tr, va, te, variant, seed, a, out_preds):
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from transformers import AutoModel, AutoTokenizer

    def seg_softmax_pool(x, score, seg, n):
        """Attention pooling theo nhóm (như hcl_train.seg_softmax_pool; chép vào để file chạy độc lập trên Kaggle).
        Trả về (vector gộp, trọng số của từng phần tử trong nhóm)."""
        x, score = x.float(), score.float()
        mx = torch.full((n,), -1e9, device=x.device).scatter_reduce(0, seg, score, "amax")
        e = torch.exp(score - mx[seg])
        s = torch.zeros(n, device=x.device).index_add(0, seg, e)
        w = e / s[seg]
        return torch.zeros(n, x.shape[1], device=x.device).index_add(0, seg, w.unsqueeze(1) * x), w

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    L1, L2, L3, group, parent = tree["l1"], tree["l2"], tree["l3"], tree["group"], tree["parent"]
    y1 = torch.tensor([L1.index(group[l]) for l in runs.label_l2], device=dev)
    y2 = torch.tensor([L2.index(l) for l in runs.label_l2], device=dev)
    y3 = torch.tensor([L3.index(l) if l in L3 else -1 for l in runs.leaf], device=dev)
    keys, rid = runs.key.fillna("").tolist(), runs.run_id.tolist()
    ctx = [f"workflow: {w} | job: {j} | step: {s}"[:400] for w, j, s in
           zip(runs.workflow.fillna(""), runs.failed_job_names.fillna(""), runs.failed_steps.fillna(""))]
    tok = AutoTokenizer.from_pretrained("microsoft/unixcoder-base")
    if a.tfidf:  # log xác suất TF-IDF theo run, bản nguyên vẹn / đã che
        tf = pd.read_parquet((a.tfidf_dir or a.data) / f"tfidf_fold{a.fold}.parquet").set_index("run_id")
        tf = tf[~tf.index.duplicated()].reindex(runs.run_id)  # 3 run lặp dòng trong run_dataset
        assert not tf.full.isna().any(), "thiếu đặc trưng TF-IDF cho một số run"
        TF = {False: np.stack(tf.full.values).astype(np.float32), True: np.stack(tf.masked.values).astype(np.float32)}

    def weights(y, k):  # căn bậc hai nghịch tần suất trên tập train
        c = np.bincount(y[tr][y[tr] >= 0].cpu().numpy(), minlength=k).astype(float)
        w = np.sqrt(c.sum() / (k * np.maximum(c, 1)))
        return torch.tensor(w / w.mean(), dtype=torch.float32, device=dev)
    w1, w2, w3 = weights(y1, len(L1)), weights(y2, len(L2)), weights(y3, len(L3))
    if a.sampler == "mpc":  # sampler đã cân bằng lớp, không bù thêm bằng trọng số
        w1, w2, w3 = None, None, None
    p3 = torch.tensor([L2.index(parent.get(l, l)) for l in L3], device=dev)  # loại cha (tầng 2) của từng lá

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
            self.att_c, self.att_j = nn.Linear(d, 1), nn.Linear(d, 1)
            self.ctx = nn.Sequential(nn.Linear(d, 64), nn.GELU())
            if a.tfidf:
                self.tf = nn.Sequential(nn.Linear(TF[False].shape[1], 64), nn.GELU())
            self.body = nn.Sequential(nn.Dropout(0.1), nn.Linear(d + 64 + 64 * bool(a.tfidf), 256), nn.GELU(), nn.Dropout(0.1))
            self.h1, self.h2, self.h3 = nn.Linear(256, len(L1)), nn.Linear(256, len(L2)), nn.Linear(256, len(L3))
            if a.share_parent:  # h3.weight đóng vai độ lệch so với trọng số loại cha
                nn.init.zeros_(self.h3.weight)
            self.con = nn.Sequential(nn.Linear(256, 128), nn.GELU(), nn.Linear(128, 64))
            if variant == "proxy":  # nguyên mẫu cha (tầng 2) + độ lệch lá
                self.proxy_parent = nn.Parameter(torch.randn(len(L2), 64) * 0.1)
                self.proxy_delta = nn.Parameter(torch.zeros(len(L3), 64))
            self.keep, self.attn, self.z = False, None, None  # lưu attention + z khi dự đoán (--save-repr)

        def embed(self, texts, max_len):
            e = tok(texts, padding=True, truncation=True, max_length=max_len, return_tensors="pt").to(dev)
            h = self.enc(**e).last_hidden_state
            m = e["attention_mask"].unsqueeze(-1).to(h.dtype)
            return ((h * m).sum(1) / m.sum(1)).float()

        def forward(self, rows, masked):
            texts, c2j, j2r, pos = [], [], [], []
            for k, (r, mk) in enumerate(zip(rows, masked)):
                for ji, job in enumerate(chunks[rid[r]]):
                    parts = [(ci, clip_chunk(mask_text(t, keys[r]) if mk else t)) for ci, t in enumerate(job)]
                    parts = [(ci, p) for ci, p in parts if p.strip()] or [(-1, "(trống)")]
                    j2r.append(k)
                    for ci, p in parts:
                        texts.append(p)
                        c2j.append(len(j2r) - 1)
                        pos.append((k, ji, ci))  # run trong batch, job, đoạn (thứ tự trong log_pack)
            h = self.embed(texts, a.max_tokens)
            c2j, j2r = torch.tensor(c2j, device=dev), torch.tensor(j2r, device=dev)
            j, wc = seg_softmax_pool(h, self.att_c(h).squeeze(1), c2j, len(j2r))
            r, wj = seg_softmax_pool(j, self.att_j(j).squeeze(1), j2r, len(rows))
            if self.keep:  # trọng số đoạn trong cả run = trọng số trong job x trọng số job
                w = (wc * wj[c2j]).detach().cpu().numpy()
                self.attn = [[] for _ in rows]
                for (k, ji, ci), x in zip(pos, w):
                    self.attn[k].append((ji, ci, round(float(x), 4)))
            feats = [r, self.ctx(self.embed([ctx[x] for x in rows], 64))]
            if a.tfidf:
                feats.append(self.tf(torch.tensor(np.stack([TF[bool(m)][x] for x, m in zip(rows, masked)]), device=dev)))
            z = self.body(torch.cat(feats, 1))
            if self.keep:
                self.z = z.detach().float().cpu().numpy().astype(np.float16)
            o3 = (z @ (self.h2.weight[p3] + self.h3.weight).T + self.h3.bias) if a.share_parent else self.h3(z)
            return self.h1(z), self.h2(z), o3, F.normalize(self.con(z), dim=1)

    def soft_supcon_mem(feat, lab, mfeat, mlab):
        """SupCon một loss, trọng số dương theo cây: cùng lá 1, cùng cha khác lá SIB_W (lá -1 coi theo tầng 2), khác 0."""
        keys_, kl = torch.cat([feat, mfeat]), torch.cat([lab, mlab])
        n = len(lab)
        sim = feat @ keys_.T / TAU
        self_ = torch.zeros_like(sim, dtype=torch.bool)
        self_[:, :n] = torch.eye(n, dtype=torch.bool, device=dev)
        sim = sim.masked_fill(self_, -1e9)
        logp = sim - torch.logsumexp(sim, 1, keepdim=True)
        same3 = (lab[:, None, 2] == kl[None, :, 2]) & (lab[:, None, 2] >= 0)
        same2 = lab[:, None, 1] == kl[None, :, 1]
        w = torch.where(same3, 1.0, torch.where(same2, SIB_W, 0.0)).masked_fill(self_, 0.0)
        ok = w.sum(1) > 0
        if not ok.any():
            return feat.sum() * 0
        return -((logp * w).sum(1)[ok] / w.sum(1)[ok]).mean()

    def proxy_loss(feat, lab):
        """Kéo run về nguyên mẫu lá (softmax trên mọi lá) + nguyên mẫu cha (trọng số PROXY_PARENT_W)."""
        pl = F.normalize(net.proxy_parent[p3] + net.proxy_delta, dim=1)
        pp = F.normalize(net.proxy_parent, dim=1)
        loss = PROXY_PARENT_W * F.cross_entropy(feat @ pp.T / TAU, lab[:, 1])
        if (lab[:, 2] >= 0).any():
            loss = loss + F.cross_entropy(feat @ pl.T / TAU, lab[:, 2], ignore_index=-1)
        return loss

    def supcon_mem(feat, lab, mfeat, mlab):
        keys_, kl = torch.cat([feat, mfeat]), torch.cat([lab, mlab])
        n = len(lab)
        sim = feat @ keys_.T / TAU
        self_ = torch.zeros_like(sim, dtype=torch.bool)
        self_[:, :n] = torch.eye(n, dtype=torch.bool, device=dev)
        sim = sim.masked_fill(self_ | (kl < 0)[None, :], -1e9)
        logp = sim - torch.logsumexp(sim, 1, keepdim=True)
        pos = (lab[:, None] == kl[None, :]) & (kl >= 0)[None, :] & ~self_
        ok = (lab >= 0) & (pos.sum(1) > 0)
        if not ok.any():
            return feat.sum() * 0
        return -((logp * pos).sum(1)[ok] / pos.sum(1)[ok]).mean()

    net = Net().to(dev)
    enc_params = [p for p in net.enc.parameters() if p.requires_grad]
    head_params = [p for n, p in net.named_parameters() if not n.startswith("enc.")]
    opt = torch.optim.AdamW([{"params": enc_params, "lr": a.lr_enc}, {"params": head_params, "lr": 1e-3}],
                            weight_decay=0.01)
    scaler = torch.amp.GradScaler(enabled=dev == "cuda")
    children = {c: [L3.index(l) for l in L3 if parent.get(l, l) == c] for c in L2}

    def decode(o1, o2, o3):
        lp1, lp2, lp3 = (torch.log_softmax(o.float(), 1).cpu().numpy() for o in (o1, o2, o3))
        g = np.array([L1.index(group[c]) for c in L2])
        s2 = lp1[:, g] + lp2
        out = []
        for i, c in enumerate(s2.argmax(1)):
            ch = children[L2[c]]
            out.append(L3[ch[int(lp3[i, ch].argmax())]] if ch else L2[c])
        last_lp.append(np.concatenate([lp1, lp2, lp3], 1).astype(np.float16))  # log xác suất 3 tầng, để hiệu chỉnh sau
        return out

    last_lp = []

    reprs = {"attn": [], "z": []}

    def predict(rows, masked, keep=False):
        net.eval()
        net.keep = keep
        last_lp.clear()
        reprs["attn"], reprs["z"] = [], []
        preds = []
        with torch.no_grad(), torch.autocast(dev, dtype=torch.float16, enabled=dev == "cuda"):
            for i in range(0, len(rows), a.eval_batch):
                b = rows[i:i + a.eval_batch]
                o1, o2, o3, _ = net(b, [masked] * len(b))
                preds += decode(o1, o2, o3)
                if keep:
                    reprs["attn"] += [json.dumps(x) for x in net.attn]
                    reprs["z"] += list(net.z)
        net.keep = False
        return preds

    leaf_tr = runs.leaf.values[tr]
    pools = {l: tr[leaf_tr == l] for l in np.unique(leaf_tr)}
    pl = np.array(list(pools))
    pw = np.sqrt([len(pools[l]) for l in pl]); pw = pw / pw.sum()

    def batches():
        if a.sampler != "mpc":
            order = rng.permutation(tr)
            yield from (order[i:i + a.batch] for i in range(0, len(order), a.batch))
            return
        k = max(1, a.batch // 2)  # k lá x 2 run mỗi batch
        for _ in range(len(tr) // a.batch):
            pick = rng.choice(len(pl), size=min(k, len(pl)), replace=False, p=pw)
            yield np.concatenate([rng.choice(pools[pl[c]], size=2, replace=len(pools[pl[c]]) < 2) for c in pick])

    mem_f, mem_l = torch.zeros(0, 64, device=dev), torch.zeros(0, 3, dtype=torch.long, device=dev)
    best, best_state, t0, step = -1.0, None, time.time(), 0
    va_eval = va[: a.val_max]
    for ep in range(a.epochs):
        net.train()
        for b in batches():
            mk = (rng.random(len(b)) < a.mask_p).tolist()
            with torch.autocast(dev, dtype=torch.float16, enabled=dev == "cuda"):
                o1, o2, o3, feat = net(b, mk)
            bt = torch.tensor(b, device=dev)
            loss = (F.cross_entropy(o1.float(), y1[bt], weight=w1) + F.cross_entropy(o2.float(), y2[bt], weight=w2)
                    + F.cross_entropy(o3.float(), y3[bt], weight=w3, ignore_index=-1))
            if a.share_parent:
                loss = loss + SHARE_L2 * net.h3.weight.float().pow(2).sum()
            if variant == "soft":
                lab = torch.stack([y1[bt], y2[bt], y3[bt]], 1)
                feat = feat.float()
                k = len(mem_f) if step >= MEMORY_WARMUP else 0
                loss = loss + LAMBDA * soft_supcon_mem(feat, lab, mem_f[:k], mem_l[:k])
                mem_f, mem_l = torch.cat([feat.detach(), mem_f])[:MEMORY], torch.cat([lab, mem_l])[:MEMORY]
            if variant == "proxy":
                lab = torch.stack([y1[bt], y2[bt], y3[bt]], 1)
                loss = loss + LAMBDA * proxy_loss(feat.float(), lab)
            if variant == "hcl":
                lab = torch.stack([y1[bt], y2[bt], y3[bt]], 1)
                feat = feat.float()
                k = len(mem_f) if step >= MEMORY_WARMUP else 0
                for lv in range(3):
                    loss = loss + LAMBDA * supcon_mem(feat, lab[:, lv], mem_f[:k], mem_l[:k, lv])
                mem_f, mem_l = torch.cat([feat.detach(), mem_f])[:MEMORY], torch.cat([lab, mem_l])[:MEMORY]
            opt.zero_grad()
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            step += 1
            if step % 200 == 0:
                print(f"    {variant} ep {ep + 1} step {step} loss {loss.item():.3f} ({time.time() - t0:.0f}s)", flush=True)
            if a.max_steps and step >= a.max_steps:
                break
        # chọn epoch theo macro-F1 tầng 2 trung bình (val nguyên vẹn, val đã che)
        sv = np.mean([scores(runs.leaf.values[va_eval].tolist(), predict(va_eval, m), parent, group)["macroF1_l2"]
                      for m in (False, True)])
        print(f"  {variant} seed {seed} epoch {ep + 1}: val macro-F1 tầng 2 {sv:.3f} ({time.time() - t0:.0f}s)", flush=True)
        if sv > best:
            best, best_state = sv, {k: v.detach().to("cpu", copy=True) for k, v in net.state_dict().items()}
    net.load_state_dict(best_state)
    res = {}
    for name, m in (("full", False), ("masked", True)):
        p = predict(te, m, keep=a.save_repr)
        res[name] = scores(runs.leaf.values[te].tolist(), p, parent, group)
        df = pd.DataFrame({"variant": variant, "seed": seed, "test": name, "run_id": runs.run_id.values[te],
                           "pred": p, "logp": list(np.concatenate(last_lp))})
        if a.save_repr:
            df["attn"], df["z"] = reprs["attn"], reprs["z"]
        out_preds.append(df)
        print(f"  {variant} test {name}: macro-F1 lá {res[name]['macroF1_l3']:.3f} tầng 2 {res[name]['macroF1_l2']:.3f} "
              f"tầng 1 {res[name]['macroF1_l1']:.3f}", flush=True)
    if a.save_repr:  # z của một phần tập train (log nguyên vẹn) cho kNN / truy hồi / định tuyến
        sub = np.random.default_rng(seed).permutation(tr)[:a.repr_train]
        p = predict(sub, False, keep=True)
        pd.DataFrame({"variant": variant, "seed": seed, "run_id": runs.run_id.values[sub], "pred": p,
                      "z": reprs["z"]}).to_parquet(Path(a.out).with_suffix(f".train_{variant}{seed}.parquet"), index=False)
    res["minutes"] = round((time.time() - t0) / 60, 1)
    del net, opt
    torch.cuda.empty_cache()
    return res


def main(a):
    runs, chunks, tree = load(a.data)
    if a.smoke:
        idx = np.concatenate([np.random.default_rng(0).permutation(np.where(runs.repo_fold.values == k)[0])[:60]
                              for k in range(5)])
        runs = runs.iloc[np.sort(idx)].reset_index(drop=True)
    folds = runs.repo_fold.values
    te = np.where(folds == a.fold)[0]
    va = np.where(folds == (a.fold + 1) % 5)[0]
    tr = np.where((folds != a.fold) & (folds != (a.fold + 1) % 5))[0]
    va = np.random.default_rng(0).permutation(va)
    print(f"fold {a.fold}: train {len(tr)}, val {len(va)} (dùng {min(len(va), a.val_max)}), test {len(te)} run", flush=True)
    results, preds = {"args": {k: str(v) for k, v in vars(a).items()}, "tree": tree}, []
    for variant in a.variants:
        for seed in range(a.seed_start, a.seed_start + a.seeds):
            results[f"{variant}_seed{seed}"] = run_variant(runs, chunks, tree, tr, va, te, variant, seed, a, preds)
            Path(a.out).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    if preds:
        pd.concat(preds).to_parquet(Path(a.out).with_suffix(".preds.parquet"), index=False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--fold", type=int, default=0)
    ap.add_argument("--variants", nargs="+", default=["ce", "hcl"])
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--seed-start", type=int, default=0)
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--batch", type=int, default=12)
    ap.add_argument("--eval-batch", type=int, default=32)
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--freeze-layers", type=int, default=6)
    ap.add_argument("--lr-enc", type=float, default=2e-5)
    ap.add_argument("--mask-p", type=float, default=0.5)
    ap.add_argument("--val-max", type=int, default=3000)
    ap.add_argument("--max-steps", type=int, default=0)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--tfidf", action="store_true", help="biến thể lai: thêm xác suất TF-IDF (tfidf_fold{k}.parquet)")
    ap.add_argument("--sampler", choices=["random", "mpc"], default="random", help="mpc: batch = lá x 2 run")
    ap.add_argument("--share-parent", action="store_true", help="trọng số lá = trọng số loại cha + độ lệch")
    ap.add_argument("--save-repr", action="store_true", help="lưu attention từng đoạn + z (test) và z của tập train")
    ap.add_argument("--repr-train", type=int, default=10000, help="số run train lưu z")
    ap.add_argument("--tfidf-dir", type=Path, default=None, help="thư mục tfidf_fold{k}.parquet (mặc định --data)")
    ap.add_argument("--out", default="results.json")
    main(ap.parse_args())
