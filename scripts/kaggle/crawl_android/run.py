"""Kernel Kaggle (CPU) cho crawl nhắm mục tiêu (đợt 3; đợt android dùng cùng file, xem scripts/kaggle/crawl_android): chạy project3.pipeline.crawl_targeted (run fail của workflow nhắm lá hiếm).

Đầu vào: dataset ducanhpham2k5/p3-crawl-r3-state do `python -m project3.pipeline.kaggle_targeted prepare` tạo
(gha.py, github.py, checkpoint.py, crawl_targeted.py, targets.jsonl, done.jsonl = repo đã xong, config.json).
Token GitHub: gh_token.txt trong dataset private ducanhpham2k5/p3-gh-token.
Đầu ra (/kaggle/working): crawl_out.tar.gz (data/crawl_pr|validate/<repo>/...), done.jsonl, runner.log.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

src = Path(glob.glob("/kaggle/input/**/targets.jsonl", recursive=True)[0]).parent
cfg = json.loads((src / "config.json").read_text(encoding="utf-8"))
work = Path("/kaggle/working")
os.chdir(work)

pkg = Path("/tmp/pkg/project3")
for sub, files in (("crawl", ("gha.py", "github.py", "checkpoint.py")), ("pipeline", ("crawl_targeted.py",))):
    (pkg / sub).mkdir(parents=True, exist_ok=True)
    (pkg / sub / "__init__.py").touch()
    for f in files:
        shutil.copy(src / f, pkg / sub)
(pkg / "__init__.py").touch()

token = Path(glob.glob("/kaggle/input/**/gh_token.txt", recursive=True)[0]).read_text(encoding="utf-8").strip()
env = {**os.environ, "PYTHONPATH": "/tmp/pkg", "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1",
       "GITHUB_ACCESS_TOKEN": token}
shutil.copy(src / "done.jsonl", work / "done.jsonl")
Path("data/logs").mkdir(parents=True, exist_ok=True)

try:
    with open(work / "runner.log", "a", encoding="utf-8") as log:
        subprocess.run([sys.executable, "-u", "-m", "project3.pipeline.crawl_targeted", "--targets",
                        str(src / "targets.jsonl"), "--done", str(work / "done.jsonl"), "--days", str(cfg["days"]),
                        "--max-runs", str(cfg["max_runs"]), "--budget-min", str(cfg["budget_minutes"]),
                        "--scope", cfg.get("scope", "targeted-r3")],
                       env=env, stdout=log, stderr=subprocess.STDOUT, timeout=(cfg["budget_minutes"] + 50) * 60)
except subprocess.TimeoutExpired:
    print("quá thời gian, đóng gói phần đã có", flush=True)
finally:
    subprocess.run([sys.executable, "-m", "project3.crawl.checkpoint", "--repair", "data/crawl_pr", "data/validate"],
                   env=env)
    with tarfile.open(work / "crawl_out.tar.gz", "w:gz") as tar:
        tar.add("data", arcname="data")
    shutil.rmtree("data")
    print(open(work / "runner.log", encoding="utf-8").read()[-3000:], flush=True)
