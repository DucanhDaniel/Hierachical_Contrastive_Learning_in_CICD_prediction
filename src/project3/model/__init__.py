"""Mô hình phân loại loại lỗi CI từ log (hướng hiện tại, docs/huong-moi-phan-loai-sau-ci.md).

Lõi (chạy được trên Kaggle/Colab, Python ≥3.11, không import project3.crawl / project3.pipeline):
  config    hằng số, đường dẫn            labels   cây nhãn 3 tầng (label_tree.json)
  text      che bằng chứng, cắt đoạn       data     đọc gói dữ liệu, chia fold, che 50%
  metrics   macro-F1 theo tầng            tfidf    TF-IDF + SGD, đặc trưng stacking cho mô hình lai
  nn/       encoder, attention, loss, sampler (cần torch)
  train     huấn luyện + đánh giá một fold (CLI chính)
  routing   attention đúng đoạn, định tuyến theo độ tin cậy

Chỉ chạy ở máy local (cần run_dataset, quy tắc gán nhãn):
  pack      đóng gói dữ liệu + mã cho Kaggle   baselines  quy tắc, TF-IDF   llm  baseline LLM
"""
