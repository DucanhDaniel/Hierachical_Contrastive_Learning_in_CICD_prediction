"""Demo (03/11/2026): phân loại một run GitHub Actions fail bằng mô hình đề xuất (weight seed 0 của 5 fold, đã lưu khi
đánh giá), xử lý đầu vào GIỐNG HỆT lúc tạo dữ liệu huấn luyện:

  crawl.gha (job fail: pick_jobs, 200 KB cuối log; error_context cho quy tắc)
  -> pipeline.run_dataset.chunk_log (đoạn theo step / goal / task)
  -> model.pack (chọn ≤ 8 đoạn theo dấu hiệu fail, giữ 6.000 ký tự cuối mỗi đoạn; đặc trưng giai đoạn/công cụ + diff)
  -> model.train (cửa sổ 1.600 ký tự chia đôi, chuẩn hoá đặc trưng theo tập train của fold, ngữ cảnh CI)

Kết quả: nhãn bộ quy tắc (để đối chiếu), bộ lọc non_build (model.abstain), nhãn 3 tầng + 5 dòng điểm cao nhất, MC Dropout
20 lần -> entropy; entropy <= ngưỡng thì trả lời, ngược lại báo "không chắc" (ngưỡng: scripts/analysis/mc_dropout.py).
Mô hình chạy trên GPU (Colab, app.py); ở máy local chỉ chạy phần lấy dữ liệu / tiền xử lý (check_preprocess).
"""
import json
import re
import time
from pathlib import Path

import numpy as np

from project3.crawl.gha import FULL_TAIL_BYTES, error_context, pick_jobs
from project3.crawl.gold_labels import AGG_JOB, NON_BUILD_WF, gold_label
from project3.crawl.build_log_labels import GROUP
from project3.crawl.fine_labels import PARENT as FINE_PARENT, subtype
from project3.crawl.stages import failed_tools
from project3.model.abstain import non_build
from project3.model.inputs import chunk_score, diff_features, file_kind, focus_window, select_chunks, struct_features
from project3.model.labels import LabelTree, leaf_of
from project3.model.pack import MAX_CHUNKS, MAX_CHUNK_CHARS
from project3.model.text import ci_context
from project3.pipeline.run_dataset import chunk_log

URL = re.compile(r"github\.com/([^/\s]+/[^/\s]+)/actions/runs/(\d+)")
MAX_JOBS = 2      # số job fail tải log mỗi run, như lúc crawl (--max-jobs-per-run 2)
MC_PASSES = 20    # bằng lần đo ngưỡng
WINDOW = 1600
NAMES = {  # tên hiển thị cho người ngoài (giống báo cáo)
    "du_an": "Dự án", "moi_truong": "Môi trường CI",
    "viet_code": "Khi viết code", "build_local": "Khi build ở máy trước khi push", "ci_merge": "Trên CI trước khi merge",
    "cau_hinh_ci": "Sửa cấu hình CI", "chay_lai": "Chạy lại",
    "compile": "Lỗi biên dịch", "quality": "Vi phạm kiểm tra code", "doc": "Lỗi tài liệu (javadoc)",
    "buildconfig": "Cấu hình build sai", "testfailure": "Unit test lỗi", "dependency": "Lỗi thư viện phụ thuộc",
    "license": "Lỗi license", "compatibility": "Không tương thích API", "itestfailure": "Test tích hợp lỗi",
    "flaky": "Test chập chờn", "git": "Lỗi git", "androidsdk": "Lỗi Android SDK / emulator",
    "infra": "Hạ tầng CI khác", "network": "Lỗi mạng", "crash": "Môi trường sập (hết bộ nhớ, hết giờ…)",
}
ACTION = {  # gợi ý hành động theo tầng 2
    "viet_code": "Sửa code / cấu hình build rồi push lại; nên bắt bằng IDE hoặc hook trước commit.",
    "build_local": "Chạy build đầy đủ ở máy (mvn verify / gradle check) để tái hiện rồi sửa.",
    "ci_merge": "Lỗi chỉ lộ trên CI (test tích hợp, emulator): xem log test trên CI để sửa.",
    "cau_hinh_ci": "Sửa file workflow / secrets / cấu hình runner, không cần sửa code.",
    "chay_lai": "Lỗi tạm thời của hạ tầng: thử chạy lại job.",
}


# ---------- lấy dữ liệu ----------

def fetch_run(url: str, gh) -> dict:
    """Run GitHub Actions -> bản ghi run: thông tin run, job fail (tên, step fail, log), thống kê diff."""
    m = URL.search(url)
    if not m:
        raise ValueError("Link phải có dạng https://github.com/<owner>/<repo>/actions/runs/<id>")
    repo, rid = m.group(1), int(m.group(2))
    run = gh.get(f"/repos/{repo}/actions/runs/{rid}")
    jobs, page = [], 1
    while True:
        r = gh.get(f"/repos/{repo}/actions/runs/{rid}/jobs", per_page=100, page=page)
        jobs += r["jobs"]
        if len(r["jobs"]) < 100:
            break
        page += 1
    jobs = [{"id": j["id"], "name": j["name"], "conclusion": j["conclusion"],
             "steps": [{"name": s["name"], "conclusion": s["conclusion"]} for s in j.get("steps") or []]} for j in jobs]
    for j in pick_jobs(jobs, MAX_JOBS):
        j["log"] = gh.get_log_tail(f"/repos/{repo}/actions/jobs/{j['id']}/logs")
    return {"repo": repo, "run_id": rid, "url": f"https://github.com/{repo}/actions/runs/{rid}", "workflow": run["name"],
            "event": run["event"], "head_sha": run["head_sha"], "conclusion": run["conclusion"],
            "created_at": run.get("created_at"), "jobs": jobs, "diff": diff_stats(gh, repo, run)}


def diff_stats(gh, repo: str, run: dict) -> dict:
    """Danh sách file + số dòng thêm/xoá của phần CI build: push = commit so với cha; PR = merge-base(nhánh gốc)..head
    (như pipeline.fetch_diffs). Lỗi (fork, commit đã mất) -> không có diff, như diff_ok = False lúc huấn luyện."""
    try:
        if run["event"] == "pull_request":
            base = gh.get(f"/repos/{repo}")["default_branch"]
            d = gh.get(f"/repos/{repo}/compare/{base}...{run['head_sha']}")
        else:
            d = gh.get(f"/repos/{repo}/commits/{run['head_sha']}")
        files = d.get("files") or []
        return {"files": [f["filename"] for f in files], "added": sum(f.get("additions", 0) for f in files),
                "deleted": sum(f.get("deletions", 0) for f in files)}
    except Exception as e:  # noqa: BLE001 — demo: thiếu diff không làm hỏng dự đoán
        return {"files": [], "added": 0, "deleted": 0, "error": str(e)[:200]}


def diff_vector(diff: dict, event: str) -> list:
    """Như inputs.diff_features nhưng từ thống kê API thay cho file .diff (cùng công thức)."""
    import math
    files = diff["files"]
    n = len(files)
    cnt = {}
    for p in files:
        cnt[file_kind(p)] = cnt.get(file_kind(p), 0) + 1
    from project3.model.inputs import DIFF_KINDS
    return ([cnt.get(k, 0) / n if n else 0.0 for k in DIFF_KINDS]
            + [math.log1p(n), math.log1p(diff["added"]), math.log1p(diff["deleted"]), float(n > 0),
               float(event == "pull_request")])


# ---------- tiền xử lý (giống pipeline.run_dataset + model.pack) ----------

def preprocess(rec: dict) -> dict:
    """Bản ghi run -> đầu vào mô hình + nhãn quy tắc. rec["jobs"][i]["log"]: log đã tải (None nếu không có)."""
    failed = [j for j in rec["jobs"] if j["conclusion"] == "failure" and not AGG_JOB.search(j["name"])]
    names = " ".join(j["name"] for j in failed)
    texts, tools, by_job, rule_texts = [], [], [], []
    for j in sorted(failed, key=lambda j: j["id"]):
        if not j.get("log"):
            continue
        tail = j["log"].encode("utf-8")[-FULL_TAIL_BYTES:].decode("utf-8", errors="ignore")
        rule_texts.append(j.get("rule_text") or error_context(j["log"]))  # rule_text: đoạn .txt đã lưu lúc crawl
        texts.append(tail)
        tools += failed_tools(tail)
        fsteps = " | ".join(s["name"] for s in j["steps"] if s["conclusion"] == "failure")[:300]
        cs = [dict(c, failed_steps=fsteps, job=j["name"]) for c in chunk_log(tail)]
        if cs:
            by_job.append(cs)
    # nhãn quy tắc (crawl.gold_labels + run_dataset: lá theo fine_labels.subtype)
    gold, ev = gold_label(rule_texts) if rule_texts else ("?", "")
    nb_wf = bool(NON_BUILD_WF.search(rec["workflow"] or "")) or gold == "non_build"
    leaf = None
    if gold in GROUP:
        test_stage = next((st for _, st in tools if st in ("test", "itest")), None)
        leaf = subtype(gold, ev, rec["workflow"] or "", names, "\n".join(texts), test_stage)
        if leaf in FINE_PARENT and FINE_PARENT[leaf] != gold:
            gold = FINE_PARENT[leaf]
    rule_leaf = leaf_of(leaf, gold) if gold in GROUP or leaf else None
    # chọn đoạn + đặc trưng (model.pack)
    scores = [[chunk_score(c["text"], ci == len(job) - 1) for ci, c in enumerate(job)] for job in by_job]
    picked = select_chunks(scores, MAX_CHUNKS)
    steps = list(dict.fromkeys(s for job in by_job for c in job for s in c["failed_steps"].split(" | ") if s))
    kinds = list({c["kind"] for job in by_job for c in job})
    struct = struct_features([c["text"] for job in by_job for c in job], steps, kinds, len(failed)) if by_job else None
    chunks, meta = [], []
    for j, c in picked:
        if not chunks or meta[-1][0] != j:
            chunks.append([])
        chunks[-1].append(by_job[j][c]["text"][-MAX_CHUNK_CHARS:])
        meta.append((j, by_job[j][c]["job"], by_job[j][c]["step"]))
    step_str = " | ".join(steps)[:300]
    return {"chunks": chunks, "chunk_meta": meta, "struct": struct,
            "diff": diff_vector(rec["diff"], rec["event"]) if "files" in rec["diff"] else rec["diff"]["vector"],
            "ctx": ci_context(rec["workflow"] or "", names[:500], step_str)[:400],
            "failed_jobs": [j["name"] for j in failed], "failed_steps": step_str,
            "rule": {"label_l2": gold, "leaf": rule_leaf, "evidence": ev},
            "non_build": non_build(names, step_str, len(failed)) or ("workflow không phải build" if nb_wf else "")}


# ---------- mô hình ----------

class Predictor:
    """Nạp cây nhãn, chuẩn hoá đặc trưng, weight 5 fold (lười). Repo có trong dữ liệu -> mô hình của fold mà repo nằm ở
    tập test (mô hình chưa thấy repo); repo mới -> DEFAULT_FOLD."""

    def __init__(self, bundle: Path, weights: str, device: str = None):
        import torch
        self.bundle = Path(bundle)
        self.tree = LabelTree.load(self.bundle / "label_tree.json")
        self.norm = json.loads((self.bundle / "norm.json").read_text())
        self.repo_fold = json.loads((self.bundle / "repo_fold.json").read_text())
        cfg = json.loads((self.bundle / "config.json").read_text())
        self.thr_entropy, self.default_fold = cfg["thr_entropy"], cfg["default_fold"]
        self.weights = weights  # mẫu đường dẫn có {fold}
        self.dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.nets = {}

    def net(self, fold: int):
        import torch
        from project3.model.nn.net import LogNet
        if fold not in self.nets:
            net = LogNet(self.tree, self.dev, freeze_layers=6, feat_dim=len(self.norm[str(fold)]["mu"]), line_attn=True)
            sd = torch.load(self.weights.format(fold=fold), map_location="cpu")
            miss = net.load_state_dict({k: v.float() if v.is_floating_point() else v for k, v in sd.items()}, strict=False)
            assert not miss.unexpected_keys, miss.unexpected_keys
            self.nets[fold] = net.to(self.dev).eval()
        return self.nets[fold]

    def predict(self, rec: dict, mc: int = MC_PASSES) -> dict:
        import torch
        from project3.model.nn.net import decode
        t0 = time.time()
        x = preprocess(rec)
        out = {k: rec[k] for k in ("repo", "run_id", "url", "workflow", "event", "created_at") if k in rec}
        out.update(failed_jobs=x["failed_jobs"], failed_steps=x["failed_steps"], rule=x["rule"], non_build=x["non_build"])
        if not x["chunks"]:
            return {**out, "error": "Không có log của job fail (log hết hạn sau 90 ngày, hoặc run không fail)."}
        fold = self.repo_fold.get(rec["repo"], self.default_fold)
        out["fold"], out["seen_repo"] = fold, rec["repo"] in self.repo_fold
        net, n = self.net(fold), self.norm[str(fold)]
        feat = (np.array(x["struct"] + x["diff"], dtype=np.float32) - np.array(n["mu"])) / np.array(n["sd"])
        texts, c2j, j2r = [], [], []
        for job in x["chunks"]:
            j2r.append(0)
            for t in job:
                texts.append(focus_window(t, WINDOW, "split"))
                c2j.append(len(j2r) - 1)
        args = (texts, c2j, j2r, 1, [x["ctx"]], None)
        kw = dict(max_tokens=512, keep=True, ft=feat[None].astype(np.float32))
        ac = lambda: torch.autocast(self.dev, dtype=torch.float16, enabled=self.dev == "cuda")
        with torch.no_grad(), ac():
            o1, o2, o3, _, extra = net(*args, **kw)
            pred, lp = decode(o1, o2, o3, self.tree)
            probs = []
            net.train()  # MC Dropout: chỉ bật dropout, không cập nhật weight (giống train.mc_predict)
            for _ in range(mc):
                a1, a2, a3, _, _ = net(*args, **kw)
                probs.append(np.exp(decode(a1, a2, a3, self.tree)[1][0, len(self.tree.l1) + len(self.tree.l2):]
                                    .astype(np.float32)))
            net.eval()
        leaf = pred[0]
        t1, t2 = self.tree.group[self.tree.tier2(leaf)], self.tree.tier2(leaf)
        sm = lambda v: np.exp(v - v.max()) / np.exp(v - v.max()).sum()
        n1, n2 = len(self.tree.l1), len(self.tree.l2)
        lp = lp[0].astype(np.float64)
        p = {"l1": sm(lp[:n1]), "l2": sm(lp[n1:n1 + n2]), "l3": sm(lp[n1 + n2:])}
        top = lambda v, labs: [(labs[i], float(v[i])) for i in np.argsort(-v)[:3]]
        P = np.stack(probs)
        P /= P.sum(-1, keepdims=True)
        mean = P.mean(0)
        ent = float(-(mean * np.log(mean + 1e-12)).sum())
        votes = [self.tree.l3[i] for i in P.argmax(1)]
        out.update(pred={"l1": t1, "l2": t2, "leaf": leaf, "p_l1": float(p["l1"][self.tree.l1.index(t1)]),
                         "p_l2": float(p["l2"][self.tree.l2.index(t2)]),
                         "p_leaf": float(p["l3"][self.tree.l3.index(leaf)]) if leaf in self.tree.l3 else None,
                         "top_l1": top(p["l1"], self.tree.l1), "top_l2": top(p["l2"], self.tree.l2),
                         "top_leaf": top(p["l3"], self.tree.l3)},
                   mc={"passes": mc, "entropy": ent, "threshold": self.thr_entropy, "agree": votes.count(leaf) / mc,
                       "answered": ent <= self.thr_entropy and not x["non_build"]})
        # điểm dòng trong cả run = attention dòng x đoạn x job (train.predict)
        lw = extra["line_logw"].float().exp().cpu().numpy()
        w = extra["w"]
        lines = [(c, ln, float(lw[g]), texts[c].split("\n")[ln]) for g, (c, ln) in enumerate(zip(extra["l2c"].tolist(), extra["lno"]))]
        out["lines"] = [{"job": x["chunk_meta"][c][1], "chunk": c, "line": ln, "score": s, "text": t[:300]}
                        for c, ln, s, t in sorted(lines, key=lambda r: -r[2])[:5]]
        out["chunks"] = [{"job": x["chunk_meta"][c][1], "step": x["chunk_meta"][c][2], "weight": float(w[c]),
                          "lines": [(t, s) for cc, _, s, t in lines if cc == c]} for c in range(len(texts))]
        out["seconds"] = round(time.time() - t0, 1)
        return out
