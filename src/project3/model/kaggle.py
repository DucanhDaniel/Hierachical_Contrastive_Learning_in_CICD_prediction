"""Sinh thư mục kernel Kaggle cho một lượt chạy model.train từ runner chung scripts/kaggle/log_model/run.py.

    python -m project3.model.kaggle kernel p3-log-repr --folds 1 --variants soft proxy \
        --extra "--tfidf --sampler mpc --share-parent --save-repr"
    -> data/kaggle_kernels/p3-log-repr/{run.py, kernel-metadata.json}; rồi `kaggle kernels push -p <thư mục>`
"""
import argparse
import json
import re
import shlex
import sys
from pathlib import Path

RUNNER = Path("scripts/kaggle/log_model")
OUT = Path("data/kaggle_kernels")


def make_kernel(kernel: str, folds: list, variants: list, extra: list, budget_h: float, gpu: str) -> Path:
    cfg = {"folds": folds, "variants": variants, "budget_h": budget_h, "extra": extra}
    text = (RUNNER / "run.py").read_text(encoding="utf-8")
    text, n = re.subn(r"^CONFIG = \{.*?\}\n", lambda _: f"CONFIG = {json.dumps(cfg)}\n", text, flags=re.S | re.M)
    assert n == 1, "không tìm thấy CONFIG trong runner"
    meta = json.loads((RUNNER / "kernel-metadata.json").read_text(encoding="utf-8"))
    meta.update(id=f"ducanhpham2k5/{kernel}", title=kernel, machine_shape=gpu)
    d = OUT / kernel
    d.mkdir(parents=True, exist_ok=True)
    (d / "run.py").write_text(text, encoding="utf-8")
    (d / "kernel-metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return d


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("kernel")
    k.add_argument("name")
    k.add_argument("--folds", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    k.add_argument("--variants", nargs="+", default=["ce", "hcl"])
    k.add_argument("--extra", default="", help="tham số thêm cho model.train, một chuỗi")
    k.add_argument("--budget-h", type=float, default=10.5)
    k.add_argument("--gpu", default="NvidiaTeslaT4")
    a = ap.parse_args()
    print(make_kernel(a.name, a.folds, a.variants, shlex.split(a.extra), a.budget_h, a.gpu))
