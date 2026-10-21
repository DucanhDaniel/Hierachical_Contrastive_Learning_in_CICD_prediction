"""Kernel Kaggle (GPU): mô hình đọc log phân loại lỗi CI theo cây nhãn (project3.model.train), nhiều fold chéo repo.

Dữ liệu + mã: dataset ducanhpham2k5/p3-log-data do `python -m project3.model.pack` tạo (mã ở project3_code.pyz).
Cấu hình lượt chạy ở CONFIG bên dưới; `python -m project3.model.kaggle kernel ...` sinh thư mục kernel với CONFIG khác.
Đầu ra (/kaggle/working): results_fold{k}.json, results_fold{k}.preds.parquet (+ .train_*.parquet khi --save-repr).
Dừng mở fold mới khi gần hết BUDGET_H giờ.
    kaggle kernels push -p scripts/kaggle/log_model
"""
import glob
import os
import shutil
import subprocess
import sys
import time

CONFIG = {"folds": [0, 1, 2, 3, 4], "variants": ["ce", "hcl"], "budget_h": 10.5,
          "extra": ["--tfidf", "--sampler", "mpc", "--share-parent", "--seed-start", "1"]}

T0 = time.time()
FOLDS, VARIANTS, BUDGET_H, EXTRA = CONFIG["folds"], CONFIG["variants"], CONFIG["budget_h"], CONFIG["extra"]
src = os.path.dirname(glob.glob("/kaggle/input/**/label_tree.json", recursive=True)[0])
code = glob.glob(os.path.join(src, "project3_code.pyz*"))[0]  # file .pyz, hoặc thư mục nếu Kaggle tự giải nén
work = "/kaggle/working"
env = {**os.environ, "PYTHONPATH": code, "PYTHONIOENCODING": "utf-8"}
subprocess.run(["nvidia-smi"], check=False)
tfd = os.path.join(work, "tfidf")
if "--tfidf" in EXTRA:  # đặc trưng TF-IDF: dùng bản có sẵn trong dataset, tính trên CPU các fold còn thiếu
    os.makedirs(tfd, exist_ok=True)
    for f in glob.glob(os.path.join(src, "tfidf_fold*.parquet")):
        shutil.copy(f, tfd)
    miss = [str(k) for k in FOLDS if not os.path.exists(os.path.join(tfd, f"tfidf_fold{k}.parquet"))]
    if miss:
        subprocess.run([sys.executable, "-m", "project3.model.tfidf", "--data", src, "--out", tfd, "--folds", *miss],
                       check=True, env=env)
for k in FOLDS:
    if time.time() - T0 > BUDGET_H * 3600 * (1 - 1 / len(FOLDS)) and k != FOLDS[0]:
        print(f"dừng trước fold {k}: gần hết thời gian", flush=True)
        break
    cmd = [sys.executable, "-m", "project3.model.train", "--data", src, "--fold", str(k), "--variants", *VARIANTS, *EXTRA,
           "--tfidf-dir", tfd, "--out", os.path.join(work, f"results_fold{k}.json")]
    print("$", " ".join(cmd), flush=True)
    code_ = subprocess.run(cmd, check=False, env=env).returncode
    print(f"fold {k} xong sau {(time.time() - T0) / 3600:.2f} giờ (mã thoát {code_})", flush=True)
    if code_ != 0 and k == FOLDS[0]:
        sys.exit(f"fold đầu lỗi (mã {code_}), dừng để không tốn GPU")
