# Đặc tả yêu cầu theo Agile – Hệ thống dự đoán và phân loại lỗi build CI/CD bằng HCL

> Căn cứ: slide giới thiệu đề tài (W1), feedback của hội đồng ở buổi duyệt, mã nguồn hiện có trong `src/project3/` và kết quả thí nghiệm trong `data/processed/hcl_full/`.
> Cập nhật: 10/10/2026.

## 0. Thay đổi theo feedback của hội đồng

| Feedback | Thay đổi trong đặc tả |
|---|---|
| Dữ liệu phải có code diff và log chạy thật, không chỉ pass/fail | Nguồn chính là crawl GitHub Actions API kèm log + diff lấy bằng git (EP-01). GHARuns chỉ dùng để chọn repo |
| 20 repo không đủ, cần "ba con số" | Mục tiêu ≥ 100 repo Java/JVM, có thống kê độ phủ (US-05, US-31) |
| Không chấp nhận LLM tự gán nhãn | Nhãn chỉ từ bộ quy tắc trên log. LLM (nếu dùng) chỉ là phương pháp so sánh với nhãn người, không phải nguồn nhãn (ràng buộc C-02) |
| Phải demo pipeline end-to-end tự động, I/O rõ ràng | Thêm US-30 (một lệnh chạy toàn bộ pipeline) và mục 2 (đầu vào / đầu ra) |
| Bộ quy tắc gán nhãn phải kiểm chứng được | US-08 đổi thành tập nhãn do người gán mù ≥ 200 run, đo precision/recall/kappa |
| Ai là người dùng thật, can thiệp lúc nào, giá trị thêm là gì | Actor chính đổi thành Reviewer/Maintainer; mục 1.2 đặc tả use case; thêm US-32 đo giá trị bằng mô phỏng |
| Phải có baseline chứng minh mô hình học từ diff | EP-03 bắt đầu bằng bảng baseline (tỉ lệ lớp, heuristic, chỉ metadata, TF-IDF diff), sau đó mới tới HCL |

## 1. Actor và use case

### 1.1 Actor

| Actor | Mô tả | Tương tác với khối (slide 13) |
|---|---|---|
| **Reviewer / Maintainer** (actor chính) | Người review PR và quyết định merge, thường là leader hoặc maintainer của repo. Dùng dự đoán loại lỗi để triage và quyết định có chờ CI hay yêu cầu sửa trước. | Tích hợp & hiển thị (bot PR, dashboard) |
| **Developer** | Người push code hoặc mở PR. Nhận cảnh báo sớm loại lỗi có thể gặp để tự kiểm tra trước khi reviewer xem. Không phải người quyết định merge. | Tích hợp & hiển thị (bot PR) |
| **Admin hệ thống** | Vận hành dịch vụ: cài webhook/GitHub App, cấu hình repo và ngưỡng, triển khai/rollback model, giám sát, quản lý secret và tài khoản. | Phục vụ, Tích hợp & hiển thị |
| **Admin dữ liệu** | Quản lý vòng đời dữ liệu và mô hình: crawl, lấy diff, gán nhãn bằng quy tắc, kiểm chứng nhãn bằng tập người gán, huấn luyện và đánh giá. | Thu thập, Học máy |

Ranh giới giữa hai admin: **Admin dữ liệu tạo ra model** (dataset → huấn luyện → đăng ký vào registry), **Admin hệ thống đưa model vào chạy** (promote/rollback, vận hành API và bot).

### 1.2 Use case chính: cảnh báo loại lỗi khi review PR

| Mục | Đặc tả |
|---|---|
| Thời điểm can thiệp | Khi PR được mở hoặc có commit mới đẩy vào PR (sự kiện `pull_request` opened/synchronize), **trước khi CI chạy xong**. Không can thiệp ở bước push thẳng lên nhánh chính. |
| Đầu vào | Diff của PR so với merge-base, metadata commit, lịch sử build của chuỗi PR và của repo |
| Đầu ra | Xác suất fail, phân bố loại lỗi (compile / lint / test), dạng lỗi chi tiết có khả năng nhất, top hunk/file đóng góp |
| Giá trị 1: triage nhanh | Reviewer biết trước "PR này dễ lỗi lint – checkstyle" hoặc "dễ lỗi integration test ở module X" mà không phải chờ CI 10–30 phút rồi mới đọc log |
| Giá trị 2: báo lỗi sớm hơn | Job có loại lỗi dự đoán cao được xếp chạy trước. Đo bằng **thời gian đến tín hiệu fail đầu tiên** giảm được bao nhiêu phút so với thứ tự mặc định (mô phỏng trên dữ liệu thật, US-32) |
| Giá trị 3: tiết kiệm tài nguyên CI | Khi job được dự đoán lỗi chạy trước và fail, có thể huỷ các job còn lại (fail-fast). Đo bằng số phút runner tiết kiệm trong mô phỏng |
| Ngoài phạm vi | Tự động chặn merge; thay thế việc đọc log; dự đoán lỗi do môi trường (infra/flaky) |

## 2. Đầu vào / đầu ra của pipeline dữ liệu

| Bước | Đầu vào | Đầu ra | Thành phần |
|---|---|---|---|
| 1. Chọn repo | Tiêu chí: Java/JVM, dùng GitHub Actions, đủ số run trong 90 ngày | `repos.txt` | GHARuns (thống kê), GitHub API |
| 2. Crawl CI | `repos.txt`, số ngày, loại sự kiện | `runs.jsonl`, `jobs.jsonl` (job, step, thời gian), `logs/<job_id>.txt` của job fail | `crawl/gha.py`, `crawl/github.py` |
| 3. Gán nhãn bằng quy tắc | Log job fail | `gold_labels.csv`: run_id, nhãn, **dòng bằng chứng** khớp quy tắc | `crawl/gold_labels.py` |
| 4. Gộp theo commit | Run + nhãn | `commits.parquet`: commit, chuỗi build, outcome, nhãn tầng 2, lần fail đầu | `crawl/build_log_labels.py` |
| 5. Lấy diff | Danh sách SHA | `diffs/<repo>/<sha>.{pr,commit}.diff` | `pipeline/fetch_diffs.py` |
| 6. Nhãn tầng 3 | Dòng bằng chứng | `fine_labels.parquet`: dạng lỗi chi tiết, module lỗi | `crawl/fine_labels.py` |
| 7. Báo cáo | Toàn bộ trên | Thống kê độ phủ theo repo: số run, tỉ lệ fail, phân bố loại lỗi, log thiếu, diff thiếu | `crawl/crawl_report.py` |

Một mẫu dữ liệu đầu ra gồm: `repo, sha, chuỗi build, thời điểm, outcome, nhãn tầng 2, nhãn tầng 3, module, dòng bằng chứng, đường dẫn diff, feature lịch sử`.

## 3. Ràng buộc

| ID | Ràng buộc |
|---|---|
| C-01 | GitHub chỉ giữ log 90 ngày: commit fail không còn log được gắn nhãn "chưa gán (hết log)", không đoán nhãn |
| C-02 | Không dùng LLM làm nguồn nhãn. Nhãn chỉ đến từ bộ quy tắc trên log và được kiểm chứng bằng tập người gán |
| C-03 | Bộ quy tắc hiện viết cho hệ sinh thái Java (Maven/Gradle). Mở rộng repo trong phạm vi Java/JVM để quy tắc còn đúng |
| C-04 | Feature chỉ dùng thông tin trước thời điểm commit; chia train/test theo thời gian (P1) hoặc theo repo (P2) |
| C-05 | Siêu tham số (λ, τ) cố định trước, mô hình chọn trên validation, không dò trên tập test |
| C-06 | Token GitHub/Kaggle đọc từ `.env`, không ghi vào mã nguồn hay log |

## 4. Bảng Epic

| Epic | Tên | Mục tiêu | Actor chính | Khối kiến trúc | Sprint |
|---|---|---|---|---|---|
| **EP-01** | Pipeline thu thập dữ liệu CI | Một lệnh chạy end-to-end: crawl run/job/step/log + diff cho **≥ 100 repo Java/JVM**, tiếp tục được khi bị ngắt, có báo cáo độ phủ | Admin dữ liệu | Thu thập | 1–2 |
| **EP-02** | Gán nhãn bằng quy tắc & kiểm chứng | Gán nhãn loại lỗi 3 tầng bằng quy tắc trên log, lưu dòng bằng chứng; đo độ chính xác bằng tập người gán mù | Admin dữ liệu | Thu thập → Học máy | 1–2 |
| **EP-03** | Baseline, huấn luyện & đánh giá | Bảng baseline chứng minh tín hiệu từ diff, rồi HCL; đánh giá P1–P3 có khoảng tin cậy, ablation | Admin dữ liệu | Học máy | 1–3 |
| **EP-04** | Dịch vụ dự đoán & giải thích | API `/predict` trả xác suất fail + loại lỗi + giải thích; lưu dự đoán để đối chiếu với kết quả thật | Reviewer, Admin hệ thống | Phục vụ | 3 |
| **EP-05** | Tích hợp GitHub & bot PR | Nhận webhook PR, comment dự đoán và thứ tự job đề xuất lên PR, thu phản hồi | Reviewer, Developer | Tích hợp & hiển thị | 3 |
| **EP-06** | Quản trị hệ thống | Cấu hình repo, ngưỡng, model đang chạy, giám sát, secret và phân quyền | Admin hệ thống | Phục vụ, Tích hợp | 3 |
| **EP-07** | Dashboard & báo cáo | Thống kê dữ liệu, so sánh baseline, độ chính xác online và lịch sử dự đoán | Cả 4 actor | Tích hợp & hiển thị | 2–3 |
| **EP-08** | Đặc tả và đo giá trị use case | Chứng minh giá trị bằng số: phút báo lỗi sớm hơn, phút runner tiết kiệm khi xếp lại job theo dự đoán | Reviewer, Admin dữ liệu | Học máy → Tích hợp | 2 |

## 5. User story

Định dạng: *Là `<actor>`, tôi muốn `<chức năng>` để `<giá trị>`.*

### EP-01 · Pipeline thu thập dữ liệu CI

| ID | User story |
|---|---|
| US-01 | Là **Admin dữ liệu**, tôi muốn cấu hình danh sách repo, khoảng thời gian (mặc định 90 ngày) và loại sự kiện (push/PR) cần crawl để chủ động phạm vi dữ liệu. |
| US-02 | Là **Admin dữ liệu**, tôi muốn crawl run, job, step và log lỗi của các workflow CI, tự tiếp tục từ điểm dừng khi bị ngắt để không phải crawl lại từ đầu. |
| US-03 | Là **Admin dữ liệu**, tôi muốn hệ thống lập danh sách run cần crawl lại (thiếu log, lỗi mạng, hết rate limit) và chạy lại có kiểm soát để dữ liệu đầy đủ nhất có thể. |
| US-04 | Là **Admin dữ liệu**, tôi muốn lấy diff của từng commit bằng git (partial clone) để có đầu vào nội dung thay đổi cho mô hình. |
| US-05 | Là **Admin dữ liệu**, tôi muốn xem báo cáo độ phủ theo repo (số run, số commit, tỉ lệ fail, lần fail đầu, phân bố loại lỗi, log/diff bị thiếu) để chứng minh dữ liệu đủ phong phú. |
| US-30 | Là **Admin dữ liệu**, tôi muốn chạy toàn bộ pipeline (crawl → log → gán nhãn → diff → báo cáo) bằng **một lệnh** với đầu vào là danh sách repo để demo và tái lập dữ liệu mà không làm tay bước nào. |
| US-31 | Là **Admin dữ liệu**, tôi muốn chọn tự động ≥ 100 repo Java/JVM theo tiêu chí rõ ràng (dùng GitHub Actions, đủ số run, có job build/test) để dữ liệu có ý nghĩa thống kê. |

### EP-02 · Gán nhãn bằng quy tắc & kiểm chứng

| ID | User story |
|---|---|
| US-06 | Là **Admin dữ liệu**, tôi muốn gán nhãn loại lỗi tầng 2 (compile / test / lint / dependency / infra-flaky) bằng bộ quy tắc regex trên log và lưu dòng bằng chứng để nhãn giải thích được và kiểm chứng được. |
| US-07 | Là **Admin dữ liệu**, tôi muốn gán nhãn dạng lỗi chi tiết tầng 3 (vd. lint-format, lint-checkstyle, test-unit, test-integration) và module bị lỗi để dùng cho loss tầng 3 và loss module. |
| US-08 | Là **Admin dữ liệu**, tôi muốn **tự gán tay** một tập ≥ 200 run fail (rút ngẫu nhiên phân tầng theo loại lỗi và repo) mà không thấy nhãn của quy tắc, để đo precision/recall của bộ quy tắc và độ đồng thuận (Cohen's kappa). |
| US-09 | Là **Admin dữ liệu**, tôi muốn hệ thống xác định chuỗi build, "lần fail đầu" và sinh feature lịch sử (lần trước fail?, loại lỗi trước, số file…) để đánh giá P3 và ghép vào mô hình. |
| US-10 | Là **Admin dữ liệu**, tôi muốn lưu dataset thành phiên bản cố định (snapshot có mã phiên bản) để kết quả thí nghiệm tái lập được. |
| US-33 | Là **Admin dữ liệu**, tôi muốn (tuỳ chọn) chạy một LLM gán nhãn trên cùng tập người gán, chỉ để so sánh với bộ quy tắc, để trả lời câu hỏi "quy tắc có thua LLM không" mà không dùng LLM làm nguồn nhãn. |

### EP-03 · Baseline, huấn luyện & đánh giá

| ID | User story |
|---|---|
| US-11 | Là **Admin dữ liệu**, tôi muốn chạy bảng baseline trước HCL trên cùng tập chia: đoán theo tỉ lệ lớp (majority, prior), heuristic (Parrot loại lỗi: lặp lại loại lỗi trước), chỉ metadata (LR lịch sử), TF-IDF trên diff, fine-tune CE thường, để chứng minh mô hình học từ diff chứ không đoán mò. |
| US-11b | Là **Admin dữ liệu**, tôi muốn chạy thêm baseline từ nghiên cứu khác (XGBoost, GitSense, SupCon một tầng) để so với công trình liên quan. |
| US-12 | Là **Admin dữ liệu**, tôi muốn huấn luyện mô hình HCL (encoder phân cấp hunk → file → commit + loss contrastive 3 tầng + feature lịch sử) với cấu hình cố định để tạo model dự đoán. |
| US-13 | Là **Admin dữ liệu**, tôi muốn đánh giá mọi mô hình theo P1 (theo thời gian), P2 (repo chưa thấy), P3 (lần fail đầu, chuỗi chưa từng fail), với macro-F1 loại lỗi, F1 từng lớp, PR-AUC lớp fail và khoảng tin cậy bootstrap, để biết chênh lệch có ý nghĩa thống kê không. |
| US-14 | Là **Admin dữ liệu**, tôi muốn chạy ablation (bỏ tầng 3, bỏ cặp commit sửa, bỏ lịch sử, ít nhãn) và trực quan hoá không gian embedding để giải thích đóng góp của từng thành phần. |
| US-15 | Là **Admin dữ liệu**, tôi muốn đăng ký model đã huấn luyện vào model registry (checkpoint + cấu hình + độ đo + phiên bản dataset) để Admin hệ thống có thể triển khai. |

### EP-04 · Dịch vụ dự đoán & giải thích

| ID | User story |
|---|---|
| US-16 | Là **Reviewer**, tôi muốn nhận xác suất fail và loại lỗi dự đoán của PR trước khi CI chạy xong để triage và yêu cầu sửa sớm thay vì chờ 10–30 phút. |
| US-17 | Là **Reviewer**, tôi muốn thấy lý do dự đoán (hunk/file đóng góp nhiều nhất theo attention, feature lịch sử quan trọng) để biết cần xem lại chỗ nào trong PR. |
| US-18 | Là **Admin hệ thống**, tôi muốn mọi dự đoán được lưu cùng kết quả build thật khi CI chạy xong để đo độ chính xác khi dùng thật. |

### EP-05 · Tích hợp GitHub & bot PR

| ID | User story |
|---|---|
| US-19 | Là **Reviewer**, tôi muốn bot tự comment lên PR (xác suất fail, loại lỗi, lý do) khi PR được mở hoặc cập nhật để không phải mở công cụ khác. |
| US-34 | Là **Developer**, tôi muốn thấy cảnh báo loại lỗi trên PR của mình ngay sau khi push để tự kiểm tra (vd. chạy checkstyle cục bộ) trước khi reviewer xem. |
| US-20 | Là **Admin hệ thống**, tôi muốn bot đề xuất thứ tự chạy job (job có loại lỗi dự đoán cao chạy trước) để CI báo lỗi sớm hơn. |
| US-21 | Là **Reviewer**, tôi muốn đánh dấu dự đoán đúng/sai ngay trên PR để góp dữ liệu cải thiện mô hình. |

### EP-06 · Quản trị hệ thống

| ID | User story |
|---|---|
| US-22 | Là **Admin hệ thống**, tôi muốn đăng ký repo và cài webhook/GitHub App có xác thực chữ ký để chỉ nhận sự kiện hợp lệ từ repo được phép. |
| US-23 | Là **Admin hệ thống**, tôi muốn cấu hình theo từng repo: bật/tắt bot, ngưỡng xác suất để cảnh báo, loại sự kiện được dự đoán để kiểm soát mức độ làm phiền. |
| US-24 | Là **Admin hệ thống**, tôi muốn chọn (promote) hoặc quay lại (rollback) phiên bản model đang phục vụ từ registry để cập nhật model không gián đoạn dịch vụ. |
| US-25 | Là **Admin hệ thống**, tôi muốn giám sát sức khoẻ dịch vụ (thời gian phản hồi, tỉ lệ lỗi, hàng đợi webhook, rate limit GitHub) để phát hiện sự cố sớm. |
| US-26 | Là **Admin hệ thống**, tôi muốn quản lý tài khoản theo vai trò và lưu token/secret an toàn để mỗi người chỉ thao tác đúng phạm vi. |

### EP-07 · Dashboard & báo cáo

| ID | User story |
|---|---|
| US-27 | Là **Admin dữ liệu**, tôi muốn dashboard thống kê dữ liệu (độ phủ theo repo, phân bố loại lỗi, độ chính xác nhãn) và so sánh baseline với HCL theo P1–P3 để trình bày kết quả. |
| US-28 | Là **Admin hệ thống**, tôi muốn dashboard độ chính xác online và cảnh báo drift theo thời gian để biết khi nào cần huấn luyện lại. |
| US-29 | Là **Reviewer**, tôi muốn xem lịch sử dự đoán và kết quả thật của repo để đánh giá độ tin cậy của bot. |

### EP-08 · Đặc tả và đo giá trị use case

| ID | User story |
|---|---|
| US-32 | Là **Admin dữ liệu**, tôi muốn mô phỏng việc xếp lại thứ tự job theo loại lỗi dự đoán trên dữ liệu job thật (thời điểm bắt đầu/kết thúc) để báo cáo số phút báo lỗi sớm hơn và số phút runner tiết kiệm so với thứ tự mặc định. |
| US-35 | Là **Reviewer**, tôi muốn có tài liệu use case một trang (actor, thời điểm, đầu vào/đầu ra, giá trị, ngoài phạm vi) để hiểu công cụ giúp gì trong quy trình review. |

## 6. Acceptance criteria

Định dạng Given / When / Then.

| AC | US | Given (cho trước) | When (khi) | Then (thì) |
|---|---|---|---|---|
| AC-01.1 | US-01 | File cấu hình có danh sách repo, số ngày, loại sự kiện | Admin dữ liệu chạy lệnh crawl | Chỉ các repo trong danh sách và run trong khoảng thời gian đã cấu hình được lấy |
| AC-01.2 | US-01 | Một repo trong danh sách không tồn tại hoặc không có quyền | Chạy crawl | Hệ thống ghi lỗi cho repo đó và tiếp tục các repo còn lại |
| AC-02.1 | US-02 | Đang crawl thì tiến trình bị dừng giữa chừng | Chạy lại cùng lệnh | Run đã lưu không bị tải lại; dòng cuối bị cắt dở được sửa, lỗi ở giữa file được báo |
| AC-02.2 | US-02 | Một tiến trình crawl đang chạy trên thư mục dữ liệu | Khởi động tiến trình thứ hai cùng thư mục | Tiến trình thứ hai bị từ chối do khoá, dữ liệu không bị ghi chồng |
| AC-02.3 | US-02 | Khoảng thời gian có hơn 1000 run (trần của API) | Liệt kê run | Khoảng thời gian được tự chia nhỏ, không bỏ sót run nào |
| AC-03.1 | US-03 | Có run fail chưa có log hoặc tải lỗi | Chạy lập kế hoạch retry | Danh sách retry chỉ gồm các run thiếu, kèm lý do |
| AC-03.2 | US-03 | Log đã bị GitHub xoá (hết hạn) | Retry | Run được đánh dấu "chưa gán (hết log)" và không retry vô hạn |
| AC-04.1 | US-04 | Danh sách SHA commit cần diff | Chạy lấy diff | Mỗi SHA có file diff; SHA thiếu trong clone được fetch bổ sung theo lô |
| AC-04.2 | US-04 | Commit trong PR | Lấy diff | Diff tính so với merge-base của nhánh chính mới nhất, không dùng mốc cũ |
| AC-05.1 | US-05 | Đã crawl xong | Chạy báo cáo | Bảng theo repo: số run, commit, commit fail, tỉ lệ fail, lần fail đầu, phân bố loại lỗi, số log/diff thiếu; tổng khớp dữ liệu gốc |
| AC-30.1 | US-30 | File `repos.txt` có 1–2 repo | Chạy một lệnh pipeline | Ra đủ `runs/jobs/logs`, `gold_labels.csv`, `commits.parquet`, thư mục diff, `fine_labels.parquet` và báo cáo, không cần thao tác tay giữa các bước |
| AC-30.2 | US-30 | Pipeline đã chạy một lần | Chạy lại cùng lệnh | Các bước đã xong được bỏ qua, chỉ phần còn thiếu được chạy |
| AC-31.1 | US-31 | Tiêu chí chọn repo đã cấu hình | Chạy chọn repo | Danh sách ≥ 100 repo Java/JVM, mỗi repo kèm lý do được chọn (số run, có job build/test) |
| AC-06.1 | US-06 | Commit fail có log | Chạy gán nhãn | Commit nhận đúng một nhãn tầng 2 kèm dòng bằng chứng; nhiều lỗi thì lấy giai đoạn sớm nhất (compile/lint trước test) |
| AC-06.2 | US-06 | Commit fail không còn log | Chạy gán nhãn | Commit có nhãn "chưa gán", không vào tập huấn luyện có nhãn loại lỗi |
| AC-06.3 | US-06 | Bộ quy tắc | Xuất tài liệu | Có bảng quy tắc: nhãn, mẫu regex, ví dụ dòng log khớp, thứ tự ưu tiên |
| AC-07.1 | US-07 | Commit đã có nhãn tầng 2 | Chạy gán nhãn chi tiết | Commit có nhãn tầng 3 (nếu quy tắc khớp) và module lỗi (nếu xác định được); nếu không thì để trống, không đoán |
| AC-08.1 | US-08 | Dataset đã gán nhãn | Rút mẫu với seed cố định | Cùng seed cho cùng mẫu; mẫu phân tầng theo loại lỗi và repo; giao diện gán tay chỉ hiện log, **không hiện nhãn quy tắc** |
| AC-08.2 | US-08 | Đã có ≥ 200 nhãn người | Tính độ chính xác | Báo cáo precision/recall theo từng nhãn, ma trận nhầm lẫn và Cohen's kappa; mục tiêu precision ≥ 90% cho compile/lint/test |
| AC-33.1 | US-33 | Tập người gán | Chạy LLM gán nhãn | Kết quả LLM chỉ xuất hiện trong bảng so sánh với quy tắc, không ghi vào dataset |
| AC-09.1 | US-09 | Chuỗi build theo nhánh/PR | Xác định lần fail đầu | Commit fail ngay sau commit pass trong cùng chuỗi được đánh dấu `first_fail` |
| AC-09.2 | US-09 | Commit bất kỳ | Sinh feature lịch sử | Feature chỉ dùng thông tin trước thời điểm commit (không rò rỉ tương lai) |
| AC-10.1 | US-10 | Dataset đã chốt | Tạo snapshot | Snapshot có mã phiên bản, số dòng, hash; thí nghiệm ghi lại phiên bản dataset đã dùng |
| AC-11.1 | US-11 | Dataset snapshot | Chạy bảng baseline | Mỗi baseline xuất macro-F1 và F1 từng lớp trên cùng tập chia, cho tập đầy đủ, P3 và chuỗi chưa từng fail |
| AC-11.2 | US-11 | Kết quả baseline | So mô hình đọc diff với baseline chỉ metadata | Có khoảng tin cậy bootstrap; kết luận "học được từ diff" chỉ khi khoảng tin cậy nằm trên 0 |
| AC-12.1 | US-12 | Cấu hình λ, τ cố định (λ = 0,5; τ = 0,1) | Huấn luyện HCL | Huấn luyện chạy hết, lưu checkpoint và log loss từng thành phần (CE, L₁, L₂, L₃, L_module) |
| AC-12.2 | US-12 | Commit có hơn 8 hunk hoặc hunk dài hơn 256 token | Mã hoá | Cắt về tối đa 8 hunk chia đều các file, mỗi hunk ≤ 256 token |
| AC-13.1 | US-13 | Model đã huấn luyện | Chạy đánh giá | Có kết quả P1, P2, P3 với 5 seed; báo cáo trung bình ± độ lệch và khoảng tin cậy bootstrap ghép cặp |
| AC-13.2 | US-13 | Kết quả hai model | So sánh | Tiêu chí thắng được ghi trước khi chạy; kết quả không đạt vẫn được báo cáo |
| AC-14.1 | US-14 | Model HCL đầy đủ | Chạy ablation | Bảng kết quả khi bỏ tầng 3, bỏ cặp commit sửa, bỏ lịch sử, ít nhãn; có hình t-SNE/UMAP của embedding tô theo loại lỗi |
| AC-15.1 | US-15 | Model đạt kết quả đánh giá | Đăng ký vào registry | Registry lưu checkpoint, cấu hình, độ đo, phiên bản dataset, trạng thái "candidate" |
| AC-16.1 | US-16 | Service đang chạy với một model "production" | Gửi diff + metadata tới `/predict` | Trả về xác suất fail ∈ [0,1], phân bố 4 lớp (pass/compile/lint/test), phiên bản model, trong ≤ 5 giây với commit ≤ 8 hunk |
| AC-16.2 | US-16 | Request thiếu trường hoặc diff rỗng | Gọi `/predict` | Trả lỗi 4xx có thông báo rõ, không làm sập service |
| AC-17.1 | US-17 | Có kết quả dự đoán | Yêu cầu giải thích | Trả top-3 hunk/file theo trọng số attention và top-5 feature lịch sử |
| AC-18.1 | US-18 | Dự đoán đã lưu | CI chạy xong (sự kiện `workflow_run completed`) | Kết quả thật được ghép vào bản ghi dự đoán theo SHA |
| AC-19.1 | US-19 | Repo bật bot, PR mới mở hoặc có commit mới | Webhook đến | Bot comment hoặc cập nhật comment cũ (không spam nhiều comment) với xác suất, loại lỗi, lý do |
| AC-19.2 | US-19 | Xác suất fail dưới ngưỡng cảnh báo | Có dự đoán | Bot chỉ hiện trạng thái gọn "rủi ro thấp" hoặc không comment, theo cấu hình |
| AC-34.1 | US-34 | Developer push commit mới vào PR | Có dự đoán loại lỗi | Comment có gợi ý kiểm tra cục bộ tương ứng (vd. lint → lệnh checkstyle/spotless của repo) |
| AC-20.1 | US-20 | Dự đoán có loại lỗi | Bot comment | Danh sách job được sắp theo loại lỗi dự đoán (vd. dự đoán lint → job lint lên đầu) |
| AC-21.1 | US-21 | Comment bot trên PR | Reviewer bấm reaction hoặc gõ lệnh phản hồi | Phản hồi được lưu kèm SHA, người phản hồi, thời điểm |
| AC-22.1 | US-22 | Webhook có secret | Nhận request sai chữ ký | Từ chối 401, ghi log, không dự đoán |
| AC-22.2 | US-22 | Repo chưa đăng ký | Nhận sự kiện từ repo đó | Bỏ qua sự kiện |
| AC-23.1 | US-23 | Admin hệ thống đổi ngưỡng / tắt bot của repo | Lưu cấu hình | Sự kiện tiếp theo dùng cấu hình mới, không cần khởi động lại service |
| AC-24.1 | US-24 | Registry có model "candidate" | Promote | Model mới phục vụ request kế tiếp; model cũ vẫn giữ để rollback |
| AC-24.2 | US-24 | Model mới gặp lỗi | Rollback | Quay về phiên bản trước trong ≤ 1 phút, mọi thao tác ghi audit log |
| AC-25.1 | US-25 | Service chạy | Mở trang giám sát / endpoint `/health` | Có độ trễ p50/p95, tỉ lệ lỗi, độ dài hàng đợi, rate limit GitHub còn lại |
| AC-25.2 | US-25 | Tỉ lệ lỗi hoặc độ trễ vượt ngưỡng | Theo dõi | Phát cảnh báo cho Admin hệ thống |
| AC-26.1 | US-26 | Tài khoản vai trò Developer/Reviewer | Truy cập chức năng promote model hoặc crawl | Bị từ chối 403 |
| AC-26.2 | US-26 | Token GitHub, secret webhook | Lưu cấu hình | Không lưu dạng rõ trong mã/log; đọc từ biến môi trường hoặc kho secret |
| AC-27.1 | US-27 | Đã có dữ liệu và kết quả đánh giá | Mở dashboard | Có thống kê độ phủ dữ liệu, độ chính xác nhãn, bảng và biểu đồ so sánh mô hình theo P1–P3, lọc theo repo |
| AC-28.1 | US-28 | Có dự đoán đã ghép kết quả thật | Mở dashboard online | Macro-F1 theo tuần; cảnh báo khi giảm quá ngưỡng so với kết quả offline P1 |
| AC-29.1 | US-29 | Reviewer có quyền trên repo | Mở lịch sử | Thấy danh sách dự đoán theo PR/commit, kết quả thật, đúng/sai |
| AC-32.1 | US-32 | Dữ liệu job có thời điểm bắt đầu/kết thúc và dự đoán trên tập test | Chạy mô phỏng | Báo cáo trung vị và phân bố số phút đến tín hiệu fail đầu tiên theo thứ tự mặc định so với thứ tự theo dự đoán, cùng số phút runner tiết kiệm khi fail-fast |
| AC-35.1 | US-35 | Đặc tả use case | Trình bày ở buổi duyệt | Một trang trả lời đủ: ai dùng, can thiệp lúc nào, đầu vào/đầu ra, giá trị đo được, ngoài phạm vi |

## 7. Product backlog

Ưu tiên theo MoSCoW (M = Must, S = Should, C = Could). Story point theo Fibonacci. Cột "Duyệt tới" đánh dấu việc **bắt buộc có trước buổi duyệt tới** theo feedback của hội đồng. Trạng thái tính theo mã nguồn và dữ liệu hiện có.

| # | ID | Tóm tắt | Epic | Actor | Ưu tiên | SP | Sprint | Duyệt tới | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|
| 1 | US-30 | Pipeline một lệnh end-to-end + demo | EP-01 | Admin dữ liệu | M | 5 | S1 | ● | To do (các bước đã có, chưa nối thành một lệnh) |
| 2 | US-31 | Chọn ≥ 100 repo Java/JVM | EP-01 | Admin dữ liệu | M | 3 | S1 | ● | To do (đang có 17 repo) |
| 3 | US-02 | Crawl run/job/log có resume, khoá | EP-01 | Admin dữ liệu | M | 8 | S1 | ● | Done cho 17 repo; cần chạy cho ≥ 100 repo |
| 4 | US-03 | Kế hoạch và chạy retry | EP-01 | Admin dữ liệu | M | 3 | S1 | ● | Done |
| 5 | US-04 | Lấy diff bằng git | EP-01 | Admin dữ liệu | M | 5 | S1 | ● | Done (26.883 diff) |
| 6 | US-05 | Báo cáo độ phủ | EP-01 | Admin dữ liệu | M | 2 | S1 | ● | Done (cần thêm phân bố loại lỗi, diff thiếu) |
| 7 | US-01 | Cấu hình phạm vi crawl | EP-01 | Admin dữ liệu | M | 2 | S1 | | Done |
| 8 | US-06 | Nhãn tầng 2 bằng quy tắc + dòng bằng chứng | EP-02 | Admin dữ liệu | M | 5 | S1 | ● | Done (cần xuất bảng quy tắc, AC-06.3) |
| 9 | US-08 | Tập người gán mù ≥ 200 run, precision/recall/kappa | EP-02 | Admin dữ liệu | M | 5 | S1 | ● | To do (mẫu 103 run hiện có chưa phải nhãn do người gán độc lập) |
| 10 | US-11 | Bảng baseline: tỉ lệ lớp, Parrot, chỉ metadata, TF-IDF, CE | EP-03 | Admin dữ liệu | M | 3 | S1 | ● | Done (`legacy/.../pilot/type_feasibility.py`) |
| 11 | US-35 | Tài liệu use case một trang | EP-08 | Reviewer | M | 2 | S1 | ● | To do (nội dung ở mục 1.2) |
| 12 | US-07 | Nhãn tầng 3 + module | EP-02 | Admin dữ liệu | M | 3 | S1 | | Done (`crawl/fine_labels.py`) |
| 13 | US-09 | Lần fail đầu + feature lịch sử | EP-02 | Admin dữ liệu | M | 5 | S1 | | Done |
| 14 | US-10 | Snapshot dataset | EP-02 | Admin dữ liệu | S | 2 | S1 | | In progress (có phiên bản dataset trên Kaggle, chưa có mã phiên bản riêng) |
| 15 | US-32 | Mô phỏng báo lỗi sớm / tiết kiệm runner | EP-08 | Admin dữ liệu | S | 5 | S2 | | To do |
| 16 | US-12 | Huấn luyện HCL | EP-03 | Admin dữ liệu | M | 13 | S2 | | Done (thí nghiệm trên Kaggle) |
| 17 | US-13 | Đánh giá P1–P3 có khoảng tin cậy | EP-03 | Admin dữ liệu | M | 8 | S2 | | In progress (đã có P1, P2, P3 trên 11 repo; cần chạy lại trên dataset ≥ 100 repo) |
| 18 | US-14 | Ablation + trực quan embedding | EP-03 | Admin dữ liệu | S | 5 | S2 | | In progress (đã có bỏ cặp commit sửa, HCL 2 tầng so với 3 tầng, ít nhãn; chưa có hình embedding) |
| 19 | US-11b | Baseline XGBoost, GitSense, SupCon 1 tầng | EP-03 | Admin dữ liệu | S | 8 | S2 | | To do |
| 20 | US-33 | LLM chỉ để so sánh với nhãn người | EP-02 | Admin dữ liệu | C | 2 | S2 | | To do |
| 21 | US-15 | Model registry | EP-03 | Admin dữ liệu | S | 3 | S2 | | To do |
| 22 | US-27 | Dashboard dữ liệu + so sánh offline | EP-07 | Admin dữ liệu | S | 5 | S2 | | To do |
| 23 | US-16 | API `/predict` | EP-04 | Reviewer | M | 5 | S3 | | To do |
| 24 | US-22 | Webhook có xác thực | EP-06 | Admin hệ thống | M | 3 | S3 | | To do |
| 25 | US-19 | Bot comment PR | EP-05 | Reviewer | M | 5 | S3 | | To do |
| 26 | US-17 | Giải thích attention + feature lịch sử | EP-04 | Reviewer | S | 5 | S3 | | To do |
| 27 | US-18 | Lưu dự đoán + kết quả thật | EP-04 | Admin hệ thống | S | 3 | S3 | | To do |
| 28 | US-34 | Gợi ý kiểm tra cục bộ cho developer | EP-05 | Developer | C | 2 | S3 | | To do |
| 29 | US-23 | Cấu hình repo, ngưỡng | EP-06 | Admin hệ thống | S | 3 | S3 | | To do |
| 30 | US-24 | Promote/rollback model | EP-06 | Admin hệ thống | S | 3 | S3 | | To do |
| 31 | US-26 | Phân quyền theo vai trò, secret | EP-06 | Admin hệ thống | S | 3 | S3 | | To do |
| 32 | US-20 | Đề xuất thứ tự chạy job | EP-05 | Admin hệ thống | C | 3 | S3 | | To do |
| 33 | US-25 | Giám sát dịch vụ | EP-06 | Admin hệ thống | C | 3 | S3 | | To do |
| 34 | US-21 | Phản hồi đúng/sai trên PR | EP-05 | Reviewer | C | 2 | S3 | | To do |
| 35 | US-28 | Dashboard online + drift | EP-07 | Admin hệ thống | C | 5 | S3 | | To do |
| 36 | US-29 | Lịch sử dự đoán | EP-07 | Reviewer | C | 3 | S3 | | To do |

Tổng story point: S1 = 53, S2 = 49, S3 = 48. Việc **trước buổi duyệt tới** (cột ●) tổng 41 SP, trong đó phần chưa làm là US-30, US-31, chạy crawl cho ≥ 100 repo, US-08 và US-35. Nếu Sprint 3 thiếu thời gian, các mục **C** chuyển sang hướng phát triển.

## 8. Kết quả hiện có (dùng cho bảng baseline)

Dự đoán loại lỗi (compile / lint / test) trên commit fail do code, 11 repo, chia theo thời gian 70/30, macro-F1, mô hình sâu lấy trung bình 5 seed.

| Mô hình | Toàn tập | Lần fail đầu (P3) | Chuỗi chưa từng fail |
|---|---|---|---|
| Đoán lớp nhiều nhất | 0.288 | 0.289 | 0.286 |
| Đoán theo tỉ lệ lớp | 0.322 | 0.321 | 0.322 |
| Parrot loại lỗi (heuristic) | 0.534 | 0.384 | 0.286 |
| LR chỉ metadata | 0.456 | 0.381 | 0.331 |
| TF-IDF trên diff | 0.463 | 0.449 | 0.432 |
| UniXcoder + CE | 0.488 | 0.418 | 0.389 |
| UniXcoder + HCL 3 tầng | 0.487 | 0.426 | 0.409 |

- Mô hình đọc diff vượt các baseline chỉ dùng tỉ lệ lớp và chỉ dùng metadata, nhất là ở P3 và chuỗi chưa từng fail, nơi Parrot không có lịch sử để lặp lại.
- Ở repo chưa thấy (P2), mô hình đọc diff đạt khoảng 0.54 so với 0.34 của TF-IDF.
- HCL 3 tầng chưa hơn CE có ý nghĩa thống kê khi so từng mô hình đơn lẻ (P1, P2, ít nhãn). Kết quả này được báo cáo đầy đủ ở US-13 và US-14.
- Các số trên là trên 11 repo; cần chạy lại khi có dataset ≥ 100 repo.

## 9. Traceability matrix

### 9.1 Yêu cầu → Story → AC → Thiết kế → Mã nguồn → Kiểm thử

| Yêu cầu chức năng | Epic | User story | AC | Khối (slide 13) | Mã nguồn / thành phần | Test case | Sprint |
|---|---|---|---|---|---|---|---|
| FR-01 Thu thập dữ liệu CI có kèm log | EP-01 | US-01, US-02 | AC-01.1–02.3 | Thu thập: Crawl GitHub API | `crawl/gha.py`, `crawl/github.py`, `crawl/checkpoint.py`, `scripts/crawl_*.ps1` | `test_crawl_checkpoint.py`, `test_crawl_lock.py`, `test_crawl_empty.py` | S1 |
| FR-02 Bổ sung dữ liệu thiếu | EP-01 | US-03 | AC-03.1–03.2 | Thu thập | `crawl/retry_plan.py` | `test_crawl_retry.py` | S1 |
| FR-03 Lấy diff commit | EP-01 | US-04 | AC-04.1–04.2 | Thu thập: git clone, git diff | `pipeline/fetch_diffs.py`, `crawl/diff_probe.py` | TC-04 (chưa có) | S1 |
| FR-04 Báo cáo độ phủ dữ liệu | EP-01 | US-05 | AC-05.1 | Thu thập | `crawl/crawl_report.py`, `crawl/analyze.py` | TC-05 (chưa có) | S1 |
| FR-21 Pipeline một lệnh, ≥ 100 repo | EP-01 | US-30, US-31 | AC-30.1–31.1 | Thu thập | (chưa có: `project3/pipeline.py`) | TC-30 (demo 1–2 repo) | S1 |
| FR-05 Gán nhãn loại lỗi bằng quy tắc | EP-02 | US-06, US-07 | AC-06.1–07.1 | Xử lý & gán nhãn | `crawl/gold_labels.py`, `crawl/build_log_labels.py`, `crawl/fine_labels.py` | `test_gold_labels.py`, TC-07 | S1 |
| FR-06 Kiểm chứng nhãn bằng tập người gán | EP-02 | US-08, US-33 | AC-08.1–08.2, AC-33.1 | Xử lý & gán nhãn | `crawl/review_sample.py`, `crawl/review_dump.py` (rút mẫu); công cụ gán mù (chưa có) | TC-08 | S1 |
| FR-07 Chuỗi build, lần fail đầu, feature lịch sử | EP-02 | US-09 | AC-09.1–09.2 | DuckDB: nhãn, lịch sử, feature | `legacy/.../pilot/experiment.py`, `legacy/.../pilot/hcl_train.py` (meta) | TC-09 (kiểm tra không rò rỉ thời gian) | S1 |
| FR-08 Phiên bản dataset | EP-02 | US-10 | AC-10.1 | DuckDB | (chưa có) | TC-10 | S1 |
| FR-09 Bảng baseline | EP-03 | US-11, US-11b | AC-11.1–11.2 | Học máy | `legacy/.../pilot/type_feasibility.py` (baselines) | TC-11 | S1–S2 |
| FR-10 Mô hình HCL | EP-03 | US-12 | AC-12.1–12.2 | Encoder phân cấp, HCL head | `legacy/.../pilot/type_feasibility.py` (finetune), `legacy/.../pilot/hcl_embed.py`, `scripts/kaggle/hcl_full/run.py` | TC-12 | S2 |
| FR-11 Đánh giá P1–P3, ablation | EP-03 | US-13, US-14 | AC-13.1–14.1 | Học máy | `legacy/.../pilot/type_feasibility.py` (`--holdout`, `--label-frac`, `--sampler`) | TC-13 | S2 |
| FR-22 Đo giá trị use case | EP-08 | US-32, US-35 | AC-32.1, AC-35.1 | Học máy → Tích hợp | (chưa có) | TC-32 | S1–S2 |
| FR-12 Quản lý phiên bản model | EP-03, EP-06 | US-15, US-24 | AC-15.1, AC-24.1–24.2 | Model registry | (chưa có) | TC-15, TC-24 | S2–S3 |
| FR-13 Dự đoán trước khi CI chạy xong | EP-04 | US-16 | AC-16.1–16.2 | FastAPI /predict | (chưa có) | TC-16 | S3 |
| FR-14 Giải thích dự đoán | EP-04 | US-17 | AC-17.1 | Giải thích | (chưa có) | TC-17 | S3 |
| FR-15 Lưu và đối chiếu kết quả | EP-04 | US-18 | AC-18.1 | Lưu kết quả | (chưa có) | TC-18 | S3 |
| FR-16 Tích hợp GitHub | EP-05, EP-06 | US-19, US-22, US-34 | AC-19.1–19.2, AC-22.1–22.2, AC-34.1 | GitHub webhook, Bot comment PR | (chưa có) | TC-19, TC-22 | S3 |
| FR-17 Ưu tiên job & phản hồi | EP-05 | US-20, US-21 | AC-20.1, AC-21.1 | Bot comment PR | (chưa có) | TC-20, TC-21 | S3 |
| FR-18 Cấu hình & bảo mật | EP-06 | US-23, US-26 | AC-23.1, AC-26.1–26.2 | Phục vụ | `crawl/github.py` (đọc token từ `.env`) | TC-23, TC-26 | S3 |
| FR-19 Giám sát | EP-06 | US-25 | AC-25.1–25.2 | Phục vụ | (chưa có) | TC-25 | S3 |
| FR-20 Dashboard | EP-07 | US-27, US-28, US-29 | AC-27.1–29.1 | Dashboard | (chưa có) | TC-27–29 | S2–S3 |

### 9.2 Actor × Epic

| Actor | EP-01 | EP-02 | EP-03 | EP-04 | EP-05 | EP-06 | EP-07 | EP-08 |
|---|---|---|---|---|---|---|---|---|
| Reviewer / Maintainer | | | | ● US-16, 17 | ● US-19, 21 | | ● US-29 | ● US-35 |
| Developer | | | | | ● US-34 | | | |
| Admin hệ thống | | | | ● US-18 | ● US-20 | ● US-22 → 26 | ● US-28 | |
| Admin dữ liệu | ● US-01 → 05, 30, 31 | ● US-06 → 10, 33 | ● US-11 → 15 | | | ○ (bàn giao model) | ● US-27 | ● US-32 |

● sở hữu story · ○ có liên quan

### 9.3 Mục tiêu đề tài và feedback → Yêu cầu

| Mục tiêu / feedback | Yêu cầu chức năng |
|---|---|
| Dataset có diff + log thật, ≥ 100 repo, pipeline tự động demo được | FR-01 → FR-04, FR-21 |
| Nhãn bằng quy tắc, kiểm chứng bằng nhãn người, không dùng LLM làm nguồn nhãn | FR-05, FR-06 |
| Chứng minh mô hình học từ diff bằng bảng baseline | FR-07, FR-09, FR-11 |
| Mô hình đọc diff theo phân cấp + cây loại lỗi | FR-10 |
| Use case rõ ràng: ai dùng, lúc nào, giá trị đo được | FR-22, FR-13 → FR-17 |
| Vận hành được trong thực tế | FR-12, FR-18, FR-19, FR-20 |
