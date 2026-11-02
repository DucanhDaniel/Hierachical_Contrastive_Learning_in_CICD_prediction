// Báo cáo so sánh baseline và ablation của mô hình HCL bản cuối (01/11/2026). Chạy: node build.js <đường dẫn .docx>
// Số liệu: scripts/analysis/baseline_report.py -> data/results/report_c/numbers.json
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

const body = [
  new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun("SO SÁNH BASELINE VÀ ABLATION")] }),
  P("Đề tài: Phân loại nguyên nhân lỗi build CI/CD theo cây nhãn phân cấp bằng Hierarchical Contrastive Learning"),
  P("Mô hình: HCL bản cuối (cấu hình C). Ngày: 02/11/2026 (cập nhật từ bản 01/11: baseline trên run \"?\", ablation bỏ từng thành phần, lọc non_build, bỏ qua run không chắc, MC Dropout)"),

  H1("0. Tóm tắt"),
  B("**Trên toàn bộ 61.552 run có nhãn quy tắc (5 fold chéo repo),** HCL bản cuối gộp 2 seed đạt macro-F1 **0,799 / 0,883 / 0,925** (lá / tầng 2 / tầng 1). Baseline mạnh nhất (TF-IDF + thông tin CI + diff) đạt 0,715 / 0,804 / 0,876. HCL thắng ở cả 5/5 fold. Chênh lệch có ý nghĩa thống kê: bootstrap theo repo cho khoảng tin cậy 95% của chênh lệch mức lá là [+0,035; +0,120]."),
  B("**Khi che dòng bằng chứng của quy tắc,** khoảng cách nhỏ lại: 0,681 so với 0,651 ở mức lá, thắng 4/5 fold, nhưng **chưa có ý nghĩa thống kê** (khoảng tin cậy 95% [−0,012; +0,063]). Mô hình một seed (0,654) chỉ ngang baseline, nên phần hơn khi che chủ yếu đến từ việc gộp seed."),
  B("**So với LLM (LogSage) trên tập con 365 run nhiều lá hiếm,** HCL đạt 0,727 ở mức lá, LLM đạt 0,814. HCL vẫn tốt nhất trong các mô hình học có giám sát."),
  B("**Trên 120 run quy tắc không gán được (người gán mù),** HCL đúng lá 37%, đúng tầng 1 71%. Sau khi rà lại nhãn: 54% và 85%. TF-IDF chỉ đúng lá 27–31%. **LLM (LogSage) đúng lá nhiều hơn HCL** (51% gán mù, 77% sau rà), tầng 1 ngang HCL. Mô hình trỏ đúng dòng lỗi người chọn ở dòng đầu 54–56%, trong 3 dòng đầu 77–80%."),
  B("**Chỉ dòng lỗi trên run có quy tắc:** dòng mô hình cho điểm cao nhất trùng dòng bằng chứng 71–74%. Lấy dòng FAIL đầu tiên chỉ trúng 28%."),
  B("**Ablation (2 fold, 1 seed):** thêm từng bước cho thấy loss chỉ dòng lỗi đóng góp nhiều nhất (+0,036 ở mức lá). Bỏ từng thành phần của bản cuối (loss tương phản, đặc trưng giai đoạn / công cụ, tóm tắt diff) chỉ làm mức lá thay đổi dưới 0,01, nhỏ hơn độ lệch giữa 2 seed."),
  B("**Run \"?\": lọc non_build và bỏ qua run không chắc.** Bộ lọc theo tên job/step bắt 16/16 run non_build (nhãn sau rà) và chỉ bắt 20/61.552 run có quy tắc. Bỏ qua run có độ tự tin thấp, ngưỡng chọn bằng kiểm định chéo theo repo với mục tiêu đặt trước 0,857: dùng softmax thì trả lời 21% run, đúng lá 0,74; dùng MC Dropout (−entropy) thì trả lời 33% run, đúng lá 0,85. Chênh lệch giữa hai cách chưa có ý nghĩa thống kê vì chỉ có 65 run."),

  H1("1. Thiết lập đánh giá"),
  H2("1.1. Dữ liệu và cách chia"),
  B("**61.552 run fail có log và có nhãn quy tắc** của 278 repo Java/Kotlin (Maven/Gradle, gồm Android). Nhãn quy tắc phiên bản 2026-10-29b-doc. Cây nhãn 3 tầng: tầng 1 Dự án / Môi trường CI, tầng 2 gồm 5 thời điểm cần sửa, tầng 3 gồm 15 lá."),
  B("**5 fold chéo repo:** với fold test k, fold k+1 làm validation, 3 fold còn lại để train. Repo ở tập test không xuất hiện khi train. Mọi mô hình chấm trên cùng tập test ở mỗi fold."),
  B("**Chỉ số:** macro-F1 ở lá, tầng 2, tầng 1, lấy trung bình 5 fold."),
  B("**Log đầy đủ / log đã che:** bản \"che\" xoá các dòng bằng chứng mà quy tắc dùng để gán nhãn. Bản này đo xem mô hình có hiểu được log hay chỉ học lại quy tắc."),

  H2("1.2. Mô hình HCL bản cuối (cấu hình C)"),
  B("**Đầu vào:** khối log quanh chỗ lỗi; mỗi khối lấy cửa sổ 1.600 ký tự chia đôi (nửa quanh dòng lỗi đầu tiên, nửa quanh dòng lỗi cuối cùng), tối đa 512 token. Kèm 22 đặc trưng giai đoạn / công cụ bị fail và 11 đặc trưng tóm tắt diff."),
  B("**Encoder phân cấp:** UniXcoder mã hoá từng đoạn; attention theo dòng → đoạn → job → run."),
  B("**Đầu ra:** 3 đầu phân loại theo 3 tầng; dự đoán được giải mã theo cây nên 3 tầng luôn nhất quán."),
  B("**Hàm loss:** cross-entropy 3 tầng + loss tương phản phân cấp mềm (SupCon; cặp dương cùng lá trọng số 1, cặp anh em cùng cha trọng số 0,4) + 0,5 × loss chỉ dòng lỗi (−log tổng trọng số attention của các dòng chứa bằng chứng quy tắc, chỉ tính trên run không bị che)."),
  B("**Huấn luyện:** mỗi fold khoảng 34 phút trên Colab A100 hoặc 2,1–2,2 giờ trên Kaggle T4. Chạy 2 seed. \"Gộp 2 seed\" là trung bình log xác suất 3 tầng của 2 seed rồi giải mã theo cây."),

  H2("1.3. Baseline"),
  P("Cách so sánh theo thông lệ của các paper dùng dữ liệu tự xây (ví dụ LogSage, ASE 2025): cài lại phương pháp của công trình trước, chạy trên đúng tập train/test của đề tài. Các baseline:"),
  B("**B0 lớp đông nhất:** luôn đoán lá nhiều run nhất trong tập train. Mức sàn."),
  B("**B0 tên workflow/job/step:** TF-IDF trên tên workflow, job, step rồi hồi quy logistic, không đọc log."),
  B("**B1 TF-IDF log:** TF-IDF (từ đơn và cặp từ) trên 30.000 ký tự cuối log, hồi quy logistic cân bằng lớp. Baseline cổ điển của phân loại log."),
  B("**TF-IDF + thông tin CI (+ diff):** B1 ghép đúng các đặc trưng giai đoạn / công cụ (và tóm tắt diff) mà HCL dùng. Dùng để tách phần đóng góp của đặc trưng khỏi phần đóng góp của mô hình."),
  B("**B2 BERT:** fine-tune BERT-base phân loại phẳng trên 512 token cuối log, theo poster ICSE 2024 \"Applying Transformer Models for Automatic Build Errors Classification of Java-Based Open Source Projects\"."),
  B("**B3 LLM:** theo LogSage (ByteDance, ASE 2025 Industry Showcase): lọc dòng log khoá rồi cho Gemini 3.5 Flash-Lite (zero-shot) chọn 1 trong 15 lá. Chỉ chạy trên tập con 365 run và 120 run \"?\" vì chi phí API (120 run \"?\" tốn 0,16 USD)."),

  H1("2. So sánh trên toàn bộ dữ liệu"),
  table(["Mô hình", "Lá", "Tầng 2", "Tầng 1", "Lá (che)", "Tầng 2 (che)", "Tầng 1 (che)"], [
    ["B0 lớp đông nhất", "0,036", "0,112", "0,470", "0,036", "0,112", "0,470"],
    ["B0 tên workflow/job/step", "0,204", "0,371", "0,582", "0,204", "0,371", "0,582"],
    ["B1 TF-IDF log", "0,677", "0,731", "0,871", "0,608", "0,692", "0,828"],
    ["B2 BERT 512 token cuối (*)", "0,455", "0,607", "0,775", "0,411", "0,588", "0,751"],
    ["TF-IDF + thông tin CI", "0,711", "0,804", "0,878", "0,651", "0,761", "0,843"],
    ["TF-IDF + thông tin CI + diff", "0,715", "0,804", "0,876", "0,651", "0,760", "0,843"],
    ["HCL bản cuối, seed 0", "0,785", "0,853", "0,896", "0,659", "0,772", "0,830"],
    ["HCL bản cuối, seed 1", "0,769", "0,865", "0,911", "0,649", "0,752", "0,837"],
    ["HCL bản cuối, trung bình 2 seed", "0,777", "0,859", "0,904", "0,654", "0,762", "0,833"],
    ["**HCL bản cuối, gộp 2 seed**", "**0,799**", "**0,883**", "**0,925**", "**0,681**", "**0,784**", "**0,852**"],
    ["B3 LLM (LogSage) (**)", "—", "—", "—", "—", "—", "—"],
  ], [34, 10, 10, 10, 10, 11, 11], { hl: [9] }),
  CAP("Bảng 1. Macro-F1 trung bình 5 fold chéo repo. (*) BERT học trên nhãn phiên bản trước (2026-10-28-oom), chấm lại trên nhãn hiện tại. (**) LLM chỉ chạy trên tập con 365 run, xem Bảng 4."),
  table(["Mô hình", "Fold 0", "Fold 1", "Fold 2", "Fold 3", "Fold 4", "Độ lệch chuẩn"], [
    ["TF-IDF + thông tin CI + diff", "0,760", "0,759", "0,696", "0,772", "0,585", "0,078"],
    ["HCL trung bình 2 seed", "0,784", "0,818", "0,749", "0,834", "0,701", "0,054"],
    ["**HCL gộp 2 seed**", "**0,800**", "**0,840**", "**0,776**", "**0,839**", "**0,740**", "**0,043**"],
    ["TF-IDF + thông tin CI + diff (che)", "0,685", "0,702", "0,662", "0,672", "0,537", "0,066"],
    ["HCL trung bình 2 seed (che)", "0,659", "0,692", "0,655", "0,655", "0,609", "0,030"],
    ["**HCL gộp 2 seed (che)**", "**0,699**", "**0,721**", "**0,671**", "0,647", "**0,666**", "**0,029**"],
  ], [34, 11, 11, 11, 11, 11, 11]),
  CAP("Bảng 2. Macro-F1 mức lá theo từng fold."),
  B("**Log đầy đủ:** HCL gộp 2 seed cao nhất ở cả 3 tầng, hơn baseline mạnh nhất 0,084 ở mức lá, 0,079 ở tầng 2, 0,049 ở tầng 1, và thắng ở cả 5 fold. Kết quả cũng ổn định hơn giữa các fold (độ lệch chuẩn 0,043 so với 0,078)."),
  B("**Kiểm định bootstrap theo repo** (gộp dự đoán test của 5 fold, lấy lại ngẫu nhiên 263 repo, 1.000 lần), so HCL gộp 2 seed với TF-IDF + thông tin CI + diff. Log đầy đủ: chênh mức lá +0,076, khoảng tin cậy 95% [+0,035; +0,120]; tầng 2 +0,070 [+0,043; +0,104]; không lần lấy mẫu nào HCL thua. Log đã che: mức lá +0,028 [−0,012; +0,063], tầng 2 +0,019 [−0,009; +0,052], tức **chưa có ý nghĩa thống kê ở mức 95%** (8% số lần lấy mẫu HCL không hơn). Chênh lệch ở đây tính trên dự đoán gộp 5 fold nên hơi khác số trung bình theo fold ở Bảng 1."),
  B("**Log đã che:** HCL gộp 2 seed hơn 0,030 ở mức lá, thắng 4/5 fold (thua ở fold 3). Một seed riêng lẻ (0,654) chỉ ngang baseline (0,651). Nghĩa là khi bằng chứng rõ nhất bị xoá, phần hơn của HCL không lớn."),
  B("**Fold 4 khó với mọi mô hình,** nhưng HCL giảm ít hơn hẳn (0,740 so với 0,585)."),
  B("**Đặc trưng CI đóng góp rõ cho TF-IDF** (0,677 → 0,711), còn tóm tắt diff gần như không thêm gì (0,711 → 0,715). HCL dùng cùng các đặc trưng này mà vẫn hơn 0,084, nên phần hơn đến từ cách đọc log, không phải từ đặc trưng."),
  B("**BERT 512 token cuối thấp hơn TF-IDF nhiều** (0,455 so với 0,677), vì 512 token cuối log thường không chứa dòng lỗi."),

  H1("3. F1 theo từng lá"),
  table(["Lá", "Số run", "TF-IDF", "TF-IDF + CI + diff", "BERT", "HCL TB 2 seed", "HCL gộp"], [
    ["flaky", "16", "0,00", "0,00", "0,00", "0,00", "0,00"],
    ["compatibility", "44", "0,00", "0,00", "0,00", "0,00", "0,00"],
    ["git", "245", "0,45", "0,48", "0,06", "0,87", "**0,86**"],
    ["doc", "320", "0,73", "**0,76**", "0,10", "0,74", "**0,76**"],
    ["license", "439", "0,54", "0,56", "0,58", "0,77", "**0,75**"],
    ["androidsdk", "509", "0,56", "0,64", "0,34", "0,80", "**0,85**"],
    ["buildconfig", "546", "0,85", "0,86", "0,34", "0,83", "**0,87**"],
    ["infra", "685", "**0,53**", "0,49", "0,20", "0,41", "0,50"],
    ["network", "2.598", "0,74", "0,74", "0,59", "0,78", "**0,80**"],
    ["crash", "3.028", "0,71", "0,70", "0,58", "0,78", "**0,82**"],
    ["dependency", "3.892", "0,83", "0,82", "0,55", "0,87", "**0,89**"],
    ["quality", "8.427", "0,90", "0,92", "0,73", "0,93", "**0,93**"],
    ["itestfailure", "9.167", "0,59", "0,85", "0,65", "0,89", "**0,91**"],
    ["compile", "12.083", "0,90", "0,93", "0,72", "0,95", "**0,96**"],
    ["testfailure", "19.553", "0,83", "0,91", "0,71", "0,93", "**0,94**"],
  ], [18, 10, 10, 16, 9, 14, 12], { hl: [0, 1, 7] }),
  CAP("Bảng 3. F1 từng lá, log đầy đủ, trung bình 5 fold. Dòng tô màu là các lá HCL chưa vượt baseline."),
  B("**HCL hơn rõ ở các lá cần ngữ cảnh:** git (+0,38 so với TF-IDF + CI + diff), androidsdk (+0,21), license (+0,19), crash (+0,12)."),
  B("**buildconfig không còn là lá yếu** (0,87, bằng baseline); ở mô hình trước là 0,78."),
  B("**Còn 3 lá yếu:** infra (0,50, ngang baseline), flaky (16 run) và compatibility (44 run) không mô hình nào đoán được, vì quá ít mẫu khi chia theo repo."),

  H1("4. So sánh với LLM trên tập con"),
  P("Baseline LLM chỉ chạy trên 365 run, mỗi lá lấy tối đa cùng một số run, nên lá hiếm chiếm tỉ trọng lớn hơn nhiều so với toàn bộ dữ liệu. Các mô hình khác được chấm lại trên đúng 365 run này; số liệu không so trực tiếp được với Bảng 1."),
  table(["Mô hình", "Lá", "Tầng 2", "Tầng 1", "Lá (che)", "Tầng 2 (che)", "Tầng 1 (che)"], [
    ["B2 BERT", "0,393", "0,521", "0,751", "0,356", "0,501", "0,730"],
    ["B1 TF-IDF", "0,598", "0,633", "0,864", "0,529", "0,580", "0,820"],
    ["TF-IDF + CI + diff", "0,609", "0,686", "0,853", "0,564", "0,634", "0,817"],
    ["**HCL bản cuối, gộp 2 seed**", "**0,727**", "**0,804**", "**0,910**", "**0,647**", "**0,710**", "**0,835**"],
    ["B3 LLM (LogSage)", "0,814", "0,852", "0,925", "0,696", "0,743", "0,881"],
  ], [30, 10, 10, 10, 10, 11, 11], { hl: [3] }),
  CAP("Bảng 4. Macro-F1 trên 365 run của tập đánh giá LLM. Nhãn đúng là nhãn quy tắc."),
  B("**HCL thu hẹp khoảng cách với LLM:** mức lá 0,727 so với 0,814 (mô hình trước 0,689). Tầng 1 gần ngang (0,910 so với 0,925)."),
  B("**LLM vẫn mạnh hơn ở lá hiếm,** vì LLM không cần mẫu huấn luyện. Theo góp ý của cô, LLM chỉ dùng làm baseline."),

  H1("5. Đối chiếu với nhãn người"),
  H2("5.1. Run có nhãn quy tắc đã được người gán"),
  P("188 run có nhãn quy tắc đã được người gán lá (147 run gán có gợi ý AI, 41 run gán mù). Đo tỉ lệ khớp nhãn người:"),
  table(["Nguồn nhãn / mô hình", "Khớp nhãn người (188 run)", "Khớp nhãn người (41 run gán mù)"], [
    ["Quy tắc (nhãn dùng để huấn luyện)", "0,846", "0,732"],
    ["B3 LLM (LogSage)", "0,809", "0,634"],
    ["**HCL bản cuối, gộp 2 seed**", "**0,718**", "**0,561**"],
    ["B1 TF-IDF log", "0,649", "0,537"],
    ["TF-IDF + CI + diff", "0,644", "0,488"],
    ["B2 BERT", "0,441", "0,317"],
  ], [40, 30, 30], { hl: [2] }),
  CAP("Bảng 5. Độ chính xác mức lá so với nhãn người, trên run có nhãn quy tắc."),
  B("Trên run quy tắc đã gán được, **mô hình học từ quy tắc không vượt được chính quy tắc** (0,718 so với 0,846). Vì vậy giá trị của mô hình phải đo ở chỗ quy tắc không làm được (mục 5.2)."),
  B("HCL vẫn khớp nhãn người tốt hơn mọi baseline học có giám sát (+0,07 so với TF-IDF)."),

  H2("5.2. Run quy tắc không gán được"),
  P("Lấy ngẫu nhiên 120 run mà quy tắc để \"?\" (tối đa 2 run/repo, 91 repo). Người gán mù: không thấy dự đoán của mô hình, không có gợi ý AI; gán lá và đánh dấu dòng lỗi trên giao diện web. Sau đó rà lại theo danh sách Claude đề xuất (lập trước khi có dự đoán của mô hình); người duyệt từng chỗ, 40/120 run đổi nhãn hoặc dòng lỗi. Dự đoán lấy từ mô hình của fold mà repo đó nằm ở tập test (seed 0)."),
  table(["Chỉ số", "Nhãn gán mù", "Nhãn sau rà lại"], [
    ["Số run rõ nhãn (bỏ unclear, non_build)", "73", "65"],
    ["Đúng lá", "0,370", "**0,538**"],
    ["Macro-F1 lá", "0,329", "0,496"],
    ["Đúng tầng 2", "0,425", "0,600"],
    ["Đúng tầng 1 (Dự án / Môi trường CI)", "0,712", "**0,846**"],
    ["Dòng lỗi người chọn = dòng đầu của mô hình", "0,558 (77 run)", "0,544 (79 run)"],
    ["Dòng lỗi người chọn trong 3 dòng đầu", "0,766", "0,797"],
  ], [50, 25, 25]),
  CAP("Bảng 6. HCL bản cuối trên 120 run quy tắc không gán được. Quy tắc không gán được run nào trong tập này. Phân bố nhãn sau rà: unclear 39, non_build 16, quality 12, dependency 9, itestfailure 9, network 7, các lá khác ≤ 6."),
  B("**Đây là nơi mô hình có giá trị thật:** quy tắc bỏ trống cả 120 run, còn mô hình phân đúng Dự án / Môi trường CI cho 85% run rõ nhãn, đúng lá cho 54%."),
  B("**Giảm mạnh so với run có quy tắc** (đúng lá khoảng 0,9). Run \"?\" khó hơn: log thường bị cắt hoặc lỗi nằm ngoài các mẫu quen thuộc. Mẫu nhỏ (65 run, mỗi lá 1–12 run) nên các số trên chỉ mang tính định hướng."),
  B("**Cần báo cả 2 cột:** cột gán mù là số không bị ảnh hưởng bởi AI; cột sau rà là số đã được người duyệt."),
  P("So với baseline trên đúng các run này (mỗi mô hình dùng mô hình của fold mà repo nằm ở tập test):"),
  table(["Mô hình", "Lá (mù)", "Macro-F1 lá (mù)", "Tầng 1 (mù)", "Lá (rà)", "Macro-F1 lá (rà)", "Tầng 2 (rà)", "Tầng 1 (rà)"], [
    ["B1 TF-IDF log", "0,288", "0,280", "0,644", "0,308", "0,243", "0,369", "0,708"],
    ["TF-IDF + CI + diff", "0,274", "0,266", "0,658", "0,308", "0,254", "0,354", "0,708"],
    ["**HCL bản cuối, seed 0**", "**0,370**", "**0,329**", "**0,712**", "**0,538**", "**0,496**", "**0,600**", "**0,846**"],
    ["B3 LLM (LogSage)", "0,507", "0,431", "0,726", "0,769", "0,615", "0,769", "0,846"],
  ], [30, 9, 11, 9, 9, 11, 10, 11], { hl: [2] }),
  CAP("Bảng 7. Độ chính xác trên run \"?\" rõ nhãn (73 run gán mù, 65 run sau rà). BERT chưa chạy trên tập này."),
  B("**HCL hơn TF-IDF rõ** (lá +0,08 gán mù, +0,23 sau rà; tầng 1 +0,05 đến +0,14)."),
  B("**LLM hơn HCL ở mức lá** (+0,14 gán mù, +0,23 sau rà), còn ở tầng 1 thì ngang. Lý do có thể: LLM đọc tới 40.000 ký tự log đã lọc, trong khi HCL chỉ đọc cửa sổ 1.600 ký tự quanh chỗ lỗi; run \"?\" thường là lỗi lạ, không có mẫu trong dữ liệu huấn luyện."),
  B("**Lưu ý khi đọc cột \"sau rà\":** các chỗ rà lại do một LLM khác (Claude) đề xuất rồi người duyệt, nên cột này có thể nghiêng về cách LLM hiểu log. Cột gán mù không bị ảnh hưởng này và vẫn cho LLM hơn HCL."),

  H1("6. Chỉ dòng lỗi"),
  P("Mô hình cho điểm từng dòng log nhờ attention theo dòng. Trên 61.552 run có quy tắc, so dòng điểm cao nhất với dòng bằng chứng của quy tắc:"),
  table(["Cách chọn dòng", "Dòng đầu trúng", "Trong 3 dòng đầu"], [
    ["**HCL bản cuối, seed 0**", "**0,709**", "**0,846**"],
    ["**HCL bản cuối, seed 1**", "**0,735**", "**0,858**"],
    ["Dòng FAIL đầu tiên", "0,279", "0,507"],
    ["Dòng có chữ lỗi (error/exception…) đầu tiên", "0,214", "0,498"],
    ["Dòng FAIL cuối cùng", "0,013", "—"],
    ["Chọn ngẫu nhiên", "0,019", "—"],
  ], [50, 25, 25]),
  CAP("Bảng 8. Tỉ lệ trúng dòng bằng chứng, 5 fold. Dòng bằng chứng nằm trong phần log mô hình đọc ở 92,4% run."),
  B("Mô hình trỏ đúng dòng gấp khoảng 2,5 lần cách lấy dòng FAIL đầu tiên."),
  B("Trên run có quy tắc, mô hình được dạy chỉ vào dòng của quy tắc, nên số này chủ yếu cho thấy mô hình bắt chước quy tắc tốt. Số có ý nghĩa hơn là trên run \"?\" với dòng do người chọn: 54–56% ở dòng đầu, 77–80% trong 3 dòng đầu (Bảng 6)."),

  H1("7. Ablation"),
  H2("7.1. Đã chạy: từng bước từ mô hình trước đến bản cuối"),
  P("Chạy thử trên fold 0 và fold 3, seed 1, mỗi bước thêm một thành phần:"),
  table(["Cấu hình", "Lá fold 0", "Lá fold 3", "Lá TB", "Tầng 2 TB", "Tầng 1 TB", "Lá TB (che)", "Dòng đầu trúng"], [
    ["v10: cửa sổ neo dòng lỗi cuối", "0,733", "0,780", "0,757", "0,844", "0,896", "0,628", "—"],
    ["A: + cửa sổ chia đôi", "0,759", "0,771", "0,765", "0,833", "0,893", "0,646", "—"],
    ["B: A + attention theo dòng", "0,739", "0,792", "0,765", "0,828", "0,890", "0,649", "0,077"],
    ["**C: B + loss chỉ dòng lỗi (bản cuối)**", "**0,772**", "**0,829**", "**0,801**", "**0,869**", "**0,926**", "**0,658**", "**0,736**"],
  ], [32, 9, 9, 9, 10, 10, 10, 11], { hl: [3] }),
  CAP("Bảng 9. Ablation từng bước, fold 0 + 3, seed 1 (1 seed, chỉ mang tính định hướng). Dòng đầu trúng tính trên mọi run có dòng bằng chứng, như Bảng 8. Phần log mô hình đọc chứa dòng bằng chứng: 83,4% với v10, 91,9% từ cấu hình A."),
  B("**Cửa sổ chia đôi** giúp mô hình thấy dòng bằng chứng ở nhiều run hơn (83% → 92%), mức lá tăng nhẹ (+0,008)."),
  B("**Attention theo dòng một mình không giúp:** mức lá không đổi, và dòng điểm cao nhất chỉ trúng 7,7% dòng bằng chứng. Không có tín hiệu dạy thì mô hình không tự học chỉ vào dòng lỗi."),
  B("**Loss chỉ dòng lỗi đóng góp nhiều nhất:** +0,036 ở mức lá, +0,041 ở tầng 2, +0,036 ở tầng 1; dòng đầu trúng tăng từ 7,7% lên 73,6%. Dạy mô hình nhìn đúng dòng vừa giúp chỉ lỗi, vừa giúp phân loại."),

  H2("7.2. Bỏ từng thành phần của bản cuối"),
  P("Cùng thiết lập với Bảng 9 (fold 0 + 3, seed 1, các tham số khác giữ nguyên như cấu hình C), mỗi lần bỏ một thành phần:"),
  table(["Cấu hình", "Lá", "Tầng 2", "Tầng 1", "Lá (che)", "Tầng 2 (che)", "Tầng 1 (che)"], [
    ["**C: bản cuối**", "**0,801**", "**0,869**", "**0,926**", "**0,658**", "**0,782**", "**0,841**"],
    ["A4: bỏ loss tương phản phân cấp (chỉ CE + loss dòng)", "0,796", "0,862", "0,924", "0,662", "0,781", "0,847"],
    ["A1: bỏ đặc trưng giai đoạn / công cụ fail", "0,803", "0,847", "0,923", "0,669", "0,784", "0,855"],
    ["A6: bỏ tóm tắt diff", "0,798", "0,865", "0,920", "0,663", "0,780", "0,836"],
  ], [40, 9, 9, 9, 10, 11, 12], { hl: [0] }),
  CAP("Bảng 10. Ablation bỏ từng thành phần, macro-F1 trung bình fold 0 + 3, seed 1. Hai seed của cấu hình C trên 5 fold lệch nhau 0,016 ở mức lá (Bảng 1). Mỗi kernel chạy 3 lượt, khoảng 6,7 giờ trên Kaggle T4."),
  B("**Mọi chênh lệch ở mức lá đều dưới 0,01,** nhỏ hơn độ lệch giữa 2 seed. Với 2 fold và 1 seed, không thấy thành phần nào trong ba thành phần này đóng góp đo được ở mức lá."),
  B("**A4 (bỏ loss tương phản):** lá −0,005, tầng 2 −0,007; khi che thì ngang hoặc cao hơn chút. Kết quả giống các phiên bản trước (HCL ngang cross-entropy)."),
  B("**A1 (bỏ giai đoạn / công cụ):** tầng 2 giảm nhiều nhất (−0,022), đúng với giả thuyết đặc trưng này giúp xác định thời điểm cần sửa; mức lá không giảm."),
  B("**A6 (bỏ diff):** gần như không đổi, khớp với kết quả ở TF-IDF (thêm diff chỉ +0,004)."),
  B("**Chưa chạy:** A2 (8 đoạn cuối log thay cho khối log lỗi), A3 (bỏ phân cấp, một đầu ra phẳng), A5 (không che dòng bằng chứng khi train). Phần đóng góp lớn của cách đọc log đã thấy qua Bảng 9."),

  H1("8. Run \"?\": lọc non_build và bỏ qua run không chắc"),
  P("Trên run \"?\", mô hình đúng lá khoảng một nửa (Bảng 6), và trong 120 run có 16 run non_build (fail ở bước thủ tục PR như changelog, tiêu đề PR, milestone, không phải lỗi build) cùng 39 run không rõ nguyên nhân. Hai bước bổ sung:"),
  H2("8.1. Lọc non_build bằng quy tắc"),
  B("**Quy tắc:** xét tên job và step bị fail (changelog, tiêu đề PR / commit, milestone / nhãn PR, Jira, squash, kích thước PR, release notes). Run fail nhiều job thì mọi step fail phải là step thủ tục hoặc step tổng hợp kết quả, để không bắt nhầm run có job test thật cùng fail."),
  B("**Kết quả:** bắt 16/16 run non_build theo nhãn sau rà (gán mù: 8/10, kèm 8 run người gán nhãn khác). Trên 61.552 run có quy tắc chỉ bắt 20 run (0,03%); trên toàn bộ 28.661 run \"?\" bắt 13%."),
  B("**Đang kiểm tra thêm:** 30 run do bộ lọc bắt được đưa vào đợt gán mù thứ 2 để đo tỉ lệ bắt nhầm."),
  H2("8.2. Bỏ qua run không chắc: softmax và MC Dropout"),
  B("**Cách chọn ngưỡng (đặt trước khi xem kết quả):** câu trả lời của mô hình phải đáng tin ít nhất ngang bộ quy tắc dùng làm nhãn, tức precision mức lá 0,857 đo ở vòng gán mù 27/10. Ngưỡng là mức độ tự tin thấp nhất đạt mục tiêu này, chọn bằng kiểm định chéo theo repo trên nhãn người của run \"?\" (chọn trên 4/5 số repo, chấm trên 1/5 còn lại, lặp 200 lần). Không chọn được ngưỡng trên run có quy tắc với log đã che: mô hình tự tin quá mức trên run \"?\" (độ tự tin trung bình 0,93 trên run có quy tắc so với 0,67 trên run \"?\")."),
  B("**MC Dropout** (Gal & Ghahramani, ICML 2016; AdaptiveLog dùng để quyết định khi nào chuyển sang LLM): giữ dropout khi dự đoán, đoán lại 20 lần trên cùng weight (cấu hình C, seed 0, không train lại; khoảng 1 giờ Colab A100). Câu trả lời vẫn lấy từ lần đoán thường; MC chỉ dùng để đo độ tự tin."),
  table(["Độ tự tin", "AUROC run quy tắc (log che)", "AUROC run \"?\" (rà)", "Trả lời (rà)", "Đúng lá (rà)", "Trả lời (mù)", "Đúng lá (mù)"], [
    ["Softmax (lần đoán thường)", "0,868", "0,713", "21%", "0,737", "8%", "0,619"],
    ["MC: tỉ lệ đồng thuận", "0,742", "0,774", "5%", "0,482", "0%", "—"],
    ["MC: xác suất trung bình", "0,886", "0,755", "32%", "0,839", "11%", "0,685"],
    ["**MC: −entropy**", "**0,884**", "**0,782**", "**33%**", "**0,849**", "11%", "0,679"],
    ["MC: −MI", "0,864", "0,800", "36%", "0,819", "9%", "0,607"],
  ], [26, 14, 12, 11, 11, 11, 11], { hl: [3] }),
  CAP("Bảng 11. AUROC: khả năng tách câu đúng / câu sai (0,5 là ngẫu nhiên). Trả lời / đúng lá: ngưỡng chọn theo kiểm định chéo theo repo, mục tiêu 0,857, trên run \"?\" rõ nhãn sau khi lọc non_build (65 run sau rà, 66 run gán mù). Run quy tắc: 500 run test mỗi fold."),
  B("**Trên run có quy tắc,** xác suất trung bình của MC tách đúng / sai tốt hơn softmax một chút (+0,017, khoảng tin cậy 95% [+0,006; +0,030]) và hiệu chỉnh tốt hơn (ECE 0,045 so với 0,060). Tỉ lệ đồng thuận phiếu kém hẳn vì 83% run đồng thuận đủ 20/20 lần."),
  B("**Trên run \"?\" (nhãn sau rà),** dùng MC (−entropy) thì trả lời 33% run, đúng lá 0,849, sát mục tiêu 0,857; softmax chỉ trả lời 21% run, đúng lá 0,737. AUROC của MC cao hơn softmax 0,04–0,09 nhưng khoảng tin cậy còn chứa 0 (−MI: +0,087 [−0,044; +0,224]), vì chỉ có 65 run."),
  B("**Với nhãn gán mù,** cả hai cách đều chỉ trả lời 8–11% run, đúng lá 0,6–0,7, chưa đạt mục tiêu."),
  B("**Phiếu đa số của MC không chính xác hơn lần đoán thường** (0,898 so với 0,901 trên log đầy đủ; 0,508 so với 0,538 trên run \"?\"). Dùng 5 lần đoán thay vì 20 cho xác suất trung bình gần như như nhau, nên khi triển khai chỉ tốn khoảng 6 lượt đoán mỗi run."),
  B("**Phát hiện run không rõ nguyên nhân** (unclear) bằng độ tự tin vẫn yếu với mọi cách: AUROC khoảng 0,6."),

  H1("9. Kết luận và hạn chế"),
  N("HCL bản cuối vượt mọi baseline học có giám sát ở cả 3 tầng trên 5 fold chéo repo, ổn định hơn giữa các fold, và chỉ được dòng lỗi gấp khoảng 2,5 lần cách lấy dòng FAIL đầu tiên."),
  N("Khi bằng chứng rõ nhất bị che, phần hơn chỉ còn nhỏ, phụ thuộc vào việc gộp seed và chưa có ý nghĩa thống kê."),
  N("Ablation cho thấy phần tăng đến từ cách đọc log (cửa sổ chia đôi, attention theo dòng, loss chỉ dòng lỗi). Bỏ loss tương phản, đặc trưng giai đoạn / công cụ hay tóm tắt diff đều thay đổi mức lá dưới 0,01."),
  N("LLM (LogSage) tốt hơn trên tập con nhiều lá hiếm, khớp nhãn người hơn, và đúng lá nhiều hơn HCL trên run \"?\" (0,51 so với 0,37 gán mù). Trên run \"?\", HCL hơn TF-IDF rõ và ngang LLM ở tầng 1 (0,71–0,85)."),
  N("Với run \"?\", lọc non_build bằng quy tắc và bỏ qua run có độ tự tin MC Dropout thấp cho độ chính xác 0,85 trên 33% run (nhãn sau rà); với nhãn gán mù thì chưa đạt mục tiêu."),
  N("**Hạn chế:** chỉ 2 seed; ablation chỉ 2 fold × 1 seed; BERT chưa huấn luyện lại trên nhãn mới và chưa chạy trên run \"?\"; LLM chỉ chạy trên tập con; tập run \"?\" nhỏ (65–73 run rõ nhãn), một người gán, 40/120 nhãn đổi sau khi rà theo đề xuất của AI; flaky và compatibility quá ít mẫu."),
  N("**Đang làm:** đợt gán mù thứ 2 gồm 150 run \"?\" (120 run rút ngẫu nhiên và 30 run do bộ lọc non_build bắt, trộn lẫn, người gán không biết run nào thuộc phần nào) để có đủ run kiểm chứng ngưỡng, MC Dropout và bộ lọc non_build."),
];

const doc = new Document({
  creator: "project3",
  title: "So sánh baseline và ablation",
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
