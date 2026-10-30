"""Kernel Kaggle (GPU): mô hình đọc log phân loại lỗi CI theo cây nhãn (project3.model.train), nhiều fold chéo repo.

Dữ liệu + mã: dataset ducanhpham2k5/p3-log-data do `python -m project3.model.pack` tạo (mã ở project3_code.pyz).
Cấu hình lượt chạy ở CONFIG bên dưới; `python -m project3.model.kaggle kernel ...` sinh thư mục kernel với CONFIG khác.
Đầu ra (/kaggle/working): results_fold{k}.json, results_fold{k}.preds.parquet (+ .train_*.parquet khi --save-repr).
Dừng mở fold mới khi gần hết BUDGET_H giờ. Trước khi train: smoke test (60 run/fold, vài bước) với từng bộ tham số trong
CONFIG["smoke"]; lỗi thì dừng ngay. smoke_only = chỉ chạy smoke (kiểm tra mã mới, không train thật).
    kaggle kernels push -p scripts/kaggle/log_model
"""
import glob
import os
import shutil
import subprocess
import sys
import time

CONFIG = {"folds": [0, 1, 2, 3, 4], "variants": ["ce", "soft"], "budget_h": 10.5, "extra": [],
          "smoke": [[]], "smoke_only": False}

T0 = time.time()
FOLDS, VARIANTS, BUDGET_H, EXTRA = CONFIG["folds"], CONFIG["variants"], CONFIG["budget_h"], CONFIG["extra"]
# mỗi phần tử folds: số fold, hoặc [fold, tên file kết quả, tham số thêm riêng lượt đó] (vd. seed khác nhau)
RUNS = [(k, f"results_fold{k}", []) if isinstance(k, int) else tuple(k) for k in FOLDS]
src = os.path.dirname(glob.glob("/kaggle/input/**/label_tree.json", recursive=True)[0])
# file .pyz, hoặc thư mục nếu Kaggle tự giải nén; có dataset p3-code (mã mới, 30/10) thì dùng bản đó
code = sorted(glob.glob("/kaggle/input/**/project3_code.pyz*", recursive=True), key=lambda p: not p.startswith(src))[-1]
work = "/kaggle/working"
env = {**os.environ, "PYTHONPATH": code, "PYTHONIOENCODING": "utf-8"}
subprocess.run(["nvidia-smi"], check=False)
tfd = os.path.join(work, "tfidf")
if "--tfidf" in EXTRA:  # đặc trưng TF-IDF: dùng bản có sẵn trong dataset, tính trên CPU các fold còn thiếu
    os.makedirs(tfd, exist_ok=True)
    for f in glob.glob(os.path.join(src, "tfidf_fold*.parquet")):
        shutil.copy(f, tfd)
    miss = [str(k) for k in sorted({r[0] for r in RUNS}) if not os.path.exists(os.path.join(tfd, f"tfidf_fold{k}.parquet"))]
    if miss:
        subprocess.run([sys.executable, "-m", "project3.model.tfidf", "--data", src, "--out", tfd, "--folds", *miss],
                       check=True, env=env)
for i, args in enumerate(CONFIG.get("smoke", [])):
    cmd = [sys.executable, "-m", "project3.model.train", "--data", src, "--fold", str(RUNS[0][0]), "--variants", VARIANTS[-1],
           *EXTRA, *args, "--tfidf-dir", tfd, "--smoke", "--epochs", "1", "--max-steps", "5", "--val-max", "40",
           "--out", os.path.join(work, f"smoke{i}.json")]
    print("$ [smoke]", " ".join(cmd), flush=True)
    if subprocess.run(cmd, check=False, env=env).returncode != 0:
        sys.exit(f"smoke {i} lỗi ({args}), dừng để không tốn GPU")
print(f"smoke xong sau {(time.time() - T0) / 60:.1f} phút", flush=True)
if CONFIG.get("smoke_only"):
    sys.exit(0)
for i, (k, name, more) in enumerate(RUNS):
    if time.time() - T0 > BUDGET_H * 3600 * (1 - 1 / len(RUNS)) and i:
        print(f"dừng trước {name}: gần hết thời gian", flush=True)
        break
    cmd = [sys.executable, "-m", "project3.model.train", "--data", src, "--fold", str(k), "--variants", *VARIANTS, *EXTRA,
           *more, "--tfidf-dir", tfd, "--out", os.path.join(work, f"{name}.json")]
    print("$", " ".join(cmd), flush=True)
    code_ = subprocess.run(cmd, check=False, env=env).returncode
    print(f"{name} xong sau {(time.time() - T0) / 3600:.2f} giờ (mã thoát {code_})", flush=True)
    if code_ != 0 and not i:
        sys.exit(f"lượt đầu lỗi (mã {code_}), dừng để không tốn GPU")
