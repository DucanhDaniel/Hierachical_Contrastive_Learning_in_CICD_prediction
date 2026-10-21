# legacy/

Code và tài liệu không còn dùng trong hướng hiện tại (phân loại loại lỗi SAU CI run từ log).
Giữ để tra cứu và tái lập kết quả cũ. Không bảo trì, không import từ `src/`.
Đường dẫn bên trong giữ nguyên như ở gốc repo, ví dụ `legacy/src/project3/pilot/experiment.py` trước đây là `src/project3/pilot/experiment.py`.
Dữ liệu tương ứng nằm ở `data/legacy/`.

| Nhóm | File | Ghi chú |
|---|---|---|
| Hướng dự đoán trước CI từ diff | `src/project3/pilot/{experiment,hcl_embed,hcl_probe,hcl_train,llm_probe,type_feasibility}.py`, `scripts/kaggle/{hcl_pilot,hcl_full}/` | Kết quả ở `data/legacy/processed/hcl_*`. Chạy lại phải trả dữ liệu từ `data/legacy/processed/` về `data/processed/` |
| GHARuns / nhãn theo tên step | `src/project3/crawl/{analyze,gharuns_*,validate_labels,step_overlap}.py` | |
| Công cụ crawl / rà soát cũ | `src/project3/crawl/{review_dump,review_sample,crawl_report,retry_plan,diff_probe}.py` | Thay bằng chuỗi crawl Kaggle và `pipeline.label_ui` |
| Chọn repo, nguồn dữ liệu phụ | `src/project3/pipeline/{select_repos,probe_repos,ghalogs,compress_data}.py` | Đã tạo xong `configs/repos_100.txt`, `configs/repos_r2.txt` |
| Rà soát quy tắc dependency 18/10 | `scripts/analysis/` | Đã áp dụng, `RULE_VERSION 2026-10-18-dependency-q1q3` |
| Bản quy tắc cũ | `configs/label_rules.v1_*.json`, `v2_*.json`, `label_rules_dependency_proposed.json` | Bản hiện hành: `configs/label_rules.json` |
| Tài liệu cũ | `docs/codex/task-*.md`, `crawl-control.md`, `crawl-100-theo-phien.md`, `bao-cao-crawl.md`, `docs/tong-ket-de-tai-build-failure-hcl.md`, `docs/ke-hoach-thuc-hien.md`, `docs/Slide/W1/script-thuyet-trinh.md` | |

Các script PowerShell crawl cũ (`scripts/crawl_*.ps1`) đã bị xoá. Chúng vẫn còn trong lịch sử git, commit `4654a3b`.
