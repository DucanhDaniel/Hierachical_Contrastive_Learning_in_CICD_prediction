"""Nén dữ liệu văn bản lớn để vừa ổ đĩa khi mở rộng ~100 repo: diff (.diff → .diff.gz).

Mỗi file: ghi bản .gz, đọc lại so khớp nội dung, rồi mới xoá bản gốc. Chạy lại an toàn (bỏ qua file đã nén).
Cập nhật cột `path` trong các CSV danh sách diff cho trỏ sang .gz.

    uv run python -m project3.pipeline.compress_data --diffs data/diffs \
        --csv data/processed/pilot_diffs.csv data/processed/diffs_extra.csv data/processed/diffs_all.csv
"""
import argparse
import csv
import gzip
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def compress(path: Path) -> int:
    """Trả về số byte tiết kiệm được."""
    gz = path.with_name(path.name + ".gz")
    raw = path.read_bytes()
    if not gz.exists() or gzip.decompress(gz.read_bytes()) != raw:
        gz.write_bytes(gzip.compress(raw, 6))
        if gzip.decompress(gz.read_bytes()) != raw:
            raise IOError(f"nén lỗi: {path}")
    saved = len(raw) - gz.stat().st_size
    path.unlink()
    return saved


def fix_csv(path: Path) -> int:
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    n = 0
    for r in rows:
        if r["path"].endswith(".diff") and not Path(r["path"]).exists() and Path(r["path"] + ".gz").exists():
            r["path"] += ".gz"
            n += 1
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return n


def main(diffs: Path, csvs: list[Path], workers: int) -> None:
    files = sorted(diffs.glob("*/*.diff"))
    print(f"{len(files)} file diff chưa nén", flush=True)
    saved = 0
    with ThreadPoolExecutor(workers) as ex:
        for k, s in enumerate(ex.map(compress, files)):
            saved += s
            if (k + 1) % 2000 == 0:
                print(f"  {k + 1}/{len(files)}, tiết kiệm {saved / 1e9:.2f} GB", flush=True)
    print(f"xong: tiết kiệm {saved / 1e9:.2f} GB", flush=True)
    for c in csvs:
        print(f"  {c}: sửa {fix_csv(c)} đường dẫn", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--diffs", type=Path, default=Path("data/diffs"))
    ap.add_argument("--csv", type=Path, nargs="*", default=[])
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    main(a.diffs, a.csv, a.workers)
