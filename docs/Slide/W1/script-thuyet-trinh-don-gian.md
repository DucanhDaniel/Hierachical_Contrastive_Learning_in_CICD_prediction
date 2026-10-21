# Script thuyết trình bản đơn giản: Dự đoán lỗi build CI/CD bằng HCL

Dùng cho file `Slide gioi thieu de tai - Build failure HCL.pptx`. Thời lượng khoảng 10 phút. Phần trong ngoặc vuông là động tác, không đọc. Chữ **in đậm** là ý chính của slide; nếu quên lời thì chỉ cần nói được câu đó.

---

## Mạch câu chuyện (nhớ 5 bước này là đủ)

1. **Vấn đề:** chạy kiểm tra code (CI) rất tốn thời gian và tiền. Nếu đoán trước được lần chạy nào sẽ hỏng thì tiết kiệm được nhiều.
2. **Cách cũ chưa đủ:** cách đoán "lần trước sao thì lần này vậy" đã gần bằng các mô hình xịn, vì các mô hình đó chưa thật sự đọc code.
3. **Dữ liệu:** em lấy dữ liệu thật trên GitHub, biết không chỉ "hỏng" mà còn "hỏng kiểu gì".
4. **Ý tưởng chính:** cho mô hình đọc phần code thay đổi, và dạy nó bằng cách so sánh: lỗi cùng kiểu thì xếp gần nhau, khác kiểu thì để xa nhau.
5. **Cách chứng minh và kế hoạch:** đánh giá đúng ở chỗ khó nhất là lần hỏng đầu tiên; sau đó là kế hoạch 3 giai đoạn.

Cách nói chung: mỗi slide chỉ nói **một ý**. Gặp số liệu thì đọc **một con số quan trọng nhất**, không đọc cả bảng.

---

## Vài từ cần giải thích một lần, sau đó dùng lại

| Từ trên slide | Nói đơn giản là |
|---|---|
| CI, build | Mỗi lần lập trình viên đẩy code lên, máy chủ tự động biên dịch và chạy kiểm tra. Mỗi lần như vậy là một "build". |
| pass / fail | Build chạy thành công / bị hỏng. |
| diff | Phần code bị thay đổi trong lần đẩy lên đó. |
| Parrot | "Con vẹt": đoán y như kết quả lần trước. |
| Lần fail đầu tiên | Lần đang chạy tốt bỗng bị hỏng. Đây là lúc con vẹt luôn đoán sai. |
| Loại lỗi | Hỏng ở bước nào: biên dịch (compile), kiểm tra định dạng code (lint), hay chạy test (test). |
| HCL (học tương phản phân cấp) | Dạy mô hình bằng cách so sánh: kéo các ví dụ giống nhau lại gần, đẩy các ví dụ khác nhau ra xa, làm theo nhiều tầng. |

---

## Slide 1–2. Mở đầu (~20 giây)

> Em chào cô ạ. Em là Phạm Đức Anh, MSSV 20235008. Đề tài của em là **dự đoán lỗi build CI/CD bằng Hierarchical Contrastive Learning**, do cô Vũ Thị Hương Giang hướng dẫn.
>
> Nói ngắn gọn, em muốn **đoán trước một lần chạy kiểm tra code có bị hỏng không, và nếu hỏng thì hỏng kiểu gì**, trước khi chạy.

## Slide 3. Nội dung (~10 giây)

> Bài của em đi theo một mạch: vấn đề là gì, vì sao cách hiện tại chưa đủ, em dùng dữ liệu gì, ý tưởng mô hình, cách chứng minh, và cuối cùng là kế hoạch.

[Không đọc từng mục trên slide.]

## Slide 4. Bối cảnh (~1 phút)

**Ý chính: chạy kiểm tra code rất tốn kém. Đoán trước được thì tiết kiệm.**

> Mỗi lần lập trình viên đẩy code lên, máy chủ sẽ tự biên dịch và chạy kiểm tra. Người ta gọi mỗi lần như vậy là một build. Ở công ty lớn việc này rất tốn: Ubisoft có hàng nghìn build mỗi ngày, mỗi build mất 10 đến 30 phút.
>
> Nếu đoán trước được build nào chắc chắn chạy tốt thì có thể bỏ qua. Build nào dễ hỏng thì cho chạy trước để báo lỗi sớm.
>
> Trường hợp dễ, ví dụ chỉ sửa tài liệu, đã có quy tắc đơn giản để bỏ qua. Em tập trung vào trường hợp khó là **có sửa code thật**. Hướng của em là cho mô hình **đọc chính phần code bị sửa**, và học thêm **hỏng kiểu gì**, chứ không chỉ học hỏng hay không.

## Slide 5. Vì sao cách hiện tại chưa đủ (~1 phút)

**Ý chính: cách đoán "lần trước sao thì lần này vậy" đã gần bằng các mô hình hiện có. Nó luôn sai đúng ở lúc quan trọng nhất.**

> Có một hiện tượng: khoảng 3/4 số build có kết quả giống hệt lần trước. Đang chạy tốt thì thường tiếp tục tốt; đang hỏng thì thường tiếp tục hỏng.
>
> Vì vậy có một cách đoán rất đơn giản mà người ta gọi đùa là "con vẹt": lần trước thế nào thì đoán lần này y như vậy. Con vẹt đạt điểm 0,42, còn các mô hình tốt nhất hiện nay chỉ khoảng 0,50, tức là hơn không nhiều.
>
> Nhưng con vẹt có một điểm yếu chết người: nó **luôn sai ở lần hỏng đầu tiên**, tức lúc đang chạy tốt bỗng bị hỏng. Đó lại đúng là lúc cảnh báo có giá trị nhất. Ngoài ra, các cách hiện tại chỉ trả lời "hỏng hay không" mà không nói "hỏng ở đâu".
>
> [Chỉ vào khung kết luận] Vì vậy em cần một mô hình **đọc được code**, được **đánh giá ở lần hỏng đầu tiên**, và **nói được loại lỗi**.

## Slide 6. Bằng chứng từ bài báo (~45 giây)

**Ý chính: không phải em tự nói. Một bài báo năm 2024 đã cho thấy con vẹt rất khó bị đánh bại.**

> Số liệu này lấy từ bài RavenBuild, công bố ở hội nghị FSE năm 2024. [Chỉ vào bảng dưới] Đáng chú ý nhất là với dự án game của Ubisoft, **con vẹt còn đạt điểm cao hơn cả mô hình mới nhất**: 0,66 so với 0,64.
>
> Tác giả cũng thống kê: trong khoảng 60% số trường hợp, các mô hình phức tạp không hơn con vẹt một cách rõ rệt. Nghĩa là muốn hơn thật thì phải nhìn vào thứ con vẹt không nhìn, đó là **nội dung code bị sửa**.

[Không đọc hết các cột. Chỉ nói đúng một con số 0,66 và 0,64.]

## Slide 7. Dữ liệu (~45 giây)

**Ý chính: em cần dữ liệu biết "hỏng kiểu gì". Các bộ có sẵn đều thiếu, nên nguồn chính là dữ liệu em tự thu thập.**

> [Chỉ dòng đầu] Nguồn chính là dữ liệu em tự lấy từ GitHub, gồm cả nhật ký lỗi của 11 dự án trong 90 ngày gần nhất. Nhờ có nhật ký lỗi, em biết chính xác mỗi lần hỏng là do biên dịch, do định dạng code, hay do test.
>
> Các bộ có sẵn thì đều thiếu một thứ. Bộ lớn nhất có hơn 70 triệu lần chạy nhưng chỉ cho biết thành công hay hỏng, không có lý do, nên em chỉ dùng để chọn dự án. Bộ khác có lý do nhưng không liên tục theo thời gian. Có bộ thì đã quá cũ.

## Slide 8. Thử trên dữ liệu thật (~1 phút)

**Ý chính: 11 dự án thật của Apache cho gần 28 nghìn lần đẩy code, đủ dùng. Phần lớn lỗi là lỗi test.**

> Em thu thập dữ liệu của 11 dự án mã nguồn mở của Apache, viết bằng Java. [Chỉ vào dòng Tổng] Có khoảng 28 nghìn lần đẩy code, trong đó gần 8 nghìn lần bị hỏng, và có **khoảng 4.800 lần hỏng đầu tiên**, đủ để đánh giá ở chỗ khó nhất.
>
> [Chỉ vào bảng loại lỗi] Trong những lần hỏng biết được lý do, lỗi test chiếm nhiều nhất, sau đó là lỗi biên dịch và lỗi định dạng code. Những lần hỏng do máy chủ (infra/flaky) không phải lỗi của code nên em tách riêng.
>
> Có một phần ba số lần hỏng chưa gán được nhãn, vì GitHub đã xoá nhật ký lỗi của chúng. Em không đoán nhãn cho các lần này mà để riêng ra.

## Slide 9. Các phương pháp đã có (~45 giây)

**Ý chính: các nghiên cứu ngày càng đọc nhiều thông tin hơn, nhưng chưa ai dùng cách học bằng so sánh cho bài toán này.**

> Có thể tóm tắt các nghiên cứu trước thành một hành trình. Ban đầu chỉ dùng con số, như số file bị sửa hay kết quả lần trước. Sau đó người ta dùng thêm nhật ký lỗi cũ. Gần đây mới bắt đầu cho mô hình đọc code.
>
> Cách học bằng so sánh, tức kéo giống nhau lại gần và đẩy khác nhau ra xa, đã thành công ở nhận diện ảnh. Nhưng theo những gì em tìm được thì **chưa ai áp dụng nó cho bài toán dự đoán build**. Đây là điểm mới của đề tài.

## Slide 10. Cách đánh giá (~1 phút)

**Ý chính: em không chỉ chấm điểm kiểu dễ. Em chấm ở chỗ khó nhất, là lần hỏng đầu tiên.**

> Em đánh giá theo bốn cách, từ dễ đến khó:
> - **P0, xáo trộn ngẫu nhiên:** chỉ để so với bài cũ. Cách này dễ vì mô hình vô tình được thấy cả tương lai.
> - **P1, theo thời gian:** học trên dữ liệu cũ, thi trên dữ liệu mới, giống khi dùng thật.
> - **P2, dự án mới:** học trên dự án này, thi trên dự án khác.
> - **P3, lần hỏng đầu tiên:** chỉ chấm những lần đang tốt bỗng hỏng. Ở đây con vẹt luôn sai, nên **mô hình nào hơn ở P3 mới là hơn thật**.
>
> Mục tiêu của em là cải thiện ở P1 đến P3, đặc biệt là P3.

## Slide 11. Luồng hoạt động (~45 giây)

**Ý chính: có hai giai đoạn. Học trước từ dữ liệu cũ, sau đó tự động dự đoán mỗi khi có code mới.**

> [Chỉ hàng trên] Giai đoạn học: thu thập dữ liệu, gán nhãn loại lỗi, biến đoạn code thành dạng số mà máy hiểu được, rồi huấn luyện mô hình.
>
> [Chỉ hàng dưới] Giai đoạn dùng: khi có người đẩy code lên, hệ thống lấy phần code bị sửa, đưa qua mô hình để ra **khả năng bị hỏng và loại lỗi dự kiến**, rồi tự động bình luận lên pull request để người review biết.

## Slide 12. Ý tưởng mô hình (~1 phút 15 giây). Slide quan trọng nhất, nói chậm

**Ý chính: dạy mô hình giống như xếp sách lên kệ. Chia "tốt" và "hỏng" trước, trong nhóm "hỏng" chia theo loại lỗi, rồi chia tiếp theo dạng lỗi chi tiết.**

> Đây là phần cốt lõi. Em xin dùng một ví dụ: xếp sách trong thư viện.
>
> - **Tầng một:** chia hai kệ lớn, một kệ cho những lần chạy tốt, một kệ cho những lần bị hỏng. Mô hình học cách đẩy hai nhóm này ra xa nhau.
> - **Tầng hai:** trong kệ "hỏng", lại chia ngăn theo loại lỗi: biên dịch, test, định dạng code. Những lần hỏng cùng kiểu được xếp gần nhau.
> - **Tầng ba:** trong mỗi ngăn lại chia nhỏ hơn. [Chỉ vào hàng dưới cùng của cây] Ví dụ lỗi định dạng có thể do sai khoảng trắng, do vi phạm quy tắc viết code, hay do thiếu giấy phép. Thông tin này em đọc được từ nhật ký lỗi.
>
> Tầng ba quan trọng vì cách huấn luyện thông thường chỉ biết ba loại lỗi, còn cách học bằng so sánh tận dụng được cả thông tin chi tiết này.
>
> Mô hình đọc code cũng theo từng lớp: từ từng đoạn thay đổi, lên từng file, rồi lên cả lần đẩy code. Giống như đọc từng câu, rồi từng trang, rồi cả chương.
>
> Em kỳ vọng mô hình tự học được các quy luật mà lập trình viên vẫn biết theo kinh nghiệm. Ví dụ: đổi tên hàm mà quên sửa chỗ gọi thì dễ lỗi biên dịch; sửa logic mà không sửa test thì dễ lỗi test; viết sai định dạng thì lỗi kiểm tra định dạng. **Con vẹt không bao giờ học được những điều này vì nó không đọc code.**

## Slide 13. Kiến trúc hệ thống (~30 giây)

**Ý chính: hệ thống gồm 4 khối nối tiếp nhau, từ lấy dữ liệu đến hiển thị cho lập trình viên.**

> [Chỉ lần lượt từ trái sang phải] Khối một thu thập dữ liệu. Khối hai huấn luyện mô hình. Khối ba là dịch vụ trả lời dự đoán, kèm giải thích vì sao. Khối bốn gắn vào GitHub để bình luận lên pull request, và có bảng theo dõi kết quả.

[Không đi vào từng ô nhỏ trên slide.]

## Slide 14. Kế hoạch (~30 giây)

**Ý chính: 3 giai đoạn: dữ liệu, mô hình, đánh giá và demo.**

> Em chia làm ba giai đoạn:
> - **Tuần 1–5:** thu thập và gán nhãn dữ liệu, chạy các cách so sánh đơn giản như con vẹt.
> - **Tuần 6–10:** xây mô hình HCL và so với các phương pháp khác.
> - **Tuần 11–14:** đánh giá đầy đủ, làm bản demo bot bình luận trên pull request, và viết báo cáo.

## Slide 15. Kết thúc (~10 giây)

> Tóm lại, em muốn làm một mô hình **đọc code để đoán trước lần chạy có hỏng không và hỏng kiểu gì**, đặc biệt ở lần hỏng đầu tiên, nơi các cách hiện tại làm kém nhất. Em cảm ơn cô đã lắng nghe, và mong nhận được góp ý của cô ạ.

---

## Nếu cô hỏi "đã làm được gì chưa" (nói ngắn, khoảng 1 phút)

> Dạ em đã chạy thử để kiểm tra đề tài có khả thi không:
> - Em đã thu thập được khoảng 24 nghìn lần đẩy code trên 11 dự án Apache, trong đó có khoảng 4.600 lần hỏng do code, có nhãn loại lỗi lấy từ nhật ký lỗi thật.
> - **Đoán loại lỗi là làm được:** với những chuỗi chưa từng hỏng, con vẹt không có gì để đoán. Mô hình đọc code đoán tốt hơn rõ, khoảng 0,43 so với 0,29.
> - **Mô hình đọc code tốt hơn các cách đơn giản:** nó vượt cả cách đếm từ khoá trong diff (TF-IDF) lẫn con vẹt ở những lần hỏng đầu tiên.
> - **HCL hiện mới ngang cách huấn luyện thông thường** khi so trên toàn bộ dữ liệu, nhưng giữ được kết quả ổn định khi dữ liệu huấn luyện bị lệch, còn cách thông thường thì tụt. Em đang thử thêm hai tình huống mà cách học bằng so sánh thường mạnh: khi có ít nhãn, và khi dự đoán cho dự án chưa từng thấy.

[Chỉ nói phần này khi được hỏi. Cập nhật lại sau khi có kết quả hai thí nghiệm mới.]

---

## Câu hỏi có thể gặp (trả lời ngắn)

**"Đoán trước thì được gì, dev vẫn phải đọc lỗi?"**
> Dạ đúng, nó không thay việc đọc lỗi. Lợi ích nằm ở quy mô lớn: bỏ bớt những lần chạy chắc chắn ổn, cho phần dễ hỏng chạy trước để biết lỗi sớm, và báo trước cho người review loại lỗi có thể gặp.

**"Sao không dùng luôn kết quả lần trước cho nhanh?"**
> Dạ em vẫn dùng nó làm một nguồn thông tin. Nhưng em chấm riêng ở lần hỏng đầu tiên, nơi thông tin đó vô dụng, để chứng minh mô hình thật sự học được từ code.

**"Nhỡ mô hình không hơn được thì sao?"**
> Dạ em vẫn báo cáo trung thực. Bộ dữ liệu có nhãn loại lỗi lấy từ nhật ký thật, cùng bảng so sánh công bằng giữa các phương pháp, bản thân chúng cũng là đóng góp của đề tài.

**"Không có GPU mạnh thì làm sao?"**
> Dạ em chạy huấn luyện trên Kaggle, được dùng GPU miễn phí khoảng 30 giờ mỗi tuần, đủ cho các thí nghiệm của đề tài.

**"Nhãn loại lỗi có đáng tin không?"**
> Dạ em lấy nhãn từ chính nhật ký lỗi, ví dụ dòng "COMPILATION ERROR" là lỗi biên dịch, và đã đọc kiểm tra lại một mẫu bằng tay. Những lần hỏng do máy chủ chứ không phải do code đều được tách riêng.
