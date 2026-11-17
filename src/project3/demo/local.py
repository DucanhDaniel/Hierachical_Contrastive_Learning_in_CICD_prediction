"""Giao diện chạy trên LAPTOP (16/11/2026): mô hình phân loại vẫn chạy trên Colab (app.launch, mở ra ngoài bằng ngrok);
laptop gọi endpoint đó, hiện kết quả, rồi bấm "Tìm nguyên nhân trong code" để chạy Claude Code ngay trên laptop bằng
gói Claude đã đăng nhập (demo.agent) — không cần API key, không mở laptop ra ngoài.

    uv run --extra demo python -m project3.demo.local https://xxxx.ngrok-free.app
    -> mở http://localhost:7861
"""
import argparse
import html
import sys

import json

from .agent import run as run_agent
from .predict import fetch_run


def answer_md(o: dict, r: dict) -> str:
    if r.get("error") and not r.get("answer"):
        return f"**Agent chưa chạy được.** {r['error']}"
    a = r["answer"]
    # chữ của agent có thể chứa <version>, <dependency>... -> Markdown hiểu là thẻ HTML và giấu đi; trong `code` giữ nguyên
    esc = lambda t: "`".join(x if k % 2 else html.escape(x, quote=False) for k, x in enumerate(str(t).split("`")))
    blob = f"https://github.com/{o['repo']}/blob/{o['head_sha']}/"
    rows = "\n".join(
        f"{i}. [{s['path']}{':' + str(s['line']) if s.get('line') else ''}]"
        f"({blob}{s['path']}{'#L' + str(s['line']) if s.get('line') else ''}) — {esc(s['reason'])}"
        for i, s in enumerate(a.get("suspects", []), 1))
    need = "Cần sửa code trong repo." if a.get("needs_code_change") else \
        "Không cần sửa code: nên chạy lại job hoặc sửa hạ tầng / cấu hình CI."
    fix = f"\n\n**Cách sửa đề xuất.** {esc(a['suggested_fix'])}" if a.get("suggested_fix") else ""
    return (f"### Kết quả của agent\n\n**{need}** Độ tin cậy agent tự đánh giá: {a.get('confidence', 0):.2f}.\n\n"
            f"**Nguyên nhân.** {esc(a.get('root_cause', ''))}{fix}\n\n"
            f"**File nghi ngờ** (bấm để mở đúng dòng ở commit lỗi)\n\n{rows}"
            f"\n\n<sub>Tải code {r['clone_seconds']} giây, agent chạy {r['seconds']} giây, {r['turns']} bước, "
            f"{r['in_tok']:,} token đầu vào, {r['out_tok']:,} token đầu ra (trừ vào hạn mức gói Claude).</sub>"
            + (f"\n\n{r['error']}" if r.get("error") else ""))


def launch(colab_url: str, port: int = 7861) -> None:
    import gradio as gr
    from gradio_client import Client
    from project3.crawl.github import GitHub, load_token
    cli = Client(colab_url, verbose=False)
    gh = GitHub(load_token())
    try:
        examples = cli.predict(api_name="/examples")
    except Exception:  # noqa: BLE001 — bản Colab cũ chưa có endpoint này
        examples = []

    ex_urls = {u for _, u in examples}

    def classify(url):
        try:
            if (url or "").split("/job/")[0] in ex_urls:  # run mẫu: log đã lưu sẵn trên Colab
                md, log, agent_in, o = cli.predict(url, api_name="/predict")
            else:  # tải run ở laptop (token GitHub của máy) rồi gửi sang Colab
                rec = fetch_run(url, gh)
                md, log, agent_in, o = cli.predict(json.dumps(rec), api_name="/predict_record")
        except Exception as e:  # noqa: BLE001
            return f"**Không gọi được mô hình trên Colab.** {type(e).__name__}: {e}", "", "", {}, ""
        return md, log, agent_in, o, ""

    def find_cause(o, agent_in):
        if not o or "repo" not in o:
            yield "Hãy bấm **Phân loại** trước."
            return
        yield "Đang tải code của repo ở đúng commit rồi chạy agent (thường 1–3 phút)..."
        yield answer_md(o, run_agent(o, agent_in, gh))

    from .app import light_style
    style, in_blocks = light_style(gr)  # nền trắng như trang trên Colab
    with gr.Blocks(title="Phân loại và truy vết lỗi build CI", **(style if in_blocks else {})) as demo:
        gr.Markdown("## Phân loại và truy vết nguyên nhân lỗi build CI\nMô hình phân loại chạy trên Colab. Agent tìm "
                    "nguyên nhân trong code chạy trên máy này bằng Claude Code. Agent chỉ đọc code, không sửa file hay "
                    "chạy lệnh.")
        with gr.Row(equal_height=True):
            url = gr.Textbox(label="Link lần chạy", placeholder="https://github.com/<owner>/<repo>/actions/runs/<id>",
                             scale=5)
            btn = gr.Button("Phân loại", variant="primary", scale=1)
        if examples:
            pick = gr.Dropdown([tuple(x) for x in examples], value=None,
                               label="Hoặc chọn một lần chạy mẫu, log đã được lưu sẵn")
            pick.change(lambda u: u or "", pick, url)
        out_md = gr.Markdown()
        out_log = gr.HTML()
        with gr.Accordion("Đầu vào đưa cho agent", open=False):
            out_agent_in = gr.Textbox(lines=8, max_lines=30, interactive=False, show_label=False)
        agent_btn = gr.Button("Tìm nguyên nhân trong code", variant="secondary")
        out_agent = gr.Markdown()
        state = gr.State({})
        outs = [out_md, out_log, out_agent_in, state, out_agent]
        btn.click(classify, url, outs)
        url.submit(classify, url, outs)
        agent_btn.click(find_cause, [state, out_agent_in], out_agent)
    demo.queue(default_concurrency_limit=1).launch(server_name="127.0.0.1", server_port=port, inbrowser=True,
                                                   **({} if in_blocks else style))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("colab_url", help="link ngrok mà ô LAUNCH của notebook Colab in ra")
    ap.add_argument("--port", type=int, default=7861)
    a = ap.parse_args()
    launch(a.colab_url, a.port)
