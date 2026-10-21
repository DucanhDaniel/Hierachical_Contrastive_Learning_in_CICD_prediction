# Mô hình làm bộ định tuyến cho LLM: E1, E2, E4 — 20/10/2026

- **Bối cảnh:** hướng kết hợp (docs/ket-qua-baseline-llm-2026-10-20.md). Mô hình cục bộ phân loại + chọn đoạn log; LLM chỉ xử lý run khó và chỉ ra vị trí lỗi.
- **Mô hình:** lai + sampler (`--tfidf --sampler mpc --share-parent`), seed 0.
- **Code:** [route_eval.py](../src/project3/pilot/route_eval.py).
- **Dữ liệu:** kernel `p3-log-repr` (2 fold, `--save-repr`, lưu attention từng đoạn + z), kết quả `data/results/log_model/v5_repr/`.

## E1. Phân luồng theo tầng 1 (5 fold, 43.613 run, dự đoán có sẵn)

| | Dự đoán env | Precision env | Recall env | Lỗi code bị đẩy nhầm sang env |
|---|---:|---:|---:|---:|
| Lai CE (không sampler) | 13,5% | 0,75 | 0,83 | 3,8% |
| Lai + sampler HCL | 17,9% | 0,58 | 0,85 | 8,6% |

- env chỉ chiếm 12,3% số run, nên phân luồng tầng 1 tiết kiệm tối đa khoảng 13% lời gọi LLM.
- Sampler làm lệch phân bố lớp; muốn dùng để định tuyến thì cần hiệu chỉnh logit.

## E2. Attention có chỉ đúng đoạn chứa bằng chứng không (2 fold, 18.953 run có đoạn chứa bằng chứng, log nguyên vẹn)

| | hit@1 | hit@3 |
|---|---:|---:|
| Lai + sampler CE | **0,579** | **0,923** |
| Lai + sampler HCL | 0,556 | 0,908 |
| Đoạn cuối | 0,396 | — |
| Ngẫu nhiên | 0,419 | — |

- 3 đoạn được chú ý nhiều nhất chứa dòng bằng chứng ở khoảng **92%** run.
- Như vậy có thể gửi LLM 3 đoạn (khoảng 1.000 token) thay vì cả đuôi log.
- Cơ chế này đến từ kiến trúc attention phân cấp (đoạn → job → run), không phải từ loss HCL: CE nhỉnh hơn HCL.

## E4. Định tuyến theo độ tin cậy (mức lá, 2 fold, TB)

| Mô hình | Tín hiệu | acc | AUROC phát hiện sai | acc khi giữ 80% | Hệ thống, gửi LLM 20% |
|---|---|---:|---:|---:|---:|
| CE | xác suất | 0,815 | 0,888 | 0,924 | 0,884 |
| CE | kNN trên z | | 0,870 | 0,919 | 0,880 |
| CE | xác suất + kNN | | **0,901** | 0,932 | 0,890 |
| HCL | xác suất | 0,837 | 0,885 | 0,933 | 0,892 |
| HCL | kNN trên z | | 0,831 | 0,923 | 0,884 |
| HCL | xác suất + kNN | | 0,869 | **0,940** | **0,896** |

"Hệ thống, gửi LLM 20%" giả định LLM đúng 72,4% trên phần run bị chuyển. Con số này đo trên mẫu cân bằng, chỉ là ước tính.

1. **Tín hiệu tin cậy phát hiện dự đoán sai tốt** (AUROC khoảng 0,89–0,90).
   - Giữ 80% run tự tin nhất thì độ đúng mức lá tăng từ 0,82–0,84 lên 0,92–0,94.
2. **Embedding HCL không định tuyến tốt hơn CE.** AUROC của kNN thấp hơn (0,831 so với 0,870). Giả thuyết "không gian HCL giúp nhận ra run khó" không được xác nhận.
3. **HCL có acc mức lá cao hơn CE** (0,837 so với 0,815, 2 fold), nên hệ thống dùng HCL nhỉnh hơn khoảng 0,006.
4. **Gửi 20–30% run khó cho LLM:** ước tính độ đúng toàn hệ thống khoảng 0,89, so với 0,84 khi chỉ dùng mô hình. Cần xác nhận bằng LLM thật trên chính các run đó.
