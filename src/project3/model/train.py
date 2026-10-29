"""Huấn luyện + đánh giá mô hình đọc log trên một fold chéo repo (bước 3, docs/huong-moi-phan-loai-sau-ci.md).

Biến thể loss (--variants): `ce` (CE 3 tầng), `hcl` (+ SupCon từng tầng + bộ nhớ), `soft` (+ SupCon cặp dương mềm theo cây:
cùng lá 1, anh em SIB_W), `proxy` (+ contrastive theo nguyên mẫu phân cấp). Tuỳ chọn:
  --tfidf          KHÔNG thuộc kiến trúc chính (bỏ 27/10/2026: TF-IDF là baseline B1, không gắn với tầng nhãn nào; chỉ bù
                   cho cách đọc 8 đoạn cuối log cũ). Giữ để chạy dòng phụ "+ TF-IDF": thêm log xác suất lá của TF-IDF
                   (tfidf_fold{k}.parquet, model.tfidf)
  --sampler mpc    batch = lá x 2 run (bỏ trọng số lớp trong CE)
  --share-parent   trọng số đầu lá = trọng số loại cha + độ lệch (phạt L2)
  --save-repr      lưu attention từng đoạn + z (test) và z của một phần tập train
  --feats all      đặc trưng có cấu trúc (features.parquet, model.inputs): struct = giai đoạn/công cụ fail, diff = tóm tắt
                   diff, all = cả hai, none = bỏ (ablation A1/A6)
  --chunks tail    đọc 8 đoạn cuối log như trước 27/10 (ablation A2); mặc định `error` = khối log quanh chỗ fail
  --flat           chỉ một đầu phân loại lá, không học tầng 1–2 (ablation A3); tầng 1–2 suy từ lá dự đoán
  --views 2        mỗi run hai góc nhìn (giữ ngẫu nhiên --view-keep đoạn, che độc lập); CE học cả hai, soft/hcl thêm
                   InfoNCE coi hai góc nhìn của cùng run là cặp dương
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
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from .data import fold_split, load_pack
from .inputs import focus_window
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
    feats: dict = None  # đặc trưng có cấu trúc đã chuẩn hoá, cùng dạng với tfidf
    clip: object = clip_chunk  # cắt đoạn trước khi mã hoá: focus_window (khối lỗi) | clip_chunk (cuối đoạn)

    def __post_init__(self):
        r = self.runs
        self.run_id = r.run_id.tolist()
        self.keys = r.key.fillna("").tolist()
        self.ctx = [ci_context(w, j, s)[:400] for w, j, s in
                    zip(r.workflow.fillna(""), r.failed_job_names.fillna(""), r.failed_steps.fillna(""))]
        self.leaf = r.leaf.values

    def inputs(self, rows, masked, drop=None):
        """Đầu vào của mạng cho các run `rows` (masked[k]: che bằng chứng run thứ k).
        drop = (rng, tỉ lệ giữ): bỏ ngẫu nhiên đoạn khi tạo góc nhìn (--views 2); mỗi job giữ ít nhất đoạn cuối.
        Trả về (texts, c2j, j2r, pos), pos[i] = (run trong batch, job, đoạn) của đoạn i."""
        texts, c2j, j2r, pos = [], [], [], []
        for k, (r, mk) in enumerate(zip(rows, masked)):
            for ji, job in enumerate(self.chunks[self.run_id[r]]):
                idx = range(len(job))
                if drop is not None and len(job) > 1:
                    idx = [ci for ci in idx if drop[0].random() < drop[1]] or [len(job) - 1]
                parts = [(ci, self.clip(mask_text(job[ci], self.keys[r]) if mk else job[ci])) for ci in idx]
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


def load_feats(path: Path, runs: pd.DataFrame, which: str, tr: np.ndarray) -> dict:
    """Đặc trưng có cấu trúc theo thứ tự runs, chuẩn hoá theo trung bình / độ lệch của tập train.
    which: struct | diff | all. Bản che dùng struct tính trên log đã che (diff không phụ thuộc che)."""
    f = pd.read_parquet(path).drop_duplicates("run_id").set_index("run_id").reindex(runs.run_id)
    assert not f["diff"].isna().any(), "thiếu đặc trưng cho một số run"
    out = {}
    for m, col in ((False, "struct_full"), (True, "struct_masked")):
        parts = ([np.stack(f[col].values)] if which in ("struct", "all") else []) +                 ([np.stack(f["diff"].values)] if which in ("diff", "all") else [])
        out[m] = np.concatenate(parts, 1).astype(np.float32)
    mu, sd = out[False][tr].mean(0), out[False][tr].std(0) + 1e-6
    return {m: ((x - mu) / sd).astype(np.float32) for m, x in out.items()}


def run_variant(fold: Fold, variant: str, seed: int, a, out_preds: list) -> dict:
    import torch
    import torch.nn.functional as F
    from .nn.losses import MemoryBank, class_weights, hcl_loss, instance_nce, proxy_loss, soft_supcon_mem
    from .nn.net import LogNet, decode
    from .nn.samplers import MPCSampler, random_batches

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    tree, runs, tr, va, te = fold.tree, fold.runs, fold.tr, fold.va, fold.te
    l2 = [tree.tier2(l) for l in runs.leaf]  # tầng 2 suy từ lá theo cây (không dùng label_l2 của quy tắc)
    y1 = torch.tensor([tree.l1.index(tree.group[l]) for l in l2], device=dev)
    y2 = torch.tensor([tree.l2.index(l) for l in l2], device=dev)
    y3 = torch.tensor([tree.l3.index(l) if l in tree.l3 else -1 for l in runs.leaf], device=dev)
    w1, w2, w3 = (class_weights(y, tr, len(L)) for y, L in ((y1, tree.l1), (y2, tree.l2), (y3, tree.l3)))
    if a.sampler == "mpc":  # sampler đã cân bằng lớp, không bù thêm bằng trọng số
        w1, w2, w3 = None, None, None

    net = LogNet(tree, dev, freeze_layers=a.freeze_layers, tfidf_dim=fold.tfidf[False].shape[1] if fold.tfidf else 0,
                 share_parent=a.share_parent, proxy=variant == "proxy",
                 feat_dim=fold.feats[False].shape[1] if fold.feats else 0).to(dev)
    enc_params = [p for p in net.enc.parameters() if p.requires_grad]
    head_params = [p for n, p in net.named_parameters() if not n.startswith("enc.")]
    opt = torch.optim.AdamW([{"params": enc_params, "lr": a.lr_enc}, {"params": head_params, "lr": 1e-3}],
                            weight_decay=0.01)
    scaler = torch.amp.GradScaler(enabled=dev == "cuda")
    autocast = lambda: torch.autocast(dev, dtype=torch.float16, enabled=dev == "cuda")

    def forward(rows, masked, keep=False, drop=None):
        texts, c2j, j2r, pos = fold.inputs(rows, masked, drop)
        tf = np.stack([fold.tfidf[bool(m)][x] for x, m in zip(rows, masked)]) if fold.tfidf else None
        ft = np.stack([fold.feats[bool(m)][x] for x, m in zip(rows, masked)]) if fold.feats else None
        out = net(texts, c2j, j2r, len(rows), [fold.ctx[x] for x in rows], tf, max_tokens=a.max_tokens, keep=keep, ft=ft)
        return out, pos

    def predict(rows, masked, keep=False):
        """-> (lá dự đoán, log xác suất 3 tầng, attention từng đoạn (JSON) hoặc None, z hoặc None)."""
        net.eval()
        preds, lps, attn, zs = [], [], [], []
        with torch.no_grad(), autocast():
            for i in range(0, len(rows), a.eval_batch):
                b = rows[i:i + a.eval_batch]
                (o1, o2, o3, _, extra), pos = forward(b, [masked] * len(b), keep)
                p, lp = decode(o1, o2, o3, tree, flat=a.flat)
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
                else soft_supcon_mem(feat, lab, mfeat, mlab, C.TAU, sib_w, hard, C.HARD_W))
        memory.push(feat, lab)
        return loss

    sampler = MPCSampler(tr, fold.leaf) if a.sampler == "mpc" else None
    memory = MemoryBank(a.memory, 64, 3, dev)
    sib_w = (torch.tensor([C.SIB_W_BY_L2.get(c, C.SIB_W) for c in tree.l2], device=dev) if a.sib_by_parent else C.SIB_W)
    hard = None
    if a.hard_neg:
        hard = torch.zeros(len(tree.l3), len(tree.l3), dtype=torch.bool, device=dev)
        for x, y in C.HARD_PAIRS:
            if x in tree.l3 and y in tree.l3:
                hard[tree.l3.index(x), tree.l3.index(y)] = hard[tree.l3.index(y), tree.l3.index(x)] = True
    best, best_state, t0, step = -1.0, None, time.time(), 0
    va_eval = va[: a.val_max]
    for ep in range(a.epochs):
        net.train()
        for b in (sampler(rng, a.batch) if sampler else random_batches(rng, tr, a.batch)):
            b = list(b) * a.views  # --views 2: mỗi run hai góc nhìn (đoạn giữ ngẫu nhiên + che độc lập), CE học cả hai
            mk = (rng.random(len(b)) < a.mask_p).tolist()
            with autocast():
                (o1, o2, o3, feat, _), _ = forward(b, mk, drop=(rng, a.view_keep) if a.views > 1 else None)
            bt = torch.tensor(b, device=dev)
            loss = F.cross_entropy(o3.float(), y3[bt], weight=w3, ignore_index=-1)
            if not a.flat:
                loss = loss + F.cross_entropy(o1.float(), y1[bt], weight=w1) + F.cross_entropy(o2.float(), y2[bt], weight=w2)
            if a.share_parent:
                loss = loss + C.SHARE_L2 * net.h3.weight.float().pow(2).sum()
            if variant != "ce":
                loss = loss + C.LAMBDA * contrastive(feat, bt, step)
                if a.views > 1:  # cặp dương = hai góc nhìn của cùng run (thông tin CE không có)
                    loss = loss + C.LAMBDA * C.INST_W * instance_nce(feat.float(), a.views, C.TAU)
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
    runs, chunks, tree = load_pack(a.data, "chunks_tail.parquet" if a.chunks == "tail" else "chunks.parquet")
    if a.smoke:
        idx = np.concatenate([np.random.default_rng(0).permutation(np.where(runs.repo_fold.values == k)[0])[:60]
                              for k in range(C.N_FOLDS)])
        runs = runs.iloc[np.sort(idx)].reset_index(drop=True)
    tr, va, te = fold_split(runs.repo_fold.values, a.fold)
    va = np.random.default_rng(0).permutation(va)
    tfidf = load_tfidf((a.tfidf_dir or a.data) / f"tfidf_fold{a.fold}.parquet", runs) if a.tfidf else None
    feats = load_feats(a.data / "features.parquet", runs, a.feats, tr) if a.feats != "none" else None
    fold = Fold(runs, chunks, tree, tr, va, te, tfidf, feats, partial(focus_window, n=a.window) if a.chunks == "error" else clip_chunk)
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
    ap.add_argument("--feats", choices=["all", "struct", "diff", "none"], default="all",
                    help="đặc trưng có cấu trúc: giai đoạn/công cụ fail (struct), tóm tắt diff (diff)")
    ap.add_argument("--chunks", choices=["error", "tail"], default="error", help="khối log lỗi | 8 đoạn cuối log (cũ)")
    ap.add_argument("--window", type=int, default=1600, help="số ký tự cửa sổ quanh dòng lỗi (--chunks error); "
                    "dùng với --max-tokens 512")
    ap.add_argument("--flat", action="store_true", help="chỉ đầu lá (ablation bỏ phân cấp)")
    ap.add_argument("--sampler", choices=["random", "mpc"], default="random", help="mpc: batch = lá x 2 run")
    ap.add_argument("--share-parent", action="store_true", help="trọng số lá = trọng số loại cha + độ lệch")
    ap.add_argument("--views", type=int, default=1, choices=[1, 2], help="2: mỗi run hai góc nhìn; soft/hcl thêm InfoNCE theo run")
    ap.add_argument("--view-keep", type=float, default=0.75, help="tỉ lệ giữ mỗi đoạn khi tạo góc nhìn")
    ap.add_argument("--memory", type=int, default=512, help="kích thước bộ nhớ đặc trưng của loss so sánh")
    ap.add_argument("--sib-by-parent", action="store_true", help="trọng số anh em theo nhánh (config.SIB_W_BY_L2)")
    ap.add_argument("--hard-neg", action="store_true", help="phạt mạnh cặp lá dễ nhầm (config.HARD_PAIRS)")
    ap.add_argument("--save-repr", action="store_true", help="lưu attention từng đoạn + z (test) và z của tập train")
    ap.add_argument("--repr-train", type=int, default=10000, help="số run train lưu z")
    ap.add_argument("--tfidf-dir", type=Path, default=None, help="thư mục tfidf_fold{k}.parquet (mặc định --data)")
    ap.add_argument("--out", default="results.json")
    return ap


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(parser().parse_args())
