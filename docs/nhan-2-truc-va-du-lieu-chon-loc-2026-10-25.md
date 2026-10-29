# Nhãn 2 trục (vị trí × giai đoạn) và dữ liệu chọn lọc

> **Đã thay thế (25/10/2026, sau khi nghe lại ghi âm):** GV không bảo bỏ cây. Xem
> [cay-nhan-3-tang-2026-10-25.md](cay-nhan-3-tang-2026-10-25.md). Trục giai đoạn ở đây vẫn dùng, nhưng làm "chỗ tìm thấy
> lỗi": đầu vào của mô hình và căn cứ để gán tầng thời điểm cần sửa. Mục 5 (dữ liệu chọn lọc) vẫn còn hiệu lực.

Cập nhật 25/10/2026, theo góp ý của GVHD:
- không làm cây nhãn nhiều tầng; nhãn mang thông tin về **vị trí** lỗi (hậu quả của thay đổi) và **giai đoạn** DevOps phát sinh lỗi;
- crawl thêm ngẫu nhiên không chữa được mất cân bằng; phải chọn lọc dữ liệu (dự án Android, giới hạn 1–2 ngôn ngữ).

Mã: `project3.crawl.stages` (quy tắc + thống kê), `project3.pipeline.stage_review` (kiểm chứng bằng người),
`project3.pipeline.probe_rare --set android` và `kaggle_targeted --round android` (đợt crawl Android). Kết quả ở
`data/run_dataset/axes.parquet`.

## 1. Vì sao bỏ cây

Cây cũ (22/10) có 3 tầng: lỗi do commit? (change/external) → sửa ở đâu? (code/buildsys/ci_infra/flaky) → 15 lá.
Vướng mắc chính:

1. **Lỗi runner không có chỗ đứng rõ ràng.** Runner sập lúc đang chạy test là `crash`, nhưng thông tin "đang chạy test"
   bị mất. Lỗi Android SDK, lỗi mạng khi tải phụ thuộc và lỗi mạng khi chạy test bị gộp chung một nhánh.
2. **Lá trộn hai thông tin khác nhau.** `itestfailure` vừa nói *vị trí* (mã nguồn/test) vừa nói *giai đoạn* (test tích hợp);
   `network` chỉ nói vị trí (môi trường) mà không nói giai đoạn.
3. **Lá hiếm không học được:** androidsdk 2 run, compatibility 44, flaky 65, doc 158. Crawl nhắm thẳng lá hiếm (đợt 3)
   cũng không tìm thêm được: mẫu 1.098 run có 0 run compatibility và 0 run androidsdk.

## 2. Hai trục

| Trục | Câu hỏi | Giá trị |
|---|---|---|
| **location** | Lỗi nằm ở đâu, phải sửa cái gì? | `code` (mã nguồn, mã test) · `build` (cấu hình build, phụ thuộc) · `env` (runner, mạng, dịch vụ ngoài) |
| **stage** | Lỗi phát sinh ở giai đoạn nào của pipeline? | `setup` · `prepare` · `compile` · `check` · `test` · `itest` · `package` |

Định nghĩa các giai đoạn:

| stage | Gồm | Ví dụ công cụ |
|---|---|---|
| setup | chuẩn bị môi trường | checkout, setup-java, cache, tải action, kéo image Docker, emulator/SDK, runner |
| prepare | chuẩn bị build | đọc pom/Gradle script, enforcer, tải phụ thuộc |
| compile | biên dịch, sinh mã | maven-compiler, compileJava/Kotlin, kapt/ksp, protobuf, xử lý resource Android |
| check | kiểm tra tĩnh | spotless, checkstyle, detekt, ktlint, javadoc, RAT/license, revapi/japicmp, dependency:analyze |
| test | test đơn vị | surefire, task `test`, testDebugUnitTest |
| itest | test tích hợp/e2e/chức năng | failsafe, integTest, funTest, connectedAndroidTest, surefire ở module `*-it`/`*-e2e` |
| package | đóng gói, phát hành | jar, shade, assemble, docker build, publish |

- **flaky** không phải vị trí mà là tính chất (fail rồi chạy lại thì qua). Nó thành cờ `flaky`, với location = code
  và stage lấy theo log.
- **Lỗi runner** được xếp tự nhiên: location = env, stage = bước đang chạy khi hỏng. Ví dụ runner sập lúc chạy test
  là env × test; mạng hỏng khi tải phụ thuộc là env × prepare; Android SDK/emulator là env × setup.
- **Lá cũ** trở thành tổ hợp của hai trục: compile = code × compile; quality/doc/license/compatibility = code × check;
  testfailure/itestfailure = code × test/itest; dependency = build × (thường là prepare); buildconfig = build × prepare.
- **Thủ tục PR** (changelog-enforcer, Jira, kiểm tra tiêu đề PR, DCO/sign-off) không phải lỗi build. Run loại này có cờ
  `governance` và bị loại ra.

## 3. Cách gán (quy tắc, không dùng LLM)

- **location** ánh xạ trực tiếp từ loại lỗi của bộ quy tắc đã kiểm chứng (`LOCATION` trong `crawl.stages`).
- **stage** lấy từ nguồn đầu tiên có kết quả, theo thứ tự sau. Cột `stage_src` ghi lại nguồn đã dùng.
  1. `tool` cho nhóm test: test hay itest quyết định theo công cụ/module bị fail. Quy tắc cũ dựa vào tên workflow/job,
     kém hơn: lá cũ và công cụ fail chỉ khớp 49% với itestfailure và 78% với testfailure.
  2. `leaf`: lá đã tự nói giai đoạn (compile → compile, quality → check, buildconfig → prepare).
  3. `tool`: goal Maven / task Gradle bị fail (`Failed to execute goal …`, `Execution failed for task …`,
     `> Task :x FAILED`). Nếu có nhiều công cụ fail thì lấy giai đoạn sớm nhất, vì nguyên nhân gốc đi trước.
  4. `evidence`: dòng bằng chứng khớp mẫu của một giai đoạn (`Could not resolve` → prepare, `runner has received a
     shutdown` → setup).
  5. `context`: goal/task cuối cùng bắt đầu chạy trước dòng bằng chứng trong cùng đoạn log.
  6. `step`: tên step fail. Bỏ step tổng hợp ("Check results") và tên chung chung ("Build").

## 4. Kết quả trên dữ liệu trước đợt 3 (98 + 102 repo, 84.094 run có log)

| | Kết quả |
|---|---|
| Run có loại lỗi được gán stage | 56.663 / 57.546 (98,5%) |
| Run `?` (quy tắc chưa gán loại lỗi) được gán stage | 13.297 / 26.548 (50,1%); 3.131 run là thủ tục PR |
| location khớp nhãn người (187 run, 17 repo cũ) | **0,963** (bộ 7 loại cũ: precision 0,914) |
| Lá ↔ công cụ fail tự khớp | 79,5% (compile 0,93, quality 0,99, license 0,98, doc 0,91) |

Bảng ô location × stage: xem mục 6, cập nhật sau khi gộp đợt 3.

**Kiểm chứng stage bằng người (đang chờ):** bảng `docs/gan-giai-doan-2026-10-25.xlsx` có 140 run, lấy mẫu phân tầng
theo stage × nguồn. Người gán **không thấy** đề xuất của quy tắc; đáp án để riêng ở `data/human_labels/stage_key.json`.
Chấm bằng lệnh `uv run --with openpyxl python -m project3.pipeline.stage_review eval`.

## 5. Dữ liệu chọn lọc

- **Ngôn ngữ:** 221 repo hiện có gồm Java 182, Kotlin 36 và Groovy 3 (theo GitHub, `data/processed/repo_meta.jsonl`).
  Phạm vi chốt là **Java + Kotlin trên JVM** (Maven/Gradle), bỏ 3 repo Groovy. Bộ quy tắc vốn được viết cho Maven/Gradle.
- **Không crawl ngẫu nhiên thêm.** Mỗi đợt mới chỉ lấy run fail của các workflow được chọn có chủ đích, và ghi `scope`
  trong `crawl_status.json`. Khi đánh giá phải tách theo đợt để dữ liệu chọn lọc không thổi phồng kết quả.
- **Đợt 3 (targeted-r3, 22/10):** 20 repo, khoảng 3.200 run fail; đã gộp ngày 25/10.
- **Đợt Android (targeted-android):** chọn workflow build/test app Android (android-emulator-runner, connectedAndroidTest,
  assembleDebug, lintDebug …) của repo Java/Kotlin chưa crawl, có ≥20 run fail trong 90 ngày, tối đa 2 workflow/repo,
  ≤200 run/workflow. Crawl chạy trên Kaggle (kernel `p3-crawl-android`).
- **Ngưỡng ô:** ô location × stage nào dưới 300 run thì không học riêng (gộp hoặc bỏ). Tập train giới hạn số run mỗi ô và
  mỗi repo; tập test giữ phân bố thật.

## 6. Bảng ô location × stage

(điền sau khi chạy lại nhãn có đợt 3)
