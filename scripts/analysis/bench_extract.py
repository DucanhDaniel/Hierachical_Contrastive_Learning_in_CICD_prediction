"""Đánh giá trích dòng log trên benchmark NGOÀI có nhãn người gán (17/11/2026): 41 lỗi Java của GHA-Bench (gói tái lập
GHA-Tools, nhãn = khoảng dòng log người gán, đáp án = bản sửa thật) + 4 lỗi Java của LogDx-CI (nhãn = dòng bằng chứng
required_signals). Dữ liệu ở data/external/ (xem memory rca-benchmarks).

    python scripts/analysis/bench_extract.py build            # -> data/results/bench/recs/<case>.json (bản ghi run như demo)
    python scripts/analysis/bench_extract.py predict <ngrok>  # gọi mô hình trên Colab (/predict_record) -> pred/<case>.json
    python scripts/analysis/bench_extract.py eval

Đo: dòng đứng đầu / 5 dòng đầu có rơi vào dòng người gán không, cho (a) đầu dòng nguyên nhân, (b) attention phân loại,
(c) N dòng cuối của log, (d) lọc dòng có error/fail/exception (lấy N dòng cuối khớp) — (c), (d) là cách đơn giản như
LogDx-CI; (e) phủ: tỉ lệ dòng người gán nằm trong các khối dòng nguyên nhân ±5 dòng (phần log agent nhận ở cách 4).
So khớp theo nội dung đã chuẩn hoá (bỏ thời gian, mã màu, đường dẫn workspace; 120 ký tự đầu) vì mô hình đọc log đã
tiền xử lý, không giữ số dòng gốc.
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd

from project3.crawl.gha import pick_jobs
from project3.pipeline.run_dataset import clean

GB = Path("data/external/gha_bench/repo/GHA-Bench")
LD = Path("data/external/logdx/repo/cases")
LD_JAVA = ["v2/holdout/gradle-projecthealth-batch5-v2-001", "v2/holdout/spring-boot-checkformat-batch5-v2-001",
           "v2/holdout/hibernate-orm-dbversion-test-batch6-v2-001", "v2/holdout/dubbo-samples-test-timeout-batch6-v2-001"]
OUT = Path("data/results/bench")
LOG_TAIL = 512_000  # như demo (GitHub.get_log_tail mặc định)
N = 5
GREP = re.compile(r"error|fail|exception", re.I)


def norm(x: str) -> str:
    return clean(x.lstrip("﻿")).strip()[:120]


def cases():
    """-> dict(case, src, repo, run_id, head_sha, event, jobs, log, labels (số dòng 1-based), fix_files, extra)."""
    for meta in sorted(GB.glob("cases/*/java/*/*/*/*.json")):
        d = meta.parent
        rel = d.relative_to(GB / "cases")
        m = json.loads(meta.read_text(encoding="utf-8"))
        cl = m["code_download_links"]
        hr = json.loads((GB / "human_review" / rel / "human_review.txt").read_text())
        patch = (GB / "golden_patches" / rel / "current_to_next.diff").read_text(encoding="utf-8", errors="replace")
        yield dict(case="gha_" + "_".join(rel.parts[2:]), src="GHA-Bench", repo=cl["repository"], run_id=int(cl["run_id"]),
                   head_sha=cl["current_commit"]["sha"], event="pull_request", jobs=m["jobs"],
                   log=next(d.glob("*whole_log.txt")).read_text(encoding="utf-8", errors="replace"),
                   labels=sorted({i for a, b in hr for i in range(a, b + 1)}),
                   fix_files=re.findall(r"^diff --git a/(\S+)", patch, re.M), extra={})
    for c in LD_JAVA:
        d = LD / c
        cs = json.loads((d / "case.json").read_text(encoding="utf-8"))
        gt = json.loads((d / "ground_truth.json").read_text(encoding="utf-8"))
        m = re.search(r"github\.com/([^/]+/[^/]+)/actions/runs/(\d+)/job/(\d+)", cs["notes"])
        yield dict(case="logdx_" + d.name, src="LogDx-CI", repo=m.group(1), run_id=int(m.group(2)), job_id=int(m.group(3)),
                   head_sha=None, event=None, jobs=None, log=(d / "raw.log").read_text(encoding="utf-8", errors="replace"),
                   labels=sorted({i for s in gt["required_signals"] for a, b in s.get("evidence_lines", [])
                                  for i in range(a, b + 1)}),
                   fix_files=gt.get("relevant_files", []), extra=gt["expected_diagnosis"])


def build() -> None:
    from project3.crawl.github import GitHub, load_token
    from project3.demo.predict import diff_stats
    gh = GitHub(load_token())
    (OUT / "recs").mkdir(parents=True, exist_ok=True)
    for c in cases():
        f = OUT / "recs" / f"{c['case']}.json"
        if f.exists():
            continue
        if c["jobs"] is None:  # LogDx: lấy job + commit từ GitHub API (log thì dùng bản trong benchmark)
            run = gh.get(f"/repos/{c['repo']}/actions/runs/{c['run_id']}")
            c["head_sha"], c["event"] = run["head_sha"], run["event"]
            c["jobs"] = gh.get(f"/repos/{c['repo']}/actions/runs/{c['run_id']}/jobs", per_page=100)["jobs"]
        jobs = [{"id": j["id"], "name": j["name"], "conclusion": j["conclusion"],
                 "steps": [{"name": s["name"], "conclusion": s["conclusion"]} for s in j.get("steps") or []]}
                for j in c["jobs"]]
        fail = [j for j in jobs if j["conclusion"] == "failure"]
        target = next((j for j in fail if j["id"] == c.get("job_id")), fail[0] if len(fail) == 1 else None)
        for j in jobs:
            j.pop("log", None)
        if target is None:
            print(c["case"], "không xác định được job lỗi", flush=True)
            continue
        jobs = [j for j in jobs if j["conclusion"] != "failure" or j is target]  # chỉ job có log trong benchmark
        log = c["log"].lstrip("﻿")
        if len(log) > LOG_TAIL:
            log = log[-LOG_TAIL:].split("\n", 1)[-1]
        target["log"], target["picked"] = log, True
        rec = {"repo": c["repo"], "run_id": c["run_id"], "url": f"https://github.com/{c['repo']}/actions/runs/{c['run_id']}",
               "workflow": "", "event": c["event"], "head_sha": c["head_sha"], "conclusion": "failure", "jobs": jobs,
               "diff": diff_stats(gh, c["repo"], {"event": c["event"], "head_sha": c["head_sha"]})}
        meta = {k: c[k] for k in ("case", "src", "labels", "fix_files", "extra")}
        meta["picked_ok"] = bool(pick_jobs(jobs, 2))
        f.write_text(json.dumps({"rec": rec, "meta": meta}), encoding="utf-8")
        print(c["case"], "ok", flush=True)


def predict(url: str) -> None:
    from gradio_client import Client
    cli = Client(url, verbose=False)
    (OUT / "pred").mkdir(parents=True, exist_ok=True)
    for f in sorted((OUT / "recs").glob("*.json")):
        out = OUT / "pred" / f.name
        if out.exists():
            continue
        rec = json.loads(f.read_text(encoding="utf-8"))["rec"]
        md, log, agent_in, o = cli.predict(json.dumps(rec), api_name="/predict_record")
        out.write_text(json.dumps({"o": o, "agent_in": agent_in, "md": md}, ensure_ascii=False), encoding="utf-8")
        print(f.stem, (o.get("pred") or {}).get("leaf"), len(o.get("cause_lines") or []), flush=True)


def evaluate() -> None:
    rows = []
    for f in sorted((OUT / "pred").glob("*.json")):
        p = json.loads(f.read_text(encoding="utf-8"))
        meta = json.loads((OUT / "recs" / f.name).read_text(encoding="utf-8"))["meta"]
        c = next(x for x in cases() if x["case"] == f.stem)
        raw = c["log"].lstrip("﻿").splitlines()
        lab = {norm(raw[i - 1]) for i in meta["labels"] if i <= len(raw)} - {""}
        hit = lambda t: bool(norm(t)) and norm(t) in lab
        o = p["o"]
        if "error" in o or not o.get("cause_lines"):
            rows.append(dict(case=f.stem, src=meta["src"], ok=False))
            continue
        nonempty = [x for x in raw if norm(x)]
        tail = nonempty[-N:][::-1]
        grep = [x for x in nonempty if GREP.search(x) and not x.lstrip("﻿").split("Z ", 1)[-1].startswith("##[group]")]
        grep = grep[-N:][::-1]
        blocks = {norm(t) for b in o.get("cause_blocks", []) for t, _ in b["lines"]}
        r = dict(case=f.stem, src=meta["src"], ok=True, leaf=o["pred"]["leaf"], n_lab=len(lab), log_k=len("\n".join(raw)) / 1e3,
                 blocks_k=len(p["agent_in"]) / 1e3, cover=len(lab & blocks) / len(lab) if lab else None)
        for k, ls in (("cause", [x["text"] for x in o["cause_lines"]]), ("attn", [x["text"] for x in o["lines"]]),
                      ("tail", tail), ("grep", grep)):
            r[f"{k}1"], r[f"{k}5"] = hit(ls[0]) if ls else False, any(hit(x) for x in ls[:N])
        rows.append(r)
    d = pd.DataFrame(rows)
    d.to_csv(OUT / "extract_eval.csv", index=False)
    ok = d[d.ok]
    print(f"{len(d)} lỗi, mô hình trả kết quả {len(ok)}; số dòng người gán (sau chuẩn hoá) trung vị {ok.n_lab.median()}")
    cols = ["cause1", "cause5", "attn1", "attn5", "tail1", "tail5", "grep1", "grep5"]
    print(ok.groupby("src")[cols].mean().round(2).to_string())
    print("tất cả:", ok[cols].mean().round(2).to_dict())
    print(f"phủ dòng người gán bởi khối ±5 dòng: TB {ok.cover.mean():.2f}, lỗi có ≥1 dòng: {(ok.cover > 0).mean():.2f}")
    print(f"độ dài: log đầy đủ trung vị {ok.log_k.median():.0f}k ký tự, đầu vào agent cách 4 trung vị {ok.blocks_k.median():.1f}k")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    {"build": build, "predict": lambda: predict(sys.argv[2]), "eval": evaluate}[sys.argv[1]]()
