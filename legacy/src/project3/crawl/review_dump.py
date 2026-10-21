"""Trích dòng lỗi chính trong log của từng run fail (dữ liệu kiểm chứng) ra file text để gán nhãn chuẩn bằng tay.

    uv run python -m project3.crawl.review_dump data/validate > data/validate_review.txt
"""
import json
import re
import sys
from pathlib import Path

KEY = re.compile(r"##\[error\]|\[ERROR\]|ERROR:|FAILED|FAILURE|Failures: [1-9]|Errors: [1-9]|Exception|error:|"
                 r"Could not|cannot find symbol|not found|violation|Too many|Process completed with exit code", re.I)
NOISE = re.compile(r"\[ERROR\]\s*$|Re-run Maven|For more information about the errors|Help 1|mvn <args>|"
                   r"full stack trace|-e switch|-X switch|resume the build|^\s*$")


def strip_ts(line: str) -> str:
    return re.sub(r"^\d{4}-\d\d-\d\dT[\d:.]+Z ", "", line).strip()


def main(root: Path) -> None:
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        runs = {r["id"]: r for r in map(json.loads, (d / "runs.jsonl").read_text(encoding="utf-8").splitlines())}
        for line in (d / "jobs.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            run = runs.get(row["run_id"])
            if not run or run["conclusion"] != "failure":
                continue
            print(f"\n=== {d.name.replace('__', '/')} | run {row['run_id']} | {run['name']}")
            for j in row["jobs"]:
                if j["conclusion"] != "failure":
                    continue
                steps = [s["name"] for s in j["steps"] if s["conclusion"] == "failure"]
                print(f"  - job: {j['name'][:90]} | step fail: {steps}")
                f = d / "logs" / f"{j['id']}.txt"
                if not f.exists():
                    print("      (không có log)")
                    continue
                lines = [strip_ts(l) for l in f.read_text(encoding="utf-8", errors="ignore").splitlines()]
                keys = [l for l in lines if KEY.search(l) and not NOISE.search(l)]
                seen, out = set(), []
                for l in keys:
                    k = l[:120]
                    if k not in seen:
                        seen.add(k)
                        out.append(l[:220])
                for l in out[:10]:
                    print(f"      {l}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "data/validate"))
