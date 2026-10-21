# Hướng mới: phân loại loại lỗi CI sau khi run (16/10/2026)

## 1. Quyết định

- Dự đoán build success/failed **không còn là pain point**, nên bỏ khỏi mục tiêu chính.
- Đóng góp chính là **xác định nhãn loại lỗi** theo cây 3 tầng: nhóm (build/test/env) → loại → lá Rausch.
- Việc xác định được làm **sau CI run**:
  - Đầu vào: log của run fail, có thể kèm diff và lịch sử commit.
  - Đầu ra: nhãn phân cấp, ví dụ `fail/build/lint/quality`.

## 2. Vì sao không làm trước run

- Đoán loại lỗi trước khi chạy thực chất vẫn là dự đoán pass/fail, chỉ chia nhỏ hơn. Bỏ pass/fail thì bài toán trước run mất lý do tồn tại.
- Đoán "nếu commit fail thì fail kiểu gì" không dẫn tới hành động nào khi CI chưa chạy.
- Đọc diff trước run chỉ đạt macro-F1 khoảng 0,49 (`legacy/.../pilot/type_feasibility.py`). Nhãn được rút ra từ log, nên log là tín hiệu trực tiếp, còn diff chỉ là tín hiệu gián tiếp.

## 3. Pain point sau run: rerun hay sửa code

Khi run fail, developer phải đọc hàng nghìn dòng log để tìm nguyên nhân. Câu hỏi đầu tiên là có nên rerun không. Cây nhãn trả lời đúng câu này:

| Nhánh / lá | Hành động |
|---|---|
| infra: network, crash, git, androidsdk; flaky | rerun, không phải lỗi của commit |
| buildconfig, compile, dependency | sửa cấu hình build hoặc code |
| lint: quality, license, doc, compatibility | sửa format, header, tài liệu, API |
| testfailure, itestfailure | debug test |

Ranh giới khó nhất (testfailure với flaky, dependency với network) cũng là chỗ có giá trị nhất.

## 4. Rủi ro chính và cách đo đóng góp

Rủi ro: hội đồng có thể hỏi "regex đã gán nhãn từ log rồi, cần mô hình làm gì?". Nhãn huấn luyện do quy tắc gán trên chính log đó, nên nếu chỉ đánh giá trên các run quy tắc đã gán được, mô hình chỉ học lại regex.

Vì vậy đóng góp phải được đo ở những chỗ quy tắc không làm được:

1. **Run quy tắc để `?`:** khoảng 29% commit fail có log chưa có nhãn (31.769 / 44.532 có nhãn).
   - Gán mù một mẫu từ nhóm này làm tập test.
   - Đo mô hình trên tập đó.
2. **Ranh giới khó ở tầng 3:** testfailure với itestfailure, test với flaky, dependency với network.
3. **Repo chưa thấy khi huấn luyện:** chia train/test theo repo, vì regex viết theo repo cụ thể thường không chuyển sang repo mới được.
4. **HCL:** kiểm tra xem cây phân cấp có giúp các lá hiếm (license, doc, buildconfig, git, compatibility) so với CE phẳng không.

Ràng buộc C-02 vẫn giữ: nhãn của tập test do người gán, LLM không phải nguồn nhãn.

## 5. Thay đổi so với kế hoạch cũ

| Thành phần | Cũ (trước run) | Mới (sau run) |
|---|---|---|
| Đặt vấn đề | Dự đoán build fail và loại lỗi từ commit | Phân loại nguyên nhân lỗi CI theo cây nhãn |
| Đầu vào chính | Diff (hunk), lịch sử | Hai nhánh: log run fail (cắt thành đoạn) và code diff của commit (hunk) |
| Bước ① kiến trúc | Cắt diff thành hunk | Cắt log thành đoạn (theo step/job, bỏ dòng nhiễu, giữ phần quanh dòng lỗi) và cắt diff thành hunk như cũ; một UniXcoder dùng chung |
| Gộp phân cấp | hunk → file → commit | đoạn → job → run (vector r) và hunk → file → commit (vector c), ghép r + c + ngữ cảnh CI |
| Đầu ra | 4 lớp: pass/compile/lint/test | Nhãn cây 3 tầng; không còn lớp pass |
| Diff và lịch sử | Đầu vào chính | Diff là nhánh thứ hai (18/10/2026); lịch sử và tên workflow/job/step là ngữ cảnh 64 số |
| Tập đánh giá | Chia theo thời gian, nhãn quy tắc | Nhãn người (gồm cả run quy tắc để `?`), có tách theo repo |

Giữ nguyên:
- Cây nhãn (`docs/khung-nhan-loi-build.md`).
- Đầu phân loại và đầu so sánh (SupCon theo từng tầng).
- Dữ liệu 100 repo trong `data/dataset/`.

## 6. Kết quả trước run được giữ lại

Kết quả đọc diff không bỏ đi. Từ 18/10/2026, diff là **nhánh thứ hai** của mô hình (slide Phụ lục A), không chỉ là ablation.

Diff có những tín hiệu log không có:
- **Tách flaky/network khỏi lỗi thật:** test fail mà diff không đụng code liên quan thì nghiêng về flaky/network.
- **dependency/buildconfig:** commit sửa `pom.xml` hay `build.gradle` là tín hiệu mạnh.
- **Log bị cắt:** run mà quy tắc để `?` vì log chỉ còn `BUILD FAILED` thì diff là tín hiệu còn lại.

Diff đã lấy xong cho 99,9% commit, encoder hunk → file → commit đã có code.

Thí nghiệm bắt buộc: **chỉ log · chỉ diff · log + diff**. Kết quả trả lời diff đóng góp thêm bao nhiêu khi đã có log, và log đóng góp bao nhiêu so với kết quả đọc diff cũ.

## 7. Việc tiếp theo

1. **Cắt log thành đoạn:** viết bước này và lưu các đoạn vào dataset, gắn với run_id và job.
2. **Dựng tập test người gán:**
   - Gán mù xong `data/human_labels/blind3/` (147 run).
   - Thêm một mẫu từ nhóm run quy tắc để `?`.
3. **Chạy baseline:**
   - Quy tắc.
   - TF-IDF + logistic regression trên log.
   - Encoder + CE phẳng.
4. **Huấn luyện HCL trên log** và so với các baseline ở mục 4 (trên Kaggle).
5. **Cập nhật tài liệu:** đặc tả (`docs/dac-ta-yeu-cau-agile.md`) và báo cáo tuần theo đặt vấn đề mới.

## Tham khảo

- Rausch et al., *An Empirical Analysis of Build Failures in the CI Workflows of Java-Based OSS* (MSR 2017): bảng II các loại lỗi, nguồn của lá tầng 3.
- Brandt et al., *LogChunks* (MSR 2020): trích đoạn log chứa nguyên nhân lỗi.
