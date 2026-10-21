# Pipeline dữ liệu: một lệnh, chạy local hoặc Kaggle

Cập nhật 11/10/2026. Mục tiêu: từ danh sách repo ra **dataset chuẩn** (US-30, US-31), tái lập được và chạy tiếp được khi bị ngắt.

## Lệnh

```powershell
# Demo cho hội đồng: 1 repo, 7 ngày, thư mục riêng (khoảng 1 phút)
python -m project3.pipeline.run --repos junit-team/junit-framework --days 7 --workdir data/demo --clones C:/p3data/demo_repos

# Dữ liệu chính sau khi crawl trên Kaggle: bỏ bước crawl, clone tạm ở ổ C
python -m project3.pipeline.run --repos-file configs/repos_100.txt --skip crawl --clones C:/p3data/repos
```

Chạy lại cùng lệnh: repo đã crawl xong và bước có đầu ra mới hơn đầu vào được bỏ qua (AC-30.2). `--only export`
chạy riêng một bước, `--force` chạy lại tất cả.

| Bước | Module | Đầu ra (trong workdir) |
|---|---|---|
| crawl | `crawl.gha` (PR rồi push) | `data/crawl_pr`, `data/validate`: runs/jobs/logs |
| labels | `crawl.gold_labels` | `gold_labels.csv` mỗi root (nhãn + dòng bằng chứng) |
| commits | `crawl.build_log_labels` | `data/processed/commits_all.parquet` |
| fine | `pilot.fine_labels` | `data/processed/fine_labels.parquet` (subtype, module) |
| diffs | `pilot.fetch_diffs` | `data/diffs/<repo>/<sha>.{pr,commit}.diff.gz`, `diffs_all.csv` |
| export | `pipeline.export_dataset` | `data/dataset/`: `commits.parquet`, `coverage.csv`, `manifest.json`, `README.md` |

## Dataset chuẩn (`data/dataset/`)

- **Đơn vị:** một commit trong chuỗi push hoặc một PR. Nhãn 3 tầng, dòng bằng chứng, diff, `rule_version`.
- **Feature lịch sử chỉ dùng quá khứ:** `prev_outcome`, `seq_idx`, `repo_fail_rate_last10` (k=10 theo Rausch et al. 2017).
- **Chia tập sẵn:** `split_time` 70/30 theo thời gian trong từng repo (P1); `repo_fold` 0–4 cố định theo tên repo (P2).
- **Cổng chất lượng** (gắn cờ, không loại): log có/fail build ≥ 0.8, tỉ lệ `?` ≤ 0.3, diff ≥ 0.95, ≥ 20 commit fail do code.
  Run fail không có job nào (workflow lỗi lúc khởi động) đếm riêng, không tính là thiếu log.
- **Tái lập:** `manifest.json` ghi code commit, rule version, cửa sổ crawl từng repo, checksum.

## Chạy trên Kaggle

| Kernel | Việc | Giới hạn | Trạng thái |
|---|---|---|---|
| `p3-crawl` | crawl run/job/log | 5000 request/giờ GitHub | **Đang chạy**, `scripts/kaggle/crawl/chain.sh` tự nối phiên 11 giờ |
| `p3-diff` | clone partial + diff | băng thông git (không cần token) | Chưa làm |
| labels → export | CPU nhẹ | — | Chạy local bằng `pipeline.run --skip crawl diffs` sau mỗi phiên |

Ước tính crawl 85 repo khoảng 200k request, tức khoảng 4 phiên. Hạn dừng crawl 14/10 22:00.

## Vòng gán nhãn

1. Sau mỗi đợt dữ liệu mới: gom cụm `?` (`label_ui clusters`) rồi người gán cụm (`label_ui opencode`, bôi đen đoạn lỗi để tạo regex).
2. Xuất quy tắc (`label_ui rules`), nhờ Codex kiểm tra; **người quyết định** mọi thay đổi nhãn (C-02).
3. Chạy lại `pipeline.run --skip crawl` (tự gán lại nhãn vì rule mới hơn `gold_labels.csv`).
4. Tập kiểm tra mù khoảng 100 run từ repo mới: không dùng để sửa quy tắc, không cho LLM sửa nhãn.
   Điều kiện dừng open coding: ≥ 90% run fail có nhãn quy tắc (theo Rausch et al. 2017).

## Lịch đến buổi duyệt 16/10

| Ngày | Việc |
|---|---|
| 11/10 | Crawl phiên 1; pipeline một lệnh + export (xong); demo 1 repo (xong) |
| 12/10 | Crawl phiên 2–3; kernel diff; báo cáo độ phủ lần 1; mốc 22:00 kiểm tra ≥ 43/85 repo PR |
| 13/10 | Open coding cụm `?` của repo mới |
| 14/10 | Crawl dừng 22:00; gán lại nhãn; lấy mẫu và gán mù tập kiểm tra |
| 15/10 | Đóng băng dataset v1, đưa số liệu vào slide, tập demo |
