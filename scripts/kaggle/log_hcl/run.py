"""Kernel Kaggle (T4): mô hình đọc log phân loại lỗi CI theo cây nhãn (project3.pilot.log_hcl), 5 fold chéo repo x {ce, hcl}.
Từ 19/10: biến thể lai (EXTRA = ["--tfidf"], cần tfidf_fold{k}.parquet trong dataset, do tfidf_feats tạo).
20/10: lá hiếm (EXTRA thêm --sampler mpc --share-parent).
20/10 (lượt 2): seed 1 (--seed-start 1), preds lưu thêm logp 3 tầng.

Dữ liệu + mã: dataset ducanhpham2k5/p3-log-data do `python -m project3.pipeline.log_pack` tạo.
Đầu ra (/kaggle/working): results_fold{k}.json, results_fold{k}.preds.parquet. Dừng mở fold mới khi gần hết 12 giờ.
    kaggle kernels push -p scripts/kaggle/log_hcl
"""
import glob
import os
import shutil
import subprocess
import sys
import time

T0 = time.time()
FOLDS, VARIANTS, BUDGET_H, EXTRA = [0, 1, 2, 3, 4], ["ce", "hcl"], 10.5, ["--tfidf", "--sampler", "mpc", "--share-parent", "--seed-start", "1"]
src = os.path.dirname(glob.glob("/kaggle/input/**/label_tree.json", recursive=True)[0])
work = "/kaggle/working"
pkg = os.path.join(work, "pkg", "project3", "pilot")
os.makedirs(pkg, exist_ok=True)
for f in ("log_hcl.py", "tfidf_feats.py"):
    shutil.copy(os.path.join(src, f), pkg)
for d in (pkg, os.path.dirname(pkg)):
    open(os.path.join(d, "__init__.py"), "a").close()
env = {**os.environ, "PYTHONPATH": os.path.join(work, "pkg"), "PYTHONIOENCODING": "utf-8"}
subprocess.run(["nvidia-smi"], check=False)
tfd = os.path.join(work, "tfidf")
if "--tfidf" in EXTRA:  # đặc trưng TF-IDF: dùng bản có sẵn trong dataset, tính trên CPU các fold còn thiếu
    os.makedirs(tfd, exist_ok=True)
    for f in glob.glob(os.path.join(src, "tfidf_fold*.parquet")):
        shutil.copy(f, tfd)
    miss = [str(k) for k in FOLDS if not os.path.exists(os.path.join(tfd, f"tfidf_fold{k}.parquet"))]
    if miss:
        subprocess.run([sys.executable, "-m", "project3.pilot.tfidf_feats", "--data", src, "--out", tfd, "--folds", *miss],
                       check=True, env=env)
for k in FOLDS:
    if time.time() - T0 > BUDGET_H * 3600 * (1 - 1 / len(FOLDS)) and k != FOLDS[0]:
        print(f"dừng trước fold {k}: gần hết thời gian", flush=True)
        break
    cmd = [sys.executable, "-m", "project3.pilot.log_hcl", "--data", src, "--fold", str(k), "--variants", *VARIANTS, *EXTRA,
           "--tfidf-dir", tfd, "--out", os.path.join(work, f"results_fold{k}.json")]
    print("$", " ".join(cmd), flush=True)
    code = subprocess.run(cmd, check=False, env=env).returncode
    print(f"fold {k} xong sau {(time.time() - T0) / 3600:.2f} giờ (mã thoát {code})", flush=True)
    if code != 0 and k == FOLDS[0]:
        sys.exit(f"fold đầu lỗi (mã {code}), dừng để không tốn GPU")
shutil.rmtree(os.path.join(work, "pkg"))
