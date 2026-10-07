# Tổng kết đề tài: Dự đoán lỗi build CI/CD bằng Hierarchical Contrastive Learning (HCL)

> **Cập nhật 07/10/2026:** chuyển nguồn dữ liệu chính sang **GHARuns** (mục 7). Thử nghiệm trên 6 repo Java của Apache cho thấy bộ này đủ cho hướng HCL: có chuỗi build 5 tháng, 523 ca "lần fail đầu tiên", và gán nhãn loại lỗi tự động được 95% run fail chỉ từ tên step. Cây nhãn được chỉnh theo dữ liệu thật: **compile / test / lint / infra-flaky** (bỏ nhánh dependency vì gần như không có).

## 0. Outline slide giới thiệu đề tài (theo bố cục slide mẫu)

File slide: `docs/Slide/W1/Slide gioi thieu de tai - Build failure HCL.pptx` (15 slide). Script thuyết trình: `docs/Slide/W1/script-thuyet-trinh.md`.

**Slide bìa:** Dự đoán lỗi build CI/CD bằng Hierarchical Contrastive Learning · Sinh viên: Phạm Đức Anh – 20235008 · GVHD: TS Vũ Thị Hương Giang

**Slide nội dung trình bày:**
1. Bối cảnh & định hướng đề tài
2. Vì sao dự đoán pass/fail hiện tại chưa đủ
3. Khảo sát dữ liệu
4. Khảo sát phương pháp
5. Giao thức đánh giá
6. Luồng dự đoán
7. Mô hình HCL
8. Kiến trúc hệ thống
9. Kế hoạch thực hiện

---

### Slide 1. Bối cảnh & định hướng đề tài
- **CI tốn kém:** Google, Mozilla tốn hàng triệu USD/năm; Ubisoft có hàng nghìn build/ngày, mỗi build 10–30 phút; Atlassian mất trung bình 120 giờ build/project/năm vì build fail trên main.
- **Build prediction:** đoán trước khi chạy (chỉ có diff + metadata) để bỏ qua build gần như chắc chắn pass, chạy job rủi ro trước, cảnh báo sớm khi review PR.
- **Phần dễ đã có luật xử lý:** code liên quan không đổi → `paths:` filter, cache của Bazel/Nx, luật CI-skip. **Phần khó là code có thay đổi:** đó là phạm vi của đề tài.
- **Định hướng:** dùng nội dung diff theo cấu trúc phân cấp và dùng **loại lỗi** làm tín hiệu huấn luyện, thay vì chỉ học pass/fail.

### Slide 2. Vì sao dự đoán pass/fail hiện tại chưa đủ
**Các cách hiện tại đạt kết quả tốt vì:**
- Pass chiếm ~87% số build; ~52% số lần fail xảy ra ngay sau một lần fail khác (SmartBuildSkip).
- 76% build lặp lại kết quả build trước (RavenBuild).
- **"Parrot"** (đoán giống lần trước) đạt F1-fail 0,42, trong khi SOTA chỉ 0,48–0,50.

**Nhưng khi dùng thật:**
- Parrot luôn sai ở **lần fail đầu tiên** (xanh → đỏ), đúng chỗ dự đoán có giá trị nhất.
- Nếu build trước đã bị bỏ qua thì **không biết kết quả lần trước**.
- ~60% số ca SOTA không hơn Parrot rõ rệt.
- Chỉ trả lời pass/fail, không nói **hỏng kiểu gì**.

→ Cần mô hình **đọc được nội dung thay đổi**, được đánh giá trên **lần fail đầu tiên**, và có cấu trúc theo **loại lỗi**.

### Slide 2 (tiếp). Kiểm chứng: Parrot so với SOTA
Nguồn: RavenBuild (Sun, Habchi, McIntosh – FSE 2024), Bảng 8–9. In đậm: tốt nhất trong từng bối cảnh. Gain = Benefit − Cost.

| Bối cảnh | Mô hình | F1-fail | Recall-fail | Precision-fail | AUC | Gain |
|---|---|---|---|---|---|---|
| Open-source (22 project) | **Parrot** | .421 | .422 | .420 | .610 | **178.0** |
| | BuildFast | .478 | .583 | .457 | .723 | 124.8 |
| | RavenBuild-CR | **.502** | **.612** | **.489** | **.738** | 156.7 |
| Project X (game AAA, Ubisoft) | **Parrot** | **.657** | **.652** | .662 | .810 | **253.6** |
| | BuildFast | .426 | .296 | **.755** | .791 | 217.8 |
| | RavenBuild | .638 | .607 | .672 | **.877** | 240.1 |

- 76% build open-source lặp lại kết quả build trước (82% build pass, 62% build fail); Project X: 87%.
- BuildFast / RavenBuild thua Parrot ở 38% / 33% trong 92 trường hợp (23 project × 4 độ đo); không hơn Parrot rõ rệt (ngoài biên 5%) ở 64% / 61%.
- SmartBuildSkip (ICSE 2020, 274.742 build, 359 project): 87% build pass, 52% fail là fail liên tiếp; tiết kiệm 30% build, chậm 1 build.
- Atlassian (FSE 2024, 350.037 PR, 1.630 project): tỉ lệ fail gần đây của repo là yếu tố mạnh nhất; 58% developer thấy dự đoán hữu ích, 29% cho là không.
- Flaky Builds (2026, 1.960 project): 3,2% build bị chạy lại, 67,7% trong số đó là flaky.

### Slide 3. Khảo sát dữ liệu
- **GHARuns (2026) – nguồn chính:** 71,7 triệu run GitHub Actions của 46k repo, liên tục 1/2–27/6/2026; có job + step (tên, kết quả) cho run không phải PR.
- **TravisTorrent (2017):** 2,6 triệu build Travis CI, có sẵn trường suy ra loại lỗi (`tr_status`, `tr_tests_failed`); dùng để đối chiếu nghiên cứu cũ. Website gốc đã ngừng (tên miền chuyển hướng sang trang lạ).
- **GHALogs (MSR 2025):** 513k run có log đầy đủ nhưng chỉ 5 run gần nhất/workflow → không có chuỗi build, chỉ dùng để tham khảo log.
- **Dataset GitSense (ISSTA 2024):** build kèm commit artifact, công khai trên Zenodo → baseline so sánh.
- **Tự crawl GitHub API:** chỉ lấy log mẫu của run mới để kiểm chứng nhãn gán theo tên step (log hết hạn sau ~90 ngày).

### Slide 3 (tiếp). Thử nghiệm GHARuns: 6 repo Java của Apache
Build push lên nhánh chính (master/main/trunk), 1/2–27/6/2026. Một commit fail nếu có ít nhất một workflow fail.

| Repo | Commit | Commit fail | Tỉ lệ fail | Lần fail đầu | Workflow / commit |
|---|---|---|---|---|---|
| apache/paimon | 968 | 358 | 37,0% | 186 | 11,2 |
| apache/pinot | 775 | 150 | 19,4% | 107 | 2,2 |
| apache/druid | 400 | 211 | 52,8% | 81 | 2,8 |
| apache/gravitino | 618 | 68 | 11,0% | 58 | 7,8 |
| apache/kafka | 578 | 82 | 14,2% | 54 | 1,0 |
| apache/iceberg | 770 | 56 | 7,3% | 37 | 9,0 |
| **Tổng** | **4.109** | **925** | **22,5%** | **523** | |

- **Gán nhãn tự động (không cần log):** 95% run fail gán được từ tên step fail (1.314 / 1.381). Commit fail: test 72% · compile 18% · lint 4% · infra 2% · chưa gán 4%.
- Nhiều loại lỗi trong một commit → lấy giai đoạn sớm nhất (compile hỏng thì test không chạy).
- Loại 23 commit thuộc đợt fail bất thường (≥ 5 commit fail cùng step trong 1 giờ).
- **Mở rộng được:** 23 repo Apache có ≥ 30 lần fail đầu (13.518 commit, 1.651 ca).
- **Hạn chế:** không có log; run PR không có chi tiết job/step → dự đoán cho build trên nhánh chính.

### Slide 4. Khảo sát phương pháp
- **Luật & metadata (2017):** HW17, Ni & Li. Feature của build hiện tại và build trước.
- **Tiết kiệm chi phí:** SmartBuildSkip (ICSE 2020) chỉ đoán lần fail đầu tiên, rồi coi các lần sau là fail cho tới khi pass; tiết kiệm 30% build, chậm 1 build.
- **Lịch sử & log:** BuildFast (ASE 2020) rút feature theo kiểu lỗi từ log cũ, dùng 2 model tùy build trước pass hay fail; DL-CIBuild dùng LSTM trên chuỗi build.
- **Ngữ cảnh & phụ thuộc:** RavenBuild (FSE 2024): ý định thay đổi, độ liên quan với build trước, mức lan trên đồ thị phụ thuộc.
- **Đọc nội dung:** GitSense (ISSTA 2024): Transformer trên commit message + diff + tên file kết hợp feature thống kê.
- **Bài toán gần (JIT defect):** CC2Vec biểu diễn phân cấp dòng → hunk → file; Zeng et al. (ISSTA 2021): logistic regression chỉ với số dòng thêm vào thắng DeepJIT/CC2Vec.
- **Contrastive phân cấp:** SupCon (NeurIPS 2020), Use All The Labels (CVPR 2022), HGCLR (ACL 2022). **Chưa thấy áp dụng cho build prediction.**

**Đề tài chọn:** encoder phân cấp (hunk → file → commit) + hierarchical contrastive theo cây loại lỗi + feature lịch sử; so sánh với Parrot, logistic regression, XGBoost (feature kiểu BuildFast), GitSense, SupCon một tầng.

### Slide 5. Giao thức đánh giá
| Giao thức | Kiểm tra điều gì | Cách làm |
|---|---|---|
| **P0 · Chia ngẫu nhiên** | Mốc so sánh với nghiên cứu cũ | Train/test cùng phân phối; dễ bị rò rỉ thông tin theo thời gian |
| **P1 · Theo thời gian** | Dùng thật được không | Train giai đoạn đầu, test giai đoạn sau; cửa sổ trượt để đo drift |
| **P2 · Chéo repo** | Khái quát sang repo mới | Train repo A, test repo B; nhóm workflow/job về loại chung |
| **P3 · Lần fail đầu tiên** | Có hơn Parrot thật không | Commit fail ngay sau commit pass (**523 ca / 6 repo**); giả lập không biết kết quả build trước |

Thêm 2 cấu hình input: **chỉ diff** và **diff + lịch sử**, để tách đóng góp của HCL khỏi feature lịch sử.

**Độ đo:** precision/recall/F1 lớp fail, PR-AUC, macro-F1 theo loại lỗi, % build tiết kiệm so với % fail bị bỏ sót, độ trễ phát hiện lỗi (số build).

**Mục tiêu:** không tối ưu ở P0, mà cải thiện ở P1–P3, đặc biệt là P3.

### Slide 6. Luồng dự đoán
- **Offline:** lọc GHARuns (push lên nhánh chính) → gán nhãn theo tên step/job, chia P0–P3 → lấy diff bằng `git clone` + trích embedding (CodeBERT/UniXcoder đóng băng) → train HCL head (loss phân cấp + lịch sử) → chọn model, dựng SHAP explainer.
- **Khi có push/PR:** lấy diff + metadata → encoder phân cấp → xác suất fail + loại lỗi dự kiến → giải thích bằng SHAP (feature) và hunk có attention cao → comment lên PR / gợi ý thứ tự chạy job.

### Slide 7. Mô hình HCL
```
pass | fail
        ├─ compile       (18% commit fail)
        ├─ test          (72%)
        ├─ lint          (4%)
        └─ infra/flaky   (2%)
```
- Tầng 1: pass và fail luôn xa nhau.
- Tầng 2: trong nhóm fail, cùng loại lỗi gom gần nhau hơn.
- Input phân cấp: dòng → hunk → file → commit (attention pooling), ghép thêm feature lịch sử.
- `L = L_cls + λ₁·L_contrast(pass/fail) + λ₂·L_contrast(loại lỗi)`
- Kỳ vọng học được mẫu như: đổi chữ ký public method → compile; đổi logic mà không sửa test → test; sai format/checkstyle → lint.

### Slide 8. Kiến trúc hệ thống
- **Khối thu thập:** GHARuns (Parquet từ Zenodo) + `git clone --filter=blob:none` (diff) + GitHub API (chỉ lấy log mẫu để kiểm chứng nhãn).
- **Khối học máy:** xử lý & gán nhãn bằng DuckDB → encoder phân cấp (đóng băng, giai đoạn 2 thử LoRA) → HCL head → model registry.
- **Khối phục vụ:** FastAPI `/predict` (xác suất fail, loại lỗi) + SHAP; lưu dự đoán và kết quả build thật.
- **Khối tích hợp & hiển thị:** GitHub webhook, bot comment trên PR, dashboard so sánh baseline theo P0–P3.

### Slide 9. Kế hoạch thực hiện
| | Sprint 1 (tuần 1–5) | Sprint 2 (tuần 6–10) | Sprint 3 (tuần 11–14) |
|---|---|---|---|
| **Công việc** | Khảo sát, đề cương; lọc GHARuns + gán nhãn (đã thử 6 repo); lấy diff; baseline Parrot/LR | Baseline XGBoost, CodeBERT, GitSense; encoder phân cấp + hierarchical contrastive loss; mốc quyết định giai đoạn 2 (~tuần 10) | Đánh giá P0–P3, ablation, trực quan hóa embedding; API + bot PR; báo cáo |
| **Sản phẩm** | Dataset commit có nhãn loại lỗi (~4.100 commit, mở rộng tới 23 repo) + kết quả baseline | HCL chạy được, bảng so sánh với các baseline | Demo bot comment trên PR + báo cáo kết quả |

**Slide cuối:** THANK YOU!

---

## 1. Bối cảnh

- **CI/CD build failure prediction**, dùng **Hierarchical Contrastive Learning (HCL)** làm phương pháp.

## 2. Bài toán

Dự đoán một commit đẩy lên **nhánh chính** sẽ làm build pass hay fail **trước khi chạy CI** (chỉ có metadata và diff), và dự đoán thêm loại lỗi.

Lợi ích: tiết kiệm tài nguyên CI (bỏ qua build gần như chắc chắn pass), chạy job rủi ro trước để fail sớm, cảnh báo sớm trước khi merge. Có ý nghĩa rõ nhất khi build đắt và nhiều; với repo nhỏ, build vài phút thì chạy thật vẫn rẻ hơn.

**Phạm vi:**
- **Đơn vị dự đoán là commit:** commit fail nếu làm hỏng ít nhất một workflow. Một commit trên nhánh chính kích hoạt trung bình 1–11 workflow tùy repo. Loại lỗi của commit lấy từ các workflow bị fail.
- **Chỉ xét build trên nhánh chính** (push/merge vào master/main/trunk). Lý do: GHARuns chỉ có chi tiết job/step cho run không phải PR; build hỏng trên main cũng là thứ gây tốn kém nhất (RavenBuild, Atlassian cũng xét bối cảnh này).
- Không nhằm "chắc chắn pass". Mô hình trả xác suất, người dùng chọn ngưỡng. Lỗi bị bỏ sót sẽ lộ ra ở build sau.
- Trường hợp code liên quan không đổi đã có luật xử lý (`paths:`, cache build, CI-skip rules). Đề tài tập trung vào trường hợp **code có thay đổi**.
- Không đoán được mã lỗi cụ thể (chưa chạy thì chưa có log); dừng ở mức loại lỗi.

## 3. Nghiên cứu liên quan

PDF và danh sách đầy đủ ở [papers/](papers/README.md). Tóm tắt những gì các paper đã làm:

| Paper | Cách làm | Điểm cần nhớ |
|---|---|---|
| HW17 (ESEM 2017), Ni & Li (MSR 2017) | ML trên metadata build hiện tại + build trước | Kết quả build trước là feature mạnh nhất |
| SmartBuildSkip (ICSE 2020) | Chỉ đoán lần fail đầu tiên, sau đó coi là fail tới khi pass; không dùng kết quả build trước | 87% build là pass, 52% fail là fail liên tiếp; tiết kiệm 30% build, chậm 1 build |
| BuildFast (ASE 2020) | Feature theo kiểu lỗi từ log cũ, phân tích AST (đổi chữ ký method, import…), `file_fail_prob`; 2 model tùy build trước | F1 lớp fail +47,5% |
| DL-CIBuild (Saidani) | LSTM trên chuỗi build (TravisTorrent) | Có đánh giá online và cross-project |
| RavenBuild (FSE 2024) | Feature ý định, độ liên quan với build trước, mức lan trên đồ thị phụ thuộc | Parrot cạnh tranh được với SOTA → phải dùng làm baseline |
| Al-Sabbagh et al. (PROMISE 2022) | Phân tích text ở mức dòng | Mức file tốt hơn cho build fail (MCC 68% so với 16%) |
| GitSense (ISSTA 2024) | Transformer trên message + diff + tên file + feature thống kê | Gần đề tài nhất; có code và data công khai |
| Atlassian (FSE 2024 Industry) | 350k PR + khảo sát 53 developer | Tỉ lệ fail gần đây của repo quan trọng nhất; developer cần giải thích |
| CC2Vec (ICSE 2020), Zeng et al. (ISSTA 2021) | JIT defect: biểu diễn phân cấp dòng → hunk → file | Mô hình đơn giản (số dòng thêm vào) có thể thắng học sâu |

**Contrastive / HCL:** SupCon (NeurIPS 2020), SimCSE (EMNLP 2021), Use All The Labels (CVPR 2022), HGCLR (ACL 2022), TS2Vec (AAAI 2022).

**Khoảng trống:**
- Trong các paper build prediction đã đọc, không bài nào dùng contrastive learning.
- Tất cả dừng ở pass/fail; loại lỗi chỉ dùng làm feature đầu vào (BuildFast), chưa dùng làm tín hiệu huấn luyện phân cấp.
- Chưa có bài kết hợp biểu diễn phân cấp kiểu CC2Vec cho build prediction. (Cần xác nhận thêm sau khi đọc bản đầy đủ của GitSense.)

Lưu ý: trạng thái build trước đó là feature rất mạnh (Parrot đúng 85–98% trên 6 repo GHARuns). Mô hình phải vượt baseline Parrot/last-status, và nên báo cáo riêng kết quả "chỉ diff" để thấy đóng góp thật của HCL.

## 4. Khái niệm contrastive learning

Học không gian embedding sao cho mẫu giống nhau nằm gần, mẫu khác nhau nằm xa.

- **Anchor / Positive / Negative:** mẫu đang xét / mẫu nên gần / mẫu nên xa.
- **InfoNCE:** tăng cosine giữa anchor và positive, giảm với các negative trong batch. Batch càng lớn càng nhiều negative. **Temperature** quyết định mức khắt khe.
- **Self-supervised (SimCSE):** positive là chính mẫu qua hai lần biến đổi (dropout). Không cần nhãn.
- **Supervised (SupCon):** positive là mọi mẫu cùng nhãn. Đề tài dùng kiểu này.

**Hierarchical:** áp contrastive ở từng tầng nhãn.

```
pass | fail
        ├─ compile
        ├─ test
        ├─ lint
        └─ infra/flaky
```

- Cùng loại lỗi: positive mạnh nhất.
- Khác loại lỗi nhưng cùng "fail": gần ở tầng trên, xa ở tầng dưới.
- Pass và fail: luôn xa.

Loss: `L = L_cls + λ₁·L_contrast(pass/fail) + λ₂·L_contrast(loại lỗi)`

**HCL nằm ở đâu:** HCL không phải một khối trong kiến trúc mà là **hàm mục tiêu huấn luyện**. Cùng một mô hình (encoder + head), chỉ khác loss: cross-entropy thuần → SupCon một tầng → HCL hai tầng. Ba cấu hình này cũng là ablation chính.

Lợi ích so với cross-entropy thường: bền hơn khi mất cân bằng lớp, khái quát tốt hơn giữa các repo, embedding có cấu trúc và trực quan hóa được. Tầng 2 chỉ tính trên mẫu có nhãn loại lỗi, nên dùng được cả dữ liệu chỉ có nhãn pass/fail.

## 5. Các hướng tìm "hierarchy"

- **A. Phân cấp dữ liệu code:** line → hunk → file → commit/PR (nằm ở kiến trúc encoder).
- **B. Phân cấp nhãn lỗi:** pass/fail → loại lỗi (nằm ở hàm loss). Dễ làm và dễ giải thích nhất.
- **C. Phân cấp thời gian/pipeline:** nhiều thang thời gian của lịch sử build; step → job → workflow run.

**Đề xuất: A + B.**

## 6. Hướng tiếp cận kỹ thuật

1. **Biểu diễn commit:** diff → hunk → embedding CodeBERT/UniXcoder (đóng băng, chạy một lần, lưu ra file) → attention pooling (hunk → file → commit).
2. **Ghép feature lịch sử build** dạng bảng vào vector commit.
3. **Huấn luyện:** chỉ train phần head nhỏ (attention pooling + vài lớp MLP) với classification loss + hierarchical contrastive loss. Vì đầu vào là vector đã tính sẵn nên mỗi lần train chỉ vài phút, chạy được trên CPU.
4. **Baseline so sánh:**
   - Parrot/last-status (theo khuyến nghị của RavenBuild).
   - Logistic regression chỉ với số dòng thêm vào (bài học từ Zeng et al.).
   - XGBoost trên khoảng 10 feature dễ lấy (kiểu BuildFast/SmartBuildSkip).
   - GitSense (có code + data công khai), nếu kịp.
   - CodeBERT + cross-entropy, SupCon một tầng (cùng code, chỉ đổi loss).
   - Tất cả chạy lại trên **cùng dữ liệu, cùng cách chia, cùng độ đo**; không so với con số in trong paper khác.
5. **Ablation:** bỏ từng tầng contrastive, bỏ feature lịch sử, bỏ tầng phân cấp code (gộp phẳng cả diff).

### Feature engineering

| Nhóm | Ví dụ | Nguồn | Lấy từ |
|---|---|---|---|
| Lịch sử build | trạng thái build trước, tỉ lệ fail 5 commit gần nhất (của repo), số commit từ lần fail cuối | SmartBuildSkip, Atlassian | GHARuns |
| Kích thước thay đổi | số dòng/file code đổi, số dòng test đổi | SmartBuildSkip | git |
| Loại thay đổi | đổi chữ ký method, thêm/xóa import, sửa `pom.xml`/`build.gradle`/workflow YAML | BuildFast | git |
| Lịch sử file | `file_fail_prob` (tỉ lệ fail của các commit từng đụng file này) | BuildFast | git + GHARuns |
| Liên quan build trước | cùng thư mục với commit trước không, ý định commit (fix/feature/refactor) | RavenBuild | git |
| Developer | kinh nghiệm trong repo, tỉ lệ fail lịch sử | BuildFast | git + GHARuns |
| Ngữ cảnh | ngày/giờ, số workflow bị kích hoạt | BuildFast | GHARuns |
| Nội dung diff | embedding phân cấp hunk → file → commit, commit message | Đề tài (HCL) | git |

## 7. Dữ liệu: GHARuns (nguồn chính)

**GHARuns** (Talebzadeh Bardsiri, Mens, Decan – Đại học Mons, 2026; Zenodo [10.5281/zenodo.20427454](https://doi.org/10.5281/zenodo.20427454)): 71,7 triệu workflow run của 45.989 repo GitHub Actions (≥ 100 sao), liên tục 1/2–27/6/2026. Ba bảng Parquet:

| File | Kích thước | Nội dung |
|---|---|---|
| `runs.parquet` | 1,44 GB | Mỗi run: `repository`, `path` (workflow), `event`, `head_sha`, `head_branch`, `run_attempt`, `conclusion`, thời gian |
| `jobs.parquet` | 1,61 GB | Mỗi job: `name`, `conclusion` (chữ hoa: `FAILURE`), nối với run qua `check_suite_id` |
| `steps.parquet` | 5,73 GB | Mỗi step: `name`, `conclusion`, nối với job qua `job_id` |

Đã tải về `data/gharuns/` (bỏ qua git). Chi tiết job/step **không có cho run pull request**.

### Quy trình xử lý (đã cài trong `src/project3/crawl/`)

1. **Chọn repo:** `apache_candidates.csv` xếp hạng repo Apache theo số lần fail đầu (23 repo có ≥ 30 ca). Hiện thử 6 repo Java: Paimon, Pinot, Druid, Gravitino, Kafka, Iceberg.
2. **Lọc:** `event = 'push'`, `head_branch` ∈ {master, main, trunk}, `conclusion` ∈ {success, failure}.
3. **Gán nhãn từng run fail** (`gharuns_label.py`):
   - Tầng 1: tên **step fail**, bỏ step/job tổng hợp (`CI checks completed`, `*-required`, `Check ... result`).
   - Tầng 2: nếu step chung chung thì dùng tên **job fail**.
   - Step setup/hạ tầng (`Set up job`, checkout, setup-java, cache, download…) → **infra**.
   - Luật theo từ khóa: lint (lint, checkstyle, spotless, static check…) → test (test, junit, integration…) → compile (build, compile, packaging…). Từ khóa test được xét trước "build" để `build / JUnit tests` thành test.
4. **Đợt fail bất thường:** ≥ 5 commit khác nhau cùng fail ở một step trong 1 giờ → **đánh dấu loại** khỏi train/đánh giá. (Không xét theo số workflow, vì một commit hỏng tự nhiên fail ở nhiều workflow cùng lúc.)
5. **Gộp theo commit:** commit fail nếu có workflow fail. Nhiều loại lỗi → lấy giai đoạn sớm nhất: compile → lint → test → infra.
6. **Lần fail đầu tiên:** commit fail mà commit liền trước (theo thời gian, cùng repo) pass.
7. **Diff:** `git clone --filter=blob:none` từng repo, `git show <head_sha>`; commit message và tác giả lấy từ `git log`.

Kết quả lưu ở `data/processed/commits.parquet`.

### Kết quả thử trên 6 repo

- 4.109 commit, 925 commit fail (22,5%), **523 lần fail đầu**, 23 commit thuộc đợt bất thường.
- Run fail: 1.381; có job fail: 1.370; có step fail: 1.365. **Gán nhãn từ step: 95%.**
- Nhãn commit fail (đã loại đợt bất thường): test 654 (72%), compile 161 (18%), lint 35 (4%), infra 16 (2%), dependency 2, chưa gán 34 (4%).
- Parrot (theo workflow, push nhánh chính) đúng 85–98% tùy repo.
- Chỉ 23 run success ở lần chạy lại (dấu hiệu flaky) → tín hiệu flaky yếu trong GHARuns.

### Kiểm chứng nhãn bằng log thật (07/10/2026) → đổi cách lấy nhãn loại lỗi

**Nhãn gán theo tên step (cách dùng cho GHARuns) không đủ tin cậy.** Đã crawl 90 ngày gần nhất (9/7–7/10/2026) kèm log cho cùng 6 repo, tạo **nhãn chuẩn từ log** (`gold_labels.py`) và so sánh:

- Nhãn chuẩn đọc dòng lỗi trong log theo thứ tự nguyên nhân gốc: compile → lint → infra (không tải được dependency/plugin, runner tắt, action timeout) → flaky → test → infra yếu (lỗi kết nối, chỉ khi không có dấu hiệu test fail). `Could not find artifact` không kèm lỗi mạng → **dependency** (vd. commit nâng lên version chưa phát hành).
- Bỏ job tổng hợp (`CI result`, `Check Dependency Outcomes`, `*-required`) và workflow không phải build (cherry-pick, cập nhật test catalog, quét CVE/Trivy).
- Kiểm tra tay 2 mẫu ngẫu nhiên (45 + 40 nhãn): sau khi sửa 2 lỗi luật (`Rat check` quá rộng, ưu tiên lỗi kết nối), mẫu thứ hai **39/40 đúng chắc chắn**, 1 ca mơ hồ (action timeout 60 phút: runner chậm hay test treo).
- **So với nhãn chuẩn, nhãn theo tên step chỉ đúng 59%** (415/709 run). Sai chủ yếu vì:
  - Lỗi hạ tầng nằm trong step build/test (173 run): Maven Central trả **429 Too Many Requests** / 503, `Connection reset`, không tải được plugin.
  - Step tên "lint" chạy cả test (Paimon `lint-python.sh`), lỗi compile trong step chạy test (Druid `run_unit-tests`).
  - Đọc YAML workflow không sửa được các lỗi này (lệnh vẫn là `mvn test`).
- Tên step thay đổi theo thời gian: chỉ ~42% tên step fail trong GHARuns còn xuất hiện ở dữ liệu hiện tại (Paimon 17% vì đã gộp workflow thành `CI`).

**Tập nhãn cuối từ log** (`build_log_labels.py` → `data/processed/commits_logs90.parquet`):

| Repo | Commit | Commit fail | Tỉ lệ fail | Lần fail đầu |
|---|---|---|---|---|
| apache/paimon | 1.024 | 252 | 24,6% | 172 |
| apache/druid | 634 | 183 | 28,9% | 113 |
| apache/iceberg | 545 | 31 | 5,7% | 20 |
| apache/gravitino | 505 | 47 | 9,3% | 40 |
| apache/pinot | 411 | 74 | 18,0% | 63 |
| apache/kafka | 370 | 64 | 17,3% | 45 |
| **Tổng** | **3.489** | **651** | **18,7%** | **453** |

| Loại lỗi (commit fail) | Số commit | Tỉ lệ | Lần fail đầu |
|---|---|---|---|
| test | 384 | 59,0% | 277 |
| infra | 135 | 20,7% | 103 |
| compile | 21 | 3,2% | 8 |
| lint | 13 | 2,0% | 5 |
| dependency | 8 | 1,2% | 1 |
| flaky | 4 | 0,6% | 3 |
| chưa rõ (log không đủ thông tin) | 86 | 13,2% | 56 |

**Hệ quả cho thiết kế:**
- **~21% commit fail là do hạ tầng**, không do code → không thể dự đoán từ diff. Cần tách riêng (loại khỏi lớp "fail do code" hoặc thành nhánh riêng trong cây nhãn), nếu không mô hình học nhiễu.
- Nhãn loại lỗi **chỉ lấy từ log** (dữ liệu 90 ngày). GHARuns chỉ dùng cho nhãn pass/fail và feature lịch sử; nhưng lưu ý pass/fail của GHARuns cũng lẫn ~20% fail do hạ tầng mà không lọc được.
- Compile/lint/dependency hiếm (~6% tổng) → cây nhãn nên đổi thành: **pass | fail → {do code: test, build (compile/lint/dependency)} | {do môi trường: infra, flaky}**.

### Vai trò của crawler GitHub API

`gha.py` (đọc `GITHUB_ACCESS_TOKEN` trong `.env`) giờ chỉ dùng để **lấy log của một mẫu run mới**, nhằm đo độ chính xác của nhãn gán theo tên step (thay cho gán tay). Lưu ý:
- Token cần scope **`public_repo`** mới tải được log (không có scope thì GitHub trả "Must have admin rights").
- Log và cả danh sách step của run cũ đều bị GitHub xóa sau vài tháng, nên chỉ lấy được cho run gần đây.
- Thử crawl Superset (1–6/10/2026): 17.154 run, fail 3%, gán nhãn từ tên step 82%. Phát hiện step `Setup Python` fail hàng loạt (380 lần) → lý do cần bước lọc đợt bất thường.

### Các bộ dữ liệu khác đã xem

| Bộ | Vì sao không làm nguồn chính |
|---|---|
| TravisTorrent (2017) | Cũ, Travis CI; website gốc đã ngừng. Dùng nếu muốn đối chiếu nghiên cứu cũ |
| GHALogs (MSR 2025) | Chỉ 5 run gần nhất/workflow → không có chuỗi build |
| Flaky Builds (2026) | 4,86M build nhưng chưa thấy link tải hàng loạt |
| GitSense data (ISSTA 2024) | Không có nhãn loại lỗi; dùng làm baseline |
| GADFPD (2026) | Không có diff |
| BUMP, LogChunks, BugSwarm | Cặp fail/pass nhỏ; dùng làm đáp án kiểm tra bộ gán nhãn nếu cần |

## 8. Đánh giá

Chi tiết 4 giao thức P0–P3 ở Slide 5 (mục 0).

- **Chia train/test theo thời gian** (2–6/2026), không chia ngẫu nhiên (tránh leakage). Chia ngẫu nhiên chỉ để so với nghiên cứu cũ.
- **Báo cáo riêng lần fail đầu tiên** (523 ca trên 6 repo, ~1.650 ca nếu mở rộng 23 repo): đây là chỗ Parrot luôn sai và là nơi HCL cần chứng minh.
- **Giả lập không biết kết quả build trước** (build đó đã bị bỏ qua), như SmartBuildSkip chỉ ra.
- Mất cân bằng lớp: tỉ lệ fail 7–53% tùy repo; loại lỗi lệch về test (72%). Dùng F1 lớp fail, PR-AUC và macro-F1 theo loại lỗi; sampler cân bằng theo lớp khi train contrastive.
- Đánh giá cross-project (train repo A, test repo B).
- Chỉ số thực tiễn: % build tiết kiệm được so với % fail bị bỏ sót, độ trễ phát hiện lỗi (số commit).
- Concept drift: đánh giá theo cửa sổ thời gian trượt.
- Loại commit thuộc đợt fail bất thường khỏi tập đánh giá chính.
- Trực quan hóa embedding (t-SNE/UMAP) để thấy cụm theo loại lỗi.

## 9. Kế hoạch hai giai đoạn (đã thống nhất)

Không có GPU được cấp, nên chia hai giai đoạn.

### Giai đoạn 1: HCL đơn giản (bắt buộc xong)
- Lọc GHARuns, gán nhãn loại lỗi (đã có script), lấy diff bằng git, dựng baseline.
- **Trích embedding một lần** bằng CodeBERT/UniXcoder (đóng băng) trên Colab/Kaggle, lưu ra Parquet/numpy.
- Train head nhỏ (attention pooling + MLP) với hierarchical contrastive loss. Mỗi lần chạy vài phút, chạy được trên Colab hoặc CPU.
- Phần "HCL" thực chất chỉ là hàm loss khoảng 40–100 dòng code (gọi SupCon ở từng tầng nhãn rồi cộng có trọng số).
- Ablation đầy đủ, cross-project, trực quan hóa embedding.

### Giai đoạn 2: Training HCL nặng (thử cải thiện)
- Fine-tune encoder bằng **LoRA**, chỉ chạy 2–3 cấu hình chính, so với giai đoạn 1.
- Chạy trên Kaggle (2×T4, ~30h/tuần) hoặc thuê GPU theo giờ (RunPod/Vast.ai, ~0.3–1 USD/giờ; ước lượng 30–50 giờ ≈ 15–25 USD).
- Kỹ thuật giảm chi phí: mixed precision, gradient checkpointing, GradCache, đóng băng phần lớn encoder, encoder nhỏ, cắt ngắn input, thử trên 10–20% dữ liệu trước.
- Khó khăn: cần batch lớn (256–1024), nhạy siêu tham số (temperature, learning rate, λ), dễ collapse, ablation nhân chi phí.

### Nguyên tắc
- **Mốc quyết định ~tuần 10:** nếu giai đoạn 1 chưa xong ablation thì bỏ giai đoạn 2, tập trung viết báo cáo.
- Báo cáo giai đoạn 2 là "thử nghiệm mở rộng", không phải đóng góp chính. Kết quả âm có phân tích vẫn hợp lệ.
- Giai đoạn 1 đã đủ là một đóng góp hoàn chỉnh. Nói rõ điều này với cô.

## 10. Về Colab

- Phù hợp: trích embedding (GPU T4, lưu từng batch ra Drive), train head nhỏ.
- Không phù hợp: xử lý GHARuns (vài GB Parquet, dùng DuckDB trên máy cá nhân), clone repo lấy diff, XGBoost. Chạy ở máy cá nhân rồi đưa Parquet đã lọc lên Drive.
- Lưu ý: phiên bị ngắt, GPU không đảm bảo (Colab Pro ~10 USD/tháng đỡ hơn), code phải resumable, cố định seed và log cấu hình (W&B hoặc CSV), giới hạn 256–512 token/hunk và số hunk/commit.
- Kaggle ổn định hơn cho các lần chạy dài.

## 11. Phân bổ khối lượng công việc

| Phần | Tỷ trọng | Ghi chú |
|---|---|---|
| Lọc GHARuns, gán nhãn, lấy diff, kiểm chứng nhãn | ~25% | Giảm nhiều so với tự crawl; script gán nhãn đã có |
| Feature engineering + baseline (Parrot, LR, XGBoost) | ~20% | Dễ |
| Trích embedding (batch job) | ~10% | Dễ |
| Train HCL head + ablation | ~25% | Phần chính |
| Báo cáo, trực quan hóa, demo | ~20% | — |

## 12. Lịch trình gợi ý (~14 tuần)

| Tuần | Việc |
|---|---|
| 1–2 | Đọc paper, chốt hierarchy (A+B), viết đề cương; **đã thử GHARuns trên 6 repo** |
| 3–5 | Chốt danh sách repo (10–20), gán nhãn, lấy diff, kiểm chứng nhãn bằng log mẫu; baseline Parrot/LR |
| 6–7 | Baseline XGBoost, CodeBERT + cross-entropy |
| 8–10 | Cài HCL: encoder phân cấp + hierarchical contrastive loss |
| ~10 | **Mốc quyết định có làm giai đoạn 2 hay không** |
| 11–12 | Ablation, cross-project, trực quan hóa embedding |
| 13–14 | Viết báo cáo, demo (bot comment xác suất fail trên PR, kèm SHAP) |

## 13. Rủi ro

- Feature lịch sử build có thể chiếm phần lớn hiệu năng (Parrot đúng 85–98%): báo cáo riêng kết quả "chỉ diff" và P3.
- HCL có thể không vượt baseline: vẫn báo cáo trung thực kèm phân tích và ablation.
- **Nhãn loại lỗi lệch về test (72%)**, nhánh lint và infra ít mẫu: dùng sampler cân bằng, báo cáo macro-F1; có thể thêm repo hay gặp lỗi compile/lint.
- **Nhãn gán theo tên step có thể sai**: kiểm chứng trên log mẫu của run mới; báo cáo độ chính xác của bộ gán nhãn.
- **Đợt fail bất thường** (sự cố hạ tầng chung) làm nhiễu nhãn: đã có bước phát hiện và loại.
- Một số commit cũ có thể không còn lấy được diff (force-push, repo đổi tên): bỏ các commit này và ghi rõ tỉ lệ.
- Dữ liệu chỉ có build trên nhánh chính: không dự đoán cho từng commit trong PR; ghi rõ trong phạm vi.
- Fine-tune nặng tốn GPU: chỉ làm khi giai đoạn 1 đã vững.

## 14. Việc cần làm tiếp

1. Hỏi cô: phạm vi (10–20 repo Java, dự đoán cho build trên nhánh chính, 6 baseline, giao thức P1 + P3) đã đủ chưa; có hỗ trợ GPU không.
2. Soạn đề cương nộp cô (mục tiêu, câu hỏi nghiên cứu, phương pháp, kế hoạch hai giai đoạn).
3. Chốt danh sách repo từ `data/processed/apache_candidates.csv` (ưu tiên repo Java có nhiều lần fail đầu).
4. Viết bước lấy diff: clone repo, `git show` theo `head_sha`, tách hunk/file, tính feature thay đổi.
5. Thêm scope `public_repo` cho token, lấy log mẫu của run mới để đo độ chính xác của nhãn theo tên step.
6. Lấy PDF GitSense, BuildFast, DeepJIT, Zeng et al. qua thư viện trường; đọc kỹ GitSense để xác nhận khoảng trống.
7. Notebook trích embedding và code hierarchical contrastive loss.
