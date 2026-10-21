// Báo cáo tuần 6 (17/10 – 21/10/2026). Chạy: node build.js <đường dẫn .docx>
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
      alignment: i > 0 && !isHead && /^[−+\-]?[\d.,%$ /≈→<>~—]+$/.test(String(t).replace(/\*\*/g, "")) ? AlignmentType.RIGHT : AlignmentType.LEFT,
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
  new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun("BÁO CÁO TUẦN 6")] }),
  P("Đề tài: Dự đoán và phân loại lỗi build CI/CD bằng Hierarchical Contrastive Learning"),
  P("Thời gian: thứ Bảy 17/10/2026 – thứ Tư 21/10/2026"),

  H1("0. Tóm tắt"),
  B("**Đổi hướng bài toán:** từ dự đoán trước khi CI chạy sang **phân loại nguyên nhân lỗi sau khi CI run fail**, đọc từ log (diff là nhánh thứ hai). Đóng góp chính là xác định đúng loại lỗi theo cây nhãn 3 tầng."),
  B("**Dữ liệu:** crawl thêm **100 repo mới** (tổng 200 repo, 269.435 commit, 117.384 run fail); rà soát lại các quy tắc dependency; lấy thêm 59 nghìn diff. Đợt 2 tăng mạnh dependency (+68%) nhưng **gần như không thêm mẫu cho các lá hiếm**."),
  B("**Mô hình:** mô hình lai (UniXcoder đọc đoạn log + xác suất TF-IDF) tốt nhất trong các mô hình đã thử: macro-F1 mức lá 0,629 / 0,556 (log nguyên vẹn / log đã che dòng bằng chứng), hơn TF-IDF khoảng +0,05 đến +0,08."),
  B("**HCL so với CE:** loss HCL cũ hơn CE khoảng +0,02 ở mức lá, nhất quán qua 2 seed nhưng **chưa có ý nghĩa thống kê** (CI95 [−0,006; +0,036]). Em đã tìm ra nguyên nhân (HCL kéo các lá anh em quá gần nhau) và thử một loss mới (**SupCon cặp dương mềm theo cây**) cho kết quả tốt hơn trên 1 fold; cần xác nhận thêm."),
  B("**So sánh với LLM** (Gemini 3.5 Flash-Lite, zero-shot, $0,95 cho 905 run): trên tập người gán, ở tầng 2 **mô hình của đề tài ngang LLM** (0,877 so với 0,872). LLM chỉ hơn rõ ở các lá hiếm. Ghi quy ước của đề tài vào prompt không giúp LLM."),
  B("**Hướng đi:** hệ thống kết hợp, trong đó mô hình phân cấp **phân loại, ước lượng độ tin cậy và khoanh vùng đoạn log**, chỉ những run khó mới chuyển cho LLM để chỉ ra vị trí lỗi. 3 đoạn log mô hình chọn chứa dòng gây lỗi ở **92%** run; tín hiệu tin cậy phát hiện dự đoán sai với AUROC khoảng 0,90."),

  H1("1. Đổi hướng bài toán"),
  P("Dự đoán build pass/fail không còn là vấn đề chính: sau khi CI chạy, kết quả pass/fail đã có sẵn. Thứ developer thực sự cần là **biết build fail vì sao**, và log CI thường dài hàng nghìn dòng, nguyên nhân không nhất thiết nằm ở dòng có chữ ERROR. Vì vậy bài toán được đổi thành:"),
  B("**Đầu vào:** log của các job fail (chia đoạn theo cấu trúc step / goal Maven / task Gradle), tên workflow / job / step fail; diff của commit là nhánh thứ hai."),
  B("**Đầu ra:** nhãn theo cây 3 tầng (tầng 1: build / test / env; tầng 2: 7 loại; tầng 3: các lá theo Rausch et al. cộng network, flaky)."),
  B("**Đánh giá:** chia chéo theo repo (5 fold, repo ở test không xuất hiện khi train); hai kiểu test: log nguyên vẹn, và log **đã che** mọi dòng chứa bằng chứng mà quy tắc dùng để gán nhãn, mô phỏng các run mà quy tắc không bắt được."),
  P("Chia đoạn log **không lọc theo từ khoá ERROR**: ranh giới là step GitHub Actions, goal Maven, task Gradle; đoạn ngắn được gộp, đoạn dài cắt cửa sổ 40 dòng. Mỗi run lấy tối đa 8 đoạn từ cuối log, luân phiên giữa các job fail; 94,7% run giữ được đoạn chứa dòng bằng chứng."),

  H1("2. Dữ liệu"),
  H2("2.1. Crawl đợt 2: thêm 100 repo"),
  B("**Chọn repo:** dò 407 repo ứng viên, mỗi repo tải khoảng 15 log run fail, gán lá tầng 3 bằng quy tắc, chấm điểm ưu tiên repo có lá hiếm (trọng số √(11.704 / số mẫu của lá)). Chọn 100 repo, **không trùng** với 100 repo đợt 1."),
  B("**Crawl trên Kaggle:** chuỗi phiên tự nối (mỗi phiên 11 giờ, giới hạn 5.000 request/giờ của GitHub). Kết quả: push xong 100/100 repo, PR xong 99/100 (repo newrelic/newrelic-java-agent lỗi lặp ở mọi phiên nên em dừng)."),
  B("**Log dài hơn:** từ đợt 2, mỗi job lưu thêm 200 KB cuối log (trước đây chỉ lưu đoạn quanh lỗi), để mô hình có ngữ cảnh khi nguyên nhân không nằm ở dòng ERROR."),
  B("**Diff:** lấy diff cho mọi commit fail (kể cả `?` và env) trên 3 kernel Kaggle song song: thêm 59.025 diff; 99,8% run fail có diff."),
  gap(),
  table(["Chỉ số", "Đợt 1 (100 repo)", "Đợt 2 (+100 repo)", "Tổng (200 repo)"], [
    ["Commit (push + PR)", "210.330", "59.105", "269.435"],
    ["Commit fail", "62.378", "18.637", "81.015"],
    ["Commit fail có nhãn quy tắc", "32.202", "11.993", "44.195"],
    ["Run fail (bỏ workflow không phải build)", "92.524", "24.860", "117.384"],
    ["Run có nhãn quy tắc và có log", "43.616", "13.933", "57.549"],
    ["Run quy tắc chưa gán được (`?`)", "18.967", "7.583", "26.550"],
    ["Run không còn log (GitHub xoá sau 90 ngày)", "29.941", "3.344", "33.285"],
    ["Số đoạn log", "392.107", "385.739", "777.846"],
  ], [40, 20, 20, 20]),
  CAP("Bảng 1. Quy mô dữ liệu trước và sau đợt 2. Số đoạn log đợt 2 lớn do có thêm 200 KB cuối log mỗi job."),

  H2("2.2. Phân bố lá tầng 3"),
  table(["Lá", "Đợt 1", "Đợt 2 thêm", "Tổng"], [
    ["testfailure", "11.691", "4.399", "16.090"], ["itestfailure", "4.956", "2.072", "7.028"],
    ["compile", "4.463", "2.404", "6.867"], ["quality", "5.542", "869", "6.411"],
    ["dependency", "1.559", "**1.060**", "2.619"], ["network", "1.263", "577", "1.840"],
    ["crash", "1.532", "295", "1.827"], ["license", "216", "28", "244"],
    ["buildconfig", "143", "64", "207"], ["git", "107", "99", "206"], ["doc", "52", "70", "122"],
    ["flaky", "61", "**0**", "61"], ["compatibility", "42", "2", "44"],
    ["`?` (quy tắc không gán được)", "30.176", "6.644", "36.820"],
  ], [40, 20, 20, 20]),
  CAP("Bảng 2. Số commit fail theo lá tầng 3."),
  B("Dependency tăng 68%; git và doc tăng khoảng gấp đôi nhưng vẫn chỉ 100–200 mẫu; license, compatibility, flaky gần như không đổi."),
  B("**Nhận xét:** dò 15 log mỗi repo không đủ để tìm repo giàu lá hiếm, và các lá này hiếm ở mọi repo. Crawl thêm repo không phải cách hiệu quả để cân bằng lá hiếm; hướng hợp lý hơn là gộp lá hiếm lên tầng 2 hoặc tìm chúng trong nhóm `?`."),

  H2("2.3. Rà soát quy tắc dependency"),
  P("Theo Zheng et al. (TOSEM 2025), gán tay cho dependency khoảng 20,8% lỗi, trong khi quy tắc của em chỉ gán 3,6%, nên em rà soát lại ranh giới của lá này. Em quyết định bốn điểm:"),
  table(["Mã", "Trường hợp", "Quyết định"], [
    ["Q1", "maven-enforcer (upper bound, convergence, banned) và `dependency:analyze`", "dependency (trước là lint)"],
    ["Q2", "HTTP 401/403 khi tải artifact", "network"],
    ["Q3", "Lệch phiên bản JDK, lỗi liên kết (NoClassDefFoundError...)", "dependency, thắng compile/test của job quyết định nhãn"],
    ["Q4", "`Failed to read artifact descriptor` không rõ nguyên nhân", "giữ `?`"],
  ], [8, 52, 40]),
  CAP("Bảng 3. Quyết định ranh giới dependency (18/10)."),
  B("Codex đề xuất 19 quy tắc theo các quyết định trên; em duyệt 18/19. Tích hợp thêm 15 quy tắc mới và đổi nhãn 4 quy tắc cũ, có điều kiện chặn (guard) để tránh dương tính giả."),
  B("Kết quả: commit fail `?` giảm 30.609 → 30.176; số run khớp nhãn người tăng 179 → 183; mô phỏng lại khớp 94.292/94.293 run."),

  H1("3. Thiết lập đánh giá"),
  B("**Chia chéo repo:** 5 fold theo repo; với fold k: test = k, val = k+1, train = 3 fold còn lại."),
  B("**Chỉ số:** macro-F1 ở 3 tầng; mức lá là chỉ số chính (đúng mục tiêu: biết nguyên nhân cụ thể)."),
  B("**Nhãn tham chiếu:** nhãn quy tắc (precision khoảng 0,91 ở tầng 2 khi đối chiếu người gán). Trên log nguyên vẹn, quy tắc gần như đúng 100% theo định nghĩa, nên kiểu test **đã che** mới đo khả năng tổng quát hoá."),
  B("**Tập người gán:** 203 run vòng gán mù 10/10 (nhãn tầng 2 sau phân xử), dùng để so mô hình với LLM theo độ đúng thật."),
  B("Toàn bộ huấn luyện chạy trên GPU T4 của Kaggle; LLM chạy qua Kaggle Benchmarks."),

  H1("4. Các thử nghiệm và số liệu"),
  H2("4.1. Baseline"),
  table(["Mô hình", "Lá, nguyên vẹn", "Lá, đã che", "Tầng 2, nguyên vẹn", "Tầng 2, đã che"], [
    ["Quy tắc", "0,996", "0,446", "0,999", "0,579"],
    ["TF-IDF (30.000 ký tự cuối, train che 50%)", "0,561", "0,487", "0,724", "0,667"],
  ], [40, 15, 15, 15, 15]),
  CAP("Bảng 4. Baseline chéo repo (macro-F1, gộp 5 fold). Chia theo thời gian thì TF-IDF đạt 0,837 / 0,813 ở tầng 2: chéo repo khó hơn nhiều."),
  B("Khi mất dòng then chốt, mô hình học được hơn quy tắc (tầng 2: 0,667 so với 0,579)."),

  H2("4.2. Mô hình đọc log: UniXcoder + attention phân cấp"),
  P("Kiến trúc: mỗi run gồm tối đa 8 đoạn log; UniXcoder mã hoá từng đoạn, attention gộp đoạn → job → run; ghép ngữ cảnh CI (tên workflow / job / step); 3 đầu phân loại theo 3 tầng, giải mã nhất quán theo cây. Biến thể **HCL** thêm SupCon ở 3 tầng. Để so công bằng, em chạy lại TF-IDF với cùng tập train và cùng lượng log:"),
  table(["Mô hình", "Lá (nguyên / che)", "Tầng 2 (nguyên / che)", "Tầng 1 (nguyên / che)"], [
    ["TF-IDF A: đọc 30.000 ký tự", "0,560 / 0,479", "0,742 / 0,670", "0,877 / 0,831"],
    ["TF-IDF C: đúng 8 đoạn + ngữ cảnh như mô hình", "0,535 / 0,459", "0,676 / 0,617", "0,831 / 0,782"],
    ["UniXcoder CE", "0,525 / 0,461", "0,684 / 0,630", "0,809 / 0,782"],
    ["UniXcoder HCL", "0,537 / 0,459", "0,685 / 0,634", "0,826 / 0,789"],
  ], [40, 20, 20, 20]),
  CAP("Bảng 5. Macro-F1 trung bình 5 fold, 1 seed."),
  B("Cùng đầu vào thì mô hình nơ-ron ngang hoặc hơn TF-IDF một chút; **nút thắt là lượng log đọc được** (8 đoạn × 256 token). HCL ≈ CE."),

  H2("4.3. Mô hình lai: UniXcoder + xác suất TF-IDF"),
  P("Thêm một nhánh: xác suất lá của TF-IDF A (tính kiểu stacking, out-of-fold theo repo để không rò nhãn) → 64 chiều, ghép trước MLP. Thêm hai cải tiến cho lá hiếm: **sampler theo lớp** (mỗi batch 6 lá × 2 run) và **trọng số đầu lá = trọng số loại cha + độ lệch**."),
  table(["Mô hình", "Lá (nguyên / che)", "Tầng 2 (nguyên / che)", "Tầng 1 (nguyên / che)"], [
    ["TF-IDF A", "0,560 / 0,479", "0,742 / 0,670", "0,877 / 0,831"],
    ["Lai CE", "0,591 / 0,515", "0,742 / 0,678", "0,882 / 0,849"],
    ["Lai HCL", "0,590 / 0,506", "0,741 / 0,673", "0,882 / 0,852"],
    ["Lai + sampler CE (TB 2 seed)", "0,590 / 0,518", "0,742 / 0,686", "0,863 / 0,830"],
    ["**Lai + sampler HCL (TB 2 seed)**", "**0,612 / 0,542**", "**0,747 / 0,693**", "0,859 / 0,833"],
  ], [40, 20, 20, 20], { hl: [4] }),
  CAP("Bảng 6. Macro-F1 trung bình 5 fold. Tốt nhất là lai + sampler HCL seed 1: lá 0,629 / 0,556."),
  B("Mô hình lai hơn TF-IDF ở mức lá (+0,03 đến +0,07) và không thua ở tầng nào."),
  B("**HCL so với CE (có sampler, 2 seed):** mức lá +0,023 (log nguyên vẹn) và +0,025 (đã che), HCL hơn ở 6–7/10 cặp seed × fold. Bootstrap theo repo: Δ = +0,018, CI95 [−0,006; +0,036], P(Δ ≤ 0) = 0,08: **nhất quán về hướng, chưa có ý nghĩa thống kê**."),
  B("Theo lá, HCL hơn CE ổn định (6/6 lần so) ở **buildconfig** và **doc**; không ổn định ở git, license; hơi kém ở dependency, quality."),
  B("Không có sampler thì HCL ≈ CE: SupCon cần cặp dương của lá hiếm trong batch."),

  H2("4.4. Vì sao HCL cải thiện ít, và loss mới"),
  P("Em lưu embedding của mô hình và đo độ tương đồng cosine giữa các cặp run:"),
  table(["Loss (fold 1)", "Cùng lá", "Anh em (cùng cha)", "Khác cha", "kNN-10 acc lá", "Macro-F1 lá (nguyên / che)"], [
    ["CE (3 đầu theo cây)", "0,80", "0,59", "0,22", "0,853", "0,645 / 0,588"],
    ["HCL cũ (SupCon cứng 3 tầng)", "0,79", "0,59", "0,17", "0,848", "0,641 / 0,596"],
    ["**soft: SupCon cặp dương mềm**", "0,78", "**0,50**", "0,18", "**0,867**", "**0,651 / 0,606**"],
    ["proxy: nguyên mẫu phân cấp", "0,78", "0,54", "0,19", "0,848", "0,639 / 0,586"],
  ], [30, 10, 14, 11, 13, 22], { hl: [2] }),
  CAP("Bảng 7. Hình học không gian embedding và kết quả fold 1 (seed 0, lai + sampler). Tham số của soft/proxy chốt trước, không dò."),
  N("**CE đã phân cấp sẵn:** với 3 đầu phân loại theo 3 tầng, CE tự tạo hình học cây (cùng lá rất gần, anh em gần vừa, khác cha xa). Mục tiêu của HCL phần lớn đã đạt được."),
  N("**HCL cũ kéo anh em quá gần:** SupCon ở tầng 2 coi lá anh em là cặp dương đầy đủ, làm khó tách quality / doc / license, test / itest, crash / network / git."),
  N("**Lá hiếm thiếu cặp dương** trong batch 12 run (sampler theo lớp sửa được phần này)."),
  N("**Nút thắt thông tin:** nhiều lỗi sai do log thiếu bằng chứng; nhãn tầng 3 của quy tắc còn thô (ví dụ tách test / itest theo tên workflow)."),
  P("Loss **soft** (cùng lá trọng số 1, anh em 0,4, khác cha 0) đạt cả hai tiêu chí đặt trước: tách anh em ra (0,59 → 0,50) mà cụm cùng lá vẫn chặt, và macro-F1 lá hơn CE, HCL cũ. Lá hưởng lợi: itestfailure 0,70 → 0,81, network 0,68 → 0,76, dependency 0,75 → 0,80 (so với HCL cũ). Mới có 1 fold, cần chạy đủ 5 fold × nhiều seed."),

  H1("5. So sánh với LLM"),
  P("Mục đích: trả lời câu hỏi \"đưa log cho AI thì phân loại đúng đến đâu\". LLM **chỉ dùng để so sánh, không dùng làm nguồn nhãn**."),
  B("**Mô hình:** Gemini 3.5 Flash-Lite (rẻ nhất trong các mô hình phổ biến trên Kaggle Benchmarks), zero-shot."),
  B("**Đầu vào:** ngữ cảnh CI + 12.000 ký tự cuối của log (cùng nguồn với mô hình); prompt định nghĩa 15 lá; đầu ra có cấu trúc {lá, dòng bằng chứng}."),
  B("**Tập chấm:** 203 run người gán, và 351 run nhãn quy tắc (25 run mỗi lá, cân bằng theo lá) chạy cả log nguyên vẹn và log đã che. Tổng 905 lời gọi, **chi phí $0,95** (bản 2: $1,07), trong quota AI miễn phí của Kaggle."),
  gap(),
  table(["Mô hình (tầng 2, 187 run người gán)", "acc", "macro-F1"], [
    ["Quy tắc (được lợi: đã sửa theo chính tập này)", "0,952", "0,906"],
    ["**Lai CE**", "**0,877**", "**0,738**"],
    ["LLM bản 1", "0,872", "0,733"],
    ["LLM bản 2 (prompt ghi rõ quy ước)", "0,866", "0,730"],
    ["Lai + sampler HCL", "0,866", "0,726"],
    ["TF-IDF A", "0,861", "0,722"],
  ], [60, 20, 20]),
  CAP("Bảng 8. Trên nhãn người (độ đúng thật), các run quy tắc gán được. Mô hình của đề tài ngang LLM."),
  table(["Mô hình (351 run, cân bằng theo lá)", "Lá, nguyên vẹn", "Lá, đã che", "Tầng 2, nguyên vẹn", "Tầng 2, đã che"], [
    ["TF-IDF A", "0,461", "0,388", "0,582", "0,534"],
    ["Lai CE", "0,484", "0,439", "0,597", "0,575"],
    ["Lai + sampler HCL", "0,509", "0,464", "0,656", "**0,625**"],
    ["**LLM bản 1**", "**0,719**", "0,610", "0,729", "0,616"],
    ["LLM bản 2", "0,679", "**0,646**", "**0,730**", "0,670"],
  ], [40, 15, 15, 15, 15]),
  CAP("Bảng 9. Trên nhãn quy tắc, mẫu cân bằng theo lá (lá hiếm nặng ký hơn thực tế)."),
  B("**LLM không đúng hoàn toàn:** trên nhãn người chỉ đạt acc 0,84–0,87, sai nhiều ở flaky (cần kết quả chạy lại), test / infra, infra / network."),
  B("**Ở tầng 2, mô hình của đề tài ngang LLM**, kể cả TF-IDF; lợi thế của LLM nằm ở **lá hiếm** (license 0,98, compatibility 0,98, doc 0,84) nhờ kiến thức sẵn có về các công cụ (apache-rat, revapi, javadoc), trong khi mô hình chỉ có vài chục mẫu."),
  B("**Ghi quy ước của đề tài vào prompt (bản 2) gần như không giúp** trên nhãn người (0,842 → 0,833). Ví dụ tách test / itest theo tên đã ghi rõ nhưng F1 vẫn khoảng 0,47; xem từng run thì phần lớn chênh lệch nằm ở chính nhãn quy tắc tầng 3 còn thô. Precision tầng 3 của quy tắc **chưa được đo bằng người**."),

  H1("6. Hướng đi: mô hình phân cấp làm bộ định tuyến cho LLM"),
  P("Developer khi build fail cần biết **nguyên nhân nằm ở đâu, đoạn code nào**; phần giải thích và chỉ chỗ sửa phù hợp với LLM. Mô hình phân cấp đảm nhận phần phân loại và định tuyến, để LLM chỉ xử lý run khó và chỉ đọc phần log cần thiết:"),
  table(["Bước", "Thành phần", "Việc làm"], [
    ["1", "Mô hình phân cấp", "Phân loại 3 tầng + độ tin cậy + chọn các đoạn log quan trọng (attention đoạn → job → run)"],
    ["2a", "Nhánh môi trường", "Tầng 1 = env (infra, network, crash, flaky): gợi ý chạy lại / báo DevOps, không gọi LLM"],
    ["2b", "Nhánh tự động", "Lá đông, tin cậy cao: trích vị trí bằng mẫu (file:dòng của compile, tên test fail, vi phạm checkstyle, artifact lỗi)"],
    ["2c", "Nhánh LLM", "Không chắc / lá hiếm: gửi LLM chỉ vài đoạn log mô hình chọn + diff + prompt theo loại lỗi; LLM chỉ ra dòng lỗi, đoạn code liên quan, gợi ý sửa"],
  ], [8, 22, 70]),
  CAP("Bảng 10. Pipeline đề xuất."),
  H2("6.1. Kết quả đo được"),
  table(["Thí nghiệm", "Kết quả chính"], [
    ["E1. Phân luồng theo tầng 1 (5 fold, 43.613 run)", "env chỉ 12,3% số run: tiết kiệm khoảng 13% lời gọi LLM, đổi lại 3,8% lỗi code bị đẩy nhầm sang env (lai CE). Bản có sampler kém hơn (8,6%)."],
    ["E2. Attention có chỉ đúng chỗ (2 fold, 18.953 run)", "Đoạn được chú ý nhất chứa dòng gây lỗi: 58% (đoạn cuối: 40%, ngẫu nhiên: 42%); **3 đoạn chú ý nhất: 92%**. Có thể gửi LLM khoảng 1.000 token thay vì 4.000."],
    ["E4. Định tuyến theo độ tin cậy (2 fold)", "Tín hiệu xác suất + kNN phát hiện dự đoán sai với **AUROC 0,87–0,90**. Giữ 80% run tự tin nhất thì độ đúng mức lá 0,93–0,94; ước tính toàn hệ thống khi gửi 20% run cho LLM khoảng 0,89 (chỉ mô hình: 0,82–0,84)."],
  ], [32, 68]),
  CAP("Bảng 11. Kết quả định tuyến. Ước tính E4 giả định LLM đúng 72% trên run bị chuyển, cần xác nhận bằng LLM thật."),
  H2("6.2. Vai trò của HCL trong hướng này"),
  B("Giá trị định tuyến chủ yếu đến từ **kiến trúc phân cấp** (attention đoạn → job → run, 3 đầu theo cây): ở E2 và E4, CE làm được ngang hoặc hơn HCL cũ; embedding của HCL cũ không giúp phát hiện run khó tốt hơn (AUROC kNN 0,83 so với 0,87)."),
  B("Loss HCL đóng góp ở **mức lá và lá hiếm** (+0,02, buildconfig, doc); loss **soft** mới cho embedding tốt nhất cho kNN (0,867), là ứng viên để cải thiện cả phân loại lẫn định tuyến."),
  B("Định vị trung thực: \"mô hình phân cấp phân loại nguyên nhân lỗi CI và khoanh vùng log cho LLM; loss tương phản theo cây cải thiện các lá hiếm\". Đề tài không tuyên bố vượt LLM về độ chính xác, mà nhấn mạnh chi phí (chạy cục bộ, gần như 0 đồng mỗi run), riêng tư (không gửi log ra ngoài) và việc làm LLM rẻ hơn, tập trung hơn."),

  H1("7. Hạn chế"),
  B("Nhãn tham chiếu chính là nhãn quy tắc; tập người gán chỉ có nhãn tầng 2 và người phân xử đã thấy nhãn quy tắc. **Chưa có nhãn người ở tầng 3.**"),
  B("Phần lớn so sánh HCL / CE mới có 1–2 seed; loss soft mới có 1 fold."),
  B("Các mô hình hiện chỉ train trên 100 repo đợt 1; dữ liệu 200 repo chưa dùng để train."),
  B("Nhánh diff chưa được đưa vào mô hình."),
  B("Ước tính toàn hệ thống trong E4 dựa trên độ đúng LLM đo ở mẫu cân bằng."),

  H1("8. Kế hoạch tuần tới"),
  N("**Xác nhận loss soft:** CE và soft, 5 fold × 3 seed, kiểm định bootstrap theo repo (khoảng 16 giờ GPU).", 2),
  N("**Thêm loại lỗi mới chỉ với vài ví dụ:** giấu một lá khỏi tập train rồi cho 5–10 ví dụ; so CE với soft (khoảng 4 giờ GPU).", 2),
  N("**E3:** LLM đọc 3 đoạn log mô hình chọn so với đọc cả đuôi log: độ chính xác, số token, có chỉ đúng dòng lỗi không (khoảng $1).", 2),
  N("**Train trên 200 repo** với cấu hình tốt nhất.", 2),
  N("**Gán tay khoảng 100 run ở mức lá** (tập trung test / itest và lá hiếm) để đo precision tầng 3 của quy tắc.", 2),
];

const doc = new Document({
  creator: "project3",
  title: "Báo cáo tuần 6",
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
