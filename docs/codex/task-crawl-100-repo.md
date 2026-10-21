# Task: Crawl mở rộng lên 100 repo trước buổi duyệt (thứ 6, 16/10/2026)

## 1. Bối cảnh và hạn chót

Hội đồng yêu cầu dữ liệu ở quy mô **"ba con số"** (≥ 100 repo), có **code diff + log thật**, nhãn từ **bộ quy tắc**
(không dùng LLM), và **demo pipeline tự động** ở buổi duyệt thứ 6, 16/10/2026.

Hiện có 17 repo trong `configs/repos_core.txt` + `configs/repos_extra.txt`. Task này crawl thêm **85 repo** trong
`configs/repos_100.txt` (chọn bằng `src/project3/pipeline/select_repos.py`; tiêu chí và lý do từng repo ở
`data/processed/repo_selection.csv`).

| Mốc | Việc |
|---|---|
| **Hôm nay, 10/10** | Bắt đầu T1 (log hết hạn sau 90 ngày, mỗi ngày chậm là mất một ngày dữ liệu) |
| **Thứ 4, 14/10, 22:00** | **Dừng crawl** dù chưa xong. Repo nào xong thì dùng repo đó |
| Thứ 5, 15/10 | T3–T5: gán nhãn, gộp commit, báo cáo; Claude lấy diff và làm thống kê cho slide |

`configs/repos_100.txt` đã **xếp theo khối lượng tăng dần**: chạy tuần tự từ đầu file để nếu hết giờ vẫn có nhiều repo nhất.

## 2. Ước tính chi phí

- 17 repo cũ: khoảng 18 nghìn run fail, crawl + gán nhãn mất khoảng 5,7 giờ.
- 85 repo mới: dự kiến 80–120 nghìn run fail. Mỗi run fail tốn ít nhất 1 request list job, nên quota GitHub
  (5.000 request/giờ, 1 token) là giới hạn chính: **khoảng 25–35 giờ**. Tải log từ Azure không tốn quota nhưng chậm.
- Nếu đến **thứ 2, 12/10, 22:00** mà chưa xong một nửa số repo, giảm `--days 90` xuống `--days 60` cho các repo còn lại
  và báo lại.

## 3. Việc cần làm

### T1. Crawl PR (ưu tiên, vì lỗi compile/lint chủ yếu nằm ở PR)
```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python -m project3.crawl.gha --repos-file configs\repos_100.txt --event pull_request `
  --days 90 --max-jobs-per-run 2 --max-logs 50000 --root data\crawl_pr *>> data\crawl_100_pr.log
```

### T2. Crawl push lên nhánh chính
```powershell
uv run python -m project3.crawl.gha --repos-file configs\repos_100.txt --event push `
  --branches master main trunk develop --days 90 --max-logs 50000 --root data\validate *>> data\crawl_100_push.log
```
T1 và T2 ghi vào hai root khác nhau nên có thể chạy song song, nhưng chúng **dùng chung quota token**. Nếu thấy
rate limit liên tục thì chạy tuần tự (T1 trước).

Có thể dùng lại khung `scripts/crawl_expand.ps1` / `crawl_control.ps1` (state, PID, retry). Lưu ý: các file
`data/*.pid`, `data/*_state.json` của đợt trước đã được xoá khi dọn thư mục; log cũ nằm trong `data/logs/`.

### T3. Gán nhãn và mở rộng quy tắc cho repo mới
```powershell
uv run python -m project3.crawl.gold_labels data\crawl_pr
uv run python -m project3.crawl.gold_labels data\validate
```
Repo mới có nhiều Kotlin/Android và nhiều tổ chức ngoài Apache. Thống kê nhãn `?` theo repo × workflow và thêm quy tắc
cho các mẫu chưa có, ví dụ:
- Kotlin compile `e: file:///...kt:12:5`, Gradle `Compilation error. See log for more details`
- Lint: `ktlint`, `detekt`, Android `Lint found errors`, `spotlessKotlinCheck`, `Checkstyle`, `PMD`, `SpotBugs`,
  `Error Prone`, `forbiddenApis`
- Test: `There were failing tests`, `Tests failed`, `FAILURE: Build failed with an exception` + task `:test`
- Workflow không phải build cần đưa vào `NON_BUILD_WF` (release, docs, labeler, CodeQL, stale, translation…)

**Sửa quy tắc theo kết quả kiểm chứng bằng người** (`docs/khung-nhan-loi-build.md` mục 5, danh sách lỗi cụ thể ở
`data/human_labels/rule_errors.csv`): siết RAT, tách dependency khỏi infra khi không có dấu hiệu mạng, thêm loại buildconfig
và doc theo khung của Rausch et al. (MSR 2017), thêm mẫu sbt/ScalaTest/MiMa/Android. Sau khi sửa, báo lại để Claude đo lại
precision trên tập người gán (220 run).

Giữ nguyên thứ tự ưu tiên và nguyên tắc: **không đoán nhãn**; không khớp quy tắc thì để `?`. Mọi quy tắc mới ghi lại
trong báo cáo (nhãn, regex, ví dụ dòng log).

### T4. Gộp commit
```powershell
uv run python -m project3.crawl.build_log_labels data\validate data\crawl_pr --out data\processed\commits_all.parquet
```

### T5. Báo cáo độ phủ (cho slide)
Cập nhật `docs/codex/bao-cao-crawl.md`, thêm:
1. Bảng theo repo: số run, số commit, commit fail, % fail, lần fail đầu, % commit fail còn log, % nhãn `?`.
2. Bảng nhãn tầng 2 tổng và theo ngôn ngữ (Java / Kotlin / Groovy).
3. Danh sách repo lỗi hoặc bỏ dở (đổi tên, tắt Actions, hết giờ) kèm lý do.
4. Danh sách quy tắc mới thêm.

**Không** tự đánh giá đúng/sai nhãn thay cho người. Tập kiểm chứng do người dùng tự gán tay (công cụ Claude làm riêng).

## 4. Phần Claude làm (không cần Codex)

- Lấy diff cho commit của repo mới (`pilot/fetch_diffs.py`, diff giờ lưu dạng `.diff.gz`). Ổ D chỉ còn khoảng 24 GB nên
  clone và diff của repo mới để ở ổ C.
- Pipeline một lệnh + demo, công cụ gán tay mù, thống kê và slide.

## 5. Bẫy đã biết

Xem mục 5 của `docs/codex/task-crawl-mo-rong-du-lieu.md` (token, trần 1000 kết quả, rate limit, kho log chậm, PR từ fork,
`action_required`, job tổng hợp, re-run). Thêm:
- Repo ngoài Apache có thể dùng nhánh chính tên `develop`; đã thêm vào `--branches`.
- Không in, không log token. Không commit gì trong `data/`.
