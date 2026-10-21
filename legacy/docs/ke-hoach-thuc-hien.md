# Kế hoạch thực hiện (cập nhật 10/10/2026)

Đề tài: Dự đoán và phân loại lỗi build CI/CD bằng Hierarchical Contrastive Learning. SV: Phạm Đức Anh (20235008), GVHD: TS Vũ Thị Hương Giang.

## 1. Mục tiêu trước mắt: buổi duyệt thứ 6, 16/10/2026

Hội đồng chưa đánh giá thuật toán. Buổi duyệt tới chấm **dữ liệu** và **tính ứng dụng**. Cần mang tới:

| # | Sản phẩm | Đáp ứng yêu cầu nào của hội đồng | Người làm |
|---|---|---|---|
| 1 | Dataset ≥ 100 repo Java/JVM, có diff + log thật, kèm bảng độ phủ | Dữ liệu "ba con số", có diff và log | Codex crawl, Claude lấy diff và thống kê |
| 2 | Pipeline một lệnh, demo trực tiếp trên 1–2 repo | Pipeline tự động end-to-end, I/O rõ ràng | Claude |
| 3 | Bảng quy tắc gán nhãn + độ chính xác so với nhãn người (≥ 200 run) | Nhãn bằng quy tắc kiểm chứng được, không dùng LLM | Claude dựng công cụ, **bạn gán tay** |
| 4 | Đặc tả use case + số phút báo lỗi sớm hơn (mô phỏng) | Actor, thời điểm can thiệp, giá trị thêm | Claude |
| 5 | Bảng baseline (tỉ lệ lớp, heuristic, chỉ metadata, TF-IDF, CE) | Chứng minh mô hình học từ diff | Đã có, chạy lại nếu kịp trên dữ liệu mới |
| 6 | Slide cập nhật theo các mục trên | — | Claude soạn, bạn duyệt |

## 2. Lịch theo ngày

| Ngày | Codex | Claude | Bạn |
|---|---|---|---|
| **T7 10/10** | Bắt đầu crawl PR cho 85 repo mới (`docs/codex/task-crawl-100-repo.md`) | Chọn 100 repo (xong); nén diff cũ, sửa lấy diff theo từng repo (đang chạy); file kế hoạch này | Giao task cho Codex |
| **CN 11/10** | Crawl PR + push | Pipeline một lệnh (US-30); công cụ gán tay mù (US-08) | Bắt đầu gán tay trên 17 repo cũ |
| **T2 12/10** | Crawl. **22:00 kiểm tra**: chưa xong một nửa thì giảm còn 60 ngày | Mô phỏng báo lỗi sớm (US-32); demo pipeline trên 1–2 repo; lấy diff cho repo đã crawl xong | Gán tay (mục tiêu ~100 run) |
| **T3 13/10** | Crawl, thêm quy tắc cho Kotlin/Android từ các nhãn `?` | Lấy diff tiếp; tính độ chính xác quy tắc trên phần đã gán | Gán tay (đủ ~200 run, có cả repo mới) |
| **T4 14/10** | **22:00 dừng crawl**; gán nhãn, gộp commit | Lấy diff phần còn lại | — |
| **T5 15/10** | Báo cáo độ phủ (`bao-cao-crawl.md`) | Thống kê độ phủ + độ chính xác nhãn; soạn slide; nếu kịp, chạy lại bảng baseline trên dữ liệu mới (CPU) | Duyệt slide, tập thuyết trình |
| **T6 16/10** | — | Chỉnh sửa cuối | **Buổi duyệt** |

## 3. Trạng thái hiện tại

| Hạng mục | Trạng thái |
|---|---|
| Crawl 17 repo (run, job, step, log), 90 ngày | Xong |
| Diff cho 26.883 commit | Xong (đang nén `.diff` → `.diff.gz`) |
| Nhãn tầng 2 bằng quy tắc regex trên log, có dòng bằng chứng | Xong cho 17 repo |
| Nhãn tầng 3 (dạng lỗi chi tiết, module) | Xong (`pilot/fine_labels.py`) |
| Danh sách 85 repo mới | Xong (`configs/repos_100.txt`, lý do ở `data/processed/repo_selection.csv`) |
| Crawl 85 repo mới | Chờ Codex bắt đầu |
| Pipeline một lệnh | Chưa (các bước đã có, chưa nối) |
| Tập nhãn người | Chưa. Mẫu 103 run cũ không tính là nhãn người độc lập |
| Kiểm chứng ngoài bằng LogChunks | Đã thử: quy tắc khớp 31/60 log JVM; thiếu sbt/ScalaTest, có vài dương tính giả (`crawl/logchunks_eval.py`) |
| Nguồn log cũ GHALogs (log từ 2023, tải từng run qua HTTP Range) | Đang thử (`pipeline/ghalogs.py`), dự phòng nếu crawl thiếu |
| Use case | Có nội dung trong `docs/dac-ta-yeu-cau-agile.md` mục 1.2, chưa có số đo giá trị |
| Thí nghiệm mô hình (11 repo) | Xong 4 lượt trên Kaggle. Đọc diff hơn các baseline; HCL ngang CE |

## 4. Kế hoạch ổ đĩa

Ổ D còn khoảng 24 GB. Dữ liệu cần giữ sau khi nén cho 100 repo ước khoảng 4–6 GB.

| Việc | Tác dụng |
|---|---|
| Diff lưu `.diff.gz` (nén 5,8 lần) | 3,4 GB còn ~0,6 GB; diff 100 repo ~3 GB |
| Lấy diff theo từng repo, xoá clone ngay sau đó (`fetch_diffs --cleanup`) | Đĩa chỉ chứa 1 clone (~100–130 MB) tại một thời điểm thay vì ~10 GB |
| Clone và diff của repo mới đặt ở ổ C (còn ~138 GB) | Không tranh chỗ với dữ liệu crawl trên ổ D |
| Log nén được 5,2 lần | Làm sau nếu cần thêm chỗ |
| `data/gharuns/` (8,2 GB) | **Chờ bạn quyết định**: xoá (có lại từ Zenodo) hoặc chuyển sang ổ C. Thống kê cần cho việc chọn repo đã lưu ở `data/processed/gharuns_repo_stats.parquet` |

## 5. Rủi ro và phương án dự phòng

| Rủi ro | Dấu hiệu | Phương án |
|---|---|---|
| Crawl không kịp 85 repo | Tối T2 12/10 chưa xong một nửa | Giảm còn 60 ngày cho repo còn lại; trình bày số repo đã xong + pipeline chạy được cho phần còn lại |
| Quy tắc gán nhãn kém trên repo Kotlin/Android | Tỉ lệ nhãn `?` cao ở repo mới | Thêm quy tắc (ktlint, detekt, Android Lint); báo cáo độ chính xác riêng cho Java và Kotlin |
| Không đủ thời gian gán tay 200 run | Đến T3 13/10 dưới 100 run | Trình bày độ chính xác trên số run đã gán, nói rõ cỡ mẫu và khoảng tin cậy |
| Hết dung lượng ổ D | Còn dưới 5 GB | Chuyển `data/gharuns/` sang ổ C; nén log |
| Rate limit GitHub do nhiều tiến trình dùng chung token | Crawl dừng chờ liên tục | Chạy PR trước, push sau, không song song |

## 6. Sau buổi duyệt (dự kiến)

| Giai đoạn | Việc |
|---|---|
| Sprint 2 (tuần 6–10) | Chạy lại bảng baseline và HCL trên dataset 100 repo (Kaggle); thêm baseline XGBoost, GitSense, SupCon 1 tầng; ablation và hình không gian embedding; thí nghiệm xác nhận trên dữ liệu tương lai từ crawl hằng tuần (kiểm định chốt trước) |
| Sprint 3 (tuần 11–14) | API `/predict`, bot comment PR cho Reviewer, mô phỏng giá trị trên dữ liệu mới; báo cáo cuối kỳ |

Chi tiết epic, user story và acceptance criteria: `docs/dac-ta-yeu-cau-agile.md`. Task crawl cho Codex: `docs/codex/task-crawl-100-repo.md`.
