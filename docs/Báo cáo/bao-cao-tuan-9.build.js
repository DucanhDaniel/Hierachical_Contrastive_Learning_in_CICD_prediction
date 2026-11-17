// Báo cáo tuần 9 (05/11 – 12/11/2026). Chạy: node bao-cao-tuan-9.build.js <đường dẫn .docx>
// Số liệu ví dụ: data/results/typical_examples/examples.json (chọn từ run người gán lá, xem mục 1.3).
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType,
  HeadingLevel, AlignmentType, LevelFormat, BorderStyle, PageNumber, Footer, ImageRun, TableLayoutType,
} = require("docx");

const W = 9638; // A4, lề 2 cm
const FONT = "Arial";
const ROOT = path.join(__dirname, "..", "..");
const EX = JSON.parse(fs.readFileSync(path.join(ROOT, "data/results/typical_examples/examples.json"), "utf8"));

// **đậm** và `mã` trong chuỗi
function runs(text, opts = {}) {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/).filter(Boolean).map((s) => {
    if (s.startsWith("**")) return new TextRun({ text: s.slice(2, -2), bold: true, ...opts });
    if (s.startsWith("`")) return new TextRun({ text: s.slice(1, -1), font: "Consolas", ...opts, size: (opts.size || 22) - 2 });
    return new TextRun({ text: s, ...opts });
  });
}
const P = (t, o = {}) => new Paragraph({ children: runs(t), spacing: { after: 120 }, ...o });
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const B = (t, level = 0) => new Paragraph({ children: runs(t), numbering: { reference: "bul", level }, spacing: { after: 60 } });
const N = (t, instance = 1) => new Paragraph({ children: runs(t), numbering: { reference: "num", level: 0, instance }, spacing: { after: 60 } });
const CAP = (t) => new Paragraph({ children: [new TextRun({ text: t, italics: true, size: 18 })], spacing: { before: 60, after: 200 } });
const CODE = (t) => new Paragraph({ children: [new TextRun({ text: t, font: "Consolas", size: 16 })], indent: { left: 540 },
  spacing: { after: 0 } });
const Q = (t) => new Paragraph({ children: [new TextRun({ text: t, italics: true })], indent: { left: 540 }, spacing: { after: 100 } });

const border = { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" };
const borders = { top: border, bottom: border, left: border, right: border };
function table(head, rows, widths, opts = {}) {
  const sum = widths.reduce((a, b) => a + b, 0);
  const ws = widths.map((w) => Math.round((w / sum) * W));
  ws[ws.length - 1] += W - ws.reduce((a, b) => a + b, 0);
  const size = opts.size || 18;
  const cell = (t, i, isHead) => new TableCell({
    width: { size: ws[i], type: WidthType.DXA }, borders,
    shading: isHead ? { type: ShadingType.CLEAR, fill: "1F4E79", color: "auto" } : undefined,
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: String(t).split("\n").map((line) => new Paragraph({
      alignment: i > 0 && !isHead && /^[−+\-]?[\d.,%/ ]+$/.test(line.replace(/\*\*/g, "")) ? AlignmentType.RIGHT : AlignmentType.LEFT,
      children: runs(line, isHead ? { size, color: "FFFFFF", bold: true } : { size }),
    })),
  });
  return new Table({
    width: { size: W, type: WidthType.DXA }, columnWidths: ws, layout: TableLayoutType.FIXED,
    rows: [new TableRow({ tableHeader: true, children: head.map((h, i) => cell(h, i, true)) }),
      ...rows.map((r) => new TableRow({ children: r.map((c, i) => cell(c, i, false)) }))],
  });
}
function IMG(file, widthPx = 600) {
  const data = fs.readFileSync(path.join(__dirname, file));
  const w = data.readUInt32BE(16), h = data.readUInt32BE(20);
  return new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120 },
    children: [new ImageRun({ type: "png", data, transformation: { width: widthPx, height: Math.round(widthPx * h / w) } })] });
}

const f2 = (x) => x.toFixed(2).replace(".", ",");
// ô "lần chạy": repo · bước bị lỗi · công cụ, kèm xác suất mô hình và vòng gán
function runCell(id, step) {
  const e = EX[id];
  const m = e.p === null ? "mô hình: chưa học lá này" : `mô hình: ${f2(e.p)}`;
  return `**${e.repo}**\nbước: ${step}\n${m}${e.blind ? " · gán mù" : ""}`;
}
// số run theo lá (data/kaggle_log_ds/runs.parquet, nhãn quy tắc 2026-10-29b-doc)
const CNT = { testfailure: "19.553", compile: "12.083", itestfailure: "9.167", quality: "8.427", dependency: "3.892",
  crash: "3.028", network: "2.598", infra: "685", buildconfig: "546", androidsdk: "509", license: "439", doc: "320",
  git: "245", compatibility: "44", flaky: "16" };
const L = (leaf) => `**${leaf}**\n(${CNT[leaf]} run)`;
const HEAD = ["Lá", "Lần chạy", "Dòng log chính", "Vì sao thuộc lá này và nhánh này"];
const WID = [14, 21, 30, 35];

const body = [
  new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun("BÁO CÁO TUẦN 9")] }),
  P("Đề tài: Phân loại nguyên nhân lỗi build CI/CD theo cây nhãn phân cấp"),
  P("Thời gian: thứ Năm 05/11/2026 – thứ Năm 12/11/2026"),

  H1("0. Tóm tắt"),
  B("**Ví dụ điển hình cho từng nhãn (theo góp ý của cô ngày 05/11):** mỗi lá trong 15 lá có 2 lần chạy CI thật, tổng 30 ví dụ ở 27 repo. Mỗi ví dụ kèm dòng log chính, lý do thuộc lá đó, lý do thuộc nhánh cha và việc người sửa cần làm."),
  B("**Cách chọn:** chỉ lấy lần chạy mà người gán tay, bộ quy tắc và mô hình đề xuất cùng ra một lá. Ưu tiên vòng gán mù (người gán không xem nhãn quy tắc). 19/30 ví dụ đến từ vòng gán mù."),
  B("**Lá có chắc chắn nằm đúng nhánh không:** trên 188 lần chạy người đã gán, quy tắc khớp người 84,6% ở mức lá, 86,7% ở tầng 2 và 97,3% ở tầng 1. Trong 29 lần chạy gán sai lá, 25 lần sai luôn nhánh tầng 2 nhưng chỉ 5 lần sai tầng 1. Ranh giới yếu nhất là **test đơn vị và test tích hợp** (11/29 lần lệch)."),
  B("**Tính toàn vẹn của đầu vào (mục 2):** log, thông tin CI, diff và nhãn của một lần chạy đều gắn với cùng lần chạy và cùng commit. GitHub đọc file workflow từ chính commit đó, chạy lại thì giữ nguyên commit. Phần đổi theo thời gian nằm ngoài commit: 28,3% lần chạy dùng action không cố định phiên bản. 10,6% lần chạy PR không có diff, nhưng mô hình đoán đúng gần như ngang nhóm có diff (90,8% so với 91,1%), nên không cần lấy lại."),
  B("**Mô hình có chỉ học lại quy tắc không (mục 3):** trên 65 lần chạy quy tắc không gán được, mô hình vẫn đúng lá 54% (đoán ngẫu nhiên khoảng 8%, TF-IDF 31%, LLM 77%). Nhưng trên các lần chạy quy tắc gán được, mô hình chưa vượt quy tắc (74% so với 84% khi so với nhãn người)."),
  B("**Công trình liên quan (mục 4):** 14 công trình và công cụ. Bộ nhãn GitHub Actions mới nhất (Zheng và cộng sự, TOSEM) chia lỗi dự án / môi trường giống tầng 1 của đề tài và có nhóm tương ứng cho 13/15 lá. Em giữ nguyên cây nhãn hiện tại. Catalog lỗi lấy từ dữ liệu ở Phụ lục B."),
  B("**Cách cắt log (mục 5):** log đã được cắt theo step, goal Maven và task Gradle (69% lần chạy có bằng chứng nằm trọn trong một khối như vậy). Chỗ cô nói đúng: 42% số đoạn vẫn là cửa sổ 40 dòng cắt đều từ khối dài (output test, stack trace). Em đã thử cắt theo đơn vị ngữ nghĩa (từng test case, stack trace, thông báo lỗi) và huấn luyện lại trên GPU: macro-F1 không tốt hơn (mức lá −0,023, trong khoảng nhiễu) vì cách cắt mới làm mất ngữ cảnh quanh dòng lỗi. Em giữ cách cắt hiện tại."),
  B("**Demo (mục 6):** bấm dòng log để mở đúng file và dòng code tại commit của lần chạy. Có link ở 71–75% lần chạy lỗi compile, doc và buildconfig; 58/60 link thử mở được."),
  B("**Truy vết đến mức code (mục 7):** em giao cho agent lập trình (Claude Code) tự đọc code của repo để tìm file gây lỗi, thử trên 60 lần chạy và 3 cách đưa đầu vào. Trên 41 lần chạy có bản sửa thật, agent đặt file đã sửa vào 3 file đầu ở mọi lần chạy (cách khớp tên file trong log được 70%). LLM chấm nguyên nhân đúng 95% khi agent nhận đoạn trích và loại lỗi, có quyền tự mở log đầy đủ, so với 82% khi chỉ có đoạn trích. Mỗi lượt dùng trung bình khoảng 117 nghìn token đầu vào (84% đọc lại từ bộ nhớ đệm), 1,9 nghìn token đầu ra, 9 bước, tương đương 0,21 USD theo bảng giá API."),
  B("**Dòng nguyên nhân (mục 7.7):** em thêm vào mô hình phân loại một đầu ra chấm điểm từng dòng log. Đầu ra này đưa dòng nguyên nhân lên đầu ở 85% lần chạy (90% với lỗi test, so với 4% của phần chú ý cũ), phân loại gần như giữ nguyên (Macro-F1 lá 0,755 so với 0,786, nằm gần mức dao động giữa các lần chạy). Khi agent chỉ nhận loại lỗi và 5 dòng này kèm vài dòng xung quanh (60 lần chạy), chọn file ngang log đầy đủ và token đầu vào giảm 16–21%, nhưng giải thích đúng hoàn toàn 46/60 so với 55/60, chưa đạt mức em đặt ra. Nguyên nhân chính là khối log mô hình đọc thường không chứa thông báo lỗi thật của lỗi test và lỗi thư viện."),
  B("**Kiểm tra trên benchmark ngoài (mục 7.8):** trên 45 lỗi Java của GHA-Bench và LogDx-CI, với đáp án là bản sửa thật, agent nhận loại lỗi và dòng nguyên nhân của mô hình giải thích đúng 39/45 so với 42/45 khi đọc log đầy đủ, chọn file kém 1 lỗi, nhưng token đầu vào giảm 39%. Dòng do mô hình chọn tốt hơn rõ so với cách lọc dòng có chữ error/fail (34/45)."),

  H1("1. Ví dụ điển hình cho từng nhãn"),
  H2("1.1. Góp ý của cô"),
  P("Trong buổi họp ngày 05/11, khi em trình bày cây nhãn mới, cô hỏi:"),
  Q("\"Liệu một lá ở tầng 3 có chắc chắn là nó nằm ở trong nhánh đấy không? Nếu mà nó chắc chắn thì bây giờ em phải đưa ra cho cô một loạt tất cả các ví dụ điển hình (...) cứ mỗi nhãn em cho cô 2 cái ví dụ điển hình.\""),
  P("Mục này trả lời câu hỏi theo 2 phần: 30 ví dụ điển hình (mục 1.4) và số đo cho thấy lá thuộc đúng nhánh chắc chắn đến đâu (mục 1.5)."),

  H2("1.2. Cây nhãn đang dùng"),
  IMG("hinh-tuan-7/cay-nhan-v2.png", 520),
  CAP("Hình 1. Cây nhãn 3 tầng: tầng 1 là nơi chứa lỗi, tầng 2 là cách xử lý, tầng 3 là loại lỗi (15 lá)."),
  P("Lưu ý về tên tầng 2: buổi 23/10 cô đề xuất tầng 2 là \"thời điểm cần sửa\". Khi dựng cây, em thấy nhánh Môi trường CI không có trục thời gian. Ví dụ, lỗi mạng hay runner sập không có \"thời điểm lẽ ra phải sửa\". Vì vậy em đổi tên tầng 2 thành **\"Cách xử lý (cần làm gì tiếp?)\"**. Cách chia lá vào nhánh giữ nguyên như tuần 7."),

  H2("1.3. Cách chọn ví dụ"),
  P("Ví dụ được chọn trong **188 lần chạy người đã gán lá** ở 2 đợt kiểm chứng nhãn (26–27/10): 147 lần chạy gán khi có gợi ý của AI và 41 lần chạy gán mù. Điều kiện chọn:"),
  N("Nhãn của người, nhãn của bộ quy tắc và dự đoán của mô hình đề xuất **trùng nhau**. Riêng compatibility (44 run) và flaky (16 run), mô hình không học vì quá ít mẫu, nên chỉ cần người và quy tắc trùng nhau.", 1),
  N("Ưu tiên lần chạy của vòng gán mù, sau đó ưu tiên lần chạy mô hình tự tin cao. **Độ tự tin** là xác suất mô hình gán cho lá đúng, từ 0 đến 1.", 1),
  N("Hai ví dụ của cùng một lá nên khác repo và khác công cụ build (Maven và Gradle), để thấy lá không chỉ gắn với một dự án.", 1),
  P("Thứ tự ưu tiên ở trên là em tự đặt. Kết quả: 19/30 ví dụ đến từ vòng gán mù, 27 repo khác nhau. Mô hình tự tin ≥ 0,94 ở 24/26 ví dụ thuộc các lá mô hình có học. Riêng flaky, cả 16 run đều của apache/kafka, vì sau lần siết quy tắc ngày 26/10 (chỉ gán flaky khi không có test nào fail hẳn), chỉ còn kafka thoả điều kiện. Link từng lần chạy ở Phụ lục A."),

  H2("1.4. Ví dụ theo từng nhánh"),

  // ---------- Dự án → Sửa code theo thông báo lỗi
  P("**Nhánh 1. Dự án → Sửa code theo thông báo lỗi** (compile, quality, doc, buildconfig). Đặc điểm chung: thông báo lỗi chỉ thẳng file và dòng cần sửa. Developer sửa được ngay mà không cần chạy lại gì. Có thể chặn từ trước khi commit bằng IDE hoặc hook kiểm tra."),
  table(HEAD, [
    [L("compile"), runCell("36118196536", "Build container image (Maven)"),
      "`ColumnAliasUtils.java:[42,42] cannot find symbol` (4 lỗi cùng loại)",
      "Trình biên dịch Java báo đúng file và dòng: code trong PR gọi tới lớp không tồn tại. Tên workflow là \"Run auth IdP tests\" nhưng lỗi thật là biên dịch, và mô hình vẫn đoán đúng compile. Vậy mô hình không chỉ dựa vào tên workflow."],
    ["", runCell("33605430789", "Build with Gradle"),
      "`SchemaService.java:297: error: illegal start of expression`",
      "Lỗi cú pháp trong code Java, biên dịch bằng Gradle. Developer sửa đúng dòng được chỉ ra."],
    [L("quality"), runCell("37233394433", "Run spotless (Gradle)"),
      "`> Task :spotlessJavaCheck FAILED`\n`The following files had format violations`",
      "Code chạy đúng nhưng sai định dạng. Công cụ còn chỉ sẵn lệnh tự sửa (`spotlessApply`)."],
    ["", runCell("33112335120", "Run pre-commit checks (Maven)"),
      "`spotless-maven-plugin:3.10.0:check ... format violations` kèm đoạn khác biệt định dạng",
      "Cùng loại lỗi trên Maven, chạy trong hook pre-commit. Chính dự án đã chặn loại lỗi này từ trước khi commit, đúng với đặc điểm của nhánh."],
    [L("doc"), runCell("30558252737", "Install with Maven"),
      "`SequenceWriter.java:43: error: reference not found` (javadoc)",
      "Chú thích javadoc `{@link ...}` trỏ tới hàm không còn tồn tại. Bước sinh tài liệu dừng build. Sửa ngay trong chú thích."],
    ["", runCell("32093672464", "Build with Gradle (workflow JavaDoc Generation)"),
      "`AbstractContract.java:312: error: reference not found`",
      "Cùng loại lỗi, chạy bằng Gradle ở một dự án khác."],
    [L("buildconfig"), runCell("38213355743", "Build product-apim with Test (Maven)"),
      "`'build.plugins.plugin.(groupId:artifactId)' must be unique but found duplicate declaration of plugin ...replacer @ line 720`",
      "File cấu hình build (pom.xml) khai báo trùng một plugin. Maven dừng ngay khi đọc pom, trước khi biên dịch dòng code nào. Sửa đúng dòng 720 của pom."],
    ["", runCell("36865855643", "Check default Kotlin configuration (Gradle)"),
      "`build.gradle.kts line 57: Script compilation error: Unresolved reference 'swagger'`",
      "File build Gradle gọi `libs.swagger.models` nhưng thư viện này chưa được khai báo trong danh mục phiên bản của dự án. Lỗi nằm ở file build, không ở code chính. LLM gán lá này là dependency (xem mục 1.5)."],
  ], WID),
  CAP("Bảng 1. Ví dụ nhánh Dự án → Sửa code theo thông báo lỗi. \"Mô hình\" là độ tự tin của mô hình đề xuất cho lá đúng."),

  // ---------- Dự án → Tái hiện lỗi ở local để sửa
  P("**Nhánh 2. Dự án → Tái hiện lỗi ở local để sửa** (testfailure, dependency, license, compatibility). Đặc điểm chung: lỗi chỉ lộ ra khi chạy đủ các bước kiểm tra của build (`mvn verify`, `gradle check`), và log CI thường không đủ để sửa. Developer chạy lại đúng lệnh đó ở máy mình là tái hiện được, không cần môi trường CI đặc biệt."),
  table(HEAD, [
    [L("testfailure"), runCell("36112314591", "Build and test (Gradle)"),
      "`Execution failed for task ':waltid-verifier-api2:test'.`\n`There were failing tests. See the report at: .../index.html`",
      "Unit test không đạt. Log chỉ trỏ tới file báo cáo nằm trên máy CI, nên developer phải chạy lại test của module đó ở máy để xem test nào hỏng và vì sao."],
    ["", runCell("30448850537", "Maven Tests"),
      "`[ERROR] Tests run: 212, Failures: 6, Errors: 0, Skipped: 0`",
      "Cùng loại lỗi trên Maven: 6 unit test không đạt."],
    [L("dependency"), runCell("34398997078", "Build and Run Unit Tests (Maven)"),
      "`Could not find artifact org.apache.accumulo:accumulo-server-base:jar:4.0.0-SNAPSHOT`",
      "Dự án phụ thuộc vào bản SNAPSHOT (bản chưa phát hành) không có trên kho thư viện. Kho vẫn truy cập được, chỉ là không có bản đó. Sửa phiên bản khai báo trong pom."],
    ["", runCell("30292857425", "Build with Maven (JDK 11)"),
      "`rdf4j-model-api-6.0.0.jar ... class file has wrong version 69.0, should be 55.0`",
      "Thư viện rdf4j 6.0.0 được build cho Java 25 (mã 69), còn job chạy Java 11 (mã 55). Trình biên dịch báo lỗi, nhưng nguyên nhân là nâng thư viện lệch phiên bản Java, nên thuộc dependency (quyết định ngày 18/10)."],
    [L("license"), runCell("33505166385", "Build & test Kubernetes modules (Maven)"),
      "`license-maven-plugin:5.1.1:check ... Some files do not have the expected license header`",
      "Có file thiếu phần ghi bản quyền ở đầu file. Bước kiểm tra chỉ chạy trong build đầy đủ. Chạy `license:format` ở máy là sửa được."],
    ["", runCell("35698987009", "Run dev/check-license (Apache RAT)"),
      "`Files with missing headers:`\n`ERROR: Unexpected count for UNAPPROVED, limit is [0,0]. Count: 1`",
      "Cùng loại lỗi với công cụ khác (Apache RAT)."],
    [L("compatibility"), runCell("29624940292", "Compare API"),
      "`There is at least one incompatibility: ...SegmentContext.getQueryableDocIdsSnapshot():METHOD_REMOVED`",
      "PR xoá một hàm public, làm hỏng tương thích với các bản đã phát hành. Cần giữ lại hàm hoặc đổi số phiên bản."],
    ["", runCell("32897014410", "Install (Maven, japicmp)"),
      "`japicmp-maven-plugin:0.26.1:cmp ... Versions of archives indicate a patch change but binary compatible changes found`",
      "Phiên bản chỉ tăng số nhỏ (patch) nhưng API đã thay đổi. Cần tăng số phiên bản cho đúng hoặc giữ nguyên API."],
  ], WID),
  CAP("Bảng 2. Ví dụ nhánh Dự án → Tái hiện lỗi ở local để sửa."),

  // ---------- Dự án → Sửa dựa trên kết quả CI
  P("**Nhánh 3. Dự án → Sửa dựa trên kết quả CI** (itestfailure, flaky). Đặc điểm chung: cần môi trường của CI mới thấy lỗi (server chạy thật, container, máy ảo Android, hoặc chạy nhiều lần), nên khó tái hiện ở máy. Developer phải đọc báo cáo test do CI sinh ra."),
  table(HEAD, [
    [L("itestfailure"), runCell("32139180837", "Run Maven Integration Tests"),
      "`AuditEventRestRepositoryIT.findByObjectPaginationTest:389 Status expected:<200> but was:<404>`\n`Tests run: 3658, Failures: 4`",
      "Test tích hợp (lớp có đuôi IT) gọi REST API của server đang chạy thật. Workflow chỉ dành cho test tích hợp, chạy hàng nghìn test, khó chạy lại toàn bộ ở máy."],
    ["", runCell("32697723195", "Android Tests"),
      "`Tests on emulator-5554 - 6.0 failed: There was 1 failure(s).`\n`> Task :composeunstyled-drawer:connectedDebugAndroidTest FAILED`",
      "Test giao diện chạy trên máy ảo Android do CI dựng sẵn (Android 6.0)."],
    [L("flaky"), runCell("34227123431", "Parse JUnit tests (Gradle)"),
      "`38482 PASSED ✅, 0 FAILED ❌, 4 FLAKY ⚠️ ...`",
      "Không có test nào fail hẳn: 4 test fail lần đầu rồi đạt khi CI tự chạy lại, nhưng CI vẫn đánh cả lần chạy là fail. Không phải sửa code của PR mà phải xem lịch sử các test chập chờn đó trên CI."],
    ["", runCell("32029382436", "Parse JUnit tests (Gradle)"),
      "`Found 2 flaky test failures:`\n`37452 PASSED ✅, 0 FAILED ❌, 2 FLAKY ⚠️ ...`",
      "Cùng kiểu, ở một PR khác của cùng dự án. Cả 16 run flaky đều thuộc apache/kafka."],
  ], WID),
  CAP("Bảng 3. Ví dụ nhánh Dự án → Sửa dựa trên kết quả CI."),

  // ---------- Môi trường CI → Sửa cấu hình CI
  P("**Nhánh 4. Môi trường CI → Sửa cấu hình CI** (git, androidsdk, infra). Đặc điểm chung: lỗi nằm ở file workflow, secrets, quyền hoặc thiết lập runner, không nằm ở code dự án. Chạy lại vẫn lỗi cho tới khi sửa cấu hình. Người xử lý thường là người phụ trách CI."),
  table(HEAD, [
    [L("git"), runCell("31807933110", "Publish Doc"),
      "`! [remote rejected] main -> main (cannot lock ref 'refs/heads/main' ...)`\n`failed to push some refs to '.../***.github.io.git'`",
      "Workflow đẩy tài liệu sang một repo khác thì bị từ chối. Bước này không liên quan tới code của PR."],
    ["", runCell("36412755108", "Create Pull Request if Needed"),
      "`error: failed to push some refs to 'https://github.com/ABKQPO/GT-Not-Leisure'`",
      "Workflow tự nén ảnh rồi tự tạo PR, nhưng không đẩy được nhánh lên repo. Cần sửa quyền hoặc cấu hình của bước tạo PR."],
    [L("androidsdk"), runCell("31213609264", "Run Tests (runner macOS)"),
      "`adb: device 'emulator-5554' not found`\n`error: could not connect to TCP port 5554: Connection refused`",
      "Máy ảo Android chưa khởi động xong khi bước test bắt đầu. Sửa thiết lập máy ảo hoặc thời gian chờ trong workflow."],
    ["", runCell("37627644375", "Run tests (API Level 35)"),
      "`Failed to download package archive for emulator: ... Peer disconnected`\n`error: could not connect to TCP port 5554`",
      "Tải gói máy ảo thất bại nên máy ảo không chạy được. Đây là ví dụ ở ranh giới: nguyên nhân đầu tiên là tải qua mạng (LLM gán network), còn người gán theo dòng lỗi cuối là androidsdk (xem mục 1.5)."],
    [L("infra"), runCell("30521241291", "Cache Operand Images"),
      "`Can't find 'action.yml' ... under '.github/actions/operand-cache'. Did you forget to run actions/checkout before running your local action?`",
      "Workflow gọi một action nằm trong repo trước khi lấy code về máy chạy. Sửa thứ tự các bước trong file workflow."],
    ["", runCell("31369405471", "Run actions/create-github-app-token@v3"),
      "`Failed to create token for \"vespaai\": A JSON web token could not be decoded`",
      "Khoá bí mật (secret) của GitHub App bị sai hoặc hết hạn. Cần cập nhật secret, không sửa code. Mô hình đúng lá nhưng chỉ tự tin 0,64: infra là lá yếu nhất của mô hình."],
  ], WID),
  CAP("Bảng 4. Ví dụ nhánh Môi trường CI → Sửa cấu hình CI."),

  // ---------- Môi trường CI → Kiểm tra hạ tầng ngoài
  P("**Nhánh 5. Môi trường CI → Kiểm tra hạ tầng ngoài** (network, crash). Đặc điểm chung: lỗi do dịch vụ hoặc máy nằm ngoài dự án; code và cấu hình không cần đổi. Người xử lý kiểm tra trạng thái dịch vụ hoặc runner rồi chạy lại. Nếu lỗi lặp lại thường xuyên thì thêm cơ chế thử lại, cache, hoặc đổi sang runner lớn hơn."),
  table(HEAD, [
    [L("network"), runCell("31117484257", "Set up job"),
      "`Failed to resolve action download info. Error: Service Unavailable`",
      "GitHub không tải được action ngay ở bước khởi tạo job, trước khi chạy dòng code nào của dự án. Dịch vụ phía GitHub báo không phục vụ được."],
    ["", runCell("35073268552", "Compile and unit test with JDK 21 (Maven)"),
      "`Could not transfer artifact org.graalvm.python:python-language:jar:24.1.1 from/to central (...): Connection reset`",
      "Cùng câu mở đầu \"Could not resolve dependencies\" với lá dependency, nhưng ở đây thư viện có thật trên kho, chỉ là kết nối bị ngắt khi tải. Chạy lại là qua (quyết định của người gán ngày 27/10)."],
    [L("crash"), runCell("34950793280", "Assemble (flavor Gplay)"),
      "`##[error]The runner has received a shutdown signal.`\n`##[error]The operation was canceled.`",
      "Máy chạy CI bị tắt giữa chừng, không có lỗi nào từ build. Đây là kiểu phổ biến nhất của crash (khoảng 58% số run). Các kiểu khác là hết bộ nhớ (khoảng 21%) và quá thời gian (khoảng 11%)."],
    ["", runCell("36812519004", "Build Job ubuntu-latest - Java 17"),
      "`The runner has received a shutdown signal.`\n`make: *** [Makefile:65: check] Error 143`",
      "Cùng kiểu ở dự án khác. Mã 143 nghĩa là tiến trình build bị hệ thống buộc dừng, không phải build tự báo lỗi."],
  ], WID),
  CAP("Bảng 5. Ví dụ nhánh Môi trường CI → Kiểm tra hạ tầng ngoài."),

  H2("1.5. Lá có chắc chắn nằm đúng nhánh không?"),
  P("Theo cách dựng cây, mỗi lá chỉ có một nhánh cha. Vì vậy câu hỏi của cô thực chất là: **khi một lần chạy bị gán sai lá, nó có bị đưa sang nhầm nhánh không?** Em đo trên 188 lần chạy người đã gán lá, so nhãn người với nhãn quy tắc:"),
  table(["Tập", "Số lần chạy", "Khớp ở lá", "Khớp ở tầng 2", "Khớp ở tầng 1"], [
    ["Cả 2 vòng gán", "188", "84,6%", "86,7%", "97,3%"],
    ["Riêng vòng gán mù", "41", "73,2%", "82,9%", "95,1%"],
  ], [30, 15, 18, 18, 19]),
  CAP("Bảng 6. Mức khớp giữa nhãn quy tắc và nhãn người ở từng tầng. Vòng có gợi ý AI cho số cao hơn vì người gán bị gợi ý dẫn dắt."),
  P("Có 29 lần chạy bị quy tắc gán sai lá. Bảng 7 chia các lần lệch theo ranh giới:"),
  table(["Ranh giới (người → quy tắc)", "Số lần", "Hệ quả", "Vì sao khó tách"], [
    ["Test tích hợp ↔ unit test", "11", "Sai tầng 2, đúng tầng 1", "Quy tắc dựa vào công cụ chạy test (surefire/failsafe, task test/connectedAndroidTest), nhưng nhiều dự án chạy test tích hợp bằng chính công cụ unit test."],
    ["infra → network, crash", "5", "Sai tầng 2, đúng tầng 1", "Cùng triệu chứng (dịch vụ test không lên, quá thời gian), nhưng một bên do cấu hình CI, một bên do hạ tầng ngoài."],
    ["dependency → buildconfig, compile", "3", "Sai tầng 2, đúng tầng 1", "Khai báo thư viện nằm trong file build, nên lỗi phụ thuộc và lỗi cấu hình build dễ lẫn nhau (như ví dụ walt-id ở Bảng 1)."],
    ["network → androidsdk", "1", "Sai tầng 2, đúng tầng 1", "Tải gói máy ảo thất bại (như ví dụ sentry-java ở Bảng 4)."],
    ["Lệch sang nhánh khác ở tầng 1", "5", "Sai cả tầng 1", "Hết bộ nhớ khi biên dịch (2), lỗi phụ thuộc bị gán là mạng hoặc hạ tầng (2), test tích hợp bị gán là hạ tầng (1)."],
    ["Lệch lá trong cùng nhánh", "4", "Đúng tầng 2", "compile ↔ doc, buildconfig; infra ↔ git, androidsdk."],
  ], [26, 9, 20, 45]),
  CAP("Bảng 7. 29 lần chạy quy tắc gán khác người, chia theo ranh giới giữa các lá."),
  B("**Tầng 1 gần như chắc chắn (97%):** gán sai lá rất hiếm khi làm nhầm giữa \"lỗi của dự án\" và \"lỗi của môi trường CI\"."),
  B("**Tầng 2 kém chắc chắn hơn:** 25/29 lần gán sai lá thì sai luôn nhánh tầng 2. Chỗ yếu tập trung ở một ranh giới là **test đơn vị và test tích hợp** (11/29). Hai loại này khác cách xử lý (tái hiện được ở local hay phải dựa vào CI) nhưng log rất giống nhau. Em giữ nguyên cách chia này trong cây nhãn."),
  B("**Các ví dụ ranh giới đã nằm sẵn trong 30 ví dụ:** walt-id (buildconfig hay dependency), aws-athena (dependency hay compile), sentry-java (androidsdk hay network), langchain4j (network hay dependency). Ở 2/4 ví dụ (walt-id, sentry-java), LLM đưa ra lá khác người, cho thấy các ranh giới này cũng khó với mô hình ngôn ngữ lớn."),

  // ======================= 2. TOÀN VẸN DỮ LIỆU =======================
  H1("2. Tính toàn vẹn của dữ liệu đầu vào"),
  H2("2.1. Góp ý của cô"),
  Q("\"Tất cả các thông tin đưa vào trong quá trình inference có cần phải lấy tại cùng một thời điểm không (...) Trong trường hợp mình ghép nó vào tại những thời điểm độc lập với nhau thì tính toàn vẹn của dữ liệu đấy nó còn được đảm bảo không?\""),
  P("Cô lấy ví dụ: người dùng có thể quay lại một commit cũ và chạy với một workflow khác, vậy làm sao biết log sinh ra từ workflow nào. Mục này kiểm tra câu hỏi đó trên dữ liệu thật."),
  H2("2.2. Mỗi phần đầu vào lấy từ đâu"),
  table(["Phần đầu vào", "Lấy từ", "Gắn với"], [
    ["Log", "API của GitHub, các job của **lượt chạy cuối** của lần chạy đó (8,0% lần chạy có chạy lại)", "Đúng lần chạy (mã lần chạy)"],
    ["Thông tin CI (tên workflow, job, step)", "API của chính lần chạy, **không** đọc từ file workflow hiện tại của repo", "Đúng lần chạy"],
    ["Thống kê diff", "Diff của commit mà lần chạy build (head_sha). Với push: so với commit cha. Với PR: phần thay đổi của PR so với điểm tách khỏi nhánh chính", "Đúng commit của lần chạy"],
    ["Nhãn", "Bộ quy tắc chạy trên chính log ở trên", "Đúng lần chạy"],
  ], [24, 52, 24]),
  CAP("Bảng 9. Nguồn của từng phần đầu vào."),
  P("Theo tài liệu GitHub Actions, file workflow được đọc từ chính commit được push (sự kiện push), hoặc từ **commit gộp tạm** giữa PR và nhánh đích tại lúc chạy (sự kiện pull_request). Khi bấm chạy lại, GitHub dùng lại đúng commit và nhánh của lần chạy đầu. Dữ liệu của đề tài chỉ gồm 2 sự kiện này (110.725 lần chạy PR, 13.983 lần chạy push), nên trường hợp \"chạy commit cũ với workflow khác\" không xảy ra: muốn đổi workflow thì phải tạo commit mới, và đó là một lần chạy khác với mã khác. 13,6% diff trong dữ liệu có sửa chính file workflow; với các lần chạy này, workflow mới nằm sẵn trong commit và log là của workflow mới."),
  H2("2.3. Những chỗ dữ liệu không được bảo đảm"),
  table(["Chỗ có thể lệch", "Số đo", "Ảnh hưởng"], [
    ["Action ghi theo tag chính (`@v4`) hoặc theo nhánh (`@main`): cùng một commit nhưng chạy lúc khác có thể dùng bản action khác", "Trong 798 nghìn lượt gọi action: 47,5% ghim theo mã commit, 18,2% theo bản cụ thể, **33,7% theo tag chính**, 0,5% theo nhánh. **28,3%** lần chạy có ít nhất một action không cố định", "Chỉ ảnh hưởng nhánh Môi trường CI. Đây đúng là loại lỗi mà nhánh này cần bắt"],
    ["Máy chạy `ubuntu-latest` đổi phiên bản theo thời gian", "Dòng ghi phiên bản máy chạy có trong 54% log đuôi đã lưu, nhưng chỉ 7% đoạn trích quanh lỗi", "Chưa đưa vào dữ liệu nên chưa đối chiếu được"],
    ["Với PR, CI build commit gộp tạm (PR + nhánh đích **lúc chạy**), còn diff chỉ chứa phần thay đổi của PR", "Chưa đo (cần git, chạy trên Kaggle)", "Lỗi do thay đổi mới trên nhánh đích (hai PR xung đột) không thấy qua diff"],
    ["Lần chạy PR không có diff (không lấy được commit, hoặc diff rỗng)", "**10,6%** lần chạy PR trong dữ liệu huấn luyện (5.654/53.315), dồn ở vài repo", "Mô hình đoán đúng 90,8%, gần ngang nhóm có diff (91,1%). Lấy lại diff chỉ tăng tối đa khoảng 0,3 điểm, nên không làm"],
    ["Log hết hạn sau 90 ngày", "27,7% lần chạy không còn log", "Lần chạy không có log bị loại, không gây lệch"],
  ], [32, 38, 30]),
  CAP("Bảng 10. Các chỗ đầu vào có thể không cùng một thời điểm."),
  P("**Kết luận:** log, thông tin CI, diff và nhãn của một lần chạy đều gắn với cùng một lần chạy và cùng một commit. Những phần thật sự đổi theo thời gian (action không ghim phiên bản, máy chạy, dịch vụ ngoài) nằm ngoài commit. Đây cũng là lý do cây nhãn có nhánh Môi trường CI. Chỗ em chưa kiểm tra được là diff so với commit gộp tạm của PR. Nó chỉ ảnh hưởng đặc trưng diff và hướng gợi ý file gây lỗi, không ảnh hưởng nhãn."),

  // ======================= 3. NHÃN QUY TẮC =======================
  H1("3. Mô hình có chỉ học lại bộ quy tắc không?"),
  P("Cô kể trường hợp nhóm của cô gán nhãn bằng công cụ quét lỗ hổng, rồi mô hình học được **hành vi của công cụ** chứ không học được nguyên nhân. Nhãn của đề tài cũng sinh từ bộ quy tắc, nên câu hỏi tương tự là: mô hình có chỉ học lại các mẫu regex không? Em có 3 phép đo:"),
  table(["Phép đo", "Cách làm", "Kết quả"], [
    ["Che dòng bằng chứng", "Lúc kiểm tra, xoá khỏi log dòng mà bộ quy tắc dùng để gán nhãn", "Macro-F1 mức lá giảm từ 0,785 xuống **0,659**. TF-IDF giảm từ 0,677 xuống 0,608. Mô hình vẫn đoán được khi thiếu đúng dòng quy tắc bám vào"],
    ["Lần chạy quy tắc không gán được", "65 lần chạy quy tắc bỏ trống, người gán tay (13 lá)", "Đúng lá: mô hình **54%**, TF-IDF 31%, LLM 77%, đoán ngẫu nhiên khoảng 8%. Đúng tầng 1: mô hình 85%. Ở đây không có dòng nào để quy tắc bám vào"],
    ["Bỏ thông tin CI", "Huấn luyện lại không có tên workflow/job/step và giai đoạn", "Mức lá giảm 0,028 (khoảng tin cậy 95%: −0,057 đến −0,008): có giúp, nhưng không phải nguồn chính. Ví dụ dhis2 ở Bảng 1: workflow tên \"Run auth IdP tests\" nhưng mô hình vẫn đoán đúng là lỗi biên dịch"],
  ], [20, 32, 48]),
  CAP("Bảng 11. Các phép đo về việc mô hình có học vượt ra ngoài bộ quy tắc không. Macro-F1 trung bình 5 lần chia dữ liệu theo repo."),
  P("Những điểm em phải thừa nhận:"),
  B("**Trên các lần chạy quy tắc gán được, mô hình chưa vượt quy tắc.** Trên 178 lần chạy người gán (13 lá), quy tắc khớp người 83,7% ở mức lá, mô hình 74,2%, LLM 80,9%. Giá trị của mô hình nằm ở các lần chạy quy tắc bỏ trống (32% lần chạy có log), nơi mô hình đạt 54% ở mức lá."),
  B("**Mô hình học theo cả lỗi của quy tắc**, giống chuyện cô kể. Tuần 7, 443 lần chạy của một repo Android bị quy tắc gán nhầm là lỗi lint (182 lần thật ra là hết bộ nhớ), và mô hình học theo. Em chỉ phát hiện được khi đọc lại lỗi của mô hình và sửa quy tắc. Vì vậy tập người gán (188 lần chạy) là thước đo chính, không phải nhãn quy tắc."),

  // ======================= 4. CÔNG TRÌNH LIÊN QUAN =======================
  H1("4. Công trình liên quan và bộ nhãn còn hợp thời không"),
  H2("4.1. Công trình có chức năng tương tự"),
  P("Theo góp ý của cô (project 3 như một đồ án tốt nghiệp thu nhỏ), em tìm các bài báo và công cụ cũng chẩn đoán lỗi CI từ log. Danh sách tài liệu ở Phụ lục C."),
  table(["Công trình", "Đầu vào → đầu ra", "Cách làm", "Khác đề tài ở đâu"], [
    ["Rausch và cộng sự, MSR 2017 [1]", "Log Travis CI → 14 loại lỗi", "Quy tắc viết tay, 14 dự án Java", "Nguồn của tầng lá; Travis, chưa có GitHub Actions"],
    ["Vassallo và cộng sự, ICSME 2017 [2]", "Log → 20 nhóm lỗi", "Phân loại tay, so sánh mã nguồn mở và công ty", "Không có mô hình tự động"],
    ["Zheng và cộng sự, TOSEM [3]", "375 lần chạy GitHub Actions lỗi → 16 nhóm nguyên nhân", "Phân loại tay + khảo sát 151 developer", "Bộ nhãn gần nhất cho GitHub Actions + Java; không có mô hình (mục 4.2)"],
    ["Lee và cộng sự, ICSE 2024 poster [4]", "Log lỗi Gradle → loại lỗi", "Fine-tune BERT", "Baseline B2 của đề tài; chỉ đọc 512 token, không dùng diff, không có nhóm môi trường"],
    ["Gradle-Autofix, IJSEKE 2022 [5]", "Thông báo lỗi Gradle → nguyên nhân + cách sửa", "Phân loại + 7 quy tắc sửa", "Chỉ lỗi script Gradle"],
    ["BuildSheriff, ICSE 2022 [6]", "Build lỗi do test + diff → nhóm theo nguyên nhân gốc", "So khớp stack trace có tính thay đổi code", "Chỉ xử lý lỗi test"],
    ["Aïdasso và cộng sự, ICSE-SEIP 2025 [7]", "Log job lỗi chập chờn → 46 loại", "Quy tắc regex gán nhãn (precision 99%) rồi xếp ưu tiên", "Chỉ lỗi chập chờn; cách gán nhãn bằng regex giống đề tài"],
    ["FlaXifyer, FSE 2026 Industry [8]", "Log job → loại lỗi chập chờn", "Fine-tune mô hình ngôn ngữ với 12 mẫu/lớp; macro-F1 84,3%", "Gần nhất về bài toán, nhưng chỉ lỗi chập chờn, dữ liệu công ty, không diff"],
    ["Ge và Zhang, 2026 (preprint) [9]", "Log GitHub Actions → có chập chờn không", "Regex gán nhãn + embedding + kNN", "Nhị phân, chỉ chập chờn"],
    ["LogSage (ByteDance), ASE 2025 Industry [10]", "Log CI → giải thích nguyên nhân + bản vá", "Lọc dòng log + LLM", "Baseline B3; trả lời dạng văn bản, không có bộ nhãn"],
    ["Valenzuela-Toledo và cộng sự, ICPC 2025 [11]", "Log GitHub Actions → giải thích", "LLM + khảo sát developer", "Không có bộ nhãn; yếu với log dài"],
    ["SAP HANA, SANER 2026 [12]", "Log Jenkins → nguyên nhân + cách xử lý", "Regex lọc log + GPT-4o + lịch sử lỗi", "Dữ liệu nội bộ một công ty"],
    ["LogSieve, MSR 2026 [13]", "Log GitHub Actions → log rút gọn cho LLM", "Bộ phân loại dòng log có liên quan", "Bước tiền xử lý; ý tưởng dùng được cho mục 5"],
    ["Gradle Develocity, Copilot \"Explain error\" [14, 15]", "Lỗi build → nhóm lỗi / giải thích", "Công cụ thương mại", "Nhãn thô hoặc không có nhãn; không công bố đánh giá"],
  ], [24, 24, 26, 26], { size: 16 }),
  CAP("Bảng 12. Các công trình và công cụ có chức năng tương tự."),
  P("**Đóng góp em có thể nhận:** chưa thấy công trình nào phân loại **mọi loại** lỗi của lần chạy GitHub Actions (không chỉ lỗi chập chờn) theo cây nhãn nhiều tầng gắn với cách xử lý, dùng cả log, diff và thông tin CI, và đo bằng tập người gán. Các phần riêng lẻ đều đã có người làm: gán nhãn bằng regex [7], phân loại log bằng mô hình ngôn ngữ [4, 8], LLM đọc log [10]."),
  H2("4.2. Bộ nhãn 2017 còn hợp thời không"),
  P("Cô nhận xét bạn cùng buổi rằng bộ dữ liệu 2017 \"10 năm rồi\". Tầng lá của đề tài cũng lấy từ một bài năm 2017 (Rausch, Travis CI). Em đối chiếu với bộ nhãn mới nhất cho GitHub Actions: Zheng và cộng sự [3] phân loại tay 375 lần chạy lỗi của 260 dự án Java."),
  B("**Tầng 1 trùng cách chia của Zheng:** họ chia lỗi do dự án (84%) và lỗi do môi trường GitHub Actions (16%), theo tiêu chí \"lỗi có còn khi chạy cùng code ở máy local không\". Đó đúng là ranh giới Dự án / Môi trường CI của đề tài."),
  B("**13/15 lá có nhóm tương ứng** (Phụ lục B). 2 nhóm của Zheng chưa có lá riêng: lỗ hổng bảo mật (15/375 run) và giảm hiệu năng (3/375 run)."),
  B("**Zheng gộp unit test và test tích hợp vào một nhóm** (102 + 18 run). Đây đúng là ranh giới yếu nhất của đề tài (mục 1.5). Dữ liệu cũng cho thấy dấu hiệu log hay gặp nhất của 2 lá này giống hệt nhau (`Tests run: N, Failures: N`, `Execution failed for task`). Em vẫn giữ 2 lá riêng vì chúng ứng với 2 cách xử lý khác nhau ở tầng 2."),
  B("**Nhánh Môi trường CI gộp nhiều nhóm của Zheng:** cấu hình workflow/secret sai, thiếu quyền, không tải được action, vượt giới hạn API đều nằm trong infra và network. Em không tách thêm lá: kiểu lớn nhất của infra là lỗi token/secret chỉ có 150 lần chạy ở 3 repo, khóa kho Maven 80 lần ở 10 repo, mà dữ liệu được chia theo repo nên lá mới gần như không có mẫu để học. Các kiểu này được ghi trong catalog (Phụ lục B)."),
  P("**Kết luận:** phần lõi của bộ nhãn 2017 (compile, test, dependency, quality, buildconfig, git, crash) vẫn khớp với dữ liệu GitHub Actions mới. Các nhóm mới riêng của GitHub Actions đã có chỗ trong nhánh Môi trường CI (infra, network). Em chốt giữ nguyên cây nhãn hiện tại."),

  // ======================= 5. CẮT LOG =======================
  H1("5. Cách cắt log"),
  P("Cô góp ý: cắt log thành các đoạn bằng nhau rồi chấm điểm theo từ khoá là sai, vì log có cấu trúc. Hôm 05/11 em trình bày chưa rõ. Thực tế log đang được cắt theo 3 bước:"),
  N("Tách theo **step** của GitHub Actions (dòng `##[group]Run ...`), bỏ phần in lại lệnh và biến môi trường.", 3),
  N("Trong mỗi step, tách theo **ranh giới công cụ**: goal Maven (`[INFO] --- plugin:goal @ module ---`), task Gradle (`> Task :x`), module của Maven Reactor. Bỏ các dòng khuôn mẫu không mang nguyên nhân.", 3),
  N("Chỉ khi một khối dài quá 40 dòng mới chia thành các cửa sổ 40 dòng (chồng nhau 5 dòng).", 3),
  P("Số đo trên 1,12 triệu đoạn của 90 nghìn lần chạy có log:"),
  B("58% số đoạn là khối nguyên vẹn (một step, goal hay task). 42% là cửa sổ cắt từ khối dài, chủ yếu là output test và stack trace."),
  B("Ở 69% lần chạy có bằng chứng, dòng bằng chứng nằm trọn trong khối nguyên vẹn. 27% chỉ nằm trong cửa sổ cắt đều, 4% ở cả hai."),
  P("Góp ý của cô đúng ở chỗ: **42% số đoạn vẫn là cửa sổ 40 dòng cắt đều** từ các khối dài, chủ yếu là output test và stack trace. Một cửa sổ có thể cắt ngang một stack trace, hoặc gộp phần cuối của test này với phần đầu của test khác. Ngoài ra, 89% lần chạy chỉ còn đoạn trích quanh dòng lỗi nên ở đó chỉ 30% đoạn còn giữ tên step."),
  H2("5.1. Thử nghiệm: cắt theo đơn vị ngữ nghĩa của log"),
  P("Em thử thay cửa sổ 40 dòng bằng việc tách khối dài theo các đơn vị có nghĩa của log, mỗi đơn vị là một sự kiện trọn vẹn:"),
  table(["Đơn vị", "Dấu hiệu bắt đầu", "Ví dụ"], [
    ["Một test case lỗi", "Dòng báo test lỗi của Maven/Gradle", "`[ERROR] FooTest.bar:42 expected:<1> but was:<2>`; `FooTest > bar() FAILED`"],
    ["Một stack trace", "Dòng ngoại lệ, kéo tới hết các dòng `at ...` và `Caused by:`", "`java.lang.NullPointerException` + các dòng `at ...`"],
    ["Một thông báo lỗi của công cụ", "Mục `* What went wrong:` (Gradle), `[ERROR] Failed to execute goal` (Maven), danh sách lỗi biên dịch", "`* What went wrong:` tới `* Try:`"],
    ["Phần còn lại", "Gom các dòng liền nhau cùng mẫu (cùng khuôn sau khi thay số, đường dẫn)", "Hàng trăm dòng `Tests run: ... in ...` của các test đạt"],
  ], [22, 38, 40]),
  CAP("Bảng 13a. Các đơn vị dùng để cắt khối dài."),
  P("Dòng cuối cùng giống cách các công cụ phân tích log gom dòng theo khuôn mẫu (log parsing, ví dụ Drain). Cách cắt theo độ giống nhau về nghĩa giữa các dòng liền kề (dùng embedding) tốn nhiều tính toán hơn mà log lại lặp nhiều, nên em thử cách theo dấu hiệu trước."),
  P("Hai yêu cầu đặt ra: mô hình phải có **đủ dữ liệu**, và phần mô hình đọc phải **chứa dòng bằng chứng**. Đo trên đường ống hiện tại, dòng bằng chứng mất nhiều nhất ở bước cắt mỗi đoạn xuống 1.600 ký tự (khoảng 512 token, giới hạn mô hình đọc một lần): 5,8% lần chạy mất ở bước này, 2,8% mất ở bước chọn 8 đoạn. Vì vậy thiết kế mới đặt mỗi đơn vị vừa sẵn 1.600 ký tự để không phải cắt mù. Các giá trị em tự đặt: đơn vị dưới 12 dòng thì gộp với đơn vị kề; khối vừa 1.600 ký tự giữ nguyên; đơn vị dài hơn thì cắt ở ranh giới bên trong, mỗi mảnh sau giữ 3 dòng đầu; mỗi đoạn kèm 5 dòng ngay trước nó. Cách chọn đoạn cũng đổi: mỗi job lỗi luôn được chọn đoạn chứa dòng báo lỗi đầu tiên."),
  H2("5.2. Kết quả đo trên dữ liệu (chưa huấn luyện)"),
  table(["", "Cách hiện tại", "Cắt mới + chọn lỗi đầu"], [
    ["Còn dòng bằng chứng trong phần mô hình đọc (lấy đều theo lá)", "91,1%", "93,5%"],
    ["Như trên, tính theo phân bố thật của dữ liệu", "93,1%", "93,4%"],
    ["Số dòng ngữ cảnh trung bình trước / sau dòng bằng chứng", "8,1 / 10,8", "6,8 / 8,0"],
    ["Lần chạy có dưới 3 dòng ngữ cảnh ở một phía", "26%", "36%"],
  ], [52, 24, 24]),
  CAP("Bảng 13b. Đo trên 9.804 lần chạy, lấy đều khoảng 1.000 lần chạy mỗi lá."),
  P("Cách mới giữ thêm bằng chứng ở các lá trước đây bị cắt mù (buildconfig 79% → 97%, compatibility 73% → 95%, dependency 84% → 96%, network 84% → 93%), nhưng ngữ cảnh quanh bằng chứng ít hơn. Tính trên phân bố thật thì tỉ lệ còn bằng chứng gần như không đổi."),
  H2("5.3. Huấn luyện thử"),
  P("Em huấn luyện lại mô hình với cách cắt mới trên GPU T4 của Kaggle, cùng cấu hình, cùng seed và cùng lần chia dữ liệu với mô hình hiện tại; chỉ khác dữ liệu đoạn log. Tập kiểm tra gồm 10.838 lần chạy của 53 repo."),
  table(["Macro-F1", "Hiện tại", "Cắt mới", "Chênh", "Khoảng tin cậy 95%"], [
    ["Lá, log đầy đủ", "0,859", "0,836", "−0,023", "[−0,074; +0,017]"],
    ["Tầng 2, log đầy đủ", "0,886", "0,892", "+0,006", "[−0,034; +0,040]"],
    ["Tầng 1, log đầy đủ", "0,913", "0,917", "+0,004", "[−0,036; +0,041]"],
    ["Lá, che dòng bằng chứng", "0,719", "0,707", "−0,012", "[−0,086; +0,054]"],
    ["Tầng 2, che dòng bằng chứng", "0,814", "0,834", "+0,021", "[−0,040; +0,085]"],
    ["Tầng 1, che dòng bằng chứng", "0,830", "0,861", "+0,031", "[−0,043; +0,123]"],
  ], [32, 14, 14, 14, 26]),
  CAP("Bảng 13c. So ghép cặp. Khoảng tin cậy tính bằng cách lấy mẫu lại repo 1.000 lần."),
  B("Mọi chênh lệch đều nằm trong khoảng nhiễu. Thời gian huấn luyện tăng 59% (2,94 giờ so với 1,85 giờ) vì mỗi lần chạy có nhiều đoạn hơn."),
  B("Theo từng lá thì lên xuống trái chiều: crash +0,06, network +0,05; khi che bằng chứng, dependency +0,16 và infra +0,12. Ngược lại doc −0,21, buildconfig −0,11, license −0,04."),
  B("Lá doc: mô hình mới bắt được gần hết lỗi doc (46/47 so với 35/47), nhưng đoán nhầm 70 lần chạy khác thành doc (trước là 8), trong đó 51 là lỗi biên dịch, riêng repo uber/NullAway chiếm 26."),
  H2("5.4. Vì sao không tốt hơn: ví dụ một lần chạy của uber/NullAway"),
  P("Lần chạy này là lỗi biên dịch. Mô hình cũ đoán đúng, mô hình mới đoán nhầm thành doc. Mục báo lỗi của Gradle dài hơn 1.600 ký tự nên cách mới phải cắt đôi:"),
  P("**Cách cũ:** một khối, lúc đọc mô hình lấy cửa sổ xoay quanh dòng lỗi, nên có cả phần trước và phần sau:"),
  ...[
    "* What went wrong: ... Compilation failed; see the compiler output below.",
    "##[error] .../OriginScanner.java:179: error: [NullAway] passing @Nullable ...",
    "      visited.add(current);",
    "  1 error",
    "* Try: > Check your code and dependencies to fix the compilation error(s)",
  ].map(CODE),
  P("**Cách mới:** đơn vị dài hơn 1.600 ký tự bị cắt khi đầy, dòng lỗi rơi xuống cuối mảnh 1:", { spacing: { before: 120, after: 120 } }),
  ...[
    "Mảnh 1:  * What went wrong: ... Compilation failed; see the compiler output below.",
    "         ##[error] .../OriginScanner.java:179: error: [NullAway] ...",
    "Mảnh 2:        visited.add(current);",
    "           1 error",
    "         * Try: > Check your code ... fix the compilation error(s)",
  ].map(CODE),
  P("Ngữ cảnh mất vì ba lý do:", { spacing: { before: 120, after: 120 } }),
  N("**Cách cũ đặt dòng lỗi vào giữa phần mô hình đọc, cách mới cắt ở vị trí cố định.** Khi một đơn vị phải cắt, phần ngay sau dòng lỗi có thể sang mảnh khác. Số đo khớp với điều này: ngữ cảnh phía sau bằng chứng giảm nhiều nhất (trung vị 11 → 7 dòng).", 4),
  N("**Đơn vị mở đầu ngay tại dòng lỗi.** Các dòng ngay trước nó, cho biết đang chạy task nào (biên dịch hay javadoc), thuộc về đơn vị trước; 5 dòng kèm thêm chỉ bù được một phần.", 4),
  N("**Mô hình đọc từng đoạn riêng rẽ** (tối đa 512 token mỗi đoạn) rồi mới gộp. Hai thông tin cùng một đoạn thì mô hình liên hệ được trực tiếp, còn khác đoạn thì yếu hơn. Lỗi javadoc và lỗi biên dịch có cùng dạng `File.java:N: error: ...`, chỉ phân biệt được nhờ dòng xung quanh.", 4),
  P("Ví dụ này cho thấy cơ chế mất ngữ cảnh, nhưng chưa chứng minh đây là nguyên nhân duy nhất: thí nghiệm mới có một lần chia và một seed."),
  H2("5.5. Kết luận"),
  P("**Em giữ cách cắt hiện tại cho mô hình chính.** Cắt theo đơn vị ngữ nghĩa giữ được nhiều dòng bằng chứng hơn ở các lá hiếm, nhưng làm mất ngữ cảnh quanh lỗi, mà với một số lá (doc, compile) chính ngữ cảnh mới phân biệt được lá. Kết quả không tốt hơn và thời gian huấn luyện tăng 59%. Cách hiện tại đã tách log theo cấu trúc (step, goal, task), chỉ phần khối quá dài mới chia cửa sổ, và lúc đọc luôn đặt dòng lỗi vào giữa."),

  // ======================= 6. DEMO =======================
  H1("6. Demo: bấm dòng log để mở mã nguồn"),
  P("Hôm 05/11 cô hỏi: bấm vào dòng log thì có mở ra mã nguồn không? Tuần này em đã thêm tính năng đó. Với mỗi dòng log làm căn cứ, demo tìm đường dẫn file và số dòng (lỗi javac, javadoc, Kotlin, file build Gradle, danh sách file sai định dạng, stack trace), rồi tạo link tới đúng file và đúng dòng **tại commit của lần chạy**. Nếu file đó có trong thay đổi của PR, demo đánh dấu để người sửa biết. File do build sinh ra (thư mục build/, target/) bị bỏ qua vì không có trong repo."),
  table(["Lá", "Có link tới file", "Có cả số dòng", "File nằm trong diff"], [
    ["compile", "75%", "69%", "43%"], ["buildconfig", "73%", "30%", "29%"], ["doc", "71%", "71%", "35%"],
    ["quality", "29%", "7%", "21%"], ["dependency", "23%", "9%", "13%"],
    ["9 lá còn lại", "0–10%", "0–5%", "0–9%"],
  ], [28, 24, 24, 24]),
  CAP("Bảng 13. Tỉ lệ lần chạy có link tới mã nguồn, 150 lần chạy PR mỗi lá (1.794 lần chạy)."),
  B("Mở thử 60 link ngẫu nhiên: 58 link đúng file. 2 link lỗi do runner Windows in đường dẫn bằng dấu `\\`, em đã sửa."),
  B("**Số liệu khớp đặc điểm nhánh 1** (Sửa code theo thông báo lỗi, mục 1.4): 71–75% lần chạy ở 3 lá chính của nhánh có link tới file. Các nhánh khác chỉ có từ 23% trở xuống."),
  B("Với lỗi test, log chỉ in tên lớp test chứ không in file gây lỗi. Chỗ này cần truy vết bằng agent (mục 7)."),

  // ======================= 7. TRUY VẾT ĐẾN MỨC CODE =======================
  H1("7. Truy vết nguyên nhân đến mức code bằng agent lập trình"),
  H2("7.1. Câu hỏi"),
  P("Mô hình phân loại cho biết lần chạy lỗi thuộc loại nào, nhưng chưa chỉ ra **file nào trong thay đổi của PR gây lỗi**. Tuần trước em đo hướng tự xây mô hình xếp hạng file, cách đơn giản nhất là ưu tiên file có tên xuất hiện trong log. Tuần này em thử cách khác: giao việc cho một **agent lập trình**, tức một mô hình ngôn ngữ lớn tự đọc code của repo như một lập trình viên. Câu hỏi là: chỉ cần đưa cho agent đoạn log và loại lỗi thì agent có tự tìm ra nguyên nhân không, và tốn bao nhiêu."),
  P("Em dùng Claude Code (mô hình Claude Opus 5.5) chạy trên máy, không tương tác. Agent chỉ được đọc file, tìm kiếm chữ và tìm file trong code của repo tại đúng commit lỗi. Agent không được sửa file, chạy lệnh hay truy cập mạng. Đầu ra theo một khuôn cố định: danh sách file nghi ngờ xếp theo mức nghi ngờ (kèm số dòng và lý do), nguyên nhân, lỗi có cần sửa code không, và độ tin cậy."),
  H2("7.2. Cách làm"),
  B("**Mẫu:** 60 lần chạy PR lỗi thuộc tầng Dự án, ở 33 repo, lấy theo chỉ tiêu từng lá: compile 10, testfailure 10, itestfailure 10, quality 8, dependency 8, buildconfig 5, license 5, doc 4. Mỗi PR thay đổi trung vị 10,5 file (từ 1 đến 417). Cả 60 lần chạy đều diễn ra từ 08/2026 đến 10/2026, sau thời điểm dữ liệu huấn luyện của mô hình kết thúc (06/2026), nên mô hình không thể đã thấy sẵn bản sửa."),
  B("**Ba cách đưa đầu vào**, mỗi lần chạy chạy cả ba:"),
  B("Cách 1, log đầy đủ: tối đa 1 MB cuối của mỗi job lỗi.", 1),
  B("Cách 2, đoạn trích và loại lỗi: đúng các đoạn log mô hình phân loại đọc, kèm nhãn mô hình phân loại dự đoán.", 1),
  B("Cách 3: như cách 2, nhưng có thêm log đầy đủ. Agent được dặn chỉ mở log đầy đủ khi đoạn trích không đủ.", 1),
  B("**Giới hạn mỗi lượt (em tự đặt):** tối đa 60 bước và 4 USD. Không lượt nào chạm giới hạn này."),
  B("**Chấm mức 1, tự động:** đáp án là các file mà commit kế tiếp làm CI chạy qua đã sửa, cách đo như báo cáo tuần trước. Em đo xem agent có đặt một file đáp án ở vị trí 1, hoặc trong 3 file đầu không."),
  B("**Chấm mức 2, dùng LLM chấm:** một lượt mô hình riêng đọc log, thay đổi của commit sửa và ba câu trả lời. Ba câu trả lời được xáo thứ tự và đổi tên thành X, Y, Z để người chấm không biết câu nào của cách nào. Mỗi nguyên nhân được chấm là đúng, đúng một phần hoặc sai. Người chấm đồng thời cho biết commit kế tiếp có thật sự sửa lỗi này không."),
  B("**Đếm token** mỗi lượt: token đầu vào (tách phần đọc lại từ bộ nhớ đệm), token đầu ra, số bước và thời gian."),
  H2("7.3. Kết quả"),
  P("Theo LLM chấm, ở **14/60 lần chạy commit kế tiếp không phải bản sửa lỗi đó**: người sửa làm việc khác, hoặc lỗi do môi trường và tự hết khi chạy lại. Có thêm 5 lần chạy không rõ. Ở các lần chạy này, đáp án mức 1 bị sai, nên em báo riêng kết quả trên **41 lần chạy commit kế tiếp thật sự là bản sửa**."),
  table(["", "Cách 1: log đầy đủ", "Cách 2: đoạn trích + loại lỗi", "Cách 3: cách 2 + được mở log đầy đủ", "Khớp tên file trong log", "Chọn ngẫu nhiên"], [
    ["File đúng ở vị trí 1 (60 lần chạy)", "0,65", "0,70", "0,68", "0,40", "0,26"],
    ["File đúng trong 3 file đầu (60 lần chạy)", "0,75", "0,82", "0,78", "0,67", "–"],
    ["File đúng ở vị trí 1 (41 lần chạy có bản sửa thật)", "0,88", "0,90", "**0,93**", "0,42", "0,22"],
    ["File đúng trong 3 file đầu (41 lần chạy)", "**1,00**", "**1,00**", "**1,00**", "0,70", "–"],
    ["LLM chấm nguyên nhân đúng (60 lần chạy)", "93%", "82%", "**95%**", "–", "–"],
    ["LLM chấm nguyên nhân đúng (41 lần chạy)", "**98%**", "80%", "95%", "–", "–"],
  ], [28, 13, 15, 16, 15, 13], { size: 18 }),
  CAP("Bảng 16. Độ đúng của agent theo ba cách đưa đầu vào. \"Khớp tên file trong log\" là cách của báo cáo tuần trước: xếp file trong diff theo số lần tên file xuất hiện trong log."),
  B("**Agent tìm đúng file tốt hơn hẳn cách khớp tên.** Trên 41 lần chạy có bản sửa thật, cả ba cách đều đặt file đã sửa vào 3 file đầu ở mọi lần chạy, còn khớp tên chỉ được 70%. Agent tìm được cả khi log không nhắc tên file, ví dụ lỗi test (log chỉ in tên lớp test) và lỗi thư viện."),
  B("**Về chọn file, ba cách gần như ngang nhau.** So từng lần chạy, số lần cách này đúng còn cách kia sai chỉ chênh 1–4 lần. Với 60 lần chạy, chênh lệch này chưa nói được cách nào hơn."),
  B("**Về giải thích nguyên nhân, cách 2 kém rõ.** So từng lần chạy: cách 3 đúng còn cách 2 không đúng ở 8 lần, chiều ngược lại 0 lần. So cách 1 với cách 2 là 9 lần và 2 lần. Đoạn trích hay thiếu thông báo lỗi chi tiết, ví dụ tên test hay tên thư viện, và cách 2 không có cách nào đọc thêm."),
  table(["Lá", "Số lần chạy", "File đúng ở vị trí 1 (cách 1 / 2 / 3)", "Nguyên nhân đúng (cách 1 / 2 / 3)"], [
    ["compile", "10", "0,60 / 0,60 / 0,60", "90% / 90% / 90%"],
    ["testfailure", "10", "0,40 / 0,60 / 0,40", "100% / 80% / 100%"],
    ["itestfailure", "10", "0,70 / 0,60 / 0,60", "100% / 90% / 100%"],
    ["quality", "8", "1,00 / 1,00 / 1,00", "100% / 88% / 100%"],
    ["dependency", "8", "0,38 / 0,62 / 0,75", "75% / **38%** / 75%"],
    ["buildconfig", "5", "1,00 / 1,00 / 1,00", "100% / 80% / 100%"],
    ["license", "5", "0,80 / 0,80 / 0,80", "100% / 100% / 100%"],
    ["doc", "4", "0,50 / 0,50 / 0,50", "75% / 100% / 100%"],
  ], [20, 14, 33, 33]),
  CAP("Bảng 17. Kết quả theo lá trên 60 lần chạy. Mỗi lá chỉ có 4–10 lần chạy nên chỉ để tham khảo."),
  P("Ở compile và testfailure, điểm chọn file thấp hơn điểm nguyên nhân, chủ yếu vì commit kế tiếp không phải bản sửa. Nhiều lần chạy testfailure là lỗi môi trường (test chập chờn, hết thời gian) và tự hết khi chạy lại: agent nói đúng là không cần sửa code, nhưng mức 1 vẫn tính là sai."),
  H2("7.4. Khối lượng token"),
  table(["Mỗi lượt", "Cách 1", "Cách 2", "Cách 3"], [
    ["Token đầu vào, trung bình", "120 nghìn", "108 nghìn", "117 nghìn"],
    ["Token đầu vào, trung vị", "98 nghìn", "81 nghìn", "88 nghìn"],
    ["Trong đó đọc lại từ bộ nhớ đệm", "84%", "83%", "84%"],
    ["Token đầu ra, trung bình", "2,1 nghìn", "2,0 nghìn", "1,9 nghìn"],
    ["Số bước, trung vị / lớn nhất", "9 / 19", "9 / 23", "9 / 25"],
    ["Thời gian, trung vị", "27 giây", "23 giây", "26 giây"],
    ["Giá theo bảng giá API, trung bình", "0,21 USD", "0,20 USD", "0,21 USD"],
  ], [40, 20, 20, 20]),
  CAP("Bảng 18. Khối lượng token trên 60 lần chạy cho mỗi cách. Em chạy bằng tài khoản Claude nên bị trừ vào hạn mức gói, không tính tiền theo token; giá ở dòng cuối tính theo bảng giá API để tham khảo."),
  B("**Token đầu vào lớn vì mỗi bước agent gửi lại toàn bộ hội thoại**, gồm các file đã đọc. Hơn 80% là phần đọc lại từ bộ nhớ đệm, rẻ hơn khoảng 10 lần so với token mới."),
  B("**Cách 2 tiết kiệm nhất, nhưng chỉ khoảng 10–17%** so với cách 1. Phần lớn token đến từ việc đọc code chứ không phải đọc log."),
  B("**Cách 3 mở log đầy đủ ở khoảng 15/60 lần chạy (25%).** Đây là ước lượng: em đếm số lần chạy mà cách 3 dùng nhiều hơn cách 2 trên 30 nghìn token đầu vào, vì bản ghi kết quả không lưu từng thao tác của agent."),
  B("Tổng chi phí của thí nghiệm theo bảng giá API: agent 37,25 USD cho 180 lượt, LLM chấm 15,24 USD."),
  H2("7.5. Ví dụ"),
  P("**apache/maven, lần chạy 35628134874 (itestfailure).** PR thay thư viện nạp lớp, và gần như mọi test tích hợp lỗi với thông báo `Failed to execute Maven`. Bản sửa là thêm thư mục chứa JLine vào cấu hình nạp lớp `m2.conf`."),
  B("Cách 2 chỉ thấy dòng tổng kết test lỗi. Agent đoán sai hướng, cho rằng lỗi ở script khởi động `mvn.cmd`, và LLM chấm là sai."),
  B("Cách 3 mở log đầy đủ, thấy `NoClassDefFoundError: org/jline/terminal/Terminal` và lần ra file `m2.conf`. LLM chấm là đúng."),
  P("**frankframework, lần chạy 34839696554 (dependency).** Lệnh `pnpm install --frozen-lockfile` lỗi vì PR thêm ràng buộc phiên bản cho thư viện `ws` nhưng không tạo lại file `pnpm-lock.yaml`. Cả ba cách đều đặt `pnpm-lock.yaml` ở vị trí 1, tức mức 1 chấm đúng cả ba."),
  B("Đoạn trích ở cách 2 không chứa thông báo `ERR_PNPM_OUTDATED_LOCKFILE`. Agent đổ lỗi cho việc đổi phiên bản pnpm, nên LLM chấm là đúng một phần."),
  B("Cách 1 và cách 3 đọc được thông báo đó và chỉ ra đúng chỗ lệch phiên bản. LLM chấm là đúng."),
  P("Ví dụ thứ hai cho thấy vì sao cần chấm mức 2: chỉ xét đúng file thì không phân biệt được agent hiểu đúng nguyên nhân hay chỉ đoán trúng file."),
  H2("7.6. Kết luận và hạn chế"),
  P("**Hướng này đáng làm, và không cần tự xây mô hình xếp hạng file.** Agent đặt file đã sửa vào 3 file đầu ở mọi lần chạy có bản sửa thật, và giải thích đúng nguyên nhân ở 95% lần chạy. Em chọn **cách 3** cho demo: đưa đoạn trích và loại lỗi mà mô hình phân loại đã có, cho agent tự mở log đầy đủ khi cần. Cách này đúng gần bằng đưa log đầy đủ và dùng lại được kết quả của mô hình phân loại. Về token thì gần như không tiết kiệm (trung bình −2,5%, trung vị −10% so với đưa log đầy đủ): agent vốn chỉ tìm và đọc phần log quanh chỗ lỗi, còn phần lớn token đến từ việc đọc code. Muốn giảm chi phí thật thì cần thử mô hình nhỏ hơn cho agent hoặc gợi ý sẵn file nghi ngờ."),
  B("Mẫu còn nhỏ: 60 lần chạy, mỗi lá 4–10 lần chạy."),
  B("Người chấm cũng là mô hình Claude, có thể thiên vị câu trả lời cùng họ mô hình. Em chưa kiểm tra người chấm bằng nhãn người."),
  B("Đáp án mức 1 nhiễu: 14/60 commit kế tiếp không phải bản sửa."),
  B("Agent cần tải code của repo tại commit lỗi, mất 1–3 phút với repo lớn. Log GitHub tự xoá sau 90 ngày: 3 lần chạy trong mẫu đã không tải được log."),
  H2("7.7. Cho mô hình phân loại chỉ ra dòng nguyên nhân"),
  P("Hướng em muốn đi là: mô hình phân loại đọc log, trả về loại lỗi và **một ít dòng log quan trọng nhất**, rồi agent chỉ nhận chừng đó để tìm nguyên nhân trong code. Như vậy đầu vào của agent nhỏ hơn nhiều so với đưa log đầy đủ hay đoạn trích. Nhưng khi xem dòng mô hình chú ý nhất, em thấy mô hình chủ yếu chú ý **dòng tổng kết** (60% lần chạy, 86% với lỗi test), ví dụ `Tests run: 120, Failures: 2`. Dòng này đủ để phân loại nhưng không nói test nào lỗi hay vì sao lỗi. Lý do là lúc huấn luyện em đã kéo sự chú ý của mô hình về dòng bằng chứng của quy tắc gán nhãn, mà dòng bằng chứng thường là dòng tổng kết."),
  P("Vì vậy em thêm vào mô hình **một đầu ra riêng chấm điểm từng dòng log** xem dòng đó có phải dòng nguyên nhân không. Đầu ra này tách khỏi phần chú ý dùng để phân loại."),
  B("**Dòng nguyên nhân dùng để huấn luyện** được lấy tự động bằng mẫu nhận dạng. Với lỗi test: dòng ngoại lệ hoặc assert, dòng liệt kê test lỗi, và dòng `Caused by` cuối cùng của mỗi chuỗi lỗi. Với các loại khác: dòng bằng chứng của quy tắc, nếu đó không phải dòng tổng kết. Mẫu này tìm được dòng nguyên nhân ở khoảng 52% lần chạy; các lần chạy còn lại không đóng góp vào phần học này."),
  B("**Lần thử đầu, đầu ra mới học chung với phần đọc log:** chỉ dòng nguyên nhân rất tốt nhưng làm phân loại kém đi (Macro-F1 lá 0,796 xuống 0,764, giảm ở 11/13 lá). Ở lần thử thứ hai, em **cho đầu ra mới học trên biểu diễn của mô hình nhưng không được sửa phần đọc log**, nên phân loại giữ như cũ. Em dùng lần thử thứ hai."),
  table(["Macro-F1 (fold 0, seed 0)", "Mô hình C", "Lần thử 1: học chung", "Lần thử 2: không sửa phần đọc log"], [
    ["Lá", "0,796", "0,764", "**0,801**"],
    ["Tầng 2", "0,883", "0,865", "**0,883**"],
    ["Tầng 1", "0,907", "0,909", "**0,919**"],
    ["Lá, khi che dòng nhận dạng", "0,666", "0,652", "**0,690**"],
  ], [34, 18, 22, 26]),
  CAP("Bảng 19. Độ đúng phân loại khi thêm đầu ra chỉ dòng nguyên nhân. Mới chạy 1 fold và 1 seed, nên phần nhỉnh hơn mô hình C ở lần thử 2 nằm trong mức dao động; điều chắc chắn là phân loại không còn bị kéo xuống."),
  table(["Tỉ lệ trúng dòng nguyên nhân", "Đầu ra mới: dòng đầu", "Đầu ra mới: trong 5 dòng đầu", "Phần chú ý cũ: dòng đầu", "Phần chú ý cũ: trong 5 dòng đầu"], [
    ["testfailure", "**90%**", "**99%**", "1%", "60%"],
    ["itestfailure", "**84%**", "**95%**", "0,5%", "38%"],
    ["compile", "78%", "96%", "76%", "98%"],
    ["Mọi lá", "**84%**", "**97%**", "48%", "80%"],
  ], [24, 19, 19, 19, 19], { size: 18 }),
  CAP("Bảng 20. Tỉ lệ dòng được chấm cao nhất là dòng nguyên nhân, trên 5.665 lần chạy của tập kiểm tra fold 0 có dòng nguyên nhân (lần thử 2)."),
  B("Với lỗi test, đầu ra mới đưa dòng ngoại lệ, assert hoặc `Caused by` lên đầu, thay cho dòng tổng kết. Với lỗi biên dịch, dòng chú ý nhất vốn đã là dòng báo lỗi nên hai cách ngang nhau."),
  B("**Hạn chế:** dòng nguyên nhân để huấn luyện do mẫu nhận dạng của em sinh ra, nên ở những lần chạy mẫu bắt được, đầu ra mới chủ yếu học lại mẫu đó. Giá trị thật của nó phải đo bằng việc agent có tìm đúng nguyên nhân hay không khi chỉ nhận các dòng này."),
  B("**5 fold:** em huấn luyện tiếp lần thử 2 cho 4 fold còn lại. Trung bình 5 fold, Macro-F1 lá là 0,755 so với 0,786 của mô hình C cùng seed (tầng 2: 0,832 so với 0,853; tầng 1: 0,900 so với 0,896). Mô hình C tự dao động khá mạnh giữa các lần chạy (fold 2 có lần 0,80, có lần 0,70; trung bình các lần chạy C trước đây khoảng 0,775), nhưng lần thử 2 thấp hơn ở 4/5 fold, nên em chưa khẳng định được là không ảnh hưởng. Tỉ lệ trúng dòng nguyên nhân giữ ổn định ở cả 5 fold: dòng đầu 84–87%, trong 5 dòng đầu 97–99%."),
  P("**Thử với agent (cách 4).** Agent chỉ nhận loại lỗi mô hình dự đoán và **5 dòng được đầu ra mới chấm cao nhất, mỗi dòng kèm 5 dòng trước và 5 dòng sau** (số 5 em tự đặt; khối nào trùng hết với khối trước thì bỏ). Agent không có đoạn trích hay log đầy đủ. Đầu vào log chỉ còn trung vị 2,1 nghìn ký tự mỗi lần chạy, so với 3–8 nghìn ký tự của đoạn trích (cách 2). Em chạy trên đủ 60 lần chạy của mục 7.2; mỗi lần chạy dùng mô hình của fold mà lần chạy đó nằm ở tập kiểm tra, nên mô hình chưa thấy lần chạy đó khi huấn luyện. Bốn câu trả lời của mỗi lần chạy được chấm cùng lúc, xáo thứ tự như mục 7.2. Trước khi chạy, em đã chốt mức \"ngang log đầy đủ\": số lần chạy giải thích đúng hoàn toàn không kém cách 1 quá 3/60, và chọn file không kém hơn."),
  table(["60 lần chạy", "Cách 1: log đầy đủ", "Cách 2: đoạn trích", "Cách 3: cách 2 + log đầy đủ", "Cách 4: dòng nguyên nhân"], [
    ["File đúng ở vị trí 1", "0,65", "0,70", "0,68", "0,65"],
    ["File đúng trong 3 file đầu", "0,75", "0,82", "0,78", "0,78"],
    ["Nguyên nhân đúng / đúng một phần / sai", "**55** / 5 / 0", "49 / 9 / 2", "**55** / 5 / 0", "46 / 12 / 2"],
    ["File đúng ở vị trí 1 (44 lần chạy có bản sửa thật)", "0,86", "0,89", "0,91", "0,84"],
    ["Token đầu vào, trung bình", "120 nghìn", "108 nghìn", "117 nghìn", "**101 nghìn**"],
    ["Token đầu vào, trung vị", "98 nghìn", "81 nghìn", "88 nghìn", "**77 nghìn**"],
    ["Giá theo bảng giá API, trung bình", "0,21 USD", "0,20 USD", "0,21 USD", "0,18 USD"],
  ], [30, 17, 17, 18, 18], { size: 18 }),
  CAP("Bảng 21. Bốn cách đưa đầu vào trên 60 lần chạy. Số liệu chọn file và token của cách 1–3 giống Bảng 16 và 18; số nguyên nhân đúng của cách 1–3 hơi khác Bảng 16 vì lần này người chấm xem bốn câu trả lời cùng lúc."),
  B("**Cách 4 chưa đạt mức đã chốt.** Chọn file ngang cách 1 (vị trí 1: cùng 0,65; trong 3 file đầu: 0,78 so với 0,75). Nhưng giải thích đúng hoàn toàn chỉ 46/60, kém cách 1 9 lần chạy, vượt xa mức cho phép 3 lần chạy. So từng lần chạy: cách 1 đúng mà cách 4 không đúng ở 9 lần, chiều ngược lại 0 lần."),
  B("**Token giảm ít hơn em mong:** trung bình giảm 16%, trung vị giảm 21% so với cách 1, và chỉ giảm khoảng 6% so với cách 2. Lý do giống mục 7.4: phần lớn token đến từ việc đọc code và phần cố định của mỗi lượt gọi, không phải từ log."),
  B("**Kém nhất ở dependency** (nguyên nhân đúng 4/8, cách 1 được 7/8) **và doc, quality.** Ví dụ frankframework (mục 7.5): đoạn log mô hình đọc không có dòng `ERR_PNPM_OUTDATED_LOCKFILE`, nên đầu ra mới không thể chọn dòng đó; mô hình còn đoán nhầm loại lỗi thành quality."),
  B("**Với lỗi test, dòng được chọn thường là ngoại lệ bao của Maven**, như `Caused by: MojoFailureException: There are test failures`, chứ không phải lỗi thật của test (10/60 lần chạy có dòng đầu là loại này). Đây là lỗi trong mẫu nhận dạng em dùng để tạo nhãn: \"dòng `Caused by` cuối chuỗi\" bắt nhầm cả chuỗi lỗi của Maven. Ví dụ apache/maven 38451590111: agent không thấy tên test lỗi, cho rằng test chập chờn và nên chạy lại, nên bị chấm sai."),
  P("**Nhận xét:** nút thắt không nằm ở việc chọn dòng mà ở đầu vào của mô hình. Mô hình chỉ đọc khối log quanh dòng `##[error]` (80 dòng trước dòng lỗi đầu tiên), mà với lỗi test và lỗi thư viện, thông báo lỗi thật thường nằm xa hơn. Muốn cách 4 đạt mức đã chốt, em thấy có hai hướng. (1) Cho agent tự mở log đầy đủ khi các dòng được chọn không đủ, giống cách 3; cách này đã đạt chất lượng của cách 1 nhưng tiết kiệm token ít. (2) Sửa mẫu nhãn để bỏ ngoại lệ bao của Maven, và cho đầu ra mới chấm dòng trên log đầy đủ thay vì chỉ khối quanh `##[error]`; cách này phải huấn luyện lại."),
  H2("7.8. Kiểm tra trên benchmark của nhóm nghiên cứu khác"),
  P("Nhãn dòng nguyên nhân ở mục 7.7 do mẫu nhận dạng của em sinh ra, còn đáp án mức 1 đoán từ commit kế tiếp. Để có phép đo độc lập, em dùng hai benchmark đã công bố, có nhãn do người gán: **GHA-Bench** (đi kèm bài GHA-Agent, ACM TOSEM; 323 lỗi GitHub Actions, mỗi lỗi có khoảng dòng log người gán và bản sửa thật của lập trình viên) và **LogDx-CI** (arXiv 2605.28876; 35 lỗi, mỗi lỗi có dòng bằng chứng và nguyên nhân do người viết). Em lấy các lỗi Java: 41 lỗi của GHA-Bench (16 Gradle, 15 Maven, 10 loại khác) và 4 lỗi của LogDx-CI, tổng **45 lỗi**. Không lỗi nào trùng lần chạy trong dữ liệu huấn luyện; 6 repo có mặt trong dữ liệu."),
  B("**Chọn dòng log, so với dòng người gán:** dòng được chấm cao nhất rơi vào dòng người gán ở 71% số lỗi với đầu ra mới, 76% với phần chú ý cũ, 82% với cách đơn giản lấy các dòng cuối có chữ error/fail/exception, và 0% với cách lấy 5 dòng cuối log. Trong 5 dòng đầu thì đầu ra mới và cách lọc chữ cùng được 91%. Phép đo này dễ vì người gán khoanh cả dòng tổng kết như `BUILD FAILURE`; vài lần đầu ra mới bị tính là trượt nhưng vẫn chọn dòng báo lỗi hợp lý."),
  B("**Agent tìm nguyên nhân, so với bản sửa thật:** em chạy agent theo ba cách trên cả 45 lỗi: cách 1 (log đầy đủ), cách 4 (loại lỗi và 5 dòng nguyên nhân của mô hình, kèm 5 dòng trước và sau), và cách đối chứng (loại lỗi và 5 dòng cuối có chữ error/fail/exception, cùng khuôn với cách 4). Người chấm xem ba câu trả lời cùng lúc, đã xáo thứ tự."),
  table(["45 lỗi Java", "Cách 1: log đầy đủ", "Cách 4: dòng nguyên nhân của mô hình", "Đối chứng: dòng có chữ error/fail"], [
    ["File đúng ở vị trí 1", "**0,80**", "0,78", "0,73"],
    ["File đúng trong 3 file đầu", "**0,87**", "0,84", "0,82"],
    ["Nguyên nhân đúng / đúng một phần / sai", "**42** / 2 / 1", "39 / 4 / 2", "34 / 4 / 7"],
    ["Token đầu vào, trung bình", "111 nghìn", "**68 nghìn**", "137 nghìn"],
    ["Token đầu vào, trung vị", "65 nghìn", "**48 nghìn**", "70 nghìn"],
    ["Số bước trung bình", "8,3", "**6,6**", "8,7"],
    ["Giá theo bảng giá API, trung bình", "0,18 USD", "**0,15 USD**", "0,21 USD"],
  ], [34, 20, 24, 22], { size: 18 }),
  CAP("Bảng 22. Agent trên 45 lỗi Java của GHA-Bench và LogDx-CI. Với 4 lỗi LogDx-CI, cả cách 1 và cách 4 đều nêu đủ các ý bắt buộc của bộ dữ liệu, cách đối chứng nêu đủ 75%."),
  B("**Trên benchmark ngoài, cách 4 gần bằng log đầy đủ mà tốn ít token hơn nhiều:** nguyên nhân đúng 39/45 so với 42/45 (kém 3 lỗi; so từng lỗi: cách 1 đúng mà cách 4 không ở 4 lỗi, chiều ngược lại 1 lỗi), chọn file kém đúng 1 lỗi, trong khi token đầu vào trung bình giảm 39% (trung vị giảm 26%) và số bước giảm. Kết quả này tốt hơn trên 60 lần chạy của em (mục 7.7), có lẽ vì log của GHA-Bench ngắn hơn (trung vị 47 nghìn ký tự) nên phần log mô hình đọc ít khi thiếu thông báo lỗi."),
  B("**Dòng do mô hình chọn tốt hơn hẳn cách lọc chữ đơn giản khi đưa cho agent:** cùng khuôn đầu vào, cách 4 đúng 39 lỗi, cách đối chứng 34 lỗi với 7 lỗi bị chấm sai, và cách đối chứng còn tốn token hơn cả log đầy đủ vì agent phải tự đi tìm. Nghĩa là phép đo \"dòng đầu có trúng dòng người gán không\" chưa phản ánh đúng giá trị của dòng được chọn; phép đo bằng agent cho thấy rõ hơn."),
  B("**Các lỗi cách 4 kém hơn:** 2 lỗi định dạng code (Spotless) mà 5 dòng chỉ cho thấy một phần chỗ sai; 1 lỗi quality mà dòng báo lỗi thật (`./bin/rosetta-cli: No such file or directory`) không nằm trong các dòng được chọn; 1 lỗi test tích hợp agent đoán sai cơ chế."),

  // ======================= 8. VIỆC TIẾP THEO =======================
  H1("8. Việc tiếp theo"),
  N("Xin cô góp ý 30 ví dụ ở mục 1, nhất là các ví dụ ranh giới và việc đổi tên tầng 2 thành \"Cách xử lý\".", 2),
  N("Toàn vẹn dữ liệu: lưu thêm phiên bản máy chạy và mã commit của action từ log, để trả lời được lỗi môi trường có do đổi phiên bản không.", 2),
  N("Nhãn phụ \"có giao cho AI tự sửa được không\" (cô gợi ý ngày 05/11): em sẽ đề xuất tiêu chí trình cô trước khi gán.", 2),
  N("Truy vết mức code: đưa agent (cách 3) vào demo cho lần chạy lỗi tầng Dự án. Em sẽ kiểm tra LLM chấm bằng cách tự chấm một phần câu trả lời.", 2),
  N("Dòng nguyên nhân (mục 7.7): thử cho agent tự mở log đầy đủ khi các dòng được chọn không đủ; sửa mẫu nhãn để bỏ ngoại lệ bao của Maven, và cân nhắc cho đầu ra mới chấm dòng trên log đầy đủ (cần huấn luyện lại).", 2),

  H1("Phụ lục A. Link 30 lần chạy"),
  P("Link có dạng `https://github.com/<repo>/actions/runs/<mã lần chạy>`. Log trên GitHub tự xoá sau 90 ngày, nên một số link cũ có thể không còn xem được log; bản log đã lưu trong dữ liệu của đề tài. Cột cuối là dòng log mô hình chú ý nhất (để trống với 2 lá mô hình không học). Ở 2 lần chạy (aws-athena, neqsim), dòng này không phải dòng bằng chứng dù mô hình đoán đúng lá: mô hình đúng nhưng chỉ chưa đúng dòng."),
  table(["Lá", "Repo", "Mã lần chạy", "Vòng gán", "Mô hình", "Dòng mô hình chú ý nhất"],
    Object.entries(EX).map(([id, e]) => [e.leaf, e.repo, id, e.blind ? "mù" : "gợi ý AI",
      e.p === null ? "–" : f2(e.p), e.attn ? e.attn.replace(/\s+/g, " ").slice(0, 110) : "–"]),
    [14, 20, 13, 8, 7, 38], { size: 16 }),
  CAP("Bảng 14. 30 lần chạy dùng làm ví dụ."),
  H1("Phụ lục B. Catalog lỗi CI/CD thường gặp"),
  P("Catalog được dựng từ chính dữ liệu của đề tài: với mỗi lá, gom các dòng bằng chứng giống nhau (thay đường dẫn, số, tên thư viện bằng ký hiệu chung) rồi lấy các dạng hay gặp nhất. Cột cuối là nhóm tương ứng trong bộ nhãn GitHub Actions của Zheng và cộng sự [3] (P = do dự án, W = do môi trường GitHub Actions). Catalog này có thể đưa vào demo để người dùng xem đầy đủ các loại lỗi."),
  table(["Nhánh", "Lá", "Dấu hiệu hay gặp trong log (số lần chạy · số repo)", "Nhóm ở Zheng [3]"], [
    ["Sửa code theo thông báo lỗi", "compile", "`COMPILATION ERROR` (3.448 · 84)\n`error: cannot find symbol` (1.065 · 63)\nKotlin `Unresolved reference` (537 · 44)", "P1 lỗi biên dịch do mã nguồn"],
    ["", "quality", "spotless `The following files had format violations` (3.540 · 28)\nCheckstyle (1.782 · 55)", "P5 kiểm tra chất lượng"],
    ["", "doc", "javadoc `error: reference not found` (120 · 24)", "P5 (Zheng gộp vào chất lượng)"],
    ["", "buildconfig", "pom thiếu phiên bản: `'dependencies.dependency.version' ... is missing. @ line N` (225 · 23)\nGradle `Script compilation error` (79 · 15)", "P2 lỗi do cấu hình dự án"],
    ["Tái hiện lỗi ở local để sửa", "testfailure", "`Tests run: N, Failures: N, Errors: N` (7.599 · 76)\n`N tests completed, N failed` (4.077 · 97)", "P8 test lỗi (unit test)"],
    ["", "dependency", "`Could not find <thư viện>` (1.987 · 144)\n`npm error code ERESOLVE` (335 · 10)\n`Non-resolvable parent POM` (250 · 27)", "P3 không tìm thấy, P4 xung đột phiên bản"],
    ["", "license", "license-maven-plugin / Apache RAT `check` báo thiếu phần ghi bản quyền (439 · 22)", "P5 (Zheng gộp vào chất lượng)"],
    ["", "compatibility", "`There is at least one incompatibility: ...METHOD_REMOVED` (44 · 2)", "Không có nhóm riêng"],
    ["Sửa dựa trên kết quả CI", "itestfailure", "`Tests run: N, Failures: N` (3.002 · 42), giống hệt dấu hiệu của unit test\n`connected...AndroidTest` trên máy ảo Android (1.141 · 26)", "P8 (test tích hợp, 15% của P8)"],
    ["", "flaky", "`N PASSED, 0 FAILED, N FLAKY` (16 · 1)", "Không có (Ge và Zhang [9] có nhãn riêng)"],
    ["Sửa cấu hình CI", "git", "`failed to push some refs` (178 · 15)\n`fatal: unable to access ...` (67 · 26)", "W8 quản lý phiên bản; W5 khi lỗi quyền"],
    ["", "androidsdk", "`could not connect to TCP port 5554: Connection refused` (457 · 27)\n`Archive is not a ZIP archive` (41 · 5)", "W4 lỗi cài đặt môi trường"],
    ["", "infra", "lỗi token/secret (150 · 3), `Could not acquire shared lock` (80 · 10), `Can't find 'action.yml'` (42 · 5); cả lá 685 lần chạy · 63 repo", "W2 cấu hình workflow, W5 quyền"],
    ["Kiểm tra hạ tầng ngoài", "network", "`Docker pull failed` (217 · 10)\nHTTP 429 `Too Many Requests` (282 · 51)\n`Failed to resolve action download info` (163 · 51)", "W3 mạng, W6 không tải được action, W7 vượt giới hạn API"],
    ["", "crash", "`The runner has received a shutdown signal` (1.751 · 50)\nhết bộ nhớ `Java heap space` / `OutOfMemoryError` (630 · 26)\n`has timed out after N minutes` (227 · 15)", "W1 giới hạn tài nguyên runner"],
    ["Chưa có lá", "–", "Quét lỗ hổng bảo mật; kiểm tra hiệu năng", "P6 (15/375), P7 (3/375)"],
  ], [16, 12, 50, 22], { size: 16 }),
  CAP("Bảng 15. Catalog lỗi theo cây nhãn, kèm dấu hiệu log lấy từ dữ liệu và nhóm tương ứng trong Zheng và cộng sự."),

  H1("Phụ lục C. Tài liệu tham khảo"),
  ...[
    "T. Rausch, W. Hummer, P. Leitner, S. Schulte. An Empirical Analysis of Build Failures in the Continuous Integration Workflows of Java-Based Open-Source Software. MSR 2017. DOI 10.1109/MSR.2017.54.",
    "C. Vassallo, G. Schermann, F. Zampetti, D. Romano, P. Leitner, A. Zaidman, M. Di Penta, S. Panichella. A Tale of CI Build Failures: An Open Source and a Financial Organization Perspective. ICSME 2017. DOI 10.1109/ICSME.2017.67.",
    "L. Zheng, S. Li, X. Huang, J. Huang, B. Lin, J. Chen, J. Xuan. Why Do GitHub Actions Workflows Fail? An Empirical Study. ACM TOSEM. DOI 10.1145/3749371.",
    "J. Lee, M. Li, K.-H. Hsu. Applying Transformer Models for Automatic Build Errors Classification of Java-Based Open Source Projects. ICSE Companion 2024 (poster), pp. 282–283.",
    "M. Kang, T. Kim, S. Kim, D. Ryu. Gradle-Autofix: An Automatic Resolution Generator for Gradle Build Error. IJSEKE 2022. DOI 10.1142/S0218194022500218.",
    "C. Zhang, B. Chen, X. Peng, W. Zhao. BuildSheriff: Change-Aware Test Failure Triage for Continuous Integration Builds. ICSE 2022.",
    "H. Aïdasso, F. Bordeleau, A. Tizghadam. On the Diagnosis of Flaky Job Failures: Understanding and Prioritizing Failure Categories. ICSE-SEIP 2025. arXiv 2501.04976.",
    "H. Aïdasso, F. Bordeleau, A. Tizghadam. Predicting Intermittent Job Failure Categories for Diagnosis Using Few-Shot Fine-Tuned Language Models. FSE 2026 Industry Track. arXiv 2601.22264.",
    "W. Ge, C. Zhang. Understanding and Detecting Flaky Builds in GitHub Actions. arXiv 2602.02307, 2026 (preprint, chưa bình duyệt).",
    "LogSage: An LLM-Based Framework for CI/CD Failure Detection and Remediation with Industrial Validation (ByteDance). ASE 2025 Industry Showcase. arXiv 2506.03691.",
    "P. Valenzuela-Toledo, C. Wu, S. Hernandez, A. Boll, R. Machacek, S. Panichella, T. Kehrer. Explaining GitHub Actions Failures with Large Language Models: Challenges, Insights, and Limitations. ICPC 2025. arXiv 2501.16495.",
    "D. Bui, S. Grintz, A. Berndt, T. Bach. Using LLMs to Support Automation of Failure Management in CI/CD Pipelines: A Case Study in SAP HANA. SANER 2026. arXiv 2602.06709.",
    "M. E. Barnes, T. A. Ghaleb, S. Hassan. LogSieve: Task-Aware CI Log Reduction for Sustainable LLM-Based Analysis. MSR 2026. arXiv 2601.20148.",
    "Gradle Inc. Develocity Failure Classification. https://docs.gradle.com/develocity/ (tài liệu sản phẩm).",
    "GitHub. Copilot can explain failed Actions jobs. GitHub Changelog, 15/01/2025 (tài liệu sản phẩm).",
    "GitHub Docs. Events that trigger workflows; Re-running workflows and jobs. https://docs.github.com/en/actions.",
  ].map((t, i) => P(`[${i + 1}] ${t}`, { spacing: { after: 60 } })),
];

const doc = new Document({
  creator: "project3",
  title: "Báo cáo tuần 9",
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
