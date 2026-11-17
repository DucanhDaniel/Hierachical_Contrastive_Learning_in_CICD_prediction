"""Catalog lỗi CI/CD trong demo (17/11/2026; góp ý GVHD 05/11: "lập bản đồ lỗi CI/CD thường gặp, hiển thị trong tool").

Nội dung lấy từ báo cáo tuần 9 (đặc điểm từng nhánh, 30 ví dụ điển hình, Phụ lục B: dấu hiệu log + nhóm tương ứng ở
Zheng và cộng sự, TOSEM) + số run theo lá + đoạn log quanh dòng bằng chứng của từng ví dụ. Phần "cách sửa", "ai sửa",
"AI được làm gì" là ĐỀ XUẤT (tự đặt, đã báo người dùng 17/11).

    python -m project3.demo.catalog      # -> data/demo_bundle/catalog.json (export.py cũng gọi)
"""
import html
import json
import re
from pathlib import Path

REPORT = Path("docs/Báo cáo/bao-cao-tuan-9.build.js")
OUT = Path("data/demo_bundle/catalog.json")
CTX = 4  # số dòng log trước/sau dòng bằng chứng trong ví dụ (tự đặt)

BRANCH_OF = {"viet_code": 1, "build_local": 2, "ci_merge": 3, "cau_hinh_ci": 4, "chay_lai": 5}
LEAF = {  # tên hiển thị, định nghĩa ngắn, cách sửa, ai sửa (vai trò), AI được làm gì
    "compile": ("Lỗi biên dịch", "Mã nguồn không biên dịch được: sai cú pháp, gọi lớp/hàm không tồn tại, sai kiểu.",
                "Mở đúng file và dòng trình biên dịch báo, sửa rồi push lại.", "Tác giả PR / chủ file lỗi", "pr"),
    "quality": ("Kiểm tra chất lượng code", "Code chạy đúng nhưng vi phạm quy tắc định dạng, lint hoặc phân tích tĩnh "
                "(Spotless, Checkstyle, PMD, SpotBugs).", "Chạy lệnh tự sửa của công cụ (ví dụ spotlessApply) hoặc sửa theo "
                "vi phạm được liệt kê.", "Tác giả PR", "pr"),
    "doc": ("Lỗi tài liệu (javadoc)", "Bước sinh tài liệu dừng build: tham chiếu sai, thẻ không hợp lệ trong chú thích.",
            "Sửa chú thích javadoc tại dòng được báo.", "Tác giả PR / chủ file lỗi", "pr"),
    "buildconfig": ("Cấu hình build sai", "File build (pom.xml, build.gradle) khai báo sai: trùng plugin, thiếu phiên "
                    "bản, lỗi script Gradle.", "Sửa file build tại dòng được báo; kiểm tra danh mục phiên bản.",
                    "Người phụ trách build của module", "comment"),
    "testfailure": ("Unit test lỗi", "Unit test không đạt; log thường chỉ có tên test và tổng số test lỗi.",
                    "Chạy lại test của module ở máy (mvn test / gradle test) để xem chi tiết, sửa code hoặc test.",
                    "Tác giả PR / chủ file test", "comment"),
    "dependency": ("Lỗi thư viện phụ thuộc", "Không tìm thấy hoặc xung đột phiên bản thư viện; thư viện lệch phiên bản Java.",
                   "Sửa phiên bản khai báo, thêm kho thư viện hoặc tạo lại file khoá phiên bản.",
                   "Tác giả PR / người phụ trách build", "comment"),
    "license": ("Thiếu ghi chú bản quyền", "File thiếu phần header bản quyền theo yêu cầu của dự án (license-maven-plugin, "
                "Apache RAT).", "Chạy lệnh tự thêm header (ví dụ license:format) rồi push lại.", "Tác giả PR", "pr"),
    "compatibility": ("Phá vỡ tương thích API", "PR xoá hoặc đổi API public, làm hỏng tương thích với bản đã phát hành.",
                      "Giữ lại API cũ (đánh dấu deprecated) hoặc tăng số phiên bản cho đúng.", "Người duy trì dự án",
                      "comment"),
    "itestfailure": ("Test tích hợp lỗi", "Test cần môi trường của CI (server thật, container, máy ảo Android) không đạt.",
                     "Xem kết quả test trên CI, tái hiện bằng môi trường tương tự rồi sửa.", "Tác giả PR / chủ file test",
                     "comment"),
    "flaky": ("Test chập chờn", "Test fail lần đầu rồi đạt khi chạy lại; không test nào fail hẳn.",
              "Không sửa code của PR; ghi nhận test chập chờn và chạy lại.", "Người duy trì bộ test", "comment"),
    "git": ("Lỗi thao tác git trong workflow", "Workflow không đẩy/kéo được nhánh hoặc repo khác (quyền, khoá ref).",
            "Sửa quyền token hoặc cấu hình bước git trong file workflow.", "Người phụ trách CI", "comment"),
    "androidsdk": ("Lỗi môi trường Android", "Máy ảo Android chưa sẵn sàng hoặc không cài được gói SDK.",
                   "Sửa thiết lập máy ảo, thời gian chờ hoặc phiên bản gói trong workflow.", "Người phụ trách CI", "comment"),
    "infra": ("Cấu hình CI / runner sai", "Lỗi file workflow, secret, quyền, khoá dùng chung hoặc thiết lập runner.",
              "Sửa file workflow hoặc cập nhật secret; không cần sửa code.", "Người phụ trách CI / quản trị repo",
              "comment"),
    "network": ("Lỗi mạng / dịch vụ ngoài", "Không tải được thư viện, action hoặc image do kết nối, giới hạn truy cập.",
                "Kiểm tra dịch vụ ngoài; khi ổn thì chạy lại job.", "Người trực hạ tầng", "comment"),
    "crash": ("Runner dừng giữa chừng", "Máy chạy CI bị tắt, hết bộ nhớ hoặc quá thời gian; không có lỗi từ build.",
              "Chạy lại; nếu lặp lại thì tăng tài nguyên hoặc thời gian chờ.", "Người trực hạ tầng", "comment"),
}
AI_POLICY = {"pr": "Agent được đề xuất cách sửa và (sau này) mở pull request sửa",
             "comment": "Agent chỉ bình luận nguyên nhân và cách sửa; người sửa"}


def _js_strings(s: str) -> list:
    return [json.loads('"' + x + '"') for x in re.findall(r'"((?:[^"\\]|\\.)*)"', s)]


def build() -> dict:
    import pandas as pd
    from project3.model.inputs import focus_window
    js = REPORT.read_text(encoding="utf-8")
    cnt = {k: v for k, v in re.findall(r'(\w+): "([\d.]+)"', re.search(r"const CNT = \{(.*?)\};", js, re.S).group(1))}
    branches = {}
    for m in re.finditer(r'P\("\*\*Nhánh (\d)\. ([^*]+)\*\* \(([^)]*)\)\. Đặc điểm chung: ((?:[^"\\]|\\.)*)"\)', js):
        trait = json.loads('"' + m.group(4) + '"')
        branches[int(m.group(1))] = {"name": m.group(2), "trait": trait[:1].upper() + trait[1:]}
    ex = json.loads(Path("data/results/typical_examples/examples.json").read_text(encoding="utf-8"))
    examples, cur = {}, None
    for m in re.finditer(r'\[(L\("(\w+)"\)|"")\s*,\s*runCell\("(\d+)",\s*"((?:[^"\\]|\\.)*)"\),\s*"((?:[^"\\]|\\.)*)",\s*'
                         r'"((?:[^"\\]|\\.)*)"\]', js):
        cur = m.group(2) or cur
        rid = m.group(3)
        e = ex[rid]
        examples.setdefault(cur, []).append(dict(
            run_id=int(rid), repo=e["repo"], step=json.loads('"' + m.group(4) + '"'), p=e["p"],
            evidence=json.loads('"' + m.group(5) + '"'), why=json.loads('"' + m.group(6) + '"'),
            url=f"https://github.com/{e['repo']}/actions/runs/{rid}", attn=e.get("attn") or ""))
    sig = {}
    tail = js[js.index('table(["Nhánh", "Lá", "Dấu hiệu'):]
    for line in tail[:6000].splitlines():
        s = _js_strings(line) if line.strip().startswith('["') else []
        if len(s) == 4 and s[1] in LEAF:
            sig[s[1]] = {"signs": s[2].split("\n"), "zheng": s[3]}
    # đoạn log quanh dòng bằng chứng (đoạn mô hình đọc), để người xem thấy lỗi trông ra sao
    ids = [e["run_id"] for v in examples.values() for e in v]
    ch = pd.read_parquet("data/kaggle_log_ds/chunks.parquet", columns=["run_id", "job_id", "chunk_idx", "text"],
                         filters=[("run_id", "in", ids)])
    for v in examples.values():
        for e in v:
            key = re.sub(r"`", "", e["evidence"].split("\n")[0])[:50]
            key = key.split("...")[0].strip()[:40]
            snip = []
            for t in ch[ch.run_id == e["run_id"]].sort_values(["job_id", "chunk_idx"]).text:
                ls = focus_window(t, 1600, "split").split("\n")
                hit = next((i for i, x in enumerate(ls) if key and key in x), None)
                if hit is None and e["attn"]:
                    hit = next((i for i, x in enumerate(ls) if e["attn"][:50] in x), None)
                if hit is not None:
                    snip = [(x[:220], i == hit) for i, x in enumerate(ls[max(0, hit - CTX):hit + CTX + 1], max(0, hit - CTX))]
                    break
            e["log"] = snip
    tree = json.loads(Path("data/kaggle_log_ds/label_tree.json").read_text(encoding="utf-8"))
    leaves = []
    for leaf, (name, defin, fix, who, ai) in LEAF.items():
        t2 = tree["parent"][leaf]
        leaves.append(dict(leaf=leaf, name=name, definition=defin, fix=fix, who=who, ai=ai, branch=BRANCH_OF[t2],
                           runs=cnt.get(leaf, "?"), **sig.get(leaf, {"signs": [], "zheng": ""}),
                           examples=examples.get(leaf, [])))
    cat = {"branches": branches, "leaves": leaves,
           "source": "Dữ liệu đề tài: 61.602 lần chạy lỗi có nhãn, 200+ repo Java/Kotlin (Maven, Gradle). Nhóm đối chiếu: "
                     "Zheng và cộng sự, Why Do GitHub Actions Workflows Fail? (ACM TOSEM)."}
    return cat


def md_inline(s: str) -> str:
    """`code` -> <code>, phần còn lại escape."""
    return "".join(f"<code>{html.escape(x)}</code>" if k % 2 else html.escape(x) for k, x in enumerate(s.split("`")))


CSS = """
.cat{font-family:Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:#1f2937}
.cat-hero{background:linear-gradient(120deg,#ee0033 0%,#b8002a 100%);color:#fff;border-radius:14px;padding:22px 26px;margin-bottom:18px}
.cat-hero h2{margin:0 0 6px;font-size:22px;font-weight:700;color:#fff}
.cat-hero p{margin:0;opacity:.92;font-size:13.5px;color:#fff}
.cat-stats{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
.cat-stat{background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.25);border-radius:10px;padding:8px 14px;font-size:12.5px;color:#fff}
.cat-stat b{display:block;font-size:18px}
.cat-nav{display:flex;flex-wrap:wrap;gap:8px;margin:4px 0 18px}
.cat-nav a{border:1px solid #f3c2cc;background:#fff5f7;color:#b8002a!important;border-radius:999px;padding:4px 12px;font-size:12.5px;text-decoration:none!important}
.cat-nav a:hover{background:#ee0033;color:#fff!important}
.cat-branch{margin:26px 0 10px;padding-left:12px;border-left:4px solid #ee0033}
.cat-branch h3{margin:0;font-size:17px;color:#111827}
.cat-branch .tier{font-size:12px;color:#6b7280;margin-top:2px}
.cat-branch p{margin:6px 0 0;font-size:13px;color:#374151}
.cat-card{border:1px solid #e5e7eb;border-radius:12px;background:#fff;margin:12px 0;box-shadow:0 1px 2px rgba(0,0,0,.04);overflow:hidden}
.cat-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;padding:14px 18px;border-bottom:1px solid #f1f5f9}
.cat-head h4{margin:0;font-size:16px;color:#111827}
.cat-head .id{font-family:Consolas,monospace;font-size:12px;color:#ee0033;background:#fff1f3;border-radius:6px;padding:1px 7px;margin-left:6px}
.cat-head .def{margin:4px 0 0;font-size:13px;color:#4b5563}
.cat-badge{white-space:nowrap;font-size:12px;border-radius:999px;padding:3px 10px;background:#f3f4f6;color:#374151}
.cat-body{display:grid;grid-template-columns:1fr 1fr;gap:0}
.cat-sec{padding:12px 18px;font-size:13px}
.cat-sec+.cat-sec{border-left:1px solid #f1f5f9}
.cat-sec h5{margin:0 0 6px;font-size:11.5px;letter-spacing:.04em;text-transform:uppercase;color:#9ca3af}
.cat-sec ul{margin:0;padding-left:18px}
.cat-sec li{margin:2px 0}
.cat code{font-family:Consolas,monospace;font-size:12px;background:#f8fafc;border:1px solid #eef2f7;border-radius:4px;padding:0 4px;color:#111827}
.cat-ai{display:inline-block;font-size:12px;border-radius:6px;padding:2px 8px;margin-top:4px}
.cat-ai.pr{background:#ecfdf5;color:#047857}.cat-ai.comment{background:#fff7ed;color:#b45309}
.cat-ex{border-top:1px solid #f1f5f9;padding:12px 18px}
.cat-ex h5{margin:0 0 8px;font-size:11.5px;letter-spacing:.04em;text-transform:uppercase;color:#9ca3af}
.cat-exi{margin-bottom:12px}
.cat-exi .meta{font-size:12.5px;color:#374151;margin-bottom:4px}
.cat-exi .meta a{color:#ee0033!important;font-weight:600;text-decoration:none!important}
.cat-exi .why{font-size:12.5px;color:#4b5563;margin-top:4px}
.cat-log{font-family:Consolas,monospace;font-size:11.5px;background:#0f172a;color:#cbd5e1;border-radius:8px;padding:8px 0;overflow-x:auto}
.cat-log div{white-space:pre;padding:0 12px;color:#cbd5e1!important}
.cat-log .hit{background:rgba(238,0,51,.32);color:#fff!important}
.cat-foot{font-size:12px;color:#6b7280;margin-top:18px}
@media (max-width:760px){.cat-body{grid-template-columns:1fr}.cat-sec+.cat-sec{border-left:0;border-top:1px solid #f1f5f9}}
"""


def render(cat: dict) -> str:
    if not cat:
        return "<p>Chưa có dữ liệu catalog.</p>"
    nb = len(cat["branches"])
    total = sum(int(str(l["runs"]).replace(".", "")) for l in cat["leaves"] if str(l["runs"]).replace(".", "").isdigit())
    out = ['<div class="cat">',
           '<div class="cat-hero"><h2>Catalog lỗi build CI/CD</h2><p>Các loại lỗi thường gặp khi build dự án Java/Kotlin '
           'trên GitHub Actions, xếp theo nơi chứa lỗi và cách xử lý. Mỗi loại kèm dấu hiệu nhận biết trong log, '
           'cách sửa, người nên sửa và ví dụ thật.</p>'
           f'<div class="cat-stats"><div class="cat-stat"><b>{len(cat["leaves"])}</b>loại lỗi</div>'
           f'<div class="cat-stat"><b>{nb}</b>cách xử lý</div><div class="cat-stat"><b>{f"{total:,}".replace(",", ".")}</b>lần chạy lỗi</div>'
           f'<div class="cat-stat"><b>{sum(len(l["examples"]) for l in cat["leaves"])}</b>ví dụ thật</div></div></div>',
           '<div class="cat-nav">' + "".join(f'<a href="#cat-{l["leaf"]}">{html.escape(l["name"])}</a>'
                                             for l in cat["leaves"]) + "</div>"]
    for b in sorted(cat["branches"], key=int):
        br = cat["branches"][b]
        t1, t2 = (br["name"].split(" → ") + [""])[:2]
        out.append(f'<div class="cat-branch"><h3>{html.escape(t2)}</h3><div class="tier">Nơi chứa lỗi: '
                   f'{html.escape(t1)}</div><p>{md_inline(br["trait"])}</p></div>')
        for l in [x for x in cat["leaves"] if str(x["branch"]) == str(b)]:
            signs = "".join(f"<li>{md_inline(s)}</li>" for s in l["signs"]) or "<li>—</li>"
            exs = []
            for e in l["examples"]:
                log = "".join(f'<div class="{"hit" if h else ""}">{html.escape(t) or " "}</div>' for t, h in e["log"])
                conf = "mô hình chưa học loại này" if e["p"] is None else f"mô hình tự tin {e['p']:.2f}"
                exs.append(f'<div class="cat-exi"><div class="meta"><a href="{html.escape(e["url"])}" target="_blank">'
                           f'{html.escape(e["repo"])} · run {e["run_id"]}</a> — bước <i>{html.escape(e["step"])}</i> · '
                           f'{conf}</div>' + (f'<div class="cat-log">{log}</div>' if log else
                                              f'<div class="meta">{md_inline(e["evidence"])}</div>')
                           + f'<div class="why">{md_inline(e["why"])}</div></div>')
            out.append(
                f'<div class="cat-card" id="cat-{l["leaf"]}"><div class="cat-head"><div><h4>{html.escape(l["name"])}'
                f'<span class="id">{l["leaf"]}</span></h4><p class="def">{html.escape(l["definition"])}</p></div>'
                f'<span class="cat-badge">{l["runs"]} lần chạy</span></div><div class="cat-body">'
                f'<div class="cat-sec"><h5>Dấu hiệu trong log (số lần chạy · số repo)</h5><ul>{signs}</ul>'
                f'<h5 style="margin-top:10px">Nhóm tương ứng (Zheng và cộng sự)</h5>{md_inline(l["zheng"]) or "—"}</div>'
                f'<div class="cat-sec"><h5>Cách sửa</h5>{html.escape(l["fix"])}<h5 style="margin-top:10px">Người nên sửa</h5>'
                f'{html.escape(l["who"])}<br><span class="cat-ai {l["ai"]}">{AI_POLICY[l["ai"]]}</span></div></div>'
                + (f'<div class="cat-ex"><h5>Ví dụ thật</h5>{"".join(exs)}</div>' if exs else "") + "</div>")
    out.append(f'<p class="cat-foot">{html.escape(cat["source"])} Cách sửa, người nên sửa và quyền của AI là đề xuất '
               f'của đề tài.</p></div>')
    return "".join(out)


def load(bundle) -> dict:
    f = Path(bundle) / "catalog.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    cat = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(cat, ensure_ascii=False), encoding="utf-8")
    print("->", OUT, len(cat["leaves"]), "lá,", sum(len(l["examples"]) for l in cat["leaves"]), "ví dụ,",
          sum(bool(e["log"]) for l in cat["leaves"] for e in l["examples"]), "có đoạn log;",
          "nhánh:", list(cat["branches"]), "; lá có dấu hiệu:", sum(bool(l["signs"]) for l in cat["leaves"]))
