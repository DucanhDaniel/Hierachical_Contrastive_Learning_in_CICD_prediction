"""MC Dropout (Gal & Ghahramani 2016, như AdaptiveLog) so với xác suất softmax làm độ tự tin của mô hình HCL bản cuối
(weight C seed 0, 20 lần đoán khi bật dropout). Chỉ đọc file dự đoán, không tải mô hình (02/11/2026).

Câu hỏi: đo độ tự tin bằng MC Dropout có tách câu đúng / câu sai tốt hơn softmax không, trên
  - 500 run test có nhãn quy tắc mỗi fold (log đủ + log đã che), nhãn = quy tắc;
  - 120 run `?` người gán (gán mù và sau rà lại), bỏ run unclear / non_build và run bị bộ lọc non_build bắt.
Chỉ số: AUROC tách đúng/sai (bootstrap theo repo), AURC (diện tích dưới đường rủi ro–độ phủ, thấp = tốt), ECE,
AUROC phát hiện run unclear / non_build, ngưỡng theo cùng giao thức abstain (mục tiêu 0,857, kiểm định chéo theo repo),
độ nhạy theo số lần T (5/10/20, lấy từ các lần đã lưu).

    python scripts/analysis/mc_dropout.py      # -> data/results/mc/summary.json
"""
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from project3.model.abstain import DATA, REVIEW, TARGET, TOP, UNK, confidence, cross_val, non_build
from project3.model.labels import LabelTree

MC = Path("data/results/mc")
# điểm độ tự tin -> (cột, dự đoán đi kèm); điểm càng cao càng tự tin
SCORES = {"softmax (hiện tại)": ("conf", "pred"), "MC đồng thuận": ("mc_agree", "mc_pred"),
          "MC xác suất TB": ("mc_pmean", "mc_pred"), "MC −entropy": ("neg_ent", "mc_pred"), "MC −MI": ("neg_mi", "mc_pred")}


def load(tree: LabelTree) -> pd.DataFrame:
    parts = []
    for f in sorted(glob.glob(str(MC / "MC_fold*.mc_soft0.parquet"))):
        k = int(Path(f).name.split("fold")[1][0])
        mc = pd.read_parquet(f).assign(fold=k)
        det = pd.concat([pd.read_parquet(MC / f"MC_fold{k}.preds.parquet"), pd.read_parquet(MC / f"MC_fold{k}.unknown.parquet")
                         .assign(test="unknown")])
        det = det[det.variant == "soft"].drop_duplicates(["test", "run_id"])
        det["conf"] = confidence(det, tree)
        parts.append(mc.merge(det[["test", "run_id", "pred", "logp", "conf"]], on=["test", "run_id"], how="left"))
    d = pd.concat(parts, ignore_index=True)
    assert d.pred.notna().all()
    d["neg_ent"], d["neg_mi"] = -d.mc_entropy, -d.mc_mi
    return d


def aurc(score: np.ndarray, ok: np.ndarray) -> float:
    """Rủi ro TB khi trả lời lần lượt từ run tự tin nhất (Geifman & El-Yaniv 2017)."""
    o = ok[np.argsort(-score, kind="stable")]
    return float(np.mean(1 - np.cumsum(o) / np.arange(1, len(o) + 1)))


def ece(p: np.ndarray, ok: np.ndarray, bins: int = 10) -> float:
    b = np.minimum((p * bins).astype(int), bins - 1)
    return float(sum(abs(ok[b == i].mean() - p[b == i].mean()) * (b == i).mean() for i in range(bins) if (b == i).any()))


def auroc_boot(d: pd.DataFrame, cols: dict, n: int = 1000, seed: int = 0) -> dict:
    """AUROC tách đúng/sai của từng điểm + chênh so với softmax, khoảng tin cậy 95% bootstrap theo repo."""
    rng = np.random.default_rng(seed)
    g = {r: np.flatnonzero(d.repo.values == r) for r in d.repo.unique()}
    reps = list(g)
    def au(idx):
        out = {}
        for name, (s, p) in cols.items():
            ok = d[f"ok_{p}"].values[idx]
            out[name] = roc_auc_score(ok, d[s].values[idx]) if 0 < ok.sum() < len(ok) else np.nan
        return out
    base = au(np.arange(len(d)))
    bs = []
    for _ in range(n):
        idx = np.concatenate([g[r] for r in rng.choice(reps, len(reps))])
        bs.append(au(idx))
    bs = pd.DataFrame(bs)
    ref = "softmax (hiện tại)"
    res = {}
    for name in cols:
        diff = (bs[name] - bs[ref]).dropna()
        res[name] = dict(auroc=base[name], ci=[float(bs[name].quantile(.025)), float(bs[name].quantile(.975))],
                         diff_vs_softmax=base[name] - base[ref],
                         diff_ci=[float(diff.quantile(.025)), float(diff.quantile(.975))] if name != ref else None)
    return res


def block(d: pd.DataFrame, gold: str) -> dict:
    """Mọi chỉ số trên một tập run, nhãn ở cột gold."""
    d = d.copy()
    for p in ("pred", "mc_pred"):
        d[f"ok_{p}"] = (d[p] == d[gold]).astype(int)
        d[f"ok1_{p}"] = (d[p].isin(TOP) == d[gold].isin(TOP)).astype(int)
    r = {"n": len(d), "acc_lá": dict(softmax=d.ok_pred.mean(), mc_bầu=d.ok_mc_pred.mean()),
         "khác_dự_đoán": float((d.pred != d.mc_pred).mean()),
         "auroc": auroc_boot(d, SCORES),
         "aurc": {k: aurc(d[s].values, d[f"ok_{p}"].values) for k, (s, p) in SCORES.items()},
         "aurc_tối_ưu": aurc(d.ok_pred.values.astype(float), d.ok_pred.values),
         "ece": {"softmax": ece(d.conf.values, d.ok_pred.values), "MC xác suất TB": ece(d.mc_pmean.values, d.ok_mc_pred.values)}}
    cv = {}
    for k, (s, p) in SCORES.items():
        x = d.assign(conf=d[s], ok=d[f"ok_{p}"].astype(bool), ok1=d[f"ok1_{p}"].astype(bool))
        cv[k] = cross_val(x[["repo", "conf", "ok", "ok1"]], TARGET)
    r["ngưỡng_cv"] = cv
    return r


def t_sens(d: pd.DataFrame, gold: str, tree: LabelTree) -> dict:
    """AUROC của đồng thuận / xác suất TB khi chỉ dùng T lần đầu."""
    L = len(tree.l3)
    out = {}
    for T in (5, 10, 20):
        agree, pm, ok = [], [], []
        for seq, pr, g in zip(d.mc_seq, d.mc_probs, d[gold]):
            v = pd.Series(json.loads(seq)[:T]).value_counts()
            agree.append(v.iloc[0] / T)
            mean = np.asarray(pr, dtype=np.float64).reshape(-1, L)[:T].mean(0)
            pm.append(mean[tree.l3.index(v.index[0])] if v.index[0] in tree.l3 else 0.0)
            ok.append(v.index[0] == g)
        ok = np.array(ok)
        out[T] = dict(acc=ok.mean(), auroc_agree=roc_auc_score(ok, agree), auroc_pmean=roc_auc_score(ok, pm))
    return out


def main() -> None:
    tree = LabelTree.load(DATA / "label_tree.json")
    d = load(tree)
    runs = pd.read_parquet(DATA / "runs.parquet").drop_duplicates("run_id").set_index("run_id")
    res = {"passes": int(d.passes.iloc[0]), "n": d.test.value_counts().to_dict()}
    for t in ("full", "masked"):
        x = d[d.test == t].copy()
        x["repo"], x["gold"] = runs.repository.reindex(x.run_id).values, runs.leaf.reindex(x.run_id).values
        res[f"quy tắc, log {'đủ' if t == 'full' else 'đã che'}"] = block(x, "gold")
        res[f"quy tắc, log {'đủ' if t == 'full' else 'đã che'}"]["T"] = t_sens(x, "gold", tree)
    # 120 run `?` người gán
    items = {json.loads(l)["stt"]: json.loads(l) for l in (REVIEW / "items.jsonl").open(encoding="utf-8")}
    items = {k: v for k, v in items.items() if v.get("round", 1) == 1}  # MC chỉ chạy trên 120 run vòng 1 (mc_ids.json)
    blind, rev = {}, {}
    for l in (REVIEW / "labels.jsonl").open(encoding="utf-8"):
        r = json.loads(l)
        if r["stt"] not in items:
            continue
        if "rà lại" not in (r.get("note") or ""):
            blind[r["stt"]] = r["leaf"]
        rev[r["stt"]] = r["leaf"]
    meta = pd.read_parquet(UNK / "runs.parquet").drop_duplicates("run_id").set_index("run_id")
    u = d[d.test == "unknown"].set_index("run_id")
    for name, h in [("run ?, gán mù", blind), ("run ?, sau rà lại", rev)]:
        x = pd.DataFrame([dict(run_id=items[s]["run_id"], repo=items[s]["repo"], human=h[s]) for s in h]).join(u, on="run_id")
        assert x.pred.notna().all()
        m = meta.reindex(x.run_id)
        x["nb"] = [non_build(j, s, n) for j, s, n in zip(m.failed_job_names, m.failed_steps, m.failed_jobs.fillna(1))]
        rest = x[x.nb == ""]
        det = {}  # phát hiện run unclear (trong các run bộ lọc không bắt) và non_build (trên cả 120): điểm thấp = nghi
        for lab, xs in (("unclear", rest), ("non_build", x)):
            y = (xs.human == lab).astype(int)
            det[lab] = {k: roc_auc_score(y, -xs[s]) for k, (s, _) in SCORES.items()} if 0 < y.sum() < len(y) else None
        clear = rest[~rest.human.isin(["unclear", "non_build"])]
        res[name] = block(clear, "human")
        res[name]["T"] = t_sens(clear, "human", tree)
        res[name]["phát_hiện"] = det
    (MC / "summary.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    for k, r in res.items():
        if not isinstance(r, dict) or "auroc" not in r:
            continue
        print(f"\n== {k}: {r['n']} run | acc lá softmax {r['acc_lá']['softmax']:.3f}, MC bầu {r['acc_lá']['mc_bầu']:.3f}"
              f" | khác dự đoán {r['khác_dự_đoán']:.1%} | ECE softmax {r['ece']['softmax']:.3f}, MC {r['ece']['MC xác suất TB']:.3f}")
        for s in SCORES:
            a, cv = r["auroc"][s], r["ngưỡng_cv"][s]
            dc = f" chênh {a['diff_vs_softmax']:+.3f} [{a['diff_ci'][0]:+.3f}, {a['diff_ci'][1]:+.3f}]" if a["diff_ci"] else ""
            print(f"  {s:20s} AUROC {a['auroc']:.3f} [{a['ci'][0]:.3f}, {a['ci'][1]:.3f}]{dc} | AURC {r['aurc'][s]:.3f}"
                  f" | cv: phủ {cv['coverage']:.0%} đúng {cv['acc']:.3f}")
        print("  T:", {t: {kk: round(v, 3) for kk, v in z.items()} for t, z in r["T"].items()})
        if "phát_hiện" in r:
            print("  phát hiện:", {lab: {s: round(v, 3) for s, v in z.items()} if z else None for lab, z in r["phát_hiện"].items()})


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
