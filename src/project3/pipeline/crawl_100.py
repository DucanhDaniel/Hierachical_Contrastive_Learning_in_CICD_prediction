"""Worker tuần tự cho task 100 repo: PR trước push, checkpoint và hạn chót VN.

    python -m project3.pipeline.crawl_100
Chạy lại để tiếp tục; kết quả từng repo đã hoàn tất được giữ.
"""
import ctypes
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from project3.crawl.gha import crawl_lock
    
DEADLINE = datetime.fromisoformat("2026-10-14T22:00:00+07:00")
MIDPOINT = datetime.fromisoformat("2026-10-12T22:00:00+07:00")
STATE = Path("data/crawl_100_state.json")
RESULTS = Path("data/crawl_100_results.json")


def now():
    return datetime.now(timezone.utc)


def save(path, value):
    partial = path.with_suffix(path.suffix + ".part")
    partial.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    # Windows có thể từ chối replace khi reader/antivirus đang giữ file đích.
    for attempt in range(5):
        try:
            partial.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.2 * 2 ** attempt)


_SAVE_WARNINGS = set()


def save_snapshot(path, value):
    """State/index là thông tin giám sát; lỗi ghi không được giết crawler con."""
    try:
        save(path, value)
    except OSError as exc:
        if path not in _SAVE_WARNINGS:
            print(f"WARNING: cannot save {path}: {type(exc).__name__}; continuing from data checkpoints", flush=True)
            _SAVE_WARNINGS.add(path)
        return False
    _SAVE_WARNINGS.discard(path)
    return True


def load_results(path):
    # .part đầy đủ có thể mới hơn file chính nếu replace bị khóa; không bỏ kết quả đã xong.
    candidates = [p for p in (path, path.with_suffix(path.suffix + ".part")) if p.exists()]
    for candidate in sorted(candidates, key=lambda p: p.stat().st_mtime_ns, reverse=True):
        try:
            value = json.loads(candidate.read_text(encoding="utf-8-sig"))
            if not isinstance(value, dict):
                raise ValueError("Results must be an object")
            return value
        except (ValueError, OSError) as exc:
            print(f"WARNING: cannot read {candidate}: {type(exc).__name__}", flush=True)
    if candidates:
        raise RuntimeError("No valid results snapshot; original files retained for inspection")
    return {}


def stop_child(proc):
    if proc.poll() is not None:
        return
    if os.name == "nt":
        # python.exe trong venv Windows có thể là launcher tạo thêm process Python.
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        proc.terminate()
    proc.wait(timeout=30)


def wait_child(proc, heartbeat, deadline=False):
    while proc.poll() is None:
        heartbeat()
        if deadline and now() >= DEADLINE:
            stop_child(proc)
            return None
        time.sleep(5)
    return proc.returncode


def main():
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONUNBUFFERED"] = "1"
    Path("data/logs").mkdir(parents=True, exist_ok=True)
    repos = [l.strip() for l in Path("configs/repos_100.txt").read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.startswith("#")]
    if len(repos) != len(set(repos)):
        raise ValueError("Duplicate repositories in task list")
    # Cùng một lock cho supervisor; không khởi chạy lượt thứ hai khi worker còn sống.
    with crawl_lock("data/.crawl_100_supervisor"):
        Path("data/crawl_100.pid").write_text(str(os.getpid()), encoding="ascii")
        results = load_results(RESULTS)
        state = {"pid": os.getpid(), "started": now().isoformat(), "total_repos": len(repos),
                 "deadline": DEADLINE.isoformat(), "midpoint": MIDPOINT.isoformat(), "days": 90}
        awake = False
        if os.name == "nt":
            awake = bool(ctypes.windll.kernel32.SetThreadExecutionState(0x80000001))
        state["keep_awake"] = awake

        def update(stage, status, **extra):
            state.update(stage=stage, status=status, updated=now().isoformat(), **extra)
            state["pr_completed"] = sum(results.get(f"pull_request|{r}", {}).get("status") == "completed" for r in repos)
            state["push_completed"] = sum(results.get(f"push|{r}", {}).get("status") == "completed" for r in repos)
            save_snapshot(STATE, state)

        def run(args, logpath, deadline=False):
            with logpath.open("a", encoding="utf-8") as log:
                proc = subprocess.Popen([sys.executable, "-u", "-m", *args], stdout=log, stderr=log)
                state["child_pid"] = proc.pid
                try:
                    return wait_child(proc, lambda: update(state["stage"], "running"), deadline)
                finally:
                    if proc.poll() is None:
                        stop_child(proc)
                    state["child_pid"] = None

        try:
            update("checkpoint", "running", repo=None)
            if run(["project3.crawl.checkpoint", "--repair"], Path("data/logs/crawl_100_supervisor.log")) != 0:
                raise RuntimeError("Checkpoint repair failed; do not crawl")
            stopped = False
            for event, root, stage in [("pull_request", "data/crawl_pr", "T1-pr"), ("push", "data/validate", "T2-push")]:
                # Lượt đầu theo đúng thứ tự file; sau đó thử lại repo failed tối đa một lượt.
                for attempt in range(2):
                    for repo in repos:
                        key = f"{event}|{repo}"
                        if results.get(key, {}).get("status") == "completed":
                            continue
                        if now() >= DEADLINE:
                            stopped = True
                            break
                        done = sum(results.get(f"pull_request|{r}", {}).get("status") == "completed" for r in repos)
                        if now() >= MIDPOINT and done < (len(repos) + 1) // 2:
                            state["days"] = 60
                        # Không mở rộng lại cửa sổ đã giảm khi resume.
                        days = min(state["days"], results.get(key, {}).get("days", 90))
                        update(stage, "running", repo=repo, event=event, days=days, attempt=attempt + 1)
                        print(f"{now().isoformat()} {stage} {repo}, days={days}, attempt={attempt + 1}", flush=True)
                        args = ["project3.crawl.gha", "--repos", repo, "--event", event, "--root", root,
                                "--days", str(days), "--max-logs", "50000"]
                        if event == "pull_request":
                            args += ["--max-jobs-per-run", "2"]
                        else:
                            args += ["--branches", "master", "main", "trunk", "develop"]
                        code = run(args, Path(f"data/crawl_100_{'pr' if event == 'pull_request' else 'push'}.log"), deadline=True)
                        status_path = Path(root) / repo.replace("/", "__") / "crawl_status.json"
                        try:
                            status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
                        except (ValueError, OSError):
                            status = {}
                        if code is None:
                            status.update(status="interrupted", updated_at=now().isoformat())
                            save_snapshot(status_path, status)
                            stopped = True
                        elif code != 0:
                            status.update(status="failed", error_type=f"ProcessExit{code}")
                        elif status.get("status") not in ("completed", "failed"):
                            # Exit 0 không đủ chứng minh repo đã xong khi status thiếu/hỏng.
                            status.update(status="failed", error_type="MissingCompletionStatus")
                        results[key] = {**status, "days": days, "finished": now().isoformat()}
                        save_snapshot(RESULTS, results)
                        if stopped:
                            break
                    if stopped:
                        break
                if stopped:
                    break
            update("T3-T4-labels", "running", repo=None, stopped_at_deadline=stopped)
            log = Path("data/logs/crawl_100_supervisor.log")
            if run(["project3.crawl.checkpoint", "--repair"], log) != 0:
                raise RuntimeError("Final checkpoint failed")
            if run(["project3.pipeline.relabel"], log) != 0:
                raise RuntimeError("Relabel failed; original dataset backups retained")
            # Rule mới/độ phủ/nhãn ? của repo mới còn cần review; không tuyên bố dataset đạt gate.
            update("T5-coverage-and-new-rules-review", "needs_review", repo=None)
        except BaseException as exc:
            update(state.get("stage", "error"), "failed", error_type=type(exc).__name__)
            raise
        finally:
            if awake:
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


if __name__ == "__main__":
    main()
