"""Quyết định trên run quy tắc để `?` (01/11/2026): lọc non_build bằng quy tắc, rồi mô hình chỉ trả lời khi đủ tự tin.

1. non_build: run fail ở bước thủ tục PR/release (changelog, tiêu đề PR, milestone, Jira, squash, kích thước PR…) không
   phải lỗi build -> không đưa vào mô hình. Quy tắc chỉ xét tên job và step (tên workflow có thể là tiêu đề PR).
2. Không chắc: độ tự tin = xác suất của lá được chọn (đầu tầng 3). Mục tiêu đặt trước: câu trả lời phải đáng tin ít nhất
   ngang bộ quy tắc dùng làm nhãn — precision mức lá đo ở vòng gán mù 27/10 là 0,857 (trọng số theo phân bố thật).
   Ngưỡng = mức thấp nhất mà độ chính xác trên các run được trả lời đạt mục tiêu. Log đã che của run có quy tắc không
   dùng để chọn ngưỡng được (mô hình tự tin quá mức trên run `?`), nên ngưỡng hiệu chỉnh trên nhãn người của run `?`
   bằng kiểm định chéo theo repo: chọn trên 4/5 repo, chấm trên 1/5 còn lại, lặp nhiều lần.

    python -m project3.model.abstain     # in kết quả trên 120 run người gán, ghi data/results/abstain/summary.json
"""
import glob
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .labels import LabelTree

TARGET = 0.857  # precision lá của bộ quy tắc, vòng gán mù 27/10/2026 (data/human_labels/leaf_review_blind)
TARGET_RAW = 0.744  # cùng vòng, không trọng số — mục tiêu thấp hơn, báo kèm để thấy ngưỡng nhạy thế nào
MIN_ANSWERED = 5  # cần ít nhất chừng này run được trả lời khi chọn ngưỡng, tránh ngưỡng chỉ dựa vào 1–2 run
NON_BUILD = {  # tên -> regex trên "job | step" (chữ thường)
    "changelog": r"changelog|logchange",
    "tiêu đề PR / commit": r"semantic[- ]?(pull[- ]?request|commit)|\bpr[- ]title|pull[- ]request[- ]title|conventional[- ]commit"
                           r"|commit[- ]messages?|fixup|sign[- ]?off|\bdco\b",
    "milestone / nhãn PR": r"milestone|\blabels?\b",
    "Jira / ticket": r"\bjira\b|\blinear\b ticket",
    "thủ tục PR khác": r"squash|pr[- ]checklist|pr quality|size of the pull request|pull[- ]request[- ]size|\bpr[- ]size"
                       r"|mergeable|metadata review",
    "release notes": r"release[- ]notes?",
}
# step chỉ tổng hợp kết quả các job khác (không tự gây lỗi)
AGGREGATE = r"check results|fail if|failure status|check all|summary|final[- ]status|required[- ]status|build-success|run exit 1"
TOP = {"git", "androidsdk", "infra", "network", "crash"}  # lá thuộc Môi trường CI
DATA, UNK = Path("data/kaggle_log_ds"), Path("data/kaggle_unknown_ds")
REVIEW = Path("data/human_labels/unknown_review")
OUT = Path("data/results/abstain")


def _rule(s: str) -> str:
    return next((k for k, p in NON_BUILD.items() if re.search(p, s)), "")


def non_build(job: str, step: str, n_jobs: int = 1) -> str:
    """Tên quy tắc non_build, hoặc '' nếu không khớp. Run fail 1 job: xét tên job + step. Run fail nhiều job: mọi step
    fail phải là step thủ tục hoặc step tổng hợp (vd. check-commit-messages fail cùng job test thật -> vẫn là lỗi build)."""
    job, step = (job or "").lower(), (step or "").lower()
    if n_jobs <= 1:
        return _rule(f"{job} | {step}")
    steps = [s for s in step.split(" | ") if s]
    hits = [_rule(s) for s in steps]
    if steps and all(h or re.search(AGGREGATE, s) for h, s in zip(hits, steps)):
        return next((h for h in hits if h), "")
    return ""


def confidence(df: pd.DataFrame, tree: LabelTree) -> np.ndarray:
    """Xác suất của lá được chọn theo đầu tầng 3 (softmax trên log xác suất đã lưu)."""
    n = len(tree.l1) + len(tree.l2)
    lp = np.stack(df.logp.to_numpy()).astype(np.float64)[:, n:]
    p = np.exp(lp - lp.max(1, keepdims=True))
    p /= p.sum(1, keepdims=True)
    idx = {l: i for i, l in enumerate(tree.l3)}
    return p[np.arange(len(df)), df.pred.map(idx).to_numpy()]


def pick(conf: np.ndarray, ok: np.ndarray, target: float) -> float:
    """Ngưỡng thấp nhất mà độ chính xác trên các run có độ tự tin >= ngưỡng đạt target (với >= MIN_ANSWERED run)."""
    for t in np.unique(conf):
        m = conf >= t
        if m.sum() < MIN_ANSWERED:
            break
        if ok[m].mean() >= target:
            return float(t)
    return float("inf")  # không đạt: không trả lời run nào


def cross_val(d: pd.DataFrame, target: float, reps: int = 200, k: int = 5, seed: int = 0) -> dict:
    """Kiểm định chéo theo repo trên các run rõ nhãn: chọn ngưỡng trên k-1 phần, chấm phần còn lại."""
    rng = np.random.default_rng(seed)
    repos = d.repo.unique()
    ans, ok, ok1, th = [], [], [], []
    for _ in range(reps):
        part = dict(zip(rng.permutation(repos), np.arange(len(repos)) % k))
        f = d.repo.map(part).to_numpy()
        for i in range(k):
            tr, te = d[f != i], d[f == i]
            t = pick(tr.conf.to_numpy(), tr.ok.to_numpy(), target)
            th.append(t)
            m = te.conf.to_numpy() >= t
            ans.append(m.sum()); ok.append(te.ok.to_numpy()[m].sum()); ok1.append(te.ok1.to_numpy()[m].sum())
    n = len(d) * reps
    a = sum(ans)
    th = np.array(th)
    return dict(target=target, coverage=a / n, acc=sum(ok) / max(a, 1), acc_t1=sum(ok1) / max(a, 1),
                thr_median=float(np.median(th[np.isfinite(th)])) if np.isfinite(th).any() else None,
                no_answer_share=float(np.mean(~np.isfinite(th))))


def main() -> None:
    tree = LabelTree.load(DATA / "label_tree.json")
    items = {json.loads(l)["stt"]: json.loads(l) for l in (REVIEW / "items.jsonl").open(encoding="utf-8")}
    items = {k: v for k, v in items.items() if v.get("round", 1) == 1}  # vòng 2 (02/11) chấm riêng khi gán xong
    blind, rev = {}, {}
    for l in (REVIEW / "labels.jsonl").open(encoding="utf-8"):
        r = json.loads(l)
        if r["stt"] not in items:
            continue
        if "rà lại" not in (r.get("note") or ""):
            blind[r["stt"]] = r["leaf"]
        rev[r["stt"]] = r["leaf"]
    up = pd.concat([pd.read_parquet(f, columns=["run_id", "pred", "logp"]) for f in
                    glob.glob("data/results/unknown/*/C_s0_fold*.unknown.parquet")]).drop_duplicates("run_id").reset_index(drop=True)
    up["conf"] = confidence(up, tree)
    meta = pd.read_parquet(UNK / "runs.parquet").drop_duplicates("run_id").set_index("run_id")
    m = meta.reindex(up.run_id)
    up["nb"] = [non_build(j, s, n) for j, s, n in zip(m.failed_job_names, m.failed_steps, m.failed_jobs.fillna(1))]
    up = up.set_index("run_id")
    lab = pd.read_parquet(DATA / "runs.parquet").drop_duplicates("run_id")
    lab_nb = [non_build(j, s, n) for j, s, n in zip(lab.failed_job_names, lab.failed_steps, lab.failed_jobs.fillna(1))]
    res = {"target": TARGET, "non_build_rules": NON_BUILD,
           "non_build_on_rule_labelled": {"n": len(lab), "fired": int(sum(map(bool, lab_nb))),
                                          "leaf_of_fired": lab.leaf[[bool(x) for x in lab_nb]].value_counts().to_dict()},
           "non_build_on_all_unknown": {"n": len(up), "fired": int((up.nb != "").sum()),
                                        "by_rule": up.nb[up.nb != ""].value_counts().to_dict()}}
    for name, h in [("gán mù", blind), ("sau rà lại", rev)]:
        d = pd.DataFrame([dict(stt=s, run_id=items[s]["run_id"], repo=items[s]["repo"], human=h[s]) for s in h]).join(up, on="run_id")
        hnb = d.human == "non_build"
        fired = d.nb != ""
        clear = d[~d.human.isin(["unclear", "non_build"]) & ~fired].copy()
        clear["ok"] = clear.pred == clear.human
        clear["ok1"] = clear.pred.isin(TOP) == clear.human.isin(TOP)
        r = {"non_build": dict(human=int(hnb.sum()), fired=int(fired.sum()), both=int((hnb & fired).sum()),
                               fired_but_human=d[fired & ~hnb].human.value_counts().to_dict(),
                               missed=d[hnb & ~fired][["stt"]].stt.tolist()),
             "clear_after_filter": len(clear), "no_abstain": dict(acc=clear.ok.mean(), acc_t1=clear.ok1.mean())}
        r["cv"] = [cross_val(clear, t) for t in (TARGET, TARGET_RAW)]
        t_all = pick(clear.conf.to_numpy(), clear.ok.to_numpy(), TARGET)
        r["thr_all"] = t_all  # ngưỡng chọn trên cả 120 run — dùng cho triển khai, KHÔNG dùng để báo độ chính xác
        rest = d[~fired]
        r["unclear_abstained_at_thr"] = float((rest[rest.human == "unclear"].conf < t_all).mean())
        curve = []
        for q in (1.0, 0.75, 0.5, 0.3):
            t = clear.conf.quantile(1 - q) if q < 1 else -1
            s = clear[clear.conf >= t]
            curve.append(dict(keep=q, thr=max(float(t), 0.0), n=len(s), acc=s.ok.mean(), acc_t1=s.ok1.mean()))
        r["curve"] = curve
        res[name] = r
    res["unknown_answered_at_thr"] = {k: float(((up.nb == "") & (up.conf >= res[k]["thr_all"])).mean()) for k in ("gán mù", "sau rà lại")}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1, default=lambda x: round(float(x), 3)))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
