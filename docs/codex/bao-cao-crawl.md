# Báo cáo crawl mở rộng dữ liệu

Cập nhật 2026-10-07 21:34:20 +0700. Pipeline: `T1-core-pr` / `running`. Thời gian từ lúc khởi chạy: 0:11:04.487150.

Worker mở rộng song song: `T2-extra-pr` / `running`; theo dõi `data/crawl_extra_push.log` hoặc `data/crawl_extra_pr.log`. Checkpoint/điều khiển: `docs/codex/crawl-control.md`.

Số liệu commit đọc trực tiếp từ `data\processed\commits_all_snapshot.parquet` (mtime: 2026-10-07T21:31:55.491299+07:00). Khi crawl còn chạy, đây là ảnh chụp tạm thời; chưa phải bộ dữ liệu hoàn tất.

## Repo × event

| repo | event | commit | fail | % fail | fail đầu | từ (UTC) | đến (UTC) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| apache/camel-quarkus | push | 97 | 31 | 31.96 | 23 | 2026-07-09T12:46:05Z | 2026-10-07T08:09:36Z |
| apache/druid | pull_request | 2176 | 761 | 34.97 | 512 | 2026-07-09T14:03:52Z | 2026-10-07T05:05:34Z |
| apache/druid | push | 634 | 183 | 28.86 | 113 | 2026-07-09T10:08:18Z | 2026-10-07T02:02:40Z |
| apache/fluss | push | 273 | 41 | 15.02 | 33 | 2026-07-09T13:08:09Z | 2026-10-06T15:45:55Z |
| apache/gravitino | push | 505 | 47 | 9.31 | 40 | 2026-07-09T00:54:17Z | 2026-10-06T04:08:21Z |
| apache/groovy | push | 401 | 83 | 20.7 | 53 | 2026-07-10T20:51:49Z | 2026-10-07T05:14:34Z |
| apache/iceberg | push | 530 | 31 | 5.85 | 20 | 2026-07-09T00:38:08Z | 2026-10-06T20:16:12Z |
| apache/ignite | push | 203 | 3 | 1.48 | 3 | 2026-07-09T14:04:32Z | 2026-10-06T16:43:21Z |
| apache/iotdb | push | 322 | 205 | 63.66 | 59 | 2026-07-09T10:27:38Z | 2026-10-06T14:13:15Z |
| apache/kafka | push | 370 | 64 | 17.3 | 45 | 2026-07-09T06:20:40Z | 2026-10-06T19:14:29Z |
| apache/ozone | pull_request | 2162 | 756 | 34.97 | 415 | 2026-07-09T15:50:18Z | 2026-10-07T08:06:19Z |
| apache/ozone | push | 545 | 254 | 46.61 | 122 | 2026-07-09T19:15:16Z | 2026-10-07T07:32:51Z |
| apache/paimon | pull_request | 4421 | 1281 | 28.98 | 848 | 2026-07-09T08:27:16Z | 2026-10-07T06:28:53Z |
| apache/paimon | push | 1024 | 252 | 24.61 | 172 | 2026-07-09T04:02:25Z | 2026-10-07T03:11:08Z |
| apache/pinot | pull_request | 3415 | 807 | 23.63 | 431 | 2026-07-09T11:03:08Z | 2026-10-07T06:43:11Z |
| apache/pinot | push | 411 | 74 | 18.0 | 63 | 2026-07-09T00:00:39Z | 2026-10-07T01:35:54Z |
| apache/polaris | push | 524 | 36 | 6.87 | 26 | 2026-07-09T12:10:32Z | 2026-10-07T07:51:10Z |
| apache/storm | push | 177 | 10 | 5.65 | 8 | 2026-07-11T14:25:34Z | 2026-10-03T09:48:59Z |
| apache/tika | push | 404 | 33 | 8.17 | 25 | 2026-07-09T11:08:00Z | 2026-10-06T23:39:00Z |
| apache/tomcat | push | 374 | 85 | 22.73 | 26 | 2026-07-09T14:22:14Z | 2026-10-07T07:51:31Z |

## Nhãn commit fail

| cause | label_group | label | commit fail | % | fail đầu |
| --- | --- | --- | --- | --- | --- |
| ? | ? | ? | 2419 | 48.02 | 1336 |
| code | build | compile | 305 | 6.06 | 174 |
| code | build | dependency | 39 | 0.77 | 19 |
| code | build | lint | 155 | 3.08 | 102 |
| code | test | test | 1723 | 34.21 | 1118 |
| env | env | flaky | 2 | 0.04 | 2 |
| env | env | infra | 394 | 7.82 | 286 |

## Tiêu chí số lượng và coverage

| chỉ số | thực tế | mục tiêu | kết quả |
| --- | --- | --- | --- |
| Commit fail cause=code | 2222 | >= 2000 | đạt tại ảnh chụp |
| Commit fail test | 1723 | >= 300 | đạt tại ảnh chụp |
| Commit fail compile | 305 | >= 300 | đạt tại ảnh chụp |
| Commit fail lint | 155 | >= 300 | chưa đạt |
| Commit fail ? | 48.02% | < 5% | chưa đạt |
| Run fail không có log sử dụng được | 2952/8938 (33.03%) | < 5% | chưa đạt |

## Kiểm chứng mẫu thủ công

Phạm vi mẫu đã lưu: data\validate. Các đánh giá thuộc đúng mẫu/fingerprint này; chưa phải kết quả kiểm chứng mẫu mới cho toàn bộ dữ liệu PR và repo mở rộng.

Seed `20261007`; mỗi nhãn tối đa 20 run riêng biệt. Kết quả chỉ được công nhận khi fingerprint đoạn log trùng với đánh giá đã lưu. `uncertain` không được tính là đúng. Đây là độ phù hợp với bằng chứng log giữ lại, chưa chứng minh nguyên nhân của mọi lần fail hoặc accuracy toàn quần thể.

| nhãn | mẫu / 20 | đúng | sai | chưa đủ bằng chứng | chưa đọc | % đúng trên mẫu | kết quả |
| --- | --- | --- | --- | --- | --- | --- | --- |
| compile | 20 | 20 | 0 | 0 | 0 | 100.0% | đạt mẫu |
| lint | 20 | 20 | 0 | 0 | 0 | 100.0% | đạt mẫu |
| dependency | 18 | 18 | 0 | 0 | 0 | 100.0% | chưa đạt/chưa đủ |
| test | 20 | 20 | 0 | 0 | 0 | 100.0% | đạt mẫu |
| infra | 20 | 17 | 0 | 3 | 0 | 85.0% | chưa đạt/chưa đủ |
| flaky | 2 | 2 | 0 | 0 | 0 | 100.0% | chưa đạt/chưa đủ |

| nhãn | repo | run | đánh giá | lý do |
| --- | --- | --- | --- | --- |
| infra | apache/druid | 31668531413 | uncertain | Đoạn log chỉ ghi extension không resolve được, không giữ nguyên nhân mạng hoặc artifact không tồn tại. |
| infra | apache/druid | 34004419071 | uncertain | Đoạn log chỉ ghi extension không resolve được, không giữ nguyên nhân mạng hoặc artifact không tồn tại. |
| infra | apache/druid | 33133676303 | uncertain | Đoạn log chỉ ghi extension không resolve được, không giữ nguyên nhân mạng hoặc artifact không tồn tại. |

## Run thiếu log

Mẫu số gồm mọi run failure của workflow build đã lưu, kể cả run chưa tải jobs. Run có ít nhất một log không rỗng được tính có log; `thiếu một phần` ghi riêng (PR chủ ý chỉ tải tối đa 2 job). `.missing` có thể là hết hạn hoặc tải thất bại, không thể phân biệt từ marker hiện tại.

| root | repo | run fail | không log | chưa có jobs | có marker missing | thiếu một phần | % không log |
| --- | --- | --- | --- | --- | --- | --- | --- |
| data\validate | apache/camel-quarkus | 31 | 1 | 0 | 0 | 0 | 3.23 |
| data\validate | apache/druid | 206 | 1 | 0 | 2 | 1 | 0.49 |
| data\validate | apache/fluss | 48 | 0 | 0 | 0 | 0 | 0.0 |
| data\validate | apache/gravitino | 54 | 1 | 0 | 1 | 0 | 1.85 |
| data\validate | apache/groovy | 95 | 1 | 0 | 1 | 0 | 1.05 |
| data\validate | apache/iceberg | 50 | 12 | 0 | 5 | 0 | 24.0 |
| data\validate | apache/ignite | 3 | 1 | 0 | 0 | 0 | 33.33 |
| data\validate | apache/iotdb | 365 | 16 | 0 | 15 | 0 | 4.38 |
| data\validate | apache/kafka | 64 | 2 | 0 | 0 | 0 | 3.12 |
| data\validate | apache/ozone | 254 | 10 | 0 | 6 | 1 | 3.94 |
| data\validate | apache/paimon | 364 | 0 | 0 | 0 | 0 | 0.0 |
| data\validate | apache/pinot | 81 | 2 | 0 | 1 | 0 | 2.47 |
| data\validate | apache/polaris | 37 | 4 | 0 | 1 | 0 | 10.81 |
| data\validate | apache/pulsar | 0 | 0 | 0 | 0 | 0 | 0.0 |
| data\validate | apache/storm | 10 | 0 | 0 | 0 | 0 | 0.0 |
| data\validate | apache/tika | 48 | 6 | 0 | 0 | 0 | 12.5 |
| data\validate | apache/tomcat | 97 | 0 | 0 | 0 | 0 | 0.0 |
| data\crawl_pr | apache/druid | 1211 | 55 | 0 | 3 | 406 | 4.54 |
| data\crawl_pr | apache/ozone | 1302 | 1302 | 1216 | 0 | 0 | 100.0 |
| data\crawl_pr | apache/paimon | 3119 | 39 | 16 | 8 | 179 | 1.25 |
| data\crawl_pr | apache/pinot | 1499 | 1499 | 221 | 0 | 0 | 100.0 |

## Nhãn ? theo repo và workflow

| root | repo | workflow | run ? |
| --- | --- | --- | --- |
| data\crawl_pr | apache/druid | Static Checks CI | 296 |
| data\crawl_pr | apache/druid | Unit & Integration tests CI | 174 |
| data\validate | apache/iotdb | Sonar-Codecov | 146 |
| data\validate | apache/ozone | build-branch | 138 |
| data\crawl_pr | apache/druid | PR Commit Checks | 80 |
| data\crawl_pr | apache/druid | Cron Job ITs | 76 |
| data\validate | apache/tomcat | Smoke Test - MacOS | 62 |
| data\validate | apache/iotdb | Cluster IT - 1C1D1A | 21 |
| data\crawl_pr | apache/paimon | Python Check Code Style and Test | 21 |
| data\validate | apache/camel-quarkus | Camel Quarkus CI | 20 |
| data\validate | apache/pinot | Pinot Integration Tests | 17 |
| data\validate | apache/druid | Unit & Integration tests CI | 16 |
| data\validate | apache/iotdb | Table Cluster IT - 1C3D | 11 |
| data\validate | apache/groovy | Build and test | 10 |
| data\validate | apache/tomcat | Validate code | 10 |
| data\validate | apache/tomcat | Smoke Test | 8 |
| data\validate | apache/pinot | Pinot Compatibility Checks | 7 |
| data\validate | apache/gravitino | Backend Integration Test | 6 |
| data\crawl_pr | apache/paimon | CI | 6 |
| data\validate | apache/druid | Static Checks CI | 5 |
| data\validate | apache/kafka | CI | 5 |
| data\crawl_pr | apache/paimon | UTCase and ITCase Spark 3.x | 5 |
| data\validate | apache/groovy | Performance check | 4 |
| data\validate | apache/iotdb | Cluster IT - 1C3D | 4 |
| data\validate | apache/tika | main jdk21 build | 4 |
| data\validate | apache/fluss | Client Integration | 3 |
| data\validate | apache/gravitino | build | 3 |
| data\validate | apache/storm | Java CI with Maven | 3 |
| data\validate | apache/tika | main jdk17 windows build (de_DE) | 3 |
| data\validate | apache/tika | main jdk25 build | 3 |
| data\crawl_pr | apache/paimon | UTCase and ITCase Others | 3 |
| data\crawl_pr | apache/paimon | End to End Tests Flink 2.x on JDK 11 | 3 |
| data\validate | apache/ignite | Sonar Quality Branch Analysis | 2 |
| data\validate | apache/iotdb | Multi-Cluster IT | 2 |
| data\validate | apache/tika | Docker snapshot - tika-server and tika-grpc | 2 |
| data\crawl_pr | apache/paimon | Check licensing | 2 |
| data\crawl_pr | apache/paimon | End to End Tests Flink 1.x | 2 |
| data\crawl_pr | apache/paimon | UTCase and ITCase Flink 2.x on JDK 11 | 2 |
| data\crawl_pr | apache/paimon | UTCase and ITCase Flink 1.x Others | 2 |
| data\validate | apache/fluss | Rust Build and Tests | 1 |
| data\validate | apache/gravitino | Frontend Integration Test | 1 |
| data\validate | apache/gravitino | Trino Integration Test | 1 |
| data\validate | apache/groovy | Generate SNAPSHOT distributions | 1 |
| data\validate | apache/groovy | Build and test for coverage | 1 |
| data\validate | apache/groovy | Generate SNAPSHOT artifacts | 1 |
| data\validate | apache/groovy | jmh | 1 |
| data\validate | apache/iceberg | Kafka Connect CI | 1 |
| data\validate | apache/iotdb | Table Cluster IT - 1C1D | 1 |
| data\validate | apache/paimon | End to End Tests Flink 1.x | 1 |
| data\validate | apache/paimon | Python Check Code Style and Test | 1 |
| data\validate | apache/paimon | UTCase and ITCase Flink 1.x Common | 1 |
| data\validate | apache/paimon | UTCase and ITCase Flink 1.x Others | 1 |
| data\validate | apache/paimon | CI | 1 |
| data\validate | apache/pinot | Pinot Quickstart Tests | 1 |
| data\validate | apache/polaris | CI/main Fix setup export failure status (#5155)  Propagate failed export reads through the existing setup failure counter so incomplete YAML is never printed as a successful export. Add coverage for top-level and nested read failures.  Fixes #5154 | 1 |
| data\validate | apache/polaris | CI/main Update dependency com.google.guava:guava to v33.7.1-jre (#5316) | 1 |
| data\validate | apache/polaris | CI/main Preserve setup principal-role properties (#5281) | 1 |
| data\validate | apache/polaris | CI/main Update dependency pyiceberg to v0.12.0 (#5429) | 1 |
| data\validate | apache/polaris | CI/main Update dependency software.amazon.awssdk:bom to v2.54.7 (#5417) | 1 |
| data\validate | apache/polaris | CI/main Update dependency jupyterlab to v4.6.4 (#5570) | 1 |
| data\validate | apache/polaris | CI/main Update github/codeql-action action to v4.38.1 (#5546) | 1 |
| data\validate | apache/polaris | CI/main Docs: Explain ENABLE_SUB_CATALOG_RBAC_FOR_FEDERATED_CATALOGS in Federation docs (#5548) | 1 |
| data\validate | apache/polaris | CI/main Update docker.io/openpolicyagent/opa Docker tag to v1.21.0 (#5602) | 1 |
| data\validate | apache/polaris | CI/main Add pagination support for policy API (#5557) | 1 |
| data\validate | apache/polaris | CI/main Site: Sync community page roster with ASF records (#5663) | 1 |
| data\validate | apache/polaris | CI/main Add Polaris Community Meeting 2026-09-17 (#5669) | 1 |
| data\validate | apache/polaris | Security | 1 |
| data\validate | apache/tika | main jdk17 build | 1 |
| data\crawl_pr | apache/paimon | UTCase and ITCase Spark 4.x | 1 |
| data\crawl_pr | apache/paimon | Check File Size | 1 |
| data\crawl_pr | apache/paimon | UTCase and ITCase Flink 1.x Common | 1 |

## Repo lỗi

- 17:56:45 [apache/pulsar] LỖI FileNotFoundError: [Errno 2] No such file or directory: 'data\\validate\\apache__pulsar\\jobs.jsonl'

## Thay đổi luật và giới hạn

- Sửa hai ký tự backspace thành `\b` trong luật test: `369 PASSED, 1 FAILED, 0 FLAKY` giờ khớp. Giữ nguyên ưu tiên compile → lint → infra mạnh → flaky → test → dependency → infra yếu.

- RAT license: `Counter(s) UNAPPROVED exceeded minimum or maximum values` → lint (Druid run 36682779402).

- Japicmp: `E: There is at least one incompatibility: ...` → lint (Pinot run 35823974157); log xác nhận kiểu trả về getCrc đổi String sang long. Không bắt dòng lệnh `--error-on-binary-incompatibility` làm evidence.

- Test Ant/shell: `Some tests completed with an Error` (Tomcat 31521893807), `4 tests, 3 passed, 1 failed` và `ERROR: Test execution of ozone/test.sh is FAILED` (Ozone 29421150227) → test. Loại ANSI trước khi match và xuất evidence để không mất chẩn đoán do màu console.

- Lỗi tải JDK/action: `Java setup process failed due to: error code: 504` và `Failed to resolve action download info` → infra (Druid 31828775776; Kafka 31103727160).

- JVM crash: `A fatal error has been detected by the Java Runtime Environment` → infra (Pinot 32173121221).

- Đọc mẫu phát hiện Kafka 29031051636 và 29317284895 có flaky nhưng nguyên nhân làm job fail là `Gradle task had a timeout. ... These are partial results!`. Thêm timeout này vào infra mạnh trước flaky; không dùng kết quả test chưa đầy đủ để kết luận flaky.

- Artifact đứng riêng / plugin không tồn tại: `Could not find artifact ...` và `No plugin found for prefix` → dependency khi không có dấu hiệu mạng (Druid 34426182770).

- Thêm dấu hiệu mạng `Premature end of Content-Length`, SSL handshake; tránh chuyển lỗi tải file bị cắt dở thành dependency chỉ vì một mirror khác báo missing artifact (Paimon 29811570144, 29811954183).

- Thêm mẫu compiler Scala/Kotlin, Gradle checkstyle/spotless, license header, revapi/japicmp compatibility; các mẫu chưa xuất hiện trong dữ liệu đang đọc chưa được xác nhận bằng log PR. Chỉ có tên task compile hoặc tên plugin compatibility chưa đủ để kết luận lỗi code.

- NON_BUILD_WF thêm benchmark, PR labels, dependency review, Dependency Submission (Pulsar push chỉ có CI - Gradle Dependency Submission, không xem là build pass). Cần kiểm tra lại theo workflow thực tế khi crawl mở rộng hoàn tất.

- Sửa evidence cuối file không có newline; gold_labels xuất được CSV rỗng. Công cụ review không tự đánh giá đúng/sai.

## Việc còn lại

- Chờ T1/T2 hoàn tất; pipeline sẽ tự chạy gán nhãn và tạo commits_all.parquet. Công cụ kết thúc sẽ cập nhật mẫu và báo cáo; mẫu mới cần đọc thủ công.

- Kiểm tra các workflow nhãn ?, sửa luật dựa vào log PR/extra, đọc đủ 20 mẫu/nhãn; nếu số lượng chưa đạt thì mở rộng repo JVM theo tài liệu nhiệm vụ.

- T5: người dùng trả lời "Chưa tạo lịch" ngày 2026-10-07. Không tạo Windows Task Scheduler.

## Theo dõi và tiếp tục

- Trạng thái pipeline: `data/crawl_expand_state.json`; PID: `data/crawl_expand.pid`. T1 ghi `data/crawl_pr.log`; T2 ghi `data/crawl_extra.log`; gán nhãn và báo cáo ghi `data/crawl_expand.log`.

- Pipeline chính T1 → T2 push → T2 PR → gold_labels → commits_all.parquet; worker phụ đã xong push và chuyển sang T2 PR. Khóa theo repo ngăn ghi trùng khi pipeline chính đến T2; có bước chờ worker phụ trước khi gán nhãn. `scripts/crawl_finish.ps1` chờ T4 xong rồi xuất mẫu mới và cập nhật báo cáo; các mẫu mới không được tự động tính là đã đọc.

- Nếu tiến trình bị ngắt, xác nhận tiến trình cũ đã dừng rồi chạy `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/crawl_expand.ps1`; crawler bỏ qua run/jobs/log đã lưu. Chạy thêm `scripts/crawl_finish.ps1` để cập nhật báo cáo sau khi xong.

- Dùng `scripts/crawl_control.ps1 -Action Status`, `-Action Pause` hoặc `-Action Resume` để quản lý các worker; checkpoint nằm tại `data/crawl_checkpoint.json`. Không tạm dừng lượt thật trong quá trình kiểm tra tính năng.

- 14 kiểm tra unittest đạt, gồm khóa giữa hai tiến trình, JSONL bị cắt và repo không có run fail/workflow; sửa lỗi đọc jobs.jsonl chưa tồn tại của Pulsar. Kiểm tra CSV root rỗng đạt; lấy mẫu hai lần cùng seed cho manifest/fingerprint giống nhau; các script PowerShell đã kiểm tra cú pháp. Resume đã chạy thật; chưa chủ động Pause.
