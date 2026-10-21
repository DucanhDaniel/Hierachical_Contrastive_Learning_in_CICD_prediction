"""Bước cuối của pipeline: ghép commit + nhãn chi tiết + diff thành dataset chuẩn, kèm độ phủ, cổng chất lượng, manifest.

    python -m project3.pipeline.export_dataset                 # đọc data/processed, ghi data/dataset/
    python -m project3.pipeline.export_dataset --out data/dataset_v1

Đầu ra (data/dataset/):
  commits.parquet  một dòng = một commit trong chuỗi push hoặc một PR: outcome, nhãn 3 tầng, đường dẫn diff,
                   feature lịch sử chỉ dùng thông tin TRƯỚC commit, cột chia tập (thời gian / repo)
  coverage.csv     độ phủ theo repo x event và cờ cổng chất lượng (không loại repo, chỉ gắn cờ)
  manifest.json    phiên bản rule, git commit của code, cửa sổ crawl, số dòng, checksum
  README.md        dataset card
"""
import argparse
import csv
import hashlib
import json
import subprocess
import zlib
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from project3.crawl.gold_labels import RULE_VERSION

ROOTS = {"pull_request": Path("data/crawl_pr"), "push": Path("data/validate")}
NO_LOG = "(không có log)"
HISTORY_K = 10  # Rausch et al. 2017: tỉ lệ fail của 10 build gần nhất ảnh hưởng kết quả build ở mọi dự án
TEST_SHARE = 0.3  # chia theo thời gian 70/30 trong từng repo, như thí nghiệm HCL
REPO_FOLDS = 5
# Cổng chất lượng: repo không đạt vẫn giữ trong dữ liệu, chỉ gắn cờ để người dùng tự quyết khi chọn tập
GATES = {"log_coverage": 0.8, "unknown_rate": 0.3, "diff_coverage": 0.95, "min_code_fail_commits": 20}


def run_stats(con):
    """Thống kê mức run từ runs.jsonl + gold_labels.csv của từng root (log có/thiếu, nhãn `?`, cửa sổ thời gian)."""
    rows = []
    for event, root in ROOTS.items():
        if not root.exists():
            continue
        gold = {}
        if (root / "gold_labels.csv").exists():
            with (root / "gold_labels.csv").open(encoding="utf-8-sig") as f:
                gold = {int(r["run_id"]): r for r in csv.DictReader(f)}
        for d in sorted(p for p in root.iterdir() if (p / "runs.jsonl").exists()):
            repo = d.name.replace("__", "/")
            runs = [json.loads(l) for l in (d / "runs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
            fail = [r for r in runs if r["conclusion"] == "failure"]
            # run fail không có job nào (workflow lỗi lúc khởi động): không có log để tải, không tính là thiếu log
            no_jobs = set()
            if (d / "jobs.jsonl").exists():
                for l in (d / "jobs.jsonl").read_text(encoding="utf-8").splitlines():
                    if l.strip() and not (row := json.loads(l))["jobs"]:
                        no_jobs.add(row["run_id"])
            labelled = [gold[r["id"]] for r in fail if r["id"] in gold]
            build = [g for g in labelled if g["non_build"] != "True" and g["gold"] != "non_build"]
            n_no_jobs = sum(int(g["run_id"]) in no_jobs for g in build)
            build = [g for g in build if int(g["run_id"]) not in no_jobs]
            with_log = [g for g in build if g["gold"] != NO_LOG]
            status = {}
            if (d / "crawl_status.json").exists():
                status = json.loads((d / "crawl_status.json").read_text(encoding="utf-8"))
            rows.append({"repository": repo, "event": event, "crawl_status": status.get("status", ""),
                         "window_from": min((r["created_at"] for r in runs), default="")[:10],
                         "window_to": max((r["created_at"] for r in runs), default="")[:10],
                         "n_runs": len(runs), "n_fail_runs": len(fail), "n_fail_runs_no_jobs": n_no_jobs,
                         "n_fail_build_runs": len(build),
                         "n_fail_runs_with_log": len(with_log),
                         "n_fail_runs_unknown": sum(g["gold"] == "?" for g in with_log)})
    return rows


def git_commit():
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "src"], capture_output=True, text=True).stdout.strip())
        return head + ("-dirty" if dirty else "")
    except OSError:
        return "unknown"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main(processed: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    commits, fine, diffs = processed / "commits_all.parquet", processed / "fine_labels.parquet", processed / "diffs_all.csv"
    con.sql(f"CREATE VIEW c AS SELECT * FROM '{commits.as_posix()}'")
    if fine.exists():
        con.sql(f"CREATE VIEW f AS SELECT repository, head_sha, label, subtype, module FROM '{fine.as_posix()}'")
    else:
        con.sql("CREATE VIEW f AS SELECT NULL::VARCHAR repository, NULL::VARCHAR head_sha, "
                "NULL::VARCHAR label, NULL::VARCHAR subtype, NULL::VARCHAR module WHERE false")
    if diffs.exists():
        con.sql(f"""CREATE VIEW d AS SELECT repository, head_sha, kind, path diff_path, ok::BOOLEAN diff_ok, err diff_err
            FROM read_csv('{diffs.as_posix()}', header=true, all_varchar=true, quote='"', escape='"')""")
    else:
        con.sql("CREATE VIEW d AS SELECT NULL::VARCHAR repository, NULL::VARCHAR head_sha, NULL::VARCHAR kind, "
                "NULL::VARCHAR diff_path, NULL::BOOLEAN diff_ok, NULL::VARCHAR diff_err WHERE false")
    # needs_diff: commit dùng cho bài toán dự đoán (pass hoặc fail do code); env/`?` không cần diff
    con.sql(f"""CREATE TABLE ds AS
    WITH base AS (
        SELECT c.*, f.subtype, f.module,
               d.diff_path, coalesce(d.diff_ok, false) diff_ok, d.diff_err,
               (c.outcome = 'pass' OR c.cause = 'code') needs_diff,
               c.first_run_at::TIMESTAMP t
        FROM c
        -- cùng sha có thể ở cả push và PR với nhãn khác nhau -> nối cả theo nhãn
        LEFT JOIN f ON f.repository = c.repository AND f.head_sha = c.head_sha AND f.label = c.label
        LEFT JOIN d ON d.repository = c.repository AND d.head_sha = c.head_sha
                   AND d.kind = CASE WHEN c.event = 'pull_request' THEN 'pr' ELSE 'commit' END),
    hist AS (
        SELECT *,
            -- trong cùng chuỗi (nhánh chính hoặc một PR): commit liền trước, chỉ dùng thông tin quá khứ
            lag(outcome) OVER (PARTITION BY repository, sequence ORDER BY t, head_sha) prev_outcome,
            row_number() OVER (PARTITION BY repository, sequence ORDER BY t, head_sha) - 1 seq_idx,
            -- trong cả repo: tỉ lệ fail của {HISTORY_K} commit gần nhất trước đó
            avg((outcome = 'fail')::INT) OVER (PARTITION BY repository ORDER BY t, head_sha
                ROWS BETWEEN {HISTORY_K} PRECEDING AND 1 PRECEDING) repo_fail_rate_last{HISTORY_K},
            percent_rank() OVER (PARTITION BY repository ORDER BY t, head_sha) time_rank
        FROM base)
    SELECT * EXCLUDE (t, time_rank),
        -- cây nhãn tường minh: tầng 1 nhóm (build/test do code, env do môi trường), tầng 2 loại lỗi, tầng 3 dạng lỗi;
        -- mỗi nút đúng một cha (kiểm tra ở fine_labels)
        CASE WHEN outcome = 'fail' AND label <> '?' THEN label_group END label_l1,
        CASE WHEN outcome = 'fail' AND label <> '?' THEN label END label_l2,
        CASE WHEN outcome = 'fail' AND label <> '?' THEN subtype END label_l3,
        CASE WHEN outcome = 'pass' THEN 'pass' WHEN label = '?' THEN 'fail/?'
             ELSE concat_ws('/', 'fail', label_group, nullif(label, label_group), subtype) END label_path,
        CASE WHEN time_rank < {1 - TEST_SHARE} THEN 'train' ELSE 'test' END split_time
    FROM hist ORDER BY repository, first_run_at""")
    # chia theo repo (P2): fold cố định theo tên repo, không phụ thuộc thứ tự hay số repo
    folds = {r: zlib.crc32(r.encode()) % REPO_FOLDS for (r,) in con.sql("SELECT DISTINCT repository FROM ds").fetchall()}
    con.sql("ALTER TABLE ds ADD COLUMN repo_fold INTEGER")
    con.executemany("UPDATE ds SET repo_fold = ? WHERE repository = ?", [(f, r) for r, f in folds.items()])
    con.sql(f"COPY ds TO '{(out / 'commits.parquet').as_posix()}' (FORMAT parquet)")

    # độ phủ theo repo x event + cổng chất lượng
    cstats = {(r, e): (n, fc, nd, dok) for r, e, n, fc, nd, dok in con.sql("""
        SELECT repository, event, count(*), sum((outcome = 'fail' AND cause = 'code')::INT),
               sum(needs_diff::INT), sum((needs_diff AND diff_ok)::INT) FROM ds GROUP BY 1, 2""").fetchall()}
    cov = []
    for s in run_stats(con):
        n, fc, nd, dok = cstats.get((s["repository"], s["event"]), (0, 0, 0, 0))
        log_cov = s["n_fail_runs_with_log"] / s["n_fail_build_runs"] if s["n_fail_build_runs"] else None
        unk = s["n_fail_runs_unknown"] / s["n_fail_runs_with_log"] if s["n_fail_runs_with_log"] else None
        diff_cov = dok / nd if nd else None
        flags = [name for name, bad in [
            ("log_coverage", log_cov is not None and log_cov < GATES["log_coverage"]),
            ("unknown_rate", unk is not None and unk > GATES["unknown_rate"]),
            ("diff_coverage", diff_cov is not None and diff_cov < GATES["diff_coverage"]),
            ("min_code_fail_commits", fc < GATES["min_code_fail_commits"]),
            ("crawl_incomplete", s["crawl_status"] not in ("completed", ""))] if bad]
        cov.append({**s, "n_commits": n, "n_code_fail_commits": fc,
                    "log_coverage": None if log_cov is None else round(log_cov, 3),
                    "unknown_rate": None if unk is None else round(unk, 3),
                    "diff_coverage": None if diff_cov is None else round(diff_cov, 3),
                    "gate_ok": not flags, "gate_flags": ";".join(flags)})
    if cov:
        with (out / "coverage.csv").open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, list(cov[0]))
            w.writeheader()
            w.writerows(cov)

    labels = dict(con.sql("SELECT label, count(*) FROM ds GROUP BY 1 ORDER BY 2 DESC").fetchall())
    n, nrepo = con.sql("SELECT count(*), count(DISTINCT repository) FROM ds").fetchone()
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(), "code_commit": git_commit(), "rule_version": RULE_VERSION,
        "n_commits": n, "n_repos": nrepo, "labels": labels,
        "history_k": HISTORY_K, "split_time_test_share": TEST_SHARE, "repo_folds": REPO_FOLDS, "gates": GATES,
        "repos_gate_ok": sorted({c["repository"] for c in cov if c["gate_ok"]}),
        "crawl_windows": {f"{c['event']}|{c['repository']}": [c["window_from"], c["window_to"]] for c in cov},
        "files": {p.name: {"bytes": p.stat().st_size, "sha256": sha256(p)}
                  for p in (out / "commits.parquet", out / "coverage.csv") if p.exists()}}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    write_card(out, manifest, cov, con)
    print(f"{n} commit, {nrepo} repo, nhãn: {labels}")
    print(f"Repo-event đạt cổng chất lượng: {sum(c['gate_ok'] for c in cov)}/{len(cov)}. Đã ghi {out}")


def write_card(out: Path, m: dict, cov: list[dict], con) -> None:
    ev = Path("data/human_labels/eval.json")
    val = json.loads(ev.read_text(encoding="utf-8")) if ev.exists() else {}
    tiers = con.sql("""SELECT outcome, cause, label_group, label, count(*) n FROM ds
        GROUP BY ALL ORDER BY outcome, cause, n DESC""").fetchall()
    leaves = dict(((l2, l3), n) for l2, l3, n in con.sql("""SELECT label_l2, coalesce(label_l3, '(trống)'), count(*)
        FROM ds WHERE label_l2 IS NOT NULL GROUP BY ALL""").fetchall())
    lines = [
        "# Dataset lỗi build CI (GitHub Actions, Java/JVM)", "",
        f"Tạo lúc {m['created_utc'][:19]} UTC · rule `{m['rule_version']}` · code `{m['code_commit'][:12]}` · "
        f"{m['n_commits']} commit · {m['n_repos']} repo", "",
        "## Thu thập",
        "Crawl GitHub Actions API: run của workflow build/test (bỏ bot, release, docs...), job/step của run fail, "
        "log job fail (chỉ giữ đoạn quanh `##[error]`). PR lấy tối đa 2 job fail mỗi run; push chỉ nhánh "
        "master/main/trunk/develop. GitHub giữ log 60–90 ngày tuỳ repo nên cửa sổ thực tế ghi trong `coverage.csv`.", "",
        "## Gán nhãn",
        "Nhãn chỉ đến từ **bộ quy tắc regex trên log** (không dùng LLM làm nguồn nhãn). Quy tắc được xây bằng open coding "
        "theo cụm chữ ký lỗi (Rausch et al., 2017) và kiểm chứng bằng tập người gán mù. Run có nhiều lỗi lấy lỗi ở "
        "giai đoạn sớm nhất: buildconfig → compile → dependency → lint → test → flaky → infra. Không khớp quy tắc nào: `?` (không đoán).",
        "", "| outcome | cause | nhóm | nhãn | số commit |", "|---|---|---|---|---:|",
        *[f"| {o} | {c} | {g} | {l} | {k} |" for o, c, g, l, k in tiers], "",
        "### Cây nhãn 3 tầng (cột `label_l1/l2/l3`, đường dẫn `label_path`)",
        "Tầng 1 nhóm (build, test: do code; env: môi trường, không huấn luyện) → tầng 2 giai đoạn lỗi → tầng 3 loại lỗi theo bảng II của Rausch et al. (MSR 2017), thêm network (lỗi do mạng) và flaky (test không ổn định). Tầng 3 suy từ dòng bằng chứng; tập lá theo Rausch do người quyết (16/10/2026), quy tắc nhận diện chưa đo precision; infra không khớp nhánh nào (vd. lỗi xác thực) để trống.", "",
        "```",
        *[line for g, l in [(g, l) for o, _, g, l, _ in tiers if o == "fail" and l != "?"]
          for line in [f"{g}/{l}" if g != l else g] + [f"    └ {l3}: {n}" for (l2, l3), n in sorted(leaves.items(), key=lambda x: -x[1])
                                            if l2 == l]],
        "```", ""]
    if val:
        lines += ["## Kiểm chứng nhãn (tập phát triển)",
                  f"Gán mù {val.get('n')} run: đồng thuận {val.get('agreement', 0):.2f}, Cohen's kappa "
                  f"{val.get('kappa', 0):.2f}. Đây là tập đã dùng để sửa quy tắc, không phải kiểm chứng độc lập.", ""]
    lines += [
        "## Cột chính của `commits.parquet`",
        "- `repository, event, sequence, pr_number, head_sha, first_run_at`: định danh commit và chuỗi (push / một PR)",
        "- `outcome` pass|fail · `cause` code|env|? · `label_group` build|test|env · `label` buildconfig|compile|dependency|lint|test|flaky|infra|?",
        "- `label_l1` build|test|env · `label_l2` loại lỗi · `label_l3` loại lỗi Rausch · `label_path` vd. fail/build/lint/quality",
        "- `subtype, module`: nhãn tầng 3 (= `label_l3`) và module lỗi từ dòng bằng chứng",
        "- `diff_path, diff_ok`: diff `sha^..sha` (push) hoặc `merge-base..sha` (PR), nén gzip",
        f"- `prev_outcome, seq_idx, repo_fail_rate_last{m['history_k']}`: lịch sử, chỉ dùng thông tin trước commit",
        "- `first_failure`: lần fail đầu sau một commit pass (loại bỏ commit đang sửa lỗi)",
        f"- `split_time` train/test {int((1 - m['split_time_test_share']) * 100)}/{int(m['split_time_test_share'] * 100)} "
        f"theo thời gian trong từng repo (P1) · `repo_fold` 0–{m['repo_folds'] - 1} cho chia theo repo (P2)", "",
        "## Cổng chất lượng",
        "Repo không đạt vẫn nằm trong dữ liệu, chỉ gắn cờ ở `coverage.csv`: "
        + ", ".join(f"`{k}` {v}" for k, v in m["gates"].items())
        + f". Đạt: {sum(c['gate_ok'] for c in cov)}/{len(cov)} repo-event.", "",
        "## Giới hạn",
        "- Quy tắc viết cho Maven/Gradle; log ngoài hệ sinh thái này dễ thành `?`.",
        "- Commit fail không còn log (hết hạn) giữ nhãn `?`.",
        "- Lỗi infra/flaky không dự đoán được từ diff; nên loại khỏi bài toán dự đoán loại lỗi.", ""]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", type=Path, default=Path("data/processed"))
    ap.add_argument("--out", type=Path, default=Path("data/dataset"))
    a = ap.parse_args()
    main(a.processed, a.out)
