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
MAX_JOBS = 2      # số job fail dùng cho nhãn chung của run, như lúc crawl (--max-jobs-per-run 2)
MAX_LOG_JOBS = 8  # số job fail tải log để dự đoán riêng từng job (03/11)
MC_PASSES = 20    # bằng lần đo ngưỡng
WINDOW = 1600
NAMES = {  # tên hiển thị (03/11: người dùng chọn nhãn tiếng Anh); lá giữ đúng tên nhãn trong dữ liệu
    "du_an": "Project", "moi_truong": "CI environment",
    # tầng 2 "Cách xử lý" (04/11): Sửa code theo thông báo lỗi / Tái hiện lỗi ở local để sửa / Sửa dựa trên kết quả CI /
    # Sửa cấu hình CI / Kiểm tra hạ tầng ngoài
    "viet_code": "Fix code from the error message", "build_local": "Reproduce locally to fix",
    "ci_merge": "Fix based on CI results", "cau_hinh_ci": "Fix CI configuration",
    "chay_lai": "Check external infrastructure",
}
ACTION = {  # gợi ý hành động theo tầng 2
    "viet_code": "Thông báo lỗi đã chỉ ra file và dòng cần sửa. Sửa theo đó rồi push lại.",
    "build_local": "Chạy lại build ở máy bằng mvn verify hoặc gradle check để tái hiện lỗi rồi sửa.",
    "ci_merge": "Lỗi chỉ xuất hiện trên CI, thường ở test tích hợp hoặc emulator. Xem kết quả test trên CI để sửa.",
    "cau_hinh_ci": "Sửa file workflow, secrets hoặc cấu hình runner. Không cần sửa code.",
    "chay_lai": "Lỗi đến từ hạ tầng bên ngoài như mạng, kho thư viện hay dịch vụ ngoài. Kiểm tra hạ tầng đó, "
                "khi đã ổn thì chạy lại.",
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
    picked = {j["id"] for j in pick_jobs(jobs, MAX_JOBS)}
    for j in pick_jobs(jobs, MAX_LOG_JOBS):
        j["log"] = gh.get_log_tail(f"/repos/{repo}/actions/jobs/{j['id']}/logs")
        j["picked"] = j["id"] in picked
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

def failed_jobs(rec: dict) -> list:
    return [j for j in rec["jobs"] if j["conclusion"] == "failure" and not AGG_JOB.search(j["name"])]


def preprocess(rec: dict, only: int = None) -> dict:
    """Bản ghi run -> đầu vào mô hình + nhãn quy tắc. rec["jobs"][i]["log"]: log đã tải (None nếu không có).
    only=None: cả run, chỉ dùng log các job `picked` (như dữ liệu huấn luyện); only=job id: coi job đó như một run chỉ có
    một job fail (dự đoán riêng từng job)."""
    failed = failed_jobs(rec)
    if only is not None:
        failed = [j for j in failed if j["id"] == only]
    names = " ".join(j["name"] for j in failed)
    texts, tools, by_job, rule_texts = [], [], [], []
    for j in sorted(failed, key=lambda j: j["id"]):
        if not j.get("log") or (only is None and not j.get("picked", True)):
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
    nb_why = ("workflow không phải build" if NON_BUILD_WF.search(rec["workflow"] or "") else
              f"bộ quy tắc nhận ra dòng `{ev[:80]}`" if gold == "non_build" else "")
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
            "diff": rec["diff"]["vector"] if "vector" in rec["diff"] else diff_vector(rec["diff"], rec["event"]),
            "ctx": ci_context(rec["workflow"] or "", names[:500], step_str)[:400],
            "failed_jobs": [j["name"] for j in failed], "failed_steps": step_str,
            "rule": {"label_l2": gold, "leaf": rule_leaf, "evidence": ev},
            "non_build": non_build(names, step_str, len(failed)) or nb_why}


# ---------- mô hình ----------

class Predictor:
    """Nạp cây nhãn, chuẩn hoá đặc trưng, weight 5 fold (lười). Repo có trong dữ liệu -> mô hình của fold mà repo nằm ở
    tập test (mô hình chưa thấy repo); repo mới -> DEFAULT_FOLD."""

    def __init__(self, bundle: Path, weights: str, device: str = None, cause_weights: str = None):
        """cause_weights (16/11/2026): mẫu đường dẫn weight mô hình có đầu dòng nguyên nhân (CAUSED_s0_fold{fold}); chỉ
        dùng để chấm dòng nguyên nhân, nhãn và độ tin cậy vẫn lấy từ `weights` (ngưỡng entropy đã chỉnh theo mô hình đó)."""
        import torch
        self.cause_weights = cause_weights
        self.bundle = Path(bundle)
        self.tree = LabelTree.load(self.bundle / "label_tree.json")
        self.norm = json.loads((self.bundle / "norm.json").read_text())
        self.repo_fold = json.loads((self.bundle / "repo_fold.json").read_text())
        cfg = json.loads((self.bundle / "config.json").read_text())
        self.thr_entropy, self.default_fold = cfg["thr_entropy"], cfg["default_fold"]
        self.weights = weights  # mẫu đường dẫn có {fold}
        self.dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.nets = {}

    def net(self, fold: int, cause: bool = False):
        import torch
        from project3.model.nn.net import LogNet
        key = (fold, cause)
        if key not in self.nets:
            net = LogNet(self.tree, self.dev, freeze_layers=6, feat_dim=len(self.norm[str(fold)]["mu"]), line_attn=True,
                         cause_head=cause)
            sd = torch.load((self.cause_weights if cause else self.weights).format(fold=fold), map_location="cpu")
            miss = net.load_state_dict({k: v.float() if v.is_floating_point() else v for k, v in sd.items()}, strict=False)
            assert not miss.unexpected_keys, miss.unexpected_keys
            self.nets[key] = net.to(self.dev).eval()
        return self.nets[key]

    def predict(self, rec: dict, mc: int = MC_PASSES, per_job: bool = True) -> dict:
        """Nhãn chung của run (như lúc đánh giá) + (per_job) nhãn riêng từng job fail có log."""
        t0 = time.time()
        x = preprocess(rec)
        out = {k: rec[k] for k in ("repo", "run_id", "url", "workflow", "event", "created_at", "head_sha") if k in rec}
        out["diff_files"] = (rec.get("diff") or {}).get("files", [])  # để đánh dấu file trong log có nằm trong diff
        out.update(failed_jobs=x["failed_jobs"], failed_steps=x["failed_steps"], rule=x["rule"], non_build=x["non_build"])
        if not x["chunks"]:
            return {**out, "error": "Không lấy được log của job lỗi. GitHub chỉ giữ log 90 ngày, "
                                     "hoặc lần chạy này không bị lỗi."}
        fold = self.repo_fold.get(rec["repo"], self.default_fold)
        out["fold"], out["seen_repo"] = fold, rec["repo"] in self.repo_fold
        out.update(self.infer(x, fold, mc))
        jobs = [j for j in failed_jobs(rec) if j.get("log")]
        if per_job and len(jobs) > 1:
            out["per_job"] = []
            for j in sorted(jobs, key=lambda j: j["id"]):
                y = preprocess(rec, only=j["id"])
                if not y["chunks"]:
                    continue
                r = self.infer(y, fold, mc)
                out["per_job"].append({"job": j["name"], "job_id": j["id"], "failed_steps": y["failed_steps"],
                                       "non_build": y["non_build"], "rule": y["rule"], "pred": r["pred"], "mc": r["mc"],
                                       "lines": r["lines"][:3]})
        out["seconds"] = round(time.time() - t0, 1)
        return out

    def infer(self, x: dict, fold: int, mc: int) -> dict:
        import torch
        from project3.model.nn.net import decode
        out = {}
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
        if self.cause_weights:  # dòng nguyên nhân: 1 lượt mô hình có đầu dòng nguyên nhân, không MC Dropout
            with torch.no_grad(), ac():
                cw = self.net(fold, cause=True)(*args, **kw)[4]["cause_logw"].float().exp().cpu().numpy()
            ranked = sorted(((c, ln, float(cw[g])) for g, (c, ln) in enumerate(zip(extra["l2c"].tolist(), extra["lno"]))),
                            key=lambda r: -r[2])[:CAUSE_TOP]
            sp = [t.split("\n") for t in texts]
            out["cause_lines"] = [{"job": x["chunk_meta"][c][1], "chunk": c, "line": ln, "score": s, "text": sp[c][ln][:300]}
                                  for c, ln, s in ranked]
            out["cause_blocks"] = cause_blocks(sp, [(c, ln) for c, ln, _ in ranked],
                                               [x["chunk_meta"][c][1] for c in range(len(texts))])
        return out


CAUSE_TOP, CTX_LINES = 5, 5  # như cách 4 của thí nghiệm agent (scripts/analysis/rca_agent.py, 16/11/2026; tự đặt)


def cause_blocks(sp: list, picks: list, jobs: list) -> list:
    """Mỗi dòng nguyên nhân kèm CTX_LINES dòng trước/sau; khối chồng nhau thì gộp; khối mà mọi dòng đã có trong khối
    trước (các đoạn log chồng nhau) thì bỏ. -> [{job, lines: [(nội dung, có phải dòng được chọn)]}]."""
    blocks = []
    for c, i in picks:
        lo, hi = max(0, i - CTX_LINES), min(len(sp[c]), i + CTX_LINES + 1)
        for b in blocks:
            if b[0] == c and lo <= b[2] and b[1] <= hi:
                b[1], b[2] = min(b[1], lo), max(b[2], hi)
                b[3].add(i)
                break
        else:
            blocks.append([c, lo, hi, {i}])
    out, seen = [], []
    for c, lo, hi, marks in blocks:
        raw = sp[c][lo:hi]
        if any(all(x in s for x in raw) for s in seen):
            continue
        seen.append(set(raw))
        out.append({"job": jobs[c], "lines": [(sp[c][j], j in marks) for j in range(lo, hi)]})
    return out


AGENT_PROMPT = """You are investigating why a GitHub Actions CI run failed (trigger: {event}).

Repository: {repo} (commit {sha}). Failed jobs: {jobs}. Failed steps: {steps}.

An automatic classifier predicted the error category below and selected the log lines most likely to show the cause
(lines marked >> are the selected lines; the others are surrounding context).

Predicted error category: {leaf} (probability {p}). Suggested handling: {l2}.

{blocks}

Find the root cause of the failure in the repository at that commit. Decide whether fixing it requires changing files in
the repository (as opposed to re-running the job or fixing CI infrastructure), and list up to 5 repository files that
most likely need to be changed, most likely first, with the line number when you know it. If the selected lines are not
enough, say what is missing."""


def agent_input(o: dict) -> str:
    """Đầu vào cho agent lập trình theo cách 4 (nhãn + dòng nguyên nhân), để người dùng dán vào Claude Code / agent khác
    đang mở repo ở đúng commit. Demo không tự chạy agent."""
    if not o.get("cause_blocks"):
        return ""
    p = o["pred"]
    blocks = "\n\n".join(f"===== candidate {k} (job {b['job']}) =====\n" + "\n".join(
        (">> " if m else "   ") + t for t, m in b["lines"]) for k, b in enumerate(o["cause_blocks"], 1))
    return AGENT_PROMPT.format(event=o.get("event") or "unknown", repo=o.get("repo"), sha=o.get("head_sha") or "?", jobs=", ".join(o["failed_jobs"]),
                               steps=o["failed_steps"] or "unknown", leaf=p["leaf"],
                               p="?" if p["p_leaf"] is None else f"{p['p_leaf']:.2f}", l2=NAMES.get(p["l2"], p["l2"]),
                               blocks=blocks)
