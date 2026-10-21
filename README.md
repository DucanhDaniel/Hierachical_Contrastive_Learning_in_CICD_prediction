# project3 — Phân loại loại lỗi build CI từ log

Đề tài Project 3: cho một GitHub Actions run bị fail (dự án Java/Kotlin), xác định loại lỗi theo cây nhãn 3 tầng
(build/test/env → 7 loại → lá chi tiết) bằng mô hình đọc log (UniXcoder + attention phân cấp, CE/HCL),
so với quy tắc, TF-IDF và LLM. Hướng hiện tại: `docs/huong-moi-phan-loai-sau-ci.md`.

## Cấu trúc

```
src/project3/
  crawl/      thu thập GitHub Actions (gha, github, checkpoint), gán nhãn quy tắc (gold_labels, build_log_labels, fine_labels)
  pipeline/   chạy cả pipeline (run), dataset mức commit/run (export_dataset, run_dataset), lấy diff (fetch_diffs),
              Kaggle crawl/diff (kaggle_crawl, kaggle_diff), gán nhãn người + rà quy tắc (label_ui, relabel, review_rules, rule_eval)
  model/      mô hình đọc log — xem src/project3/model/__init__.py
scripts/kaggle/  kernel Kaggle: crawl/, diff/, log_model/ (huấn luyện), llm_baseline/ (Kaggle Benchmarks)
configs/         label_rules.json (quy tắc hiện hành), danh sách repo
data/            dữ liệu (không đưa lên git) — xem data/README.md
docs/            đặc tả, kết quả thí nghiệm, slide, báo cáo
legacy/          code/tài liệu của hướng cũ (dự đoán trước CI từ diff), không bảo trì
tests/           python -m unittest discover -s tests
```

## Lệnh chính (chạy ở gốc repo)

```bash
# dữ liệu
python -m project3.pipeline.run --repos-file configs/repos_100.txt --skip crawl   # nhãn -> commit -> export
python -m project3.pipeline.run_dataset                                          # dataset mức run + đoạn log

# mô hình
python -m project3.model.pack                     # gói dữ liệu + mã -> data/kaggle_log_ds (dataset p3-log-data)
python -m project3.model.tfidf --export-text      # văn bản cho đặc trưng TF-IDF
python -m project3.model.train --data data/kaggle_log_ds --fold 0 --variants ce hcl --smoke   # thử nhanh
python -m project3.model.kaggle kernel p3-log-x --folds 0 1 --variants ce soft --extra "--tfidf"  # kernel Kaggle
python -m project3.model.baselines all | fair     # baseline quy tắc / TF-IDF
python -m project3.model.routing data/results/log_model/v5_repr
python -m project3.model.llm prepare | score DIR
```

Trên Kaggle/Colab không cần cài package: đặt `PYTHONPATH` tới `project3_code.pyz` trong gói dữ liệu
(Python ≥3.11) rồi chạy `python -m project3.model.train ...`.
