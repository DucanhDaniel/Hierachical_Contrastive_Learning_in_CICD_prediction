"""Token của agent đi vào đâu (15/11/2026): chạy lại cách D trên vài run với --output-format stream-json để có từng bước.

Mỗi kết quả công cụ (đọc file, tìm chữ, tìm file) nằm lại trong hội thoại và được gửi lại ở mọi bước sau, nên chi phí của
nó ≈ kích thước × (số lần gọi mô hình còn lại). Ghi: loại thao tác (đọc code / đọc pr.diff / đọc log / đoạn trích / tìm
chữ / tìm file), kích thước (token ước = ký tự / 3,5 — tự đặt, chỉ để so tương đối), số lần bị gửi lại.

    python scripts/analysis/rca_trace.py run      # -> data/results/rca_agent/trace/<run>_D.jsonl
    python scripts/analysis/rca_trace.py report
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from rca_agent import (FILES, MAX_TURNS, MAX_USD, MODEL, OUT, PROMPT, SCHEMA, WS, claude_bin,  # noqa: E402
                       clone_ws)

TR = OUT / "trace"
COND = "D"
CHARS_PER_TOK = 3.5
# 10 run trải theo mức token của cách D (cao / vừa / thấp), gồm các run tốn nhất đã bàn
RUNS = [34942615458, 35091516702, 35628134874, 34840039100, 34839696554, 36219812056,
        33126459686, 34588391252, 35259389112, 33017633561]


def run() -> None:
    TR.mkdir(parents=True, exist_ok=True)
    s = pd.read_parquet(OUT / "sample.parquet").drop_duplicates("run_id").set_index("run_id")
    for rid in RUNS:
        out = TR / f"{rid}_{COND}.jsonl"
        if out.exists():
            continue
        r = s.loc[rid]
        r = type("R", (), {"run_id": rid, "repository": r.repository, "head_sha": r.head_sha})
        ws = WS / str(rid)
        err = clone_ws(r)
        if err:
            print(rid, "clone lỗi:", err, flush=True)
            continue
        if (ws / "_ci").exists():
            shutil.rmtree(ws / "_ci")
        shutil.copytree(OUT / "ctx" / str(rid) / COND, ws / "_ci")
        cmd = [claude_bin(), "-p", PROMPT.format(files=FILES[COND]), "--output-format", "stream-json", "--verbose",
               "--json-schema", json.dumps(SCHEMA), "--model", MODEL, "--tools", "Read,Grep,Glob",
               "--strict-mcp-config", "--setting-sources", "project", "--disable-slash-commands",
               "--no-session-persistence", "--max-turns", str(MAX_TURNS), "--max-budget-usd", str(MAX_USD)]
        t0 = time.time()
        p = subprocess.run(cmd, cwd=ws, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=3600)
        out.write_text(p.stdout, encoding="utf-8")
        print(rid, f"{time.time() - t0:.0f}s", "rc", p.returncode, p.stderr[-200:], flush=True)
        shutil.rmtree(ws, ignore_errors=True)


def kind(name: str, inp: dict) -> str:
    path = str(inp.get("file_path") or inp.get("path") or "").replace("\\", "/")
    if name == "Read":
        for k, v in (("pr.diff", "đọc pr.diff"), ("log_full", "đọc log đầy đủ"), ("log.txt", "đọc log đầy đủ"),
                     ("log_excerpt", "đọc đoạn trích"), ("_ci/", "đọc file _ci khác")):
            if k in path:
                return v
        return "đọc code"
    if name == "Grep":
        return "tìm chữ trong _ci" if "_ci" in path or "_ci" in str(inp.get("glob", "")) else "tìm chữ trong code"
    return "tìm file" if name == "Glob" else name


def text_len(c) -> int:
    if isinstance(c, str):
        return len(c)
    if isinstance(c, list):
        return sum(len(x.get("text", "")) if isinstance(x, dict) else len(str(x)) for x in c)
    return len(str(c))


def report() -> None:
    rows, per_run = [], []
    for f in sorted(TR.glob(f"*_{COND}.jsonl")):
        rid = int(f.stem.split("_")[0])
        ev = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.startswith("{")]
        calls, uses, results = 0, {}, []
        call_in = []  # token đầu vào từng lần gọi mô hình
        seen_msg = set()
        for e in ev:
            if e.get("type") == "assistant":
                m = e["message"]
                if m.get("id") not in seen_msg:  # một lần gọi có thể tách thành nhiều sự kiện cùng id
                    seen_msg.add(m.get("id"))
                    calls += 1
                    u = m.get("usage", {})
                    call_in.append(u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                                   + u.get("cache_creation_input_tokens", 0))
                for c in m.get("content", []):
                    if c.get("type") == "tool_use":
                        uses[c["id"]] = (c["name"], c.get("input", {}))
            elif e.get("type") == "user":
                for c in e["message"].get("content", []) if isinstance(e["message"].get("content"), list) else []:
                    if c.get("type") == "tool_result":
                        results.append((c["tool_use_id"], text_len(c.get("content")), calls))
        res = next((e for e in ev if e.get("type") == "result"), {})
        for tid, n, at_call in results:
            name, inp = uses.get(tid, ("?", {}))
            tok = n / CHARS_PER_TOK
            rows.append(dict(run_id=rid, kind=kind(name, inp), tok=tok, resent=calls - at_call,
                             carried=tok * (calls - at_call)))
        per_run.append(dict(run_id=rid, calls=calls, first_call=call_in[0] if call_in else 0,
                            in_tok=sum(call_in), turns=res.get("num_turns"), usd=res.get("total_cost_usd")))
    d, pr = pd.DataFrame(rows), pd.DataFrame(per_run)
    d.to_csv(TR / "tool_results.csv", index=False)
    pr["prompt_part"] = pr.first_call * pr.calls  # phần lời giao việc + định nghĩa công cụ, gửi lại mọi lần gọi
    pr = pr.merge(d.groupby("run_id").carried.sum().rename("tools_part"), on="run_id", how="left")
    pd.set_option("display.width", 200)
    print(pr.round(2).to_string(index=False))
    tot = pr.in_tok.sum()
    print(f"\nTổng token đầu vào {tot:,.0f}: lời giao việc + định nghĩa công cụ (lần gọi đầu × số lần gọi) "
          f"{pr.prompt_part.sum() / tot:.0%}, kết quả công cụ gửi lại {pr.tools_part.sum() / tot:.0%} (ước)")
    g = d.groupby("kind").agg(lần=("tok", "size"), token_mỗi_lần=("tok", "median"), token_gốc=("tok", "sum"),
                              token_gửi_lại=("carried", "sum")).sort_values("token_gửi_lại", ascending=False)
    g["tỉ_lệ"] = g.token_gửi_lại / g.token_gửi_lại.sum()
    print("\nTheo loại thao tác (10 run):")
    print(g.round(2).to_string())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    {"run": run, "report": report}[sys.argv[1]]()
