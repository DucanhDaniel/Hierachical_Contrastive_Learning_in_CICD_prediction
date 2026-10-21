# Baseline LLM phân loại lỗi CI từ log — 20/10/2026

- **Mục đích:** trả lời câu hỏi "đưa log cho AI thì phân loại đúng đến đâu". LLM chỉ dùng để so sánh, **không phải nguồn nhãn** (C-02).
- **Mô hình:** Gemini 3.5 Flash-Lite qua Kaggle Benchmarks (quota AI). Zero-shot, không ví dụ mẫu.
- **Chi phí:** 905 lời gọi, tổng **$0,95** (khoảng $0,001 mỗi run).
- **Code:**
  - [llm_baseline.py](../src/project3/pilot/llm_baseline.py): `prepare` và `score`.
  - [task.py](../scripts/kaggle/llm_baseline/task.py): task Kaggle `p3-llm-baseline`.
- **Kết quả:** `data/llm_baseline/` (llm_preds.parquet, scores.csv).

## Thiết lập

- **Đầu vào:** ngữ cảnh CI (workflow / job, thêm step ở tập nhãn quy tắc) + 12.000 ký tự cuối các đoạn log (cùng nguồn với mô hình).
- **Prompt:** định nghĩa 15 lá theo Rausch + network/flaky/infra, quy ước Q1–Q3, quy ước "nguyên nhân sớm nhất". Đầu ra có cấu trúc `{lá, dòng bằng chứng}`.
- **Tập người gán:** 203 run vòng mù 10/10, nhãn tầng 2 sau phân xử, bỏ `unclear`.
- **Tập nhãn quy tắc:** 351 run, 25 run mỗi lá (lấy ngẫu nhiên, phân tầng theo lá), chạy cả log nguyên vẹn và log đã che.
  - So với quy tắc, TF-IDF A, lai CE, lai + sampler HCL trên đúng các run đó; mỗi run dùng mô hình của fold có run đó ở test.
  - Mẫu cân bằng theo lá nên **lá hiếm nặng ký hơn** so với phân bố thật.

## Kết quả

**Tập người gán (tầng 2, n = 203)**

| | acc | macro-F1 | compile | dependency | infra | lint | test | flaky |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| LLM | 0,842 | 0,714 | 0,88 | 0,89 | 0,81 | 0,89 | 0,81 | 0 |
| Quy tắc | 0,877 | 0,872 | 0,91 | 0,86 | 0,85 | 1,00 | 0,94 | 0,67 |

- Trong 16 run quy tắc để `?`, LLM gán đúng **8**.
- **Lưu ý:** quy tắc được lợi trên tập này.
  - Người phân xử đã thấy nhãn quy tắc.
  - Các lỗi quy tắc tìm ra ở tập này đã được sửa sau đó.
- Bỏ flaky (4 run) thì macro-F1 của LLM khoảng 0,86, của quy tắc khoảng 0,91.

**Tập nhãn quy tắc (n = 351 mỗi cột, cân bằng theo lá)**

| Mô hình | Lá, nguyên vẹn | Tầng 2, nguyên vẹn | Lá, đã che | Tầng 2, đã che |
|---|---:|---:|---:|---:|
| Quy tắc | 0,999 | 0,997 | 0,437 | 0,581 |
| TF-IDF A | 0,461 | 0,582 | 0,388 | 0,534 |
| Lai CE | 0,484 | 0,597 | 0,439 | 0,575 |
| Lai + sampler HCL | 0,509 | 0,656 | 0,464 | **0,625** |
| **LLM** | **0,719** | **0,729** | **0,610** | 0,616 |

Đây là macro-F1. Trên log nguyên vẹn, quy tắc gần 1 theo định nghĩa (nhãn tham chiếu chính là nhãn quy tắc).

F1 theo lá của LLM (nguyên vẹn / đã che):

| Lá | F1 |
|---|---|
| compile | 0,96 / 0,87 |
| quality | 0,90 / 0,85 |
| license | 0,98 / 0,61 |
| compatibility | 0,98 / 0,98 |
| doc | 0,84 / 0,81 |
| buildconfig | 0,81 / 0,62 |
| git | 0,81 / 0,81 |
| crash | 0,85 / 0,80 |
| network | 0,70 / 0,50 |
| dependency | 0,62 / 0,52 |
| infra | 0,51 / 0,37 |
| testfailure | 0,50 / 0,42 |
| itestfailure | 0,43 / 0,42 |
| flaky | 0,21 / 0,08 |

## Nhận xét

1. **LLM rẻ, không huấn luyện, vượt các mô hình của đề tài ở mức lá trên mẫu cân bằng:**
   - Mức lá: +0,21 trên log nguyên vẹn, +0,15 trên log đã che so với mô hình tốt nhất.
   - Phần hơn đến chủ yếu từ **lá hiếm** (license, compatibility, doc, buildconfig, git): LLM có sẵn kiến thức về các công cụ này, còn mô hình của đề tài thiếu mẫu để học.
2. **Ở tầng 2 trên log đã che, mô hình lai + sampler HCL ngang LLM** (0,625 so với 0,616).
3. **LLM yếu đúng ở các chỗ cần quy ước riêng hoặc thông tin ngoài log:**
   - testfailure / itestfailure: quy tắc tách theo tên workflow.
   - dependency: ranh giới Q1–Q3.
   - infra.
   - flaky: cần biết kết quả chạy lại.
4. **So với người gán, LLM không đúng hoàn toàn:** acc 0,84, thấp hơn quy tắc. Kết quả này trả lời trực tiếp câu hỏi ban đầu.
5. **Giới hạn:**
   - Một mô hình, một lần chạy, zero-shot.
   - Mẫu cân bằng làm phóng đại vai trò lá hiếm.
   - Nhãn tham chiếu của tập 351 run là nhãn quy tắc.

## Bản 2: prompt ghi rõ quy ước của đề tài (task `p3-llm-baseline-v2`, $1,07)

- **Prompt bổ sung:**
  - thứ tự ưu tiên buildconfig > compile > dependency > lint > test > flaky > infra;
  - tách itest theo tên (đúng regex trong `fine_labels.IT`);
  - ranh giới dependency / network (Q1–Q3);
  - dấu hiệu cụ thể của từng lá infra, theo đúng thứ tự khớp của quy tắc;
  - flaky chỉ khi log ghi rõ.
- **Kết quả:** `data/llm_baseline/llm_preds_v2.parquet`, `scores_v2.csv`. Bản 1 đổi tên thành `*_v1`.

| Tập | Chỉ số | Bản 1 | Bản 2 |
|---|---|---:|---:|
| Người gán, n = 203 | acc tầng 2 | 0,842 | 0,833 |
| | macro-F1 tầng 2 | 0,714 | 0,707 |
| Nhãn quy tắc, nguyên vẹn | macro-F1 lá | 0,719 | 0,679 |
| | macro-F1 tầng 2 | 0,729 | 0,730 |
| Nhãn quy tắc, đã che | macro-F1 lá | 0,610 | 0,646 |
| | macro-F1 tầng 2 | 0,616 | 0,670 |

- Bản 2 giảm ở lá trên log nguyên vẹn chủ yếu do androidsdk (chỉ 2 run: 0,67 → 0).
- testfailure / itestfailure không cải thiện dù quy tắc tách đã ghi rõ (0,48 / 0,47).
  - Xem từng run thì phần lớn chênh lệch nằm ở **chính nhãn quy tắc thô**: workflow "UTCase and ITCase" khớp mẫu IT cho mọi test; "functional tests" bị xếp testfailure.
  - **Precision tầng 3 của quy tắc chưa được đo bằng người**, nên điểm mức lá so với nhãn quy tắc có trần không rõ.

## So trên nhãn người, cùng run (187 run quy tắc gán được, có dự đoán chéo repo của mô hình)

| Mô hình | acc tầng 2 | macro-F1 tầng 2 |
|---|---:|---:|
| Quy tắc (được lợi, xem trên) | 0,952 | 0,906 |
| Lai CE | 0,877 | 0,738 |
| LLM bản 1 | 0,872 | 0,733 |
| LLM bản 2 | 0,866 | 0,730 |
| Lai + sampler HCL | 0,866 | 0,726 |
| TF-IDF A | 0,861 | 0,722 |

## Kết luận

1. **Ghi quy ước vào prompt gần như không giúp LLM.** Bản 2 ≈ bản 1 trên nhãn người; chỉ tăng trên log đã che.
2. **Ở tầng 2 trên nhãn người, mô hình của đề tài ngang LLM** (0,87–0,88), kể cả TF-IDF.
3. **Lợi thế của LLM nằm ở lá hiếm** (license, compatibility, doc, buildconfig, git, crash), nhờ kiến thức sẵn có về công cụ, cùng ở log đã che.
4. **Hướng kết hợp hợp lý:**
   - Mô hình cục bộ quyết định tầng 1–2 và các lá đông.
   - Chỉ gửi LLM những run mô hình không chắc hoặc nghi lá hiếm.
