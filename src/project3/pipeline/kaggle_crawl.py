"""Chuẩn bị đầu vào / gộp đầu ra cho kernel crawl trên Kaggle (scripts/kaggle/crawl).

    python -m project3.pipeline.kaggle_crawl prepare --budget-min 660   # tạo data/kaggle_crawl_ds
    python -m project3.pipeline.kaggle_crawl merge data/kaggle_crawl_out  # gộp output đã tải về vào data/

Đợt 2 (18/10/2026, repo chọn bằng probe_repos):
    python -m project3.pipeline.kaggle_crawl prepare --repos-file configs/repos_r2.txt --deadline 2026-10-24T22:00:00+07:00

Kết quả từng repo dùng chung data/crawl_100_results.json với worker local, nên hai bên tiếp nối được nhau.
Không chạy local và Kaggle cùng lúc (cùng token, cùng repo).
"""
import argparse
import json
import shutil
import tarfile
from datetime import datetime
from pathlib import Path

from project3.pipeline.crawl_100 import DEADLINE, MIDPOINT, RESULTS, load_results, save

DS = Path("data/kaggle_crawl_ds")
DATASET_ID = "ducanhpham2k5/p3-crawl-state"
ROOTS = {"pull_request": Path("data/crawl_pr"), "push": Path("data/validate")}


REPOS_FILE = Path("configs/repos_100.txt")


def repo_list(path: Path = REPOS_FILE):
    return [l.strip() for l in Path(path).read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")]


def prepare(budget_min: int, days: int, repos_file: Path = REPOS_FILE, deadline: str | None = None):
    if DS.exists():
        shutil.rmtree(DS)
    DS.mkdir(parents=True)
    for f in ("gha.py", "github.py", "checkpoint.py"):
        shutil.copy(Path("src/project3/crawl") / f, DS)
    shutil.copy(repos_file, DS / "repos.txt")
    results = load_results(RESULTS)
    (DS / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (DS / "crawl_config.json").write_text(json.dumps(
        {"budget_minutes": budget_min, "days": days, "deadline": deadline or DEADLINE.isoformat(),
         # đợt mới: không rút xuống 60 ngày giữa chừng (midpoint = hạn chót)
         "midpoint": deadline or MIDPOINT.isoformat()}), encoding="utf-8")
    # Repo đang dở: mang theo runs/jobs/log đã có để không tải lại. Đuôi .dat để Kaggle không tự giải nén.
    partial = []
    with tarfile.open(DS / "state.dat", "w") as tar:
        for repo in repo_list(repos_file):
            for event, root in ROOTS.items():
                d = root / repo.replace("/", "__")
                if d.is_dir() and results.get(f"{event}|{repo}", {}).get("status") != "completed":
                    tar.add(d, arcname=d.as_posix())
                    partial.append(f"{event}|{repo}")
    (DS / "dataset-metadata.json").write_text(json.dumps(
        {"title": "p3-crawl-state", "id": DATASET_ID, "licenses": [{"name": "other"}]}), encoding="utf-8")
    done = sum(v.get("status") == "completed" for v in results.values())
    print(f"{DS}: {done} repo-event đã xong, mang theo {len(partial)} repo dở: {partial}")


def merge(out_dir: Path, repos_file: Path = REPOS_FILE):
    results = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    n = 0
    with tarfile.open(out_dir / "crawl_out.tar.gz") as tar:
        for m in tar.getmembers():
            p = Path(m.name)
            if p.parts[:2] in (("data", "crawl_pr"), ("data", "validate")):
                tar.extract(m, ".", filter="data")  # bản Kaggle là bản đầy đủ hơn của repo dở -> ghi đè
                n += m.isfile()
            elif p.parts[:2] == ("data", "logs") and m.isfile():
                m.name = f"data/logs/{p.stem}_{stamp}{p.suffix}"  # giữ log từng phiên, không ghi đè
                tar.extract(m, ".", filter="data")
    local = load_results(RESULTS)
    local.update(results)
    save(RESULTS, local)
    shutil.copy(out_dir / "runner.log", f"data/logs/kaggle_runner_{stamp}.log")
    repos = repo_list(repos_file)
    pr = sum(local.get(f"pull_request|{r}", {}).get("status") == "completed" for r in repos)
    push = sum(local.get(f"push|{r}", {}).get("status") == "completed" for r in repos)
    print(f"Gộp {n} file. PR xong {pr}/{len(repos)}, push xong {push}/{len(repos)}")
    for k, v in local.items():
        if v.get("status") != "completed" and k.split("|", 1)[1] in repos:
            print(f"  chưa xong: {k} -> {v.get('status')} {v.get('error_type', '')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--budget-min", type=int, default=660, help="phút chạy tối đa mỗi phiên (Kaggle giới hạn 12 giờ)")
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--repos-file", type=Path, default=REPOS_FILE)
    p.add_argument("--deadline", help="ISO có múi giờ; mặc định hạn chót đợt 1")
    m = sub.add_parser("merge")
    m.add_argument("out_dir", type=Path)
    m.add_argument("--repos-file", type=Path, default=REPOS_FILE)
    a = ap.parse_args()
    if a.cmd == "prepare":
        prepare(a.budget_min, a.days, a.repos_file, a.deadline)
    else:
        merge(a.out_dir, a.repos_file)
