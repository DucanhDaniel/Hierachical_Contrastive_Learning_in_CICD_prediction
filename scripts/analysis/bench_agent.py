"""Agent tìm nguyên nhân trên benchmark NGOÀI (17/11/2026): 45 lỗi Java (41 GHA-Bench + 4 LogDx-CI), đáp án = bản sửa
thật của lập trình viên (GHA-Bench golden patch) hoặc nguyên nhân chuyên gia viết (LogDx-CI). Người dùng duyệt ~40 USD
danh nghĩa (gói Claude). Cần chạy bench_extract.py build + predict trước (bản ghi run + dự đoán của mô hình trên Colab).

Ba cách đưa đầu vào (cùng repo ở commit lỗi + _ci/pr.diff; chỉ Read/Grep/Glob; như demo.agent):
  A = log đầy đủ của job lỗi (_ci/log.txt, tối đa 1 MB cuối), không có nhãn
  E = cách 4: nhãn của mô hình + 5 dòng nguyên nhân ±5 dòng (demo.predict.agent_input)
  G = đối chứng: nhãn của mô hình + 5 dòng cuối khớp error/fail/exception ±5 dòng (cùng khuôn với E)

    python scripts/analysis/bench_agent.py run | judge | score
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("P3_REPO_CACHE", r"D:\projects\project3\data\bench_repos")
os.environ.setdefault("P3_AGENT_WS", r"D:\projects\project3\data\bench_ws")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from bench_extract import GREP, OUT, cases  # noqa: E402
from project3.demo.agent import MAX_TURNS, MODEL, SCHEMA, TASK, WS, claude_bin, clone, pr_diff, rm  # noqa: E402
from project3.demo.predict import AGENT_PROMPT, NAMES, cause_blocks  # noqa: E402
from project3.pipeline.run_dataset import clean  # noqa: E402

AG, JD = OUT / "agent", OUT / "judge"
CONDS = ("A", "E", "G")
LOG_BYTES = 1_000_000
LETTERS = "XYZ"
JUDGE_LOG_CHARS, JUDGE_REF_CHARS = 30_000, 20_000  # như rca_agent (tự đặt)
A_PROMPT = """You are investigating why a GitHub Actions CI run failed (trigger: {event}).

Repository: {repo} (commit {sha}). Failed jobs: {jobs}. Failed steps: {steps}.

The raw log of the failed job is in `_ci/log.txt` (very long logs keep only their last part).

Find the root cause of the failure in the repository at that commit. Decide whether fixing it requires changing files in
the repository (as opposed to re-running the job or fixing CI infrastructure), and list up to 5 repository files that
most likely need to be changed, most likely first, with the line number when you know it."""


def blocks_text(blocks: list) -> str:
    return "\n\n".join(f"===== candidate {k} (job {b['job']}) =====\n" + "\n".join(
        (">> " if m else "   ") + t for t, m in b["lines"]) for k, b in enumerate(blocks, 1))


def prompts(c: dict, o: dict, agent_in: str) -> dict:
    hdr = dict(event=o.get("event") or "unknown", repo=c["repo"], sha=o["head_sha"], jobs=", ".join(o["failed_jobs"]),
               steps=o["failed_steps"] or "unknown")
    raw = [clean(x) for x in c["log"].lstrip("\ufeff").splitlines()]
    idx = [i for i, x in enumerate(raw) if x.strip() and GREP.search(x) and not x.startswith("##[group]")][-5:][::-1]
    g = cause_blocks([raw], [(0, i) for i in idx], [o["failed_jobs"][0] if o["failed_jobs"] else "?"])
    p = o["pred"]
    lab = dict(leaf=p["leaf"], p="?" if p["p_leaf"] is None else f"{p['p_leaf']:.2f}", l2=NAMES.get(p["l2"], p["l2"]))
    return {"A": A_PROMPT.format(**hdr), "E": agent_in, "G": AGENT_PROMPT.format(**hdr, **lab, blocks=blocks_text(g))}


def run() -> None:
    from project3.crawl.github import GitHub, load_token
    gh = GitHub(load_token())
    AG.mkdir(parents=True, exist_ok=True)
    for c in cases():
        pf = OUT / "pred" / f"{c['case']}.json"
        if not pf.exists():
            continue
        todo = [k for k in CONDS if not (AG / f"{c['case']}_{k}.json").exists()]
        if not todo:
            continue
        p = json.loads(pf.read_text(encoding="utf-8"))
        o = p["o"]
        pr = prompts(c, o, p["agent_in"])
        ws = WS / str(c["run_id"])
        try:
            t0 = time.time()
            clone(c["repo"], o["head_sha"], ws)
            (ws / "_ci").mkdir()
            (ws / "_ci" / "pr.diff").write_text(pr_diff(gh, c["repo"], o["head_sha"], o.get("event", "")), encoding="utf-8")
            clone_s = time.time() - t0
        except Exception as e:  # noqa: BLE001
            print(c["case"], "clone lỗi:", str(e)[:200], flush=True)
            if ws.exists():
                rm(ws)
            continue
        for k in todo:
            log = ws / "_ci" / "log.txt"
            if k == "A":
                log.write_text(c["log"].lstrip("\ufeff")[-LOG_BYTES:], encoding="utf-8")
            elif log.exists():
                log.unlink()
            cmd = [claude_bin(), "-p", TASK, "--output-format", "json", "--json-schema", json.dumps(SCHEMA),
                   "--model", MODEL, "--tools", "Read,Grep,Glob", "--strict-mcp-config", "--setting-sources", "project",
                   "--disable-slash-commands", "--no-session-persistence", "--max-turns", str(MAX_TURNS),
                   "--max-budget-usd", "4"]
            t1 = time.time()
            r = subprocess.run(cmd, cwd=ws, input=pr[k], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=3600)
            rec = {"case": c["case"], "cond": k, "seconds": round(time.time() - t1, 1), "clone_s": round(clone_s, 1),
                   "returncode": r.returncode, "stderr": r.stderr[-1500:], "prompt_chars": len(pr[k])}
            try:
                rec["out"] = json.loads(r.stdout)
            except json.JSONDecodeError:
                rec["raw"] = r.stdout[-3000:]
            (AG / f"{c['case']}_{k}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
            oo = rec.get("out", {})
            print(c["case"], k, f"{rec['seconds']:.0f}s", f"${oo.get('total_cost_usd', float('nan')):.2f}",
                  "lỗi" if r.returncode or oo.get("is_error") else "", flush=True)
            if "hit your" in (r.stdout + r.stderr).lower():  # hết hạn mức gói: dừng, chạy lại sau
                rm(ws)
                sys.exit("hết hạn mức gói Claude, dừng")
        rm(ws)


JUDGE = """You are grading three automated root-cause analyses (X, Y and Z) of a failed GitHub Actions CI run.
The input (after this instruction) contains: the CI failure log (its last part), REFERENCE evidence of the real cause
(either the developer's fix: the diff from the failing commit to the next commit after which CI passed, or a root
cause written by an expert annotator), and the three analyses. Give exactly one verdict per analysis.

1. If the reference is a developer fix, decide whether it actually addresses this failure (`fix_addresses_failure`);
   if the reference is an expert root cause, answer "yes".
2. Decide whether the failure was caused by the code / build configuration or was transient / infrastructure.
3. For each analysis, judge whether its root cause is correct, partially correct, or wrong, using the log and the
   reference as evidence. A different but valid way to fix the same root cause counts as correct.
Judge only from the evidence given."""


def judge_schema() -> dict:
    return {"type": "object", "properties": {
        "fix_addresses_failure": {"type": "string", "enum": ["yes", "no", "unclear"]},
        "failure_kind": {"type": "string", "enum": ["code_or_build_config", "transient_or_infrastructure", "unclear"]},
        "verdicts": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "object", "properties": {
            "answer": {"type": "string", "enum": list(LETTERS)},
            "root_cause": {"type": "string", "enum": ["correct", "partially_correct", "wrong"]},
            "reason": {"type": "string"}}, "required": ["answer", "root_cause", "reason"], "additionalProperties": False}}},
        "required": ["fix_addresses_failure", "failure_kind", "verdicts"], "additionalProperties": False}


def ans(rec: dict) -> dict:
    o = rec.get("out") or {}
    if o.get("structured_output"):
        return o["structured_output"]
    try:
        return json.loads(o.get("result") or "")
    except (json.JSONDecodeError, TypeError):
        return {}


def reference(c: dict) -> str:
    if c["src"] == "GHA-Bench":
        d = next(Path("data/external/gha_bench/repo/GHA-Bench/golden_patches").glob(
            "*/java/" + "/".join(c["case"][4:].rsplit("_", 2))))
        return "DEVELOPER FIX (failing commit -> next commit)\n" + \
            (d / "current_to_next.diff").read_text(encoding="utf-8", errors="replace")[:JUDGE_REF_CHARS]
    gt = json.loads((Path("data/external/logdx/repo/cases") / next(x for x in __import__("bench_extract").LD_JAVA
                                                                   if x.endswith(c["case"][6:])) / "ground_truth.json")
                    .read_text(encoding="utf-8"))
    return "EXPERT ROOT CAUSE\n" + gt["root_cause"]["summary"]


def judge() -> None:
    JD.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    for c in cases():
        perm = [str(x) for x in rng.permutation(list(CONDS))]
        fs = {k: AG / f"{c['case']}_{k}.json" for k in CONDS}
        out = JD / f"{c['case']}.json"
        if out.exists() or not all(f.exists() for f in fs.values()):
            continue
        a = {k: json.dumps(ans(json.loads(f.read_text(encoding="utf-8"))), ensure_ascii=False, indent=1)
             for k, f in fs.items()}
        body = (f"===== CI FAILURE LOG (last part) =====\n{c['log'][-JUDGE_LOG_CHARS:]}\n\n===== REFERENCE =====\n"
                f"{reference(c)}\n" + "".join(f"\n===== ANALYSIS {L} =====\n{a[k]}\n" for L, k in zip(LETTERS, perm)))
        cmd = [claude_bin(), "-p", JUDGE, "--output-format", "json", "--json-schema", json.dumps(judge_schema()),
               "--model", MODEL, "--tools", "", "--strict-mcp-config", "--setting-sources", "project",
               "--disable-slash-commands", "--no-session-persistence", "--max-turns", "3"]
        empty = OUT / "judge_cwd"
        empty.mkdir(exist_ok=True)
        r = subprocess.run(cmd, cwd=empty, input=body, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=1800)
        rec = {"case": c["case"], "order": perm, "returncode": r.returncode, "stderr": r.stderr[-1000:]}
        try:
            rec["out"] = json.loads(r.stdout)
        except json.JSONDecodeError:
            rec["raw"] = r.stdout[-3000:]
        if "hit your" in (r.stdout + r.stderr).lower():
            sys.exit("hết hạn mức gói Claude, dừng")
        out.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        print(c["case"], (rec.get("out") or {}).get("structured_output", {}).get("fix_addresses_failure"), flush=True)


def score() -> None:
    meta = {c["case"]: c for c in cases()}
    rows = []
    for f in sorted(AG.glob("*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        c, a, o = meta[rec["case"]], ans(rec), rec.get("out") or {}
        gt = {x.replace("\\", "/") for x in c["fix_files"]}
        sus = [s["path"].replace("\\", "/").removeprefix("./") for s in a.get("suspects", [])]
        m = lambda p: p in gt or any(g.endswith("/" + p) or p.endswith("/" + g) for g in gt)
        text = (a.get("root_cause", "") + " " + a.get("suggested_fix", "")).lower()
        u = o.get("usage", {})
        rows.append(dict(case=rec["case"], src=c["src"], cond=rec["cond"], ok=bool(a), top1=bool(sus) and m(sus[0]),
                         top3=any(m(x) for x in sus[:3]), needs_code=a.get("needs_code_change"),
                         mention=np.mean([w.lower() in text for w in c["extra"].get("must_mention", [])])
                         if c["extra"] else np.nan,
                         in_tok=u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                         + u.get("cache_creation_input_tokens", 0), out_tok=u.get("output_tokens", 0),
                         turns=o.get("num_turns"), usd=o.get("total_cost_usd"), seconds=rec["seconds"],
                         prompt_k=rec["prompt_chars"] / 1e3))
    d = pd.DataFrame(rows)
    j = []
    for f in sorted(JD.glob("*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        so = (rec.get("out") or {}).get("structured_output") or {}
        mp = dict(zip(LETTERS, rec["order"]))
        for v in so.get("verdicts", []):
            j.append(dict(case=rec["case"], cond=mp[v["answer"]], judge=v["root_cause"], fix_ok=so.get("fix_addresses_failure"),
                          kind=so.get("failure_kind")))
    if j:
        d = d.merge(pd.DataFrame(j), on=["case", "cond"], how="left")
    d.to_csv(OUT / "agent_scores.csv", index=False)
    pd.set_option("display.width", 220)
    print(d.groupby("cond")[["ok", "top1", "top3", "in_tok", "out_tok", "turns", "usd", "seconds", "prompt_k"]].mean()
          .round(3).T.to_string())
    print("trung vị token đầu vào:", d.groupby("cond").in_tok.median().to_dict())
    if j:
        print(pd.crosstab(d.cond, d.judge).to_string())
        v = d[d.fix_ok == "yes"]
        print(f"chỉ lỗi mà bản sửa đúng là sửa lỗi này: {v.case.nunique()}")
        print(v.groupby("cond")[["top1", "top3"]].mean().round(3).to_string())
        print(pd.crosstab(v.cond, v.judge).to_string())
        w = d.pivot_table(index="case", columns="cond", values="judge", aggfunc="first").eq("correct")
        print("A đúng mà E không:", (w.A & ~w.E).sum(), "| E đúng mà A không:", (w.E & ~w.A).sum(),
              "| A đúng mà G không:", (w.A & ~w.G).sum(), "| E đúng mà G không:", (w.E & ~w.G).sum(),
              "| G đúng mà E không:", (w.G & ~w.E).sum())
    print("LogDx must_mention:", d[d.src == "LogDx-CI"].groupby("cond").mention.mean().round(2).to_dict())
    print(f"tổng danh nghĩa agent ${d.usd.sum():.2f}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    {"run": run, "judge": judge, "score": score}[sys.argv[1]]()
