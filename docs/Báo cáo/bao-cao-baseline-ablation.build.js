// Báo cáo kết quả mô hình: so sánh baseline và ablation (viết cho người ngoài đề tài, 02/11/2026).
// Chạy: node build.js <đường dẫn .docx>. Số liệu: scripts/analysis/baseline_report.py -> data/results/report_c/numbers.json,
// data/results/abstain/summary.json, data/results/mc/summary.json, data/results/abl/.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType, ImageRun,
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
function IMG(file, widthPx = 640) {
  const data = fs.readFileSync(path.join(__dirname, file));
  const w = data.readUInt32BE(16), h = data.readUInt32BE(20); // kích thước PNG
  return new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120 },
    children: [new ImageRun({ type: "png", data, transformation: { width: widthPx, height: Math.round(widthPx * h / w) } })] });
}

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

// đoạn log nguyên văn: số dòng | nội dung (chữ đều) | điểm trong đoạn | điểm trong run; dòng có điểm được tô màu
function logTable(rows) {
  const ws = [560, 0, 1150, 1150];
  ws[1] = W - ws[0] - ws[2] - ws[3];
  const cell = (t, i, head, hl) => new TableCell({
    width: { size: ws[i], type: WidthType.DXA }, borders,
    shading: head ? { type: ShadingType.CLEAR, fill: "1F4E79", color: "auto" } : hl ? { type: ShadingType.CLEAR, fill: "E2EFDA", color: "auto" } : undefined,
    margins: { top: 20, bottom: 20, left: 70, right: 70 },
    children: [new Paragraph({ alignment: i !== 1 && !head ? AlignmentType.RIGHT : AlignmentType.LEFT,
      children: [new TextRun(head ? { text: t, size: 16, bold: true, color: "FFFFFF" }
        : { text: t, ...(i === 1 ? { font: "Consolas", size: 15 } : { size: 16 }), bold: hl })] })],
  });
  return new Table({
    width: { size: W, type: WidthType.DXA }, columnWidths: ws,
    rows: [new TableRow({ tableHeader: true, children: ["Dòng", "Nội dung log", "Điểm trong đoạn", "Điểm trong run"].map((h, i) => cell(h, i, true)) }),
      ...rows.map((r) => new TableRow({ children: r.map((c, i) => cell(c, i, false, r[3] !== "")) }))],
  });
}

const M = "Mô hình đề xuất"; // tên dùng thống nhất trong mọi bảng

const body = [
  new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun("KẾT QUẢ MÔ HÌNH: SO SÁNH VỚI BASELINE VÀ ABLATION")] }),
  P("Đề tài: Phân loại nguyên nhân lỗi build CI/CD theo cây nhãn phân cấp bằng Hierarchical Contrastive Learning"),
  P("Ngày: 02/11/2026"),

  H1("Tóm tắt"),
  B("**Bài toán:** khi một lần chạy CI (GitHub Actions) của dự án Java/Kotlin bị lỗi, mô hình đọc log và trả lời: lỗi nằm ở **dự án hay môi trường CI**, lẽ ra **phải sửa lúc nào**, **loại lỗi** cụ thể (1 trong 15 loại), kèm **các dòng log làm căn cứ**."),
  B("**So với baseline trên 61.552 lần chạy có nhãn:** mô hình đề xuất đạt 0,799 ở mức loại lỗi, baseline tốt nhất đạt 0,715. Mô hình thắng ở cả 5 lần chia dữ liệu, chênh lệch có ý nghĩa thống kê. Khi xoá các dòng bằng chứng rõ nhất khỏi log, mô hình chỉ còn hơn nhẹ (0,681 so với 0,651, chưa có ý nghĩa thống kê)."),
  B("**So với LLM:** LLM (Gemini, theo phương pháp LogSage) vẫn tốt hơn trên các mẫu nhỏ mà LLM được chạy: 0,814 so với 0,727 trên 365 lần chạy; đúng loại lỗi 51% so với 37% trên các lần chạy mà bộ quy tắc không gán được nhãn."),
  B("**Ablation:** phần cải thiện lớn nhất đến từ việc dạy mô hình nhìn đúng dòng lỗi (+0,036). Bỏ phần học tương phản, thông tin CI hay tóm tắt thay đổi code chỉ làm kết quả thay đổi dưới 0,01."),
  B("**Với lần chạy quy tắc không gán được nhãn:** lọc bỏ lỗi không phải do build và chỉ trả lời khi mô hình đủ tự tin, mô hình trả lời 33% số lần chạy với độ chính xác 85%. Mẫu kiểm tra còn nhỏ (65 lần chạy)."),

  H1("1. Bài toán và dữ liệu"),
  P("**Đầu vào:** một lần chạy CI bị lỗi (gọi tắt là **run**), gồm log của các job lỗi, tên workflow / job / step lỗi và commit kích hoạt lần chạy. **Đầu ra:** nhãn theo cây 3 tầng (Bảng 1) và các dòng log làm căn cứ."),
  table(["Tầng 1: lỗi nằm ở đâu", "Tầng 2: lẽ ra phải sửa lúc nào", "Tầng 3: loại lỗi (số run)"], [
    ["**Dự án** (mã nguồn, cấu hình build)", "Khi viết code", "Lỗi biên dịch (12.083), Vi phạm kiểm tra code (8.427), Lỗi tài liệu javadoc (320), Cấu hình build sai (546)"],
    ["", "Khi build ở máy trước khi push", "Unit test lỗi (19.553), Lỗi thư viện phụ thuộc (3.892), Lỗi license (439), Không tương thích API (44)"],
    ["", "Trên CI trước khi merge", "Test tích hợp lỗi (9.167), Test chập chờn (16)"],
    ["**Môi trường CI** (runner, mạng, secrets)", "Sửa cấu hình CI", "Lỗi git (245), Lỗi Android SDK / emulator (509), Hạ tầng CI khác (685)"],
    ["", "Chạy lại", "Lỗi mạng (2.598), Môi trường sập: hết bộ nhớ, hết giờ… (3.028)"],
  ], [22, 24, 54]),
  CAP("Bảng 1. Cây nhãn 3 tầng và số run có nhãn của từng loại lỗi."),
  B("**Dữ liệu:** 278 repo mã nguồn mở Java/Kotlin (Maven/Gradle, có Android), 61.552 run lỗi có log và có nhãn."),
  B("**Nhãn do bộ quy tắc gán:** mỗi quy tắc khớp một dòng log đặc trưng (gọi là **dòng bằng chứng**), ví dụ `COMPILATION ERROR` → Lỗi biên dịch. Đối chiếu với 188 run do người gán, bộ quy tắc khớp 85%."),
  B("**Run quy tắc không gán được nhãn:** 28.661 run không khớp quy tắc nào. Lấy ngẫu nhiên 120 run trong số này cho người gán nhãn mà không xem dự đoán của mô hình (**gán mù**), dùng để đo mô hình ở đúng chỗ quy tắc bất lực (mục 5)."),

  H1("2. Mô hình đề xuất"),
  B("**Đọc 3 nguồn:** (1) log quanh chỗ lỗi: tối đa 8 đoạn, mỗi đoạn lấy 1.600 ký tự gồm nửa quanh dòng báo lỗi đầu tiên và nửa quanh dòng báo lỗi cuối cùng; (2) thông tin CI: tên workflow / job / step lỗi và giai đoạn / công cụ bị lỗi (biên dịch, test, kiểm tra code…); (3) tóm tắt thay đổi code của commit (sửa file gì, bao nhiêu)."),
  B("**Đọc log:** UniXcoder (mô hình ngôn ngữ cho mã nguồn đã huấn luyện sẵn) đọc từng đoạn log. Mô hình chấm điểm từng dòng trong đoạn, từng đoạn trong job, từng job trong run, rồi tổng hợp thành một vector đại diện cho run. Điểm từng dòng cho biết dòng nào là căn cứ của dự đoán (mục 6)."),
  B("**3 đầu ra cho 3 tầng nhãn.** Kết quả được giải mã theo cây nên 3 tầng không bao giờ mâu thuẫn (loại lỗi luôn thuộc đúng nhóm cha)."),
  B("**Huấn luyện bằng 3 thành phần:** (1) phân loại đúng nhãn ở cả 3 tầng; (2) **học tương phản phân cấp (HCL)**: kéo vector của các run cùng loại lỗi lại gần nhau, các run khác loại nhưng cùng nhóm cha gần vừa phải; (3) **dạy chỉ dòng lỗi**: đẩy điểm cao vào dòng bằng chứng của quy tắc. Một nửa số run khi huấn luyện bị xoá dòng bằng chứng, để mô hình không chỉ học thuộc các dòng đó."),
  B("**Kết hợp 2 lần huấn luyện:** huấn luyện 2 lần với khởi tạo ngẫu nhiên khác nhau, rồi lấy trung bình xác suất của 2 mô hình. Mọi số liệu \"mô hình đề xuất\" dưới đây là bản kết hợp, trừ khi ghi khác."),
  IMG("hinh-tuan-7/cau-hinh-c.png"),
  P("**Hình 1.** Cấu trúc mô hình đề xuất.", { alignment: AlignmentType.CENTER }),

  H1("3. Cách đánh giá"),
  B("**Chia theo repo:** chia 278 repo thành 5 phần. Mỗi lần lấy 1 phần làm tập kiểm tra, 4 phần còn lại để huấn luyện, lặp 5 lần. Mô hình luôn được chấm trên **repo chưa từng thấy**, và mọi mô hình dùng chung cách chia."),
  B("**Chỉ số macro-F1** (0 đến 1): F1 tính riêng cho từng loại lỗi rồi lấy trung bình, nên loại lỗi hiếm quan trọng ngang loại lỗi phổ biến. Tính ở cả 3 tầng; con số chính là tầng 3 (loại lỗi)."),
  B("**Kiểm tra khó (xoá bằng chứng):** chấm thêm trên log đã xoá dòng bằng chứng của quy tắc, để xem mô hình có hiểu log hay chỉ thuộc lại các dòng mà quy tắc dùng."),
  P("**Baseline:** cài lại phương pháp của các công trình trước và chạy trên đúng cách chia dữ liệu của đề tài (cách làm thông thường khi đề tài tự xây dữ liệu, ví dụ LogSage):"),
  table(["Baseline", "Cách làm", "Nguồn"], [
    ["Đoán loại phổ biến nhất", "Luôn đoán loại lỗi nhiều run nhất", "Mức sàn"],
    ["TF-IDF trên tên job", "Chỉ dùng tên workflow / job / step, không đọc log", "Mức sàn"],
    ["TF-IDF trên log", "Đếm từ trong 30.000 ký tự cuối log, hồi quy logistic", "Cách phân loại log cổ điển"],
    ["TF-IDF + thông tin CI + thay đổi code", "Như trên, thêm đúng thông tin CI và tóm tắt thay đổi code mà mô hình đề xuất dùng", "Để tách phần đóng góp của thông tin phụ"],
    ["BERT", "Fine-tune BERT trên 512 token cuối log", "ICSE 2024 (poster)"],
    ["LLM (LogSage)", "Lọc dòng log quan trọng, Gemini 3.5 Flash-Lite chọn 1 trong 15 loại lỗi, không cần huấn luyện", "ASE 2025; chỉ chạy trên mẫu nhỏ vì chi phí"],
  ], [26, 50, 24]),
  CAP("Bảng 2. Các baseline."),

  H1("4. Kết quả trên dữ liệu có nhãn"),
  H2("4.1. Toàn bộ 61.552 run"),
  table(["Mô hình", "Loại lỗi", "Tầng 2", "Tầng 1", "Loại lỗi (khó)", "Tầng 2 (khó)", "Tầng 1 (khó)"], [
    ["Đoán loại phổ biến nhất", "0,036", "0,112", "0,470", "0,036", "0,112", "0,470"],
    ["TF-IDF trên tên job", "0,204", "0,371", "0,582", "0,204", "0,371", "0,582"],
    ["TF-IDF trên log", "0,677", "0,731", "0,871", "0,608", "0,692", "0,828"],
    ["BERT", "0,455", "0,607", "0,775", "0,411", "0,588", "0,751"],
    ["TF-IDF + thông tin CI", "0,711", "0,804", "0,878", "0,651", "0,761", "0,843"],
    ["TF-IDF + thông tin CI + thay đổi code", "0,715", "0,804", "0,876", "0,651", "0,760", "0,843"],
    [`${M}, 1 lần huấn luyện (trung bình)`, "0,777", "0,859", "0,904", "0,654", "0,762", "0,833"],
    [`**${M}**`, "**0,799**", "**0,883**", "**0,925**", "**0,681**", "**0,784**", "**0,852**"],
  ], [34, 10, 10, 10, 12, 12, 12], { hl: [7] }),
  CAP("Bảng 3. Macro-F1 trung bình 5 lần chia theo repo. \"Khó\": log đã xoá dòng bằng chứng. LLM không có trong bảng vì chỉ chạy trên mẫu nhỏ (Bảng 5)."),
  B("**Mô hình đề xuất tốt nhất ở cả 3 tầng,** hơn baseline mạnh nhất 0,084 ở mức loại lỗi và thắng ở cả 5 lần chia. Lấy mẫu lại theo repo 1.000 lần (bootstrap): khoảng tin cậy 95% của chênh lệch là [+0,035; +0,120], tức chênh lệch có ý nghĩa thống kê."),
  B("**Kiểm tra khó:** mô hình chỉ hơn 0,030 (0,681 so với 0,651), khoảng tin cậy [−0,012; +0,063], **chưa có ý nghĩa thống kê**. Một lần huấn luyện riêng lẻ (0,654) chỉ ngang baseline."),
  B("**Hai lần huấn luyện cho kết quả gần nhau** (0,785 và 0,769). Kết hợp 2 lần tăng thêm khoảng 0,02."),
  B("**Thông tin CI giúp TF-IDF rõ** (0,677 → 0,711), tóm tắt thay đổi code gần như không (→ 0,715). **BERT kém hơn TF-IDF** vì 512 token cuối log thường không chứa dòng báo lỗi."),

  H2("4.2. Theo từng loại lỗi"),
  table(["Loại lỗi", "Số run", "TF-IDF + CI + thay đổi code", M], [
    ["Lỗi git", "245", "0,48", "**0,86**"],
    ["Lỗi Android SDK / emulator", "509", "0,64", "**0,85**"],
    ["Lỗi license", "439", "0,56", "**0,75**"],
    ["Môi trường sập", "3.028", "0,70", "**0,82**"],
    ["Lỗi tài liệu javadoc", "320", "0,76", "0,76"],
    ["Cấu hình build sai", "546", "0,86", "**0,87**"],
    ["Lỗi mạng", "2.598", "0,74", "**0,80**"],
    ["Lỗi thư viện phụ thuộc", "3.892", "0,82", "**0,89**"],
    ["Test tích hợp lỗi", "9.167", "0,85", "**0,91**"],
    ["Unit test lỗi", "19.553", "0,91", "**0,94**"],
    ["Lỗi biên dịch", "12.083", "0,93", "**0,96**"],
    ["Vi phạm kiểm tra code", "8.427", "0,92", "**0,93**"],
    ["Hạ tầng CI khác", "685", "0,49", "0,50"],
    ["Không tương thích API", "44", "0,00", "0,00"],
    ["Test chập chờn", "16", "0,00", "0,00"],
  ], [34, 14, 26, 26], { hl: [12, 13, 14] }),
  CAP("Bảng 4. F1 theo loại lỗi, log đầy đủ. Dòng tô màu: mô hình chưa vượt baseline."),
  B("**Hơn rõ ở các loại lỗi cần hiểu ngữ cảnh:** lỗi git (+0,38), Android SDK (+0,21), license (+0,19), môi trường sập (+0,12)."),
  B("**Còn yếu:** Hạ tầng CI khác (nội dung rất đa dạng, mỗi kiểu lỗi thường chỉ có trong 1 repo). Không tương thích API và Test chập chờn quá ít mẫu, không mô hình nào học được."),

  H2("4.3. So với LLM trên mẫu nhỏ"),
  P("LLM chỉ chạy trên 365 run (mỗi loại lỗi lấy tối đa 25 run) vì chi phí API. Loại lỗi hiếm chiếm tỉ lệ lớn hơn nhiều so với toàn bộ dữ liệu, nên không so được trực tiếp với Bảng 3."),
  table(["Mô hình", "Loại lỗi", "Tầng 2", "Tầng 1", "Loại lỗi (khó)", "Tầng 2 (khó)", "Tầng 1 (khó)"], [
    ["BERT", "0,393", "0,521", "0,751", "0,356", "0,501", "0,730"],
    ["TF-IDF trên log", "0,598", "0,633", "0,864", "0,529", "0,580", "0,820"],
    ["TF-IDF + CI + thay đổi code", "0,609", "0,686", "0,853", "0,564", "0,634", "0,817"],
    [`**${M}**`, "**0,727**", "**0,804**", "**0,910**", "**0,647**", "**0,710**", "**0,835**"],
    ["LLM (LogSage)", "0,814", "0,852", "0,925", "0,696", "0,743", "0,881"],
  ], [30, 10, 10, 10, 12, 14, 14], { hl: [3] }),
  CAP("Bảng 5. Macro-F1 trên 365 run của mẫu LLM."),
  B("LLM vẫn tốt hơn, chủ yếu ở loại lỗi hiếm (LLM không cần mẫu huấn luyện). Ở tầng 1, mô hình đề xuất gần ngang LLM (0,910 so với 0,925). LLM chỉ dùng làm baseline, không dùng để gán nhãn."),

  H2("4.4. Đối chiếu với nhãn người"),
  table(["Nguồn nhãn / mô hình", "Khớp nhãn người (188 run)", "Khớp nhãn người (41 run gán mù)"], [
    ["Bộ quy tắc (dùng làm nhãn huấn luyện)", "0,846", "0,732"],
    ["LLM (LogSage)", "0,809", "0,634"],
    [`**${M}**`, "**0,718**", "**0,561**"],
    ["TF-IDF trên log", "0,649", "0,537"],
    ["TF-IDF + CI + thay đổi code", "0,644", "0,488"],
    ["BERT", "0,441", "0,317"],
  ], [40, 30, 30], { hl: [2] }),
  CAP("Bảng 6. Tỉ lệ đúng loại lỗi so với nhãn người, trên run có nhãn quy tắc."),
  B("Mô hình học từ quy tắc nên **không vượt được bộ quy tắc ở chỗ quy tắc đã gán được**. Giá trị của mô hình phải đo ở chỗ quy tắc không gán được (mục 5)."),

  H1("5. Run quy tắc không gán được nhãn"),
  P("120 run lấy ngẫu nhiên (tối đa 2 run/repo, 91 repo). Người gán loại lỗi và đánh dấu dòng lỗi trên giao diện web, không thấy dự đoán của mô hình. Sau đó rà lại theo danh sách góp ý do một mô hình AI khác (Claude) lập; người duyệt từng chỗ, 40/120 run đổi nhãn hoặc dòng lỗi. Có 39 run không đủ thông tin và 16 run lỗi không phải do build (thủ tục PR), được bỏ khi chấm. Mỗi mô hình dùng bản huấn luyện chưa thấy repo của run."),
  table(["Mô hình", "Đúng loại lỗi (gán mù)", "Đúng loại lỗi (sau rà)", "Đúng tầng 1 (gán mù)", "Đúng tầng 1 (sau rà)"], [
    ["TF-IDF trên log", "0,288", "0,308", "0,644", "0,708"],
    ["TF-IDF + CI + thay đổi code", "0,274", "0,308", "0,658", "0,708"],
    [`**${M}** (1 lần huấn luyện)`, "**0,370**", "**0,538**", "**0,712**", "**0,846**"],
    ["LLM (LogSage)", "0,507", "0,769", "0,726", "0,846"],
  ], [32, 17, 17, 17, 17], { hl: [2] }),
  CAP("Bảng 7. Tỉ lệ đúng trên run có nhãn rõ (73 run gán mù, 65 run sau rà). Chi phí LLM: 0,16 USD."),
  B("**Quy tắc bỏ trống cả 120 run;** mô hình đề xuất xác định đúng lỗi nằm ở dự án hay môi trường CI cho 71–85% run, đúng loại lỗi 37–54%, hơn TF-IDF rõ."),
  B("**LLM đúng loại lỗi nhiều hơn mô hình đề xuất,** ở tầng 1 thì ngang nhau. LLM đọc tới 40.000 ký tự log, mô hình chỉ đọc 1.600 ký tự mỗi đoạn; các run này thường là lỗi lạ, không có trong dữ liệu huấn luyện."),
  B("**Đọc cột \"sau rà\" thận trọng:** góp ý rà lại đến từ một mô hình AI nên có thể nghiêng về cách LLM hiểu log. Cột gán mù không bị ảnh hưởng và vẫn cho LLM hơn."),
  B("**Dòng lỗi:** dòng mô hình cho điểm cao nhất trùng dòng người đánh dấu ở 54–56% run; trong 3 dòng điểm cao nhất ở 77–80% run."),

  H1("6. Chỉ dòng lỗi: một ví dụ"),
  P("Phần này chưa so sánh với phương pháp khác, chỉ minh hoạ bằng một run thật trong 120 run ở mục 5."),
  B("**Run:** repo linkedin/venice, run 30617913741 (pull request). 2 job lỗi: \"StaticAnalysis (17)\" ở step \"Run Static Analysis\", và \"StaticAnalysisAndUnitTestsFailureAlert\" (job này chỉ báo lại rằng job trước lỗi)."),
  B("**Quy tắc:** không gán được. **Người gán mù:** Vi phạm kiểm tra code, đánh dấu 4 dòng lỗi."),
  H2("6.1. Đầu vào"),
  P("Mô hình nhận tên workflow / job / step, giai đoạn bị lỗi, tóm tắt thay đổi code, và 7 đoạn log (5 đoạn của job StaticAnalysis, 2 đoạn của job báo lại). Bảng 8 là đoạn mô hình chú ý nhất, nguyên văn (đường dẫn máy chạy thay bằng <ws>)."),
  logTable([
    ["0", "> Task :tests:venice-pulsar-test:compileTestJava NO-SOURCE", "", ""],
    ["1", "> Task :tests:venice-pulsar-test:testClasses UP-TO-DATE", "", ""],
    ["2", "> Task :tests:venice-pulsar-test:spotbugsTest NO-SOURCE", "", ""],
    ["3", "> Task :tests:venice-pulsar-test:spotbugsPulsarIntegrationTest", "", ""],
    ["4", "FAILURE: Build failed with an exception.", "", ""],
    ["5", "> Task :tests:venice-pulsar-test:check", "", ""],
    ["6", "gradle/actions: Writing build results to <ws>/build-results/__run-1785488058550.json", "", ""],
    ["7", "* What went wrong:", "", ""],
    ["8", "Execution failed for task ':clients:da-vinci-client:spotbugsMain'.", "0,961", "0,953"],
    ["9", "> A failure occurred while executing com.github.spotbugs.snom.internal.SpotBugsRunnerForWorker$SpotBugsExecutor", "0,008", "0,008"],
    ["10", "   > 2 SpotBugs violations were found.See the report at: file://<ws>/clients/da-vinci-client/build/reports/spotbugs/main.html,…", "0,031", "0,030"],
    ["11", "* Try:", "", ""],
    ["12", "> Run with --stacktrace option to get the stack trace.", "", ""],
    ["13", "> Run with --info or --debug option to get more log output.", "", ""],
    ["14", "> Run with --scan to get full insights.", "", ""],
    ["15", "* Get more help at https://help.gradle.org", "", ""],
    ["16", "BUILD FAILED in 6m 3s", "", ""],
    ["17", "Deprecated Gradle features were used in this build, making it incompatible with Gradle 8.0.", "", ""],
    ["18", "You can use '--warning-mode all' to show the individual deprecation warnings and determine if …", "", ""],
    ["19", "See https://docs.gradle.org/7.3/userguide/command_line_interface.html#sec:command_line_warnings", "", ""],
    ["20", "180 actionable tasks: 130 executed, 13 from cache, 37 up-to-date", "", ""],
    ["21", "##[error]Process completed with exit code 1.", "", ""],
  ]),
  CAP("Bảng 8. Đoạn log mô hình chú ý nhất và điểm từng dòng. Dòng để trống có điểm trong run dưới 0,002."),
  H2("6.2. Đầu ra"),
  table(["Tầng", "Dự đoán", "Xác suất", "Nhãn người"], [
    ["Tầng 1: lỗi nằm ở đâu", "Dự án", "0,999", "Dự án"],
    ["Tầng 2: lẽ ra phải sửa lúc nào", "Khi viết code", "0,999", "Khi viết code"],
    ["Tầng 3: loại lỗi", "**Vi phạm kiểm tra code** (SpotBugs)", "1,000", "Vi phạm kiểm tra code"],
    ["Độ tự tin (đoán lại 20 lần, mục 8)", "Cả 20 lần đều cùng đáp án", "—", "—"],
    ["Dòng căn cứ", "Dòng 8, 10, 9 (Bảng 8)", "—", "Dòng 5, 8, 9, 10"],
  ], [28, 36, 12, 24]),
  CAP("Bảng 9. Đầu ra của mô hình cho run ví dụ."),
  H2("6.3. Cách suy ra dòng căn cứ"),
  N("Mô hình đọc từng đoạn log, gom các token cùng dòng thành một vector đại diện cho dòng đó.", 2),
  N("Mô hình chấm điểm từng dòng trong đoạn (tổng điểm các dòng trong đoạn bằng 1). Dòng 8 được 0,961.", 2),
  N("Tương tự, mô hình chấm điểm từng đoạn trong job và từng job trong run. Job StaticAnalysis được gần như toàn bộ điểm (job báo lại chỉ in \"One or more required jobs failed\"); trong job đó, đoạn ở Bảng 8 được 0,992.", 2),
  N("**Điểm dòng trong run = điểm dòng × điểm đoạn × điểm job.** Dòng 8: 0,961 × 0,992 × 1,000 = 0,953. Vector của cả run là tổng các vector dòng nhân với điểm này, rồi đi qua 3 đầu ra. Vì vậy dòng điểm cao là dòng đóng góp nhiều nhất vào dự đoán. Mô hình trả về 5 dòng điểm cao nhất.", 2),
  N("Mô hình học cách chấm điểm này trên run có nhãn quy tắc (đẩy điểm vào dòng bằng chứng), rồi tự áp dụng cho run mới. Run ví dụ không có dòng bằng chứng nào khi huấn luyện.", 2),
  B("**Ví dụ cho thấy:** mô hình bỏ qua các dòng báo lỗi chung chung (\"FAILURE: Build failed…\", \"Process completed with exit code 1\") và job chỉ báo lại kết quả; mô hình dồn điểm vào dòng nêu bước SpotBugs bị lỗi và số vi phạm, đúng các dòng người chọn."),
  B("**Lưu ý:** điểm dòng cho biết mô hình dựa vào dòng nào, chưa phải lời giải thích đầy đủ. Đây là một ví dụ mô hình đúng; tỉ lệ chung ở mục 5."),

  H1("7. Ablation: thành phần nào đóng góp"),
  P("Thêm hoặc bỏ từng thành phần, giữ nguyên các phần còn lại. Do chi phí GPU, chỉ chạy 2 trong 5 lần chia dữ liệu và 1 lần huấn luyện; chênh lệch dưới khoảng 0,016 (mức lệch giữa 2 lần huấn luyện) coi như không khác."),
  table(["Cấu hình", "Loại lỗi", "Tầng 2", "Tầng 1", "Loại lỗi (khó)", "Trỏ đúng dòng"], [
    ["Bản trước: đọc 1.600 ký tự quanh dòng báo lỗi cuối", "0,757", "0,844", "0,896", "0,628", "—"],
    ["+ đọc cả quanh dòng báo lỗi đầu", "0,765", "0,833", "0,893", "0,646", "—"],
    ["+ chấm điểm từng dòng", "0,765", "0,828", "0,890", "0,649", "0,077"],
    [`+ dạy chỉ dòng lỗi = **${M}**`, "**0,801**", "**0,869**", "**0,926**", "**0,658**", "**0,736**"],
    [`${M}, bỏ học tương phản (HCL)`, "0,796", "0,862", "0,924", "0,662", "—"],
    [`${M}, bỏ thông tin giai đoạn / công cụ lỗi`, "0,803", "0,847", "0,923", "0,669", "—"],
    [`${M}, bỏ tóm tắt thay đổi code`, "0,798", "0,865", "0,920", "0,663", "—"],
  ], [40, 11, 11, 11, 13, 14], { hl: [3] }),
  CAP("Bảng 10. Macro-F1 trung bình 2 lần chia, 1 lần huấn luyện. Trỏ đúng dòng: tỉ lệ run có dòng điểm cao nhất trùng dòng bằng chứng của quy tắc."),
  B("**Dạy chỉ dòng lỗi đóng góp nhiều nhất:** +0,036 ở mức loại lỗi, +0,041 ở tầng 2; tỉ lệ trỏ đúng dòng tăng từ 7,7% lên 73,6%. Chỉ chấm điểm dòng mà không dạy thì mô hình không tự tìm ra dòng lỗi."),
  B("**Đọc cả quanh dòng báo lỗi đầu** đưa dòng bằng chứng vào phần mô hình đọc ở 92% run (trước đó 83%), mức loại lỗi tăng nhẹ."),
  B("**Bỏ học tương phản, thông tin giai đoạn / công cụ hoặc tóm tắt thay đổi code:** mức loại lỗi thay đổi dưới 0,01. Riêng bỏ thông tin giai đoạn / công cụ làm tầng 2 giảm 0,022."),
  B("**Chưa chạy:** đọc 8 đoạn cuối log thay cho vùng quanh lỗi; bỏ cây nhãn (1 đầu ra phẳng); không xoá dòng bằng chứng khi huấn luyện."),

  H1("8. Chỉ trả lời khi đủ tự tin"),
  P("Trên run quy tắc không gán được, mô hình chỉ đúng khoảng một nửa. Hai bước bổ sung để mô hình chỉ trả lời khi đáng tin:"),
  B("**Lọc lỗi không phải do build:** quy tắc theo tên job / step (changelog, tiêu đề PR, milestone, Jira, kích thước PR…). Bắt đủ 16/16 run loại này trong 120 run, và chỉ 20 trên 61.552 run có nhãn (bắt nhầm rất ít)."),
  B("**Đo độ tự tin, 2 cách:** (1) xác suất mô hình gán cho đáp án; (2) cho mô hình đoán lại 20 lần, mỗi lần tắt ngẫu nhiên một phần mạng (**MC Dropout**, Gal & Ghahramani 2016; AdaptiveLog dùng cách này), đáp án càng dao động thì càng kém tự tin. Đáp án trả về vẫn lấy từ lần đoán thường."),
  B("**Chọn ngưỡng:** mục tiêu đặt trước là độ chính xác ít nhất bằng bộ quy tắc (85,7%, đo khi người kiểm tra quy tắc). Ngưỡng được chọn trên một phần repo và chấm trên phần còn lại, lặp nhiều lần, để con số không bị chọn trên chính dữ liệu chấm."),
  table(["Cách đo độ tự tin", "Phân biệt đúng / sai", "Trả lời (sau rà)", "Đúng loại lỗi (sau rà)", "Trả lời (gán mù)", "Đúng loại lỗi (gán mù)"], [
    ["Xác suất của mô hình", "0,71", "21%", "0,74", "8%", "0,62"],
    ["**Đoán lại 20 lần (MC Dropout)**", "**0,78**", "**33%**", "**0,85**", "11%", "0,68"],
  ], [26, 14, 14, 16, 14, 16], { hl: [1] }),
  CAP("Bảng 11. Trên run quy tắc không gán được (65 run sau rà, 66 run gán mù, đã lọc lỗi không phải do build). Phân biệt đúng / sai: AUROC, 0,5 là đoán mò, 1 là hoàn hảo."),
  B("**Đoán lại 20 lần tốt hơn:** trả lời nhiều run hơn (33% so với 21%) và đúng hơn (0,85, sát mục tiêu 0,857). Nhưng mẫu chỉ 65 run nên chênh lệch **chưa có ý nghĩa thống kê**; với nhãn gán mù, cả hai cách đều chưa đạt mục tiêu."),
  B("**Trên run có nhãn quy tắc,** đoán lại 20 lần cũng phân biệt đúng / sai tốt hơn chút (0,884 so với 0,868 trên log đã xoá bằng chứng, có ý nghĩa thống kê). Đoán lại 5 lần cho kết quả gần như 20 lần, nên khi dùng thật chỉ tốn khoảng 6 lần đoán mỗi run."),

  H1("9. Kết luận và hạn chế"),
  N("Mô hình đề xuất tốt hơn mọi baseline có huấn luyện ở cả 3 tầng nhãn, trên repo chưa từng thấy, và trả kèm các dòng log làm căn cứ."),
  N("Khi xoá các dòng bằng chứng rõ nhất, mô hình chỉ còn hơn nhẹ, chưa có ý nghĩa thống kê."),
  N("Phần cải thiện chính đến từ cách đọc log và việc dạy mô hình nhìn đúng dòng lỗi; học tương phản, thông tin CI và tóm tắt thay đổi code không tạo khác biệt đo được ở mức loại lỗi."),
  N("LLM tốt hơn ở loại lỗi hiếm và ở run quy tắc không gán được, nhưng tốn chi phí cho mỗi lần gọi; ở tầng 1, mô hình đề xuất ngang LLM."),
  N("**Hạn chế:** chỉ 2 lần huấn luyện; ablation chỉ 2 lần chia × 1 lần huấn luyện; LLM chỉ chạy trên mẫu nhỏ; BERT chưa chạy trên run quy tắc không gán được; mẫu run quy tắc không gán được còn nhỏ (65–73 run nhãn rõ, một người gán); Không tương thích API và Test chập chờn quá ít mẫu."),
  N("**Đang làm:** gán mù thêm 150 run quy tắc không gán được (120 run ngẫu nhiên và 30 run do bộ lọc \"không phải lỗi build\" bắt, trộn lẫn) để kiểm chứng ngưỡng tự tin và bộ lọc trên mẫu lớn hơn."),
];

const doc = new Document({
  creator: "project3",
  title: "Kết quả mô hình: so sánh với baseline và ablation",
  styles: {
    default: { document: { run: { font: FONT, size: 22 } } },
    paragraphStyles: [
      { id: "Title", name: "Title", basedOn: "Normal", run: { font: FONT, size: 32, bold: true, color: "1F4E79" }, paragraph: { alignment: AlignmentType.CENTER, spacing: { after: 120 } } },
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
