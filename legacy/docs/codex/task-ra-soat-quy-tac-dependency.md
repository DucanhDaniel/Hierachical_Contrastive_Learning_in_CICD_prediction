# Task: Rà soát quy tắc gán nhãn `dependency`

Ngày 18/10/2026. Rule version hiện hành `2026-10-15-buildconfig-doc` ([gold_labels.py](../../src/project3/crawl/gold_labels.py), [label_rules.json](../../configs/label_rules.json)).

## Vì sao làm

1. **Giả thuyết cần điều tra (chưa phải kết luận):** quy tắc có thể bỏ sót dependency (run nằm trong `?`) hoặc gán nhầm sang `infra`/`compile`.
   - Gợi ý từ Zheng et al. (TOSEM 2025): gán tay 375 job fail trên GitHub Actions (Java), nhóm con dependency (P3 không resolve được và P4 xung đột) chiếm 20,8%, cấu hình project (P2) chiếm 5,1%.
   - Nhãn quy tắc của đề tài có dependency 3,6% và buildconfig 0,5% số commit fail có nhãn.
   - **Hai con số không so trực tiếp được:** khác đơn vị (job với commit), khác tập mẫu (375 job ngẫu nhiên với 100 repo, chỉ commit đã có nhãn) và khác định nghĩa (P4 của Zheng gồm cả lệch phiên bản Java/Gradle). Chênh lệch chỉ là lý do để kiểm tra, không chứng minh quy tắc sai.
   - Chi tiết so sánh: [doi-chieu-paper-lien-quan.md](../doi-chieu-paper-lien-quan.md).
2. **Mục tiêu đề tài:** giảm lệch số mẫu các lá tầng 3. Crawl thêm repo không sửa được phần lệch do quy tắc gây ra.
3. **Lỗi đã biết từ vòng gán mù 10/10:** "infra nuốt dependency" (plugin/artifact resolve bị gán infra).

## Định nghĩa ranh giới (đang áp dụng, đã được người duyệt)

Cây nhãn: [khung-nhan-loi-build.md](../khung-nhan-loi-build.md). Thứ tự giai đoạn: buildconfig → compile → dependency → lint → test → flaky → infra.

| Nhãn | Gồm | Không gồm |
|---|---|---|
| **dependency** (build/dependency) | artifact/plugin không tồn tại hoặc không resolve được vì lý do của commit: version chưa phát hành, sai tọa độ, xung đột version mà công cụ build báo, lockfile chưa cập nhật, cài dependency JS (npm/yarn/pnpm) fail | lỗi mạng khi tải |
| **infra**, lá **network** (env/infra/network) | tải thất bại do mạng hoặc repo từ xa: timeout, connection reset/refused, 429, 5xx, SSL, `Could not transfer artifact` kèm lỗi mạng | |
| **buildconfig** | pom.xml / script Gradle sai: thiếu version, POM không parse được, project không có trong reactor | |
| **compile** | lỗi javac/kotlinc/scalac, kể cả do API của dependency đổi (lỗi lộ ra ở giai đoạn compile) | |
| **lint** | hiện gồm cả enforcer `Require upper bound dependencies` và `dependency:analyze` (`Used undeclared dependencies`, `Non-test scoped test only dependencies`). **Sẽ chuyển sang dependency theo Q1** | |

Quy ước cũ, không đổi nếu người chưa duyệt:
- `Failed to read artifact descriptor` đứng một mình thì giữ `?`.
- Resolve thất bại mà không chứng minh được lỗi mạng hay artifact không tồn tại thì giữ `?`.

## Quy tắc dependency hiện có

**Trong `GOLD_RULES` của `gold_labels.py`:**
- `resolution`: các câu tóm tắt Maven/Gradle (`Could not resolve dependencies`, `Could not resolve all files|dependencies`, `could not be resolved`, `Non-resolvable parent|import POM`, `Failed to read artifact descriptor`, `Unresolveable build extension`). Hàm `resolution_context` lấy ≤30 dòng sau câu tóm tắt rồi xét:
  - khớp `NETWORK` thì gán infra;
  - khớp `MISSING_ARTIFACT` thì gán dependency;
  - còn lại thì `?`.
- `dependency`: `Could not find artifact`, `Could not find g:a:v`, `was not found in https?://`, `No plugin found for prefix`. Nếu ngữ cảnh khớp `NETWORK` thì gán infra.
- `NETWORK` gồm cả mã **401 và 403**, xem quyết định Q2.

**Trong `configs/label_rules.json`** (chỉ chạy khi `GOLD_RULES` trả `?`):
- dependency ưu tiên 71–75: `Missing '…' dependency on the classpath`, lockfile chưa cập nhật, `npm error code ERESOLVE`, frontend-maven-plugin `yarn install`, exec-maven-plugin `pnpm install`.
- lint 34, 36, 44, 45: các rule enforcer / `dependency:analyze`. Rule 36 và 44 còn gắn tên artifact cụ thể (`org.codehaus.woodstox`, `org.checkerframework`), cần tổng quát hoá nếu giữ.
- infra 85: resolve kèm `Could not transfer artifact` và timeout.

## Số liệu ban đầu (quét log đã crawl, đợt 1: 100 repo có run fail)

Số run có log, theo nhãn hiện hành, chứa mỗi dạng tín hiệu (một run có thể khớp nhiều dạng). Script: [scripts/analysis/dep_signal_stats.py](../../scripts/analysis/dep_signal_stats.py).

| Tín hiệu | `?` (19.632 run) | dependency (1.627) | infra (5.090) |
|---|---:|---:|---:|
| Câu tóm tắt resolve | 388 | 1.066 | 814 |
| `Failed to read artifact descriptor` | 144 | 4 | 228 |
| `Could not transfer artifact` / `Could not GET/HEAD` | 313 | 9 | 830 |
| maven-enforcer (upper bound, convergence, banned) | 227 | 110 | 72 |
| Lệch phiên bản JDK (`UnsupportedClassVersionError`, `invalid target release`…) | 23 | 0 | 1 |
| Xung đột / không chọn được biến thể Gradle | 93 | 13 | 8 |
| Plugin không resolve được | 260 | 87 | 107 |
| Lockfile | 99 | 197 | 1 |
| Lỗi liên kết lúc chạy (`NoClassDefFoundError`, `NoSuchMethodError`…) | 125 | 0 | 27 |
| HTTP 401/403, Unauthorized, Forbidden | 187 | 9 | 300 |
| Dependency JS (`ERESOLVE`, `Cannot find module`, `ERR_PNPM_`) | 144 | 204 | 1 |

**Nhận xét ban đầu (Codex cần kiểm tra lại):**
- **Khoảng 800 run infra** có câu tóm tắt resolve, và **300 run infra** có 401/403. Đây là chỗ nghi "infra nuốt dependency":
  - 401/403 có thể là thiếu credential (lá `auth` đang đề xuất);
  - cũng có thể là repo trả 403 cho artifact không tồn tại.
- **Tín hiệu dependency trong `?` chỉ vài trăm run mỗi dạng.** Các dạng chồng lặp nhau; số run duy nhất khớp ít nhất một dạng (không tính 401/403) là `?` **1.254/19.632 (6,4%)**, infra 921/5.090, dependency 1.457/1.627. Các mẫu regex ở bảng này là mẫu rộng để đếm, không phải quy tắc gán nhãn. Hai khả năng cho phần còn lại: log đã lưu bị cắt (chỉ còn `BUILD FAILED`), hoặc lỗi xung đột lộ ra dưới dạng compile/test (bước 4).

## Việc cần làm

1. **Đo tỉ lệ phù hợp theo rà soát của Codex** (chưa được người xác nhận) cho nhãn dependency và infra dính tới resolve.
   - Lấy mẫu phân tầng khoảng 30 run mỗi nhóm, đọc log, ghi "phù hợp / không phù hợp / chưa rõ" kèm lý do một dòng:
     - dependency qua `resolution`, qua `dependency`, qua từng rule fallback;
     - infra có câu tóm tắt resolve;
     - infra có 401/403.
   - **Không gọi kết quả là precision.** Chỉ gọi là precision kiểm chứng khi có nhãn tham chiếu do người duyệt.
   - Báo tỉ lệ kèm số "chưa rõ" riêng, không gộp vào phù hợp hay không phù hợp.
   - Lưu lại để chạy lại được: seed, danh sách run_id theo nhóm, ghi chú từng run, vào `data/human_labels/codex_review_dependency_<ngày>.jsonl`. File này **không phải nhãn người**, tên phải giữ tiền tố `codex_review_`.
2. **Rà các nhóm trong `?`:**
   - Gom run `?` có tín hiệu ở bảng trên theo chữ ký dòng lỗi, như cách làm open coding trước đây (`label_ui.py opencode` / `review_rules.py`).
   - Với từng cụm: đề xuất nhãn **tầng 2** (`dependency` / `infra` / `buildconfig` / `compile` / `lint` / `?`) và, nếu cần, lá tầng 3 đề xuất (ví dụ `infra` + lá `network`). Kèm regex, số run khớp và 3 log mẫu.
   - Ưu tiên các nhóm: plugin không resolve được, câu tóm tắt resolve còn để `?`, xung đột Gradle, enforcer, lockfile, JS.
3. **Kiểm tra `NETWORK` và `MISSING_ARTIFACT`:**
   - Giữ 401/403 trong `NETWORK` (Q2). Chỉ báo số run infra có 401/403 để tham khảo.
   - **Chỉ gán dependency khi có bằng chứng về nguyên nhân cụ thể;** thiếu bằng chứng thì giữ `?` (cùng tinh thần Q4).
     - Câu tóm tắt như `Could not resolve plugin artifact` hay `Plugin [id: …] was not found in any of the following sources` tự nó **không** chứng minh artifact thiếu. Phải xét ngữ cảnh: không có lỗi mạng (`NETWORK`) và có dấu hiệu không tồn tại (404, `Could not find`, danh sách `Searched in the following locations` không kèm lỗi tải).
     - `No matching variant` / `incompatible because this component declares` là **không tương thích biến thể** (thường là phiên bản JVM hoặc thuộc tính Gradle), không phải artifact thiếu. Xét theo Q3 (lệch phiên bản → dependency) và nêu riêng thành một cụm, không gộp vào `MISSING_ARTIFACT`.
   - Bổ sung dạng mạng còn thiếu, ví dụ `Could not GET … Received status code 5xx` nếu chưa khớp.
4. **Xung đột lộ ra dưới dạng compile/test** (P4 của Zheng): theo Q3, các lỗi này là dependency.
   - Đề xuất quy tắc, đo tỉ lệ phù hợp theo rà soát (như bước 1).
   - Báo số run đổi nhãn từ compile, test và `?` sang dependency.
   - Cài đặt theo cách tổng hợp nhiều job ở mục Q3.
5. **Tổng quát hoá rule fallback** đang gắn tên artifact cụ thể (36, 44) nếu chúng được giữ.
6. **Viết bộ chạy đánh giá riêng** `src/project3/pipeline/rule_eval.py` (mới).
   - **Vì sao cần:** `relabel.py` ghi cố định vào dữ liệu chính (CSV/Parquet), thư mục audit chỉ là bản sao lưu nên chạy `relabel` không phải mô phỏng. `review_rules.py` chỉ thử từng regex riêng theo thứ tự cố định trên mẫu, không chạy lại cả bộ phân loại và chưa đọc `round3/4_decisions.json`.
   - **Phạm vi cố định (tái lập được):**
     - Chỉ chạy trên các run trong `data/rule_eval/scope_r1_20261018.csv` (repo, run_id, root): 100 repo, 94.293 run, đã khử trùng theo (repo, run_id).
     - Kèm `scope_r1_20261018.manifest.json` ghi sha256 của file phạm vi, hai `gold_labels.csv`, `gold_labels.py`, `label_rules.json` và `RULE_VERSION` lúc cố định.
     - Crawl đợt 2 sẽ gộp thêm repo vào `data/crawl_pr|validate`. `rule_eval` phải lọc theo file phạm vi, không quét cả thư mục.
     - Mỗi lần chạy ghi `manifest.json` vào thư mục đầu ra: file phạm vi và hash; hash của bộ quy tắc hiện hành và bộ đề xuất; danh sách log đã đọc (số file và sha256 của danh sách đường dẫn đã sắp xếp); run thiếu log; thời gian chạy.
     - Nếu hash `gold_labels.csv` khác manifest phạm vi (do relabel hoặc gộp đợt 2) thì cảnh báo, và lấy nhãn "hiện hành" bằng cách chạy lại bộ hiện hành trên log, không đọc CSV.
   - **Yêu cầu:**
     - Chạy **toàn bộ** bộ phân loại (`GOLD_RULES` + fallback + `fine_labels.subtype`) hai lần trên log đã có: một lần với bộ hiện hành, một lần với bộ đề xuất. Bộ đề xuất nạp từ file đề xuất, hoặc từ cờ, hoặc nhánh code tách riêng; không sửa bộ hiện hành.
     - **Chỉ ghi vào thư mục đầu ra** truyền qua tham số (mặc định `data/rule_eval/<ngày>/`). Không ghi vào `data/crawl_pr`, `data/validate`, `data/dataset`, `data/processed`.
   - **Báo cáo đầu ra:**
     - số run `?` trước/sau;
     - ma trận đổi nhãn theo run (tầng 2 và lá tầng 3, cũ → mới), kèm `run_changes.csv` (run_id, nhãn cũ, nhãn mới, bằng chứng mới);
     - ước tính số commit đổi nhãn theo lá tầng 3 (gộp run → commit như `build_log_labels`);
     - xung đột với nhãn người: `labels.jsonl` + `adjudication.jsonl` (dòng cuối có hiệu lực), `blind3/` nếu đã có nhãn, và quyết định cụm trong `round3_decisions.json`, `round4_decisions.json` (đối chiếu theo run thuộc cụm);
     - thời gian chạy và run chậm nhất. Regex phải có lượng từ giới hạn, `\S{1,200}` thay cho `\S+`.
   - Có test nhỏ khẳng định bộ chạy không ghi ra ngoài thư mục đầu ra.

## Sản phẩm bàn giao

1. `docs/codex/ra-soat-dependency-2026-10-XX.md`: kết quả bước 1–6, bảng tỉ lệ phù hợp theo rà soát (có cột "chưa rõ"), danh sách cụm đề xuất, kết quả `rule_eval`.
2. `src/project3/pipeline/rule_eval.py` và test của nó.
3. `configs/label_rules_dependency_proposed.json`: các quy tắc đề xuất, cùng định dạng `label_rules.json` (`label`, `regex`, `signature`, `matches_unlabeled`, `conflicts_in_human_sample`, `note`, `origin: "codex-proposed"`).
   - `label` **luôn là nhãn tầng 2** như bộ hiện hành: `dependency`, `infra`, `buildconfig`, `compile`, `lint`, `test`, `flaky`, `non_build`. Không bao giờ ghi `network` vào `label`.
   - Lá tầng 3 ghi ở trường riêng `leaf_proposed` (ví dụ `network`, `dependency`). Lá thực tế vẫn do `fine_labels.subtype` tính. Nếu đề xuất cần đổi `subtype` (ví dụ thêm mẫu vào `INFRA` network) thì ghi riêng trong báo cáo.
   - Quy tắc Q3 dùng `label: "dependency"` và trường `layer: "q3_override"` để `rule_eval` biết áp theo cách tổng hợp ở mục Q3.
4. `docs/duyet-quy-tac-dependency-2026-10-XX.xlsx`: bảng để người duyệt, giống các file `duyet-quy-tac-*.xlsx` trước. Mỗi dòng có các cột: quy tắc, nhãn đề xuất, cột nhãn người chọn (để trống; nhãn trùng đề xuất nghĩa là đồng ý), số run, 2–3 dòng log mẫu.
5. Test mới trong `tests/test_gold_labels.py` cho mỗi ranh giới được sửa. **Chỉ thêm sau khi người duyệt.**

**Chỉ tích hợp vào `gold_labels.py` / `label_rules.json` sau khi người duyệt bảng xlsx.** Khi tích hợp:
- đổi `RULE_VERSION` ở cả hai nơi;
- chạy lại `relabel` (có sao lưu), rồi `export_dataset`;
- báo số commit theo lá tầng 3 trước/sau.

## Quyết định của người dùng (18/10/2026)

- **Q1. Enforcer và `dependency:analyze` chuyển từ lint sang dependency.** Phạm vi: upper bound, convergence, banned dependencies, `Used undeclared dependencies`, `Non-test scoped test only dependencies`. Thay quyết định ngày 10/10.
  - Sửa nhãn các rule fallback 34, 36, 44, 45 (tổng quát hoá 36, 44 bỏ tên artifact).
  - Thêm regex enforcer vào lớp dependency.
  - Kiểm tra test hiện có nào đang khẳng định các dạng này là lint.
- **Q2. HTTP 401/403 khi tải artifact là network.** Giữ `NETWORK` như hiện tại, không tách 401/403. Bước 3 bỏ phần "tách 401/403"; vẫn báo số run để tham khảo.
- **Q3. Lệch phiên bản JDK và lỗi liên kết do xung đột thư viện là dependency** (theo nguyên nhân gốc, không theo giai đoạn).
  - Bước 4 đổi từ "chỉ thống kê" sang **đề xuất quy tắc**.
  - Ứng viên: `UnsupportedClassVersionError`, `class file has wrong version`, `has been compiled by a more recent version`, `Unsupported class file major version`, `invalid target release`, `release version N not supported`; `NoSuchMethodError`, `NoSuchFieldError`, `AbstractMethodError`, `IncompatibleClassChangeError`.
  - **Cần thận trọng:**
    - `NoClassDefFoundError: Could not initialize class` là lỗi khởi tạo static, không phải xung đột, phải loại ra.
    - `ClassNotFoundException` hay xuất hiện trong log test bình thường; chỉ tính khi đó là nguyên nhân làm fail (gần dòng fail hoặc ở `Caused by` cuối).
  - Báo tỉ lệ phù hợp theo rà soát của Codex (như bước 1) trước khi đưa vào bảng duyệt.
  - **Cách tổng hợp khi run có nhiều job: Q3 chỉ là lớp ghi đè hẹp, mọi trường hợp khác giữ nguyên kết quả hiện hành.**
    - Thứ tự trong `GOLD_RULES` **không** phải thứ tự giai đoạn (lint, resolution, infra mạnh đứng trước test; dependency thiếu artifact đứng sau test), và `base_gold_label` duyệt quy tắc trước rồi mới duyệt job. **Không đổi cơ chế này.** Đổi thứ tự chung giữa các job (ví dụ lint + artifact thiếu, test + artifact thiếu, hết dung lượng + test) là đề xuất riêng, ngoài phạm vi task. Nếu Codex thấy cần thì ghi vào báo cáo để người duyệt.
    - Cài đặt (Claude đề xuất, người dùng xác nhận khi duyệt bảng):
      1. Tính nhãn run R và **job quyết định** j* bằng bộ hiện hành. Cần sửa `base_gold_label` để trả thêm chỉ số job khớp, không đổi kết quả.
      2. R ∈ {compile, test} và **chính job j\*** có tín hiệu Q3 → đổi thành dependency.
      3. R = `?` và có job nào đó có tín hiệu Q3 → dependency.
      4. Mọi trường hợp khác giữ R, kể cả buildconfig, lint, infra, flaky, dependency.
    - Ví dụ:
      - Job A lỗi javac thật, job B có `NoSuchMethodError` trong test → j* = A, A không có Q3 → **compile**.
      - Job A có `NoSuchMethodError` làm test fail, R = test từ A → **dependency**.
      - Job A chỉ có `UnsupportedClassVersionError` (không khớp quy tắc nào), job B test fail → R = test từ B, B không có Q3 → **test**. Đây là giới hạn đã biết của cách làm hẹp; báo số run rơi vào dạng này.
    - **Test hồi quy bắt buộc:** so ba cấu hình trên cùng phạm vi để tách tác động của từng nhóm thay đổi:
      1. **Bộ hiện hành.**
      2. **Bộ hiện hành + chỉ thay đổi cơ chế Q3:** gồm sửa `base_gold_label` để trả job quyết định, và lớp Q3. Chưa bật Q1, chưa bật các rule đề xuất khác.
         - Khi lớp Q3 tắt (chỉ còn sửa `base_gold_label`): nhãn mọi run phải trùng cấu hình 1.
         - Khi bật Q3: run đổi nhãn so với cấu hình 1 chỉ được là compile/test/`?` → dependency.
      3. **Bộ đề xuất đầy đủ:** Q1 + Q3 + các rule mới. Báo ma trận đổi nhãn so với cấu hình 1 và so với cấu hình 2, để thấy phần đổi do Q1/rule mới (ví dụ lint → dependency) riêng với phần đổi do Q3.
  - Đo số run đổi nhãn compile → dependency và test → dependency (bước 6), kèm 10 ví dụ mỗi chiều trong báo cáo.
- **Q4. `Failed to read artifact descriptor` khi ngữ cảnh không rõ: giữ `?`.**

Khi tích hợp, cập nhật bảng ranh giới ở trên và [khung-nhan-loi-build.md](../khung-nhan-loi-build.md) theo Q1 và Q3.

## Không làm

- Không dùng LLM để gán nhãn (ràng buộc C-02). Đề xuất của Codex là đề xuất quy tắc, phải qua người duyệt.
- Không sửa nhãn người: `labels.jsonl`, `adjudication.jsonl`, `key*.json`, `round*_decisions.json`, `tier3_approval.json`.
- Không ghi đè `data/dataset/`, `data/crawl_pr|validate/gold_labels.csv` trước khi người duyệt.
- Không sửa crawler (`crawl/gha.py`, `crawl/github.py`); crawl đợt 2 đang chạy trên Kaggle.
- Không gộp lượt 3–4 open coding (đang tạm dừng theo người dùng) vào task này.
- Lượt này chỉ xét phạm vi cố định ở bước 6 (đợt 1). Log đợt 2 (`configs/repos_r2.txt`) về sau dùng làm tập kiểm tra quy tắc mới trên repo chưa thấy.
