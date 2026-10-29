# Cây nhãn 3 tầng: artifact → thời điểm cần sửa → loại lỗi

Bản ghi ngày 25/10/2026, theo góp ý của GVHD ở buổi 23/10. Ghi âm `recording/20261023_095224.m4a` đã được chép lời bằng
Whisper, bản chép ở `data/transcripts/` (không đưa vào git).

**Trạng thái (26/10):** người dùng CHỐT 2 artifact (Dự án / Môi trường CI); đã đưa vào `project3.model.labels` (GROUP/PARENT; cây cũ ở CAUSE_*). Kiểm chứng lá: `pipeline.leaf_review`, bảng `docs/gan-la-2026-10-26.xlsx`.

Thay cho:
- cây theo nguyên nhân ngày 22/10 (`docs/khung-nhan-loi-build.md`, change/external → code/buildsys/ci_infra/flaky → lá);
- phương án 2 trục độc lập location × stage (`docs/nhan-2-truc-va-du-lieu-chon-loc-2026-10-25.md`). Phương án này hiểu
  sai ý GV: GV **không** bảo bỏ cây.

## 1. GV nói gì (trích bản chép lời; Whisper chép sai một số chữ)

| Phút | Nội dung |
|---|---|
| 00:17–00:37 | Lỗi runner: "làm luôn nó là **cái đối tượng mà chứa cái thay đổi**"; lỗi của runner thì đưa thẳng vào đó |
| 00:37–00:59 | "Không cần phải nhiều tầng quá". Chỉ gom các nút con dưới một cha khi chúng **có đặc tính chung** |
| 01:05–01:14 | Một tầng là "**vị trí xảy ra thay đổi** … nó là cái **artifact**" |
| 01:29–01:53 | Tầng nữa là "giai đoạn hoặc impact … **thời điểm mà mình nên phát hiện ra lỗi**"; "ta tìm ở chỗ này nhưng ta sửa ở chỗ này" (đoạn này chép lộn xộn, cần nghe lại) |
| 03:47–04:10 | "**Nguyên nhân với nguồn là hai câu chuyện khác nhau**. Nguồn là cái vật chứa" |
| 03:12 | "Ba tầng em nên xem lại và em **có thể đảo**" |
| 04:29–04:34 | "Một tầng là **loại lỗi**, một tầng là **artifact chứa lỗi**, một tầng là **thời điểm cần phải sửa đổi**" |
| 04:45–05:03 | Nhãn phải "liên quan trực tiếp đến những **hành động sau này**"; "người ta sửa vào lúc nào thì cái đó là quan trọng" |

## 2. Cây đề xuất (phương án A: 2 artifact)

```
Tầng 1: ARTIFACT          Tầng 2: THỜI ĐIỂM CẦN SỬA     Tầng 3: LOẠI LỖI                         Số run
──────────────────────────────────────────────────────────────────────────────────────────────────────
Dự án            ──┬── Khi viết code .......... compile, quality, doc, buildconfig       20.954
(mã + cấu hình     ├── Build local trước push . testfailure, license, compatibility,     23.068
 build)            │                            dependency
                   └── CI trước merge ......... itestfailure, flaky                       8.920

Môi trường CI    ──┬── Sửa cấu hình CI ........ git, androidsdk, infra                    1.123
(runner, mạng,     └── Chạy lại ............... network, crash                            5.436
 secrets)
```

Số run lấy từ `data/run_dataset` ngày 25/10, đã gồm đợt r3; tổng 59.501 run có nhãn. Mọi nút cha có ≥ 2 con. Nguyên tắc
này giữ vì trước đây từng bị nhận xét là cây có nút một con.

Đặc tính chung của từng nhóm ở tầng 2:

| Nút | Đặc tính chung |
|---|---|
| Khi viết code | IDE hoặc trình biên dịch báo ngay khi mở/build dự án; lỗi pom và build.gradle cũng hiện ngay lúc import |
| Build local trước push | Chỉ lộ ra khi chạy `mvn verify` / `gradle check`: chạy test, tải phụ thuộc, kiểm tra license/API |
| CI trước merge | Cần môi trường CI mới thấy: test tích hợp, emulator, test chập chờn |
| Sửa cấu hình CI | Lỗi lặp lại do thiết lập: quyền git, SDK Android, secrets |
| Chạy lại | Lỗi ngẫu nhiên của hạ tầng, chạy lại là qua |

**So với cây 22/10:**
- Tầng 1 mới gần giống change/external, nhưng tiêu chí khác. Cây cũ chia theo **nguyên nhân** (lỗi có do commit không),
  cây mới chia theo **vật chứa** lỗi.
- Tầng 2 (thời điểm cần sửa) là phần mới.
- Lá giữ nguyên 15 lá Rausch, nên dữ liệu và code HCL dùng tiếp được; chỉ phải đổi bảng cha–con.

## 3. "Chỗ tìm thấy lỗi" và "vật chứa lỗi" khác nhau

| | Là gì | Vai trò |
|---|---|---|
| Chỗ tìm thấy lỗi | step / goal Maven / task Gradle / module / file mà log báo lỗi (`project3.crawl.stages`) | **Đầu vào** của mô hình; thông tin kèm theo khi báo cáo |
| Vật chứa lỗi (tầng 1) | Dự án / Môi trường CI | Nhãn |
| Thời điểm cần sửa (tầng 2) | 5 giá trị ở trên | Nhãn |
| Loại lỗi (tầng 3) | 15 lá | Nhãn |

Ví dụ: test fail vì container DB không khởi động được. Lỗi **tìm thấy** ở `FooIT`, step "Run integration tests", nhưng
**vật chứa** là Môi trường CI.

Phần này trả lời câu GV hỏi ở phút 14–16 (vì sao chia đầu vào như vậy): log được chia theo step/goal/task vì đó chính
là chỗ tìm thấy lỗi. Mô hình đọc chỗ tìm thấy để suy ra vật chứa và thời điểm cần sửa.

Thông tin kèm theo, không đưa vào cây:
- đường dẫn file lỗi (`src/main` hay `src/test`): có ở 84–100% run compile/quality/doc;
- dependency tách thành "thiếu artifact" (2.116 run, 128 repo) và "xung đột/lệch phiên bản" (603 run, khoảng 40 repo).

## 4. Ứng dụng vào quy trình DevOps

```
Dev push / mở PR → CI chạy → FAIL → [mô hình đọc log, gán 3 tầng] → hành động tự động / gửi đúng người
```

**Tầng 1 quyết định AI xử lý:**
- Dự án → người viết PR, **chặn merge**.
- Môi trường CI → nhóm DevOps; không đổ lỗi cho PR.

**Tầng 2 quyết định LÀM GÌ:**

| Nút | Hành động ngay | Cải tiến quy trình |
|---|---|---|
| Khi viết code | Báo dev file/dòng lỗi | Bật pre-commit hook / kiểm tra trong IDE (shift-left) |
| Build local | Nhắc dev chạy `mvn verify` / `gradle check` trước khi push | Đưa vào hướng dẫn đóng góp |
| CI trước merge | Báo dev xem test tích hợp | Bình thường: CI sinh ra để bắt loại lỗi này |
| Sửa cấu hình CI | Gửi DevOps (thiếu secret, SDK, quyền git) | Sửa workflow một lần |
| Chạy lại | **Tự động chạy lại** | Theo dõi độ ổn định của runner |

**Tầng 3** là nội dung chi tiết của thông báo, kèm đoạn log bằng chứng.

Ví dụ comment của bot trên PR:
> Lỗi thuộc **Môi trường CI → Chạy lại → network** (HTTP 503 khi tải artifact). Không phải lỗi của PR này. Đã tự
> động chạy lại.

> Lỗi thuộc **Dự án → Khi viết code → quality** (spotless: `Foo.java` sai format). Chạy `mvn spotless:apply` rồi push
> lại; gợi ý bật pre-commit hook.

**Giá trị cho trưởng nhóm (thống kê theo tháng):**
- bao nhiêu % fail là lỗi môi trường (tầng 1);
- bao nhiêu % lẽ ra bắt được lúc viết code (tầng 2);
- có cần đầu tư runner ổn định hơn không (nút "chạy lại").

**Use case cho hội đồng (yêu cầu ngày 10/10):**
- Actor: reviewer / trưởng nhóm quyết định merge.
- Thời điểm can thiệp: ngay khi CI fail trên PR.
- Giá trị so với để CI chạy tự nhiên: không phải đọc log, tự chạy lại lỗi ngẫu nhiên, gửi đúng người.

Trên dữ liệu hiện có, 6.559 / 59.501 run fail (11%) thuộc nhánh Môi trường CI; khoảng 5.400 thuộc nút "Chạy lại".

## 5. Điểm còn mở

1. **2 artifact hay 3 artifact** (Code / Cấu hình build / Môi trường CI)?
   - Với 3 artifact, nhánh Cấu hình build chỉ có buildconfig (khi viết code) và dependency (build local), tức là các nút
     chỉ có một lá.
   - Thêm lá (tách dependency) vẫn không sửa được, vì vấn đề nằm ở tầng thời điểm.
   - Câu hỏi gửi GV: *"Nhánh cấu hình build chỉ có buildconfig và dependency, khi chia theo thời điểm cần sửa thì mỗi
     nút chỉ còn 1 lá. Em gộp artifact thành Dự án / Môi trường CI, hay giữ 3 artifact và chấp nhận ngoại lệ ở nhánh
     build?"*
2. **Thứ tự tầng.** GV nói "có thể đảo".
   - Đặt thời điểm ở gốc hợp với câu chuyện use case.
   - Nhưng khi đó nút artifact bị lặp dưới nhiều gốc, và tầng mang tính quy ước nhất nằm ở gốc.
   - Quyết định sau khi đo độ đồng thuận người gán của tầng thời điểm.
3. **Tầng thời điểm có phần quy ước** (license bắt ở IDE hay ở build local?). Cần gán mù để đo đồng thuận.
4. **Ngoại lệ làm tầng 2 có thông tin riêng ngoài loại lỗi**, cần đo xem nhiều hay ít:
   - lỗi chỉ fail ở một biến thể ma trận (OS/JDK) → chuyển sang CI trước merge;
   - lỗi môi trường lặp lại mọi lần → sửa cấu hình CI chứ không phải chạy lại.
5. **Nhánh Môi trường CI ít run** (khoảng 6.500 so với 53.000 của nhánh Dự án). Đợt crawl Android (kernel
   `p3-crawl-android`) sẽ bù một phần.
