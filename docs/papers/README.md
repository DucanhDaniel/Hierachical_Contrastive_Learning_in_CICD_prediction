# Paper liên quan: CI/CD build failure prediction + HCL

Tên file có tiền tố là hội nghị và năm đăng. Thư mục 1–4 chỉ chứa bài ở hội nghị lớn (SE: ICSE, FSE, ASE, ISSTA, MSR; ML/NLP: NeurIPS, ICML, ICLR, CVPR, ACL, EMNLP, AAAI). Bài không thuộc nhóm này nằm ở thư mục 5.

## 1. Build failure prediction (`1_build_prediction/`)

| File | Paper | Dùng để |
|---|---|---|
| ICSE2020_SmartBuildSkip_Jin_Servant.pdf | Jin & Servant, *A Cost-efficient Approach to Building in CI* (ICSE 2020) | Baseline kinh điển, bài toán bỏ qua build |
| ICSE2021_What_helped_and_what_did_not_CI.pdf | Jin & Servant, *What helped, and what did not? An Evaluation of the Strategies to Improve CI* (ICSE 2021) | So sánh 14 biến thể của 10 kỹ thuật, các độ đo chi phí/thời gian phản hồi |
| FSE2024_RavenBuild.pdf | *RavenBuild: Context, Relevance, and Dependency Aware Build Outcome Prediction* (FSE 2024) | SOTA gần đây |
| FSE2024-Industry_Atlassian_CI_build_failure_prediction.pdf | Hong et al., *Practitioners' Challenges and Perceptions of CI Build Failure Predictions at Atlassian* (FSE 2024 Industry) | Góc nhìn thực tế: developer cần độ chính xác và giải thích |
| MSR2025-Data_GHALogs_dataset.pdf | Moriconi et al., *GHALogs: Large-scale dataset of GitHub Actions runs* (MSR 2025, Data track) | **Dataset 513k lần chạy GitHub Actions có log đầy đủ** |

## 2. JIT defect prediction & biểu diễn code change (`2_jit_defect_code_change/`)

| File | Paper |
|---|---|
| ICSE2020_CC2Vec.pdf | CC2Vec: biểu diễn code change phân cấp hunk → file (ICSE 2020) |
| MSR2021_JITLine.pdf | JITLine: baseline đơn giản nhưng mạnh (MSR 2021) |
| FSE2023_CCT5.pdf | CCT5: mô hình pre-train cho code change (ESEC/FSE 2023) |
| ICSME2023_CCBERT.pdf | CCBERT (ICSME 2023, hội nghị tốt nhưng xếp dưới nhóm ICSE/FSE/ASE) |

## 3. Contrastive & hierarchical contrastive (`3_contrastive_hcl/`)

| File | Paper |
|---|---|
| NeurIPS2020_SupCon.pdf | **Supervised Contrastive Learning**, nền tảng của HCL |
| ICML2020_SimCLR.pdf | SimCLR |
| EMNLP2021_SimCSE.pdf | SimCSE |
| CVPR2022_UseAllTheLabels_...pdf | **Hierarchical multi-label contrastive**, gần nhất với hướng B (phân cấp nhãn) |
| ACL2022_HGCLR_...pdf | Hierarchy-guided contrastive cho phân loại văn bản phân cấp |
| AAAI2022_TS2Vec_...pdf | Contrastive phân cấp theo thời gian (hướng C) |
| arXiv2018_CPC_InfoNCE_nen_tang.pdf | CPC: chỉ có trên arXiv nhưng là nguồn gốc InfoNCE, được trích dẫn rất nhiều, nên giữ lại |

## 4. Encoder & huấn luyện (`4_encoder_training/`)

| File | Paper |
|---|---|
| EMNLP2020-Findings_CodeBERT.pdf | CodeBERT |
| ACL2022_UniXcoder.pdf | UniXcoder |
| ICLR2022_LoRA.pdf | LoRA (giai đoạn 2) |

## 5. Không phải hội nghị lớn (`5_khong_phai_hoi_nghi_lon/`)

Giữ lại để tham khảo, không nên dùng làm trích dẫn chính.

| File | Lý do |
|---|---|
| arXiv_SLR_ML_in_CI_v1_bi_tu_choi.pdf | Theo comment trên arXiv thì bài đã bị từ chối, v2 đã bị rút |
| arXiv2024_CI_Skip_RL.pdf | Chỉ có preprint |
| arXiv2026_Flaky_Builds_GitHub_Actions.pdf | Chỉ có preprint (nhưng taxonomy 15 loại flaky failure vẫn hữu ích) |
| arXiv2023_Commit_Classification_Contrastive.pdf | Chỉ có preprint |
| ToolDemo2025_DRS-OSS.pdf | Bài tool demo |
| JSS2024_BiCC-BERT_JIT_defect.pdf | Tạp chí JSS (tốt, nhưng không phải hội nghị) |
| PhDThesis_Saidani_CI_build_prediction.pdf | Luận án, gồm DL-CIBuild (tạp chí ASE) |
| Chalmers_build_outcome_textual_commits.pdf | Chưa xác định nơi đăng |
| Workshop-RepL4NLP2021_GradCache.pdf | Workshop của ACL (vẫn hữu ích cho giai đoạn 2) |

## Bài ở hội nghị lớn nhưng chưa có PDF công khai (cần tải qua ACM/IEEE bằng tài khoản trường)

- **GitSense**, *Commit Artifact Preserving Build Prediction* (ISSTA 2024): Transformer trên diff + commit message, **gần đề tài nhất**. Code: github.com/GuoqingWang1999/GitSense, data: Zenodo 12820030
- Chen et al., *BuildFast: History-Aware Build Outcome Prediction* (ASE 2020)
- Ni & Li, *Cost-effective build outcome prediction using cascaded classifiers* (MSR 2017)
- Hoang et al., *DeepJIT* (MSR 2019)
- Zeng et al., *Deep Just-in-Time Defect Prediction: How Far Are We?* (ISSTA 2021)
- Brandt et al., *LogChunks: A Data Set for Build Log Analysis* (MSR 2020, Data track)
