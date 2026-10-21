"""Kiểm chứng bộ quy tắc gold_labels trên LogChunks (Brandt et al., MSR 2020): log Travis CI kèm
đoạn "lý do fail" do người gán và được developer xác nhận.

LogChunks không có nhãn compile/lint/test, nên đo hai thứ không cần gán thêm:
- định vị: dòng bằng chứng quy tắc chọn trên cả log có nằm trong đoạn người gán không;
- nhất quán: nhãn quy tắc trên riêng đoạn người gán có trùng nhãn trên cả log không.
File CSV xuất ra có cột human_label để người gán điền, rồi chạy lại với --scored để tính precision/recall.

    uv run python -m project3.crawl.logchunks_eval data/external/logchunks/raw/LogChunks
"""
import argparse
import csv
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from .gold_labels import gold_label

JVM = {"Java", "Scala", "Kotlin", "Groovy"}
ANSI = re.compile(r"\x1b\[[0-9;]*m|\[\d*(?:;\d+)*m")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", ANSI.sub("", s)).strip()


def load(root: Path):
    for xml in sorted((root / "build-failure-reason").glob("*/*.xml")):
        lang = xml.parent.name
        for ex in ET.parse(xml).getroot().iter("Example"):
            log = root / "logs" / ex.findtext("Log")
            if log.exists():
                yield {"lang": lang, "repo": xml.stem.replace("@", "/"), "log": ex.findtext("Log"),
                       "chunk": ex.findtext("Chunk") or "", "text": log.read_text(encoding="utf-8", errors="ignore")}


def main(root: Path, out: Path, scored: Path | None) -> None:
    rows = []
    for e in load(root):
        lab, ev = gold_label([e["text"]])
        lab_chunk, _ = gold_label([e["chunk"]])
        chunk = norm(e["chunk"])
        hit = bool(ev) and norm(ev)[:80] in chunk
        rows.append({"lang": e["lang"], "jvm": e["lang"] in JVM, "repo": e["repo"], "log": e["log"],
                     "rule_label": lab, "rule_label_on_chunk": lab_chunk, "evidence_in_chunk": hit,
                     "evidence": ev, "chunk": chunk[:300], "human_label": ""})
    for name, sub in [("JVM", [r for r in rows if r["jvm"]]), ("Tất cả ngôn ngữ", rows)]:
        n = len(sub)
        lab = [r for r in sub if r["rule_label"] != "?"]
        print(f"\n== {name}: {n} log, {len({r['repo'] for r in sub})} repo")
        print(f"  quy tắc gán được nhãn: {len(lab)}/{n} ({len(lab) / max(1, n):.0%})")
        print("  phân bố nhãn:", dict(Counter(r["rule_label"] for r in sub).most_common()))
        hit = sum(r["evidence_in_chunk"] for r in lab)
        print(f"  bằng chứng nằm trong đoạn người gán: {hit}/{len(lab)} ({hit / max(1, len(lab)):.0%})")
        same = sum(r["rule_label"] == r["rule_label_on_chunk"] for r in lab)
        print(f"  nhãn trên đoạn người gán == nhãn trên cả log: {same}/{len(lab)} ({same / max(1, len(lab)):.0%})")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(r for r in rows if r["jvm"])
    print(f"\nĐã lưu {out} (chỉ JVM; điền cột human_label rồi chạy --scored)")
    if scored:
        gold = [r for r in csv.DictReader(open(scored, encoding="utf-8-sig")) if r["human_label"]]
        print(f"\n== Có nhãn người: {len(gold)} log")
        for c in sorted({r["human_label"] for r in gold} | {r["rule_label"] for r in gold}):
            tp = sum(r["rule_label"] == c == r["human_label"] for r in gold)
            p = tp / max(1, sum(r["rule_label"] == c for r in gold))
            rc = tp / max(1, sum(r["human_label"] == c for r in gold))
            print(f"  {c:12s} P={p:.2f} R={rc:.2f} (n người={sum(r['human_label'] == c for r in gold)})")
        acc = sum(r["rule_label"] == r["human_label"] for r in gold) / max(1, len(gold))
        print(f"  accuracy {acc:.2f}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default="data/external/logchunks/raw/LogChunks")
    ap.add_argument("--out", default="data/external/logchunks/rule_vs_chunk_jvm.csv")
    ap.add_argument("--scored", default=None)
    a = ap.parse_args()
    main(Path(a.root), Path(a.out), Path(a.scored) if a.scored else None)
