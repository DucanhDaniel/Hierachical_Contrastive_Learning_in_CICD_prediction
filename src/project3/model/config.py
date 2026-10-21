"""Hằng số và đường dẫn dùng chung. Đường dẫn tương đối với gốc repo."""
from pathlib import Path

DATA = Path("data")
RUN_DATASET = DATA / "run_dataset"     # dataset mức run + đoạn log (pipeline.run_dataset)
PACK = DATA / "kaggle_log_ds"          # gói dữ liệu cho mô hình (model.pack), dataset Kaggle p3-log-data
HUMAN_LABELS = DATA / "human_labels"
RESULTS = DATA / "results"
LOG_MODEL_OUT = RESULTS / "log_model"  # output Kaggle của model.train, mỗi lượt một thư mục con (v2, v3_tfidf, ...)
BASELINE_OUT = RESULTS / "log_baselines"
LLM_OUT = RESULTS / "llm_baseline"

ENCODER = "microsoft/unixcoder-base"
N_FOLDS = 5
SEED = 20261018          # seed của baseline và TF-IDF (chọn run che 50%, SGD)
MAX_RUN_CHARS = 30_000   # TF-IDF đọc 30.000 ký tự cuối của run

# loss so sánh (đã chốt trước, không dò)
TAU = 0.1                # nhiệt độ SupCon / proxy
LAMBDA = 0.5             # trọng số loss so sánh cộng vào CE
MEMORY = 512             # kích thước bộ nhớ đặc trưng
MEMORY_WARMUP = 50       # số bước đầu chưa dùng bộ nhớ
SHARE_L2 = 1e-3          # phạt L2 độ lệch lá khi --share-parent
SIB_W = 0.4              # trọng số cặp anh em (loss soft)
PROXY_PARENT_W = 0.3     # trọng số loss nguyên mẫu cha (loss proxy)
