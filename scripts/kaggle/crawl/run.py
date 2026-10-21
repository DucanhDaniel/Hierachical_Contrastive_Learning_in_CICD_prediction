"""Kernel Kaggle (CPU) cho task crawl 100 repo: chạy project3.crawl.gha y như crawl_100 trên máy, PR trước push sau.

Đầu vào: dataset ducanhpham2k5/p3-crawl-state do `python -m project3.pipeline.kaggle_crawl prepare` tạo
(gha.py, github.py, checkpoint.py, repos.txt, results.json, crawl_config.json, state.dat = repo đang dở).
Token GitHub: gh_token.txt trong dataset private ducanhpham2k5/p3-gh-token, nếu không có thì Kaggle Secrets.
Đầu ra (/kaggle/working): crawl_out.tar.gz (data/crawl_pr|validate/<repo>/...), results.json, summary.json, runner.log.
Tự dừng khi hết budget_minutes để còn thời gian đóng gói trước giới hạn 12 giờ của Kaggle.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

T0 = time.time()
src = Path(glob.glob("/kaggle/input/**/crawl_config.json", recursive=True)[0]).parent
cfg = json.loads((src / "crawl_config.json").read_text(encoding="utf-8"))
work = Path("/kaggle/working")
os.chdir(work)
LOG = (work / "runner.log").open("a", encoding="utf-8")


def log(msg):
    line = f"{datetime.now(timezone.utc):%H:%M:%S} {msg}"
    print(line, flush=True)
    LOG.write(line + "\n")
    LOG.flush()


def now():
    return datetime.now(timezone.utc)


BUDGET = cfg["budget_minutes"] * 60
DEADLINE = datetime.fromisoformat(cfg["deadline"])
MIDPOINT = datetime.fromisoformat(cfg["midpoint"])

# Mã crawler dùng nguyên bản từ repo, đặt vào package tạm (không nằm trong output)
pkg = Path("/tmp/pkg/project3/crawl")
pkg.mkdir(parents=True, exist_ok=True)
for f in ("gha.py", "github.py", "checkpoint.py"):
    shutil.copy(src / f, pkg)
for d in (pkg, pkg.parent):
    (d / "__init__.py").touch()

GH_TOKEN = ""  # dán token vào đây trên editor Kaggle (không điền trong repo)


def github_token():
    """Ưu tiên GH_TOKEN, rồi dataset private p3-gh-token, cuối cùng Kaggle Secrets (chỉ dùng được khi chạy từ web)."""
    if GH_TOKEN:
        return GH_TOKEN
    files = glob.glob("/kaggle/input/**/gh_token.txt", recursive=True)
    if files:
        return Path(files[0]).read_text(encoding="utf-8").strip()
    from kaggle_secrets import UserSecretsClient
    return UserSecretsClient().get_secret("GITHUB_ACCESS_TOKEN")


env = {**os.environ, "PYTHONPATH": "/tmp/pkg", "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1",
       "GITHUB_ACCESS_TOKEN": github_token()}

if (src / "state.dat").exists():
    with tarfile.open(src / "state.dat") as tar:
        tar.extractall(work, filter="data")
repos = [l.strip() for l in (src / "repos.txt").read_text(encoding="utf-8").splitlines()
         if l.strip() and not l.startswith("#")]
results = json.loads((src / "results.json").read_text(encoding="utf-8"))
Path("data/logs").mkdir(parents=True, exist_ok=True)
log(f"repos={len(repos)} done={sum(v.get('status') == 'completed' for v in results.values())} "
    f"budget={cfg['budget_minutes']}min")


def save_results():
    (work / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


def out_of_time():
    return time.time() - T0 >= BUDGET or now() >= DEADLINE


def run(args, logpath):
    """Chạy module con; None nếu phải dừng vì hết budget/hạn chót."""
    with open(logpath, "a", encoding="utf-8") as f:
        proc = subprocess.Popen([sys.executable, "-u", "-m", *args], stdout=f, stderr=f, env=env)
        while proc.poll() is None:
            if out_of_time():
                proc.terminate()
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                return None
            time.sleep(5)
        return proc.returncode


try:
    stopped = False
    for event, root, short in [("pull_request", "data/crawl_pr", "pr"), ("push", "data/validate", "push")]:
        for attempt in range(2):  # lượt đầu theo thứ tự file, sau đó thử lại repo failed một lượt
            for repo in repos:
                key = f"{event}|{repo}"
                if results.get(key, {}).get("status") == "completed":
                    continue
                if out_of_time():
                    stopped = True
                    break
                days = cfg["days"]
                done = sum(results.get(f"pull_request|{r}", {}).get("status") == "completed" for r in repos)
                if now() >= MIDPOINT and done < (len(repos) + 1) // 2:
                    days = 60
                days = min(days, results.get(key, {}).get("days", days))
                log(f"{short} {repo} days={days} attempt={attempt + 1}")
                args = ["project3.crawl.gha", "--repos", repo, "--event", event, "--root", root,
                        "--days", str(days), "--max-logs", "50000"]
                args += ["--max-jobs-per-run", "2"] if event == "pull_request" else \
                        ["--branches", "master", "main", "trunk", "develop"]
                if attempt or results.get(key, {}).get("status") == "failed":
                    # repo lớn: truy vấn list run cửa sổ 7 ngày hay bị GitHub trả 5xx -> chia cửa sổ 1 ngày
                    args += ["--window-days", "1"]
                code = run(args, f"data/logs/kaggle_crawl_{short}.log")
                status_path = Path(root) / repo.replace("/", "__") / "crawl_status.json"
                try:
                    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
                except (ValueError, OSError):
                    status = {}
                if code is None:
                    status.update(status="interrupted", updated_at=now().isoformat())
                    status_path.write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")
                    stopped = True
                elif code != 0:
                    status.update(status="failed", error_type=f"ProcessExit{code}")
                elif status.get("status") not in ("completed", "failed"):
                    status.update(status="failed", error_type="MissingCompletionStatus")
                results[key] = {**status, "days": days, "finished": now().isoformat(), "where": "kaggle"}
                save_results()
                log(f"  -> {results[key]['status']} ({(time.time() - T0) / 60:.0f} phút)")
                if stopped:
                    break
            if stopped:
                break
        if stopped:
            break
finally:
    save_results()
    # Dòng JSONL cuối có thể bị cắt khi dừng giữa chừng
    subprocess.run([sys.executable, "-m", "project3.crawl.checkpoint", "--repair", "data/crawl_pr", "data/validate"],
                   env=env, stdout=LOG, stderr=LOG)
    summary = {"finished_utc": now().isoformat(), "minutes": round((time.time() - T0) / 60, 1),
               "pr_completed": sum(results.get(f"pull_request|{r}", {}).get("status") == "completed" for r in repos),
               "push_completed": sum(results.get(f"push|{r}", {}).get("status") == "completed" for r in repos),
               "total_repos": len(repos)}
    (work / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log(f"summary {summary}")
    # Một file nén thay vì hàng chục nghìn file log lẻ trong output
    with tarfile.open(work / "crawl_out.tar.gz", "w:gz") as tar:
        tar.add("data", arcname="data")
    shutil.rmtree("data")
    log(f"đóng gói xong: {(work / 'crawl_out.tar.gz').stat().st_size / 1e6:.1f} MB")
