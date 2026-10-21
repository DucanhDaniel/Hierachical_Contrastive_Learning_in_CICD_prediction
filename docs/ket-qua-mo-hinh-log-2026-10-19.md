# Mô hình đọc log (UniXcoder, CE và HCL) so với TF-IDF — 19/10/2026

Bước 3 trong [huong-moi-phan-loai-sau-ci.md](huong-moi-phan-loai-sau-ci.md). Baseline: [ket-qua-baseline-log-2026-10-18.md](ket-qua-baseline-log-2026-10-18.md).

- **Mô hình nơ-ron:**
  - Code: [log_hcl.py](../src/project3/pilot/log_hcl.py); dữ liệu đóng gói bằng [log_pack.py](../src/project3/pipeline/log_pack.py).
  - Chạy trên kernel `p3-log-hcl`; kết quả ở `data/results/log_model/v2/`.
- **TF-IDF so sánh công bằng:**
  - Code: [log_baselines_fair.py](../src/project3/pilot/log_baselines_fair.py).
  - Kết quả: `data/results/log_baselines/fair.json`.
- **Cách chia:**
  - 5 fold chéo repo; với fold k: test = k, val = k+1, train = 3 fold còn lại.
  - 1 seed, 2 epoch, che bằng chứng ở 50% mẫu train.

## Các cấu hình TF-IDF

| Cấu hình | Train | Đầu vào |
|---|---|---|
| A | 3 fold | 30.000 ký tự cuối |
| B | 3 fold | đúng 8 đoạn mô hình thấy |
| C | 3 fold | B + chuỗi workflow/job/step, tức đúng thông tin mô hình có |

## Macro-F1, trung bình 5 fold

| Mô hình | Lá | Tầng 2 | Tầng 1 | Lá, đã che | Tầng 2, đã che | Tầng 1, đã che |
|---|---:|---:|---:|---:|---:|---:|
| TF-IDF A | 0,560 | **0,742** | **0,877** | 0,479 | **0,670** | **0,831** |
| TF-IDF B | 0,523 | 0,678 | 0,830 | 0,443 | 0,616 | 0,779 |
| TF-IDF C | 0,535 | 0,676 | 0,831 | 0,459 | 0,617 | 0,782 |
| UniXcoder CE | 0,525 | 0,684 | 0,809 | 0,461 | 0,630 | 0,782 |
| UniXcoder HCL | 0,537 | 0,685 | 0,826 | 0,459 | 0,634 | 0,789 |

## Tầng 2 theo fold (test nguyên vẹn / đã che)

| Fold | CE | HCL | TF-IDF C |
|---|---|---|---|
| 0 | 0,644 / 0,600 | 0,629 / 0,583 | 0,570 / 0,517 |
| 1 | 0,668 / 0,626 | 0,685 / 0,643 | 0,708 / 0,653 |
| 2 | 0,572 / 0,588 | 0,675 / 0,706 | 0,701 / 0,682 |
| 3 | 0,819 / 0,665 | 0,815 / 0,639 | 0,774 / 0,660 |
| 4 | 0,716 / 0,672 | 0,623 / 0,600 | 0,629 / 0,571 |

## Nhận xét

1. **Với cùng đầu vào (so với C), mô hình nơ-ron hơn TF-IDF một chút:**
   - Tầng 2: khoảng +0,01 trên test nguyên vẹn, +0,015 trên test đã che.
   - Mức chênh nhỏ hơn biến động giữa các fold (±0,1).
2. **HCL ≈ CE:**
   - Chênh 0,001 trên test nguyên vẹn và 0,004 trên test đã che ở tầng 2; HCL hơn CE 0,017 ở tầng 1.
   - Dấu hiệu "HCL hơn" thấy trên fold 0–2 không còn khi tính đủ 5 fold: fold 2 HCL hơn nhiều, nhưng fold 4 thua nhiều.
   - Kết quả này khớp với kết quả HCL trên diff trước đây.
3. **Nút thắt là lượng log đọc được:**
   - Từ A sang B, tầng 2 giảm 0,064 trên test nguyên vẹn và 0,054 trên test đã che.
   - TF-IDF đọc toàn bộ đuôi log (A) vẫn tốt nhất.
4. Với 1 seed, chưa thể kết luận thứ tự giữa CE, HCL và TF-IDF C.

## Việc tiếp theo (chưa duyệt)

- Mở rộng đầu vào lên khoảng 16 đoạn × 384 token, và/hoặc kết hợp đặc trưng TF-IDF A với embedding.
- Chạy thêm seed (≥3) để đo phương sai.
- Thêm nhánh diff: log, diff, log + diff.

## Mô hình lai: UniXcoder + xác suất TF-IDF (chạy 19/10, kết quả ở `data/results/log_model/v3_tfidf/`)

- **Nhánh thêm:** log xác suất lá của TF-IDF A (30.000 ký tự cuối) -> 64 số, ghép cùng r và ngữ cảnh trước MLP (`log_hcl --tfidf`).
- **Đặc trưng theo kiểu stacking** ([tfidf_feats.py](../src/project3/pilot/tfidf_feats.py)):
  - Run train: xác suất out-of-fold (TF-IDF fit trên 2 fold train còn lại, chia theo repo).
  - Run val/test: TF-IDF fit trên cả 3 fold train.
  - Kiểm tra: argmax của xác suất trên fold test khớp đúng điểm TF-IDF A.

### Macro-F1, trung bình 5 fold, cùng cách chia, 1 seed

| Mô hình | Lá | Tầng 2 | Tầng 1 | Lá, đã che | Tầng 2, đã che | Tầng 1, đã che |
|---|---:|---:|---:|---:|---:|---:|
| TF-IDF A | 0,560 | 0,742 | 0,877 | 0,479 | 0,670 | 0,831 |
| UniXcoder CE | 0,525 | 0,684 | 0,809 | 0,461 | 0,630 | 0,782 |
| UniXcoder HCL | 0,537 | 0,685 | 0,826 | 0,459 | 0,634 | 0,789 |
| **Lai CE** | **0,591** | **0,742** | **0,882** | **0,515** | **0,678** | 0,849 |
| Lai HCL | 0,590 | 0,741 | **0,882** | 0,506 | 0,673 | **0,852** |

Tầng 2 theo fold (nguyên vẹn / đã che), lai CE: 0,711/0,634 · 0,745/0,713 · 0,717/0,695 · 0,863/0,710 · 0,673/0,640.

### Nhận xét

1. **Mô hình lai không thua thành phần nào và hơn rõ ở mức lá:**
   - Mức lá: +0,031 so với TF-IDF A trên test nguyên vẹn, +0,036 trên test đã che.
   - Tầng 1: +0,005 trên test nguyên vẹn, +0,02 trên test đã che.
   - Tầng 2: bằng TF-IDF A trên test nguyên vẹn, +0,008 trên test đã che.
   - So với UniXcoder thuần: tầng 2 +0,06, mức lá +0,05 đến +0,07.
2. **Hai nguồn bổ sung cho nhau:**
   - TF-IDF đọc được toàn bộ đuôi log.
   - Encoder đọc kỹ các đoạn cuối và ngữ cảnh CI.
   - Phần lợi tập trung ở lá, đúng là tầng mà mô hình chỉ dùng TF-IDF yếu nhất.
3. **HCL vẫn ≈ CE** (chênh ≤0,009), nhất quán với các lần trước.
4. **Lá hiếm vẫn gần 0** (license, doc, flaky). Fold 0, HCL lai, test đã che: license 0,08, doc 0,20.
5. **Giới hạn:** chỉ 1 seed. Fold 4 thì lai CE (0,673) thua TF-IDF A (0,723) trên test nguyên vẹn.

## Thử nghiệm lá hiếm: sampler theo lớp + mượn trọng số loại cha (20/10, `data/results/log_model/v4_rare/`)

- **Thiết lập:** `log_hcl --tfidf --sampler mpc --share-parent`.
  - Sampler `mpc`: batch = 6 lá × 2 run, lá chọn với xác suất ~ √(số mẫu); bỏ trọng số lớp trong CE.
  - `--share-parent`: trọng số đầu lá = trọng số loại cha ở tầng 2 + độ lệch (phạt L2 1e-3).
  - Hai thay đổi bật cùng lúc. 1 seed, 5 fold.

### Macro-F1 trung bình 5 fold (nguyên vẹn / đã che)

| Mô hình | Lá | Tầng 2 | Tầng 1 |
|---|---|---|---|
| TF-IDF A | 0,560 / 0,479 | 0,742 / 0,670 | 0,877 / 0,831 |
| Lai CE | 0,591 / 0,515 | 0,742 / 0,678 | 0,882 / 0,849 |
| Lai HCL | 0,590 / 0,506 | 0,741 / 0,673 | 0,882 / 0,852 |
| Lai + mpc CE | 0,574 / 0,503 | 0,733 / 0,682 | 0,856 / 0,821 |
| **Lai + mpc HCL** | **0,595 / 0,527** | **0,741 / 0,692** | 0,847 / 0,823 |

### F1 theo lá (gộp dự đoán 5 fold, test nguyên vẹn; lá xếp theo số mẫu giảm dần)

| Mô hình | testfailure | compile | itestfailure | dependency | infra | license | buildconfig | git | doc |
|---|---|---|---|---|---|---|---|---|---|
| Lai CE | 0,87 | 0,93 | 0,72 | 0,76 | 0,21 | 0,80 | 0,66 | 0,35 | 0,33 |
| Lai HCL | 0,82 | 0,89 | 0,66 | 0,70 | 0,22 | 0,78 | 0,76 | 0,57 | 0,47 |
| Lai + mpc CE | 0,85 | 0,89 | 0,71 | 0,77 | 0,13 | 0,79 | 0,72 | 0,26 | 0,44 |
| Lai + mpc HCL | 0,86 | 0,89 | 0,74 | 0,75 | 0,15 | 0,84 | 0,77 | 0,26 | 0,50 |

flaky = 0 ở mọi mô hình.

### Nhận xét

1. **Khi lá hiếm có cặp dương, HCL hơn CE:**
   - Lá: +0,021 trên test nguyên vẹn, +0,024 trên test đã che.
   - Tầng 2 trên test đã che: +0,010.
   - Theo fold, HCL hơn CE ở 3/5 fold (mức lá, test nguyên vẹn).
   - Không có sampler thì HCL ≈ CE. Điều này khớp giả thuyết: SupCon cần cặp dương của lá hiếm trong batch.
2. **HCL dịch F1 từ lá đông sang lá hiếm (lai HCL so với lai CE, không sampler):**
   - Lá hiếm tăng: buildconfig +0,10, git +0,22, doc +0,14.
   - Lá đông giảm: testfailure −0,05, itestfailure −0,06, dependency −0,06.
   - Do đó macro-F1 gần như không đổi.
3. **Sampler làm giảm tầng 1** (0,882 → 0,85) và infra.
   - Lá đông bị lấy mẫu thưa hơn, nên mô hình lệch khỏi phân bố thật.
   - Cách sửa: điều chỉnh logit theo tần suất (logit adjustment) lúc suy luận.
4. **Cấu hình tốt nhất ở mức lá hiện là lai + mpc HCL** (0,595 / 0,527). Nhưng hơn lai CE chỉ +0,004 / +0,012, với 1 seed thì chưa đủ để kết luận.

## Lặp lại với seed 1 (20/10, `data/results/log_model/v6_seed1/`, cấu hình lai + sampler, preds có logp 3 tầng)

### Macro-F1 trung bình 5 fold

| | Seed 0: CE / HCL | Seed 1: CE / HCL | HCL > CE (10 cặp seed × fold) |
|---|---|---|---|
| Lá, nguyên vẹn | 0,574 / 0,595 | 0,605 / 0,629 | 6/10, Δ TB +0,023 |
| Lá, đã che | 0,503 / 0,527 | 0,532 / 0,556 | 7/10, Δ TB +0,025 |
| Tầng 2, nguyên vẹn | 0,733 / 0,741 | 0,750 / 0,753 | 6/10, Δ TB +0,006 |
| Tầng 1, nguyên vẹn | 0,856 / 0,847 | 0,869 / 0,870 | 5/10 |

### Kiểm định

- Bootstrap theo repo (300 lần), gộp 2 seed, macro-F1 lá tính trên toàn bộ dự đoán:
  - Nguyên vẹn: Δ **+0,018**, CI95 [−0,006; +0,036], P(Δ ≤ 0) = 0,08.
  - Đã che: Δ +0,011, CI95 [−0,011; +0,026], P(Δ ≤ 0) = 0,18.
- **Kết luận:** HCL hơn CE ở mức lá một cách **nhất quán về hướng** (cả 2 seed, khoảng +0,02). Mức chênh **chưa có ý nghĩa thống kê** ở 95%.

### Hiệu chỉnh logit

- Cách làm: cộng τ·(log prior thật − log prior của sampler) vào cả 3 đầu.
- Kết quả: **không cải thiện macro-F1** (τ = 0,5 / 1: tầng 1 +0,003; lá −0,01 với HCL).
- Với seed 1, tầng 1 không còn tụt (0,870, so với 0,882 của lai không sampler).

### Δ F1 theo lá (HCL − CE), đủ 3 lượt × 2 kiểu test (20/10)

- **Ổn định 6/6:** buildconfig (+0,02 → +0,09), doc (+0,04 → +0,14).
- **Không ổn định 3/6:** git, license. Mức +0,22 cho git chỉ có ở lượt không sampler, seed 0.
- **HCL kém hơn hoặc ngang 0/6:** dependency (−0,01 → −0,06), quality (≈ −0,01).
- **Sampler:** loại bỏ phần thua ở lá đông (testfailure, itestfailure) mà HCL gặp khi không có sampler.

## Loss tương phản mới sửa "anh em bị kéo quá gần" (20/10, fold 1, seed 0, lai + sampler; `data/results/log_model/v7_loss/`)

- **Thiết lập:** `soft` = SupCon một loss, cặp dương mềm theo cây (cùng lá 1, anh em 0,4); `proxy` = nguyên mẫu phân cấp (lá = cha + độ lệch, cha trọng số 0,3).
- Tham số chốt trước, không dò. CE, HCL lấy từ `v5_repr`, cùng fold và cùng seed.

### Kết quả fold 1

| Loss | Lá, nguyên / che | Tầng 2, nguyên / che | Tầng 1, nguyên / che | cos cùng lá | cos anh em | cos khác cha | kNN-10 acc lá |
|---|---|---|---|---:|---:|---:|---:|
| CE | 0,645 / 0,588 | 0,727 / 0,713 | 0,897 / 0,877 | 0,80 | 0,59 | 0,22 | 0,853 |
| HCL (3 tầng, cứng) | 0,641 / 0,596 | 0,746 / 0,731 | 0,904 / 0,879 | 0,79 | 0,59 | 0,17 | 0,848 |
| **soft** | **0,651 / 0,606** | 0,740 / 0,723 | 0,884 / 0,864 | 0,78 | **0,50** | 0,18 | **0,867** |
| proxy | 0,639 / 0,586 | 0,746 / 0,727 | 0,892 / 0,865 | 0,78 | 0,54 | 0,19 | 0,848 |

F1 theo lá đáng chú ý (log nguyên vẹn):

| Lá | CE | HCL | soft |
|---|---:|---:|---:|
| itestfailure | 0,78 | 0,70 | **0,81** |
| dependency | 0,74 | 0,75 | **0,80** |
| network | 0,72 | 0,68 | **0,76** |
| buildconfig | 0,97 | — | 0,87 |

- **soft đạt cả hai tiêu chí đặt trước:**
  - Cos anh em giảm 0,59 → 0,50, trong khi cùng lá vẫn 0,78.
  - Macro-F1 lá hơn CE (+0,006 nguyên vẹn, +0,018 đã che) và hơn HCL.
  - Embedding tốt nhất cho kNN (0,867).
- **proxy không hơn CE.**
- **Giới hạn:** chỉ 1 fold, 1 seed. Cần 5 fold × nhiều seed mới kết luận được.
