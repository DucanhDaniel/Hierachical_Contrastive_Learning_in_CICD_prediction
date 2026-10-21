# Báo cáo crawl mở rộng dữ liệu

Cập nhật 2026-10-08 03:05:29 +0700. Pipeline: `crawl-and-labels` / `completed`. Thời gian từ lúc khởi chạy: 5:42:03.831647.

Worker mở rộng song song: `T2-extra-pr` / `completed`; theo dõi `data/crawl_extra_push.log` hoặc `data/crawl_extra_pr.log`. Checkpoint/điều khiển: `docs/codex/crawl-control.md`.

Giám sát qua đêm: `waiting-for-current-workers` / `running`; `data/crawl_overnight_state.json` là trạng thái riêng, không đồng nghĩa đạt tiêu chí nhãn.

Số liệu commit đọc trực tiếp từ `data\processed\commits_all.parquet` (mtime: 2026-10-08T03:05:19.190536+07:00). Khi crawl còn chạy, đây là ảnh chụp tạm thời; chưa phải bộ dữ liệu hoàn tất.

## Repo × event

| repo | event | commit | fail | % fail | fail đầu | từ (UTC) | đến (UTC) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| apache/camel-quarkus | pull_request | 487 | 182 | 37.37 | 127 | 2026-07-09T21:26:19Z | 2026-10-07T15:46:21Z |
| apache/camel-quarkus | push | 98 | 31 | 31.63 | 23 | 2026-07-09T12:46:05Z | 2026-10-07T13:00:04Z |
| apache/druid | pull_request | 2180 | 763 | 35.0 | 514 | 2026-07-09T14:03:52Z | 2026-10-07T12:59:43Z |
| apache/druid | push | 634 | 183 | 28.86 | 113 | 2026-07-09T10:08:18Z | 2026-10-07T02:02:40Z |
| apache/fluss | pull_request | 1607 | 457 | 28.44 | 302 | 2026-07-10T02:35:56Z | 2026-10-07T17:02:40Z |
| apache/fluss | push | 274 | 41 | 14.96 | 33 | 2026-07-09T13:08:09Z | 2026-10-07T16:52:36Z |
| apache/gravitino | pull_request | 3283 | 744 | 22.66 | 517 | 2026-07-09T17:10:08Z | 2026-10-07T13:06:35Z |
| apache/gravitino | push | 505 | 47 | 9.31 | 40 | 2026-07-09T00:54:17Z | 2026-10-06T04:08:21Z |
| apache/groovy | pull_request | 662 | 140 | 21.15 | 107 | 2026-07-09T23:24:32Z | 2026-10-07T17:20:48Z |
| apache/groovy | push | 401 | 83 | 20.7 | 53 | 2026-07-10T20:51:49Z | 2026-10-07T05:14:34Z |
| apache/iceberg | pull_request | 3588 | 608 | 16.95 | 441 | 2026-07-09T16:55:06Z | 2026-10-07T15:25:27Z |
| apache/iceberg | push | 530 | 31 | 5.85 | 20 | 2026-07-09T00:38:08Z | 2026-10-06T20:16:12Z |
| apache/ignite | pull_request | 1268 | 145 | 11.44 | 67 | 2026-07-10T05:30:15Z | 2026-10-07T19:13:08Z |
| apache/ignite | push | 205 | 3 | 1.46 | 3 | 2026-07-09T14:04:32Z | 2026-10-07T13:28:25Z |
| apache/iotdb | pull_request | 1300 | 670 | 51.54 | 400 | 2026-07-09T15:05:21Z | 2026-10-07T18:57:08Z |
| apache/iotdb | push | 322 | 205 | 63.66 | 59 | 2026-07-09T10:27:38Z | 2026-10-06T14:13:15Z |
| apache/kafka | pull_request | 2153 | 725 | 33.67 | 473 | 2026-07-09T16:03:14Z | 2026-10-07T13:09:53Z |
| apache/kafka | push | 370 | 64 | 17.3 | 45 | 2026-07-09T06:20:40Z | 2026-10-06T19:14:29Z |
| apache/ozone | pull_request | 2276 | 842 | 36.99 | 487 | 2026-07-09T15:50:18Z | 2026-10-07T18:26:43Z |
| apache/ozone | push | 548 | 256 | 46.72 | 124 | 2026-07-09T19:15:16Z | 2026-10-07T11:23:35Z |
| apache/paimon | pull_request | 4433 | 1287 | 29.03 | 851 | 2026-07-09T08:27:16Z | 2026-10-07T13:11:40Z |
| apache/paimon | push | 1024 | 252 | 24.61 | 172 | 2026-07-09T04:02:25Z | 2026-10-07T03:11:08Z |
| apache/pinot | pull_request | 3424 | 829 | 24.21 | 444 | 2026-07-09T11:03:08Z | 2026-10-07T14:01:31Z |
| apache/pinot | push | 411 | 74 | 18.0 | 63 | 2026-07-09T00:00:39Z | 2026-10-07T01:35:54Z |
| apache/polaris | pull_request | 1750 | 381 | 21.77 | 199 | 2026-07-09T17:10:34Z | 2026-10-07T18:55:07Z |
| apache/polaris | push | 530 | 36 | 6.79 | 26 | 2026-07-09T12:10:32Z | 2026-10-07T18:03:01Z |
| apache/pulsar | pull_request | 1152 | 349 | 30.3 | 180 | 2026-07-09T19:11:52Z | 2026-10-07T16:32:12Z |
| apache/storm | pull_request | 370 | 39 | 10.54 | 27 | 2026-07-09T18:46:56Z | 2026-10-06T03:37:38Z |
| apache/storm | push | 177 | 10 | 5.65 | 8 | 2026-07-11T14:25:34Z | 2026-10-03T09:48:59Z |
| apache/tika | pull_request | 806 | 172 | 21.34 | 115 | 2026-07-09T20:58:43Z | 2026-10-07T18:26:56Z |
| apache/tika | push | 408 | 33 | 8.09 | 25 | 2026-07-09T11:08:00Z | 2026-10-07T18:13:36Z |
| apache/tomcat | pull_request | 98 | 43 | 43.88 | 30 | 2026-07-25T16:31:51Z | 2026-10-07T06:59:40Z |
| apache/tomcat | push | 382 | 85 | 22.25 | 26 | 2026-07-09T14:22:14Z | 2026-10-07T18:13:07Z |

## Nhãn commit fail

| cause | label_group | label | commit fail | % | fail đầu |
| --- | --- | --- | --- | --- | --- |
| ? | ? | ? | 4338 | 44.22 | 2619 |
| code | build | compile | 648 | 6.61 | 390 |
| code | build | dependency | 94 | 0.96 | 62 |
| code | build | lint | 539 | 5.49 | 313 |
| code | test | test | 3546 | 36.15 | 2261 |
| env | env | flaky | 2 | 0.02 | 2 |
| env | env | infra | 643 | 6.55 | 467 |

## Tiêu chí số lượng và coverage

| chỉ số | thực tế | mục tiêu | kết quả |
| --- | --- | --- | --- |
| Commit fail cause=code | 4827 | >= 2000 | đạt tại ảnh chụp |
| Commit fail test | 3546 | >= 300 | đạt tại ảnh chụp |
| Commit fail compile | 648 | >= 300 | đạt tại ảnh chụp |
| Commit fail lint | 539 | >= 300 | đạt tại ảnh chụp |
| Commit fail ? | 44.22% | < 5% | chưa đạt |
| Run fail không có log sử dụng được | 6686/19161 (34.89%) | < 5% | chưa đạt |

## Kiểm chứng mẫu thủ công

Phạm vi mẫu đã lưu: data\crawl_pr, data\validate. Các đánh giá thuộc đúng mẫu/fingerprint này; chưa phải kết quả kiểm chứng mẫu mới cho toàn bộ dữ liệu PR và repo mở rộng.

Seed `20261007`; mỗi nhãn tối đa 20 run riêng biệt. Kết quả chỉ được công nhận khi fingerprint đoạn log trùng với đánh giá đã lưu. `uncertain` không được tính là đúng. Đây là độ phù hợp với bằng chứng log giữ lại, chưa chứng minh nguyên nhân của mọi lần fail hoặc accuracy toàn quần thể.

| nhãn | mẫu / 20 | đúng | sai | chưa đủ bằng chứng | chưa đọc | % đúng trên mẫu | kết quả |
| --- | --- | --- | --- | --- | --- | --- | --- |
| compile | 20 | 0 | 0 | 0 | 20 | 0.0% | chưa đạt/chưa đủ |
| lint | 20 | 1 | 0 | 0 | 19 | 5.0% | chưa đạt/chưa đủ |
| dependency | 20 | 0 | 0 | 0 | 20 | 0.0% | chưa đạt/chưa đủ |
| test | 20 | 0 | 0 | 0 | 20 | 0.0% | chưa đạt/chưa đủ |
| infra | 20 | 0 | 0 | 0 | 20 | 0.0% | chưa đạt/chưa đủ |
| flaky | 2 | 2 | 0 | 0 | 0 | 100.0% | chưa đạt/chưa đủ |

Chưa có ví dụ sai/chưa đủ bằng chứng đã ghi nhận.

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
| data\validate | apache/iotdb | 368 | 16 | 0 | 15 | 0 | 4.35 |
| data\validate | apache/kafka | 64 | 2 | 0 | 0 | 0 | 3.12 |
| data\validate | apache/ozone | 256 | 10 | 0 | 6 | 1 | 3.91 |
| data\validate | apache/paimon | 364 | 0 | 0 | 0 | 0 | 0.0 |
| data\validate | apache/pinot | 81 | 2 | 0 | 1 | 0 | 2.47 |
| data\validate | apache/polaris | 37 | 4 | 0 | 1 | 0 | 10.81 |
| data\validate | apache/pulsar | 0 | 0 | 0 | 0 | 0 | 0.0 |
| data\validate | apache/storm | 10 | 0 | 0 | 0 | 0 | 0.0 |
| data\validate | apache/tika | 48 | 6 | 0 | 0 | 0 | 12.5 |
| data\validate | apache/tomcat | 97 | 0 | 0 | 0 | 0 | 0.0 |
| data\crawl_pr | apache/camel-quarkus | 242 | 85 | 0 | 2 | 11 | 35.12 |
| data\crawl_pr | apache/druid | 1215 | 55 | 0 | 3 | 410 | 4.53 |
| data\crawl_pr | apache/fluss | 708 | 135 | 0 | 1 | 91 | 19.07 |
| data\crawl_pr | apache/gravitino | 3467 | 2123 | 0 | 2 | 0 | 61.23 |
| data\crawl_pr | apache/groovy | 188 | 5 | 0 | 3 | 19 | 2.66 |
| data\crawl_pr | apache/iceberg | 949 | 949 | 217 | 0 | 0 | 100.0 |
| data\crawl_pr | apache/ignite | 145 | 106 | 0 | 1 | 0 | 73.1 |
| data\crawl_pr | apache/iotdb | 1889 | 513 | 0 | 73 | 294 | 27.16 |
| data\crawl_pr | apache/kafka | 1013 | 1013 | 1000 | 0 | 0 | 100.0 |
| data\crawl_pr | apache/ozone | 1348 | 772 | 0 | 2 | 58 | 57.27 |
| data\crawl_pr | apache/paimon | 3125 | 23 | 0 | 8 | 180 | 0.74 |
| data\crawl_pr | apache/pinot | 1576 | 254 | 0 | 6 | 163 | 16.12 |
| data\crawl_pr | apache/polaris | 436 | 103 | 0 | 0 | 68 | 23.62 |
| data\crawl_pr | apache/pulsar | 645 | 252 | 0 | 0 | 9 | 39.07 |
| data\crawl_pr | apache/storm | 41 | 14 | 0 | 0 | 0 | 34.15 |
| data\crawl_pr | apache/tika | 262 | 140 | 0 | 0 | 18 | 53.44 |
| data\crawl_pr | apache/tomcat | 100 | 87 | 0 | 0 | 0 | 87.0 |

## Nhãn ? theo repo và workflow

| root | repo | workflow | run ? |
| --- | --- | --- | --- |
| data\crawl_pr | apache/druid | Static Checks CI | 297 |
| data\crawl_pr | apache/druid | Unit & Integration tests CI | 174 |
| data\crawl_pr | apache/ozone | pull request | 167 |
| data\crawl_pr | apache/ozone | build-branch | 148 |
| data\validate | apache/iotdb | Sonar-Codecov | 146 |
| data\crawl_pr | apache/pinot | Pinot Integration Tests | 105 |
| data\crawl_pr | apache/pulsar | Pulsar CI | 103 |
| data\crawl_pr | apache/pulsar | Pulsar CI Flaky | 101 |
| data\crawl_pr | apache/camel-quarkus | Camel Quarkus CI | 84 |
| data\crawl_pr | apache/iotdb | Sonar-Codecov | 83 |
| data\crawl_pr | apache/druid | PR Commit Checks | 80 |
| data\crawl_pr | apache/iotdb | Cluster IT - 1C1D1A | 79 |
| data\crawl_pr | apache/druid | Cron Job ITs | 76 |
| data\validate | apache/ozone | build-branch | 75 |
| data\crawl_pr | apache/pinot | Pinot Compatibility Checks | 65 |
| data\crawl_pr | apache/iotdb | Table Cluster IT - 1C3D | 57 |
| data\crawl_pr | apache/gravitino | build | 52 |
| data\crawl_pr | apache/fluss | Rust License and Formatting Check | 36 |
| data\crawl_pr | apache/gravitino | Trino Integration Test | 36 |
| data\crawl_pr | apache/pulsar | Semantic Pull Request | 36 |
| data\crawl_pr | apache/fluss | Client Integration | 35 |
| data\crawl_pr | apache/gravitino | Python Client Integration Test | 35 |
| data\validate | apache/tomcat | Smoke Test - MacOS | 29 |
| data\crawl_pr | apache/gravitino | Backend Integration Test | 28 |
| data\crawl_pr | apache/iotdb | Cluster IT - 1C3D | 28 |
| data\crawl_pr | apache/fluss | Rust Build and Tests | 27 |
| data\crawl_pr | apache/fluss | CI | 26 |
| data\validate | apache/iotdb | Cluster IT - 1C1D1A | 21 |
| data\crawl_pr | apache/paimon | Python Check Code Style and Test | 21 |
| data\validate | apache/camel-quarkus | Camel Quarkus CI | 20 |
| data\validate | apache/pinot | Pinot Integration Tests | 17 |
| data\crawl_pr | apache/gravitino | Frontend Integration Test | 17 |
| data\validate | apache/druid | Unit & Integration tests CI | 16 |
| data\crawl_pr | apache/iotdb | Multi-Cluster IT | 16 |
| data\crawl_pr | apache/groovy | Lint gate | 15 |
| data\crawl_pr | apache/storm | Java CI with Maven | 14 |
| data\crawl_pr | apache/polaris | PR#5175 Update tcort/github-action-markdown-link-check action to v1.1.3 | 13 |
| data\crawl_pr | apache/iotdb | Cluster IT - 1C1D | 12 |
| data\crawl_pr | apache/tika | main jdk17 build | 12 |
| data\validate | apache/iotdb | Table Cluster IT - 1C3D | 11 |
| data\crawl_pr | apache/fluss | Gateway CI | 11 |
| data\crawl_pr | apache/groovy | Generate SNAPSHOT artifacts | 11 |
| data\crawl_pr | apache/iotdb | Table Cluster IT - 1C1D | 11 |
| data\crawl_pr | apache/pinot | Pinot Unit Tests | 11 |
| data\validate | apache/groovy | Build and test | 10 |
| data\validate | apache/tomcat | Validate code | 10 |
| data\crawl_pr | apache/groovy | Generate SNAPSHOT distributions | 10 |
| data\crawl_pr | apache/ignite | SonarBuild | 10 |
| data\crawl_pr | apache/polaris | Security | 10 |
| data\crawl_pr | apache/camel-quarkus | Validate PR Style | 9 |
| data\crawl_pr | apache/fluss | Check License | 9 |
| data\crawl_pr | apache/polaris | PR#2678 Update docker.io/apache/spark Docker tag to v3.5.9 | 9 |
| data\validate | apache/tomcat | Smoke Test | 8 |
| data\crawl_pr | apache/gravitino | Conflict Marker Check | 8 |
| data\crawl_pr | apache/gravitino | Maintenance Integration Test | 8 |
| data\crawl_pr | apache/gravitino | Spark Integration Test | 8 |
| data\crawl_pr | apache/groovy | Check licenses | 8 |
| data\crawl_pr | apache/iotdb | Dependency Check | 8 |
| data\crawl_pr | apache/pinot | Pinot Quickstart Tests | 8 |
| data\validate | apache/pinot | Pinot Compatibility Checks | 7 |
| data\crawl_pr | apache/gravitino | Access Control Integration Test | 7 |
| data\crawl_pr | apache/gravitino | Iceberg REST Trino Integration Test | 7 |
| data\crawl_pr | apache/gravitino | mcp-integration-test | 7 |
| data\crawl_pr | apache/groovy | Build and test | 7 |
| data\crawl_pr | apache/paimon | CI | 7 |
| data\validate | apache/gravitino | Backend Integration Test | 6 |
| data\crawl_pr | apache/gravitino | Flink Integration Test | 6 |
| data\crawl_pr | apache/groovy | Performance check | 6 |
| data\crawl_pr | apache/iotdb | Check TODOs and FIXMEs in Changed Files | 6 |
| data\validate | apache/druid | Static Checks CI | 5 |
| data\validate | apache/iotdb | Cluster IT - 1C3D | 5 |
| data\validate | apache/kafka | CI | 5 |
| data\crawl_pr | apache/gravitino | IdP Basic Test | 5 |
| data\crawl_pr | apache/iotdb | Unit-Test | 5 |
| data\crawl_pr | apache/paimon | UTCase and ITCase Spark 3.x | 5 |
| data\crawl_pr | apache/pinot | Pinot Java 11 Client Compatibility | 5 |
| data\crawl_pr | apache/polaris | PR#2392 Update plugin openapi-generator to v7.25.0 | 5 |
| data\crawl_pr | apache/polaris | PR#5360 [DRAFT] Adapt Polaris to Iceberg 1.12 | 5 |
| data\validate | apache/groovy | Performance check | 4 |
| data\validate | apache/tika | main jdk21 build | 4 |
| data\crawl_pr | apache/polaris | PR#2392 Update plugin openapi-generator to v7.24.0 | 4 |
| data\crawl_pr | apache/polaris | PR#5162 Add decrypt only access for legacy AWS KMS keys | 4 |
| data\crawl_pr | apache/polaris | PR#5328 Cache table metadata by metadata file location | 4 |
| data\crawl_pr | apache/polaris | PR#5350 Spark 4: add bundle regression tests (#4664) | 4 |
| data\crawl_pr | apache/tika | branch_3x jdk11 build | 4 |
| data\crawl_pr | apache/tomcat | Smoke Test - MacOS | 4 |
| data\validate | apache/fluss | Client Integration | 3 |
| data\validate | apache/gravitino | build | 3 |
| data\validate | apache/storm | Java CI with Maven | 3 |
| data\validate | apache/tika | main jdk17 windows build (de_DE) | 3 |
| data\validate | apache/tika | main jdk25 build | 3 |
| data\crawl_pr | apache/gravitino | Test Charts | 3 |
| data\crawl_pr | apache/paimon | UTCase and ITCase Others | 3 |
| data\crawl_pr | apache/paimon | End to End Tests Flink 2.x on JDK 11 | 3 |
| data\crawl_pr | apache/storm | Cypress E2E Tests | 3 |
| data\validate | apache/ignite | Sonar Quality Branch Analysis | 2 |
| data\validate | apache/iotdb | Multi-Cluster IT | 2 |
| data\validate | apache/tika | Docker snapshot - tika-server and tika-grpc | 2 |
| data\crawl_pr | apache/gravitino | Web UI Tests | 2 |
| data\crawl_pr | apache/groovy | jmh-classic | 2 |
| data\crawl_pr | apache/groovy | Native Image Metadata Check | 2 |
| data\crawl_pr | apache/iotdb | Multi-Language Client | 2 |
| data\crawl_pr | apache/iotdb | Edge IT | 2 |
| data\crawl_pr | apache/paimon | Check licensing | 2 |
| data\crawl_pr | apache/paimon | End to End Tests Flink 1.x | 2 |
| data\crawl_pr | apache/paimon | UTCase and ITCase Flink 2.x on JDK 11 | 2 |
| data\crawl_pr | apache/paimon | UTCase and ITCase Flink 1.x Others | 2 |
| data\crawl_pr | apache/polaris | PR#4644 Update dependency software.amazon.awssdk:bom to v2.48.1 | 2 |
| data\crawl_pr | apache/polaris | PR#4644 Update dependency software.amazon.awssdk:bom to v2.48.3 | 2 |
| data\crawl_pr | apache/polaris | PR#5122 Follow-up polish to the `createTable`/`updateTable` idempotency work. | 2 |
| data\crawl_pr | apache/polaris | PR#4644 Update dependency software.amazon.awssdk:bom to v2.49.2 | 2 |
| data\crawl_pr | apache/polaris | PR#4831 Entity-level filtering: API and feature flag | 2 |
| data\crawl_pr | apache/polaris | PR#4667 OpenLineage: add no-op POST /api/v1/lineage ingest endpoint | 2 |
| data\crawl_pr | apache/polaris | PR#5398 Bound async file-cleanup deletions with a configurable timeout | 2 |
| data\crawl_pr | apache/polaris | PR#5452 Update dependency com.google.cloud:google-cloud-iamcredentials to v2.97.0 | 2 |
| data\crawl_pr | apache/polaris | PR#4831 Draft: Entity-level filtering Part 1 | 2 |
| data\crawl_pr | apache/polaris | PR#5592 Update runtime distributions LICENSE with dependencies shaded in artifacts | 2 |
| data\crawl_pr | apache/polaris | PR#5469 Polaris Tag Management: tag assignment write path | 2 |
| data\crawl_pr | apache/polaris | PR#4613 Add Directories feature for managing objects (including unstructured data) on object stores | 2 |
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
| data\crawl_pr | apache/camel-quarkus | PR doc validation | 1 |
| data\crawl_pr | apache/fluss | DevKit Smoke | 1 |
| data\crawl_pr | apache/fluss | Helm Chart | 1 |
| data\crawl_pr | apache/groovy | jmh | 1 |
| data\crawl_pr | apache/iotdb | ZH-Locale-Compile | 1 |
| data\crawl_pr | apache/paimon | UTCase and ITCase Spark 4.x | 1 |
| data\crawl_pr | apache/paimon | Check File Size | 1 |
| data\crawl_pr | apache/paimon | UTCase and ITCase Flink 1.x Common | 1 |
| data\crawl_pr | apache/polaris | PR#2392 Update plugin openapi-generator to v7.23.0 | 1 |
| data\crawl_pr | apache/polaris | PR#4644 Update dependency software.amazon.awssdk:bom to v2.48.0 | 1 |
| data\crawl_pr | apache/polaris | PR#4606 Service: Make default table/view locations unique | 1 |
| data\crawl_pr | apache/polaris | PR#5058 WIP Floci testcontainers  - commit stack | 1 |
| data\crawl_pr | apache/polaris | PR#4644 Update dependency software.amazon.awssdk:bom to v2.47.6 | 1 |
| data\crawl_pr | apache/polaris | PR#4939 Support staged table creates in commitTransaction | 1 |
| data\crawl_pr | apache/polaris | PR#4644 Update dependency software.amazon.awssdk:bom to v2.47.5 | 1 |
| data\crawl_pr | apache/polaris | PR#5004 Propagate storage HTTP client settings to S3FileIO for table operations | 1 |
| data\crawl_pr | apache/polaris | PR#4912 Implement entity-property idempotency for createTable | 1 |
| data\crawl_pr | apache/polaris | PR#4644 Update dependency software.amazon.awssdk:bom to v2.47.4 | 1 |
| data\crawl_pr | apache/polaris | PR#5032 Include user-defined attributes when building PolarisPrincipal from PrincipalEntity | 1 |
| data\crawl_pr | apache/polaris | PR#2678 Update docker.io/apache/spark Docker tag to v3.5.8 | 1 |
| data\crawl_pr | apache/polaris | PR#4644 Update dependency software.amazon.awssdk:bom to v2.49.0 | 1 |
| data\crawl_pr | apache/polaris | PR#4644 Update dependency software.amazon.awssdk:bom to v2.48.4 | 1 |
| data\crawl_pr | apache/polaris | PR#5084 feat(events): add webhook event listener with HMAC signing and retry | 1 |
| data\crawl_pr | apache/polaris | PR#5112 Clarify principal role selection semantics | 1 |
| data\crawl_pr | apache/polaris | PR#4644 Update dependency software.amazon.awssdk:bom to v2.49.6 | 1 |
| data\crawl_pr | apache/polaris | PR#5187 Update dependency org.jspecify:jspecify to v1.0.1 | 1 |
| data\crawl_pr | apache/polaris | PR#5183 Update dependency io.quarkus.platform:quarkus-bom to v3.38.0 | 1 |
| data\crawl_pr | apache/polaris | PR#4644 Update dependency software.amazon.awssdk:bom to v2.49.5 | 1 |
| data\crawl_pr | apache/polaris | PR#4644 Update dependency software.amazon.awssdk:bom to v2.49.4 | 1 |
| data\crawl_pr | apache/polaris | PR#5168 Update dependency com.diffplug.spotless:spotless-plugin-gradle to v8.9.0 | 1 |
| data\crawl_pr | apache/polaris | PR#5155 Fix setup export failure status | 1 |
| data\crawl_pr | apache/polaris | PR#4644 Update dependency software.amazon.awssdk:bom to v2.49.3 | 1 |
| data\crawl_pr | apache/polaris | PR#5141 [DRAFT] Switch event attributes to AttributeMap | 1 |
| data\crawl_pr | apache/polaris | PR#4644 Update dependency software.amazon.awssdk:bom to v2.49.1 | 1 |
| data\crawl_pr | apache/polaris | PR#5243 Update ranger to v2.9.0 | 1 |
| data\crawl_pr | apache/polaris | PR#5129 fix(cache): add configurable refresh buffer to StorageCredentialCache | 1 |
| data\crawl_pr | apache/polaris | PR#4644 Update dependency software.amazon.awssdk:bom to v2.50.2 | 1 |
| data\crawl_pr | apache/polaris | PR#5209 Update dependency org.apache.httpcomponents.client5:httpclient5 to v5.6.3 | 1 |
| data\crawl_pr | apache/polaris | PR#4644 Update dependency software.amazon.awssdk:bom to v2.50.1 | 1 |
| data\crawl_pr | apache/polaris | PR#4644 Update dependency software.amazon.awssdk:bom to v2.50.0 | 1 |
| data\crawl_pr | apache/polaris | PR#5284 Update github/codeql-action action to v4.37.7 | 1 |
| data\crawl_pr | apache/polaris | PR#5283 Fix typos and grammar issues in the documentation | 1 |
| data\crawl_pr | apache/polaris | PR#4644 Update dependency software.amazon.awssdk:bom to v2.52.1 | 1 |
| data\crawl_pr | apache/polaris | PR#5281 Preserve setup principal-role properties | 1 |
| data\crawl_pr | apache/polaris | PR#3581 Update dependency org.apache.hive:hive-exec to v4 | 1 |
| data\crawl_pr | apache/polaris | PR#5263 Avoid deleting table metadata on ambiguous commit failures | 1 |
| data\crawl_pr | apache/polaris | PR#5029 fix(jdbc): skip slash-only prefixes in optimized overlap queries | 1 |
| data\crawl_pr | apache/polaris | PR#5289 Fix: CLI's "--debug" mode leaks credentials to stderr (sanitizer misses camelCase keys on the wire) | 1 |
| data\crawl_pr | apache/polaris | PR#5382 Re-enable cloud storage ViewCatalogTests | 1 |
| data\crawl_pr | apache/polaris | PR#5370 Hide `PolarisAuthorizer` error details in `ForbiddenException` message | 1 |
| data\crawl_pr | apache/polaris | PR#5306 fix(jdbc): key the policy mapping delete on the identity columns | 1 |
| data\crawl_pr | apache/polaris | PR#5428 Update docker.io/floci/floci Docker tag to v2 | 1 |
| data\crawl_pr | apache/polaris | PR#5427 Update docker.io/floci/floci-gcp Docker tag to v0.8.0 | 1 |
| data\crawl_pr | apache/polaris | PR#5426 Update docker.io/floci/floci-az Docker tag to v0.12.0 | 1 |
| data\crawl_pr | apache/polaris | PR#5424 Fix #5401: Polaris crash-loops on local Kubernetes: the OTel GCP resou | 1 |
| data\crawl_pr | apache/polaris | PR#5412 CLI: add storage-name support | 1 |
| data\crawl_pr | apache/polaris | PR#5411 Hugo site: fix github-polaris shortcode | 1 |
| data\crawl_pr | apache/polaris | PR#5463 Update dependency com.google.cloud:google-cloud-iamcredentials to v2.97.0 | 1 |
| data\crawl_pr | apache/polaris | PR#5458  Reconcile ambiguous JDBC writes during Iceberg metadata commits  | 1 |
| data\crawl_pr | apache/polaris | PR#5201 Update dependency com.google.cloud:google-cloud-storage-bom to v2.72.0 | 1 |
| data\crawl_pr | apache/polaris | PR#5446 Add the Polaris Shares API OpenAPI specification (beta, draft) | 1 |
| data\crawl_pr | apache/polaris | PR#5246 Fix /v1/config disclosing catalog properties without CATALOG_READ_PROPERTIES | 1 |
| data\crawl_pr | apache/polaris | PR#5135 Replace CEL-based NoSQL maintenance retention with commit count configuration | 1 |
| data\crawl_pr | apache/polaris | PR#4115 (feat) Implement metrics rest api | 1 |
| data\crawl_pr | apache/polaris | PR#5606 Update dependency com.google.cloud:google-cloud-iamcredentials to v2.98.0 | 1 |
| data\crawl_pr | apache/polaris | PR#5598 Support cross-account KMS keys in credential policies | 1 |
| data\crawl_pr | apache/polaris | PR#5119 Support for external principals | 1 |
| data\crawl_pr | apache/polaris | PR#5580 Update registry.access.redhat.com/ubi9/openjdk-21-runtime Docker tag to v1.24-3.1789566892 | 1 |
| data\crawl_pr | apache/polaris | PR#5577 CLI: Add register support for tables/views commands | 1 |
| data\crawl_pr | apache/polaris | PR#5575 Support non-numeric OIDC principal ID claims in the default principal mapper | 1 |
| data\crawl_pr | apache/polaris | PR#5566 Make distributed cache-invalidation peer discovery replaceable | 1 |
| data\crawl_pr | apache/polaris | PR#5665 Disable unused MongoDB readiness check | 1 |
| data\crawl_pr | apache/polaris | PR#5647 fix: seed purge FileIO context from catalog table-defaults | 1 |
| data\crawl_pr | apache/polaris | PR#5622 Persistence: Add DynamoDB backend module skeleton | 1 |
| data\crawl_pr | apache/polaris | PR#5603 Update Gradle to v9.8.0 | 1 |
| data\crawl_pr | apache/polaris | PR#2392 Update plugin openapi-generator to v7.26.0 | 1 |
| data\crawl_pr | apache/polaris | PR#5722 Persistence: objective javadoc for the dynamodb-atomic module | 1 |
| data\crawl_pr | apache/polaris | PR#5690 Fix renovate config | 1 |
| data\crawl_pr | apache/polaris | PR#5682 Overhaul Keycloak getting-started guides with more realistic setups | 1 |
| data\crawl_pr | apache/polaris | PR#5675 Update dependency mypy to >=2.4, <=2.4.0 | 1 |
| data\crawl_pr | apache/polaris | PR#5657 fix: delete connection secrets when an external catalog is deleted | 1 |
| data\crawl_pr | apache/polaris | PR#5659 Add TABLE_READ_METRICS privilege for metrics RBAC | 1 |
| data\crawl_pr | apache/polaris | PR#5733 Docs: Clarify which changes need changelog entries | 1 |
| data\crawl_pr | apache/polaris | PR#5515 Bound the catalog-role count taken when dropping a catalog | 1 |
| data\crawl_pr | apache/polaris | PR#5704 Stop the H2 init script from overwriting the recorded schema version | 1 |
| data\crawl_pr | apache/polaris | PR#5732 Fix Ranger authorizer NoClassDefFoundError for javax.ws.rs.core.Cookie | 1 |
| data\crawl_pr | apache/pulsar | CI - Go Functions | 1 |
| data\crawl_pr | apache/pulsar | CI - Python Functions | 1 |
| data\crawl_pr | apache/tika | no split packages | 1 |
| data\crawl_pr | apache/tomcat | Manager2 Test | 1 |
| data\crawl_pr | apache/tomcat | Smoke Test | 1 |
| data\crawl_pr | apache/tomcat | Validate code | 1 |

## Repo lỗi

- 22:42:00 [apache/kafka] LỖI HTTPError: 500 Server Error: Internal Server Error for url: https://api.github.com/repos/apache/kafka/actions/runs/29431255482/jobs?per_page=100&filter=latest
- 23:35:34 [apache/iceberg] LỖI HTTPError: 502 Server Error: Bad Gateway for url: https://api.github.com/repos/apache/iceberg/actions/runs/30012759023/jobs?per_page=100&filter=latest
- 17:56:45 [apache/pulsar] LỖI FileNotFoundError: [Errno 2] No such file or directory: 'data\\validate\\apache__pulsar\\jobs.jsonl'
- 21:37:20 [apache/ozone] LỖI HTTPError: 502 Server Error: Bad Gateway for url: https://api.github.com/repos/apache/ozone/actions/runs/31613065509/jobs?per_page=100&filter=latest
- 23:33:14 [apache/camel-quarkus] LỖI HTTPError: 502 Server Error: Bad Gateway for url: https://api.github.com/repos/apache/camel-quarkus/actions/workflows/22092/runs?page=1&status=completed&created=2026-09-10T17%3A00%3A00Z..2026-09-17T16%3A59%3A59Z&per_page=100&event=pull_request
- 00:08:12 [apache/ignite] LỖI HTTPError: 502 Server Error: Bad Gateway for url: https://api.github.com/repos/apache/ignite/actions/workflows/108385154/runs?page=2&status=completed&created=2026-08-06T18%3A00%3A00Z..2026-08-13T17%3A59%3A59Z&per_page=100&event=pull_request

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

Giám sát qua đêm bổ sung retry HTTP 500/502/503/504, chọn repo thiếu jobs/log, giữ backup marker missing khi thử lại một lần; 17 kiểm tra unittest đạt. Sau tối đa 3 lượt bổ sung sẽ cập nhật dataset/báo cáo, vẫn để kết quả kiểm chứng mẫu mới là pending cho đến khi đọc thủ công.
