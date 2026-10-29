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
  B("**Đầu vào mô hình (đề xuất):** chia đầu vào thành 3 phần, mỗi phần ứng với một tầng của cây nhãn: **đổi gì** (tóm tắt diff ứng với tầng 1), **hỏng ở bước nào** (giai đoạn và công cụ bị fail ứng với tầng 2), **hỏng ra sao** (khối log quanh chỗ lỗi ứng với tầng 3). Mỗi phần được kiểm chứng bằng ablation."),

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
  P("Mô hình cũ lấy 8 đoạn log **ở cuối log**, luân phiên giữa các job fail, cộng thêm tên workflow / job / step. Cách chọn này **theo vị trí**, không gắn với tầng nhãn nào. Kết quả baseline tuần này cũng cho thấy hạn chế của cách lấy theo vị trí: BERT chỉ đọc 512 token cuối log đạt macro-F1 mức lá 0,462, thấp hơn TF-IDF đọc 30.000 ký tự (0,674)."),

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
  P("**Trạng thái:** phần trích giai đoạn và công cụ fail đã xong; phần chọn khối log lỗi, tóm tắt diff và nhánh đặc trưng trong mô hình chưa cài đặt."),

  H1("3. Việc tiếp theo"),
  N("Cài đặt đầu vào mới: chọn khối log theo giai đoạn / công cụ fail, tóm tắt diff, nhánh đặc trưng có cấu trúc trong mô hình."),
  N("Đo tỉ lệ run có dòng bằng chứng trong đầu vào (cách mới so với cách cũ)."),
  N("Huấn luyện mô hình đầy đủ trên cây nhãn mới (5 fold chéo repo), chạy ablation A1–A6 trên Kaggle, so với các baseline."),
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
