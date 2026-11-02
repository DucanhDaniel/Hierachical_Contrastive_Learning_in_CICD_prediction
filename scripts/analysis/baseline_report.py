"""Số liệu cho báo cáo so sánh baseline và ablation của mô hình HCL bản cuối (cấu hình C).
Chỉ đọc file dự đoán (*.preds.parquet, ladder_preds_*.parquet, ...), không tải mô hình. Nhãn đúng = runs.parquet hiện tại.

    python scripts/analysis/baseline_report.py data/kaggle_log_ds   # -> data/results/report_c/numbers.json
"""
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import f1_score

from project3.model.labels import LabelTree
from project3.model.metrics import hier_scores
from project3.model.nn.net import decode

OUT = Path("data/results/report_c")
BASE = {  # tên hiển thị -> (file, tên model trong file)
    "B0 lớp đông nhất": ("data/results/doc/p3-baselines-cpu/ladder_preds_majority.parquet", None),
    "B0 tên workflow/job/step": ("data/results/doc/p3-baselines-cpu/ladder_preds_ctx.parquet", None),
    "B1 TF-IDF log": ("data/results/doc/p3-baselines-cpu/ladder_preds_tfidf.parquet", None),
    "B2 BERT 512 token cuối": ("data/results/ladder/bert/ladder_preds_bert.parquet", None),
    "TF-IDF + thông tin CI": ("data/results/doc/p3-input-check/ladder_preds_tfidf_struct.parquet", None),
    "TF-IDF + thông tin CI + diff": ("data/results/doc/p3-input-check/ladder_preds_tfidf_all.parquet", None),
}
C_FILES = "data/results/c/**/C_s*_fold*.preds.parquet|data/results/lines/*/C_fold*.preds.parquet"
ABL = {  # pilot fold 0 + 3, seed 1
    "v10 (cửa sổ neo dòng lỗi cuối)": "data/results/attn/*/results_fold*.preds.parquet",
    "A: + cửa sổ chia đôi": "data/results/lines/*/A_fold*.preds.parquet",
    "B: A + attention theo dòng": "data/results/lines/*/B_fold*.preds.parquet",
    "C: B + loss chỉ dòng lỗi (bản cuối)": "data/results/lines/*/C_fold*.preds.parquet",
}
TOP = {"git", "androidsdk", "infra", "network", "crash"}  # lá thuộc Môi trường CI


def fold_of(path) -> int:
    return int(Path(path).name.split("fold")[1][0])


def files(pat: str) -> list:
    return sorted({f for x in pat.split("|") for f in glob.glob(x, recursive=True)})


def model_preds(pat: str, tree) -> pd.DataFrame:
    """Dự đoán từng seed + gộp seed (trung bình log xác suất 3 tầng rồi giải mã theo cây)."""
    p = pd.concat([pd.read_parquet(f, columns=["seed", "test", "run_id", "pred", "logp"]).assign(fold=fold_of(f))
                   for f in files(pat)]).drop_duplicates(["seed", "test", "run_id"])
    n1, n2 = len(tree.l1), len(tree.l2)
    out = [p.drop(columns="logp").assign(seed=p.seed.astype(str))]
    for (fold, test), d in p.groupby(["fold", "test"]):
        piv = {s: g.set_index("run_id") for s, g in d.groupby("seed")}
        ids = sorted(set.intersection(*(set(g.index) for g in piv.values())))
        lp = np.mean([np.stack(g.loc[ids].logp.to_numpy()).astype(np.float32) for g in piv.values()], axis=0)
        pred, _ = decode(*(torch.from_numpy(x) for x in (lp[:, :n1], lp[:, n1:n1 + n2], lp[:, n1 + n2:])), tree)
        out.append(pd.DataFrame({"seed": "gộp", "test": test, "run_id": ids, "pred": pred, "fold": fold}))
    return pd.concat(out)


def scores(p: pd.DataFrame, gold: pd.Series, tree) -> pd.DataFrame:
    """macro-F1 3 tầng theo (seed, test, fold)."""
    rows = []
    for (seed, test, fold), d in p.groupby(["seed", "test", "fold"]):
        d = d[d.run_id.isin(gold.index)]
        s = hier_scores(gold.loc[d.run_id].tolist(), d.pred.tolist(), tree.parent, tree.group)
        rows.append(dict(seed=seed, test=test, fold=fold, n=len(d), leaf=s["macroF1_l3"], t2=s["macroF1_l2"],
                         t1=s["macroF1_l1"], acc=s["acc_l3"], **{f"F1_{k}": v for k, v in s["F1_l3"].items()}))
    return pd.DataFrame(rows)


def bootstrap(data: Path, gold: pd.Series, tree, cp: pd.DataFrame, base_file: str, n: int = 1000) -> dict:
    """Chênh macro-F1 (HCL gộp 2 seed − baseline) trên dự đoán test gộp 5 fold; bootstrap lấy lại theo repo."""
    repo = pd.read_parquet(data / "runs.parquet", columns=["run_id", "repository"]).drop_duplicates("run_id").set_index("run_id").repository
    b = pd.read_parquet(base_file)[["test", "run_id", "pred"]]
    out = {}
    for test in ("full", "masked"):
        h = cp[(cp.seed == "gộp") & (cp.test == test)].drop_duplicates("run_id").set_index("run_id").pred
        x = b[b.test == test].drop_duplicates("run_id").set_index("run_id").pred
        ids = h.index.intersection(x.index).intersection(gold.index)
        d = pd.DataFrame({"g": gold.loc[ids], "h": h.loc[ids], "b": x.loc[ids], "r": repo.loc[ids]})
        d["g2"], d["h2"], d["b2"] = (d[c].map(lambda v: tree.parent.get(v, v)) for c in ("g", "h", "b"))
        rcode, names = pd.factorize(d.r)
        rng = np.random.default_rng(0)
        w = np.stack([np.bincount(rng.integers(0, len(names), len(names)), minlength=len(names)) for _ in range(n)])
        res = {"n_repo": len(names), "n": len(d)}
        for k, g, hh, bb in [("leaf", "g", "h", "b"), ("t2", "g2", "h2", "b2")]:
            lab = sorted(set(d[g]))
            idx = {x: i for i, x in enumerate(lab)}
            gi = d[g].map(idx).to_numpy()
            # đếm TP / số dự đoán / số đúng theo (repo, nhãn); dự đoán ngoài tập nhãn đúng chỉ làm giảm precision lớp khác
            def counts(col):
                pi = d[col].map(idx).fillna(-1).astype(int).to_numpy()
                tp = np.zeros((len(names), len(lab))); pc = np.zeros_like(tp); tc = np.zeros_like(tp)
                np.add.at(tp, (rcode[gi == pi], gi[gi == pi]), 1)
                np.add.at(pc, (rcode[pi >= 0], pi[pi >= 0]), 1)
                np.add.at(tc, (rcode, gi), 1)
                return tp, pc, tc

            def macro(c, wt):
                tp, pc, tc = (wt @ x for x in c)
                return np.mean(np.where(pc + tc > 0, 2 * tp / np.maximum(pc + tc, 1), 0), axis=-1)
            ch, cb = counts(hh), counts(bb)
            one = np.ones((1, len(names)))
            delta = macro(ch, w) - macro(cb, w)
            res[k] = dict(delta=float((macro(ch, one) - macro(cb, one))[0]), lo=float(np.percentile(delta, 2.5)),
                          hi=float(np.percentile(delta, 97.5)), p_le0=float(np.mean(delta <= 0)))
        out[test] = res
    return out


def main(data: Path) -> None:
    tree = LabelTree.load(data / "label_tree.json")
    gold = pd.read_parquet(data / "runs.parquet", columns=["run_id", "leaf"]).drop_duplicates("run_id").set_index("run_id").leaf
    res = {}

    # 1. 5 fold chéo repo: baseline + C
    tabs = {}
    for name, (f, _) in BASE.items():
        p = pd.read_parquet(f)[["test", "fold", "run_id", "pred"]].assign(seed="-")
        tabs[name] = scores(p, gold, tree)
    cp = model_preds(C_FILES, tree)
    cs = scores(cp, gold, tree)
    for s, lab in [("0", "HCL bản cuối, seed 0"), ("1", "HCL bản cuối, seed 1"), ("gộp", "HCL bản cuối, gộp 2 seed")]:
        tabs[lab] = cs[cs.seed == s]
    tabs["HCL bản cuối, TB 2 seed"] = cs[cs.seed.isin(["0", "1"])].groupby(["test", "fold"]).mean(numeric_only=True).reset_index()
    main_rows, fold_rows = [], []
    for name, t in tabs.items():
        m = t.groupby("test")[["leaf", "t2", "t1"]].mean()
        sd = t.groupby("test").leaf.std()
        main_rows.append(dict(model=name, **{f"{c}_{k}": float(m.loc[k, c]) for k in ("full", "masked") for c in ("leaf", "t2", "t1")},
                              sd_full=float(sd.get("full", np.nan)), sd_masked=float(sd.get("masked", np.nan))))
        for r in t.itertuples():
            fold_rows.append(dict(model=name, test=r.test, fold=int(r.fold), leaf=r.leaf, t2=r.t2, t1=r.t1))
    res["main"] = main_rows
    res["folds"] = fold_rows
    leafcols = [c for c in cs.columns if c.startswith("F1_")]
    res["per_leaf"] = {name: {c[3:]: float(v) for c, v in t[t.test == "full"][leafcols].mean().items()} for name, t in tabs.items()
                       if name in ("B1 TF-IDF log", "TF-IDF + thông tin CI + diff", "B2 BERT 512 token cuối",
                                   "HCL bản cuối, gộp 2 seed", "HCL bản cuối, TB 2 seed")}
    res["leaf_count"] = gold.value_counts().to_dict()
    res["bootstrap"] = bootstrap(data, gold, tree, cp, BASE["TF-IDF + thông tin CI + diff"][0])

    # 2. Tập con 365 run của LLM (LogSage) và 190 run người gán
    llm = pd.read_parquet("data/results/llm_logsage/preds.parquet")
    pools = {"B1 TF-IDF log": BASE["B1 TF-IDF log"][0], "TF-IDF + thông tin CI + diff": BASE["TF-IDF + thông tin CI + diff"][0],
             "B2 BERT 512 token cuối": BASE["B2 BERT 512 token cuối"][0]}
    allp = {k: pd.read_parquet(f)[["test", "run_id", "pred"]] for k, f in pools.items()}
    allp["HCL bản cuối, gộp 2 seed"] = cp[cp.seed == "gộp"][["test", "run_id", "pred"]]
    sub = []
    for test, d in llm[llm.set == "model"].groupby("test"):
        d = d[d.run_id.isin(gold.index)]
        g = gold.loc[d.run_id]
        s = hier_scores(g.tolist(), d.pred.tolist(), tree.parent, tree.group)
        sub.append(dict(model="B3 LLM (LogSage)", test=test, n=len(d), leaf=s["macroF1_l3"], t2=s["macroF1_l2"], t1=s["macroF1_l1"]))
        for k, p in allp.items():
            q = p[p.test == test].drop_duplicates("run_id").set_index("run_id").pred.reindex(d.run_id)
            s = hier_scores(g.tolist(), q.fillna("?").tolist(), tree.parent, tree.group)
            sub.append(dict(model=k, test=test, n=int(q.notna().sum()), leaf=s["macroF1_l3"], t2=s["macroF1_l2"], t1=s["macroF1_l1"]))
    res["llm_subset"] = sub
    hum = llm[(llm.set == "human") & (llm.test == "full")].drop_duplicates("run_id")
    hum = hum[hum.run_id.isin(gold.index)]
    agree = {"Quy tắc (nhãn huấn luyện)": gold.loc[hum.run_id].to_numpy(), "B3 LLM (LogSage)": hum.pred.to_numpy()}
    for k, p in allp.items():
        agree[k] = p[p.test == "full"].drop_duplicates("run_id").set_index("run_id").pred.reindex(hum.run_id).to_numpy()
    hv = hum.gold_leaf.to_numpy()
    res["human_rule_runs"] = [dict(model=k, n=int(pd.notna(v).sum()), acc=float(np.mean(v[pd.notna(v)] == hv[pd.notna(v)])),
                                   acc_blind=float(np.mean((v == hv)[(hum["round"] == "human_blind").to_numpy() & pd.notna(v)])))
                              for k, v in agree.items()]
    res["human_rule_runs_n"] = {"all": len(hum), "blind": int((hum["round"] == "human_blind").sum())}

    # 3. 120 run quy tắc để `?` (người gán mù, rồi rà lại)
    items = {json.loads(l)["stt"]: json.loads(l) for l in open("data/human_labels/unknown_review/items.jsonl", encoding="utf-8")}
    items = {k: v for k, v in items.items() if v.get("round", 1) == 1}  # vòng 2 (02/11) chấm riêng khi gán xong
    recs = [r for r in map(json.loads, open("data/human_labels/unknown_review/labels.jsonl", encoding="utf-8")) if r["stt"] in items]
    blind, rev = {}, {}
    for r in recs:
        if "rà lại" not in (r.get("note") or ""):
            blind[r["stt"]] = r
        rev[r["stt"]] = r
    up = pd.concat([pd.read_parquet(f, columns=["run_id", "pred", "lines"]) for f in glob.glob("data/results/unknown/*/C_s0_fold*.unknown.parquet")])
    up = up.drop_duplicates("run_id").set_index("run_id")
    unk = {}
    for name, lab in [("gán mù", blind), ("sau rà lại", rev)]:
        rows = []
        for stt, r in lab.items():
            it = items[stt]
            ev = [it["lines"][k - 1].strip() for k in r["lines"] if 0 < k <= len(it["lines"])]
            pr = up.pred.get(it["run_id"])
            hit1 = hit3 = None
            if ev and it["run_id"] in up.index and up.lines.get(it["run_id"]):
                top = [t.strip() for *_, t in json.loads(up.lines[it["run_id"]])]
                hit = [any(t and (t[:120] in e or e[:120] in t) for e in ev) for t in top]
                hit1, hit3 = any(hit[:1]), any(hit[:3])
            rows.append(dict(human=r["leaf"], pred=pr, hit1=hit1, hit3=hit3))
        d = pd.DataFrame(rows)
        clear = d[~d.human.isin(["unclear", "non_build"])]
        env = lambda x: "moi_truong" if x in TOP else "du_an"
        par = lambda x: tree.parent.get(x, x)
        h = d.dropna(subset=["hit1"])
        unk[name] = dict(n=len(d), n_clear=len(clear), dist=d.human.value_counts().to_dict(),
                         acc_leaf=float((clear.pred == clear.human).mean()),
                         acc_t2=float((clear.pred.map(par) == clear.human.map(par)).mean()),
                         acc_t1=float((clear.pred.map(env) == clear.human.map(env)).mean()),
                         macro_leaf=float(f1_score(clear.human, clear.pred, labels=sorted(set(clear.human)), average="macro", zero_division=0)),
                         n_lines=len(h), top1=float(h.hit1.mean()), top3=float(h.hit3.mean()),
                         n_changed=sum(blind[k]["leaf"] != rev[k]["leaf"] or blind[k]["lines"] != rev[k]["lines"] for k in rev))
        # baseline trên cùng run: TF-IDF (kernel p3-unknown-baselines), LLM LogSage (llm_logsage --unknown)
        ub = pd.read_parquet("data/results/unknown_baselines/unknown120_preds.parquet")
        other = {m: g.set_index("run_id").pred for m, g in ub.groupby("model")}
        llm_p = Path("data/results/llm_logsage/unknown120/preds.parquet")
        if llm_p.exists():
            other["llm_logsage"] = pd.read_parquet(llm_p).set_index("run_id").pred
        ids = [items[k]["run_id"] for k in lab]
        hum = pd.Series([r["leaf"] for r in lab.values()], index=ids)
        hum = hum[~hum.isin(["unclear", "non_build"])]
        unk[name]["baselines"] = {}
        for m, pr in other.items():
            q = pr.reindex(hum.index).fillna("?")
            unk[name]["baselines"][m] = dict(
                n=int(pr.reindex(hum.index).notna().sum()), acc_leaf=float((q == hum).mean()),
                acc_t2=float((q.map(par) == hum.map(par)).mean()), acc_t1=float(((q.map(env) == hum.map(env)) & q.isin(tree.l3)).mean()),
                macro_leaf=float(f1_score(hum, q, labels=sorted(set(hum)), average="macro", zero_division=0)))
    res["unknown"] = unk
    res["unknown_pred_dist"] = (up.pred.value_counts(normalize=True)).to_dict() | {"_n": len(up)}

    # 4. Chỉ dòng lỗi trên run có quy tắc (5 fold) — từ line_check (scripts/colab/line_check.py)
    lc = pd.read_parquet("data/results/c/line_check_C_5fold.parquet")
    res["line_check_cols"] = lc.columns.tolist()

    # 5. Ablation pilot (fold 0 + 3, seed 1)
    abl = []
    for name, pat in ABL.items():
        p = pd.concat([pd.read_parquet(f, columns=["seed", "test", "run_id", "pred"]).assign(fold=fold_of(f)) for f in files(pat)])
        p = p[p.seed.astype(str) == "1"].assign(seed="1")
        s = scores(p, gold, tree)
        for r in s.itertuples():
            abl.append(dict(config=name, test=r.test, fold=int(r.fold), leaf=r.leaf, t2=r.t2, t1=r.t1))
    res["ablation"] = abl

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "numbers.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    pd.set_option("display.width", 200)
    print(pd.DataFrame(main_rows).set_index("model").round(3).to_string())
    print(pd.DataFrame(sub).pivot_table(index="model", columns="test", values=["leaf", "t2", "t1"]).round(3).to_string())
    print(pd.DataFrame(res["human_rule_runs"]).round(3).to_string(), res["human_rule_runs_n"])
    print(json.dumps(unk, ensure_ascii=False, indent=1))
    print(pd.DataFrame(abl).pivot_table(index="config", columns=["test", "fold"], values="leaf", sort=False).round(3).to_string())
    print(pd.DataFrame(abl).groupby(["config", "test"], sort=False)[["leaf", "t2", "t1"]].mean().round(3).unstack("test").to_string())
    print(json.dumps(res["bootstrap"], indent=1))
    print("->", OUT / "numbers.json")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(Path(sys.argv[1]))
