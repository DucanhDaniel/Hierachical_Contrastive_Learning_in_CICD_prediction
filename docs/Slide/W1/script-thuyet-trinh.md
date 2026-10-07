# Script thuyết trình: Dự đoán lỗi build CI/CD bằng Hierarchical Contrastive Learning

Dùng cho file `Slide gioi thieu de tai - Build failure HCL.pptx` (bản đầu tiên). Tổng thời lượng khoảng 12 phút. Phần trong ngoặc vuông là gợi ý động tác, không đọc.

---

## Slide 1–2. Bìa và tiêu đề (~20 giây)

Em chào cô ạ. Em là Phạm Đức Anh, MSSV 20235008. Đề tài Project 3 của em là **dự đoán lỗi build CI/CD bằng Hierarchical Contrastive Learning**, dưới sự hướng dẫn của cô Vũ Thị Hương Giang.

## Slide 3. Nội dung trình bày (~15 giây)

Bài trình bày của em gồm 9 phần. Đầu tiên là bối cảnh và lý do các cách dự đoán hiện tại chưa đủ. Tiếp theo là phần khảo sát dữ liệu và phương pháp. Sau đó em trình bày giao thức đánh giá, luồng dự đoán, mô hình và kiến trúc hệ thống. Cuối cùng là kế hoạch thực hiện.

## Slide 4. Bối cảnh & định hướng (~1 phút)

Mỗi khi lập trình viên đẩy code lên, hệ thống CI sẽ tự động build và chạy test. Việc này rất tốn kém: Google hay Mozilla tốn hàng triệu đô mỗi năm cho CI, còn ở Ubisoft mỗi ngày có hàng nghìn build, mỗi build mất 10 đến 30 phút.

Bài toán **build prediction** đặt câu hỏi: có đoán được build sẽ pass hay fail **trước khi chạy** không, khi mới chỉ có diff và metadata của commit? Nếu đoán được thì có thể bỏ qua những build gần như chắc chắn pass, cho job rủi ro chạy trước, và cảnh báo sớm khi review PR.

Ở đây em tách bài toán làm hai phần. Phần dễ là khi code liên quan không thay đổi, ví dụ chỉ sửa README. Trường hợp này đã có luật xử lý, như `paths` filter của GitHub Actions hay cache build. Phần khó là khi **code có thay đổi**, và đó là phạm vi của đề tài.

Định hướng của em là cho mô hình **đọc nội dung diff theo cấu trúc phân cấp**, và dùng **loại lỗi** làm tín hiệu huấn luyện, thay vì chỉ học hai nhãn pass/fail.

## Slide 5. Vì sao dự đoán pass/fail hiện tại chưa đủ (~1 phút 15 giây)

Nhìn vào số liệu, các mô hình hiện tại cho kết quả khá tốt. Nhưng lý do là vì dữ liệu có quán tính rất mạnh: khoảng 87% build là pass, khoảng 52% số lần fail xảy ra ngay sau một lần fail khác, và 76% build có kết quả giống hệt build ngay trước nó.

Vì vậy bài RavenBuild ở FSE 2024 thử một cách đoán "ngây thơ", gọi là **Parrot**: lần trước thế nào thì đoán lần này y như vậy. Kết quả là Parrot đạt F1 lớp fail 0,42, trong khi các mô hình tốt nhất cũng chỉ đạt 0,48 đến 0,50. Các mô hình này chủ yếu vẫn đếm số liệu, chưa đọc nội dung thay đổi.

Khi đem ra dùng thật thì có bốn vấn đề:
- Thứ nhất, Parrot luôn sai ở **lần fail đầu tiên**, tức là lúc đang xanh chuyển sang đỏ. Đó lại chính là lúc dự đoán có giá trị nhất.
- Thứ hai, nếu build trước đã bị bỏ qua thì không biết kết quả của nó.
- Thứ ba, ở khoảng 60% số trường hợp, các mô hình tốt nhất không hơn Parrot một cách rõ rệt.
- Thứ tư, mô hình chỉ trả lời pass hay fail mà không nói hỏng kiểu gì.

[Chỉ vào khung đỏ] Vì vậy, đề tài cần một mô hình đọc được nội dung thay đổi, được đánh giá trên lần fail đầu tiên, và có cấu trúc theo loại lỗi.

## Slide 6. Kiểm chứng: Parrot so với SOTA (~1 phút)

Slide này là số liệu gốc để kiểm chứng những gì em vừa nói. [Chỉ vào bảng] Đây là Bảng 8 trong bài RavenBuild, so sánh Parrot với BuildFast và RavenBuild trong hai bối cảnh.

- **Với 22 project mã nguồn mở**, RavenBuild-CR tốt nhất về F1 lớp fail với 0,50, nhưng Parrot vẫn đạt 0,42 mà không cần học gì cả.
- **Với Project X, một game AAA của Ubisoft**, Parrot thậm chí còn cao hơn: F1 lớp fail 0,66, so với 0,64 của RavenBuild và 0,43 của BuildFast.
- Ở cột Gain, tức là thời gian phản hồi tiết kiệm được trừ đi chi phí, Parrot cao nhất ở cả hai bối cảnh.

Tác giả giải thích nguyên nhân: 76% build mã nguồn mở có kết quả lặp lại build trước, gồm 82% build pass và 62% build fail; ở Project X con số này là 87%. Tính trên 92 trường hợp, tức 23 project nhân 4 độ đo, BuildFast và RavenBuild thua Parrot lần lượt ở 38% và 33%. Ở 64% và 61% số trường hợp, chúng không hơn Parrot một cách rõ rệt.

Bên phải là các số liệu từ nghiên cứu khác, cho kết luận tương tự:
- SmartBuildSkip, trên 274 nghìn build của 359 project, ghi nhận 87% build pass và 52% fail là fail liên tiếp.
- Khảo sát ở Atlassian trên 350 nghìn PR cho thấy yếu tố mạnh nhất là tỉ lệ fail gần đây của repo. 58% developer thấy dự đoán hữu ích, nhưng 29% cho là không.
- Nghiên cứu về flaky build cho thấy 3,2% build bị chạy lại, và 67,7% trong số đó là flaky.

Điểm chung là: **Parrot mạnh vì dữ liệu có quán tính, nhưng nó luôn sai khi kết quả đổi chiều.** Đây là lý do em đặt giao thức đánh giá P3 ở phần sau.

## Slide 7. Khảo sát dữ liệu (~45 giây)

Về dữ liệu, em đã khảo sát năm nguồn và chọn **GHARuns** làm nguồn chính:
- **GHARuns** công bố năm 2026, có 71,7 triệu lần chạy GitHub Actions của gần 46 nghìn repo, theo dõi **liên tục** từ tháng 2 đến tháng 6/2026. Điểm quan trọng là bộ này có cả tên và kết quả của từng job, từng step, nên em gán được loại lỗi mà không cần log.
- **TravisTorrent** là bộ kinh điển, dùng để đối chiếu với nghiên cứu cũ, nhưng đã cũ và trang web gốc không còn hoạt động.
- **GHALogs** có log đầy đủ nhưng mỗi workflow chỉ lấy 5 lần chạy gần nhất, nên không có chuỗi build liên tục.
- **Dataset của GitSense** được công khai, em dùng làm baseline.
- Crawler tự viết qua GitHub API giờ chỉ dùng để lấy log mẫu, nhằm kiểm tra lại độ chính xác của nhãn.

## Slide 8. Thử nghiệm GHARuns (~1 phút)

Em đã thử trên 6 repo Java của Apache. [Chỉ vào bảng] Chỉ xét các commit đẩy lên nhánh chính trong 5 tháng, tổng cộng 4.109 commit. Trong đó 925 commit làm hỏng ít nhất một workflow, tức 22,5%, và có **523 lần fail đầu tiên**, đủ cho giao thức P3. Tỉ lệ fail chênh nhau nhiều giữa các repo, từ 7% ở Iceberg đến 53% ở Druid, nên phù hợp để thử đánh giá chéo repo.

Về gán nhãn, chỉ cần dựa vào tên step bị fail, em đã gán được 95% số lần chạy fail. Phân bố thực tế là: test 72%, compile 18%, lint 4%, hạ tầng 2%. Vì vậy em điều chỉnh cây nhãn theo dữ liệu thật, thay nhánh dependency bằng lint. Em cũng loại các đợt fail bất thường, khi nhiều commit cùng fail ở một step trong thời gian ngắn, vì đó thường là sự cố hạ tầng chứ không phải do code.

Hạn chế của bộ này là không có log, và không có chi tiết cho các lần chạy từ pull request. Vì vậy đề tài dự đoán cho build trên nhánh chính. Nếu cần mở rộng, có thêm 23 repo Apache với khoảng 1.650 lần fail đầu tiên.

## Slide 9. Khảo sát phương pháp (~1 phút)

Các phương pháp đi theo một trình tự như sau:
- Khoảng năm 2017, các nghiên cứu chỉ dùng metadata của build hiện tại và build trước.
- **SmartBuildSkip** ở ICSE 2020 hướng tới tiết kiệm chi phí: chỉ đoán lần fail đầu tiên, sau đó coi các lần tiếp theo là fail. Cách này tiết kiệm được 30% số build.
- **BuildFast** ở ASE 2020 khai thác log của các build cũ, còn **DL-CIBuild** dùng LSTM trên chuỗi build.
- **RavenBuild** năm 2024 bổ sung ngữ cảnh và đồ thị phụ thuộc.
- **GitSense** ở ISSTA 2024 bắt đầu dùng Transformer để đọc commit message và diff. Đây là bài gần với đề tài của em nhất.

Ở các bài toán lân cận, CC2Vec đã biểu diễn code theo phân cấp dòng, hunk, file. Contrastive learning phân cấp cũng đã có, như SupCon hay Use All The Labels ở CVPR 2022. Tuy nhiên trong các bài em đã đọc, **chưa có bài nào áp dụng contrastive learning cho build prediction**.

Hướng em chọn là: encoder phân cấp từ hunk lên file lên commit, kết hợp contrastive theo cây loại lỗi và feature lịch sử. Em sẽ so sánh với Parrot, logistic regression, XGBoost, GitSense và SupCon một tầng.

## Slide 10. Giao thức đánh giá (~1 phút)

Để đánh giá công bằng, em dùng bốn giao thức:
- **P0** chia ngẫu nhiên, chỉ để so với các nghiên cứu cũ. Cách chia này dễ rò rỉ thông tin theo thời gian, và Parrot đã rất mạnh ở đây.
- **P1** chia theo thời gian, train trên giai đoạn đầu và test trên giai đoạn sau, để xem mô hình có dùng thật được không.
- **P2** chéo repo: train trên repo này, test trên repo khác.
- **P3** là giao thức quan trọng nhất: chỉ xét **lần fail đầu tiên**, tức commit fail ngay sau một commit pass. Trên 6 repo đã thử có 523 ca như vậy. Ở P3 em cũng giả lập trường hợp không biết kết quả build trước, và so sánh hai cấu hình "chỉ dùng diff" với "diff cộng lịch sử", để tách được đóng góp thật của mô hình.

Độ đo gồm F1 và PR-AUC cho lớp fail, macro-F1 theo loại lỗi, tỉ lệ build tiết kiệm được so với tỉ lệ lỗi bị bỏ sót, và độ trễ phát hiện lỗi.

Mục tiêu của em không phải làm đẹp con số ở P0, mà là cải thiện ở P1 đến P3, đặc biệt là P3.

## Slide 11. Luồng dự đoán (~45 giây)

Hệ thống có hai luồng.
- **Luồng offline** [chỉ hàng trên]: lọc dữ liệu GHARuns cho các build trên nhánh chính, gán nhãn theo tên step và chia dữ liệu, lấy diff bằng git clone rồi trích embedding bằng CodeBERT, huấn luyện HCL, và dựng SHAP explainer.
- **Luồng online** [chỉ hàng dưới]: khi có push hoặc pull request, hệ thống lấy diff và metadata, đưa qua encoder phân cấp. Bộ dự đoán trả về xác suất fail kèm loại lỗi dự kiến, rồi bot comment lên PR với lý do và gợi ý thứ tự chạy job.

## Slide 12. Mô hình HCL (~1 phút)

Đây là phần cốt lõi của đề tài. [Chỉ vào cây] Em tổ chức nhãn thành hai tầng:
- **Tầng một** là pass và fail. Mô hình học cách đẩy hai nhóm này ra xa nhau.
- **Tầng hai** nằm trong nhánh fail, gồm compile, test, lint và infra/flaky, đúng theo phân bố thực tế trong GHARuns. Các build cùng loại lỗi được kéo lại gần nhau hơn.

Có thể hình dung giống như xếp sách: trước tiên chia hai kệ lớn, rồi trong mỗi kệ lại chia tiếp theo thể loại.

Đầu vào cũng phân cấp: từ dòng lên hunk, lên file, lên commit, dùng attention để gộp, sau đó ghép thêm feature lịch sử build. Hàm loss gồm loss phân loại cộng với contrastive loss ở từng tầng, có trọng số.

Em kỳ vọng mô hình học được những mẫu như: đổi chữ ký method thì dễ lỗi compile, đổi logic mà không sửa test thì dễ lỗi test, sai format hay checkstyle thì lỗi lint. Đây là điều các mô hình chỉ đếm số không làm được.

## Slide 13. Kiến trúc hệ thống (~45 giây)

Hệ thống gồm bốn khối, đi từ trái sang phải:
- **Khối thu thập** dùng dữ liệu GHARuns, lấy diff bằng git, và chỉ gọi GitHub API để lấy log mẫu kiểm chứng nhãn.
- **Khối học máy** xử lý, gán nhãn, rồi qua encoder phân cấp và HCL head. Model được lưu lại trong registry.
- **Khối phục vụ** có API FastAPI trả về xác suất fail và loại lỗi, kèm SHAP để giải thích, đồng thời lưu kết quả để đánh giá sau.
- **Khối tích hợp** nhận webhook từ GitHub, comment lên PR và có dashboard so sánh các baseline.

## Slide 14. Kế hoạch thực hiện (~45 giây)

Em chia công việc thành ba sprint:
- **Sprint 1, tuần 1 đến 5:** khảo sát, viết đề cương, lọc GHARuns và gán nhãn (em đã thử xong trên 6 repo), lấy diff, chạy các baseline đơn giản. Sản phẩm là bộ dữ liệu khoảng 4.100 commit có nhãn loại lỗi, có thể mở rộng tới 23 repo.
- **Sprint 2, tuần 6 đến 10:** chạy các baseline mạnh hơn như XGBoost, CodeBERT, GitSense, và cài đặt HCL. Khoảng tuần 10 em sẽ quyết định có làm thêm giai đoạn fine-tune nặng bằng GPU hay không.
- **Sprint 3, tuần 11 đến 14:** đánh giá đầy đủ theo P0 đến P3, chạy ablation, xây API và bot comment PR, rồi viết báo cáo.

## Slide 15. Kết thúc (~10 giây)

Phần trình bày của em đến đây là hết. Em cảm ơn cô đã lắng nghe, và mong nhận được góp ý của cô ạ.

---

## Câu hỏi có thể gặp và gợi ý trả lời

**"Biết trước pass/fail thì có ích gì, dev vẫn phải xem log?"**
Đúng ạ, dự đoán không thay thế việc đọc log. Giá trị nằm ở quy mô lớn: tiết kiệm tài nguyên CI, chạy job rủi ro trước để fail sớm, và cảnh báo khi review PR. Vì vậy em dự đoán thêm cả loại lỗi, để dev biết nên chuẩn bị cho kiểu lỗi nào.

**"Sao không dùng luôn kết quả build trước, vì nó mạnh nhất?"**
Em vẫn dùng nó trong cấu hình "diff + lịch sử". Nhưng em báo cáo riêng cấu hình "chỉ diff" và giao thức P3, để chứng minh mô hình đóng góp thật chứ không chỉ lặp lại build trước như Parrot.

**"Nếu HCL không vượt baseline thì sao?"**
Em vẫn báo cáo trung thực, kèm ablation và phân tích lỗi. Phần dữ liệu có nhãn loại lỗi trên GitHub Actions bản thân nó cũng là một đóng góp.

**"Không có GPU thì làm thế nào?"**
Giai đoạn 1 em trích embedding một lần trên Colab hoặc Kaggle, sau đó chỉ train một head nhỏ, chạy được cả trên CPU. Fine-tune nặng bằng LoRA chỉ làm nếu kịp tiến độ ở mốc tuần 10.

**"Sao không tự crawl mà dùng dữ liệu có sẵn?"**
Em có viết crawler và thử trên Superset, nhưng log và cả thông tin step trên GitHub bị xóa sau vài tháng, và mỗi repo có hơn 70 workflow cần lọc. GHARuns đã lưu liên tục 5 tháng cho 46 nghìn repo, có đủ job và step, nên dữ liệu đầy đủ và tái lập được. Crawler em giữ lại để lấy log mẫu, kiểm tra độ chính xác của nhãn.

**"Nhãn loại lỗi gán tự động có đáng tin không?"**
Em gán theo tên step bị fail, được 95% số lần chạy fail. Em sẽ kiểm chứng bằng cách so với log thật của một mẫu run mới, và báo cáo độ chính xác của bộ gán nhãn. Các đợt fail hàng loạt do sự cố hạ tầng được phát hiện và loại riêng.

