"""Áp dụng lại rule trên log đã tải; sao lưu dataset và xuất thay đổi để kiểm tra.

    python -m project3.pipeline.relabel

Không sửa nhãn người, key của vòng mù, hay các snapshot/thí nghiệm đã xuất.
"""
import argparse
import csv
import json
import shutil
import sys
from collections import Counter
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from project3.crawl import build_log_labels, gold_labels
from project3.crawl import fine_labels
from .label_ui import current_labels

ROOTS = [Path("data/validate"), Path("data/crawl_pr")]


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fields)
        writer.writeheader()
        writer.writerows(rows)


def main(resume_audit=None, reports_only=False):
    if reports_only and not resume_audit:
        raise ValueError("--reports-only requires --resume-audit")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = resume_audit or Path("data/processed") / f"relabel_{stamp}"
    if not resume_audit:
        out.mkdir()
    targets = [root / "gold_labels.csv" for root in ROOTS] + [
        Path("data/processed/commits_all.parquet"), Path("data/processed/fine_labels.parquet")]
    for path in targets:
        if path.exists():
            backup = out / "backup" / path
            if not resume_audit:
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup)
            elif not backup.exists():
                raise FileNotFoundError(f"Missing original backup: {backup}")
    shutil.copy2(Path(gold_labels.__file__), out / "rules.py")
    shutil.copy2(gold_labels.FALLBACK_RULES_PATH, out / "label_rules.json")
    summary = {"rule_version": gold_labels.RULE_VERSION, "status": "running", "roots": {}}
    summary_path = out / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    changes = []
    fresh = {}
    before_integration = {}
    class Tee:
        """In ra màn hình và ghi file cùng lúc, flush ngay để theo dõi được tiến độ."""
        def __init__(self, *streams):
            self.streams = streams

        def write(self, s):
            for f in self.streams:
                f.write(s)
                f.flush()
            return len(s)

        def flush(self):
            for f in self.streams:
                f.flush()

    print(f"Audit: {out}  (log đầy đủ: {out / 'rebuild.log'})", flush=True)
    with (out / "rebuild.log").open("a" if reports_only else "w", encoding="utf-8") as log, \
            redirect_stdout(Tee(sys.__stdout__, log)):
        for root in ROOTS:
            old_rows = read_csv(out / "backup" / root / "gold_labels.csv")
            old = {r["run_id"]: r for r in old_rows}
            before_integration.update({int(rid): r for rid, r in old.items()})
            if not reports_only:
                gold_labels.main(root)
            new_rows = read_csv(root / "gold_labels.csv")
            # build_log_labels dùng lần ghi cuối cho mỗi run; đối chiếu cùng ngữ nghĩa.
            new = list({r["run_id"]: r for r in new_rows}.values())
            transitions = Counter()
            for r in new:
                fresh[int(r["run_id"])] = r
                before = old.get(r["run_id"])
                if before and before["gold"] != r["gold"]:
                    transitions[f"{before['gold']} -> {r['gold']}"] += 1
                    changes.append({"root": str(root), "repo": r["repo"], "run_id": r["run_id"],
                                    "workflow": r["workflow"], "old": before["gold"], "new": r["gold"],
                                    "old_evidence": before["evidence"], "new_evidence": r["evidence"]})
            summary["roots"][str(root)] = {"old_rows": len(old_rows), "new_rows": len(new_rows),
                "old_runs": len(old), "new_runs": len(new),
                "added_runs": len({r['run_id'] for r in new} - old.keys()),
                "removed_runs": len(old.keys() - {r['run_id'] for r in new}),
                "label_changes": dict(transitions), "new_labels": dict(Counter(r["gold"] for r in new))}
            summary["roots"][str(root)].update(
                old_build_unknown=sum(r["gold"] == "?" and r["non_build"] != "True" for r in old.values()),
                new_build_unknown=sum(r["gold"] == "?" and r["non_build"] != "True" for r in new),
                new_non_build=sum(r["non_build"] == "True" for r in new))
            log.flush()
        if not reports_only:
            print(f"[{datetime.now():%H:%M:%S}] gộp theo commit -> {targets[2]}", flush=True)
            build_log_labels.main(ROOTS, targets[2])
            print(f"[{datetime.now():%H:%M:%S}] nhãn chi tiết -> {targets[3]}", flush=True)
            fine_labels.main(targets[2], targets[3])
            print(f"[{datetime.now():%H:%M:%S}] ghi báo cáo đối chiếu ...", flush=True)
    write_csv(out / "run_changes.csv", changes,
              ["root", "repo", "run_id", "workflow", "old", "new", "old_evidence", "new_evidence"])
    con = duckdb.connect()
    old_path = (out / "backup" / targets[2]).as_posix()
    con.read_parquet(old_path).create_view("old")
    con.read_parquet(targets[2].as_posix()).create_view("new")
    changed = con.sql("""SELECT n.repository, n.event, n.sequence, n.head_sha,
        o.label AS "old", n.label AS "new", o.cause old_cause, n.cause new_cause,
        o.run_labels old_run_labels, n.run_labels new_run_labels
        FROM old o JOIN new n USING (repository, sequence, head_sha)
        WHERE o.label != n.label OR o.run_labels != n.run_labels""").fetchdf()
    changed.to_csv(out / "commit_changes.csv", index=False, encoding="utf-8-sig")
    removed = con.sql("""SELECT o.* FROM old o WHERE NOT EXISTS
        (SELECT 1 FROM new n WHERE n.repository=o.repository AND n.sequence=o.sequence AND n.head_sha=o.head_sha)""").fetchdf()
    removed.to_csv(out / "removed_commits.csv", index=False, encoding="utf-8-sig")
    summary["commits"] = {
        "old": con.sql("SELECT count(*) FROM old").fetchone()[0],
        "new": con.sql("SELECT count(*) FROM new").fetchone()[0],
        "removed": len(removed),
        "label_changes": dict(Counter(f"{r.old} -> {r.new}" for r in changed.itertuples() if r.old != r.new)),
        "old_unknown_fail": con.sql("SELECT count(*) FROM old WHERE label='?'").fetchone()[0],
        "new_unknown_fail": con.sql("SELECT count(*) FROM new WHERE label='?'").fetchone()[0],
    }
    human_dir = Path("data/human_labels")
    human = current_labels(human_dir)
    adj = current_labels(human_dir, "adjudication.jsonl")
    key = json.loads((human_dir / "key.json").read_text(encoding="utf-8"))
    sample = json.loads((human_dir / "sample.json").read_text(encoding="utf-8"))
    comparison = []
    for item in sample:
        rid = item["run_id"]
        if rid not in human or rid not in fresh:
            continue
        final = adj.get(rid, human[rid])["label"]
        row = fresh[rid]
        comparison.append({"repo": item["repo"], "run_id": rid, "workflow": item["workflow"],
            "old": key[str(rid)], "before_integration": before_integration.get(rid, {}).get("gold", ""),
            "new": row["gold"], "human_blind": human[rid]["label"], "final": final,
            "evidence": row["evidence"], "url": f"https://github.com/{item['repo']}/actions/runs/{rid}"})
    fields = ["repo", "run_id", "workflow", "old", "before_integration", "new", "human_blind", "final", "evidence", "url"]
    write_csv(out / "human_sample_comparison.csv", comparison, fields)
    error_ids = {int(r["run_id"]) for r in read_csv(human_dir / "rule_errors.csv")}
    write_csv(out / "rule_errors_checked.csv", [r for r in comparison if r["run_id"] in error_ids], fields)
    # Sau khi sửa trên chính mẫu này, đây là phép đối chiếu, không phải kiểm chứng độc lập.
    summary["human_sample"] = {"n": len(comparison),
        "old_matches_final": sum(r["old"] == ("?" if r["final"] == "unclear" else r["final"]) for r in comparison),
        "new_matches_final": sum(r["new"] == ("?" if r["final"] == "unclear" else r["final"]) for r in comparison),
        "note": "Development sample; human labels and frozen evaluation key are unchanged."}
    candidates = [r for r in comparison if r["before_integration"] == "?"]
    covered = [r for r in candidates if r["new"] != "?"]
    summary["fallback_human_sample"] = {"unknown_before": len(candidates), "covered": len(covered),
        "matches_final": sum(r["new"] == r["final"] for r in covered),
        "non_build": sum(r["new"] == "non_build" for r in covered),
        "note": "Development sample; non_build was not an option in the original human UI."}
    summary["status"] = "completed"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume-audit", type=Path, help="Resume using the original backups in this audit directory")
    parser.add_argument("--reports-only", action="store_true", help="Rebuild comparison reports after dataset generation finished")
    args = parser.parse_args()
    main(args.resume_audit, args.reports_only)
