"""Hình cấu trúc cho báo cáo tuần 7: v10 và các baseline. Chạy: uvx --with matplotlib python hinh_tuan_7.py"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).parent / "hinh-tuan-7"
OUT.mkdir(exist_ok=True)
plt.rcParams["font.family"] = "DejaVu Sans"

C_IN, C_PROC, C_ENC, C_HEAD, C_OUT = "#DDEBF7", "#FFF2CC", "#E2EFDA", "#FCE4D6", "#EDEDED"


def box(ax, x, y, w, h, text, fc, fs=9, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                fc=fc, ec="#595959", lw=1))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, wrap=True,
            fontweight="bold" if bold else "normal")
    return (x, y, w, h)


def arrow(ax, a, b, side_a="r", side_b="l"):
    def pt(bx, s):
        x, y, w, h = bx
        return {"r": (x + w, y + h / 2), "l": (x, y + h / 2), "t": (x + w / 2, y + h), "b": (x + w / 2, y)}[s]
    ax.add_patch(FancyArrowPatch(pt(a, side_a), pt(b, side_b), arrowstyle="-|>", mutation_scale=11,
                                 color="#404040", lw=1.1, shrinkA=1, shrinkB=1))


def canvas(w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, w); ax.set_ylim(0, h); ax.axis("off")
    return fig, ax


def v10():
    fig, ax = canvas(16, 6.6)
    # đầu vào
    log = box(ax, 0.2, 4.6, 2.3, 1.1, "Log các job fail", C_IN, bold=True)
    ctx = box(ax, 0.2, 2.9, 2.3, 1.1, "Ngữ cảnh CI\nworkflow / job / step", C_IN, bold=True)
    ft = box(ax, 0.2, 1.0, 2.3, 1.3, "Đặc trưng có cấu trúc\n22 giai đoạn / công cụ fail\n+ 11 tóm tắt diff", C_IN,
             fs=8, bold=True)
    sel = box(ax, 3.0, 4.5, 2.6, 1.3, "Chọn khối log lỗi\n≤ 8 đoạn / run, cửa sổ\n1.600 ký tự quanh dòng fail",
              C_PROC)
    enc = box(ax, 6.1, 2.9, 2.7, 2.9, "UniXcoder\n(dùng chung)\n\n512 token / đoạn\nđóng băng embedding\n+ 6 lớp dưới",
              C_ENC, bold=False)
    pool = box(ax, 9.3, 4.5, 2.4, 1.3, "Trung bình token\n→ attention: đoạn → job → run\n(768 chiều)", C_PROC, fs=8.5)
    c64 = box(ax, 9.3, 2.9, 2.4, 1.1, "Linear → 64", C_PROC)
    f64 = box(ax, 9.3, 1.1, 2.4, 1.1, "Chuẩn hoá → Linear → 64", C_PROC)
    z = box(ax, 12.1, 2.7, 1.5, 1.7, "Ghép\n→ MLP\n→ z (256)", C_ENC, bold=True)
    h1 = box(ax, 14.0, 4.6, 1.85, 1.0, "Tầng 1 (2)\nDự án / Môi trường", C_HEAD, fs=8.5)
    h2 = box(ax, 14.0, 3.05, 1.85, 1.0, "Tầng 2 (5)\nthời điểm cần sửa", C_HEAD, fs=8.5)
    h3 = box(ax, 14.0, 1.5, 1.85, 1.0, "Lá (13)\nloại lỗi", C_HEAD, fs=8.5)
    arrow(ax, log, sel); arrow(ax, sel, enc, "r", "l")
    arrow(ax, ctx, enc)
    ax.add_patch(FancyArrowPatch((8.8, 5.15), (9.3, 5.15), arrowstyle="-|>", mutation_scale=11, color="#404040", lw=1.1))
    ax.add_patch(FancyArrowPatch((8.8, 3.45), (9.3, 3.45), arrowstyle="-|>", mutation_scale=11, color="#404040", lw=1.1))
    arrow(ax, ft, f64)
    for b in (pool, c64, f64):
        arrow(ax, b, z)
    for h in (h1, h2, h3):
        arrow(ax, z, h)
    ax.text(14.92, 0.95, "Giải mã theo cây: tầng 2 = argmax(log p₁ + log p₂),\nlá = lá con có p₃ lớn nhất",
            ha="center", va="top", fontsize=8, style="italic")
    ax.text(0.2, 0.25, "Huấn luyện: cross-entropy ở 3 tầng (trọng số lớp = căn bậc hai nghịch tần suất) + 0,5 × SupCon mềm "
            "(cùng lá: dương 1, lá anh em cùng cha: 0,4);\n50% run train bị che dòng bằng chứng. "
            "Gộp seed: trung bình log xác suất 3 tầng của các mô hình rồi mới giải mã.", fontsize=8.5, va="bottom")
    fig.savefig(OUT / "v10.png", dpi=200, bbox_inches="tight")


def baselines():
    rows = [
        ("B0 ngữ cảnh CI", "Tên workflow / job / step", "TF-IDF (1–2 gram)", "Hồi quy logistic\n(cân bằng lớp)"),
        ("B1 TF-IDF", "30.000 ký tự cuối log", "TF-IDF (1–2 gram)", "Hồi quy logistic\n(cân bằng lớp)"),
        ("TF-IDF + CI (+ diff)", "30.000 ký tự cuối log\n+ 22 đặc trưng CI (+ 11 diff)", "TF-IDF ⊕ đặc trưng\nđã chuẩn hoá",
         "Hồi quy logistic\n(cân bằng lớp)"),
        ("B2 BERT\n(ICSE 2024 poster)", "512 token cuối log", "BERT-base\nfine-tune 2 epoch", "Softmax 13 lá"),
        ("B3 LLM\n(LogSage, ASE 2025)", "Log + ngữ cảnh CI", "Lọc dòng log khoá\n(từ khoá, 50 dòng cuối,\nkhối [−4, +6]; ≤ 40.000 ký tự)",
         "Gemini 3.5 Flash-Lite\nzero-shot, prompt có\nđịnh nghĩa 15 lá"),
    ]
    h = 1.25
    fig, ax = canvas(15, h * len(rows) + 0.3)
    for i, (name, inp, mid, clf) in enumerate(rows):
        y = (len(rows) - 1 - i) * h + 0.2
        ax.text(0.1, y + 0.5, name, va="center", fontsize=9.5, fontweight="bold")
        a = box(ax, 2.6, y, 3.4, 1.0, inp, C_IN, fs=8.5)
        b = box(ax, 6.5, y, 3.3, 1.0, mid, C_PROC, fs=8.5)
        c = box(ax, 10.3, y, 2.7, 1.0, clf, C_ENC, fs=8.5)
        d = box(ax, 13.5, y + 0.2, 1.3, 0.6, "1 lá", C_HEAD, fs=8.5)
        arrow(ax, a, b); arrow(ax, b, c); arrow(ax, c, d)
    fig.savefig(OUT / "baselines.png", dpi=200, bbox_inches="tight")


TREE = [  # (tầng 1, [(tầng 2, [(lá, số run)])]); số run theo nhãn 2026-10-29b-doc
    ("Dự án", [
        ("Khi viết code", [("compile", "12.083"), ("quality", "8.427"), ("doc", "320"), ("buildconfig", "546")]),
        ("Build local trước khi push", [("testfailure", "19.553"), ("dependency", "3.892"), ("license", "439"),
                                        ("compatibility", "44")]),
        ("CI trước khi merge", [("itestfailure", "9.167"), ("flaky", "16")]),
    ]),
    ("Môi trường CI", [
        ("Sửa cấu hình CI", [("git", "245"), ("androidsdk", "509"), ("infra", "685")]),
        ("Chạy lại", [("network", "2.598"), ("crash", "3.028")]),
    ]),
]
NOT_LEARNED = {"compatibility", "flaky"}


def cay_nhan():
    n = sum(len(ls) for _, g in TREE for _, ls in g)
    step, top = 0.62, 0.55
    H = top + n * step + 0.35
    fig, ax = canvas(13, H)
    X0, X1, X2, X3 = 0.2, 2.0, 5.0, 9.0          # mép trái các cột
    W0, W1, W2, W3 = 1.2, 2.3, 3.2, 3.5
    bh = 0.44
    for x, w, t, s in ((X0, W0, "Gốc", ""), (X1, W1, "Tầng 1", "Artifact chứa lỗi (sửa ở đâu?)"),
                       (X2, W2, "Tầng 2", "Thời điểm cần sửa (sửa lúc nào?)"), (X3, W3, "Tầng 3 (lá)", "Loại lỗi · số run")):
        ax.text(x + w / 2, H - 0.12, t, ha="center", va="top", fontsize=11, color="#404040")
        ax.text(x + w / 2, H - 0.45, s, ha="center", va="top", fontsize=8.5, color="#7F7F7F", style="italic")

    def node(x, w, yc, text, fc, ec, tc, dashed=False):
        ax.add_patch(FancyBboxPatch((x, yc - bh / 2), w, bh, boxstyle="round,pad=0.01,rounding_size=0.1", fc=fc, ec=ec,
                                    lw=1.1, ls="--" if dashed else "-"))
        ax.text(x + w / 2, yc, text, ha="center", va="center", fontsize=9.5, color=tc, fontweight="bold")

    def elbow(xa, ya, xb, ybs):  # cha (mép phải xa, ya) -> các con (mép trái xb, ybs)
        xm = (xa + xb) / 2
        ax.plot([xa, xm], [ya, ya], color="#8C8C8C", lw=1)
        ax.plot([xm, xm], [min(ybs + [ya]), max(ybs + [ya])], color="#8C8C8C", lw=1)
        for y in ybs:
            ax.plot([xm, xb], [y, y], color="#8C8C8C", lw=1)

    y = H - top - 0.55
    l1_ys = []
    for t1, groups in TREE:
        l2_ys = []
        for t2, leaves in groups:
            ys = []
            for leaf, cnt in leaves:
                dashed = leaf in NOT_LEARNED
                node(X3, W3, y, f"{leaf}  ·  {cnt}" + ("  (chưa học)" if dashed else ""), "#FBE5D6",
                     "#F4B183", "#A6A6A6" if dashed else "#843C0C", dashed)
                ys.append(y); y -= step
            yc = (ys[0] + ys[-1]) / 2
            node(X2, W2, yc, t2, "#E2F0E8", "#8FCBA6", "#1E5631")
            elbow(X2 + W2, yc, X3, ys)
            l2_ys.append(yc)
        yc = (l2_ys[0] + l2_ys[-1]) / 2
        node(X1, W1, yc, t1, "#E8E6F8", "#ABA4E0", "#3F3794")
        elbow(X1 + W1, yc, X2, l2_ys)
        l1_ys.append(yc)
    yr = (l1_ys[0] + l1_ys[-1]) / 2
    node(X0, W0, yr, "failed", "#EDEDE9", "#A6A6A6", "#404040")
    elbow(X0 + W0, yr, X1, l1_ys)
    fig.savefig(OUT / "cay-nhan.png", dpi=200, bbox_inches="tight", facecolor="white")


if __name__ == "__main__":
    v10()
    baselines()
    cay_nhan()
    print("->", *sorted(p.name for p in OUT.glob("*.png")))
