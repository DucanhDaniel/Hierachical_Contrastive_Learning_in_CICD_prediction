# Chạy song song, checkpoint và tạm dừng crawl

Hai worker đang được dùng:

- `scripts/crawl_expand.ps1`: PR repo lõi, sau đó push/PR mở rộng và gán nhãn/gộp commit.
- `scripts/crawl_extra_push.ps1`: lấy push repo mở rộng; sau khi push hoàn tất, Resume chuyển worker này sang PR bằng `-CrawlEvent pull_request`. Log riêng: `data/crawl_extra_push.log` hoặc `data/crawl_extra_pr.log`; trạng thái: `data/crawl_extra_push_state.json`.

Mỗi crawler vẫn có 8 luồng tải log. Các worker dùng chung quota GitHub. Khóa OS tại `<root>/<owner>__<repo>/.crawl.lock` ngăn hai crawler mới cùng ghi một repo/event, cho phép PR repo lõi và PR repo mở rộng cùng dùng root `data/crawl_pr`. Worker nào đến một repo đang bị khóa thì chờ, rồi đọc lại metadata và bỏ qua jobs/log đã lưu. Pipeline chính chờ worker phụ hoàn tất trước khi gán nhãn/gộp parquet.

Ngày 2026-10-07 lúc kiểm tra 21:14, worker đầu tiên không còn chạy, log dừng ở bước lấy jobs Pinot lúc 18:06; state cũ vẫn ghi running. Đã khôi phục cả hai worker từ checkpoint lúc 21:23. Cả hai dùng khóa theo repo. Worker phụ đã xong lượt push và hiện lấy PR repo mở rộng. Không xác định nguyên nhân tiến trình cũ dừng chỉ từ state/log hiện có.

## Các lệnh điều khiển

Chạy từ `D:\projects\project3` trong PowerShell của người dùng:

```powershell
# Xem worker nào đang chạy và trạng thái/checkpoint đã lưu
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/crawl_control.ps1 -Action Status

# Tạm dừng các worker và lưu checkpoint
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/crawl_control.ps1 -Action Pause

# Tiếp tục từ dữ liệu đã lưu, giữ hai worker nếu push mở rộng còn dang dở
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/crawl_control.ps1 -Action Resume
```

`Pause` chỉ dừng cây tiến trình có PID đã lưu và command line trỏ đúng script trong workspace. Nó cũng dừng worker chờ xuất báo cáo. `Resume` từ chối khởi chạy nếu còn worker được quản lý đang chạy.

## Checkpoint thực tế

- `runs.jsonl`: run đã lưu theo ID, ghi sau từng cửa sổ API.
- `jobs.jsonl`: run đã lấy jobs, ghi sau từng run.
- `logs/<job_id>.txt`: log hoàn tất; `.missing`: kết quả tải không có log. Các marker `.missing` hiện được giữ nguyên khi resume.
- `data/crawl_checkpoint.json`: ảnh chụp số runs, jobs, logs, missing, partial theo repo; cập nhật khi kiểm tra/tạm dừng/tiếp tục. Dữ liệu JSONL và log trên đĩa là nguồn quyết định phần cần tải tiếp.

Khi resume, crawler kiểm tra các ID/file đã có; metadata cửa sổ 90 ngày được quét lại để bổ sung run mới, nhưng jobs/log hoàn tất được bỏ qua. Đây không phải checkpoint cursor API hay mốc thời gian cố định; cửa sổ được tính lại tại lần chạy tiếp theo.

Crawler mới ghi log vào `.txt.part` rồi đổi tên thành `.txt` sau khi ghi xong. File `.part` bị bỏ dở không được tính là hoàn tất và sẽ được ghi lại khi resume. Khóa OS tự nhả khi tiến trình dừng; không cần xóa `.crawl.lock`.

`Pause` dùng dừng tiến trình, không đợi toàn bộ lượt crawl. Để bảo vệ worker đầu tiên chưa có cơ chế ghi atomic, các log vừa được sửa trong 10 giây gần thời điểm dừng được chuyển thành `.interrupted.<timestamp>`; vài log này sẽ được tải lại. File gốc vẫn được giữ để đối chiếu. Dòng JSONL cuối bị cắt cũng được sao lưu trước khi bỏ phần chưa hoàn chỉnh. Nếu JSONL hỏng ở giữa file, công cụ báo lỗi và không tự sửa.

Chỉ chạy phục hồi khi crawler đã dừng:

```powershell
uv run python -m project3.crawl.checkpoint --repair
```

14 kiểm tra tự động đã đạt, gồm khóa giữa hai tiến trình, JSONL cuối bị cắt, UTF-8 bị cắt, lỗi ở giữa file và repo không có run fail/workflow. Cú pháp các script điều khiển/worker đã kiểm tra. Resume đã thực hiện trên lượt crawl thật ngày 2026-10-07; chưa chủ động Pause lượt thật.

Không tạo Windows Task Scheduler theo lựa chọn của người dùng ngày 2026-10-07. Pipeline hiện tại chưa tải diff code.
