"""Hình giải thích hai khối đầu vào của mô hình (04/11/2026), kiểu hình paper, tiếng Anh:
(a) Error-block selection — run 32561500047 (apache/camel-quarkus, compile error): 25 đoạn, điểm thật của
    model.inputs.chunk_score, 8 đoạn được model.inputs.select_chunks chọn, cửa sổ focus_window(1600, "split").
(b) CI + diff statistics — run 30617913741 (linkedin/venice): giá trị thật trong features.parquet.
Chạy: uvx --with matplotlib python hinh_dau_vao.py -> hinh-tuan-7/dau-vao-mo-hinh.png"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

OUT = Path(__file__).parent / "hinh-tuan-7"
plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["mathtext.fontset"] = "dejavusans"
INK, GREY = "#2F2F2F", "#6E6E6E"
BLUE_E, ORANGE_E, GREEN_E = "#5B8FCC", "#E08A52", "#4FA373"
HEAT = plt.get_cmap("YlOrRd")
MONO = "DejaVu Sans Mono"

SCORES = [0.0, 0.0, 0.0, 0.0, 12.0, 0.0, 0.3, 0.0, 0.0, 0.0, 0.0, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0, 0.7, 0.0, 0.0, 0.0,
          0.0, 12.0, 1.3, 8.0]
PICKED = {4, 6, 11, 17, 21, 22, 23, 24}
HEADS = {0: "gplus:execute", 1: "compiler:compile", 4: "gplus:execute (sanity-checks)", 5: "formatter:format",
         13: "jar:test-jar", 14: "Reactor Summary …", 22: "BUILD FAILURE", 23: "stack trace …"}


def arr(ax, p, q, color="#4A4A4A", cs="arc3", lw=1.3, ls="-"):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=12, color=color, lw=lw, ls=ls,
                                 connectionstyle=cs, shrinkA=1, shrinkB=1, zorder=4))


def panel_a(ax):
    ax.text(0.0, 6.55, "(a) Error-block selection", fontsize=12.5, fontweight="bold", color=INK)
    # job log -> chunks
    x0, top, h = 0.3, 5.9, 0.205
    ax.text(x0 + 0.55, top + 0.18, "Failed job log\n(last 200 KB)", ha="center", va="bottom", fontsize=9, color=INK,
            fontweight="bold")
    for i, s in enumerate(SCORES):
        y = top - (i + 1) * h
        ax.add_patch(Rectangle((x0, y), 1.1, h, fc=HEAT(0.06 + 0.8 * min(1, s / 12)), ec="#9A9A9A", lw=0.6, zorder=2))
        if i in PICKED:
            ax.add_patch(Rectangle((x0 - 0.04, y + 0.01), 1.18, h - 0.02, fc="none", ec=GREEN_E, lw=1.8, zorder=3))
        ax.text(x0 + 1.2, y + h / 2, f"{s:g}", fontsize=6.8, color=GREY, va="center")
        if i in HEADS:
            ax.text(x0 - 0.1, y + h / 2, HEADS[i], fontsize=6.8, color=GREY, va="center", ha="right", family=MONO)
    ax.text(x0 + 0.55, top - len(SCORES) * h - 0.25, "25 chunks", ha="center", fontsize=8.5, color=GREY, style="italic")
    ax.text(x0 + 1.32, top + 0.05, "score", fontsize=7.5, color=GREY, style="italic")

    # step 1, 2, 3 text
    tx = 2.45
    steps = [("① Split", "at GitHub steps, Maven goals,\nGradle tasks (≤ 40 lines)"),
             ("② Score each chunk", "5·min(#failure lines, 2)\n+ 2·min(#error lines, 6) / 6\n+ 1·[last chunk of job]"),
             ("③ Keep top-8 chunks", "best chunk of every job first,\nthen highest scores (green boxes)"),
             ("④ 1,600-char window", "half around the first failure line\n+ half around the last one\n(one window if they are close)")]
    for k, (t, d) in enumerate(steps):
        y = 5.75 - k * 1.38
        ax.text(tx, y, t, fontsize=10, fontweight="bold", color=INK, va="top")
        ax.text(tx + 0.2, y - 0.32, d, fontsize=8.6, color=GREY, va="top", linespacing=1.35,
                family=MONO if k == 1 else None)

    # zoom on chunk 22
    zx, zy, zw, zh = 5.35, 0.55, 5.1, 5.45
    ax.add_patch(FancyBboxPatch((zx, zy), zw, zh, boxstyle="round,pad=0,rounding_size=0.1", fc="white", ec="#9A9A9A",
                                lw=1.1, zorder=1))
    ax.text(zx + 0.12, zy + zh - 0.22, "Chunk 23 / 25  (score 12)", fontsize=9, fontweight="bold", color=INK,
            va="center")
    lines = [("[INFO] … Integration Tests :: CLI Connector  SKIPPED", 0),
             ("[INFO] … ZooKeeper Master  SUCCESS [ 1.594 s]", 0),
             ("[INFO] BUILD FAILURE", 2),
             ("[INFO] Total time:  09:11 min (Wall Clock)", 0),
             ("[ERROR] Failed to execute goal …maven-compiler-plugin", 2),
             ("        :compile on project …aws2-grouped", 1),
             ("[ERROR] …/Aws2StsResource.java:[29,43] package", 1),
             ("        org.apache.camel.component.aws2.sts does not exist", 1),
             ("[ERROR] …/Aws2StsResource.java:[55,33] cannot find symbol", 1),
             ("[ERROR]   symbol:   class STS2Operations", 1),
             ("[ERROR] -> [Help 1]", 1),
             ("org.apache.maven.lifecycle.LifecycleExecutionException:", 1),
             ("    at org.apache.maven.lifecycle.internal.MojoExecutor…", 0),
             ("    at org.apache.maven.lifecycle.internal.MojoExecutor…", 0),
             ("    at org.apache.maven.lifecycle.internal.MojoExecutor…", 0)]
    y0 = zy + zh - 0.62
    for i, (t, kind) in enumerate(lines):
        y = y0 - i * 0.31
        if kind == 2:
            ax.add_patch(Rectangle((zx + 0.08, y - 0.13), zw - 0.16, 0.26, fc="#FFD9B3", ec="none", zorder=1))
        ax.text(zx + 0.15, y, t, fontsize=7.2, family=MONO, color=INK if kind else "#9A9A9A", va="center", zorder=2)
    # bracket for the window
    wy0, wy1 = y0 - 2 * 0.31 + 0.15, y0 - 11 * 0.31 - 0.15
    bx = zx + zw - 0.12
    ax.plot([bx - 0.12, bx, bx, bx - 0.12], [wy0, wy0, wy1, wy1], color=GREEN_E, lw=1.8, zorder=3)
    ax.text(bx + 0.12, (wy0 + wy1) / 2, "1,600-char\nwindow\n→ encoder", fontsize=8.3, color="#1E5631",
            fontweight="bold", va="center")
    ax.text(zx + 0.15, zy + 0.2, "orange = failure lines (BUILD FAILURE, Failed to execute goal)", fontsize=7.6,
            color=GREY, va="center")
    ax.text(x0 + 1.55, top - 23 * h + h / 2, "◀ zoomed", fontsize=7.5, color="#1E5631", fontweight="bold",
            va="center")


def onehot(ax, x, y, labels, on, title, w=0.62):
    ax.text(x, y + 0.42, title, fontsize=9, color=INK, fontweight="bold", va="center")
    for i, l in enumerate(labels):
        hit = l == on
        ax.add_patch(Rectangle((x + i * w, y - 0.15), w - 0.04, 0.3, fc="#F7B98B" if hit else "#F4F4F2",
                               ec=ORANGE_E if hit else "#BDBDBD", lw=1, zorder=2))
        ax.text(x + i * w + (w - 0.04) / 2, y, l, fontsize=6.9, ha="center", va="center", zorder=3,
                color=INK if hit else GREY, fontweight="bold" if hit else "normal")


def values(ax, x, y, items, title, w=1.02):
    ax.text(x, y + 0.42, title, fontsize=9, color=INK, fontweight="bold", va="center")
    for i, (l, v) in enumerate(items):
        hit = v not in ("0", "no")
        ax.add_patch(Rectangle((x + i * w, y - 0.15), w - 0.05, 0.3, fc="#F7B98B" if hit else "#F4F4F2",
                               ec=ORANGE_E if hit else "#BDBDBD", lw=1, zorder=2))
        ax.text(x + i * w + (w - 0.05) / 2, y, v, fontsize=7.4, ha="center", va="center", zorder=3, color=INK)
        ax.text(x + i * w + (w - 0.05) / 2, y - 0.3, l, fontsize=6.6, ha="center", va="top", color=GREY,
                linespacing=1.15)


def panel_b(ax):
    X = 11.3
    ax.text(X, 6.55, "(b) CI + diff statistics", fontsize=12.5, fontweight="bold", color=INK)
    ax.text(X, 6.12, "example: linkedin/venice, SpotBugs failure", fontsize=8.6, color=GREY, style="italic")
    stages = ["setup", "prepare", "compile", "check", "test", "itest", "package", "none"]
    # CI statistics
    ax.add_patch(FancyBboxPatch((X - 0.1, 2.45), 5.75, 3.35, boxstyle="round,pad=0,rounding_size=0.1", fc="none",
                                ec=BLUE_E, lw=1.2))
    ax.text(X + 5.55, 5.6, "CI statistics · 22", fontsize=9, color=BLUE_E, fontweight="bold", ha="right", va="center")
    onehot(ax, X + 0.1, 4.8, stages, "check", "Failed stage · from log (task spotbugsMain)")
    onehot(ax, X + 0.1, 3.85, stages, "check", "Failed stage · from step name (Run Static Analysis)")
    values(ax, X + 0.1, 3.2, [("Maven", "0"), ("Gradle", "1"), ("#failed\ntools", "1"), ("#failed\njobs", "2"),
                              ("PR-chore\nstep", "no"), ("#failure\nlines", "4")], "", w=0.92)
    # diff statistics
    ax.add_patch(FancyBboxPatch((X - 0.1, -0.05), 5.75, 2.3, boxstyle="round,pad=0,rounding_size=0.1", fc="none",
                                ec=BLUE_E, lw=1.2))
    ax.text(X + 5.55, 2.05, "Diff statistics · 11", fontsize=9, color=BLUE_E, fontweight="bold", ha="right", va="center")
    values(ax, X + 0.1, 1.5, [("main", "0.8"), ("test", "0.2"), ("build", "0"), ("CI", "0"), ("doc", "0"),
                               ("other", "0")], "Share of changed files by type", w=0.92)
    values(ax, X + 0.1, 0.55, [("#files", "10"), ("+lines", "318"), ("−lines", "12"), ("has diff", "1"),
                               ("is PR", "1")], "", w=1.08)
    ax.text(X + 2.8, -0.3, "counts use log(1+x);  all 33 values are z-normalised on the training set  →  f",
            fontsize=8.2, color=GREY, ha="center", va="center", style="italic")


def main():
    fig, ax = plt.subplots(figsize=(17.5, 7.2))
    ax.set_xlim(-0.6, 17.2); ax.set_ylim(-0.4, 6.9); ax.axis("off")
    panel_a(ax)
    panel_b(ax)
    fig.savefig(OUT / "dau-vao-mo-hinh.png", dpi=220, bbox_inches="tight", facecolor="white")
    print("->", OUT / "dau-vao-mo-hinh.png")


if __name__ == "__main__":
    main()
