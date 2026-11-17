"""Đánh giá agent (Claude Code chạy không tương tác) tìm nguyên nhân lỗi CI ở mức file (14/11/2026).

Câu hỏi: agent đọc (A) log đầy đủ hay (B) đoạn log mô hình phân loại trích ra + loại lỗi mô hình dự đoán thì tìm đúng file
cần sửa tốt hơn, tốn bao nhiêu token? Cả hai cùng có thông tin CI (workflow/job/step) và diff của PR.

Đáp án (giống scripts/analysis/rca_feasibility.py): file trong diff PR tại commit lỗi mà commit qua ĐẦU TIÊN sau đó trên
cùng nhánh PR đã sửa (patch khác nhau giữa diff PR tại commit lỗi và tại commit qua).

Chống lộ đề: repo checkout đúng commit lỗi rồi XOÁ .git (không còn lịch sử phía sau); agent chỉ có Read/Grep/Glob (không
Bash, không web, không MCP), không đọc được ngoài thư mục làm việc, bỏ cấu hình người dùng (--setting-sources project).

    PYTHONPATH=src python scripts/analysis/rca_agent.py pick --smoke          # 3 run thử
    PYTHONPATH=src python scripts/analysis/rca_agent.py prepare
    PYTHONPATH=src python scripts/analysis/rca_agent.py run --cond A B
    PYTHONPATH=src python scripts/analysis/rca_agent.py score
Kết quả ở data/results/rca_agent/.
"""
import argparse
import glob
import gzip
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from rca_feasibility import parse_diff  # noqa: E402

OUT = Path("data/results/rca_agent")
WS = Path(os.environ.get("RCA_WS", r"D:\projects\project3\data\rca_ws"))  # đường dẫn ngắn: Windows giới hạn 260 ký tự
def claude_bin() -> str:
    """claude.exe đi kèm extension VS Code; extension tự cập nhật đổi tên thư mục -> tìm lại bản mới nhất mỗi lần gọi."""
    if os.environ.get("CLAUDE_BIN"):
        return os.environ["CLAUDE_BIN"]
    ext = Path.home() / ".vscode" / "extensions"
    bins = [p / "resources" / "native-binary" / "claude.exe" for p in ext.glob("anthropic.claude-code-*-win32-x64")]
    bins = [b for b in bins if b.exists()]
    if not bins:
        raise FileNotFoundError("không tìm thấy claude.exe trong " + str(ext))
    return str(max(bins, key=lambda b: tuple(int(x) for x in b.parents[2].name.split("-")[2].split("."))))
MODEL = "claude-opus-5-5"
LOG_BYTES = 1_000_000   # "log đầy đủ" = tối đa 1 MB cuối của mỗi job lỗi (log GitHub chỉ giữ 90 ngày)
MAX_TURNS, MAX_USD = 60, 4.0
# mẫu chính 60 run (người dùng duyệt 14/11): log còn hạn, đáp án 1-3 file, mọi file sửa nằm trong diff, sửa <= 3 file
QUOTA = {"compile": 10, "testfailure": 10, "itestfailure": 10, "quality": 8, "dependency": 8, "buildconfig": 5,
         "license": 5, "doc": 4}

SCHEMA = {
    "type": "object",
    "properties": {
        "needs_code_change": {"type": "boolean"},
        "suspects": {"type": "array", "maxItems": 5, "items": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "line": {"type": ["integer", "null"]},
                           "reason": {"type": "string"}},
            "required": ["path", "line", "reason"], "additionalProperties": False}},
        "root_cause": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["needs_code_change", "suspects", "root_cause", "confidence"],
    "additionalProperties": False,
}
PROMPT = """You are investigating why a GitHub Actions CI run failed on a pull request.

The repository is checked out at the failing commit in the current directory (there is no git history).
The `_ci/` folder describes the failure:
- `_ci/info.txt`: repository, workflow, failed jobs and failed steps.
- `_ci/pr.diff`: the changes introduced by the pull request.
{files}

Find the root cause of the failure. Decide whether fixing it requires changing files in this repository (as opposed to
re-running the job or fixing CI infrastructure), and list up to 5 repository files that most likely need to be changed
to fix the failure, most likely first, with the line number when you know it. Paths must be relative to the repository
root. Do not modify any file."""
FILES = {
    "A": "- `_ci/log.txt`: the raw log of the failed job(s); very long logs keep only their last part.",
    "B": "- `_ci/log_excerpt.txt`: excerpts of the failed job log(s), selected by an automatic tool.\n"
         "- `_ci/classifier.txt`: the error category predicted by an automatic classifier for this failure.",
    # C (14/11, sau khi B thiếu tên test ở 2/17 run): như B + log đầy đủ để agent tự mở khi đoạn trích không đủ
    "C": "- `_ci/log_excerpt.txt`: excerpts of the failed job log(s), selected by an automatic tool. Start here.\n"
         "- `_ci/classifier.txt`: the error category predicted by an automatic classifier for this failure.\n"
         "- `_ci/log_full.txt`: the raw log of the failed job(s); very long logs keep only their last part. Open it only "
         "when the excerpts are not enough.",
}
# D (14/11, người dùng duyệt): như B nhưng đoạn trích cắt từ LOG ĐẦY ĐỦ + stack trace test lỗi (agent_excerpt.py)
FILES["D"] = FILES["B"]
# E (15/11, flow người dùng chốt): nhãn của mô hình + các dòng mà đầu dòng nguyên nhân (mô hình k2, --cause-detach)
# chấm cao nhất, mỗi dòng kèm CTX_LINES dòng trước/sau (tự đặt, đã báo) — không có đoạn trích hay log đầy đủ
FILES["E"] = ("- `_ci/log_lines.txt`: the log lines that an automatic classifier identified as the most likely cause of the "
              "failure, most likely first, each with a few surrounding lines.\n"
              "- `_ci/classifier.txt`: the error category predicted by the same classifier for this failure.")
CAUSE_TOP, CTX_LINES = 5, 5
CAUSE_PREDS = "data/results/cause/*/CAUSED_s0_fold*.preds.parquet"
RUN_CONDS = ("A", "B", "C")  # run() luôn chạy đủ các đầu vào này cho mỗi run rồi mới xoá repo


def answer(o: dict) -> dict:
    """Câu trả lời có khuôn của agent; có lượt Claude Code để JSON trong `result` thay vì `structured_output`."""
    so = (o or {}).get("structured_output")
    if so:
        return so
    try:
        return json.loads((o or {}).get("result") or "")
    except (json.JSONDecodeError, TypeError):
        return {}
LEAF_EN = {
    "compile": "compilation error", "quality": "code quality check (format, lint, static analysis)",
    "doc": "documentation generation (javadoc)", "buildconfig": "build configuration (pom.xml / build.gradle)",
    "testfailure": "unit test failure", "license": "license header check", "compatibility": "API compatibility check",
    "dependency": "dependency resolution or version conflict", "itestfailure": "integration / end-to-end test failure",
    "flaky": "flaky test", "git": "git operation in CI", "androidsdk": "Android SDK / emulator setup",
    "infra": "CI infrastructure (secrets, permissions, actions, services)", "network": "network / external service",
    "crash": "runner crash, out of memory or timeout",
}
TIER2_EN = {"viet_code": "fix the code according to the error message", "build_local": "reproduce locally to fix",
            "ci_merge": "fix based on CI results (needs CI environment)", "cau_hinh_ci": "fix the CI configuration",
            "chay_lai": "check external infrastructure, then re-run"}


def sh(cmd, cwd=None, timeout=1800):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)


# ---------------------------------------------------------------- pick
def candidates() -> pd.DataFrame:
    """Run tầng Dự án, PR, có diff, có commit qua kế tiếp; tính đáp án như rca_feasibility."""
    tree = json.load(open("data/kaggle_log_ds/label_tree.json", encoding="utf-8"))
    project = {x for x in tree["parent"] if tree["group"][tree["parent"][x]] == "du_an"}
    lab = pd.read_parquet("data/kaggle_log_ds/runs.parquet", columns=["run_id", "leaf", "repo_fold"])
    runs = pd.read_parquet("data/run_dataset/runs.parquet",
                           columns=["run_id", "repository", "event", "head_sha", "created_at", "workflow",
                                    "failed_job_names", "diff_path", "diff_ok"]).merge(lab, on="run_id")
    runs = runs[runs.leaf.isin(project) & (runs.event == "pull_request") & runs.diff_ok.fillna(False)]
    commits = pd.read_parquet("data/processed/commits_all.parquet",
                              columns=["repository", "event", "sequence", "head_sha", "first_run_at", "outcome"])
    commits = commits[commits.event == "pull_request"].sort_values("first_run_at")
    nxt = {}
    for _, g in commits.groupby("sequence", sort=False):
        s, o = g.head_sha.tolist(), g.outcome.tolist()
        for i in range(len(s)):
            if o[i] == "fail":
                j = next((j for j in range(i + 1, len(s)) if o[j] == "pass"), None)
                if j is not None:
                    nxt[(g.repository.iloc[0], s[i])] = s[j]
    runs["fix_sha"] = [nxt.get((r, s)) for r, s in zip(runs.repository, runs.head_sha)]
    return runs[runs.fix_sha.notna()]


def ground_truth(df: pd.DataFrame) -> pd.DataFrame:
    diffs = pd.read_csv("data/processed/diffs_all.csv", usecols=["repository", "head_sha", "kind", "path", "ok"],
                        low_memory=False)
    diffs = diffs[(diffs.kind == "pr") & diffs.ok].drop_duplicates(["repository", "head_sha"])
    path = dict(zip(zip(diffs.repository, diffs.head_sha), diffs.path))
    rows = []
    for r in df.itertuples():
        a, b = path.get((r.repository, r.head_sha)), path.get((r.repository, r.fix_sha))
        cand = parse_diff(a) if isinstance(a, str) else None
        after = parse_diff(b) if isinstance(b, str) else None
        if not cand or after is None:
            rows.append(dict(run_id=r.run_id, cand=None, gt_files=None, n_touched=None, n_outside=None))
            continue
        touched = {f for f in set(cand) | set(after) if cand.get(f) != after.get(f)}
        rows.append(dict(run_id=r.run_id, cand=sorted(cand), gt_files=sorted(touched & set(cand)),
                         n_touched=len(touched), n_outside=len(touched - set(cand))))
    return df.merge(pd.DataFrame(rows), on="run_id")


def pick(smoke: bool, n_per_leaf: int, max_touched: int, days: int, seed: int) -> None:
    c = candidates()
    c["created_at"] = pd.to_datetime(c.created_at, utc=True)
    c = c[c.created_at >= pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)]  # log còn tải được
    meta = pd.read_json("data/processed/repo_meta.jsonl", lines=True)
    meta["code_mb"] = meta.languages.map(lambda d: sum(d.values()) / 1e6 if isinstance(d, dict) else np.nan)
    c = c.merge(meta[["repository", "code_mb"]], on="repository", how="left")
    rng = np.random.default_rng(seed)
    if smoke:  # 3 run: compile, testfailure, dependency; repo nhỏ để clone nhanh
        c = c[c.code_mb < 3]
        pool = pd.concat([g.sample(min(len(g), 40), random_state=seed) for _, g in c.groupby("leaf")])
        g = ground_truth(pool)
        g = g[g["gt_files"].map(lambda x: x is not None and 1 <= len(x) <= 3) & (g.n_outside == 0) & (g.n_touched <= max_touched)]
        sel = pd.concat([g[g.leaf == lf].head(1) for lf in ("compile", "testfailure", "dependency")])
    else:  # mẫu chính (người dùng duyệt 14/11): chọn ngẫu nhiên theo run, dư ~30% phòng log hết hạn
        smoke_ids = set(pd.read_parquet(OUT / "sample_smoke.parquet").run_id) if (OUT / "sample_smoke.parquet").exists() else set()
        c = c[~c.run_id.isin(smoke_ids)]
        sel = []
        for lf, q in QUOTA.items():
            g = c[c.leaf == lf].sample(frac=1, random_state=seed)
            got = []
            for i in range(0, len(g), 200):  # tính đáp án theo lô cho tới khi đủ
                gg = ground_truth(g.iloc[i:i + 200])
                gg = gg[gg["gt_files"].map(lambda x: x is not None and 1 <= len(x) <= 3) & (gg.n_outside == 0)
                        & (gg.n_touched <= max_touched)]
                got.append(gg)
                if sum(map(len, got)) >= int(np.ceil(q * 1.3)):
                    break
            sel.append(pd.concat(got).head(int(np.ceil(q * 1.3))))
            print(lf, len(sel[-1]))
        sel = pd.concat(sel)
    OUT.mkdir(parents=True, exist_ok=True)
    sel.to_parquet(OUT / ("sample_smoke.parquet" if smoke else "sample.parquet"), index=False)
    print(sel[["run_id", "repository", "leaf", "code_mb", "gt_files", "n_touched"]].to_string())


# ---------------------------------------------------------------- prepare
def failed_job_ids(repo: str, run_id: int) -> list:
    d = Path("data/crawl_pr") / repo.replace("/", "__")
    for line in (d / "jobs.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        if r["run_id"] == run_id:
            return [(j["id"], j["name"], [s["name"] for s in j.get("steps", []) if s.get("conclusion") == "failure"])
                    for j in r["jobs"] if j.get("conclusion") == "failure" and (d / "logs" / f"{j['id']}.txt").exists()]
    return []


def classifier_txt(leaf: str, logp) -> str:
    tree = json.load(open("data/kaggle_log_ds/label_tree.json", encoding="utf-8"))
    lp = np.array(logp)[len(tree["l1"]) + len(tree["l2"]):]
    prob = float(np.exp(lp[tree["l3"].index(leaf)])) if leaf in tree["l3"] else None
    t2 = tree["parent"][leaf]
    art = "project (code / build configuration)" if tree["group"][t2] == "du_an" else "CI environment"
    txt = f"predicted error category: {leaf} ({LEAF_EN[leaf]})\n"
    if prob is not None:
        txt += f"probability: {prob:.2f}\n"
    return txt + f"artifact: {art}\nsuggested handling: {TIER2_EN[t2]}\n"


def cause_view(run_id: int) -> tuple | None:
    """Đầu vào E: (log_lines.txt, classifier.txt) từ mô hình k2 của fold có run ở tập kiểm tra, hoặc None."""
    from project3.model.inputs import focus_window
    for f in glob.glob(CAUSE_PREDS):
        p = pd.read_parquet(f, columns=["test", "run_id", "pred", "logp", "cause_lines"],
                            filters=[("run_id", "==", run_id)])
        p = p[p.test == "full"]
        if not len(p):
            continue
        ch = pd.read_parquet("data/kaggle_log_ds/chunks.parquet", filters=[("run_id", "==", run_id)])
        texts = [focus_window(t, 1600, "split").split("\n") for t in ch.sort_values(["job_id", "chunk_idx"]).text]
        used, blocks = set(), []
        for _, _, _, w, line in json.loads(p.cause_lines.iloc[0])[:CAUSE_TOP]:
            # tìm dòng trong các đoạn mô hình đã đọc (so khớp nội dung; dòng trùng nội dung lấy lần xuất hiện chưa dùng)
            hit = next(((c, i) for c, ls in enumerate(texts) for i, x in enumerate(ls)
                        if x[:200] == line and (c, i) not in used), None)
            if hit is None:
                continue
            used.add(hit)
            c, i = hit
            lo, hi = max(0, i - CTX_LINES), min(len(texts[c]), i + CTX_LINES + 1)
            if any(c == c2 and lo <= h2 and l2 <= hi for c2, l2, h2, _ in blocks):  # trùng khối trước -> gộp
                for k, (c2, l2, h2, ws) in enumerate(blocks):
                    if c == c2 and lo <= h2 and l2 <= hi:
                        blocks[k] = (c2, min(l2, lo), max(h2, hi), ws + [(i, w)])
                        break
                continue
            blocks.append((c, lo, hi, [(i, w)]))
        out, seen = [], []
        for c, lo, hi, ws in blocks:
            # 16/11: các đoạn mô hình đọc có thể chồng nhau -> bỏ khối mà mọi dòng đã có trong một khối trước
            raw = texts[c][lo:hi]
            if any(all(x in s for x in raw) for s in seen):
                continue
            seen.append(set(raw))
            marks = {i for i, _ in ws}
            body = "\n".join((">> " if j in marks else "   ") + texts[c][j] for j in range(lo, hi))
            out.append(f"===== candidate {len(out) + 1} (lines marked >> are the selected lines) =====\n{body}")
        return "\n\n".join(out), classifier_txt(p.pred.iloc[0], p.logp.iloc[0])
    return None


def ctx_e(base: Path, run_id: int) -> bool:
    d = base / "E"
    if d.exists():
        return True
    v = cause_view(run_id)
    if v is None:
        return False
    d.mkdir()
    for k in ("info.txt", "pr.diff"):
        shutil.copy(base / "B" / k, d / k)
    (d / "log_lines.txt").write_text(v[0], encoding="utf-8")
    (d / "classifier.txt").write_text(v[1], encoding="utf-8")
    return True


def model_view(run_id: int) -> tuple:
    """(đoạn log mô hình đọc, dự đoán) — mô hình C seed 0 của lần chia có repo ở tập kiểm tra."""
    from project3.model.inputs import focus_window
    ch = pd.read_parquet("data/kaggle_log_ds/chunks.parquet", filters=[("run_id", "==", run_id)])
    ch = ch.sort_values(["job_id", "chunk_idx"])
    excerpt = "\n\n".join(f"===== excerpt {i + 1} (job {r.job_id}) =====\n{focus_window(r.text, 1600, 'split')}"
                          for i, r in enumerate(ch.itertuples()))
    tree = json.load(open("data/kaggle_log_ds/label_tree.json", encoding="utf-8"))
    for f in glob.glob("data/results/c/*/C_s0_fold*.preds.parquet"):
        p = pd.read_parquet(f, columns=["test", "run_id", "pred", "logp"], filters=[("run_id", "==", run_id)])
        p = p[p.test == "full"]
        if len(p):
            leaf = p.pred.iloc[0]
            lp = np.array(p.logp.iloc[0])[len(tree["l1"]) + len(tree["l2"]):]
            prob = float(np.exp(lp[tree["l3"].index(leaf)])) if leaf in tree["l3"] else None
            t2 = tree["parent"][leaf]
            art = "project (code / build configuration)" if tree["group"][t2] == "du_an" else "CI environment"
            txt = f"predicted error category: {leaf} ({LEAF_EN[leaf]})\n"
            if prob is not None:
                txt += f"probability: {prob:.2f}\n"
            txt += f"artifact: {art}\nsuggested handling: {TIER2_EN[t2]}\n"
            return excerpt, txt, leaf
    return excerpt, "", None


def clone_ws(r) -> str | None:
    """Repo tại commit lỗi, đã xoá .git, ở WS/<run_id>. Trả về lỗi (chuỗi) hoặc None."""
    ws = WS / str(r.run_id)
    if ws.exists():
        return None
    ws.mkdir(parents=True)
    url = f"https://github.com/{r.repository}.git"
    for cmd in (["git", "init", "-q"], ["git", "remote", "add", "origin", url],
                ["git", "-c", "core.longpaths=true", "fetch", "-q", "--depth", "1", "origin", r.head_sha],
                ["git", "-c", "core.longpaths=true", "checkout", "-q", "FETCH_HEAD"]):
        try:
            p = sh(cmd, cwd=ws)
        except subprocess.TimeoutExpired:
            p = None
        if p is None or p.returncode:
            shutil.rmtree(ws, ignore_errors=True)
            return f"{' '.join(cmd)}: {'quá giờ' if p is None else p.stderr[:200]}"
    shutil.rmtree(ws / ".git", onexc=lambda f, p, e: (os.chmod(p, 0o700), f(p)))  # file chỉ đọc trên Windows
    return None


def ctx_c(base: Path) -> None:
    """Đầu vào C = B + log đầy đủ (lấy từ A), tạo từ các file đã chuẩn bị, không cần mạng."""
    d = base / "C"
    if d.exists():
        return
    shutil.copytree(base / "B", d)
    shutil.copy(base / "A" / "log.txt", d / "log_full.txt")


def ctx_d(base: Path) -> None:
    """Đầu vào D = B với log_excerpt.txt thay bằng đoạn trích cắt từ log đầy đủ (agent_excerpt.excerpt_v2)."""
    d = base / "D"
    if d.exists():
        return
    from agent_excerpt import excerpt_v2
    shutil.copytree(base / "B", d)
    (d / "log_excerpt.txt").write_text(excerpt_v2((base / "A" / "log.txt").read_text(encoding="utf-8")),
                                       encoding="utf-8")


def prepare() -> None:
    from project3.crawl.github import GitHub, load_token
    gh = GitHub(load_token())
    s = pd.read_parquet(OUT / "sample.parquet")
    ready = {}
    for r in s.itertuples():
        base = OUT / "ctx" / str(r.run_id)
        if (base / "done").exists():
            ready[r.leaf] = ready.get(r.leaf, 0) + 1
            continue
        if ready.get(r.leaf, 0) >= QUOTA.get(r.leaf, 1):  # đủ chỉ tiêu, không chuẩn bị run dự phòng
            continue
        jobs = failed_job_ids(r.repository, r.run_id)
        logs = []
        for jid, name, steps in jobs:
            try:
                t = gh.get_log_tail(f"/repos/{r.repository}/actions/jobs/{jid}/logs", tail_bytes=LOG_BYTES)
            except Exception as e:  # lỗi mạng (SSL, quá giờ...): bỏ job này, không làm dừng cả chuỗi
                print(r.run_id, f"tải log job {jid} lỗi: {type(e).__name__}", flush=True)
                t = None
            if t:
                logs.append(f"===== job: {name} (id {jid}) =====\n{t}")
        if not logs:
            print(r.run_id, "không tải được log (hết hạn?)")
            continue
        info = (f"repository: {r.repository}\nworkflow: {r.workflow}\nevent: pull_request\n" +
                "".join(f"failed job: {n}; failed steps: {', '.join(st) or 'unknown'}\n" for _, n, st in jobs))
        excerpt, cls, pred = model_view(r.run_id)
        diff = gzip.open(r.diff_path, "rt", encoding="utf-8", errors="replace").read()
        for cond, files in (("A", {"log.txt": "\n\n".join(logs)}),
                            ("B", {"log_excerpt.txt": excerpt, "classifier.txt": cls})):
            d = base / cond
            d.mkdir(parents=True, exist_ok=True)
            for k, v in {"info.txt": info, "pr.diff": diff, **files}.items():
                (d / k).write_text(v, encoding="utf-8")
        failed = clone_ws(r)
        if failed:  # một run lỗi không làm dừng cả chuỗi: bỏ, run dự phòng của lá sẽ thế chỗ
            print(r.run_id, "bỏ, clone lỗi:", failed, flush=True)
            shutil.rmtree(base, ignore_errors=True)
            continue
        json.dump({"pred": pred, "log_chars_A": sum(map(len, logs)), "log_chars_B": len(excerpt)},
                  open(base / "meta.json", "w"))
        (base / "done").write_text("ok")
        ready[r.leaf] = ready.get(r.leaf, 0) + 1
        print(r.run_id, r.repository, f"log A {sum(map(len, logs)) / 1e3:.0f}k ký tự, B {len(excerpt) / 1e3:.0f}k, "
                                      f"dự đoán {pred}")


# ---------------------------------------------------------------- run
def run(conds: list) -> None:
    s = pd.read_parquet(OUT / "sample.parquet")
    (OUT / "runs").mkdir(parents=True, exist_ok=True)
    used = {}
    for r in s.itertuples():
        ws, base = WS / str(r.run_id), OUT / "ctx" / str(r.run_id)
        if not (base / "done").exists():
            continue
        if used.get(r.leaf, 0) >= QUOTA.get(r.leaf, 1):  # đủ chỉ tiêu của lá (mẫu chọn dư 30%)
            continue
        used[r.leaf] = used.get(r.leaf, 0) + 1
        ctx_c(base)
        ctx_d(base)
        has_e = ctx_e(base, r.run_id)
        todo = [c for c in dict.fromkeys([*conds, *RUN_CONDS]) if not (OUT / "runs" / f"{r.run_id}_{c}.json").exists()
                and (c != "E" or has_e)]
        if todo and not ws.exists():  # repo đã xoá (run chạy A/B trước khi có C) -> clone lại
            err = clone_ws(r)
            if err:
                print(r.run_id, "clone lại lỗi:", err, flush=True)
                continue
        for cond in todo:
            out = OUT / "runs" / f"{r.run_id}_{cond}.json"
            if (ws / "_ci").exists():
                shutil.rmtree(ws / "_ci")
            shutil.copytree(base / cond, ws / "_ci")
            cmd = [claude_bin(), "-p", PROMPT.format(files=FILES[cond]), "--output-format", "json",
                   "--json-schema", json.dumps(SCHEMA), "--model", MODEL, "--tools", "Read,Grep,Glob",
                   "--strict-mcp-config", "--setting-sources", "project", "--disable-slash-commands",
                   "--no-session-persistence", "--max-turns", str(MAX_TURNS), "--max-budget-usd", str(MAX_USD)]
            t0 = time.time()
            p = sh(cmd, cwd=ws, timeout=3600)
            rec = {"run_id": r.run_id, "cond": cond, "seconds": round(time.time() - t0, 1), "returncode": p.returncode,
                   "stderr": p.stderr[-2000:]}
            try:
                rec["out"] = json.loads(p.stdout)
            except json.JSONDecodeError:
                rec["raw"] = p.stdout[-5000:]
            out.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
            o = rec.get("out", {})
            print(r.run_id, cond, f"{rec['seconds']:.0f}s", f"cost≈${o.get('total_cost_usd', float('nan')):.2f}",
                  f"turns {o.get('num_turns')}", "lỗi" if p.returncode else "")
        shutil.rmtree(ws / "_ci", ignore_errors=True)
        if all((OUT / "runs" / f"{r.run_id}_{c}.json").exists() for c in RUN_CONDS):
            shutil.rmtree(ws, ignore_errors=True)  # chạy xong mọi đầu vào -> xoá repo cho nhẹ ổ đĩa


# ---------------------------------------------------------------- judge (mức 2)
def judge_schema(n: int) -> dict:
    return {
    "type": "object",
    "properties": {
        "fix_addresses_failure": {"type": "string", "enum": ["yes", "no", "unclear"]},
        "failure_kind": {"type": "string", "enum": ["code_or_build_config", "transient_or_infrastructure", "unclear"]},
        "fix_summary": {"type": "string"},
        "verdicts": {"type": "array", "minItems": n, "maxItems": n, "items": {
            "type": "object",
            "properties": {"answer": {"type": "string", "enum": list(LETTERS[:n])},
                           "root_cause": {"type": "string", "enum": ["correct", "partially_correct", "wrong"]},
                           "reason": {"type": "string"}},
            "required": ["answer", "root_cause", "reason"], "additionalProperties": False}},
    },
    "required": ["fix_addresses_failure", "failure_kind", "fix_summary", "verdicts"],
    "additionalProperties": False,
    }


LETTERS = "XYZW"
JUDGE_SCHEMA = judge_schema(3)
JUDGE_PROMPT_HEAD = """You are grading {n} automated root-cause analyses of a failed GitHub Actions CI run on a pull request.
The input (after this instruction) contains: the CI failure log (its last part), the changes the developer made in the
NEXT commit of the same pull request (after which CI passed), and {n} analyses {letters}. Give exactly one verdict
per analysis, labelled with that analysis's letter."""
JUDGE_PROMPT = JUDGE_PROMPT_HEAD.format(n="three", letters="X, Y and Z")
JUDGE_PROMPT_REST = """

1. Decide whether the developer's next commit actually addresses this failure (`fix_addresses_failure`). It may not:
   the failure can be transient (network, runner, flaky test) and the next commit may contain unrelated work.
2. Decide whether the failure was caused by the code / build configuration or was transient / infrastructure.
3. For each analysis, judge whether its root cause is correct, partially correct, or wrong, using the log and the
   developer's change as evidence. A different but valid way to fix the same root cause counts as correct.
Judge only from the evidence given."""
JUDGE_PROMPT = JUDGE_PROMPT + "\n" + JUDGE_PROMPT_REST
def judge_prompt(n: int) -> str:
    if n == 3:
        return JUDGE_PROMPT  # giữ nguyên câu lệnh của lần chấm 3 câu
    letters = ", ".join(LETTERS[:n - 1]) + " and " + LETTERS[n - 1]
    return JUDGE_PROMPT_HEAD.format(n={2: "two", 4: "four"}[n], letters=letters) + "\n" + JUDGE_PROMPT_REST


JUDGE_LOG_CHARS, JUDGE_FIX_CHARS = 30_000, 20_000  # giới hạn độ dài đưa cho LLM chấm (tự đặt, đã báo)


def fix_changes(r) -> str:
    """Patch của những file mà commit sửa đã đổi (so diff PR tại commit lỗi với diff PR tại commit qua)."""
    diffs = pd.read_csv("data/processed/diffs_all.csv", usecols=["repository", "head_sha", "kind", "path", "ok"],
                        low_memory=False)
    diffs = diffs[(diffs.kind == "pr") & diffs.ok & (diffs.repository == r.repository)]
    path = dict(zip(diffs.head_sha, diffs.path))
    a, b = parse_diff(path[r.head_sha]), parse_diff(path[r.fix_sha])
    out = []
    for f in sorted(set(a) | set(b)):
        if a.get(f) != b.get(f):
            out.append(f"--- file {f}\n[PR diff of this file BEFORE the next commit]\n{a.get(f, '(file not in PR)')}"
                       f"\n[PR diff of this file AFTER the next commit]\n{b.get(f, '(file no longer in PR)')}")
    return "\n".join(out)[:JUDGE_FIX_CHARS]


def judge(conds: tuple = RUN_CONDS, jdir: str = "judge") -> None:
    """Chấm cùng lúc các câu trả lời `conds` (tên X/Y/Z/W xáo ngẫu nhiên) -> OUT/<jdir>/<run>.json."""
    s = pd.read_parquet(OUT / "sample.parquet")
    (OUT / jdir).mkdir(parents=True, exist_ok=True)
    empty = OUT / "judge_cwd"
    empty.mkdir(exist_ok=True)
    rng = np.random.default_rng(0)
    for r in s.itertuples():
        out = OUT / jdir / f"{r.run_id}.json"
        fs = {c: OUT / "runs" / f"{r.run_id}_{c}.json" for c in conds}
        perm = [str(x) for x in rng.permutation(list(conds))]  # rút ngẫu nhiên cho mọi run (giữ thứ tự tái lập)
        if not all(f.exists() for f in fs.values()):
            continue
        if out.exists() and len(json.loads(out.read_text(encoding="utf-8")).get("order", [])) == len(conds):
            continue  # đã chấm đủ 3 câu (file chấm cũ 2 câu A/B sẽ được chấm lại)
        ans = {c: json.dumps(answer(json.loads(f.read_text(encoding="utf-8")).get("out")), ensure_ascii=False, indent=1)
               for c, f in fs.items()}
        order = perm  # X/Y/Z xáo ngẫu nhiên, LLM chấm không biết đâu là A/B/C
        log = (OUT / "ctx" / str(r.run_id) / "A" / "log.txt").read_text(encoding="utf-8")[-JUDGE_LOG_CHARS:]
        body = (f"===== CI FAILURE LOG (last part) =====\n{log}\n\n===== DEVELOPER'S NEXT COMMIT =====\n{fix_changes(r)}\n"
                + "".join(f"\n===== ANALYSIS {k} =====\n{ans[c]}\n" for k, c in zip(LETTERS, order)))
        cmd = [claude_bin(), "-p", judge_prompt(len(conds)), "--output-format", "json",
               "--json-schema", json.dumps(judge_schema(len(conds))),
               "--model", MODEL, "--tools", "", "--strict-mcp-config", "--setting-sources", "project",
               "--disable-slash-commands", "--no-session-persistence", "--max-turns", "3"]
        p = subprocess.run(cmd, cwd=empty, input=body, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=1800)
        rec = {"run_id": r.run_id, "order": order, "returncode": p.returncode, "stderr": p.stderr[-1000:]}
        try:
            rec["out"] = json.loads(p.stdout)
        except json.JSONDecodeError:
            rec["raw"] = p.stdout[-3000:]
        out.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        o = rec.get("out", {})
        print(r.run_id, f"cost≈${o.get('total_cost_usd', float('nan')):.2f}",
              (o.get("structured_output") or {}).get("fix_addresses_failure"))


# ---------------------------------------------------------------- score
def norm(p: str, cand: list) -> str:
    p = p.replace("\\", "/").removeprefix("./")
    if p in cand:
        return p
    hit = [c for c in cand if c.endswith("/" + p) or p.endswith("/" + c)]
    return hit[0] if len(hit) == 1 else p


def score(jdir: str = "judge") -> None:
    s = pd.read_parquet(OUT / "sample.parquet").set_index("run_id")
    rows = []
    for f in sorted((OUT / "runs").glob("*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        o = rec.get("out", {})
        so = answer(o)
        r = s.loc[rec["run_id"]]
        cand, gt = list(r["cand"]), set(r["gt_files"])
        sus = [norm(x["path"], cand) for x in so.get("suspects", [])]
        u = o.get("usage", {})
        rows.append(dict(run_id=rec["run_id"], leaf=r["leaf"], cond=rec["cond"], ok=bool(so),
                         top1=bool(sus[:1]) and sus[0] in gt, top3=any(x in gt for x in sus[:3]),
                         any5=any(x in gt for x in sus), in_diff=np.mean([x in cand for x in sus]) if sus else np.nan,
                         needs_code=so.get("needs_code_change"), n_sus=len(sus),
                         rand_top1=len(gt) / len(cand), cost_usd=o.get("total_cost_usd"), turns=o.get("num_turns"),
                         in_tok=u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                         + u.get("cache_creation_input_tokens", 0), out_tok=u.get("output_tokens"),
                         in_uncached=u.get("input_tokens", 0), in_cache_write=u.get("cache_creation_input_tokens", 0),
                         in_cache_read=u.get("cache_read_input_tokens", 0),
                         seconds=rec["seconds"]))
    d = pd.DataFrame(rows)
    # mức 2: LLM chấm (X/Y -> A/B theo thứ tự đã xáo)
    jrows = []
    for f in sorted((OUT / jdir).glob("*.json")) if (OUT / jdir).exists() else []:
        rec = json.loads(f.read_text(encoding="utf-8"))
        so = (rec.get("out") or {}).get("structured_output") or {}
        m = dict(zip(LETTERS, rec["order"]))
        for v in so.get("verdicts", []):
            jrows.append(dict(run_id=rec["run_id"], cond=m[v["answer"]], judge=v["root_cause"],
                              fix_ok=so.get("fix_addresses_failure"), kind=so.get("failure_kind"),
                              judge_cost=(rec.get("out") or {}).get("total_cost_usd", 0) / len(rec["order"])))
    if jrows:
        d = d.merge(pd.DataFrame(jrows), on=["run_id", "cond"], how="left")
    d.to_csv(OUT / "scores.csv", index=False)
    pd.set_option("display.width", 250)
    print(d.to_string(index=False))
    cols = ["top1", "top3", "any5", "needs_code", "rand_top1", "cost_usd", "turns", "in_tok", "out_tok", "seconds"]
    print("\n== tất cả run"); print(d.groupby("cond")[cols].mean().round(3).to_string())
    tok = ["in_tok", "in_uncached", "in_cache_write", "in_cache_read", "out_tok", "cost_usd"]
    print("\n== khối lượng token mỗi lượt (trung bình / trung vị / tổng)")
    print(d.groupby("cond")[tok].agg(["mean", "median", "sum"]).round(0).T.to_string())
    if jrows:
        v = d[d.fix_ok == "yes"]
        print(f"\n== chỉ run mà commit sau thật sự sửa lỗi này (LLM chấm): {v.run_id.nunique()}/{d.run_id.nunique()} run")
        print(v.groupby("cond")[["top1", "top3", "any5"]].mean().round(3).to_string())
        print("\n== LLM chấm nguyên nhân (mọi run)")
        print(pd.crosstab(d.cond, d.judge, normalize="index").round(3).to_string())
        print("\n== LLM chấm nguyên nhân, chỉ run commit sau thật sự sửa lỗi")
        print(pd.crosstab(v.cond, v.judge, normalize="index").round(3).to_string())
        print("\nfix_addresses_failure:", d.drop_duplicates("run_id").fix_ok.value_counts().to_dict(),
              "| failure_kind:", d.drop_duplicates("run_id").kind.value_counts().to_dict(),
              f"| chi phí chấm ≈ ${d.judge_cost.sum():.2f}")
    print(f"tổng chi phí agent ≈ ${d.cost_usd.sum():.2f}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pick")
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--n-per-leaf", type=int, default=8)
    p.add_argument("--max-touched", type=int, default=3)
    p.add_argument("--days", type=int, default=85)
    p.add_argument("--seed", type=int, default=0)
    sub.add_parser("prepare")
    p = sub.add_parser("run")
    p.add_argument("--cond", nargs="+", default=["A", "B"])
    p = sub.add_parser("judge")
    p.add_argument("--conds", nargs="+", default=list(RUN_CONDS))
    p.add_argument("--dir", default="judge")
    p = sub.add_parser("score")
    p.add_argument("--dir", default="judge")
    a = ap.parse_args()
    if a.cmd == "pick":
        pick(a.smoke, a.n_per_leaf, a.max_touched, a.days, a.seed)
    elif a.cmd == "prepare":
        prepare()
    elif a.cmd == "run":
        run(a.cond)
    elif a.cmd == "judge":
        judge(tuple(a.conds), a.dir)
    else:
        score(a.dir)
