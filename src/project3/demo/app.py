"""Giao diện web của demo (Gradio) + mở ra ngoài bằng ngrok (03/11/2026). Chạy trên Colab GPU (scripts/colab/p3_demo.ipynb):

    from project3.demo.app import launch
    url = launch("/content/p3demo", "/content/p3w/C_s0_fold{fold}.model_soft0.pt", ngrok_token=...)

Nhập link một run GitHub Actions bị fail (hoặc chọn run mẫu đã lưu sẵn log trong gói demo, dùng được cả khi log trên
GitHub đã hết hạn sau 90 ngày) -> nhãn 3 tầng, gợi ý hành động, độ tự tin, các dòng log làm căn cứ.
"""
import gzip
import html
import json
from pathlib import Path

from .predict import ACTION, NAMES, URL, Predictor, agent_input, fetch_run
from .source import links as src_links
from .catalog import load as load_catalog, render as render_catalog


def src_md(o: dict, text: str) -> str:
    """Link mở file mã nguồn nhắc trong dòng log (tại commit của lần chạy), đánh dấu file có trong thay đổi của PR."""
    ls = src_links(text, o.get("repo"), o.get("head_sha"), o.get("diff_files"))
    return "".join(f" — [mở {l['path'].rsplit('/', 1)[-1]}{':' + str(l['line']) if l['line'] else ''}]({l['url']})"
                   + (" *(file có trong thay đổi)*" if l["in_diff"] else "") for l in ls[:2])


def src_html(o: dict, text: str) -> str:
    ls = src_links(text, o.get("repo"), o.get("head_sha"), o.get("diff_files"))
    return "".join(f' <a href="{html.escape(l["url"])}" target="_blank" style="color:#1d4ed8">[mở file'
                   f'{" · có trong thay đổi" if l["in_diff"] else ""}]</a>' for l in ls[:1])


def load_examples(bundle: Path) -> dict:
    """run_id -> (mô tả, bản ghi run đã lưu). Kaggle tự giải nén .json.gz thành .json khi tải dataset."""
    out = {}
    for f in sorted((Path(bundle) / "examples").rglob("*.json*")):
        b = f.read_bytes()
        rec = json.loads(gzip.decompress(b) if f.suffix == ".gz" else b)
        out[rec["run_id"]] = (rec.pop("note", ""), rec)
    return out


TIERS = ("Tầng 1 · Artifact", "Tầng 2 · Handling action", "Tầng 3 · Error type")


def summary(o: dict) -> str:
    if "error" in o:
        return f"**Không phân loại được.** {o['error']}"
    p, mc, rule = o["pred"], o["mc"], o["rule"]
    nm = lambda k: NAMES.get(k, k)
    code = lambda s: "`" + s.replace("`", "'") + "`"
    cell = lambda s: s.replace("|", "/").replace("`", "'")
    out = [f"### [{o['repo']} · run {o['run_id']}]({o['url']})",
           f"Workflow **{o['workflow']}**, sự kiện {o['event']}. Job lỗi: {', '.join(o['failed_jobs'])}. "
           f"Step lỗi: {o['failed_steps'] or 'không rõ'}."]
    if o["non_build"]:
        out.append(f"**Đây không phải lỗi build**: {o['non_build']}. Kết quả bên dưới chỉ để tham khảo.")
    out.append("| | Nhãn | Xác suất |\n|---|---|---|\n" + "\n".join(
        f"| {t} | **{nm(k)}** | {'—' if c is None else f'{c:.2f}'} |"
        for t, k, c in zip(TIERS, (p["l1"], p["l2"], p["leaf"]), (p["p_l1"], p["p_l2"], p["p_leaf"]))))
    out.append(f"**Gợi ý xử lý.** {ACTION.get(p['l2'], '')}")
    agree = f"Cho mô hình đoán lại {mc['passes']} lần, {mc['agree']:.0%} số lần ra cùng kết quả."
    out.append(f"**Độ tin cậy.** {'Đủ tin cậy.' if mc['answered'] else 'Chưa đủ tin cậy, nên có người xem lại.'} {agree}")
    out.append(f"**Bộ quy tắc.** Gán nhãn **{nm(rule['leaf'])}** dựa trên dòng {code(rule['evidence'][:160])}."
               if rule["leaf"] else "**Bộ quy tắc.** Không gán được nhãn cho lần chạy này.")
    if o.get("per_job"):
        out.append("**Kết quả từng job lỗi**\n\n| Job | Step lỗi | Artifact | Handling action | Error type | Tin cậy "
                   "| Bộ quy tắc |\n|---|---|---|---|---|---|---|\n" + "\n".join(
                       f"| {cell(j['job'])} | {cell(j['failed_steps'] or '—')} | {nm(j['pred']['l1'])} | "
                       f"{nm(j['pred']['l2'])} | **{nm(j['pred']['leaf'])}** | "
                       + ("Không phải build" if j["non_build"] else "Đủ" if j["mc"]["answered"] else "Chưa đủ")
                       + f" | {j['rule']['leaf'] or '—'} |" for j in o["per_job"]))
    if o.get("cause_lines"):
        out.append("**Dòng log có khả năng là nguyên nhân**\n\n" + "\n".join(
            f"{i}. {code(l['text'][:180])} — điểm {l['score']:.3f}, job {l['job']}{src_md(o, l['text'])}"
            for i, l in enumerate(o["cause_lines"], 1)))
    out.append("**Dòng log làm căn cứ để phân loại**\n\n" + "\n".join(
        f"{i}. {code(l['text'][:180])} — điểm {l['score']:.3f}, job {l['job']}{src_md(o, l['text'])}"
        for i, l in enumerate(o["lines"], 1)))
    out.append(f"<sub>Repo này không nằm trong dữ liệu huấn luyện của mô hình được dùng. "
               f"Thời gian xử lý {o['seconds']} giây.</sub>")
    return "\n\n".join(out)


def log_view(o: dict, k: int = 2) -> str:
    """Các đoạn log mô hình chú ý nhất, mỗi dòng tô màu theo điểm trong run."""
    if "chunks" not in o:
        return ""
    parts = []
    pad = "white-space:pre-wrap;padding:1px 6px;color:#222"
    num = '<span style="color:#999;display:inline-block;width:3em">{}</span>'
    box = 'font-family:Consolas,monospace;font-size:12px;border:1px solid #ddd;border-radius:6px;background:#fff'
    if o.get("cause_blocks"):  # 16/11: dòng nguyên nhân + dòng xung quanh, chính là phần log đưa cho agent
        parts.append('<h3 style="margin:8px 0">Dòng nguyên nhân và các dòng xung quanh</h3>'
                     '<p style="margin:0 0 4px;color:#555">Dòng tô đỏ là dòng mô hình chọn. Đây là phần log được đưa '
                     'cho agent ở ô bên dưới.</p>')
        for b in o["cause_blocks"]:
            rows = "".join(f'<div style="{pad};background:rgba(239,68,68,.25)">{html.escape(t)}{src_html(o, t)}</div>'
                           if m else f'<div style="{pad}">{html.escape(t)}</div>' for t, m in b["lines"])
            parts.append(f'<p style="margin:12px 0 4px;color:#222"><b>Job {html.escape(b["job"])}</b></p>'
                         f'<div style="{box}">{rows}</div>')
    parts.append('<h3 style="margin:16px 0 8px">Đoạn log mô hình chú ý nhiều nhất khi phân loại</h3>')
    for c in sorted(o["chunks"], key=lambda c: -c["weight"])[:k]:
        mx = max(s for _, s in c["lines"]) or 1
        rows = "".join(
            f'<div style="{pad};background:rgba(255,193,7,{min(1, s / mx) * 0.85:.2f})">{num.format(i)}{html.escape(t)}'
            f'{src_html(o, t)}<span style="float:right;color:#666">{s:.3f}</span></div>' if s >= 0.002 else
            f'<div style="{pad}">{num.format(i)}{html.escape(t)}{src_html(o, t)}</div>' for i, (t, s) in enumerate(c["lines"]))
        parts.append(f'<p style="margin:12px 0 4px;color:#222"><b>Job {html.escape(c["job"])}</b>, step '
                     f'{html.escape(c["step"] or "không rõ")}</p><div style="font-family:Consolas,monospace;'
                     f'font-size:12px;border:1px solid #ddd;border-radius:6px;background:#fff">{rows}</div>')
    return "".join(parts)


def light_style(gr):
    """Giao diện nền trắng (cả khi máy người xem để chế độ tối); dùng chung cho app (Colab) và local (laptop)."""
    theme = gr.themes.Default(primary_hue="red", neutral_hue="slate").set(
        body_background_fill="white", body_background_fill_dark="white", block_background_fill="white",
        block_background_fill_dark="white", body_text_color_dark="#1f2937", block_label_text_color_dark="#374151",
        input_background_fill_dark="white", border_color_primary_dark="#e5e7eb")
    from .catalog import CSS as CAT_CSS  # 17/11: catalog lỗi + tông đỏ trắng
    css = (".gradio-container{max-width:1100px!important;margin:auto}"
           "button.primary{background:#ee0033!important;border-color:#ee0033!important;color:#fff!important}"
           "button[role=tab][aria-selected=true]{color:#ee0033!important;border-color:#ee0033!important}"
           + CAT_CSS)
    light = "() => document.body.classList.remove('dark')"  # luôn nền trắng, kể cả khi máy người xem để chế độ tối
    style = dict(theme=theme, css=css, js=light)
    in_blocks = int(gr.__version__.split(".")[0]) < 6  # Gradio 6 chuyển theme / css / js từ Blocks sang launch()
    return style, in_blocks


def launch(bundle: str, weights: str, port: int = 7860, ngrok_token: str = None, share: bool = False,
           cause_weights: str = None) -> str:
    import gradio as gr
    from project3.crawl.github import GitHub, load_token
    gr.close_all()  # chạy lại ô LAUNCH trong cùng phiên: bản cũ còn giữ cổng -> "Cannot find empty port"
    if ngrok_token:  # tắt tiến trình ngrok cũ; không dùng get_tunnels() vì nó tự khởi động ngrok khi chưa có token
        from pyngrok import ngrok
        ngrok.kill()
    pred = Predictor(Path(bundle), weights, cause_weights=cause_weights)
    pred.net(pred.default_fold)  # tải UniXcoder + weight trước, để lần bấm đầu không chờ lâu
    if cause_weights:
        pred.net(pred.default_fold, cause=True)
    try:  # token GitHub chỉ cần khi dán link trực tiếp trên trang Colab; demo.local tự tải run ở laptop
        gh = GitHub(load_token())
    except Exception:  # noqa: BLE001
        gh = None
    examples = load_examples(bundle)

    def run(url):
        m = URL.search(url or "")
        if not m:
            return "Link cần có dạng `https://github.com/<owner>/<repo>/actions/runs/<id>`.", "", "", {}
        rid = int(m.group(2))
        try:
            rec = examples[rid][1] if rid in examples else fetch_run(url, gh)
            o = pred.predict(rec)
        except Exception as e:  # noqa: BLE001 — hiện lỗi cho người dùng thay vì sập giao diện
            return f"**Có lỗi khi xử lý.** {type(e).__name__}: {e}", "", "", {}
        return render(o)

    def render(o):
        slim = {k: v for k, v in o.items() if k != "chunks"}
        return summary(o), log_view(o), agent_input(o), slim

    def run_record(rec_json):
        """16/11: laptop (demo.local) tự tải run bằng token GitHub của máy rồi gửi bản ghi sang -> Colab không cần token."""
        try:
            return render(pred.predict(json.loads(rec_json)))
        except Exception as e:  # noqa: BLE001
            return f"**Có lỗi khi xử lý.** {type(e).__name__}: {e}", "", "", {}

    style, in_blocks = light_style(gr)

    with gr.Blocks(title="Phân loại lỗi build CI", **(style if in_blocks else {})) as demo:
        with gr.Tab("Phân loại lỗi"):
            gr.Markdown("## Phân loại nguyên nhân lỗi build CI\n"
                        "Dán link một lần chạy GitHub Actions bị lỗi. Mô hình đọc log, thông tin CI và phần code thay đổi, "
                        "rồi cho biết lỗi thuộc loại nào, nên xử lý ra sao và dựa vào những dòng log nào để kết luận.\n\n"
                        "Nhãn được suy ra từ nội dung log chứ không từ tên job, nên một job tên `lint` vẫn có thể là lỗi "
                        "biên dịch. Mô hình được huấn luyện trên các dự án Java và Kotlin dùng Maven hoặc Gradle.")
            with gr.Row(equal_height=True):
                url = gr.Textbox(label="Link lần chạy", placeholder="https://github.com/<owner>/<repo>/actions/runs/<id>",
                                 scale=5)
                btn = gr.Button("Phân loại", variant="primary", scale=1)
            if examples:
                pick = gr.Dropdown([(f"{v[1]['repo']} · {v[0]}", v[1]["url"]) for v in examples.values()], value=None,
                                   label="Hoặc chọn một lần chạy mẫu, log đã được lưu sẵn")
                pick.change(lambda u: u or "", pick, url)
            out_md = gr.Markdown()
            out_log = gr.HTML()
            # 16/11: đầu vào cho agent lập trình (nhãn + dòng nguyên nhân), dán vào agent đang mở repo ở đúng commit
            out_agent = gr.Textbox(label="Đầu vào cho agent tìm nguyên nhân trong code (sao chép rồi dán vào Claude Code "
                                         "hoặc agent khác đang mở repo ở đúng commit)", lines=8, max_lines=30,
                                   interactive=False,  # Gradio 6 đổi show_copy_button thành buttons
                                   **({"show_copy_button": True} if in_blocks else {"buttons": ["copy"]}))
            with gr.Accordion("Kết quả đầy đủ dạng JSON", open=False):
                out_json = gr.JSON()
            outs = [out_md, out_log, out_agent, out_json]
            btn.click(run, url, outs, api_name="predict")  # 16/11: laptop gọi qua gradio_client (demo.local)
            url.submit(run, url, outs, api_name=False)
            rec_in, rec_btn = gr.Textbox(visible=False), gr.Button(visible=False)
            rec_btn.click(run_record, rec_in, outs, api_name="predict_record")
            ex_btn, ex_out = gr.Button(visible=False), gr.JSON(visible=False)  # danh sách run mẫu cho demo.local
            ex_btn.click(lambda: [(f"{v[1]['repo']} · {v[0]}", v[1]["url"]) for v in examples.values()], None, ex_out,
                         api_name="examples")
        with gr.Tab("Catalog lỗi CI/CD"):
            gr.HTML(render_catalog(load_catalog(bundle)))
    demo.queue().launch(server_name="0.0.0.0", server_port=port, prevent_thread_lock=True, share=share, quiet=True,
                        **({} if in_blocks else style))
    if not ngrok_token:
        return f"http://localhost:{port}"
    from pyngrok import conf, ngrok
    conf.get_default().auth_token = ngrok_token  # set_auth_token lỗi khi đã lưu token từ lần chạy trước
    return ngrok.connect(port, "http").public_url
