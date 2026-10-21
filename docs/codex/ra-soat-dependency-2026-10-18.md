# Rà soát dependency — 18/10/2026

**Trạng thái: đề xuất chờ người duyệt; chưa tích hợp quy tắc và chưa relabel/export dataset.**

Phạm vi cố định: 94,293 run; phiên bản `2026-10-15-buildconfig-doc`. Seed `20261018`. Bộ chạy chỉ ghi vào `data\rule_eval\dependency-eval-20261018-v6`. Manifest và danh sách log nằm trong thư mục này.

## Cách đo

Ba cấu hình: bộ hiện hành (0), hiện hành + Q3 (1), bộ đề xuất đầy đủ (2). Bộ truy vết được so cả nhãn và bằng chứng với `gold_label` gốc trên từng run có log. Job fail tổng hợp được loại như bộ hiện hành. Không ghép nguyên nhân giữa các job. Các nhận định Codex là ghi chú rà soát; không phải nhãn người hay precision kiểm chứng.

Thời gian chạy: 679.8 giây. Sai khác truy vết so bộ gốc: **0**. Run có tín hiệu Q3 ở job khác job quyết định: **2**, được giữ nguyên nhãn.

## Phân bố nhãn và chuyển nhãn

| Nhãn | Hiện hành | Chỉ Q3 | Đầy đủ |
|---|---:|---:|---:|
| (không có log) | 29937 | 29937 | 29937 |
| ? | 19630 | 19521 | 18964 |
| buildconfig | 266 | 266 | 266 |
| compile | 8116 | 8028 | 8028 |
| dependency | 1627 | 1830 | 2270 |
| flaky | 65 | 65 | 65 |
| infra | 5090 | 5090 | 5285 |
| lint | 8301 | 8301 | 8223 |
| test | 19483 | 19477 | 19477 |

Run chậm nhất: `kroxylicious/kroxylicious` / `34576154796` — **12.65 giây** (gồm đọc log, phân loại và đối chiếu với hàm gốc; không phải thời gian riêng của một regex). Danh sách 20 run chậm nằm trong `summary.json`.

Trong các run mới từ ? sang infra, subtype hiện hành ánh xạ 185 run vào network và để trống 13 run. Không tự gán lá network bằng trường leaf_proposed.

Mẫu số `?` sau khử trùng là **19.630 run duy nhất**, khác 19.632 dòng ban đầu: hai run apache/ozone `29313822431` và `29246957748` mỗi run xuất hiện hai lần trong CSV/jobs. Chi tiết ở `scope_dedup_note.json`; không phải hai run đã được quy tắc mới giải quyết.

Thống kê tín hiệu dưới đây dùng `SIGNALS` trong bộ chạy (một số mẫu chặt hơn hoặc bổ sung so với script thống kê ban đầu), không xem số hợp các tín hiệu là bản sao y hệt mẫu rộng ban đầu.

| Tín hiệu | ? | dependency | infra |
|---|---:|---:|---:|
| resolve_summary | 388 | 1066 | 814 |
| artifact_descriptor | 144 | 4 | 228 |
| transfer | 313 | 9 | 830 |
| enforcer | 227 | 107 | 31 |
| jdk_version | 15 | 0 | 1 |
| gradle_conflict | 76 | 0 | 1 |
| plugin_resolve | 260 | 87 | 107 |
| lockfile | 99 | 197 | 1 |
| runtime_linkage | 125 | 0 | 27 |
| status_401_403 | 187 | 9 | 300 |
| js_deps | 144 | 204 | 1 |

Nhóm infra: mẫu rộng có 300 run chứa mã hoặc chữ Unauthorized/Forbidden; regex mã HTTP 401/403 tường minh chỉ khớp **285** run, 15 run còn lại chỉ khớp chữ. `Forbidden method invocation` là ví dụ không phải HTTP. Đây là tín hiệu xuất hiện trong log, chưa phải kết luận mã đó gây fail. Xem `http_status_stats.json`.

| So sánh | Cũ → mới | Run |
|---|---|---:|
| baseline_to_full | ? → infra | 198 |
| q3_to_full | ? → infra | 198 |
| baseline_to_full | ? → dependency | 468 |
| q3_to_full | ? → dependency | 359 |
| baseline_to_q3 | ? → dependency | 109 |
| baseline_to_full | lint → dependency | 78 |
| q3_to_full | lint → dependency | 78 |
| baseline_to_full | infra → dependency | 3 |
| q3_to_full | infra → dependency | 3 |
| baseline_to_q3 | compile → dependency | 88 |
| baseline_to_full | compile → dependency | 88 |
| baseline_to_q3 | test → dependency | 6 |
| baseline_to_full | test → dependency | 6 |

### Ví dụ Q3: compile → dependency (10 ví dụ có trong phạm vi)

| Repo | Run ID | Bằng chứng mới | Log |
|---|---|---|---|
| apache/fluss | 31725881760 | class file has wrong version 61.0, should be 55.0 | data/crawl_pr/apache__fluss/logs/98788906865.txt |
| apache/fluss | 31725881939 | class file has wrong version 61.0, should be 52.0 | data/crawl_pr/apache__fluss/logs/98788908124.txt; data/crawl_pr/apache__fluss/logs/98788908404.txt |
| apache/fory | 31572770024 | class file has wrong version 61.0, should be 55.0 | data/crawl_pr/apache__fory/logs/94038131932.txt |
| apache/gravitino | 36886350776 | java.lang.UnsupportedClassVersionError: com/google/errorprone/ErrorProneJavacPlugin has been compiled by a more recent version of the Java Runtime (class file version 65.0), this v | data/crawl_pr/apache__gravitino/logs/110454485216.txt |
| apache/gravitino | 36886350804 | java.lang.UnsupportedClassVersionError: com/google/errorprone/ErrorProneJavacPlugin has been compiled by a more recent version of the Java Runtime (class file version 65.0), this v | data/crawl_pr/apache__gravitino/logs/110454209721.txt |
| apache/gravitino | 36886350816 | java.lang.UnsupportedClassVersionError: com/google/errorprone/ErrorProneJavacPlugin has been compiled by a more recent version of the Java Runtime (class file version 65.0), this v | data/crawl_pr/apache__gravitino/logs/110451048821.txt |
| apache/gravitino | 36886352199 | java.lang.UnsupportedClassVersionError: com/google/errorprone/ErrorProneJavacPlugin has been compiled by a more recent version of the Java Runtime (class file version 65.0), this v | data/crawl_pr/apache__gravitino/logs/110454337425.txt |
| apache/gravitino | 36886352328 | java.lang.UnsupportedClassVersionError: com/google/errorprone/ErrorProneJavacPlugin has been compiled by a more recent version of the Java Runtime (class file version 65.0), this v | data/crawl_pr/apache__gravitino/logs/110451075799.txt |
| apache/gravitino | 36886352414 | java.lang.UnsupportedClassVersionError: com/google/errorprone/ErrorProneJavacPlugin has been compiled by a more recent version of the Java Runtime (class file version 65.0), this v | data/crawl_pr/apache__gravitino/logs/110454416185.txt |
| apache/gravitino | 36886352544 | java.lang.UnsupportedClassVersionError: com/google/errorprone/ErrorProneJavacPlugin has been compiled by a more recent version of the Java Runtime (class file version 65.0), this v | data/crawl_pr/apache__gravitino/logs/110451109570.txt |

### Ví dụ Q3: test → dependency (6 ví dụ có trong phạm vi)

| Repo | Run ID | Bằng chứng mới | Log |
|---|---|---|---|
| apache/gravitino | 34928884095 | Caused by: java.lang.NoClassDefFoundError: org/apache/spark/sql/AnalysisException | data/crawl_pr/apache__gravitino/logs/104252811645.txt |
| apache/paimon | 33646342430 | [ERROR]   Run 1: org/apache/fluss/testutils/common/TestLoggerExtension has been compiled by a more recent version of the Java Runtime (class file version 55.0), this version of the | data/crawl_pr/apache__paimon/logs/100301928129.txt |
| apache/polaris | 36012121854 | Caused by: java.lang.NoClassDefFoundError: io/quarkiverse/amazon/common/runtime/AmazonClientApache5TransportRecorder | data/crawl_pr/apache__polaris/logs/107675206845.txt; data/crawl_pr/apache__polaris/logs/107683077714.txt |
| open-telemetry/opentelemetry-java-instrumentation | 31363430363 | > org/springframework/ai/chat/model/ChatModel has been compiled by a more recent version of the Java Runtime (class file version 61.0), this version of the Java Runtime only recogn | data/crawl_pr/open-telemetry__opentelemetry-java-instrumentation/logs/93376775240.txt; data/crawl_pr/open-telemetry__opentelemetry-java-instrumentation/logs/93376776029.txt |
| open-telemetry/opentelemetry-java-instrumentation | 32742929143 | java.lang.UnsupportedClassVersionError: io/opentelemetry/javaagent/instrumentation/opensearch/v3_0/OpenSearchServerAddress has been compiled by a more recent version of the Java Ru | data/crawl_pr/open-telemetry__opentelemetry-java-instrumentation/logs/97505522813.txt; data/crawl_pr/open-telemetry__opentelemetry-java-instrumentation/logs/97505522858.txt |
| open-telemetry/opentelemetry-java-instrumentation | 32863113516 | java.lang.UnsupportedClassVersionError: io/opentelemetry/javaagent/instrumentation/opensearch/v3_0/OpenSearchConfiguredHost has been compiled by a more recent version of the Java R | data/crawl_pr/open-telemetry__opentelemetry-java-instrumentation/logs/97879112886.txt; data/crawl_pr/open-telemetry__opentelemetry-java-instrumentation/logs/97879123783.txt |

### Ví dụ Q3: ? → dependency (10 ví dụ có trong phạm vi)

| Repo | Run ID | Bằng chứng mới | Log |
|---|---|---|---|
| GetStream/stream-chat-android | 31006874847 | > Dependency requires at least JVM runtime version 21. This build uses a Java 17 JVM. | data/crawl_pr/GetStream__stream-chat-android/logs/92312182571.txt |
| GoogleCloudPlatform/DataflowTemplates | 36896489598 | Caused by: java.lang.UnsupportedClassVersionError: com/puppycrawl/tools/checkstyle/api/CheckstyleException has been compiled by a more recent version of the Java Runtime (class fil | data/crawl_pr/GoogleCloudPlatform__DataflowTemplates/logs/110484660644.txt; data/crawl_pr/GoogleCloudPlatform__DataflowTemplates/logs/110484660896.txt |
| GoogleCloudPlatform/DataflowTemplates | 36896489675 | Caused by: java.lang.UnsupportedClassVersionError: com/puppycrawl/tools/checkstyle/api/CheckstyleException has been compiled by a more recent version of the Java Runtime (class fil | data/crawl_pr/GoogleCloudPlatform__DataflowTemplates/logs/110484660747.txt; data/crawl_pr/GoogleCloudPlatform__DataflowTemplates/logs/110484661046.txt |
| GoogleCloudPlatform/DataflowTemplates | 36896489677 | Caused by: java.lang.UnsupportedClassVersionError: com/puppycrawl/tools/checkstyle/api/CheckstyleException has been compiled by a more recent version of the Java Runtime (class fil | data/crawl_pr/GoogleCloudPlatform__DataflowTemplates/logs/110484660565.txt; data/crawl_pr/GoogleCloudPlatform__DataflowTemplates/logs/110484660803.txt |
| GoogleCloudPlatform/DataflowTemplates | 36896489749 | Caused by: java.lang.UnsupportedClassVersionError: com/puppycrawl/tools/checkstyle/api/CheckstyleException has been compiled by a more recent version of the Java Runtime (class fil | data/crawl_pr/GoogleCloudPlatform__DataflowTemplates/logs/110484661606.txt; data/crawl_pr/GoogleCloudPlatform__DataflowTemplates/logs/110484661644.txt |
| GoogleCloudPlatform/DataflowTemplates | 36896489806 | Caused by: java.lang.UnsupportedClassVersionError: com/puppycrawl/tools/checkstyle/api/CheckstyleException has been compiled by a more recent version of the Java Runtime (class fil | data/crawl_pr/GoogleCloudPlatform__DataflowTemplates/logs/110484662244.txt; data/crawl_pr/GoogleCloudPlatform__DataflowTemplates/logs/110484662310.txt |
| GoogleCloudPlatform/DataflowTemplates | 36896490022 | Caused by: java.lang.UnsupportedClassVersionError: com/puppycrawl/tools/checkstyle/api/CheckstyleException has been compiled by a more recent version of the Java Runtime (class fil | data/crawl_pr/GoogleCloudPlatform__DataflowTemplates/logs/110484662282.txt; data/crawl_pr/GoogleCloudPlatform__DataflowTemplates/logs/110484662398.txt |
| GregTechCEu/GregTech-Modern | 29982631687 | Caused by: java.lang.NoClassDefFoundError: com/gregtechceu/gtceu/core/IFireImmuneEntity | data/crawl_pr/GregTechCEu__GregTech-Modern/logs/89127636505.txt |
| NationalSecurityAgency/datawave | 36869889319 | ##[error]Exception in thread "main" java.lang.NoSuchMethodError: 'java.lang.String org.eclipse.aether.impl.UpdateCheck.getPolicy()' | data/crawl_pr/NationalSecurityAgency__datawave/logs/110394831553.txt; data/crawl_pr/NationalSecurityAgency__datawave/logs/110394855109.txt |
| apache/druid | 29780131595 | [ERROR] Failed to execute goal org.apache.maven.plugins:maven-compiler-plugin:3.14.1:compile (default-compile) on project druid-processing: Fatal error compiling: error: release ve | data/crawl_pr/apache__druid/logs/88488810349.txt |

Chi tiết tầng 2 và lá tầng 3: `summary.json`, `run_changes.csv`. Chuyển nhãn commit: `commit_changes.csv`; đây là **ước tính** theo `(repo, sequence, head_sha)` chỉ từ run fail có trong scope, chưa phải bản xuất dataset đầy đủ. Không dùng các số run này để suy thẳng tỷ lệ commit hoặc đối chiếu trực tiếp với 375 job trong paper.

## Rà soát mẫu Codex

| Nhóm | Phù hợp | Không phù hợp | Chưa rõ | Tổng đã đọc | Phù hợp / mẫu đã rõ |
|---|---:|---:|---:|---:|---:|
| dependency/core:7:dependency | 29 | 0 | 1 | 30 | 29/29 (100.0%) |
| dependency/fallback:71 | 6 | 0 | 0 | 6 | 6/6 (100.0%) |
| dependency/fallback:72 | 30 | 0 | 0 | 30 | 30/30 (100.0%) |
| dependency/fallback:73 | 30 | 0 | 0 | 30 | 30/30 (100.0%) |
| dependency/fallback:74 | 0 | 0 | 30 | 30 | Chưa đủ bằng chứng |
| dependency/fallback:75 | 0 | 0 | 27 | 27 | Chưa đủ bằng chứng |
| dependency/resolution | 27 | 0 | 3 | 30 | 27/27 (100.0%) |
| infra/resolve_summary | 30 | 0 | 0 | 30 | 30/30 (100.0%) |
| infra/status_401_403 | 30 | 0 | 0 | 30 | 30/30 (100.0%) |
| proposal/Q3-gradle-conflict | 24 | 0 | 0 | 24 | 24/24 (100.0%) |
| proposal/Q3-gradle-jvm | 13 | 0 | 0 | 13 | 13/13 (100.0%) |
| proposal/Q3-jdk-bytecode | 30 | 0 | 0 | 30 | 30/30 (100.0%) |
| proposal/Q3-jdk-target | 1 | 0 | 0 | 1 | 1/1 (100.0%) |
| proposal/Q3-linkage | 1 | 0 | 0 | 1 | 1/1 (100.0%) |
| proposal/Q3-missing-class-pair | 29 | 0 | 1 | 30 | 29/29 (100.0%) |

Ghi chú từng mẫu: `data\human_labels\codex_review_dependency_2026-10-18.jsonl`. Quần thể từng nhóm và mẫu seed cố định: `sample_population.json`, `samples.json`; đoạn log của job quyết định và mẫu Q3 có trong `review_samples.json`, trích bằng `scripts/analysis/dependency_review_samples.py`. “Chưa rõ” tách riêng; không coi là đúng hoặc sai. Các nhóm infra/resolve và infra/401 có thể chồng lặp. Không cộng các tầng để suy precision chung.

Đã rà soát 342 lượt mẫu: 243 mẫu baseline + 99 mẫu Q3, có thể trùng run giữa các nhóm. Có 280 lượt phù hợp và 62 lượt chưa rõ; không có đủ cơ sở để xác nhận các lượt chưa rõ là đúng hoặc sai. Fallback 71 chỉ có 6 run trong quần thể, fallback 75 có 27 nên lấy toàn bộ. Nhóm Q3 target/linkage chỉ có một trường hợp mỗi nhóm, không đủ để suy chất lượng ngoài scope.

Điểm cần người duyệt chú ý: cả 30 mẫu yarn fallback 74 và 27 mẫu pnpm fallback 75 chỉ thấy summary/exit code, chưa đủ loại trừ mạng hoặc cấu hình; không dùng chúng để công bố precision cao. Ba trường hợp Gradle version rỗng và một artifact bị ràng buộc repo cũng cần phân biệt buildconfig/quyền truy cập với dependency. Một mẫu missing-class của chính GregTech chưa chứng minh xung đột thư viện.

## Bộ quy tắc đề xuất

| ID | Lớp | Nhãn | Regex khớp run ? | Run thực đổi nhãn |
|---|---|---|---:|---:|
| Q1-replace-34 | fallback_replace | dependency | 0 | 53 |
| Q1-replace-36 | fallback_replace | dependency | 160 | 172 |
| Q1-replace-44 | fallback_replace | dependency | 160 | 0 |
| Q1-replace-45 | fallback_replace | dependency | 0 | 16 |
| Q1-upper-bound | unknown_only | dependency | 160 | 0 |
| Q1-convergence | unknown_only | dependency | 83 | 59 |
| Q1-banned | unknown_only | dependency | 7 | 5 |
| Q3-jdk-bytecode | q3_override | dependency | 14 | 106 |
| Q3-jdk-target | q3_override | dependency | 1 | 1 |
| Q3-linkage | q3_override | dependency | 1 | 1 |
| Q3-gradle-jvm | q3_override | dependency | 13 | 13 |
| Q3-gradle-conflict | q3_override | dependency | 24 | 24 |
| Q3-missing-class-pair | q3_override | dependency | 72 | 58 |
| DEP-pnpm-version | unknown_only | dependency | 77 | 77 |
| DEP-lockfile-frozen | unknown_only | dependency | 31 | 31 |
| DEP-npm-eresolve | unknown_only | dependency | 0 | 0 |
| DEP-plugin-missing | unknown_only | dependency | 135 | 0 |
| DEP-gradle-file-missing | unknown_only | dependency | 27 | 27 |
| NET-gradle-http | unknown_only | infra | 238 | 198 |

Regex, guard, số khớp và tối đa ba log mẫu mỗi quy tắc nằm trong `configs/label_rules_dependency_proposed.json`, `rule_examples.json` và bảng XLSX. Số regex khớp là trước guard/ưu tiên; số thực đổi nhãn là quyết định cuối cùng. Quy tắc chưa có log khớp chưa được xác nhận bằng dữ liệu scope này.

Q1: đổi bốn fallback 34/36/44/45; 36 và 44 bỏ tên artifact. Quy tắc mới chỉ xét enforcer báo lỗi, không xét `passed` hay tên plugin đơn thuần. Đã loại ứng viên `has been banned from the build`: Maven có thể chỉ đang bỏ qua module do lỗi trước đó, không phải banned dependency. Q3: bytecode/target JDK, lỗi liên kết trong ngữ cảnh thất bại, xung đột version/JVM Gradle. Không thêm ClassNotFoundException hay NoClassDefFoundError tổng quát: chỉ xét cặp NoClassDefFoundError → ClassNotFoundException cùng lớp, nguyên nhân cuối gần BUILD FAILED; static initialization bị loại. Các dạng còn lại giữ ? khi chưa chứng minh nguyên nhân.

Q2 giữ 401/403 trong NETWORK. Lỗi GET/HEAD chỉ đề xuất infra khi ngữ cảnh khớp NETWORK. Q4 giữ `Failed to read artifact descriptor` không rõ nguyên nhân là ?. Plugin thiếu chỉ đề xuất khi có ngữ cảnh không tồn tại và không có NETWORK. `No matching variant` không được tự động coi là thiếu artifact.

## Các cụm chưa gán nhãn

| Tín hiệu | Chữ ký | Run |
|---|---|---:|
| plugin_resolve | Plugin [id: 'ru.vyarus.pom', version: '3.0.0', apply: false] was not found in any of the following sources: | 109 |
| enforcer | [ERROR] Rule 4: org.apache.maven.enforcer.rules.dependency.RequireUpperBoundDeps failed with message: | 79 |
| js_deps | Error: ERR_PNPM_NO_MATCHING_VERSION | 77 |
| runtime_linkage | Caused by: java.lang.NoClassDefFoundError: org/jboss/logging/Logger | 55 |
| transfer | > Could not GET '<url> Received status code <n> from server: Too Many Requests | 53 |
| resolve_summary | > Could not resolve all artifacts for configuration 'classpath'. | 50 |
| resolve_summary | > Could not resolve all files for configuration ':detekt-rules:testRuntimeClasspath'. | 50 |
| gradle_conflict | No matching variant of dev.detekt:detekt-api:2.0.0-alpha.5 with capability 'dev.detekt:detekt-api-test-fixtures' was found. The consumer was configured to find a library for use du | 50 |
| enforcer | [ERROR] Rule 1: org.apache.maven.enforcer.rules.dependency.DependencyConvergence failed with message: | 37 |
| transfer | Caused by: org.gradle.internal.resource.transport.http.HttpRequestException: Could not GET '<url> | 35 |
| lockfile | ? Verifying lockfile against supply-chain policies (<n> entries)... | 30 |
| transfer | > Could not GET '<url> | 30 |
| transfer | > Could not GET '<url> Received status code <n> from server: Forbidden | 26 |
| status_401_403 | > Could not GET '<url> Received status code <n> from server: Forbidden | 24 |
| transfer | Caused by: org.gradle.internal.resource.transport.http.HttpErrorStatusCodeException: Could not GET '<url> | 23 |
| transfer | [ERROR] Failed to execute goal org.sonatype.central:central-publishing-maven-plugin:0.<n>.0:publish (injected-central-publishing) on project axon-docs-samples: Failed to deploy art | 20 |
| enforcer | [ERROR] Rule 0: org.apache.maven.enforcer.rules.dependency.DependencyConvergence failed with message: | 18 |
| js_deps | [ERR_PNPM_OUTDATED_LOCKFILE] Cannot install with "frozen-lockfile" because pnpm-lock.yaml is not up to date with <ROOT>/console/frontend/src/main/frontend/package.json | 18 |
| resolve_summary | > Could not resolve all files for configuration ':opensearch-sql-plugin:compileClasspath'. | 18 |
| enforcer | [INFO] Rule 0: org.apache.maven.enforcer.rules.dependency.BannedDependencies passed | 16 |
| gradle_conflict | > No matching variant errors are explained in more detail at <url> | 16 |
| resolve_summary | [ERROR] Extension io.github.lenaschoenburg:branch-scoped-local-repository:0.2.0 or one of its dependencies could not be resolved: Plugin io.github.lenaschoenburg:branch-scoped-loca | 16 |
| artifact_descriptor | Failed to read artifact descriptor for io.github.lenaschoenburg:branch-scoped-local-repository:jar:0.2.0 | 16 |
| plugin_resolve | [ERROR] Extension io.github.lenaschoenburg:branch-scoped-local-repository:0.2.0 or one of its dependencies could not be resolved: Plugin io.github.lenaschoenburg:branch-scoped-loca | 16 |
| resolve_summary | Could not resolve all artifacts for configuration 'classpath'. | 13 |
| lockfile | ➤ YN<n>: It will prevent malicious lockfile manipulations, in exchange for a slower install time. You can opt-out if necessary; check our documentation for more details. | 13 |
| enforcer | [ERROR] Require upper bound dependencies error for io.grpc:grpc-googleapis:1.<n>.0 [runtime]. Paths to dependency are: | 12 |
| status_401_403 | [ERROR] Forbidden method invocation: java.lang.String#format(java.lang.String,java.lang.Object[]) [Uses default locale] | 11 |
| status_401_403 | Caused by: java.lang.IllegalStateException: HTTP/S status code: <n> | 11 |
| resolve_summary | > Could not resolve all files for configuration ':compileClasspath'. | 10 |
| lockfile | [ERROR] $ bun install --frozen-lockfile && bun --bun webpack --config webpack.config.js | 10 |
| transfer | Caused by: org.gradle.internal.resource.transport.http.HttpErrorStatusCodeException: Could not GET '<url> Received statu | 9 |
| runtime_linkage | Caused by: java.lang.ClassNotFoundException: org.codehaus.groovy.runtime.callsite.CallSiteArray | 9 |
| resolve_summary | [ERROR] Extension com.gradle:common-custom-user-data-maven-extension:2.4.0 or one of its dependencies could not be resolved: Plugin com.gradle:common-custom-user-data-maven-extensi | 9 |
| artifact_descriptor | Failed to read artifact descriptor for com.gradle:common-custom-user-data-maven-extension:jar:2.4.0 | 9 |

Toàn bộ cụm và tối đa ba log mẫu/cụm được lưu ở `clusters.json`; `cluster_assessment.json` nối từng cụm với nhãn mẫu theo bộ đề xuất và regex ứng viên. Số run của cụm là số chứa tín hiệu, không suy từ ba mẫu thành số run đổi nhãn. Một run có thể thuộc nhiều cụm tín hiệu. Tên dependency, lockfile, enforcer hoặc ngoại lệ đơn thuần chưa chứng minh nguyên nhân làm fail.

Các cụm đáng chú ý còn giữ ?: 109 thông báo plugin ru.vyarus.pom bị rút gọn không có mã mạng hoặc bằng chứng artifact thiếu; 50 thông báo detekt test-fixtures không có capability/variant phù hợp (không tự coi là lệch JVM); thông báo trợ giúp `No matching variant errors are explained` và Yarn hardened-mode/lockfile chỉ là mô tả, không phải nguyên nhân. Artifact descriptor của Maven extension thiếu cause tiếp tục giữ ? theo Q4. Cặp missing-class đủ guard vẫn cần người duyệt: thiếu class của chính project có thể là lỗi đóng gói, chưa chứng minh xung đột thư viện.

## Nhãn người, giới hạn và kiểm tra

Có 5583 bản ghi đối chiếu không khớp ít nhất một cấu hình; **1** bản ghi xung đột mới so baseline. Xem `human_conflicts.json`, gồm nguồn và nhãn từng cấu hình. Đọc labels/adjudication theo dòng cuối và ưu tiên adjudication; blind3 giữ lá tầng 3; round3/4 đối chiếu bằng thành viên cụm, chỉ để báo xung đột, không tích hợp rule các vòng này.

Hàm subtype hiện hành có thể chưa nhận HTTP 401/403 từ dòng bằng chứng, và timeout có thể vào lá crash trước network. Báo lá thực tế theo code hiện hành; `leaf_proposed` không ghi đè kết quả subtype. Cần người duyệt riêng thay đổi subtype nếu muốn thống nhất toàn bộ lỗi tải vào network.

CSV khác manifest được cảnh báo; nhãn baseline luôn tính lại từ log. `csv_drift.json` ghi khác biệt theo run. `missing_logs.json` ghi log thiếu, không suy nguyên nhân từ file không tồn tại. Manifest hash danh sách đường dẫn log không chứng minh nội dung file bất biến; cần giữ snapshot log khi tái lập.

Kiểm tra bộ chạy: `python -B -m unittest discover -s tests -p test_rule_eval.py -v`. Test chặn mở file để ghi ngoài output và kiểm tra quy tắc chọn job/giới hạn Q3. Các test ranh giới mới của gold_labels chỉ thêm sau duyệt.

Chạy lại vào thư mục **mới**: `python -B -m project3.pipeline.rule_eval --proposed configs/label_rules_dependency_proposed.json --out data/rule_eval/dependency-rerun-20261018`. Bảng cần người duyệt: `docs/duyet-quy-tac-dependency-2026-10-18.xlsx` (cột Nhãn người chọn để trống). Sau duyệt mới tích hợp, đổi RULE_VERSION, sao lưu rồi relabel/export.

### Xung đột mới theo nguồn và quy tắc

| Nguồn | Quy tắc | Bản ghi xung đột mới |
|---|---|---:|
| data\human_labels\labels.jsonl | Q3-jdk-bytecode | 1 |

Thay đổi do Q1/Q3 có thể trái nhãn người theo chính sách cũ; đây là trường hợp phải duyệt lại theo chính sách mới, không tự coi mọi xung đột là quy tắc sai. Một run có thể có nhiều nguồn nhãn tham chiếu.

Bộ đề xuất đúng lúc chạy được lưu nguyên ở `proposal.input.json`; file JSON bàn giao chỉ bổ sung số đếm và xung đột sau đánh giá. Hai hash được phân biệt trong manifest. Các lượt thử chưa hoàn tất ở thư mục không có manifest completed không được dùng làm kết quả.
