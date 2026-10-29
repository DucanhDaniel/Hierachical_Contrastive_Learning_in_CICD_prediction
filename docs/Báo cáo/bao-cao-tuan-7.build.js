// Báo cáo tuần 7 (22/10 – 28/10/2026). Chạy: node build.js <đường dẫn .docx>
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType,
  HeadingLevel, AlignmentType, LevelFormat, BorderStyle, PageNumber, Footer,
} = require("docx");

const W = 9638; // A4, lề 2 cm
const FONT = "Arial";

// **đậm** trong chuỗi
function runs(text, opts = {}) {
  return text.split(/(\*\*[^*]+\*\*)/).filter(Boolean).map((s) =>
    s.startsWith("**") ? new TextRun({ text: s.slice(2, -2), bold: true, ...opts }) : new TextRun({ text: s, ...opts }));
}
const P = (t, o = {}) => new Paragraph({ children: runs(t), spacing: { after: 120 }, ...o });
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const B = (t, level = 0) => new Paragraph({ children: runs(t), numbering: { reference: "bul", level }, spacing: { after: 60 } });
const N = (t, instance = 1) => new Paragraph({ children: runs(t), numbering: { reference: "num", level: 0, instance }, spacing: { after: 60 } });
const CAP = (t) => new Paragraph({ children: [new TextRun({ text: t, italics: true, size: 18 })], spacing: { before: 60, after: 200 } });
const Q = (t) => new Paragraph({ children: [new TextRun({ text: t, italics: true })], indent: { left: 540 }, spacing: { after: 100 } });

const border = { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" };
const borders = { top: border, bottom: border, left: border, right: border };
function table(head, rows, widths, opts = {}) {
  const sum = widths.reduce((a, b) => a + b, 0);
  const ws = widths.map((w) => Math.round((w / sum) * W));
  ws[ws.length - 1] += W - ws.reduce((a, b) => a + b, 0);
  const cell = (t, i, isHead, hl) => new TableCell({
    width: { size: ws[i], type: WidthType.DXA }, borders,
    shading: isHead ? { type: ShadingType.CLEAR, fill: "1F4E79", color: "auto" } : hl ? { type: ShadingType.CLEAR, fill: "E2EFDA", color: "auto" } : undefined,
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: [new Paragraph({
      alignment: i > 0 && !isHead && /^[−+\-]?[\d.,%$ /≈→<>~—()]+$/.test(String(t).replace(/\*\*/g, "")) ? AlignmentType.RIGHT : AlignmentType.LEFT,
      children: runs(String(t), isHead ? { size: 18, color: "FFFFFF", bold: true } : { size: 18 }),
    })],
  });
  return new Table({
    width: { size: W, type: WidthType.DXA }, columnWidths: ws,
    rows: [new TableRow({ tableHeader: true, children: head.map((h, i) => cell(h, i, true)) }),
      ...rows.map((r, ri) => new TableRow({ children: r.map((c, i) => cell(c, i, false, (opts.hl || []).includes(ri))) }))],
  });
}
const gap = () => new Paragraph({ spacing: { after: 60 }, children: [] });

const body = [
  new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun("BÁO CÁO TUẦN 7")] }),
  P("Đề tài: Phân loại nguyên nhân lỗi build CI/CD theo cây nhãn phân cấp"),
  P("Thời gian: thứ Năm 22/10/2026 – thứ Tư 28/10/2026"),

  H1("0. Tóm tắt"),
  B("**Crawl có chọn lọc thay cho crawl ngẫu nhiên:** 2 đợt chạy trên Kaggle. Đợt 3 nhắm các workflow có lá hiếm (19 repo), đợt Android nhắm lỗi môi trường theo góp ý của cô (59 repo). Tổng dữ liệu: **278 repo, 124.708 run fail, 61.602 run có nhãn quy tắc và có log**."),
  B("**Kết quả crawl:** buildconfig +57%, androidsdk gấp đôi (228 → 468), doc +25%; nhánh Môi trường CI tăng thêm 407 run. Không thêm được mẫu flaky, compatibility và gần như không thêm crash. 41% run Android quy tắc chưa gán được, cao hơn mức 32% của dữ liệu cũ."),
  B("**Đầu vào mô hình:** chia đầu vào thành 3 phần, mỗi phần ứng với một tầng của cây nhãn: **đổi gì** (tóm tắt diff ứng với tầng 1), **hỏng ở bước nào** (giai đoạn và công cụ bị fail ứng với tầng 2), **hỏng ra sao** (khối log quanh chỗ lỗi ứng với tầng 3). Khối log lỗi chứa dòng bằng chứng ở **84%** run, so với 56% khi lấy theo vị trí cuối log."),
  B("**Gán lại nhãn lỗi hết bộ nhớ (OOM):** 508 run đổi nhãn. Chủ yếu là 443 run của một repo Android trước đây bị gán nhầm lint; 182 run trong số đó thật ra là hết bộ nhớ (lá crash)."),
  B("**Kết quả 5 fold trên nhãn mới:** mô hình đề xuất (v10) đạt macro-F1 **0,719 / 0,817 / 0,885** (lá / tầng 2 / tầng 1), cao nhất trong các mô hình chạy trên toàn bộ dữ liệu nhưng chỉ hơn baseline TF-IDF có cấu trúc 0,006 ở mức lá. Khi log bị che dòng bằng chứng, v10 vẫn thua baseline này ở mức lá (0,620 so với 0,653). Các lá còn yếu: infra, doc, buildconfig."),

  H1("1. Kết quả crawl"),
  H2("1.1. Mục tiêu"),
  P("Sau 2 đợt crawl ngẫu nhiên (200 repo), các lá hiếm vẫn rất ít mẫu, và nhánh Môi trường CI (git, androidsdk, infra, network, crash) chỉ chiếm khoảng 11% số run có nhãn. Tuần này em không crawl thêm repo ngẫu nhiên mà **chọn workflow theo lá cần bổ sung**. Mọi đợt crawl đều chạy bằng notebook trên Kaggle."),
  B("**Đợt 3 (lá hiếm):** dò mẫu khoảng 6 run fail mỗi workflow ứng viên, gán lá bằng quy tắc, chấm điểm = số run fail × tỉ lệ lá hiếm trong mẫu. Chọn 22 workflow ở 20 repo, nhắm buildconfig (7), flaky (6), compatibility (4), doc (3), license (3)."),
  B("**Đợt Android (lỗi môi trường):** tìm repo Android/Kotlin trên GitHub, chỉ giữ repo **≥ 50 sao** (bỏ repo cá nhân build APK fail liên tục), workflow còn hoạt động và có **≥ 10 run fail**. Chọn 60 workflow ở 60 repo, mỗi workflow tối đa 200 run. Đợt này không lấy mẫu trước, vì đợt 3 cho thấy mẫu 6 run/workflow ước lượng kém."),

  H2("1.2. Số lượng theo đợt"),
  table(["Đợt", "Repo", "Run fail", "Run có log", "Có nhãn quy tắc", "Chưa gán được (?)", "Tỉ lệ ?"], [
    ["Đợt 1 + 2 (ngẫu nhiên)", "200", "117.384", "84.099", "57.549", "26.550", "32%"],
    ["Đợt 3 (lá hiếm)", "19", "3.044", "2.564", "1.952", "612", "24%"],
    ["Đợt Android", "59", "4.280", "3.555", "2.101", "1.454", "41%"],
    ["**Tổng**", "**278**", "**124.708**", "**90.218**", "**61.602**", "**28.616**", "**32%**"],
  ], [26, 8, 12, 12, 14, 14, 9]),
  CAP("Bảng 1. Số run theo đợt crawl. Nhãn của mọi đợt tính bằng bộ quy tắc mới nhất (phiên bản 2026-10-26, sau đợt rà soát nhãn lá). Tỉ lệ ? = chưa gán được / run có log."),

  H2("1.3. Số mẫu theo lá"),
  table(["Tầng 1", "Tầng 2", "Lá", "Đợt 1 + 2", "Đợt 3", "Android", "Tổng", "Tăng"], [
    ["Dự án", "Viết code", "compile", "10.885", "489", "575", "11.949", "+10%"],
    ["", "", "quality", "8.754", "91", "100", "8.945", "+2%"],
    ["", "", "doc", "158", "39", "0", "197", "**+25%**"],
    ["", "", "buildconfig", "291", "166", "12", "469", "**+61%**"],
    ["", "Build local", "testfailure", "18.517", "646", "470", "19.633", "+6%"],
    ["", "", "license", "421", "18", "0", "439", "+4%"],
    ["", "", "compatibility", "44", "0", "0", "44", "0"],
    ["", "", "dependency", "3.568", "105", "166", "3.839", "+8%"],
    ["", "CI / merge", "itestfailure", "8.407", "327", "442", "9.176", "+9%"],
    ["", "", "flaky", "16", "0", "0", "16", "0"],
    ["Môi trường CI", "Cấu hình CI", "git", "202", "0", "43", "245", "+21%"],
    ["", "", "androidsdk", "228", "0", "240", "468", "**+105%**"],
    ["", "", "infra", "890", "4", "17", "911", "+2%"],
    ["", "Chạy lại", "network", "2.406", "66", "22", "2.494", "+4%"],
    ["", "", "crash", "2.762", "1", "14", "2.777", "+1%"],
  ], [14, 13, 15, 11, 9, 9, 11, 9], { hl: [2, 3, 11] }),
  CAP("Bảng 2. Số run có nhãn theo lá và đợt crawl. Cột Tăng = (đợt 3 + Android) / đợt 1 + 2. Dòng tô màu là lá tăng rõ."),

  H2("1.4. Nhận xét"),
  B("**Đợt 3 có hiệu quả với buildconfig và doc** (+166 và +39 run) nhưng thấp hơn nhiều so với ước tính khi chọn (khoảng 841 run lá hiếm, thực tế khoảng 220). Mẫu 6 run/workflow quá nhỏ để ước lượng tỉ lệ lá."),
  B("**Không thêm được flaky và compatibility.** Các workflow \"flaky\" được chọn theo quy tắc cũ. Sau khi rà soát nhãn lá, quy tắc flaky được siết lại (chỉ tính khi có test FLAKY mà không có test nào thật sự fail), nên các run này chuyển thành testfailure hoặc ?. Vì vậy 2 lá này (dưới 50 mẫu) **tạm bỏ khỏi bài toán học ở mức lá**; chúng vẫn được tính ở tầng 2."),
  B("**Đợt Android làm androidsdk tăng gấp đôi** và tăng git +21%, nhánh Môi trường CI thêm 336 run. Tuy vậy **crash gần như không tăng** (+14): lỗi crash mà cô nhắc chủ yếu nằm ở dữ liệu cũ (2.762 run)."),
  B("**41% run Android quy tắc chưa gán được**, cao hơn mức 32% của dữ liệu cũ. Quy tắc hiện tại được viết cho Maven/Gradle Java, có thể chưa bao các lỗi riêng của Android. Cần đọc mẫu (open coding) để bổ sung quy tắc trước khi crawl thêm Android."),
  B("**Phân bố cuối cùng:** tầng 1 gồm Dự án 54.707 và Môi trường CI 6.895 (11%). Tầng 2 gồm Build local 23.955, Viết code 21.560, CI / merge 9.192, Chạy lại 5.271, Cấu hình CI 1.624."),
  B("**Quyết định:** tạm dừng crawl. Thêm repo ngẫu nhiên chủ yếu thêm mẫu cho các lá đã nhiều. Muốn tăng lá hiếm hiệu quả hơn thì phải có quy tắc cho các run ? trước."),

  H1("2. Đầu vào mô hình"),
  H2("2.1. Góp ý của cô"),
  P("Trong buổi họp 23/10, cô góp ý về cách chia đầu vào của mô hình:"),
  Q("\"Bản chất những kỹ thuật này thì không mới và mình cũng không cần lấy ra cái mới. Tuy nhiên nó phải trả lời được câu hỏi tại sao lại chia như thế này chứ không phải dùng những cách chia khác.\""),
  Q("\"[Cô không thấy] cái gì liên quan giữa tiêu chí chia đầu vào với cái tổ chức phân tầng mà em gán nhãn.\""),
  Q("Ví dụ học bổng: \"tiêu chí là GPA thì dữ liệu đầu vào phải là GPA… chứ không phải tất cả.\""),
  P("Mô hình cũ lấy 8 đoạn log **ở cuối log**, luân phiên giữa các job fail, cộng thêm tên workflow / job / step. Cách chọn này **theo vị trí**, không gắn với tầng nhãn nào. Kết quả baseline tuần này cũng cho thấy hạn chế của cách lấy theo vị trí: BERT chỉ đọc 512 token cuối log đạt macro-F1 mức lá 0,465, thấp hơn TF-IDF đọc 30.000 ký tự (0,676) (Bảng 8)."),

  H2("2.2. Đầu vào đề xuất: mỗi phần ứng với một tầng nhãn"),
  P("Đầu vào được chia theo cách một người chẩn đoán một lần build fail: **commit đã đổi gì**, **hỏng ở bước nào**, **hỏng ra sao**. Mỗi câu hỏi ứng với một tầng của cây nhãn."),
  table(["Phần đầu vào", "Trả lời câu hỏi", "Nội dung", "Quyết định tầng"], [
    ["1. Tóm tắt diff", "Commit này đã thay đổi gì?", "Tỉ lệ file đổi theo loại (code chính, code test, file build, workflow CI, tài liệu); số file, số dòng đổi; có diff hay không; PR hay push", "Tầng 1: Dự án hay Môi trường CI"],
    ["2. Thông tin CI", "Lỗi xảy ra ở bước nào?", "Tên workflow, job, step fail; giai đoạn fail (chuẩn bị môi trường / biên dịch / kiểm tra code / test / test tích hợp / đóng gói); công cụ fail (compiler, checkstyle, surefire, failsafe, javadoc…)", "Tầng 2: thời điểm cần sửa"],
    ["3. Khối log lỗi", "Lỗi trông như thế nào?", "Đoạn log quanh chỗ fail: log của step fail → đoạn của goal Maven / task Gradle fail → các dòng báo lỗi và vài dòng xung quanh", "Tầng 3: loại lỗi cụ thể"],
  ], [16, 18, 44, 22]),
  CAP("Bảng 3. Ba phần đầu vào và tầng nhãn mà mỗi phần giúp quyết định."),
  B("**Tóm tắt diff → tầng 1.** Commit chỉ sửa README mà build vẫn fail thì gần như chắc lỗi do môi trường (mạng, runner). Commit sửa `pom.xml` hoặc `build.gradle` rồi fail thì dễ là lỗi cấu hình build hoặc thư viện. Commit sửa file workflow thì có thể là lỗi cấu hình CI."),
  B("**Thông tin CI → tầng 2.** Giai đoạn fail cho biết lẽ ra lỗi phải được phát hiện lúc nào: fail ở biên dịch hay kiểm tra code thì sửa được ngay khi viết code; fail ở test thì chạy build ở máy là thấy; fail ở test tích hợp thì thường chỉ lộ ra trên CI; fail ở bước chuẩn bị môi trường thì là cấu hình CI hoặc chỉ cần chạy lại."),
  B("**Khối log lỗi → tầng 3.** Nội dung thông báo lỗi phân biệt các lá trong cùng một nhóm, ví dụ compile và quality, hoặc network và crash."),
  P("Thông tin giai đoạn và công cụ fail được máy trích tự động từ log: goal Maven (`maven-surefire-plugin:test`, `maven-compiler-plugin:compile`…), task Gradle (`:app:compileJava`, `:app:test`…) và tên step. Phần trích này đã được viết và kiểm thử trong tuần."),

  H2("2.3. Ví dụ"),
  table(["Phần", "Nội dung mô hình nhận"], [
    ["Khối log lỗi", "[ERROR] Tests run: 12, Failures: 1 … FooServiceTest.testSave expected <3> but was <2>, cùng vài dòng xung quanh"],
    ["Thông tin CI", "workflow CI, job build (17), step mvn verify; giai đoạn **test**; công cụ **surefire**"],
    ["Tóm tắt diff", "sửa 2 file code chính, 1 file code test, 0 file build; 40 dòng"],
    ["**Nhãn**", "Dự án → Build local → **testfailure**"],
  ], [20, 80]),
  CAP("Bảng 4. Ví dụ đầu vào của một run fail do unit test."),

  H2("2.4. Vì sao dùng tóm tắt diff thay vì toàn bộ diff"),
  B("**Đã có dữ liệu:** 93% run có nhãn đã có diff. Thiếu nhiều nhất ở buildconfig (51%) và androidsdk (49%), nên \"có diff hay không\" cũng là một đặc trưng."),
  B("**Diff đầy đủ dài và nhiễu:** diff của PR là toàn bộ thay đổi từ nhánh gốc đến commit, có thể hàng nghìn dòng. Thí nghiệm cũ chỉ đọc diff đạt khoảng 0,49 macro-F1."),
  B("**Không tranh chỗ với log:** ngân sách token của mô hình đã dành cho log. Vài chục con số tóm tắt diff không làm giảm lượng log mô hình đọc được."),
  B("**Dễ giải thích và dễ kiểm chứng:** có thể bỏ riêng phần diff ra để đo đóng góp (A6 ở Bảng 5)."),

  H2("2.5. Kiểm chứng bằng ablation"),
  P("Mỗi lựa chọn đầu vào là một giả thuyết, được kiểm chứng bằng cách bỏ riêng thành phần đó và đo xem tầng nào giảm:"),
  table(["Ablation", "Bỏ / thay", "Giả thuyết"], [
    ["A1", "Bỏ thông tin giai đoạn, công cụ fail", "Tầng 2 và tầng 1 giảm"],
    ["A2", "Khối log lỗi → 8 đoạn cuối log (như mô hình cũ)", "Mức lá giảm; tỉ lệ run có dòng bằng chứng trong đầu vào giảm"],
    ["A3", "Bỏ phân cấp (một đầu ra phẳng cho các lá)", "Tầng 1, 2 giảm khi lá sai"],
    ["A4", "Bỏ loss tương phản (chỉ dùng CE)", "Đo xem loss tương phản có giúp không"],
    ["A5", "Bỏ che dòng bằng chứng khi train", "Kết quả trên log đã che giảm mạnh"],
    ["A6", "Bỏ tóm tắt diff", "Tầng 1 và các lá buildconfig, dependency giảm"],
  ], [10, 45, 45]),
  CAP("Bảng 5. Kế hoạch ablation."),
  P("Trước khi huấn luyện, em đo trực tiếp **tỉ lệ run mà đầu vào chứa đúng dòng bằng chứng** của nhãn, so cách chọn khối log mới với cách lấy 8 đoạn cuối, để trả lời câu hỏi \"đầu vào có chứa thông tin quyết định nhãn hay không\"."),
  P("**Trạng thái:** cả 3 phần đầu vào đã cài đặt trong mô hình v10 (mục 4). Kết quả đo dòng bằng chứng trên 61.368 run:"),
  table(["Cách chọn log", "Có đoạn chứa bằng chứng", "Bằng chứng nằm trong cửa sổ mô hình đọc"], [
    ["8 đoạn cuối log (mô hình cũ)", "92,6%", "56,0%"],
    ["**Khối log lỗi (đề xuất)**", "**96,6%**", "**84,1%**"],
  ], [40, 30, 30]),
  CAP("Bảng 6. Tỉ lệ run mà đầu vào chứa dòng bằng chứng của nhãn. Cửa sổ mô hình đọc: phần của đoạn log thật sự đưa vào mô hình (khoảng 1.600 ký tự quanh chỗ lỗi với cách đề xuất, phần cuối đoạn với cách cũ). Mẫu số của cột 3 là các run có dòng bằng chứng."),
  P("Khối log lỗi đưa dòng bằng chứng vào cửa sổ đọc ở thêm 28 điểm phần trăm số run. Đây là lý do chính để chọn khối log theo chỗ fail thay vì theo vị trí cuối log."),

  H1("3. Gán lại nhãn lỗi hết bộ nhớ (OOM)"),
  H2("3.1. Vấn đề"),
  P("Khi xem kết quả theo fold, lá quality của repo nextcloud/talk-android có F1 rất thấp. Đọc log cho thấy cả **459 run** của repo này mang nhãn lint vì một quy tắc khớp dòng `FAIL: failed to run ... lint`. Dòng này do script riêng của repo in ra khi task Gradle `lint` **không chạy xong**, không phải khi lint tìm thấy vi phạm. Trong khi đó quy tắc lỗi hết bộ nhớ (`OutOfMemoryError: Java heap space`) có độ ưu tiên thấp hơn nên bị bỏ qua."),
  P("Em rà lại toàn bộ dữ liệu: **1.723 run** có dấu hiệu OOM trong log. Chỉ **369 run** có OOM là nguyên nhân duy nhất (mọi khối `What went wrong` của Gradle hoặc `Failed to execute goal` của Maven đều là OOM). 97 run có OOM kèm lỗi khác (compile, test fail); 1.239 run chỉ có OOM ở phần log phụ (ví dụ trong output của test), không phải nguyên nhân."),
  H2("3.2. Sửa quy tắc"),
  B("**Quy tắc OOM mới, xét trước các quy tắc khác:** chỉ gán infra (lá crash) khi mọi khối lỗi tổng kết đều là OOM và không có lỗi compile hoặc test fail đi kèm."),
  B("**Quy tắc lint của talk-android:** chỉ áp dụng khi log có dòng `warning count increased` (lint thật sự tìm thấy vi phạm mới)."),
  B("**Bỏ từ khoá \"Metaspace\"** khỏi nhận diện crash vì khớp nhầm tham số `-XX:MaxMetaspaceSize` trong cấu hình JVM."),
  table(["Đổi nhãn", "Số run"], [
    ["lint → infra (crash)", "182"],
    ["lint → ? (chưa gán được)", "261"],
    ["test → infra (crash)", "32"],
    ["? → infra (crash)", "30"],
    ["compile / dependency → infra (crash)", "3"],
    ["**Tổng**", "**508**"],
  ], [70, 30]),
  CAP("Bảng 7. Số run đổi nhãn sau khi sửa quy tắc (phiên bản quy tắc 2026-10-28-oom)."),
  P("261 run talk-android chuyển sang ? vì log đã crawl chỉ giữ khoảng 6 KB cuối job, phần `What went wrong` bị cắt nên không xác định được nguyên nhân. Sau khi gán lại: crash 3.028 run (trước đó 2.777), quality 8.502 run (trước đó 8.945). 188/190 run của tập gán tay vẫn còn trong dữ liệu. Không có run gán tay nào bị đổi nhãn."),

  H1("4. Kết quả huấn luyện trên nhãn mới"),
  H2("4.1. Thiết lập"),
  B("**Dữ liệu:** 61.368 run có nhãn, 13 lá được học (compatibility 44 run và flaky 16 run vẫn có trong tập test nhưng không mô hình nào dự đoán được)."),
  B("**Chia dữ liệu:** 5 fold chéo repo (repo ở tập test không xuất hiện khi train). Mọi mô hình chấm trên **cùng** tập test ở mỗi fold. Chỉ số: macro-F1 ở lá, tầng 2, tầng 1, trung bình 5 fold."),
  B("**Log đầy đủ / log che:** \"che\" là xoá dòng bằng chứng mà quy tắc dùng để gán nhãn, nhằm đo xem mô hình có chỉ học lại quy tắc hay không."),
  B("**Mô hình đề xuất (v10):** UniXcoder đọc khối log lỗi (512 token), cộng thông tin CI và tóm tắt diff; đầu ra phân cấp 3 tầng. Huấn luyện trên GPU L4 (Colab), khoảng 70 phút mỗi fold."),
  B("**Baseline:** B0 (lớp đông nhất; chỉ tên workflow/job/step), B1 TF-IDF trên log, B2 BERT 512 token cuối log (theo poster ICSE 2024), B3 LLM theo LogSage (ASE 2025). Thêm TF-IDF + đặc trưng có cấu trúc (thông tin CI, tóm tắt diff) để tách đóng góp của đặc trưng khỏi đóng góp của mô hình ngôn ngữ."),

  H2("4.2. So sánh trên toàn bộ dữ liệu"),
  table(["Mô hình", "Lá", "Tầng 2", "Tầng 1", "Lá (che)", "Tầng 2 (che)", "Tầng 1 (che)"], [
    ["B0 lớp đông nhất", "0,036", "0,113", "0,470", "0,036", "0,113", "0,470"],
    ["B0 tên workflow/job/step", "0,200", "0,370", "0,583", "0,200", "0,370", "0,583"],
    ["B1 TF-IDF log", "0,676", "0,729", "0,873", "0,611", "0,694", "0,831"],
    ["B2 BERT 512 token cuối", "0,465", "0,604", "0,782", "0,423", "0,586", "0,754"],
    ["TF-IDF + thông tin CI", "0,702", "0,797", "0,877", "0,641", "0,758", "0,846"],
    ["TF-IDF + thông tin CI + diff", "0,713", "0,800", "0,880", "**0,653**", "0,761", "**0,850**"],
    ["**v10 (đề xuất)**", "**0,719**", "**0,817**", "**0,885**", "0,620", "**0,768**", "0,849"],
  ], [30, 10, 10, 10, 10, 11, 11], { hl: [6] }),
  CAP("Bảng 8. Macro-F1 trung bình 5 fold chéo repo, nhãn quy tắc phiên bản 2026-10-28-oom. Độ lệch chuẩn giữa các fold ở mức lá khoảng 0,065–0,08."),
  B("**v10 cao nhất ở cả 3 tầng khi log đầy đủ.** Khoảng cách rõ nhất ở tầng 2 (+0,017 so với TF-IDF có cấu trúc), và v10 cũng ổn định hơn giữa các fold (độ lệch chuẩn tầng 2: 0,028 so với 0,044). Ở mức lá chỉ hơn 0,006, nhỏ hơn nhiều so với độ dao động giữa các fold."),
  B("**Khi che bằng chứng, v10 thua ở mức lá** (0,620 so với 0,653), còn tầng 2 và tầng 1 ngang nhau. Tức là v10 dựa vào dòng bằng chứng nhiều hơn TF-IDF."),
  B("**Đặc trưng có cấu trúc đóng góp rõ:** thêm thông tin CI và diff vào TF-IDF tăng mức lá từ 0,676 lên 0,713 và tầng 2 từ 0,729 lên 0,800. Điều này ủng hộ cách chia đầu vào ở mục 2."),
  B("**BERT 512 token cuối thấp hơn TF-IDF rất nhiều** (0,465 so với 0,676), vì 512 token cuối log thường không chứa dòng lỗi (Bảng 6)."),
  B("**Fold 4 khó với mọi mô hình:** v10 đạt 0,603 ở mức lá, TF-IDF có cấu trúc 0,606, trong khi các fold khác khoảng 0,68–0,78."),

  H2("4.3. F1 theo từng lá"),
  table(["Lá", "Số run", "TF-IDF", "TF-IDF + CI + diff", "BERT", "v10"], [
    ["git", "245", "0,45", "0,47", "0,12", "**0,73**"],
    ["license", "439", "0,55", "0,56", "0,67", "**0,81**"],
    ["androidsdk", "468", "0,60", "0,67", "0,31", "**0,70**"],
    ["itestfailure", "9.167", "0,60", "0,86", "0,62", "**0,88**"],
    ["testfailure", "19.607", "0,83", "0,92", "0,74", "**0,93**"],
    ["compile", "11.947", "0,89", "**0,94**", "0,73", "0,91"],
    ["quality", "8.502", "0,90", "**0,92**", "0,73", "0,90"],
    ["network", "2.492", "0,74", "0,73", "0,60", "0,74"],
    ["crash", "3.028", "0,71", "0,71", "0,62", "0,71"],
    ["dependency", "3.838", "**0,83**", "**0,83**", "0,55", "0,80"],
    ["buildconfig", "469", "0,88", "**0,89**", "0,31", "0,76"],
    ["doc", "197", "0,69", "**0,70**", "0,12", "0,58"],
    ["infra", "909", "**0,49**", "0,47", "0,20", "0,30"],
  ], [20, 12, 14, 20, 12, 12], { hl: [10, 11, 12] }),
  CAP("Bảng 9. F1 từng lá, log đầy đủ, trung bình 5 fold. Dòng tô màu là các lá v10 thua rõ."),
  B("**v10 mạnh ở các lá môi trường và lá cần ngữ cảnh:** git (+0,26), license (+0,25), androidsdk, itestfailure."),
  B("**v10 yếu ở infra, doc, buildconfig.** Đây là 3 lá ít mẫu (197–909 run), và lá infra là \"lỗi môi trường khác\" không khớp git/network/androidsdk/crash nên nội dung rất đa dạng. Ba lá này kéo macro-F1 mức lá của v10 xuống."),

  H2("4.4. So sánh với LLM (B3) trên tập con"),
  P("Baseline LLM (B3, LogSage với Gemini 3.5 Flash-Lite) chỉ chạy trên 365 run, lấy ngẫu nhiên tối đa cùng một số run cho mỗi lá, vì chi phí gọi API. Vì lá hiếm chiếm tỉ trọng lớn hơn nhiều so với toàn bộ dữ liệu, số liệu ở đây không so trực tiếp với Bảng 8 được. Các mô hình khác được chấm lại trên đúng 365 run này:"),
  table(["Mô hình", "Lá", "Tầng 2", "Tầng 1", "Lá (che)", "Tầng 2 (che)", "Tầng 1 (che)"], [
    ["B2 BERT", "0,403", "0,499", "0,743", "0,350", "0,488", "0,710"],
    ["B1 TF-IDF", "0,580", "0,628", "0,855", "0,519", "0,579", "0,817"],
    ["TF-IDF + CI + diff", "0,601", "0,693", "0,839", "0,555", "0,651", "0,824"],
    ["v10", "0,632", "0,724", "0,876", "0,579", "0,670", "0,824"],
    ["**B3 LLM (LogSage)**", "**0,805**", "**0,840**", "**0,919**", "**0,689**", "**0,734**", "**0,875**"],
  ], [30, 10, 10, 10, 10, 11, 11]),
  CAP("Bảng 10. Macro-F1 trên 365 run của tập đánh giá LLM. Nhãn đúng là nhãn quy tắc mới (2026-10-28-oom)."),
  P("Trên tập con có nhiều lá hiếm, LLM vượt rõ mọi mô hình học có giám sát (lá 0,805 so với 0,632 của v10). Trong các mô hình học có giám sát, v10 vẫn tốt nhất. Kết quả này cho thấy lá hiếm là điểm yếu chung của mô hình học có giám sát. Theo góp ý của cô, LLM chỉ dùng làm baseline."),

  H1("5. Việc tiếp theo"),
  N("Cải thiện các lá yếu (infra, doc, buildconfig): phân tích lỗi của v10 trên các lá này, xem đầu vào có chứa bằng chứng không, thử tăng trọng số lá hiếm."),
  N("Chạy ablation A1–A6 trên nhãn mới (Bảng 5)."),
  N("Gán mù khoảng 30 run có OOM kèm lỗi khác để kiểm tra quy tắc OOM mới."),
  N("Đọc mẫu các run Android quy tắc chưa gán được để bổ sung quy tắc; sau đó mới quyết định có crawl thêm hay không."),
];

const doc = new Document({
  creator: "project3",
  title: "Báo cáo tuần 7",
  styles: {
    default: { document: { run: { font: FONT, size: 22 } } },
    paragraphStyles: [
      { id: "Title", name: "Title", basedOn: "Normal", run: { font: FONT, size: 36, bold: true, color: "1F4E79" }, paragraph: { alignment: AlignmentType.CENTER, spacing: { after: 120 } } },
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 28, bold: true, color: "1F4E79" }, paragraph: { spacing: { before: 280, after: 120 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 24, bold: true, color: "2E75B6" }, paragraph: { spacing: { before: 200, after: 100 }, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [
    { reference: "bul", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } },
      { level: 1, format: LevelFormat.BULLET, text: "–", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 1080, hanging: 270 } } } }] },
    { reference: "num", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 300 } } } }] },
  ] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], size: 18 })] })] }) },
    children: body,
  }],
});
Packer.toBuffer(doc).then((b) => { fs.writeFileSync(process.argv[2], b); console.log("ok", process.argv[2]); });
