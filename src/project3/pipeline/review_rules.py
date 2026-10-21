"""Review quy tắc open coding trước khi tích hợp: đo độ phủ, xung đột và tốc độ của từng regex trên log thật.

    python -m project3.pipeline.review_rules                  # các cụm trong clusters.json đã gán
    python -m project3.pipeline.review_rules --labeled 6000    # số run đã có nhãn lấy mẫu để dò xung đột

Mỗi regex được chặn độ dài `\\S+` -> `\\S{1,200}` (tránh backtracking thảm hoạ như rule 42 ngày 14/10).
Một lượt đọc log: mỗi log chuẩn hoá một lần rồi thử mọi regex; in tiến độ mỗi 1000 run.
Đầu ra: data/human_labels/rule_review.csv (một dòng một quy tắc) + tóm tắt trên màn hình.
"""
import argparse
import csv
import json
import random
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from project3.crawl.gold_labels import diagnostic_text
from project3.pipeline.label_ui import ROOTS, current_labels, run_logs

H = Path("data/human_labels")
SLOW_MS = 200  # một lần search lâu hơn mức này là dấu hiệu regex nguy hiểm


def bounded(rx: str) -> str:
    return rx.replace(r"\S+", r"\S{1,200}")


def main(n_labeled: int, seed: int, proposed: str | None = None) -> None:
    cl = {x["run_id"]: x for x in json.loads((H / "clusters.json").read_text(encoding="utf-8"))}
    decided = current_labels(H, "opencoding.jsonl")
    if proposed:  # đánh giá bộ đề xuất chồng lên nhãn người (không ghi vào file nhãn người)
        decided |= current_labels(H, proposed)
        print(f"Chồng đề xuất từ {proposed}", flush=True)
    rules = [(k, r["label"], re.compile(bounded(r["regex"]), re.M)) for k, r in decided.items()
             if k in cl and r.get("regex") and r["label"] != "unclear"]
    print(f"{len(rules)} quy tắc có regex (bỏ unclear) trong {sum(k in cl for k in decided)} cụm đã gán", flush=True)
    own = {rid: k for k, c in cl.items() for rid in c["all_runs"]}  # run -> cụm của nó

    runs = []  # (run_id, nhãn quy tắc hiện tại, [đường dẫn log])
    for root in ROOTS:
        logs = run_logs(root)
        for r in csv.DictReader(open(root / "gold_labels.csv", encoding="utf-8-sig")):
            rid = int(r["run_id"])
            if r["non_build"] != "True" and rid in logs and r["gold"] != "(không có log)":
                runs.append((rid, r["gold"], [j["log"] for j in logs[rid]]))
    rng = random.Random(seed)
    unknown = [x for x in runs if x[1] == "?"]
    labeled = [x for x in runs if x[1] != "?"]
    labeled = rng.sample(labeled, min(n_labeled, len(labeled)))
    human = {k: v["label"] for k, v in current_labels(H).items()}
    human |= {k: v["label"] for k, v in current_labels(H, "adjudication.jsonl").items()}
    sample_ids = set(human)
    todo = unknown + labeled
    print(f"Quét {len(unknown)} run `?` (toàn bộ) + {len(labeled)} run đã có nhãn (mẫu)", flush=True)

    stats = {k: {"in_cluster": 0, "other_unknown": 0, "conflict": Counter(), "agree": 0, "human_conflict": [],
                 "slow": 0, "ms": 0.0, "other_clusters": Counter()} for k, _, _ in rules}
    t0 = time.time()
    first_hit = Counter()  # run `?` -> nhãn của quy tắc đầu tiên khớp (độ phủ của cả bộ)
    order = {lab: i for i, lab in enumerate(["non_build", "buildconfig", "compile", "lint", "dependency", "infra", "flaky", "test"])}
    rules.sort(key=lambda r: order[r[1]])
    for i, (rid, gold, paths) in enumerate(todo, 1):
        texts = [diagnostic_text(Path(p).read_text(encoding="utf-8", errors="replace")) for p in paths]
        got = None
        for k, lab, pat in rules:
            t = time.perf_counter()
            hit = any(pat.search(x) for x in texts)
            ms = (time.perf_counter() - t) * 1000
            s = stats[k]
            s["ms"] += ms
            if ms > SLOW_MS:
                s["slow"] += 1
            if not hit:
                continue
            got = got or lab
            if gold == "?":
                if own.get(rid) == k:
                    s["in_cluster"] += 1
                else:
                    s["other_unknown"] += 1
                    if rid in own:
                        s["other_clusters"][own[rid]] += 1
            elif gold == lab:
                s["agree"] += 1
            else:
                s["conflict"][gold] += 1
            if rid in sample_ids and human[rid] not in (lab, "unclear"):
                s["human_conflict"].append(f"{rid}:{human[rid]}")
        if gold == "?":
            first_hit[got or "?"] += 1
        if i % 1000 == 0 or i == len(todo):
            el = time.time() - t0
            print(f"  [{time.strftime('%H:%M:%S')}] {i}/{len(todo)} run, {el / 60:.1f} phút, "
                  f"còn ~{el / i * (len(todo) - i) / 60:.1f} phút", flush=True)

    rows = []
    for k, lab, pat in rules:
        s, c = stats[k], cl[k]
        n_lab = s["agree"] + sum(s["conflict"].values())
        flags = []
        if s["slow"]:
            flags.append(f"CHẬM({s['slow']})")
        if c["count"] and s["in_cluster"] / c["count"] < 0.5:
            flags.append("ÍT KHỚP CỤM")
        if n_lab and sum(s["conflict"].values()) / n_lab > 0.2:
            flags.append("XUNG ĐỘT NHÃN CŨ")
        if s["human_conflict"]:
            flags.append("TRÁI NHÃN NGƯỜI")
        if s["other_unknown"] > 3 * max(c["count"], 1):
            flags.append("RẤT RỘNG")
        rows.append({"cluster": k, "label": lab, "cluster_runs": c["count"], "match_in_cluster": s["in_cluster"],
                     "match_other_unknown": s["other_unknown"],
                     "other_clusters": ";".join(f"{x}:{n}" for x, n in s["other_clusters"].most_common(5)),
                     "labeled_sample_agree": s["agree"],
                     "labeled_sample_conflict": ";".join(f"{x}:{n}" for x, n in s["conflict"].most_common()),
                     "human_conflict": ";".join(s["human_conflict"][:10]), "avg_ms": round(s["ms"] / len(todo), 3),
                     "flags": " ".join(flags), "signature": c["signature"], "regex": decided[k]["regex"]})
    with (H / "rule_review.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    covered = {rid for rid, gold, _ in unknown}  # chỉ để in tổng
    print(f"\nĐã ghi {H / 'rule_review.csv'}. Quy tắc bị gắn cờ:")
    for r in sorted(rows, key=lambda r: -len(r["flags"])):
        if r["flags"]:
            print(f"  {r['cluster']} [{r['label']}] {r['flags']} | cụm {r['match_in_cluster']}/{r['cluster_runs']}, "
                  f"`?` khác {r['match_other_unknown']}, xung đột {r['labeled_sample_conflict'] or 0}, "
                  f"người {r['human_conflict'] or 0} | {r['regex'][:70]}")
    left = first_hit["?"]
    print(f"Run `?` hiện tại: {len(covered)}; bộ quy tắc gán được {len(covered) - left} "
          f"({(len(covered) - left) / max(len(covered), 1):.0%}), còn `?` {left}")
    print("  theo nhãn:", dict(first_hit.most_common()))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--labeled", type=int, default=6000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--proposed", help="file đề xuất trong data/human_labels, chồng lên nhãn người khi đánh giá")
    a = ap.parse_args()
    main(a.labeled, a.seed, a.proposed)
