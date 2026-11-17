"""Đo khả thi của gợi ý nguyên nhân ở mức code (file trong diff) trên dữ liệu hiện có (05/11/2026). Chỉ CPU, không mô hình.

Tập đo: run fail có nhãn quy tắc thuộc tầng "Dự án" (lỗi do code/cấu hình của repo), sự kiện pull_request, có diff PR.
  ứng viên  = file trong diff PR tại commit fail (merge-base(origin/HEAD, sha)..sha, data/diffs/*.pr.diff.gz)
  đáp án    = file mà lần sửa đụng tới: commit pass ĐẦU TIÊN sau commit fail trên cùng nhánh PR (commits_all.sequence);
              file "bị sửa" = file có patch khác nhau giữa diff PR tại commit fail và tại commit pass
  baseline  = ngẫu nhiên; khớp tên (file có tên, bỏ phần mở rộng, xuất hiện trong các đoạn log của run)

    python scripts/analysis/rca_feasibility.py   # -> data/results/rca_feasibility/{runs.parquet, summary.csv}
"""
import gzip
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("data/results/rca_feasibility")
DIFF_HDR = re.compile(r"^diff --git a/(.*?) b/(.*)$")


def parse_diff(path: str) -> dict:
    """{đường dẫn file: nội dung patch (bỏ dòng index, vì mã blob đổi khi nội dung đổi -> so bằng chính các dòng +/-)}."""
    files, cur, buf = {}, None, []
    try:
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = DIFF_HDR.match(line.rstrip("\n"))
                if m:
                    if cur is not None:
                        files[cur] = "".join(buf)
                    cur, buf = m.group(2), []
                elif cur is not None and not line.startswith("index "):
                    buf.append(line)
        if cur is not None:
            files[cur] = "".join(buf)
    except (OSError, EOFError):
        return None
    return files


def stem(path: str) -> str:
    return Path(path).name.split(".")[0]


def main() -> None:
    tree = json.load(open("data/kaggle_log_ds/label_tree.json", encoding="utf-8"))
    project = {x for x in tree["l3"] if tree["group"][tree["parent"][x]] == "du_an"}
    lab = pd.read_parquet("data/kaggle_log_ds/runs.parquet", columns=["run_id", "leaf"])
    runs = pd.read_parquet("data/run_dataset/runs.parquet",
                           columns=["run_id", "repository", "event", "head_sha", "diff_path", "diff_ok"])
    runs = runs.merge(lab, on="run_id")
    runs = runs[runs.leaf.isin(project) & (runs.event == "pull_request") & runs.diff_ok.fillna(False)]
    commits = pd.read_parquet("data/processed/commits_all.parquet",
                              columns=["repository", "event", "sequence", "head_sha", "first_run_at", "outcome"])
    commits = commits[commits.event == "pull_request"].sort_values("first_run_at")
    diffs = pd.read_csv("data/processed/diffs_all.csv", usecols=["repository", "head_sha", "kind", "path", "ok"],
                        low_memory=False)
    diffs = diffs[(diffs.kind == "pr") & diffs.ok].set_index(["repository", "head_sha"]).path
    diffs = diffs[~diffs.index.duplicated()]

    # commit pass đầu tiên sau mỗi commit fail trên cùng nhánh PR
    nxt = {}
    for _, g in commits.groupby("sequence", sort=False):
        shas, outs = g.head_sha.tolist(), g.outcome.tolist()
        for i, (s, o) in enumerate(zip(shas, outs)):
            if o == "fail":
                j = next((j for j in range(i + 1, len(shas)) if outs[j] == "pass"), None)
                if j is not None:
                    nxt[(g.repository.iloc[0], s)] = shas[j]
    runs["fix_sha"] = [nxt.get((r, s)) for r, s in zip(runs.repository, runs.head_sha)]
    print(f"run tầng Dự án, PR, có diff: {len(runs)} ({runs.repository.nunique()} repo); có commit pass sau: "
          f"{runs.fix_sha.notna().sum()}")

    # chữ trong log mà mô hình đọc (các đoạn log của run), chỉ cho run có commit sửa
    keep = runs[runs.fix_sha.notna()]
    chunks = pd.read_parquet("data/run_dataset/chunks.parquet", columns=["run_id", "text"],
                             filters=[("run_id", "in", keep.run_id.tolist())])
    logtext = chunks.groupby("run_id").text.agg("\n".join)

    rows, cache = [], {}

    def files_of(repo, sha):
        if (repo, sha) not in cache:
            p = diffs.get((repo, sha))
            cache[(repo, sha)] = parse_diff(p) if isinstance(p, str) else None
        return cache[(repo, sha)]

    for r in runs.itertuples():
        cand = files_of(r.repository, r.head_sha)
        row = dict(run_id=r.run_id, repository=r.repository, leaf=r.leaf, n_cand=len(cand) if cand else 0,
                   has_fix=r.fix_sha is not None)
        if cand and r.fix_sha is not None:
            after = files_of(r.repository, r.fix_sha)
            if after is not None:
                touched = {f for f in set(cand) | set(after) if cand.get(f) != after.get(f)}
                gt = touched & set(cand)
                text = logtext.get(r.run_id, "")
                ment = {f: len(re.findall(r"\b" + re.escape(stem(f)) + r"\b", text)) if stem(f) else 0 for f in cand}
                hit = [f for f, c in ment.items() if c > 0]
                # khớp tên: xếp file theo số lần nhắc giảm dần; hoà thì ngẫu nhiên -> xác suất đúng kỳ vọng
                order = sorted(set(ment.values()), reverse=True)
                top1 = top3 = 0.0
                seen = 0
                for v in order:
                    grp = [f for f in cand if ment[f] == v]
                    g_gt = sum(f in gt for f in grp)
                    if seen == 0:
                        top1 = g_gt / len(grp)
                    take = min(len(grp), max(0, 3 - seen))
                    if take and g_gt:  # xác suất có ít nhất 1 đáp án trong `take` file chọn ngẫu nhiên từ nhóm
                        miss = 1.0
                        for i in range(take):
                            miss *= (len(grp) - g_gt - i) / (len(grp) - i) if len(grp) - g_gt - i > 0 else 0.0
                        top3 = 1 - (1 - top3) * miss
                    seen += len(grp)
                    if seen >= 3:
                        break
                row.update(n_touched=len(touched), n_gt=len(gt), n_outside=len(touched - set(cand)),
                           n_mentioned=len(hit), gt_mentioned=len(gt & set(hit)),
                           rand_top1=len(gt) / len(cand), name_top1=top1, name_top3=top3)
        rows.append(row)
    df = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT / "runs.parquet", index=False)

    ev = df[df.n_gt.fillna(0) > 0]
    print(f"có diff tại cả commit fail và commit pass: {df.n_touched.notna().sum()}; "
          f"lần sửa đụng ít nhất 1 file ứng viên: {len(ev)}")
    print("\nSố file ứng viên (diff PR tại commit fail), mọi run tầng Dự án:")
    print(pd.cut(df.n_cand, [-1, 0, 1, 2, 5, 10, 50, 1e9], labels=["0", "1", "2", "3-5", "6-10", "11-50", ">50"])
          .value_counts(sort=False).to_string())

    def agg(g):
        return pd.Series(dict(run=len(g), repo=g.repository.nunique(), cand_median=g.n_cand.median(),
                              gt_median=g.n_gt.median(), one_cand=(g.n_cand == 1).mean(),
                              rand_top1=g.rand_top1.mean(), name_top1=g.name_top1.mean(), name_top3=g.name_top3.mean(),
                              gt_named=(g.gt_mentioned > 0).mean(), none_named=(g.n_mentioned == 0).mean()))

    s = pd.concat([ev.groupby("leaf").apply(agg), agg(ev).to_frame("TẤT CẢ").T]).sort_values("run", ascending=False)
    s.to_csv(OUT / "summary.csv", encoding="utf-8")
    pd.set_option("display.width", 220)
    print("\nTrên run có đáp án (lần sửa đụng file ứng viên):")
    print(s.round(3).to_string())
    print("->", OUT)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
