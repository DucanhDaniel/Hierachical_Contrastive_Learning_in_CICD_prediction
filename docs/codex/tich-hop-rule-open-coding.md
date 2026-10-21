# Tích hợp rule open coding — 10/10/2026

Đã tích hợp version `2026-10-10-open-coding-v1`. Bộ thực thi gồm 63 rule: lint 33, infra 12, compile 7, test 6,
non_build 4, dependency 1. Nguồn là bản `configs/label_rules_proposed.json` đã rà soát lần 3.

## Cách chạy

`gold_labels.py` đọc bản thực thi `configs/label_rules.json` theo đường dẫn workspace, sắp theo priority và biên dịch
regex một lần. File đề xuất vẫn riêng để việc export open coding tiếp theo không tự thay bộ rule đang dùng.
Mỗi rule thực thi giữ `source_regex` để đối chiếu với bản người duyệt.

`base_gold_label()` giữ nguyên toàn bộ `GOLD_RULES`, thứ tự và logic hiện hành. `gold_label()` chỉ chạy fallback nếu
kết quả base là `?`, giữ evidence từ dòng khớp. Không đổi các nhãn base đã xác định; không đoán nhãn cho cụm unclear.

Fallback trả `non_build` thì CSV đánh dấu `non_build=True`. `build_log_labels.py` đọc cờ này và bỏ run trước khi
đếm runs/fail, gom nhãn và xác định first_failure. Commit chỉ có run bị loại không xuất vào tập commit; commit có
build pass và một run non_build fail vẫn là pass.

Không thêm mẫu timeout vào `NETWORK` gốc trong lần tích hợp này: giữ nguyên contract base; dạng timeout mới của
Lumina được fallback nhận diện từ cause mạng trên cùng dòng. Mẫu Missing dependency yêu cầu thông báo classpath cụ thể.

## Tổng quát hóa và hồi quy

Đã thử 17 phép tổng quát hóa module/version. Quét log của mọi run có nhãn đã xác định trong hai root hiện hành:
6 phép mới khớp thêm run mang nhãn khác, nên giữ regex gốc cho các priority **13, 18, 20, 24, 25, 32**.
11 phép còn lại được giữ. Bằng chứng ở `data/processed/open_coding_generalization_check.json`.

Các phép giữ lại gồm version Maven, đường dẫn task pylint, formatCheckPython và groovydocAll. Không mở rộng
thành mẫu goal surefire/failsafe thất bại. Chữ ký chưa có regex chỉ là ghi chú, không tự trở thành rule.

## Kết quả áp dụng

Đã chạy `project3.pipeline.relabel`. Audit và backup ở
[`data/processed/relabel_20261010T162953654184Z/`](../../data/processed/relabel_20261010T162953654184Z/).

| Chỉ số | Trước | Sau |
|---|---:|---:|
| Run build còn `?`, đếm theo ID duy nhất | 3.228 | 1.723 |
| Commit fail còn `?` | 3.609 | 2.729 |
| Tổng commit | 37.759 | 38.097 |
| Nhãn chi tiết của commit fail do code | — | 6.166 |

- Trong các run cũ: 233 chuyển `? → compile`, 498 `? → lint`, 313 `? → infra`, 102 `? → test`,
  6 `? → dependency`, 354 `? → non_build`. Một chuyển đổi nằm ở workflow vốn đã non_build nên không tính vào
  mức giảm run build `?`.
- Bản xuất nhận thêm 77 run fail có metadata jobs của JUnit Framework; tổng commit tăng còn có tác động từ
  metadata crawl mới. Không quy mọi thay đổi tổng số commit cho rule.
- Có 100 commit cũ `? → pass` sau khi bỏ run non_build; 91 commit không còn build run nào nên bị loại khỏi bản mới.
  Danh sách ở `commit_changes.csv` và `removed_commits.csv`.
- Trên mẫu người gán: fallback gán 12/36 run chưa xác định, 8 khớp nhãn cuối. Hai run non_build không có nhãn tương
  ứng trong giao diện gán mù ban đầu. Đây là mẫu phát triển đã dùng sửa rule, không phải kiểm chứng độc lập.

Đã tạo lại hai gold CSV, `commits_all.parquet` và `fine_labels.parquet`; không sửa snapshot hay kết quả Kaggle cũ.
Backup gồm dataset cũ, source rule và cấu hình fallback thực thi.

## Kiểm tra

30 tests đạt: fallback không đè nhãn base; compile trước lint; descriptor thiếu cause giữ `?`; timeout/dependency
có cause cụ thể; loại non_build không làm commit pass thành fail; các kiểm tra crawl/checkpoint hiện có.
Sau khi bỏ các phép tổng quát hóa không đạt, chạy lại 18 kiểm tra gold labels đều đạt.

Kiểm tra dữ liệu thực xác nhận `GOLD_RULES` không đổi, mọi nhãn run cũ đã xác định được giữ, không có non_build
trong run_labels của commit, key commit không trùng và nhãn chi tiết khớp commit code-fail. SHA-256 xác nhận
`labels.jsonl`, `adjudication.jsonl`, `key.json` không thay đổi. Kết quả ở `verification.json` trong thư mục audit.
