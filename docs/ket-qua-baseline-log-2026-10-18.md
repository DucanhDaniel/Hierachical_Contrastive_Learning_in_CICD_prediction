# Baseline phân loại lỗi từ log — 18/10/2026

Bước 2 trong [huong-moi-phan-loai-sau-ci.md](huong-moi-phan-loai-sau-ci.md).

- **Code:** [log_baselines.py](../src/project3/model/baselines.py).
- **Kết quả:** `data/results/log_baselines/` (results.json, report.md, preds.parquet).
- **Dữ liệu:** `data/run_dataset` (rule version `2026-10-18-dependency-q1q3`), gồm 43.616 run fail có nhãn quy tắc và có log, 100 repo đợt 1.

## Cách đo

- **Chia chéo repo:** 5 fold theo `repo_fold`; gộp dự đoán của 5 fold rồi tính điểm.
- **Chia theo thời gian:** theo `split_time`.
- **Che bằng chứng (test "masked"):** xoá mọi dòng chứa dòng bằng chứng mà quy tắc dùng để gán nhãn (43.615/43.616 run có dòng này).
  - Phần còn lại của log giữ nguyên.
  - Test đã che **mô phỏng** run mà quy tắc không bắt được. Đây là mô phỏng, không phải nhóm `?` thật.
- **Quy tắc:** chạy lại `gold_label` trên đoạn log đã cắt (để kiểm tra việc cắt không làm mất bằng chứng) và trên log đã che.
- **TF-IDF:**
  - Đặc trưng: từ + cặp từ, 300k đặc trưng, tối đa 30.000 ký tự cuối mỗi run.
  - Bộ phân loại: logistic regression (SGD, log-loss, class_weight balanced), phân loại ở mức lá; tầng 2 và tầng 1 suy ngược từ lá.
  - Hai cách train: log nguyên vẹn (`full`), hoặc che bằng chứng ở 50% mẫu train (`mix50`).
- **Nhãn tham chiếu:** chính là nhãn quy tắc. Trên test nguyên vẹn, quy tắc vì thế gần như đúng 100% theo định nghĩa.

## Kết quả

| Chia | Mô hình | Test | acc lá | macro-F1 lá | macro-F1 tầng 2 | macro-F1 tầng 1 |
|---|---|---|---:|---:|---:|---:|
| chéo repo | quy tắc | nguyên vẹn | 0,999 | 0,996 | 0,999 | 0,999 |
| chéo repo | quy tắc | **đã che** | 0,559 | 0,446 | 0,579 | 0,692 |
| chéo repo | TF-IDF full | nguyên vẹn | 0,767 | 0,558 | 0,726 | 0,892 |
| chéo repo | TF-IDF full | đã che | 0,705 | 0,457 | 0,623 | 0,801 |
| chéo repo | TF-IDF mix50 | nguyên vẹn | 0,761 | 0,561 | 0,724 | 0,884 |
| chéo repo | **TF-IDF mix50** | **đã che** | **0,718** | **0,487** | **0,667** | **0,818** |
| thời gian | quy tắc | đã che | 0,570 | 0,420 | 0,572 | 0,672 |
| thời gian | TF-IDF full | nguyên vẹn | 0,913 | 0,783 | 0,847 | 0,946 |
| thời gian | TF-IDF mix50 | đã che | 0,895 | 0,748 | 0,813 | 0,927 |

F1 theo lá, chéo repo:

| Lá | quy tắc, đã che | TF-IDF mix50, nguyên vẹn | TF-IDF mix50, đã che |
|---|---:|---:|---:|
| testfailure | 0,80 | 0,77 | 0,76 |
| compile | 0,81 | 0,89 | 0,84 |
| quality | 0,42 | 0,86 | 0,83 |
| itestfailure | 0,73 | 0,42 | 0,42 |
| crash | 0,72 | 0,80 | 0,51 |
| dependency | 0,48 | 0,81 | 0,74 |
| network | 0,54 | 0,67 | 0,60 |
| license | 0,13 | 0,66 | 0,27 |
| buildconfig | 0,86 | 0,79 | 0,68 |
| git | 0,58 | 0,83 | 0,79 |
| doc | 0,44 | 0,58 | 0,57 |
| flaky / compatibility / androidsdk | ≈ 0 | 0 | 0 |

## Nhận xét

1. **Cắt đoạn không làm mất bằng chứng:** quy tắc chạy trên đoạn đã cắt vẫn khớp nhãn 99,9%.
2. **Khi mất dòng then chốt, mô hình học được hơn quy tắc:**
   - Chéo repo: macro-F1 tầng 2 là 0,667 so với 0,579.
   - Theo thời gian: 0,813 so với 0,572.
   - Train có che (`mix50`) giúp trên test đã che (+0,04 tầng 2 chéo repo) mà gần như không mất điểm trên test nguyên vẹn.
   - Đây là bằng chứng đầu tiên cho lập luận "mô hình gán được chỗ quy tắc bỏ sót", nhưng mới trên mô phỏng. Cần xác nhận trên run `?` do người gán.
3. **Chéo repo khó hơn nhiều so với theo thời gian** (acc 0,77 so với 0,91). TF-IDF phần lớn học thuộc từ vựng của từng repo. Đây là khoảng trống để encoder tiền huấn luyện và HCL chứng minh giá trị.
4. **itestfailure thấp (0,42):** lá này do quy tắc xác định từ **tên workflow/job** (mẫu IT/e2e), không phải từ log. Mô hình chỉ đọc log thì không phân biệt được. Như vậy ô "ngữ cảnh CI: tên workflow / job / step" trong kiến trúc là bắt buộc.
5. **license giảm mạnh khi che** (0,66 → 0,27): bằng chứng license thường chỉ có một dòng (`Unapproved`, `RAT`).
6. **Lá quá ít mẫu hoặc chỉ có ở 1–5 repo** (flaky, compatibility, androidsdk) không học được khi chia chéo repo. Đúng như dự kiến, các lá này nên để `−1` ở tầng 3 và chỉ học ở tầng 2.

## Giới hạn

- **Nhãn tham chiếu là nhãn quy tắc:** điểm trên test nguyên vẹn đo mức bắt chước quy tắc, không phải độ đúng thật.
- **Test đã che chỉ là mô phỏng:** quy tắc có thể vẫn tìm thấy dòng khớp thứ hai trong log. Run `?` thật có thể khác (log bị cắt, lỗi lạ).
- **Chưa có diff:** đang chờ 32.445 commit lấy diff trên Kaggle. Chưa dùng tên workflow/job/step làm đặc trưng.

## Việc tiếp theo

- Thêm tên workflow/job/step vào TF-IDF, để đo riêng đóng góp của ngữ cảnh CI.
- UniXcoder + CE phẳng, rồi + HCL, trên cùng cách chia (Kaggle GPU), cấu hình chỉ log và log + diff.
- Tập test do người gán: `blind3` + mẫu run `?`.
