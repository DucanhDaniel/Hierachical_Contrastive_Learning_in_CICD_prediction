"""Model architecture figure in paper style (04/11/2026): English, technique names, abstract blocks.
Run: uvx --with matplotlib python hinh_kien_truc.py -> hinh-tuan-7/kien-truc-mo-hinh.png"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle

OUT = Path(__file__).parent / "hinh-tuan-7"
plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["mathtext.fontset"] = "dejavusans"

BLUE, BLUE_E = "#EAF2FB", "#5B8FCC"
GREEN, GREEN_E = "#E4F3EA", "#4FA373"
PURPLE, PURPLE_E = "#EEEAF8", "#7F6FC4"
ORANGE, ORANGE_E = "#FDEDE3", "#E08A52"
GREY_F, GREY_E = "#F2F2F0", "#A3A3A0"
LOSS, INK = "#C0392B", "#2F2F2F"
HEAT = plt.get_cmap("YlOrRd")


def rbox(ax, x, y, w, h, fc, ec, text="", fs=10, tc=INK, bold=True, ls="-", r=0.1):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}", fc=fc, ec=ec, lw=1.3, ls=ls,
                                zorder=2))
    if text:
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=tc,
                fontweight="bold" if bold else "normal", zorder=3, linespacing=1.25)
    return x, y, w, h


def arr(ax, p, q, color="#4A4A4A", ls="-", cs="arc3", lw=1.3):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=12, color=color, lw=lw, ls=ls,
                                 connectionstyle=cs, shrinkA=1, shrinkB=1, zorder=4))


def R(b):
    return b[0] + b[2], b[1] + b[3] / 2


def L(b):
    return b[0], b[1] + b[3] / 2


def cells(ax, x, y, vals, s=0.24):
    out = []
    for i, v in enumerate(vals):
        ax.add_patch(Rectangle((x, y - i * s), s, s, fc=HEAT(0.08 + 0.85 * v), ec="#8C8C8C", lw=0.7, zorder=3))
        out.append((x + s / 2, y - i * s + s / 2))
    return out


def loss(ax, x, y, text):
    ax.text(x, y, text, ha="center", va="center", fontsize=9.5, color=LOSS, zorder=5,
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=LOSS, lw=1, ls="--"))


def main():
    W, H = 17.5, 6.6
    X0 = -2.4  # cột đầu vào có ví dụ thật (run 30617913741, linkedin/venice) nên rộng hơn
    fig, ax = plt.subplots(figsize=(W - X0, H))
    ax.set_xlim(X0, W); ax.set_ylim(0, H); ax.axis("off")

    def ibox(y, h, title, lines):
        b = rbox(ax, X0 + 0.15, y, 2.4 - X0 - 0.15, h, BLUE, BLUE_E)
        ax.text(X0 + 0.3, y + h - 0.22, title, fontsize=9.5, fontweight="bold", color="#1F4E79", va="center", zorder=3)
        for i, (t, hl) in enumerate(lines):
            yy = y + h - 0.55 - i * 0.27
            if hl:
                ax.add_patch(Rectangle((X0 + 0.25, yy - 0.12), 2.4 - X0 - 0.35, 0.24, fc="#FFD9B3", ec="none", zorder=2))
            ax.text(X0 + 0.3, yy, t, fontsize=7.4, family="DejaVu Sans Mono", color=INK, va="center", zorder=3)
        return b

    meta = ibox(4.85, 1.35, "CI metadata", [("workflow: AnalyseStatiqueEtTestsUnitaires", 0),
                                             ("job:      StaticAnalysis (17)", 0), ("step:     Run Static Analysis", 0)])
    log = ibox(2.3, 2.3, "Failed job logs", [("* What went wrong:", 0), ("Execution failed for task", 1),
                                             ("  ':da-vinci-client:spotbugsMain'.", 1),
                                             ("> 2 SpotBugs violations were found.", 0), ("* Try: ...", 0),
                                             ("BUILD FAILED in 6m 3s", 0)])
    diff = ibox(0.3, 1.75, "Commit diff", [("10 files (8 main, 2 test), +318 / -12", 0),
                                           ("M  OffsetRecord.java      +59  -6", 0), ("M  PubSubUtil.java        +43  -1", 0),
                                           ("A  TestOffsetRecord.java  +116", 0)])

    sel = rbox(ax, 2.9, 3.6, 1.75, 1.05, GREY_F, GREY_E, "Error-block\nselection", fs=9.5)
    feat = rbox(ax, 2.9, 0.65, 1.75, 1.05, GREY_F, GREY_E, "CI + diff\nstatistics", fs=9.5)
    arr(ax, R(log), L(sel))
    arr(ax, R(diff), L(feat))
    arr(ax, (2.4, 3.85), (3.1, 1.7), color="#9A9A9A", cs="arc3,rad=0.15")

    # chunks -> shared encoder
    for k in range(3):
        rbox(ax, 5.05 + k * 0.1, 3.75 - k * 0.1, 0.6, 0.85, "white", "#8C8C8C", r=0.04)
    ax.text(5.45, 2.95, "chunks", ha="center", fontsize=8.5, color="#6E6E6E", style="italic")
    arr(ax, R(sel), (5.03, 4.12))
    ax.add_patch(Polygon([(6.1, 3.2), (6.1, 5.4), (7.3, 4.95), (7.3, 3.65)], closed=True, fc=GREEN, ec=GREEN_E, lw=1.4,
                         zorder=2))
    ax.text(6.7, 4.3, "UniXcoder", ha="center", va="center", fontsize=10.5, fontweight="bold", color="#1E5631",
            rotation=90, zorder=3)
    arr(ax, (5.95, 4.15), (6.1, 4.15))
    arr(ax, R(meta), (6.1, 5.15), cs="arc3,rad=-0.15")
    ax.text(6.45, 5.95, "shared", ha="center", fontsize=8.5, color="#6E6E6E", style="italic")

    # hierarchical attention pooling
    lv = cells(ax, 7.75, 5.05, [0.05, 0.1, 0.05, 0.95, 0.12, 0.35, 0.05])
    for _, cy in lv:
        arr(ax, (7.3, 4.3), (7.73, cy), color="#B5B5B5", lw=0.6)
    cv = cells(ax, 8.85, 4.6, [0.15, 0.95, 0.1])
    for _, cy in lv:
        arr(ax, (7.99, cy), (8.83, cv[1][1]), color="#A0A0A0", lw=0.6)
    jv = cells(ax, 9.85, 4.35, [1.0, 0.05])
    for _, cy in cv:
        arr(ax, (9.09, cy), (9.83, jv[0][1]), color="#A0A0A0", lw=0.6)
    for x, t in ((7.87, "line"), (8.97, "chunk"), (9.97, "job")):
        ax.text(x, 3.05, t, ha="center", fontsize=8.8, color="#6E6E6E", style="italic")
    rbox(ax, 7.55, 2.7, 2.75, 3.0, "none", "#B9B9B9", ls=":", r=0.12)
    ax.text(8.92, 2.45, "Hierarchical attention pooling", ha="center", fontsize=9.5, fontweight="bold", color=INK)

    # vectors
    r_ = rbox(ax, 10.75, 3.75, 0.32, 0.9, GREEN, GREEN_E)
    c_ = rbox(ax, 10.75, 5.4, 0.32, 0.9, BLUE, BLUE_E)
    f_ = rbox(ax, 10.75, 0.7, 0.32, 0.9, GREY_F, GREY_E)
    for b, t in ((r_, "$\\mathbf{r}$"), (c_, "$\\mathbf{c}$"), (f_, "$\\mathbf{f}$")):
        ax.text(b[0] + b[2] / 2, b[1] - 0.22, t, ha="center", fontsize=12, color=INK)
    for _, cy in jv:
        arr(ax, (10.09, cy), L(r_), color="#A0A0A0", lw=0.6)
    ax.plot([6.95, 6.95, 10.4], [5.05, 5.85, 5.85], color="#7FA7D6", lw=1.3, zorder=1)
    arr(ax, (10.4, 5.85), L(c_), color="#7FA7D6")
    arr(ax, R(feat), L(f_))
    ax.text(7.7, 1.38, "Normalization", ha="center", fontsize=8.5, color="#6E6E6E", style="italic")

    # fusion
    fus = rbox(ax, 11.6, 2.3, 1.05, 3.1, PURPLE, PURPLE_E, "Concat\n↓\nMLP\n↓\n$\\mathbf{z}$", fs=10,
               tc="#3F3794")
    for b in (r_, c_, f_):
        y = min(max(R(b)[1], 2.5), 5.2)
        arr(ax, R(b), (11.6, y))

    # heads + hierarchical decoding
    heads = ["Tier-1 head\n(artifact)", "Tier-2 head\n(handling action)", "Tier-3 head\n(error type)"]
    hb = []
    for i, t in enumerate(heads):
        b = rbox(ax, 13.2, 4.45 - i * 1.0, 1.7, 0.75, ORANGE, ORANGE_E, t, fs=8.8, tc="#8A3A0C")
        arr(ax, (12.65, 3.85), L(b))
        hb.append(b)
    rbox(ax, 13.05, 2.3, 2.0, 3.1, "none", "#B9B9B9", ls=":", r=0.12)
    ax.text(14.05, 2.05, "Hierarchical decoding", ha="center", fontsize=9.5, fontweight="bold", color=INK)
    out = rbox(ax, 15.55, 3.25, 1.75, 1.3, ORANGE, ORANGE_E, "3-tier\nlabel path", fs=10, tc="#8A3A0C")
    for b in hb:
        arr(ax, R(b), L(out))

    ev = rbox(ax, 15.55, 5.35, 1.75, 0.85, "white", ORANGE_E, "Evidence lines", fs=9.5, tc="#8A3A0C", ls="--")
    cf = rbox(ax, 15.55, 1.45, 1.75, 0.95, "white", ORANGE_E, "Confidence score\n(MC Dropout)", fs=9, tc="#8A3A0C",
              ls="--")
    hy = lv[3][1]
    ax.plot([7.99, 8.25, 8.25, 15.3], [hy, hy, 6.5, 6.5], color=ORANGE_E, lw=1.2, ls="--", zorder=1)
    arr(ax, (15.3, 6.5), (15.53, 5.95), color=ORANGE_E)
    arr(ax, (14.95, 2.35), L(cf), color=ORANGE_E, ls="--")

    # losses
    loss(ax, 8.95, 5.35, "$\\mathcal{L}_{line}$")
    arr(ax, (8.6, 5.3), (8.02, 5.2), color=LOSS, ls="--", lw=1)
    loss(ax, 12.12, 1.7, "$\\mathcal{L}_{HCL}$")
    arr(ax, (12.12, 1.92), (12.12, 2.28), color=LOSS, ls="--", lw=1)
    loss(ax, 14.05, 5.75, "$\\mathcal{L}_{CE}$")
    arr(ax, (14.05, 5.55), (14.05, 5.22), color=LOSS, ls="--", lw=1)

    fig.savefig(OUT / "kien-truc-mo-hinh.png", dpi=220, bbox_inches="tight", facecolor="white")
    print("->", OUT / "kien-truc-mo-hinh.png")


if __name__ == "__main__":
    main()
