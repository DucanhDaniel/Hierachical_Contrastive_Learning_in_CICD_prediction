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

from .predict import ACTION, NAMES, URL, Predictor, fetch_run


def load_examples(bundle: Path) -> dict:
    """run_id -> (mô tả, bản ghi run đã lưu). Kaggle tự giải nén .json.gz thành .json khi tải dataset."""
    out = {}
    for f in sorted((Path(bundle) / "examples").rglob("*.json*")):
        b = f.read_bytes()
        rec = json.loads(gzip.decompress(b) if f.suffix == ".gz" else b)
        out[rec["run_id"]] = (rec.pop("note", ""), rec)
    return out


def summary(o: dict) -> str:
    if "error" in o:
        return f"**Không phân loại được:** {o['error']}"
    p, mc, rule = o["pred"], o["mc"], o["rule"]
    nm = lambda k: NAMES.get(k, k)
    head = (f"### [{o['repo']} · run {o['run_id']}]({o['url']})\n"
            f"Workflow **{o['workflow']}** ({o['event']}) · job lỗi: {', '.join(o['failed_jobs'])} · step lỗi: "
            f"{o['failed_steps'] or '—'}\n\n")
    if o["non_build"]:
        head += f"> ⚠️ **Lỗi không phải do build** (bước thủ tục: {o['non_build']}). Kết quả dưới đây chỉ để tham khảo.\n\n"
    verdict = ("✅ **Đủ tự tin**" if mc["answered"] else "❓ **Không chắc, cần người xem**") + \
              f" (đoán lại {mc['passes']} lần, {mc['agree']:.0%} lần cùng đáp án; độ phân tán {mc['entropy']:.2f}, ngưỡng {mc['threshold']:.2f})"
    rows = [("Lỗi nằm ở đâu", nm(p["l1"]), p["p_l1"]), ("Lẽ ra phải sửa lúc nào", nm(p["l2"]), p["p_l2"]),
            ("Loại lỗi", nm(p["leaf"]), p["p_leaf"])]
    tbl = "| Tầng | Dự đoán | Xác suất |\n|---|---|---|\n" + "\n".join(
        f"| {a} | **{b}** | {c:.3f} |" if c is not None else f"| {a} | **{b}** | — |" for a, b, c in rows)
    code = lambda s: "`" + s.replace("`", "'") + "`"
    rule_txt = (f"gán được: **{nm(rule['leaf'])}** (dòng bằng chứng: {code(rule['evidence'][:160])})" if rule["leaf"]
                else "**không gán được** (run `?`) — đây là chỗ mô hình bổ sung cho quy tắc")
    lines = "\n".join(f"{i}. {code(l['text'][:180])} — điểm {l['score']:.3f} (job {l['job']})"
                      for i, l in enumerate(o["lines"], 1))
    return (head + tbl + f"\n\n**Gợi ý:** {ACTION.get(p['l2'], '')}\n\n**Độ tự tin:** {verdict}\n\n"
            f"**Bộ quy tắc:** {rule_txt}\n\n**Dòng log làm căn cứ (5 dòng điểm cao nhất):**\n{lines}\n\n"
            f"<sub>Mô hình của phần chia {o['fold']} ({'repo chưa thấy khi huấn luyện' if o['seen_repo'] else 'repo mới'}); "
            f"{o['seconds']} giây.</sub>")


def log_view(o: dict, k: int = 2) -> str:
    """Các đoạn log mô hình chú ý nhất, mỗi dòng tô màu theo điểm trong run."""
    if "chunks" not in o:
        return ""
    parts = []
    for c in sorted(o["chunks"], key=lambda c: -c["weight"])[:k]:
        mx = max(s for _, s in c["lines"]) or 1
        rows = "".join(
            f'<div style="background:rgba(255,193,7,{min(1, s / mx) * 0.85:.2f});white-space:pre-wrap;padding:0 4px">'
            f'<span style="color:#888;display:inline-block;width:3em">{i}</span>{html.escape(t)}'
            f'<span style="float:right;color:#555">{s:.3f}</span></div>' if s >= 0.002 else
            f'<div style="white-space:pre-wrap;padding:0 4px"><span style="color:#888;display:inline-block;width:3em">{i}</span>'
            f'{html.escape(t)}</div>' for i, (t, s) in enumerate(c["lines"]))
        parts.append(f'<p><b>Job {html.escape(c["job"])}</b> · step {html.escape(c["step"] or "—")} · trọng số đoạn '
                     f'{c["weight"]:.3f}</p><div style="font-family:Consolas,monospace;font-size:12px;border:1px solid #ddd">'
                     f'{rows}</div>')
    return "".join(parts)


def launch(bundle: str, weights: str, port: int = 7860, ngrok_token: str = None, share: bool = False) -> str:
    import gradio as gr
    from project3.crawl.github import GitHub, load_token
    pred = Predictor(Path(bundle), weights)
    pred.net(pred.default_fold)  # tải UniXcoder + weight trước, để lần bấm đầu không chờ lâu
    gh = GitHub(load_token())
    examples = load_examples(bundle)

    def run(url):
        m = URL.search(url or "")
        if not m:
            return "Link phải có dạng `https://github.com/<owner>/<repo>/actions/runs/<id>`", "", {}
        rid = int(m.group(2))
        try:
            rec = examples[rid][1] if rid in examples else fetch_run(url, gh)
            o = pred.predict(rec)
        except Exception as e:  # noqa: BLE001 — hiện lỗi cho người dùng thay vì sập giao diện
            return f"**Lỗi:** {type(e).__name__}: {e}", "", {}
        slim = {k: v for k, v in o.items() if k != "chunks"}
        return summary(o), log_view(o), slim

    with gr.Blocks(title="Phân loại nguyên nhân lỗi build CI") as demo:
        gr.Markdown("## Phân loại nguyên nhân lỗi build CI (GitHub Actions, Java/Kotlin)\n"
                    "Dán link một lần chạy CI **bị lỗi**. Mô hình đọc log, thông tin CI và thay đổi code rồi cho biết "
                    "lỗi nằm ở đâu, lẽ ra phải sửa lúc nào, loại lỗi, kèm các dòng log làm căn cứ.")
        url = gr.Textbox(label="Link run", placeholder="https://github.com/<owner>/<repo>/actions/runs/<id>")
        btn = gr.Button("Phân loại", variant="primary")
        if examples:
            gr.Examples([[v[1]["url"]] for v in examples.values()], inputs=url,
                        label="Run mẫu (log đã lưu sẵn): " + " · ".join(v[0] for v in examples.values()))
        out_md = gr.Markdown()
        out_log = gr.HTML()
        with gr.Accordion("Kết quả dạng JSON", open=False):
            out_json = gr.JSON()
        btn.click(run, url, [out_md, out_log, out_json])
        url.submit(run, url, [out_md, out_log, out_json])
    demo.queue().launch(server_name="0.0.0.0", server_port=port, prevent_thread_lock=True, share=share, quiet=True)
    if not ngrok_token:
        return f"http://localhost:{port}"
    from pyngrok import ngrok
    ngrok.set_auth_token(ngrok_token)
    return ngrok.connect(port, "http").public_url
