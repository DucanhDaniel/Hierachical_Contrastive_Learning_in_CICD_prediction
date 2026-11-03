# Project Description

## Project3 — Phân loại nguyên nhân lỗi build CI bằng học tương phản phân cấp

**Hierarchical Contrastive Learning for CI Build Failure Classification**

---

### Tổng quan

Project3 là dự án nghiên cứu phân loại loại lỗi của các lần chạy **GitHub Actions bị thất bại trên dự án Java/Kotlin**. Hệ thống đọc log, kết hợp ngữ cảnh CI và đặc trưng tóm tắt thay đổi mã nguồn để trả về nhãn theo cây ba tầng: **artifact chứa lỗi → thời điểm cần sửa → loại lỗi**.

Kết quả hướng tới hỗ trợ lập trình viên và nhóm DevOps xác định lỗi thuộc dự án hay môi trường CI, lựa chọn hướng xử lý và tìm nhanh các dòng log liên quan. Dự án gồm pipeline thu thập dữ liệu, gán nhãn bằng quy tắc, rà soát thủ công, huấn luyện mô hình và đánh giá thực nghiệm.

---

### Bài toán giải quyết

Khi CI thất bại, người phát triển phải đọc log dài và phân tán qua nhiều job, step để xác định nguyên nhân. Các lỗi có biểu hiện gần nhau nhưng cách xử lý khác nhau: lỗi tải phụ thuộc do mạng khác với khai báo sai phụ thuộc; test lỗi thực sự khác với test chập chờn.

Dự án tập trung vào các khó khăn sau:

- Phân loại lỗi sau khi CI đã chạy, với log là nguồn thông tin chính.
- Tổ chức nhãn gắn với hành động: sửa code, kiểm tra build local, xem test tích hợp, sửa cấu hình CI hoặc cân nhắc chạy lại.
- Khai thác quan hệ cha–con giữa các loại lỗi và xử lý mất cân bằng giữa các nhãn.
- Đánh giá khả năng áp dụng trên repository chưa xuất hiện trong tập huấn luyện.
- Đo giá trị bổ sung so với bộ quy tắc, nhất là các trường hợp chưa gán được nhãn hoặc thiếu bằng chứng trong log.

---

### Giải pháp kỹ thuật

**Thu thập và chuẩn bị dữ liệu**

- Thu thập workflow run, job và log từ sự kiện pull request và push; hỗ trợ checkpoint, thử lại và cập nhật tăng dần.
- Gán nhãn bằng quy tắc kèm bằng chứng; giữ `?` cho trường hợp chưa xác định được, kết hợp gán nhãn mù và phân xử của con người.
- Xây dựng dataset mức run, chia log thành đoạn, liên kết commit diff và lưu ở định dạng Parquet.
- Đóng gói dữ liệu, cây nhãn và mã mô hình để chạy trên local, Kaggle hoặc Colab.

**Mô hình phân loại**

- **UniXcoder** mã hóa các đoạn log quanh vị trí lỗi và ngữ cảnh CI.
- **Attention phân cấp** tổng hợp đoạn → job → run; tùy chọn attention theo dòng để lấy điểm chú ý của từng dòng log.
- **Đặc trưng có cấu trúc** bổ sung giai đoạn/công cụ xảy ra lỗi và thông tin tóm tắt diff.
- **Ba đầu phân loại** học nhãn ở ba tầng; so sánh cross-entropy với HCL, tương phản mềm theo cây và tương phản theo nguyên mẫu phân cấp.
- **MC Dropout và định tuyến theo độ tin cậy** hỗ trợ nhận diện trường hợp cần người xem lại.

**Kiến trúc hệ thống**

| Thành phần | Công nghệ / phương pháp |
|------------|-------------------------|
| Ngôn ngữ và quản lý môi trường | Python, uv, `pyproject.toml`, `uv.lock` |
| Thu thập dữ liệu | GitHub REST API, Requests, Git |
| Xử lý và lưu dữ liệu | DuckDB, pandas, PyArrow, Parquet, JSON/JSONL |
| Mô hình học sâu | PyTorch, Transformers, `microsoft/unixcoder-base` |
| Baseline | Quy tắc, TF-IDF với bộ phân loại tuyến tính, LLM |
| Môi trường thí nghiệm | Local, Kaggle, Google Colab |
| Giao diện demo thử nghiệm | Gradio, tùy chọn ngrok để truy cập từ xa |
| Kiểm thử | Python unittest |

---

### Tính năng chính

**Chuẩn bị và kiểm soát dữ liệu**

- Chạy pipeline từ danh sách repository đến dataset phục vụ thí nghiệm.
- Thu thập tiếp từ checkpoint, theo dõi dữ liệu đã có và xử lý lỗi mạng/API.
- Gán nhãn có bằng chứng, lấy mẫu kiểm chứng và đánh giá đề xuất quy tắc ngoại tuyến trước khi tích hợp.
- Xuất dataset mức commit/run và gói mô hình độc lập cho môi trường GPU.

**Huấn luyện và đánh giá**

- Huấn luyện các biến thể `ce`, `hcl`, `soft`, `proxy` trên cùng pipeline mô hình.
- Đánh giá chéo repository bằng năm fold; báo cáo macro-F1 ở từng tầng.
- So sánh log nguyên vẹn với log đã che dòng bằng chứng của quy tắc.
- Chạy ablation về đặc trưng diff/CI, cách chọn đoạn log, attention và cấu trúc phân cấp.
- Lưu dự đoán, biểu diễn, trọng số attention và checkpoint để phân tích sau thí nghiệm.

**Demo hỗ trợ phân tích lỗi**

- Nhập URL của một run GitHub Actions thất bại hoặc chọn ví dụ đã lưu log.
- Hiển thị nhãn ba tầng, gợi ý xử lý, độ tin cậy và các dòng log được mô hình chú ý.
- Cần gói dữ liệu demo và checkpoint được chuẩn bị riêng; mã demo nằm trong `src/project3/demo/`.
- Gợi ý hành động là đầu ra hỗ trợ quyết định; demo không tự chạy lại workflow hay thay đổi quyền merge.

**Luồng xử lý**

```text
GitHub Actions thất bại
    → Thu thập log, ngữ cảnh CI và diff
    → Gán nhãn quy tắc / con người kiểm chứng
    → Chuẩn hóa dataset và đóng gói dữ liệu
    → UniXcoder + attention + học phân cấp
    → Artifact chứa lỗi / thời điểm cần sửa / loại lỗi
    → Gợi ý hành động + dòng log liên quan + độ tin cậy
```

---

### Quy mô và phạm vi

- **Đơn vị phân loại:** một run GitHub Actions thất bại; phạm vi chính là dự án Java/Kotlin.
- **Cây nhãn hiện hành:** hai artifact, năm nhóm thời điểm cần sửa và 15 loại lỗi chi tiết.

| Artifact chứa lỗi | Thời điểm cần sửa | Loại lỗi |
|-------------------|-------------------|----------|
| Dự án | Khi viết code | `compile`, `quality`, `doc`, `buildconfig` |
| Dự án | Build local trước push | `testfailure`, `license`, `compatibility`, `dependency` |
| Dự án | CI trước merge | `itestfailure`, `flaky` |
| Môi trường CI | Sửa cấu hình CI | `git`, `androidsdk`, `infra` |
| Môi trường CI | Chạy lại | `network`, `crash` |

- **Cấu hình đánh giá:** năm fold theo repository; mỗi lượt dùng ba fold huấn luyện, một fold validation và một fold test.
- **Nguồn đối chiếu:** bộ quy tắc, TF-IDF và baseline LLM; nhãn do người gán dùng để kiểm chứng độc lập.
- **Giới hạn:** số run, repository, nhãn được giữ và điểm mô hình phụ thuộc từng snapshot. Gói mô hình có thể bỏ các lá quá ít mẫu; `label_tree.json` ghi nhận tập nhãn thực tế.
- **Trạng thái:** dự án nghiên cứu và demo, cần dữ liệu cùng trọng số riêng để chạy mô hình. Hướng dự đoán kết quả CI trước khi chạy từ diff được lưu tại `legacy/`.

Hướng dẫn cài đặt và các lệnh sử dụng nằm trong [README.md](README.md). Chi tiết cây nhãn nằm trong [tài liệu thiết kế nhãn](docs/cay-nhan-3-tang-2026-10-25.md).
