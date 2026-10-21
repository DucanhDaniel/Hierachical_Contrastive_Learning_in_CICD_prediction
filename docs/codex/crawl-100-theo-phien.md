# Crawl 100 repo theo từng phiên

Task đã bắt đầu lúc 22:33 ngày 10/10/2026. Chạy PR trước, push sau, tuần tự theo 85 repo trong `configs/repos_100.txt`.
Người dùng chỉ mở máy vài tiếng mỗi phiên; không cần chạy liên tục đến 12/10. Không tạo Task Scheduler.

Trong PowerShell ở `D:\projects\project3`:

```powershell
# Xem trạng thái
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/crawl_100_control.ps1 -Action Status

# Trước khi tắt máy: dừng worker riêng của task và sửa checkpoint nếu có dòng cuối bị cắt
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/crawl_100_control.ps1 -Action Pause

# Lần sau mở máy: tiếp tục phần chưa xong
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/crawl_100_control.ps1 -Action Resume

# Xem tiến độ PR
Get-Content data/crawl_100_pr.log -Tail 20
```

`Resume` từ chối khởi chạy nếu supervisor/crawler con của task vẫn đang chạy. Repo đã hoàn tất trong
`data/crawl_100_results.json` được bỏ qua; repo dang dở dùng `runs.jsonl`, `jobs.jsonl` và log đã lưu để tiếp tục.
Những log hoàn tất được giữ; checkpoint không phải cursor của API, nên resume repo dang dở vẫn quét metadata
trong cửa sổ hiện hành nhưng bỏ qua jobs/log đã hoàn tất. Không dùng `crawl_control.ps1` của đợt 17 repo cũ để điều khiển task mới.

State: `data/crawl_100_state.json`; PID supervisor: `data/crawl_100.pid`. Log PR/push:
`data/crawl_100_pr.log`, `data/crawl_100_push.log`. Supervisor/checkpoint/gán nhãn:
`data/logs/crawl_100_supervisor.log`, `data/logs/crawl_100_runner_<timestamp>.*log`.

Mốc 22:00 ngày 12/10 là đánh giá tiến độ: nếu PR chưa xong ít nhất 43/85 repo thì các repo còn lại chuyển từ
90 xuống 60 ngày ở lần bắt đầu repo tiếp theo. Mốc 22:00 ngày 14/10 là hạn dừng crawl; không yêu cầu giữ máy
bật tới mốc này. Sau khi tải xong hoặc chạm hạn, worker kiểm tra checkpoint rồi tạo lại nhãn run/commit/nhãn
chi tiết với backup. Review rule cho repo mới và báo cáo độ phủ T5 vẫn cần thực hiện; trạng thái cuối là `needs_review`.

Trong lúc worker chạy, nó yêu cầu Windows giữ máy thức; Pause giải phóng yêu cầu đó. Nếu máy tắt đột ngột,
hãy dùng Status rồi Resume khi mở lại. Không coi state `running` là bằng chứng process còn sống.

Lượt khởi chạy đầu đã xác nhận ghi 558 run của JUnit Framework, trong đó 91 run fail đang lấy jobs.
Bản hiện hành dừng cả cây launcher Python khi chạm hạn; đã kiểm tra bằng tests. Lần Resume tiếp theo sẽ nạp
bản hiện hành. Lượt khởi chạy đầu chưa nạp bản sửa này và đã dừng vì lỗi state như mô tả bên dưới.

## Phục hồi lỗi state — 11/10/2026

Worker đầu đã dừng lúc 22:38 ngày 10/10 vì `PermissionError` khi đổi `crawl_100_state.json.part` thành file state
chính. State trước đây được ghi mỗi 5 giây ngay trong vòng chờ crawler; lỗi ghi thoát lên `finally` và dừng child.
Đó là lỗi ở supervisor mới, không phải lỗi mạng GitHub hay JSONL dữ liệu.

Đã bổ sung:

- Retry atomic replace tối đa 5 lần với backoff cho PermissionError; giữ nguyên bản `.part` nếu vẫn không thay được.
- Ghi state/kết quả là best effort: báo warning một lần cho mỗi file lỗi, tiếp tục child và thử ghi lại ở các vòng sau.
  Khi file ghi lại được, warning được reset. Không chuyển sang ghi JSON trực tiếp lên file chính có thể đang bị reader giữ.
- Resume đọc bản results chính hoặc `.part` hợp lệ mới nhất; nếu bản mới bị cắt, dùng bản hợp lệ còn lại. Nếu cả hai
  đều không hợp lệ thì báo lỗi và giữ file để kiểm tra, không tự đánh dấu repo hoàn tất.
- Status/Pause/Resume cũng đọc snapshot state chính hoặc `.part` mới nhất hợp lệ để xác định PID thực.
- Repo có child exit 0 nhưng không có status completed/failed hợp lệ bị đánh dấu failed để retry, không coi exit code
  đơn lẻ là đã tải xong.

Giữ cơ chế checkpoint, thử lại repo failed, lock chống hai supervisor, và dừng cả cây child tại hạn chót. Các lỗi ghi
JSONL/log trong chính crawler vẫn phải báo failed; không che lỗi dữ liệu bằng state best effort.

7 tests riêng của supervisor đạt, gồm replace bị khóa rồi thành công, khóa kéo dài không dừng child, results `.part`
mới hơn và `.part` bị cắt. Cú pháp controller PowerShell đạt. Thay đổi này chưa khởi động lại lượt crawl.
