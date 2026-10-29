"""Crawl đợt 3 (22/10/2026): chỉ run FAIL của các workflow chọn bởi probe_rare (nhắm lá tầng 3 hiếm).

Ghi đúng định dạng của crawl.gha vào data/crawl_pr (pull_request) và data/validate (push, nhánh chính) nên các bước
gold_labels -> build_log_labels -> fine_labels -> run_dataset dùng được ngay. Cùng quy ước với crawl_100: PR tải log
tối đa 2 job fail/run (ưu tiên job giai đoạn sớm), nhánh chính tối đa 4 (crawl_100: mọi job). Khác crawl_100 nữa: run schedule /
workflow_dispatch trên nhánh chính cũng được lấy (vào data/validate, trường event giữ nguyên) vì nhiều kiểm tra
javadoc/license/compatibility chỉ chạy định kỳ. Không lấy run thành công (bài toán là phân
loại run fail), nên repo mới của đợt này mang `scope: targeted-r3` trong crawl_status.json; phạm vi từng repo ghi ở
targeted_r3.json. Dữ liệu lệch về lá hiếm có chủ đích -> khi đánh giá cần tách theo đợt (repo đợt 3 = danh sách targets).

    python -m project3.pipeline.crawl_targeted --targets configs/targets_r3.jsonl --max-runs 400
"""
import argparse
import gzip
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from project3.crawl.gha import (FULL_TAIL_BYTES, LOG_WORKERS, append, crawl_lock, error_context, log, pick_jobs,
                                read_ids, run_row)
from project3.crawl.github import GitHub, load_token

ROOTS = {"pull_request": Path("data/crawl_pr"), "push": Path("data/validate")}
BRANCHES = {"master", "main", "trunk", "develop"}  # như crawl_100 cho push
MAIN_EVENTS = {"push", "schedule", "workflow_dispatch"}
SCOPE = "targeted-r3"  # đổi bằng --scope (đợt android: targeted-android)


def failed_runs(gh: GitHub, repo: str, wf_id: int, since: str, max_runs: int) -> list[dict]:
    """Run fail mới nhất trước, tối đa max_runs (API trả tối đa 1000 cho một bộ lọc)."""
    out, page = [], 1
    while len(out) < max_runs and page <= 10:
        data = gh.get(f"/repos/{repo}/actions/workflows/{wf_id}/runs", status="failure", created=f">={since}",
                      per_page=100, page=page)
        out += data["workflow_runs"]
        if len(data["workflow_runs"]) < 100:
            break
        page += 1
    return out[:max_runs]


def fetch_log(gh: GitHub, repo: str, log_dir: Path, job_id: int) -> None:
    """Như crawl.gha: đuôi dài .tail.txt.gz ghi trước, .txt (error_context) tồn tại = job đã xong."""
    text = gh.get_log_tail(f"/repos/{repo}/actions/jobs/{job_id}/logs")
    if text is None:
        (log_dir / f"{job_id}.missing").touch()
        return
    tail_part = log_dir / f"{job_id}.tail.part"
    tail_part.write_bytes(gzip.compress(text.encode("utf-8")[-FULL_TAIL_BYTES:], compresslevel=6))
    tail_part.replace(log_dir / f"{job_id}.tail.txt.gz")
    part = log_dir / f"{job_id}.txt.part"
    part.write_text(error_context(text), encoding="utf-8")
    part.replace(log_dir / f"{job_id}.txt")


def crawl_event(gh: GitHub, repo: str, event: str, runs: list[dict], workflows: list[dict]) -> dict:
    out = ROOTS[event] / repo.replace("/", "__")
    out.mkdir(parents=True, exist_ok=True)
    status_path = out / "crawl_status.json"
    if not status_path.exists():  # repo mới của đợt 3; repo đã crawl đủ thì giữ nguyên trạng thái cũ
        status_path.write_text(json.dumps({"event": event, "status": "running", "scope": SCOPE}), encoding="utf-8")
        (out / "workflows.json").write_text(json.dumps(workflows, ensure_ascii=False, indent=1), encoding="utf-8")
    runs_path, jobs_path = out / "runs.jsonl", out / "jobs.jsonl"
    seen = read_ids(runs_path)
    new = [run_row(r) for r in runs if r["id"] not in seen]
    append(runs_path, new)
    done = read_ids(jobs_path, "run_id")
    todo = [r for r in runs if r["id"] not in done]
    for r in todo:
        try:
            data = gh.get(f"/repos/{repo}/actions/runs/{r['id']}/jobs", per_page=100, filter="latest")
        except requests.HTTPError as e:
            if e.response is None or e.response.status_code != 404:
                raise
            data = {"jobs": []}
        jobs = [{"id": j["id"], "name": j["name"], "conclusion": j["conclusion"],
                 "steps": [{"name": s["name"], "conclusion": s["conclusion"], "number": s["number"]}
                           for s in j.get("steps") or []]} for j in data["jobs"]]
        append(jobs_path, [{"run_id": r["id"], "jobs": jobs}])
    want = {r["id"] for r in runs}
    rows = [json.loads(l) for l in jobs_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    log_dir = out / "logs"
    log_dir.mkdir(exist_ok=True)
    limit = 2 if event == "pull_request" else 4  # crawl_100 lấy mọi job cho push; matrix lớn tốn hạn mức
    jobs = [j["id"] for row in rows if row["run_id"] in want for j in pick_jobs(row["jobs"], limit)]
    jobs = [j for j in jobs if not (log_dir / f"{j}.txt").exists() and not (log_dir / f"{j}.missing").exists()]
    errors = 0
    with ThreadPoolExecutor(max_workers=LOG_WORKERS) as pool:
        for f in as_completed([pool.submit(fetch_log, gh, repo, log_dir, j) for j in jobs]):
            try:
                f.result()
            except Exception as e:
                errors += 1
                log(f"[{repo}] LỖI log: {type(e).__name__}")
    scope_path = out / (SCOPE.replace("-", "_") + ".json")
    scope = json.loads(scope_path.read_text(encoding="utf-8")) if scope_path.exists() else {"workflows": {}}
    for w in workflows:
        scope["workflows"][str(w["id"])] = {**w, "failed_runs": sum(r["workflow_id"] == w["id"] for r in runs)}
    scope["updated_at"] = datetime.now(timezone.utc).isoformat()
    scope_path.write_text(json.dumps(scope, ensure_ascii=False, indent=1), encoding="utf-8")
    st = json.loads(status_path.read_text(encoding="utf-8"))
    if st.get("scope") == SCOPE:
        st.update(status="failed" if errors else "completed", updated_at=scope["updated_at"])
        status_path.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    if errors:
        raise RuntimeError(f"{errors} log tải lỗi, chạy lại để thử tiếp")
    return {"runs": len(runs), "new_runs": len(new), "logs": len(jobs)}


def main(targets: Path, days: int, max_runs: int, done_path: Path, budget_min: float = 0) -> None:
    t0 = time.time()
    rows = [json.loads(l) for l in targets.open(encoding="utf-8") if l.strip()]
    by_repo = {}
    for r in rows:
        by_repo.setdefault(r["repository"], []).append(r)
    done = {json.loads(l)["repository"] for l in done_path.open(encoding="utf-8")} if done_path.exists() else set()
    gh = GitHub(load_token())
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    todo = [r for r in by_repo if r not in done]
    log(f"{len(by_repo)} repo / {len(rows)} workflow, còn {len(todo)} repo")
    for i, repo in enumerate(todo, 1):
        if budget_min and time.time() - t0 > budget_min * 60:  # dừng giữa hai repo; repo chưa xong chạy lại sau
            log(f"Hết ngân sách {budget_min:.0f} phút, còn {len(todo) - i + 1} repo")
            break
        wfs = [{"id": t["workflow_id"], "name": t["name"], "path": t["path"]} for t in by_repo[repo]]
        try:
            runs = [r for w in wfs for r in failed_runs(gh, repo, w["id"], since, max_runs)]
            res = {}
            for event, root in ROOTS.items():
                # run định kỳ / chạy tay trên nhánh chính đi cùng push (giữ trường event gốc trong runs.jsonl)
                if event == "pull_request":
                    ev = [r for r in runs if r["event"] == "pull_request"]
                else:
                    ev = [r for r in runs if r["event"] in MAIN_EVENTS and r["head_branch"] in BRANCHES]
                if ev:
                    with crawl_lock(str(root / repo.replace("/", "__"))):
                        res[event] = crawl_event(gh, repo, event, ev, wfs)
            with done_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"repository": repo, **res, "at": datetime.now(timezone.utc).isoformat()}) + "\n")
            log(f"[{i}/{len(todo)}] {repo}: {res} (remaining={gh.remaining})")
        except Exception as e:  # repo lỗi không dừng cả lượt; chạy lại sẽ thử tiếp
            log(f"[{i}/{len(todo)}] {repo}: LỖI {type(e).__name__}: {str(e)[:150]}")
    log("Xong.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", type=Path, default=Path("configs/targets_r3.jsonl"))
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--max-runs", type=int, default=400, help="tối đa số run fail mỗi workflow")
    ap.add_argument("--done", type=Path, default=Path("data/processed/crawl_targeted_r3_done.jsonl"))
    ap.add_argument("--budget-min", type=float, default=0, help="không bắt đầu repo mới sau N phút (0 = không giới hạn)")
    ap.add_argument("--scope", default=SCOPE, help="nhãn đợt ghi vào crawl_status.json của repo mới")
    a = ap.parse_args()
    SCOPE = a.scope
    main(a.targets, a.days, a.max_runs, a.done, a.budget_min)
