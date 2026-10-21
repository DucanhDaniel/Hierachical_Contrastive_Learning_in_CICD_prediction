# Khung nhãn lỗi build và kiểm chứng bộ quy tắc gán nhãn

Cập nhật 10/10/2026. Trả lời yêu cầu của hội đồng: nhãn phải dựa trên **một khung nhãn đã công bố** làm cơ sở đối chiếu và
phải **kiểm chứng được**, không để AI tự gán.

## 1. Khung nhãn gốc: Rausch et al. (MSR 2017)

Nguồn chính: T. Rausch, W. Hummer, P. Leitner, S. Schulte, *An Empirical Analysis of Build Failures in the Continuous
Integration Workflows of Java-Based Open-Source Software*, Proc. 14th Int. Conf. on Mining Software Repositories (MSR 2017),
IEEE/ACM, DOI 10.1109/MSR.2017.54 — mục IV, bảng II (`docs/papers/1_build_prediction/An Empirical Analysis of Build Failures in the.pdf`).
Mô tả chi tiết hơn: luận văn của T. Rausch (TU Wien, 2017), mục 5.1, bảng 5.1
(`docs/papers/1_build_prediction/TUWien2017_Rausch_thesis_build_failures_Java_CI.pdf`).

**Phương pháp của Rausch giống phương pháp của đề tài:**
- Đọc log của build fail (Maven/Gradle), tìm **dòng thông báo đặc trưng** của từng loại lỗi, tổng quát thành **biểu thức chính
  quy**, rồi gán loại lỗi cho mọi log khớp mẫu.
- Mẫu được phát triển dần bằng *open coding* (công cụ LogCat): lấy ngẫu nhiên một log chưa gán, đặt giả thuyết về dòng lỗi,
  kiểm tra trên log khác, lặp lại đến khi hầu hết log được gán.
- Mỗi log được gán **tối đa một nhãn**; lặp lại đến khi **≥ 90%** số log khớp một mẫu, sau đó tinh chỉnh mẫu ở các vòng sau.
- Quy mô: 14 project Java (12 project được phân loại), **54.248 log** job fail, **92%** được gán; 21 nhãn ban đầu gộp thành **14 loại**.
- Kết quả liên quan trực tiếp tới đề tài: ở 10/14 project, hơn 50% (tới 80%) số build fail đi ngay sau một build fail khác,
  tức là dữ liệu có quán tính mạnh, đúng điều làm baseline Parrot mạnh.


> **Cập nhật 18/10/2026 (rule version `2026-10-18-dependency-q1q3`, người duyệt qua `docs/duyet-quy-tac-dependency-2026-10-18.xlsx`):**
> lá **dependency** mở rộng theo nguyên nhân gốc.
> - **Q1:** maven-enforcer (upper bound, convergence, banned dependencies) và `dependency:analyze` chuyển từ lint sang dependency.
> - **Q3:** lệch phiên bản JDK (`class file has wrong version`, `UnsupportedClassVersionError`, `invalid target release`), Gradle báo lệch JVM/xung đột version, và thiếu class bên ngoài (`NoClassDefFoundError` → `ClassNotFoundException` cùng lớp) là dependency. Chỉ ghi đè compile/test của chính job quyết định nhãn, hoặc run `?`.
> - **Q2:** HTTP 401/403 khi tải artifact vẫn là network.
> - **Q4:** `Failed to read artifact descriptor` không rõ nguyên nhân giữ `?`.
> - **Chưa dùng:** lỗi liên kết `NoSuchMethodError` (người chọn unclear).
>
> Chi tiết: [codex/ra-soat-dependency-2026-10-18.md](codex/ra-soat-dependency-2026-10-18.md).
>
> **Cập nhật 16/10/2026:** tầng 3 đổi thành đúng tập nhãn bảng II của Rausch (testfailure, itestfailure, compile, buildconfig, dependency, quality, doc, license, compatibility, git, crash, androidsdk) cộng hai lá đề tài thêm: **network** (lỗi do mạng) và **flaky** (test không ổn định). Các tên tầng 3 cũ trong bảng dưới (test_unit, lint_format, infra_* ...) chỉ còn giá trị lịch sử.

Bảng II của Rausch (14 loại) và cách đề tài ánh xạ:

| Loại (Rausch) | Mô tả (Rausch) | Nhãn của đề tài: tầng 2 → tầng 3 | Ghi chú |
|---|---|---|---|
| testfailure | Một test tự động không đạt | **test** → test_unit | |
| itestfailure | Integration test không đạt | **test** → test_it | Rausch tách riêng; đề tài để ở tầng 3 |
| compile | Biên dịch thất bại | **compile** → compile_main / compile_test | |
| quality | Vi phạm quy tắc code khi kiểm tra tĩnh (checkstyle, findbugs…) | **lint** → lint_format / lint_checkstyle | Rausch gộp nhiều công cụ thành một loại, như đề tài |
| license | Plugin kiểm tra license báo lỗi | **lint** → lint_license | |
| compatibility | Không tương thích API, vd. xung đột phiên bản | **lint** → lint_api (revapi, japicmp) | Đề tài coi kiểm tra API là kiểm tra tĩnh |
| dependency | Không resolve được dependency (sai phiên bản…) | **dependency** (gộp vào nhánh build cùng compile) | |
| buildconfig | Cấu hình build lỗi (vd. pom.xml sai cú pháp) | **buildconfig** (tầng 2 riêng, nhánh build) → bc_pom / bc_reactor / bc_gradle | Thêm 15/10/2026: pom.xml khai báo sai/không đọc được, chọn module không tồn tại, script Gradle không biên dịch được. Xét trước mọi giai đoạn khác |
| doc | Lỗi khi xử lý tài liệu (javadoc) | **lint** → lint_doc | Thêm 15/10/2026: thông báo chỉ javadoc in (`reference not found`, `unknown tag`…); trước đó 76 run javadoc bị gán nhầm compile |
| git | Lỗi tương tác VCS, vd. worker không lấy được code | **infra** | Lỗi môi trường, không huấn luyện |
| crash | Môi trường build sập hoặc quá thời gian | **infra** | |
| androidsdk | Lỗi Android SDK (không tải được…) | **infra** | Quan trọng khi thêm repo Android |
| buildout | Lỗi công cụ build riêng của một submodule | không áp dụng | |
| unknown | Lỗi không xác định rõ nguyên nhân | **`?` / unclear** | Đề tài để trống, không đoán |
| *(không có)* | | **flaky** | Đề tài thêm: test không ổn định (GitHub có re-run) |

Cách gộp của đề tài: test (testfailure, itestfailure) / build-code (buildconfig, compile, quality, license, compatibility, dependency,
doc) / môi trường (git, crash, androidsdk) / không xác định (unknown). Nhánh môi trường bị loại khỏi huấn luyện vì
không do code.

## 2. So sánh phân bố với Rausch

Dữ liệu của đề tài: 17 repo, 19.266 run fail của workflow build; **71%** còn log (phần còn lại GitHub đã xoá sau 90 ngày).

| Chỉ số | Rausch (Travis CI, 14 project) | Đề tài (GitHub Actions, 17 repo) |
|---|---|---|
| Loại lỗi phổ biến nhất | testfailure | test |
| Tỉ lệ test failure | trung bình 41% số build; có project > 80% | trung bình 49% mỗi repo (trong run đã gán); cao nhất 83% |
| Ba loại phổ biến nhất | testfailure, quality, compile ≈ 62% số lỗi | test, lint, compile = 69% số run có log (90% số run đã gán) |
| Tỉ lệ log gán được loại lỗi | 92% (tính cả loại "unknown") | 76,5% (không tính `?`) |
| Lỗi môi trường | git, crash là nhiễu đáng kể | infra 6,3% |

Thứ tự và tỉ trọng các loại lỗi chính khớp với Rausch. Khác biệt chính là **độ phủ** (76,5% so với 92%): Rausch tính cả loại "unknown"
vào phần đã gán, còn đề tài để `?`; đề tài cũng chưa có quy tắc cho buildconfig, doc. Về kiểm chứng, Rausch chỉ ghi
trong phần *Threats to Validity* rằng tác giả đầu đã xem tay một mẫu và lặp lại đến khi không còn thấy gán sai, **không báo cáo
con số độ chính xác**; đề tài đo định lượng bằng tập người gán mù (mục 3).

## 3. Kiểm chứng bằng nhãn người

Công cụ: `src/project3/pipeline/label_ui.py`; dữ liệu: `data/human_labels/`.

- Mẫu 220 run fail, phân tầng theo nhãn quy tắc (kể cả `?`) và trải đều 10–17 repo mỗi nhãn; người gán **không thấy** nhãn quy tắc.
- **Vòng mù:** đồng thuận 0,632, Cohen's kappa 0,564.
- **Vòng phân xử** (48 run bất đồng, lúc này hiện nhãn quy tắc và dòng bằng chứng): người nhầm 32, quy tắc sai 10, cả hai sai 6.
- **Precision của quy tắc sau phân xử:** compile 0,95; dependency 1,00; infra 0,83; lint 0,85; test 0,96; **tổng 0,91** (171/187).
- Lỗi của quy tắc (`data/human_labels/rule_errors.csv`): kiểm tra license RAT không có chi tiết vi phạm (6), lỗi resolve
  plugin/artifact bị xếp infra thay vì dependency (4), một số test thực chất là flaky/infra.

Giới hạn: người phân xử cũng là người gán và đã thấy nhãn quy tắc khi phân xử; mới có một người gán; mẫu chỉ từ 17 repo cũ.
Cần thêm người gán thứ hai (~50 run) và mẫu từ repo mới.

## 4. Kiểm chứng ngoài: LogChunks (Brandt et al., MSR 2020)

LogChunks gồm 797 log Travis CI kèm **đoạn lý do fail** do người đánh dấu (được developer xác nhận). Bộ này **không có nhãn
loại lỗi**, nên không dùng làm khung nhãn được; dùng để kiểm tra quy tắc có **định vị** đúng dòng lỗi không
(`src/project3/crawl/logchunks_eval.py`).

| Tập | Quy tắc gán được | Dòng bằng chứng nằm trong đoạn người đánh dấu |
|---|---|---|
| JVM (60 log, 6 repo) | 31/60 (52%) | 3/31 (10%) |
| Tất cả ngôn ngữ (797 log) | 97/797 (12%) | 14/97 (14%) |

Cách đọc kết quả:
- Quy tắc viết cho log GitHub Actions (dựa vào `##[error]`, cách in của Maven/Gradle hiện nay), nên trên log Travis 2014–2019
  độ phủ thấp; ngôn ngữ khác JVM gần như không có quy tắc (đúng phạm vi đề tài).
- Dòng bằng chứng hay nằm ngoài đoạn người đánh dấu vì hai bên chọn mức chi tiết khác nhau: quy tắc chọn **dòng tổng kết**
  (vd. `Tests run: 2, Failures: 1 … FAILURE`), người đánh dấu chọn **dòng chi tiết** (vd. `expected: <false> but was: <true>`).
  Hai dòng cùng một lỗi nên đây không phải gán sai loại.
- Lỗ hổng thật cần sửa: thiếu mẫu sbt/ScalaTest (`*** FAILED ***`, `TestsFailedException`), MiMa (kiểm tra tương thích nhị
  phân của Scala); dương tính giả do javadoc warning chứa chữ "error" và WARNING "could not be resolved" bị xếp infra.

## 5. Đề xuất sửa quy tắc (chuyển cho Codex ở bước gán nhãn T3)

| # | Thay đổi | Căn cứ |
|---|---|---|
| 1 | RAT: chỉ gán lint khi có `Unapproved: [1-9]` hoặc danh sách file thiếu license; `apache-rat-plugin … check` đơn thuần thì để `?` | 6 lỗi trong tập người gán |
| 2 | Lỗi resolve plugin/artifact/POM không kèm dấu hiệu mạng (timeout, connection reset, 429/5xx) → dependency, không phải infra | 4 lỗi; định nghĩa "dependency" của Rausch |
| 3 | Thêm loại **buildconfig** (pom/gradle sai cú pháp, plugin cấu hình sai) và **doc** (javadoc error, không tính warning) | Bảng II Rausch; dương tính giả javadoc trên LogChunks |
| 4 | Thêm mẫu sbt/ScalaTest, MiMa, Android SDK/Lint, ktlint, detekt | LogChunks; repo Kotlin/Android mới |
| 5 | Sau khi sửa: chạy lại trên tập người gán (220 run) và LogChunks, báo cáo precision trước/sau | Quy trình kiểm chứng → sửa → đo lại |
