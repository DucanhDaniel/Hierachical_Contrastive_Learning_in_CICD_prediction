# Kiểm tra rule và gán lại nhãn cũ — 10/10/2026

Đã đọc log trên đĩa của 16 run trong `data/human_labels/rule_errors.csv`, không chỉ dòng evidence bị cắt ở 200 ký tự. File này ghi những bất đồng sau phân xử; một dòng xuất hiện trong file không tự chứng minh quy tắc sai. Các nhãn dưới đây là kết luận kiểm tra của Codex, chưa thay thế nhãn người.

## Kết luận từng run

| Repo | Run | Rule cũ | Nhãn người cuối | Rule mới | Bằng chứng và kết luận |
|---|---|---|---|---|---|
| druid | 31652966117 | lint | unclear | lint | RAT: `Counter(s) UNAPPROVED exceeded`. Đây là kiểm tra license, thuộc lint theo hướng dẫn gán. |
| pinot | 31876099283 | infra | unclear | test | Job Unit Test Set 2 báo `There are test failures`; job Linter khác chỉ báo extension không resolve được, không cho biết nguyên nhân. Không dùng job thứ hai để phủ nhận test fail ở job thứ nhất. |
| paimon | 32867467808 | infra | dependency | ? | Plugin resolve thất bại, `Failed to read artifact descriptor`; không có bằng chứng artifact không tồn tại hay lỗi mạng. |
| paimon | 32350719328 | infra | dependency | ? | Checkstyle plugin không resolve được descriptor. Không phải checkstyle violation; cũng chưa chứng minh thiếu phiên bản artifact. |
| iceberg | 30253491348 | infra | unclear | infra | Maven Central trả `Received status code 403 from server: Forbidden` cho nhiều artifact. Không phải test assertion failure. |
| tomcat | 36061422660 | compile | dependency | compile | javac báo package trong source Tomcat không tồn tại và `cannot find symbol`. Không có lỗi tải artifact chứng minh dependency thiếu. |
| storm | 36813992706 | lint | unclear | lint | RAT: `Unexpected count for UNAPPROVED, limit is [0,0]. Count: 2`. |
| storm | 36813597751 | lint | unclear | lint | Cùng bằng chứng RAT/UNAPPROVED. |
| druid | 34181241344 | lint | unclear | lint | RAT/UNAPPROVED ở druid-opentsdb-emitter. |
| druid | 35548743274 | lint | unclear | lint | Hai job đều báo RAT/UNAPPROVED. |
| kafka | 33147166333 | test | flaky | test | Summary: `38451 PASSED, 1 FAILED, 3 FLAKY`. Một test còn fail; có test flaky khác không làm cả run thành flaky. |
| gravitino | 33845156102 | test | infra | test | Test fail kèm `NoClassDefFoundError`, `ClassNotFoundException`, `ZipFile closed` khi load Hive client. Chưa có bằng chứng lỗi hạ tầng ngoài để đổi test fail thành infra. |
| iotdb | 34300025790 | compile | infra | compile | Một job có connection reset; job khác có `COMPILATION ERROR` và thiếu method `createTsFileResource`. Giữ ưu tiên compile khi tổng hợp run. |
| druid | 36682779402 | lint | unclear | lint | RAT/UNAPPROVED ở druid-cassandra-storage. |
| ozone | 30240168203 | infra | dependency | ? | PMD plugin không resolve được descriptor; log không in nguyên nhân mạng hay artifact không tồn tại. |
| ozone | 33727909313 | infra | unclear | infra | `Could not transfer artifact`, `status code: 429`, `Too Many Requests`. RAT chưa chạy được; đây không phải lint violation. |

12/16 run giữ nhãn rule; 4/16 đổi nhãn. Không đổi compiler error thành dependency chỉ vì compiler nói thiếu class/package; cũng không đổi mọi resolver failure thành dependency chỉ vì không nhìn thấy lỗi mạng.

## Rule mới

Version: `2026-10-10-resolution-context`, ở `src/project3/crawl/gold_labels.py`.

- Resolver failure có cause mạng/HTTP trong khối lỗi: `infra`; evidence chỉ tới dòng cause.
- Artifact/plugin không tồn tại được ghi rõ: `dependency`, gồm cả Gradle `Could not find group:artifact:version`. Các số trong version artifact không được hiểu thành HTTP status.
- Chỉ có `could not be resolved` hoặc `Failed to read artifact descriptor`, thiếu cause: không tự kết luận infra/dependency. Nếu không có lỗi xác định khác trong run, trả `?` và giữ evidence để review.
- Mỗi job được kiểm tra riêng trước khi tổng hợp theo ưu tiên rule; dấu hiệu mạng ở job khác không làm artifact-missing thành infra.
- Bỏ phần GitHub Actions echo lệnh/env trong group `Run ...`. Chuỗi lỗi trong lệnh `grep` của script retry không phải lỗi đã xảy ra.
- Giữ cách phân biệt compile, lint, test và flaky; giữ bộ lọc workflow/job tổng hợp.

`?` ở dataset tương ứng với `unclear` trong giao diện nhãn người. Đây là nhãn chưa xác định nguyên nhân, không phải pass.

Kiểm tra thêm mẫu 220 run phát hiện Polaris `29111153115` thiếu `tools.jackson.datatype:jackson-datatype-guava:3.2.1` và Tika `31741881271` thiếu artifact `tika-pipes-file-system:zip:4.0.0-SNAPSHOT`. Rule mới nhận diện dependency từ thông báo gốc; đây là hai ca cần xem lại ngoài danh sách 16 run ban đầu.

## Dataset và đối chiếu

Lệnh áp dụng: `.venv/Scripts/python.exe -m project3.pipeline.relabel`.

Lệnh sao lưu trước khi tạo lại hai `gold_labels.csv`, `data/processed/commits_all.parquet` và `data/processed/fine_labels.parquet`. Mỗi lần chạy tạo một thư mục `data/processed/relabel_<UTC timestamp>/`, có `backup/`, bản rule, log, `summary.json`, `run_changes.csv`, `commit_changes.csv`, `human_sample_comparison.csv` và `rule_errors_checked.csv`.

Các snapshot, dataset/thí nghiệm đã xuất và gói Kaggle cũ không được sửa hồi tố. Nếu chạy lại thí nghiệm, phải lấy dataset hiện hành và xuất gói mới; kết quả cũ vẫn dùng nhãn cũ.

Kết quả lần áp dụng này ở [`data/processed/relabel_20261010T141842874390Z/`](../../data/processed/relabel_20261010T141842874390Z/):

- Có **130 run đổi nhãn do rule**, xác nhận bằng cách chạy rule cũ từ Git HEAD và rule mới trên cùng log hiện có: 104 `infra → ?`, 16 `infra → dependency`, 7 `infra → test`, 3 `? → dependency`.
- Có thêm 976 thay đổi chỉ do log mới và 8 thay đổi do cả log mới lẫn rule. Chi tiết tách nguyên nhân ở `change_attribution.csv`; `old_rules.py` lưu baseline dùng đối chiếu.
- Thêm 1.339 run có nhãn so với CSV cũ. Bộ hiện hành có 19.682 run duy nhất trong hai root và 37.759 commit (trước: 37.656 commit). Không có run cũ nào bị loại khỏi bản xuất mới.
- Commit fail chưa xác định loại: **4.338 → 3.609**. Mức giảm có cả tác động của log tải thêm, không được quy hết cho rule mới.
- CSV PR có 9 dòng lặp run_id (bản cũ: 4), xuất phát từ metadata jobs đã lưu. Đối chiếu và pipeline commit đều dùng bản ghi cuối của mỗi run; số run ở đây đếm theo ID duy nhất.
- So với nhãn người cuối trên mẫu phát triển 220 run, độ khớp sau chuẩn hóa `unclear` thành `?` là **179 → 177 run**. Chưa sửa các nhãn người đang bất đồng với bằng chứng nêu ở bảng trên, và không coi con số này là kiểm chứng độc lập.

Không thay đổi `labels.jsonl`, `adjudication.jsonl`, `key.json`, `eval.json` hay `rule_errors.csv`. Nhãn tay cần người gán xem lại trước khi đổi. Bảng đối chiếu mới dùng toàn bộ log job fail hiện có mà pipeline nhãn đọc; giao diện gán mù chỉ hiện tối đa hai job và 60.000 ký tự cuối mỗi log, nên hai bên có thể khác lượng thông tin.

Mẫu 220 run đã được dùng để tìm/sửa rule; độ khớp trên mẫu này là kết quả phát triển, không phải kiểm chứng độc lập hay độ chính xác toàn dataset. Cần một mẫu mới chưa dùng để sửa rule nếu muốn đo độ chính xác sau sửa.

Kiểm tra: 22 tests đạt, gồm resolver thiếu cause, artifact missing, HTTP 403/429, ranh giới giữa job, command echo, compiler/lint/test/flaky và các kiểm tra checkpoint/crawl hiện có. Trên Windows, đặt `PYTHONIOENCODING=utf-8` khi chạy toàn bộ tests để subprocess đọc log đúng encoding.
