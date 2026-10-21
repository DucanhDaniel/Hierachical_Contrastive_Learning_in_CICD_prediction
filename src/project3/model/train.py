"""Huấn luyện + đánh giá mô hình đọc log trên một fold chéo repo (bước 3, docs/huong-moi-phan-loai-sau-ci.md).

Biến thể loss (--variants): `ce` (CE 3 tầng), `hcl` (+ SupCon từng tầng + bộ nhớ), `soft` (+ SupCon cặp dương mềm theo cây:
cùng lá 1, anh em SIB_W), `proxy` (+ contrastive theo nguyên mẫu phân cấp). Tuỳ chọn:
  --tfidf          mô hình lai: thêm log xác suất lá của TF-IDF (tfidf_fold{k}.parquet, model.tfidf)
  --sampler mpc    batch = lá x 2 run (bỏ trọng số lớp trong CE)
  --share-parent   trọng số đầu lá = trọng số loại cha + độ lệch (phạt L2)
  --save-repr      lưu attention từng đoạn + z (test) và z của một phần tập train
Che bằng chứng: với xác suất --mask-p, xoá mọi dòng chứa dòng bằng chứng trước khi mã hoá. Chọn epoch theo macro-F1 tầng 2
trung bình (val nguyên vẹn, val đã che); đánh giá trên test nguyên vẹn và test đã che.

    python -m project3.model.train --data data/kaggle_log_ds --fold 0 --variants ce hcl --out results.json
Đầu ra: results.json (chỉ số), results.preds.parquet (dự đoán + logp; + attn, z khi --save-repr),
results.train_{variant}{seed}.parquet (z tập train, khi --save-repr).
"""
import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from .data import fold_split, load_pack
from .labels import LabelTree
from .metrics import hier_scores
from .text import ci_context, clip_chunk, mask_text


@dataclass
class Fold:
    """Dữ liệu của một fold: runs + đoạn log + cây nhãn + chỉ số train/val/test (+ đặc trưng TF-IDF nếu có)."""
    runs: pd.DataFrame
    chunks: dict
    tree: LabelTree
    tr: np.ndarray
    va: np.ndarray
    te: np.ndarray
    tfidf: dict = None  # {False: mảng log nguyên vẹn, True: mảng log đã che}, cùng thứ tự với runs

    def __post_init__(self):
        r = self.runs
        self.run_id = r.run_id.tolist()
        self.keys = r.key.fillna("").tolist()
        self.ctx = [ci_context(w, j, s)[:400] for w, j, s in
                    zip(r.workflow.fillna(""), r.failed_job_names.fillna(""), r.failed_steps.fillna(""))]
        self.leaf = r.leaf.values

    def inputs(self, rows, masked):
        """Đầu vào của mạng cho các run `rows` (masked[k]: che bằng chứng run thứ k).
        Trả về (texts, c2j, j2r, pos), pos[i] = (run trong batch, job, đoạn) của đoạn i."""
        texts, c2j, j2r, pos = [], [], [], []
        for k, (r, mk) in enumerate(zip(rows, masked)):
            for ji, job in enumerate(self.chunks[self.run_id[r]]):
                parts = [(ci, clip_chunk(mask_text(t, self.keys[r]) if mk else t)) for ci, t in enumerate(job)]
                parts = [(ci, p) for ci, p in parts if p.strip()] or [(-1, "(trống)")]
                j2r.append(k)
                for ci, p in parts:
                    texts.append(p)
                    c2j.append(len(j2r) - 1)
                    pos.append((k, ji, ci))
        return texts, c2j, j2r, pos


def load_tfidf(path: Path, runs: pd.DataFrame) -> dict:
    tf = pd.read_parquet(path).set_index("run_id")
    tf = tf[~tf.index.duplicated()].reindex(runs.run_id)  # vài run lặp dòng trong run_dataset
    assert not tf.full.isna().any(), "thiếu đặc trưng TF-IDF cho một số run"
    return {False: np.stack(tf.full.values).astype(np.float32), True: np.stack(tf.masked.values).astype(np.float32)}


def run_variant(fold: Fold, variant: str, seed: int, a, out_preds: list) -> dict:
    import torch
    import torch.nn.functional as F
    from .nn.losses import MemoryBank, class_weights, hcl_loss, proxy_loss, soft_supcon_mem
    from .nn.net import LogNet, decode
    from .nn.samplers import MPCSampler, random_batches

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    tree, runs, tr, va, te = fold.tree, fold.runs, fold.tr, fold.va, fold.te
    y1 = torch.tensor([tree.l1.index(tree.group[l]) for l in runs.label_l2], device=dev)
    y2 = torch.tensor([tree.l2.index(l) for l in runs.label_l2], device=dev)
    y3 = torch.tensor([tree.l3.index(l) if l in tree.l3 else -1 for l in runs.leaf], device=dev)
    w1, w2, w3 = (class_weights(y, tr, len(L)) for y, L in ((y1, tree.l1), (y2, tree.l2), (y3, tree.l3)))
    if a.sampler == "mpc":  # sampler đã cân bằng lớp, không bù thêm bằng trọng số
        w1, w2, w3 = None, None, None

    net = LogNet(tree, dev, freeze_layers=a.freeze_layers, tfidf_dim=fold.tfidf[False].shape[1] if fold.tfidf else 0,
                 share_parent=a.share_parent, proxy=variant == "proxy").to(dev)
    enc_params = [p for p in net.enc.parameters() if p.requires_grad]
    head_params = [p for n, p in net.named_parameters() if not n.startswith("enc.")]
    opt = torch.optim.AdamW([{"params": enc_params, "lr": a.lr_enc}, {"params": head_params, "lr": 1e-3}],
                            weight_decay=0.01)
    scaler = torch.amp.GradScaler(enabled=dev == "cuda")
    autocast = lambda: torch.autocast(dev, dtype=torch.float16, enabled=dev == "cuda")

    def forward(rows, masked, keep=False):
        texts, c2j, j2r, pos = fold.inputs(rows, masked)
        tf = np.stack([fold.tfidf[bool(m)][x] for x, m in zip(rows, masked)]) if fold.tfidf else None
        out = net(texts, c2j, j2r, len(rows), [fold.ctx[x] for x in rows], tf, max_tokens=a.max_tokens, keep=keep)
        return out, pos

    def predict(rows, masked, keep=False):
        """-> (lá dự đoán, log xác suất 3 tầng, attention từng đoạn (JSON) hoặc None, z hoặc None)."""
        net.eval()
        preds, lps, attn, zs = [], [], [], []
        with torch.no_grad(), autocast():
            for i in range(0, len(rows), a.eval_batch):
                b = rows[i:i + a.eval_batch]
                (o1, o2, o3, _, extra), pos = forward(b, [masked] * len(b), keep)
                p, lp = decode(o1, o2, o3, tree)
                preds += p
                lps.append(lp)
                if keep:  # trọng số đoạn trong cả run = trọng số trong job x trọng số job
                    per_run = [[] for _ in b]
                    for (k, ji, ci), x in zip(pos, extra["w"]):
                        per_run[k].append((ji, ci, round(float(x), 4)))
                    attn += [json.dumps(x) for x in per_run]
                    zs += list(extra["z"])
        return preds, np.concatenate(lps), (attn if keep else None), (zs if keep else None)

    def contrastive(feat, bt, step):
        lab = torch.stack([y1[bt], y2[bt], y3[bt]], 1)
        if variant == "proxy":
            return proxy_loss(feat.float(), lab, net.proxy_parent, net.proxy_delta, net.leaf_parent, C.TAU, C.PROXY_PARENT_W)
        feat = feat.float()
        mfeat, mlab = memory.get(step, C.MEMORY_WARMUP)
        loss = (hcl_loss(feat, lab, mfeat, mlab, C.TAU) if variant == "hcl"
                else soft_supcon_mem(feat, lab, mfeat, mlab, C.TAU, C.SIB_W))
        memory.push(feat, lab)
        return loss

    sampler = MPCSampler(tr, fold.leaf) if a.sampler == "mpc" else None
    memory = MemoryBank(C.MEMORY, 64, 3, dev)
    best, best_state, t0, step = -1.0, None, time.time(), 0
    va_eval = va[: a.val_max]
    for ep in range(a.epochs):
        net.train()
        for b in (sampler(rng, a.batch) if sampler else random_batches(rng, tr, a.batch)):
            mk = (rng.random(len(b)) < a.mask_p).tolist()
            with autocast():
                (o1, o2, o3, feat, _), _ = forward(b, mk)
            bt = torch.tensor(b, device=dev)
            loss = (F.cross_entropy(o1.float(), y1[bt], weight=w1) + F.cross_entropy(o2.float(), y2[bt], weight=w2)
                    + F.cross_entropy(o3.float(), y3[bt], weight=w3, ignore_index=-1))
            if a.share_parent:
                loss = loss + C.SHARE_L2 * net.h3.weight.float().pow(2).sum()
            if variant != "ce":
                loss = loss + C.LAMBDA * contrastive(feat, bt, step)
            opt.zero_grad()
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            step += 1
            if step % 200 == 0:
                print(f"    {variant} ep {ep + 1} step {step} loss {loss.item():.3f} ({time.time() - t0:.0f}s)", flush=True)
            if a.max_steps and step >= a.max_steps:
                break
        sv = np.mean([hier_scores(fold.leaf[va_eval].tolist(), predict(va_eval, m)[0], tree.parent, tree.group)["macroF1_l2"]
                      for m in (False, True)])
        print(f"  {variant} seed {seed} epoch {ep + 1}: val macro-F1 tầng 2 {sv:.3f} ({time.time() - t0:.0f}s)", flush=True)
        if sv > best:
            best, best_state = sv, {k: v.detach().to("cpu", copy=True) for k, v in net.state_dict().items()}
    net.load_state_dict(best_state)

    res = {}
    for name, m in (("full", False), ("masked", True)):
        p, lp, attn, z = predict(te, m, keep=a.save_repr)
        res[name] = hier_scores(fold.leaf[te].tolist(), p, tree.parent, tree.group)
        df = pd.DataFrame({"variant": variant, "seed": seed, "test": name, "run_id": runs.run_id.values[te],
                           "pred": p, "logp": list(lp)})
        if a.save_repr:
            df["attn"], df["z"] = attn, z
        out_preds.append(df)
        print(f"  {variant} test {name}: macro-F1 lá {res[name]['macroF1_l3']:.3f} tầng 2 {res[name]['macroF1_l2']:.3f} "
              f"tầng 1 {res[name]['macroF1_l1']:.3f}", flush=True)
    if a.save_repr:  # z của một phần tập train (log nguyên vẹn) cho kNN / truy hồi / định tuyến
        sub = np.random.default_rng(seed).permutation(tr)[:a.repr_train]
        p, _, _, z = predict(sub, False, keep=True)
        pd.DataFrame({"variant": variant, "seed": seed, "run_id": runs.run_id.values[sub], "pred": p, "z": z}
                     ).to_parquet(Path(a.out).with_suffix(f".train_{variant}{seed}.parquet"), index=False)
    res["minutes"] = round((time.time() - t0) / 60, 1)
    del net, opt
    torch.cuda.empty_cache()
    return res


def main(a) -> None:
    runs, chunks, tree = load_pack(a.data)
    if a.smoke:
        idx = np.concatenate([np.random.default_rng(0).permutation(np.where(runs.repo_fold.values == k)[0])[:60]
                              for k in range(C.N_FOLDS)])
        runs = runs.iloc[np.sort(idx)].reset_index(drop=True)
    tr, va, te = fold_split(runs.repo_fold.values, a.fold)
    va = np.random.default_rng(0).permutation(va)
    tfidf = load_tfidf((a.tfidf_dir or a.data) / f"tfidf_fold{a.fold}.parquet", runs) if a.tfidf else None
    fold = Fold(runs, chunks, tree, tr, va, te, tfidf)
    print(f"fold {a.fold}: train {len(tr)}, val {len(va)} (dùng {min(len(va), a.val_max)}), test {len(te)} run", flush=True)
    results, preds = {"args": {k: str(v) for k, v in vars(a).items()}, "tree": tree.to_dict()}, []
    for variant in a.variants:
        for seed in range(a.seed_start, a.seed_start + a.seeds):
            results[f"{variant}_seed{seed}"] = run_variant(fold, variant, seed, a, preds)
            Path(a.out).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    if preds:
        pd.concat(preds).to_parquet(Path(a.out).with_suffix(".preds.parquet"), index=False)


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--fold", type=int, default=0)
    ap.add_argument("--variants", nargs="+", default=["ce", "hcl"], choices=["ce", "hcl", "soft", "proxy"])
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
    ap.add_argument("--smoke", action="store_true", help="60 run mỗi fold, để thử nhanh")
    ap.add_argument("--tfidf", action="store_true", help="biến thể lai: thêm xác suất TF-IDF (tfidf_fold{k}.parquet)")
    ap.add_argument("--sampler", choices=["random", "mpc"], default="random", help="mpc: batch = lá x 2 run")
    ap.add_argument("--share-parent", action="store_true", help="trọng số lá = trọng số loại cha + độ lệch")
    ap.add_argument("--save-repr", action="store_true", help="lưu attention từng đoạn + z (test) và z của tập train")
    ap.add_argument("--repr-train", type=int, default=10000, help="số run train lưu z")
    ap.add_argument("--tfidf-dir", type=Path, default=None, help="thư mục tfidf_fold{k}.parquet (mặc định --data)")
    ap.add_argument("--out", default="results.json")
    return ap


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(parser().parse_args())
