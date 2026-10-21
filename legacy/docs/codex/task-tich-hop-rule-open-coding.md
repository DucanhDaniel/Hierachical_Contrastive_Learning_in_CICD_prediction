# Task: Tích hợp quy tắc từ open coding vào bộ gán nhãn

Ngày 10/10/2026. Người dùng đã gom các run `?` (nhãn quy tắc hiện hành, rule version `2026-10-10-resolution-context`) theo
chữ ký dòng lỗi và duyệt từng cụm bằng `src/project3/pipeline/label_ui.py opencode` (cách làm *open coding* giống LogCat của
Rausch et al., MSR 2017). Kết quả cần được đưa vào `src/project3/crawl/gold_labels.py`.

## Đầu vào

| File | Nội dung |
|---|---|
| `configs/label_rules_proposed.json` | 63 quy tắc, **đã sắp theo `priority`** (non_build → compile → lint → dependency → infra → flaky → test): `label`, `regex` (cú pháp Python `re`, cờ `re.M`), `signature`, `matches_unlabeled` (số run `?` khớp), `conflicts_in_human_sample` (run_id trong tập người gán mà nhãn người khác nhãn quy tắc); `non_build_signatures` (5 chữ ký non_build chưa có regex, chỉ để tham khảo) |
| `data/human_labels/opencoding.jsonl` | Nhật ký duyệt từng cụm (dòng sau cùng của mỗi cụm có hiệu lực); các bản trước khi sửa: `opencoding.before_fix_20261010.jsonl`, `opencoding.before_fix2_20261010.jsonl` |
| `data/human_labels/clusters.json` | 150 cụm lớn nhất (81% run `?`), mỗi cụm 4 log mẫu và danh sách `all_runs` |

Đã rà soát và sửa 12 cụm trước khi xuất (ghi chú `sửa theo rà soát` trong `opencoding.jsonl`): check-licenses → lint,
failsafe verify → test (sau đó đổi thành `?`, xem lần 2), enforcer/dependency-analyze thống nhất lint, groovydoc → lint, performanceTest → test; cụm
`MojoFailureException` chung chung và `<!DOCTYPE html>` → không tạo quy tắc; tiêu đề PR → non_build; Tomcat Ant dùng dòng
`Some tests completed with a Failure` thay cho dòng INFO.

### Sửa theo rà soát của Codex (lần 2)

Đã xử lý cả 6 điểm Codex nêu:

| # | Điểm | Đã sửa |
|---|---|---|
| 1 | Checkstyle `RegexpSingleline` bị gán test | c97 → lint |
| 2 | "Failed before controller upgrade" bị loại non_build | c76, c14, c25 (kịch bản tương thích Pinot: before/after upgrade/downgrade) → không tạo quy tắc, giữ `?` vì log không nêu nguyên nhân |
| 3 | `Failed to read artifact descriptor` gán dependency | c18, c33, c94, c95 → không tạo quy tắc, giữ `?` theo quy ước hiện hành |
| 4 | Xung đột thật ở lớp dự phòng | Surefire/failsafe: 152/201 run surefire và 89/89 run failsafe không ghi nguyên nhân trong đoạn log đã lưu → bỏ quy tắc "goal fail → test"; chỉ giữ `The forked VM terminated without properly saying goodbye` → infra (loại *crash* của Rausch). Spotless có `FormatterException: … error:` (code sai cú pháp) → compile, đứng trước lint. Pinot upgrade → `?`. Ba run Codex nêu (33378296818, 36813806886, 29739127369) không còn bị gán sai |
| 5 | `non_build` chưa được loại ở bước commit | **Việc tích hợp, xem bước 3 dưới** |
| 6 | OWASP dependency-check gán dependency | c49 → non_build (cùng chính sách security scan với `NON_BUILD_WF`: CVE, Trivy, security scan) |

Kiểm tra lại sau sửa: lớp mới gán **12/36** run `?` của tập người gán, **đúng 8**; 2 ca lệch là non_build (lúc gán mù
chưa có lựa chọn này); 2 ca còn lại là quy ước *crash → infra* (`Java heap space`, forked VM) mà người gán chọn unclear/test.
Tổng xung đột khi thử trên mọi run của tập người gán: 5 (trước: 10).

### Sửa theo rà soát của Codex (lần 3)

- Lumina (c84): resolve thất bại kèm lỗi mạng trên cùng dòng (`Could not transfer artifact … connect timed out`) → **infra**
  (regex `could\s+not\s+be\s+resolved:.*Could\s+not\s+transfer\s+artifact.*(?i:connect timed out|read timed out|connection
  reset/refused|unknown host|no route to host)`, khớp 4/4 log mẫu, phủ 11 run `?`). Gợi ý: bổ sung dạng timeout này vào
  `NETWORK` của bộ quy tắc gốc.
- AmazonServicesClientsProcessor (c7): siết vào nguyên nhân `Missing '…' dependency on the classpath` → dependency (phủ 20 run `?`).
- Sau sửa: 63 quy tắc, phủ 1.500/3.230 run `?`, tổng xung đột 5; số đo trên tập người gán không đổi (12/36, đúng 8).

## Việc cần làm

1. **Thêm một lớp quy tắc dự phòng** chạy **sau** `GOLD_RULES` hiện có: chỉ áp dụng khi kết quả hiện hành là `?`. Không đổi
   thứ tự hay nội dung các quy tắc cũ. Lưu evidence là dòng khớp như các quy tắc khác. Ghi rule version mới.
2. **Tổng quát hoá regex** gắn tên module hoặc phiên bản cụ thể để dùng được cho repo mới, ví dụ:
   - `>\s+Task\s+:server-common:spotlessJava\s+FAILED` → `>\s+Task\s+\S*:spotless\w*\s+FAILED`
   - `Execution failed for task ':common:javadoc'` → `Execution failed for task '[^']*:javadoc'`
   - `Execution failed for task ':clients:client-python:pylint'` → `Execution failed for task '[^']*:pylint'`
   - Không tổng quát hoá thành "goal surefire/failsafe fail": các goal này fail vì nhiều nguyên nhân (đã bỏ ở lần 2).
   Giữ đúng nhãn của cụm; regex sau khi tổng quát không được khớp thêm run đang có nhãn khác (kiểm tra bằng bước 4).
3. **Quy tắc `non_build`** (4 quy tắc có regex: PR chưa được duyệt `isn't ready for running the CI`, action không được phép,
   kiểm tra tiêu đề PR, quét OWASP): đánh dấu run là không phải build. **Phải sửa cả `build_log_labels.py`** để bỏ run có
   `non_build = True` khi gộp commit (hiện chỉ đọc cột `gold`), nếu không run bị loại vẫn làm commit thành fail/`?`.
4. **Chạy lại gán nhãn** bằng `project3.pipeline.relabel` (có sao lưu, `run_changes.csv`, đối chiếu với nhãn người). Báo:
   số run `?` trước/sau, phân bố nhãn mới, và trên tập người gán (`data/human_labels/`): lớp quy tắc mới gán bao nhiêu run và
   đúng bao nhiêu (lúc xuất: 12/36, đúng 8).
5. Xem lại 5 xung đột trong `conflicts_in_human_sample` (thử regex trên mọi run của tập người gán, kể cả run đã có nhãn
   từ quy tắc cũ). Phần lớn không ảnh hưởng vì lớp mới chỉ chạy khi kết quả là `?`; nếu một regex cũng sai ở run `?` thì siết lại.

## Không làm

- Không sửa `labels.jsonl`, `adjudication.jsonl`, `key.json` (nhãn người).
- Không đoán nhãn cho cụm `unclear` (gồm cụm 607 run không có dòng lỗi trong đoạn log đã lưu: nếu muốn xử lý, cần tải lại
  phần đuôi log dài hơn, ghi riêng, không gộp vào task này).
- Tập 220 run đã dùng để sửa quy tắc: số đo trên tập này là kết quả phát triển, không phải kiểm chứng độc lập.

## Trạng thái tích hợp

Đã tích hợp ngày 10/10/2026, version `2026-10-10-open-coding-v1`; bản thực thi ở `configs/label_rules.json`.
Đã sửa bộ lọc non_build khi gộp commit, kiểm tra hồi quy tổng quát hóa regex và gán lại dataset với backup.
Chi tiết kết quả và giới hạn đo lường: [tich-hop-rule-open-coding.md](tich-hop-rule-open-coding.md).
