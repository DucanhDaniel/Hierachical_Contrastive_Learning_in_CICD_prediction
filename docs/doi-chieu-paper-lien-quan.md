# Đối chiếu cây nhãn và định vị đề tài với các paper liên quan (18/10/2026)

Bổ sung cho [huong-moi-phan-loai-sau-ci.md](huong-moi-phan-loai-sau-ci.md). Hai paper gần đề tài nhất:

- **[Z25]** Zheng et al., *Why Do GitHub Actions Workflows Fail? An Empirical Study*, ACM TOSEM 2025 ([DOI](https://dl.acm.org/doi/10.1145/3749371)).
  - Phân tích tay 375 job fail của 260 project Java trên GitHub Actions; 151 developer khảo sát xác nhận.
  - Cây 2 tầng: 5 nhóm, 16 nhóm con.
  - File gán nhãn công khai ([repo](https://github.com/zhengly1/workflow_failure)), bản tải về: `data/external/zheng_tosem2025/replication-labeling.xlsx`.
- **[G26]** Ge & Zhang, *Understanding and Detecting Flaky Builds in GitHub Actions*, arXiv 2602.02307 (2026).
  - 1.960 project Java trên GitHub Actions; 15 loại lỗi flaky.
  - Bộ phát hiện học máy nhị phân flaky / không flaky ở mức job.

## 1. Đối chiếu cây nhãn với [Z25]

Đơn vị đếm khác nhau: [Z25] đếm job, đề tài đếm commit (nhãn quy tắc trên 100 repo đợt 1).

| Nhóm [Z25] | Nhóm con [Z25] (số job) | Nút trong cây đề tài | Ghi chú |
|---|---|---|---|
| Compilation | P1 lỗi trong mã nguồn (54) | build/compile/compile | khớp |
| Compilation | P4 xung đột dependency (45) | build/dependency/dependency, hoặc build/compile | ví dụ trong file: lệch phiên bản Java/Gradle, xung đột version. Đề tài xếp theo giai đoạn: lỗi lộ ra lúc biên dịch thì là compile |
| Compilation | P3 dependency không resolve được (33) | build/dependency/dependency; lỗi tải tạm thời là env/infra/network | đề tài tách lỗi mạng khi tải ra network |
| Compilation | P2 cấu hình project sai (19) | build/buildconfig/buildconfig | một số ca trong file là lỗi xác thực khi deploy, đề tài xếp vào env/infra (chưa có lá) |
| Quality | P5 không qua kiểm tra chất lượng (26) | build/lint/quality (license, doc là lá riêng) | đề tài chi tiết hơn |
| Quality | P6 "lỗ hổng tiềm ẩn" (15) | build/dependency/dependency | thực chất là dependency bị cấm (maven-enforcer) và kiểm tra Gradle wrapper |
| Quality | P7 suy giảm hiệu năng (3) | **không có** | job benchmark/regression; rất hiếm |
| Testing | P8 test fail (120) | test/test/testfailure, itestfailure | đề tài tách unit và integration |
| Env/Config | W2 cấu hình workflow sai (21) | **không có lá riêng**; hiện rơi vào `?` hoặc env/infra | ví dụ: thiếu token GitHub, JDK home không tồn tại, upload coverage lỗi |
| Env/Config | W4 dựng môi trường lỗi do dependency (13) | env/infra/network hoặc build/dependency | ví dụ: setup-java, setup-r-dependencies |
| Env/Config | W3 lỗi mạng (10) | env/infra/network | khớp |
| Env/Config | W1 thiếu phần cứng / tài nguyên (2) | env/infra/crash | khớp |
| Env/Config | W5 thiếu quyền truy cập dịch vụ ngoài (2) | env/infra (để trống lá) | thuộc nhóm 564 commit infra chưa có lá (auth/token) |
| GitHub Issues | W8 quản lý VCS (6) | env/infra/git | khớp |
| GitHub Issues | W7 vượt rate limit GitHub API (3) | env/infra (để trống lá) | cùng nhóm auth/token |
| GitHub Issues | W6 không resolve được action (3) | env/infra/network | |

### Kết luận đối chiếu

1. **Phủ được gần hết:** 12/16 nhóm con của [Z25] khớp với một lá trong cây (theo số job là 346/375 = 92%). Bốn nhóm còn lại là P7, W2, W5, W7.
   - Chi tiết hơn [Z25] ở ba chỗ: unit/integration test, quality/license/doc, và network tách khỏi dependency.
   - Lá flaky không có trong [Z25] (họ không chạy lại job).
2. **Ba khoảng trống:**
   - **Lỗi quyền / token / rate limit (W5, W7, một phần W2, P2):** khớp với 564 commit infra đang để trống lá. Đề xuất thêm lá `auth` dưới env/infra (cần người duyệt).
   - **Cấu hình workflow sai (W2, 21 job = 5,6%):** Rausch không có loại này vì thời Travis CI chưa có. Đề xuất cân nhắc thêm lá `ciconfig` dưới env/infra, hoặc gộp vào `auth` nếu phần lớn là token.
   - **Suy giảm hiệu năng (P7):** chỉ 3 job, không đáng thêm lá.
3. **Phân bố khác nhau, và đây là kết quả đáng chú ý:**

| Nhóm | [Z25] (375 job, gán tay, mẫu ngẫu nhiên) | Đề tài (31.769 commit, nhãn quy tắc) |
|---|---:|---:|
| Test | 32,0% | 52,5% |
| Biên dịch: compile, dependency, buildconfig | 40,3% (P1 14,4 · P3+P4 20,8 · P2 5,1) | 18,3% (compile 14,2 · dependency 3,6 · buildconfig 0,5) |
| Quality / lint | 11,7% | 18,6% |
| Môi trường / GitHub | 16,0% | 10,4% |

   - **dependency và buildconfig thấp hơn 5–10 lần.** Đây chỉ là **giả thuyết cần điều tra**: quy tắc có thể bỏ sót. Hai bảng khác đơn vị (job với commit), khác tập mẫu và khác định nghĩa (P4 của [Z25] gồm cả lệch phiên bản Java/Gradle), nên không so trực tiếp được.
     - Quét log ngày 18/10: chỉ **1.254/19.632 run `?` (6,4%)** có tín hiệu dependency rõ.
     - Như vậy rà quy tắc chỉ bù được một phần. Đang giao Codex kiểm tra: [codex/task-ra-soat-quy-tac-dependency.md](codex/task-ra-soat-quy-tac-dependency.md).
   - **Test cao hơn:** quy tắc test có độ phủ cao.
   - **Hệ quả cho mục tiêu giảm lệch nhãn:** một phần độ lệch tầng 3 sinh ra từ cách gán nhãn, không chỉ từ dữ liệu. Crawl thêm không sửa được phần này. Hai việc sửa được:
     - Bổ sung quy tắc dependency/buildconfig cho nhóm `?`.
     - Mô hình gán được nhóm `?` (lập luận chính của đề tài).
   - Cần kiểm tra lại giả thuyết này trên tập gán mù: đếm tỉ lệ dependency/buildconfig trong các run quy tắc để `?`.

## 2. Định vị so với [G26]

| | [G26] | Đề tài |
|---|---|---|
| Dữ liệu | Java, GitHub Actions, 1.960 project | Java/JVM, GitHub Actions, 100 + 100 repo |
| Câu hỏi | job fail này có flaky không? (2 lớp) | run fail này thuộc loại lỗi nào? (cây 3 tầng, ~14 lá) |
| Nguồn nhãn | chạy lại job tới 10 lần, có job nào pass thì là flaky | quy tắc trên log (bản v2, người duyệt) + tập gán mù để kiểm chứng |
| 15 loại lỗi | phân tích tay, chỉ để mô tả, không phải đầu ra của mô hình | là đầu ra của mô hình |
| Mô hình | embedding MiniLM của dòng lỗi, top-K log tương tự (FAISS) + metadata → logistic regression | encoder trên đoạn log, gộp đoạn → job → run, đầu phân loại theo tầng + SupCon theo tầng |

**Quan hệ:**
- [G26] trả lời câu hỏi rerun hay không. Đề tài trả lời câu rộng hơn: rerun, hay sửa ở đâu (cấu hình build, code, dependency, lint, test).
- Trong cây đề tài, flaky chỉ là một lá. Nhãn flaky của đề tài hiện rất ít (61 commit, chỉ từ tóm tắt `N FLAKY` của Kafka).
- Nhãn kiểu [G26] (dựa trên chạy lại) có thể **bổ sung lá flaky** mà không cần LLM:
  - Run có `run_attempt` > 1 và lần sau pass trên cùng head_sha thì là ứng viên flaky.
  - Dữ liệu crawl đã có trường `run_attempt`, cần kiểm tra đủ dùng không.

**Những lá [G26] cho là phổ biến trong lỗi flaky:** network (15,8%), dependency resolution (6,3%), môi trường ngoài không nhất quán (4,7%).
- network và dependency khớp với lá của đề tài.
- "Môi trường ngoài không nhất quán" và "API service unavailable" tương ứng với env/infra (network hoặc lá để trống).

**Cách viết trong báo cáo:** đề tài tổng quát hoá [G26] từ "flaky hay không" thành phân loại nguyên nhân theo cây nhãn. Kỹ thuật của [G26] (embedding dòng lỗi và log tương tự) dùng làm **baseline**.

## 3. Việc đề xuất (chờ duyệt)

1. Thêm lá `auth` (quyền, token, rate limit) dưới env/infra, giải nghĩa "lỗi xác thực / phân quyền". Lá này lấp 564 commit infra đang trống và khớp W5, W7 của [Z25].
2. Cân nhắc lá `ciconfig` cho lỗi cấu hình workflow (W2 của [Z25]).
3. Trên tập gán mù: đo tỉ lệ dependency/buildconfig trong nhóm `?` để kiểm tra giả thuyết quy tắc bỏ sót.
4. Thử suy nhãn flaky từ lần chạy lại (`run_attempt`) như [G26].
5. Thêm baseline kiểu [G26] (MiniLM + kNN log tương tự + logistic regression) vào bảng thí nghiệm.
