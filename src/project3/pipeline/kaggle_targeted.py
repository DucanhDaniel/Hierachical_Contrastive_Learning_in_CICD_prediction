"""Chuẩn bị đầu vào / gộp đầu ra cho kernel crawl đợt 3 trên Kaggle (scripts/kaggle/crawl_targeted).

    python -m project3.pipeline.kaggle_targeted prepare --budget-min 630   # tạo data/kaggle_r3_ds
    python -m project3.pipeline.kaggle_targeted merge data/kaggle_r3_out/<phiên>
    # đợt android (25/10/2026): kernel scripts/kaggle/crawl_android, dataset p3-crawl-android-state
    python -m project3.pipeline.kaggle_targeted --round android prepare --targets configs/targets_android.jsonl --max-runs 200
    python -m project3.pipeline.kaggle_targeted --round android merge data/kaggle_android_out/<phiên>

Repo đã xong ghi ở data/processed/crawl_targeted_r3_done.jsonl (dùng chung với chạy local), phiên sau bỏ qua.
Repo đang dở lúc hết giờ không được mang theo: phiên sau crawl lại từ đầu (chỉ vài trăm run/repo).
"""
import argparse
import json
import shutil
import sys
import tarfile
from pathlib import Path

DS = Path("data/kaggle_r3_ds")
DATASET_ID = "ducanhpham2k5/p3-crawl-r3-state"
DONE = Path("data/processed/crawl_targeted_r3_done.jsonl")
SCOPE = "targeted-r3"


def use_round(name: str) -> None:
    """Đường dẫn / dataset / scope của một đợt (r3 giữ tên cũ)."""
    global DS, DATASET_ID, DONE, SCOPE
    DS, DATASET_ID = Path(f"data/kaggle_{name}_ds"), f"ducanhpham2k5/p3-crawl-{name}-state"
    DONE, SCOPE = Path(f"data/processed/crawl_targeted_{name}_done.jsonl"), f"targeted-{name}"


def prepare(targets: Path, budget_min: int, days: int, max_runs: int) -> None:
    if DS.exists():
        shutil.rmtree(DS)
    DS.mkdir(parents=True)
    for f in ("gha.py", "github.py", "checkpoint.py"):
        shutil.copy(Path("src/project3/crawl") / f, DS)
    shutil.copy("src/project3/pipeline/crawl_targeted.py", DS)
    shutil.copy(targets, DS / "targets.jsonl")
    (DS / "done.jsonl").write_text(DONE.read_text(encoding="utf-8") if DONE.exists() else "", encoding="utf-8")
    (DS / "config.json").write_text(json.dumps({"budget_minutes": budget_min, "days": days, "max_runs": max_runs,
                                                "scope": SCOPE}),
                                    encoding="utf-8")
    (DS / "dataset-metadata.json").write_text(json.dumps(
        {"title": DATASET_ID.split("/")[1], "id": DATASET_ID, "licenses": [{"name": "other"}]}), encoding="utf-8")
    repos = {json.loads(l)["repository"] for l in targets.open(encoding="utf-8") if l.strip()}
    done = {json.loads(l)["repository"] for l in (DS / "done.jsonl").open(encoding="utf-8") if l.strip()}
    print(f"{DS}: {len(repos)} repo, đã xong {len(repos & done)}, còn {len(repos - done)}")


def merge(out_dir: Path) -> None:
    n, skipped = 0, set()
    with tarfile.open(out_dir / "crawl_out.tar.gz") as tar:
        for m in tar.getmembers():
            p = Path(m.name)
            if p.parts[:2] not in (("data", "crawl_pr"), ("data", "validate")) or len(p.parts) < 3:
                continue
            local = Path(*p.parts[:3])
            st = local / "crawl_status.json"
            # repo đã crawl đầy đủ từ đợt trước: bản Kaggle chỉ có phần mới -> không được ghi đè
            if st.exists() and json.loads(st.read_text(encoding="utf-8")).get("scope") != SCOPE:
                skipped.add(local.as_posix())
                continue
            tar.extract(m, ".", filter="data")
            n += m.isfile()
    old = {json.loads(l)["repository"] for l in DONE.open(encoding="utf-8")} if DONE.exists() else set()
    new = [l for l in (out_dir / "done.jsonl").read_text(encoding="utf-8").splitlines()
           if l.strip() and json.loads(l)["repository"] not in old]
    with DONE.open("a", encoding="utf-8") as f:
        f.writelines(l + "\n" for l in new)
    shutil.copy(out_dir / "runner.log", Path("data/logs") / f"kaggle_{SCOPE.split('-')[1]}_runner_{out_dir.name}.log")
    print(f"Gộp {n} file, +{len(new)} repo xong (tổng {len(old) + len(new)}); bỏ qua repo cũ: {sorted(skipped)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", default="r3", help="tên đợt: r3 | android")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--targets", type=Path, default=Path("configs/targets_r3.jsonl"))
    p.add_argument("--budget-min", type=int, default=630)
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--max-runs", type=int, default=400)
    m = sub.add_parser("merge")
    m.add_argument("out_dir", type=Path)
    a = ap.parse_args()
    use_round(a.round)
    if a.cmd == "prepare":
        prepare(a.targets, a.budget_min, a.days, a.max_runs)
    else:
        merge(a.out_dir)
