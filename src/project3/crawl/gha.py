"""Crawl GitHub Actions: workflow CI → run → job/step (run fail) → log (job fail, chỉ giữ đoạn quanh ##[error]).

Dữ liệu lưu ở <root>/<owner>__<repo>/ dạng JSONL, chạy lại sẽ bỏ qua phần đã có (chạy định kỳ để tích lũy,
vì GitHub chỉ giữ log 90 ngày).

    uv run python -m project3.crawl.gha --repos apache/kafka --days 90 --event push --branches master main trunk
    uv run python -m project3.crawl.gha --repos-file data/repos.txt --days 90 --event pull_request \
        --max-jobs-per-run 2 --root data/crawl_pr
"""
import argparse
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
import errno
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .github import GitHub, load_token


def log(msg: str) -> None:
    """In kèm giờ, flush ngay để theo dõi được qua file log."""
    print(f"{datetime.now():%H:%M:%S} {msg}", flush=True)

# Workflow không phải build/test (bot, label, release, docs...)
EXCLUDE = re.compile(
    r"label|bot|stale|welcome|claude|copilot|dependabot|release|publish|deploy|docs|pages|backport|milestone|"
    r"notif|sbom|showtime|fossa|codeql|allowlist|tech.?debt|translation|assistant|recheck|comment|approve|"
    r"mirror|refresh|sync|registry|constraints|cache|calendar|monitor|report|upload|merge conflict|hold",
    re.I)
# Job chỉ tổng hợp kết quả các job khác -> log không chứa nguyên nhân lỗi
AGG_JOB = re.compile(r"CI result|checks? completed|-required|required checks|all checks|ci success|gate$", re.I)
# Tên step/job gợi ý lỗi ở giai đoạn sớm (compile/lint/dependency) -> ưu tiên tải log trước
EARLY_STAGE = re.compile(r"compil|build|lint|checkstyle|spotless|format|\brat\b|license|style|install|dependenc", re.I)
LOG_WORKERS = 8
LOG_TAIL_LINES = 150
LOG_BEFORE_ERROR = 80
API_CAP = 1000  # API list run trả tối đa 1000 kết quả cho một bộ lọc -> phải chia nhỏ khoảng thời gian


@contextmanager
def crawl_lock(root: str):
    """Khóa root giữa các tiến trình; hệ điều hành tự nhả khóa khi tiến trình dừng."""
    path = Path(root)
    path.mkdir(parents=True, exist_ok=True)
    with (path / '.crawl.lock').open('a+b') as f:
        if f.seek(0, 2) == 0:
            f.write(b'0')
            f.flush()
        if os.name == 'nt':
            import msvcrt

            def acquire():
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)

            def release():
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            def acquire():
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

            def release():
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        waiting = False
        while True:
            try:
                acquire()
                break
            except OSError as e:
                if e.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                if not waiting:
                    log(f'Chờ crawler khác nhả khóa root {path}')
                    waiting = True
                time.sleep(5)
        if waiting:
            log(f'Đã lấy khóa root {path}, tiếp tục crawl')
        try:
            yield
        finally:
            release()


def error_context(text: str) -> str:
    """Giữ đoạn log quanh các dòng ##[error] (GitHub đánh dấu lỗi); không có thì lấy phần cuối."""
    lines = text.splitlines()
    err = [i for i, line in enumerate(lines) if "##[error]" in line]
    if not err:
        return "\n".join(lines[-LOG_TAIL_LINES:])
    return "\n".join(lines[max(0, err[0] - LOG_BEFORE_ERROR): err[-1] + 5])


def ci_workflows(gh: GitHub, repo: str) -> list[dict]:
    wfs = gh.get(f"/repos/{repo}/actions/workflows", per_page=100)["workflows"]
    keep = [w for w in wfs if w["state"] == "active" and not w["path"].startswith("dynamic/")
            and not EXCLUDE.search(w["name"] + " " + w["path"])]
    return keep


def read_ids(path: Path, key: str = "id") -> set:
    if not path.exists():
        return set()
    return {json.loads(line)[key] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def append(path: Path, rows: list[dict]) -> None:
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


RUN_FIELDS = ("id", "workflow_id", "name", "event", "head_branch", "head_sha", "conclusion", "run_attempt",
              "run_number", "created_at", "updated_at", "run_started_at")


def run_row(r: dict) -> dict:
    row = {k: r.get(k) for k in RUN_FIELDS}
    # PR: repo nguồn (fork) + số PR (rỗng nếu PR từ fork) để gom các commit cùng một PR và lấy diff sau này
    row["head_repository"] = (r.get("head_repository") or {}).get("full_name")
    row["pull_requests"] = [p["number"] for p in r.get("pull_requests") or []]
    return row


def list_runs(gh: GitHub, repo: str, wf_id: int, start: datetime, end: datetime, event: str | None,
              max_pages: int) -> list[dict]:
    """Mọi run completed tạo trong [start, end); tự chia đôi khoảng thời gian khi vượt trần 1000 kết quả."""
    rng = f"{start:%Y-%m-%dT%H:%M:%SZ}..{end - timedelta(seconds=1):%Y-%m-%dT%H:%M:%SZ}"
    params = dict(status="completed", created=rng, per_page=100)
    if event:
        params["event"] = event
    url = f"/repos/{repo}/actions/workflows/{wf_id}/runs"
    first = gh.get(url, page=1, **params)
    if first["total_count"] > API_CAP and end - start > timedelta(hours=1):
        mid = start + (end - start) / 2
        return list_runs(gh, repo, wf_id, start, mid, event, max_pages) + list_runs(gh, repo, wf_id, mid, end, event, max_pages)
    out = list(first["workflow_runs"])
    page = 1
    while len(out) < first["total_count"] and page < max_pages:
        page += 1
        data = gh.get(url, page=page, **params)
        if not data["workflow_runs"]:
            break
        out += data["workflow_runs"]
    return out


def pick_jobs(jobs: list[dict], limit: int) -> list[dict]:
    """Job fail cần tải log: bỏ job tổng hợp, ưu tiên job giai đoạn sớm (lỗi compile/lint che mất lỗi test)."""
    fail = [j for j in jobs if j["conclusion"] == "failure" and not AGG_JOB.search(j["name"])]

    def late(j: dict) -> bool:
        steps = " ".join(s["name"] for s in j["steps"] if s["conclusion"] == "failure")
        return not EARLY_STAGE.search(steps or j["name"])
    fail.sort(key=late)
    return fail[:limit] if limit else fail


def crawl_repo(gh: GitHub, repo: str, days: int, max_pages: int, logs: bool, max_logs: int,
               event: str | None = None, branches: list[str] | None = None, root: str = "data/raw",
               max_jobs_per_run: int = 0, window_days: int = 7) -> None:
    out = Path(root) / repo.replace("/", "__")
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    since = now - timedelta(days=days)

    wfs = ci_workflows(gh, repo)
    (out / "workflows.json").write_text(json.dumps(
        [{k: w[k] for k in ("id", "name", "path")} for w in wfs], ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"[{repo}] {len(wfs)} workflow CI: {[w['name'] for w in wfs]}")

    # 1) run: từng cửa sổ window_days ngày, ghi ngay sau mỗi cửa sổ để dừng giữa chừng vẫn giữ được
    runs_path = out / "runs.jsonl"
    runs_path.touch(exist_ok=True)
    seen = read_ids(runs_path)
    for w in wfs:
        new = 0
        start = since
        while start < now:
            end = min(now, start + timedelta(days=window_days))
            batch = [run_row(r) for r in list_runs(gh, repo, w["id"], start, end, event, max_pages)
                     if r["id"] not in seen and (not branches or r["head_branch"] in branches)]
            append(runs_path, batch)
            seen |= {r["id"] for r in batch}
            new += len(batch)
            start = end
        log(f"  {w['name']}: +{new} run (remaining={gh.remaining})")

    # 2) job/step cho run fail
    runs = [json.loads(l) for l in runs_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    failed = [r for r in runs if r["conclusion"] == "failure"]
    jobs_path = out / "jobs.jsonl"
    jobs_path.touch(exist_ok=True)
    done = read_ids(jobs_path, "run_id")
    todo = [r for r in failed if r["id"] not in done]
    log(f"  run fail: {len(failed)}, cần lấy job: {len(todo)}")
    for i, r in enumerate(todo, 1):
        data = gh.get(f"/repos/{repo}/actions/runs/{r['id']}/jobs", per_page=100, filter="latest")
        jobs = [{"id": j["id"], "name": j["name"], "conclusion": j["conclusion"],
                 "steps": [{"name": s["name"], "conclusion": s["conclusion"], "number": s["number"]}
                           for s in j.get("steps") or []]} for j in data["jobs"]]
        append(jobs_path, [{"run_id": r["id"], "jobs": jobs}])
        if i % 50 == 0 or i == len(todo):
            log(f"    job {i}/{len(todo)} (remaining={gh.remaining})")

    # 3) log của job fail (chỉ giữ đoạn quanh lỗi)
    if not logs:
        return
    log_dir = out / "logs"
    log_dir.mkdir(exist_ok=True)
    rows = [json.loads(l) for l in jobs_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    fail_jobs = [j for row in rows for j in pick_jobs(row["jobs"], max_jobs_per_run)]
    todo = [j for j in fail_jobs if not (log_dir / f"{j['id']}.txt").exists() and not (log_dir / f"{j['id']}.missing").exists()]
    todo = todo[:max_logs]
    log(f"  job fail cần log: {len(fail_jobs)}, lấy log lần này: {len(todo)}")

    def fetch(j: dict) -> None:
        text = gh.get_log_tail(f"/repos/{repo}/actions/jobs/{j['id']}/logs")
        if text is None:
            (log_dir / f"{j['id']}.missing").touch()
        else:
            target = log_dir / f"{j['id']}.txt"
            partial = target.with_suffix('.txt.part')
            partial.write_text(error_context(text), encoding="utf-8")
            partial.replace(target)

    # tải song song: giới hạn tốc độ là theo từng kết nối tới kho log
    with ThreadPoolExecutor(max_workers=LOG_WORKERS) as pool:
        futures = {pool.submit(fetch, j): j['id'] for j in todo}
        errors = 0
        for i, future in enumerate(as_completed(futures), 1):
            try:
                future.result()
            except Exception as e:
                errors += 1
                log(f"[{repo}] LỖI log job {futures[future]}: {type(e).__name__}; chưa đánh dấu hoàn tất")
            if i % 50 == 0 or i == len(todo):
                log(f"    log {i}/{len(todo)} (remaining={gh.remaining})")
        if errors:
            raise RuntimeError(f'{errors} log tải lỗi, cần chạy tiếp để thử lại')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos", nargs="+", default=[])
    ap.add_argument("--repos-file", action="append", default=[],
                    help="file danh sách repo, mỗi dòng một repo (bỏ dòng trống / dòng #); dùng được nhiều lần")
    ap.add_argument("--days", type=int, default=30, help="lấy run tạo trong N ngày gần nhất")
    ap.add_argument("--window-days", type=int, default=7, help="độ dài mỗi cửa sổ thời gian khi list run")
    ap.add_argument("--max-pages", type=int, default=10, help="tối đa số trang (100 run) mỗi workflow mỗi cửa sổ")
    ap.add_argument("--no-logs", action="store_true")
    ap.add_argument("--max-logs", type=int, default=300, help="tối đa số log job fail tải mỗi repo mỗi lần chạy")
    ap.add_argument("--max-jobs-per-run", type=int, default=0,
                    help="số job fail tối đa tải log mỗi run (0 = tất cả); ưu tiên job compile/lint")
    ap.add_argument("--event", help="chỉ lấy run của event này, vd. push, pull_request")
    ap.add_argument("--branches", nargs="*", help="chỉ giữ run trên các nhánh này, vd. master main trunk (chỉ dùng với push)")
    ap.add_argument("--root", default="data/raw", help="thư mục lưu dữ liệu")
    a = ap.parse_args()
    token = load_token()
    if not token:
        raise SystemExit("Không thấy GITHUB_ACCESS_TOKEN trong .env")
    repos = list(a.repos)
    for f in a.repos_file:
        repos += [l.strip() for l in Path(f).read_text(encoding="utf-8").splitlines()
                  if l.strip() and not l.startswith("#")]
    if not repos:
        raise SystemExit("Cần --repos hoặc --repos-file")
    gh = GitHub(token)
    for repo in repos:
        with crawl_lock(str(Path(a.root) / repo.replace('/', '__'))):
            try:
                crawl_repo(gh, repo, a.days, a.max_pages, not a.no_logs, a.max_logs, a.event, a.branches, a.root,
                           a.max_jobs_per_run, a.window_days)
            except Exception as e:  # một repo lỗi (đổi tên, tắt Actions...) không làm dừng cả lượt crawl
                log(f"[{repo}] LỖI {type(e).__name__}: {e}")
    log("Xong.")


if __name__ == "__main__":
    main()
