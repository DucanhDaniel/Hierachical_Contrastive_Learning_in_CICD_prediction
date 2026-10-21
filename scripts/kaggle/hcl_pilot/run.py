"""Kernel Kaggle cho pilot HCL: embed hunk bằng UniXcoder (T4, fp16) rồi chạy 5 biến thể x 5 seed (STEP=train),
linear probe chẩn đoán (STEP=probe), hoặc thí nghiệm dự đoán loại lỗi (STEP=type).

Dữ liệu và mã nguồn lấy từ dataset ducanhpham2k5/hcl-pilot-data (hunks.json.gz, meta.parquet, *.py).
Đẩy lên: kaggle kernels push -p scripts/kaggle/hcl_pilot
"""
import glob
import gzip
import os
import shutil
import subprocess
import sys

src = os.path.dirname(glob.glob("/kaggle/input/**/meta.parquet", recursive=True)[0])
print("dataset:", src, sorted(os.listdir(src)), flush=True)
work = "/kaggle/working"
hunks = os.path.join(src, "hunks.json.gz")
if not os.path.exists(hunks):  # Kaggle tự giải nén .gz khi tạo dataset -> nén lại cho hcl_embed
    hunks = os.path.join(work, "hunks.json.gz")
    with open(os.path.join(src, "hunks.json"), "rb") as f, gzip.open(hunks, "wb") as g:
        shutil.copyfileobj(f, g)
pkg = os.path.join(work, "pkg", "project3", "pilot")
os.makedirs(pkg, exist_ok=True)
for f in ("experiment.py", "hcl_embed.py", "hcl_train.py", "hcl_probe.py", "type_feasibility.py"):
    shutil.copy(os.path.join(src, f), pkg)
for d in (pkg, os.path.dirname(pkg)):
    open(os.path.join(d, "__init__.py"), "a").close()
env = {**os.environ, "PYTHONPATH": os.path.join(work, "pkg"), "PYTHONIOENCODING": "utf-8"}


def sh(*cmd):
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, env=env)


STEP = "type"  # train | probe | type
sh("nvidia-smi")
sh(sys.executable, "-c", "import torch, transformers, sklearn; print(torch.__version__, transformers.__version__, sklearn.__version__)")
if STEP == "type":  # dự đoán loại lỗi: baseline + fine-tune UniXcoder (ce, hcl) x 3 seed
    sh(sys.executable, "-m", "project3.pilot.type_feasibility", "--meta", os.path.join(src, "meta.parquet"),
       "--hunks", hunks, "--seeds", "3", "--out", os.path.join(work, "type_feasibility.json"))
    if hunks.startswith(work):
        os.remove(hunks)
    shutil.rmtree(os.path.join(work, "pkg"))
    sys.exit(0)
emb = os.path.join(work, "emb.npz")
sh(sys.executable, "-m", "project3.pilot.hcl_embed", "--hunks", hunks,
   "--fp16", "--batch", "128", "--out", emb)
if STEP == "train":
    sh(sys.executable, "-m", "project3.pilot.hcl_train", "--meta", os.path.join(src, "meta.parquet"),
       "--emb", emb, "--seeds", "5", "--out", os.path.join(work, "results.json"))
    os.remove(emb)  # ~190MB, tính lại được; giữ output nhỏ
else:  # chẩn đoán: linear probe trên embedding; giữ emb.npz để tái sử dụng
    sh(sys.executable, "-m", "project3.pilot.hcl_probe", "--meta", os.path.join(src, "meta.parquet"),
       "--emb", emb, "--out", os.path.join(work, "probe.json"))
if hunks.startswith(work):
    os.remove(hunks)
shutil.rmtree(os.path.join(work, "pkg"))
