# Task: Mở rộng bộ dữ liệu build failure có nhãn loại lỗi (crawl GitHub Actions + gán nhãn từ log)

## 1. Bối cảnh

Đề tài: dự đoán build CI/CD fail **trước khi chạy**, từ diff của commit, mô hình Hierarchical Contrastive Learning.
Cây nhãn cần có cho mỗi commit:

```
pass | fail
        ├─ code  ├─ test
        │        └─ build  (compile / lint / dependency)
        └─ env   (infra / flaky)
```

Nhãn loại lỗi **phải lấy từ log thật**. Nhãn đoán theo tên step (cách dùng cho bộ GHARuns) chỉ đúng 59%.
Nguyên nhân là lỗi hạ tầng (Maven 429/503, connection reset) xảy ra ngay trong step build/test.

Dữ liệu hiện có (`data/processed/commits_logs90.parquet`): 6 repo Apache, chỉ gồm push lên nhánh chính,
90 ngày, 3.489 commit, 651 fail. **Nhóm `build` chỉ có 42 commit fail (14 lần fail đầu), không đủ để train.**
Lỗi compile/lint chủ yếu bị bắt ở pull request, trước khi merge. Vì vậy task này lấy thêm **build của PR**
và **thêm repo**.

Ràng buộc thời gian: GitHub chỉ giữ log **90 ngày**. Mỗi ngày chưa crawl là mất một ngày dữ liệu.
Chạy crawl ngay (T1, T2) trước khi làm các việc khác.

## 2. Code đã có (đã chạy thử, không cần viết lại)

| File | Việc |
|---|---|
| `src/project3/crawl/github.py` | REST client. Đọc `GITHUB_ACCESS_TOKEN` từ `.env`, tự chờ khi chạm rate limit, retry khi lỗi mạng. `get_log_tail()` chỉ tải 512KB cuối log bằng Range request (kho log Azure rất chậm từ VN). |
| `src/project3/crawl/gha.py` | Crawler: workflow CI → run → job/step của run fail → log của job fail (chỉ giữ đoạn quanh `##[error]`). Chạy lại sẽ bỏ qua phần đã có. Hỗ trợ `--event pull_request`, `--repos-file` (dùng nhiều lần), `--max-jobs-per-run`, chia cửa sổ thời gian để vượt trần 1000 kết quả của API. |
| `src/project3/crawl/gold_labels.py` | Gán nhãn từng run fail từ log bằng `GOLD_RULES` (regex, có thứ tự ưu tiên compile → lint → infra mạnh → flaky → test → infra yếu). Xuất `<root>/gold_labels.csv`. `NON_BUILD_WF` loại workflow không phải build. |
| `src/project3/crawl/build_log_labels.py` | Gộp run → commit. Nhãn commit = nguyên nhân sớm nhất. Cột `cause` (code/env), `label_group` (test/build/env), `label`, `first_failure`. Nhận nhiều root. |
| `configs/repos_core.txt`, `configs/repos_extra.txt` | Danh sách repo. |
| `scripts/crawl_weekly.ps1` | Chạy toàn bộ: push + PR → gold_labels → build_log_labels. Ghi log ra `data/crawl_weekly.log`. |

Định dạng dữ liệu, mỗi repo một thư mục `<root>/<owner>__<repo>/`:
- `runs.jsonl`: id, workflow_id, name, event, head_branch, head_sha, conclusion, run_attempt, created_at, ...
  Với PR có thêm `head_repository` (repo fork) và `pull_requests` (số PR; rỗng nếu PR từ fork).
- `jobs.jsonl`: `{run_id, jobs: [{id, name, conclusion, steps: [{name, conclusion, number}]}]}` (chỉ run fail).
- `logs/<job_id>.txt`: đoạn log quanh lỗi. `logs/<job_id>.missing`: log đã hết hạn.

Thư mục dữ liệu: `data/validate/` (push, đã có 6 repo), `data/crawl_pr/` (PR, chưa có).

## 3. Việc cần làm

### T1. Crawl build PR cho 6 repo lõi (làm ngay)
```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python -m project3.crawl.gha --repos-file configs\repos_core.txt --event pull_request `
  --days 90 --max-jobs-per-run 2 --max-logs 50000 --root data\crawl_pr *>> data\crawl_pr.log
```
Ước tính khoảng 10 nghìn run fail và khoảng 15–20 nghìn log, mất vài giờ. Chạy nền và theo dõi `data\crawl_pr.log`.
Nếu bị ngắt, chạy lại đúng lệnh trên; crawler sẽ tiếp tục từ chỗ dừng.

### T2. Crawl repo mở rộng (push + PR)
```powershell
uv run python -m project3.crawl.gha --repos-file configs\repos_extra.txt --event push --branches master main trunk `
  --days 90 --max-logs 50000 --root data\validate *>> data\crawl_extra.log
uv run python -m project3.crawl.gha --repos-file configs\repos_extra.txt --event pull_request `
  --days 90 --max-jobs-per-run 2 --max-logs 50000 --root data\crawl_pr *>> data\crawl_extra.log
```
Repo nào lỗi (đổi tên, tắt Actions) thì crawler ghi `LỖI` rồi đi tiếp. Báo lại danh sách các repo đó.

### T3. Kiểm tra và mở rộng luật gán nhãn (phần quan trọng nhất)
1. Chạy `uv run python -m project3.crawl.gold_labels data\crawl_pr` và `... data\validate`.
2. Thống kê nhãn `?` theo repo và workflow. Đọc log của các run `?` (lấy theo `run_id` trong
   `gold_labels.csv`, file log là `logs/<job_id>.txt` của các job fail trong `jobs.jsonl`). Tìm các mẫu lỗi
   chưa có luật rồi thêm regex vào `GOLD_RULES`. Các mẫu nhiều khả năng sẽ gặp với PR:
   - API compatibility (revapi, japicmp): xếp vào `lint`.
   - Gradle `Execution failed for task ':...:compileJava'`, `checkstyleMain`, `spotlessJavaCheck`.
   - Scala/Kotlin compile error.
   - Lỗi license header.
   - Workflow mới cần đưa vào `NON_BUILD_WF`: kiểm tra tiêu đề PR, labeler, bảo mật, benchmark.
3. Giữ đúng thứ tự ưu tiên của luật. Lỗi kết nối chỉ tính là `infra` khi log không có dấu hiệu test fail
   (luật infra "yếu" đứng sau test). Riêng `Could not find artifact` không kèm lỗi mạng thì là `dependency`.
4. **Kiểm chứng độ chính xác:** với mỗi nhãn (compile, lint, dependency, test, infra, flaky), lấy ngẫu nhiên
   20 run (seed cố định), xuất dòng `evidence` cùng khoảng 30 dòng log quanh dòng đó ra
   `data/label_review_<label>.txt`. Tự đọc và đánh giá đúng/sai. Ghi kết quả vào báo cáo.
   Viết script `src/project3/crawl/review_sample.py` cho việc này.

### T4. Tạo tập nhãn cuối
```powershell
uv run python -m project3.crawl.build_log_labels data\validate data\crawl_pr --out data\processed\commits_all.parquet
```

### T5. Đặt lịch crawl hằng tuần
Tạo Windows Task Scheduler chạy `scripts\crawl_weekly.ps1` mỗi tuần, ví dụ:
```powershell
schtasks /Create /SC WEEKLY /D SUN /ST 02:00 /TN project3_crawl `
  /TR "powershell -ExecutionPolicy Bypass -File D:\projects\project3\scripts\crawl_weekly.ps1"
```
Hỏi người dùng trước khi tạo task.

## 4. Tiêu chí hoàn thành

| Chỉ số (đọc từ `commits_all.parquet`) | Mục tiêu |
|---|---|
| Commit fail có `cause = code` | ≥ 2.000 |
| Mỗi nhãn `test`, `compile`, `lint` | ≥ 300 commit fail (dependency, flaky có thể ít hơn) |
| Tỷ lệ `?` trong commit fail | < 5% |
| Độ chính xác khi xem mẫu (T3.4) | ≥ 95% mỗi nhãn |
| Run fail không có log (`.missing` hoặc không tải được) | < 5% |

Chưa đạt thì thêm repo vào `configs/repos_extra.txt`. Chỉ thêm repo Java/JVM dùng Maven/Gradle; chọn từ
`data/processed/apache_candidates.csv` hoặc các repo lớn như apache/flink, apache/hudi, apache/hadoop, apache/beam.

## 5. Bẫy đã biết, không được làm sai

- **Token:** nằm trong `.env` (`GITHUB_ACCESS_TOKEN`). Không in, không log, không commit. `.env` và `data/` đã nằm
  trong `.gitignore`. Không gửi header `Authorization` sang URL Azure Blob (log redirect tới đó): Azure sẽ trả
  0 byte. Code hiện tại đã xử lý đúng chỗ này, đừng sửa lại.
- **Trần 1000 kết quả:** API list run chỉ trả tối đa 1000 run cho một bộ lọc. `list_runs()` đã tự chia đôi
  khoảng thời gian. Đừng thay bằng phân trang `created>=` đơn giản.
- **Rate limit:** 5000 request/giờ. Request list run và job tốn quota; tải log từ Azure thì không.
  `github.py` đã tự chờ khi chạm giới hạn. Lỗi 403 không phải rate limit là lỗi quyền, sẽ raise `PermissionError`.
- **Kho log chậm:** khoảng 30–100 KB/s mỗi kết nối, hay treo. Giữ `LOG_WORKERS = 8`, timeout ngắn, chỉ tải phần
  đuôi. Đừng tải cả file log.
- **PR từ fork:** `pull_requests` rỗng. `build_log_labels` gom các commit cùng PR theo
  `(head_repository, head_branch)`.
- **PR cần duyệt:** run của người mới đóng góp có conclusion `action_required`. Các conclusion khác ngoài
  success/failure (cancelled, skipped...) đã bị bỏ, giữ nguyên như vậy.
- **Job tổng hợp** ("CI result", "... required checks"): log không chứa nguyên nhân lỗi, đã bị bỏ (`AGG_JOB`).
- **Re-run:** lấy job với `filter=latest`, tức lần chạy cuối của run.
- **Lần fail đầu:** push là commit fail mà commit trước trên nhánh chính pass. PR là commit fail mà commit
  trước trong PR pass, hoặc là commit đầu tiên của PR.
- Encoding: luôn đặt `PYTHONIOENCODING=utf-8` (Windows cp1252 sẽ lỗi khi in tiếng Việt).

## 6. Quy ước code

- Python 3.14, quản lý bằng `uv`. Chạy module bằng `uv run python -m project3.crawl.<module>`.
- Comment và docstring tiếng Việt, ngắn. Code gọn, không thêm abstraction thừa, theo phong cách các file sẵn có.
- Không thêm dependency mới nếu không cần (hiện có: requests, duckdb).
- Không commit gì trong `data/`.

## 7. Báo cáo khi xong

Ghi vào `docs/codex/bao-cao-crawl.md`:
1. Bảng theo repo × event: số commit, số fail, % fail, số lần fail đầu, khoảng thời gian.
2. Bảng nhãn: cause / label_group / label, số commit fail, %, số lần fail đầu.
3. Kết quả xem mẫu T3.4: số đúng / 20 cho từng nhãn, kèm ví dụ sai.
4. Các luật đã thêm hoặc sửa trong `GOLD_RULES` / `NON_BUILD_WF`, kèm lý do và một dòng log ví dụ.
5. Các repo lỗi, tỷ lệ log missing, tổng thời gian crawl.
