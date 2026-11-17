"""Kiểm tra đoạn trích cho agent (agent_excerpt.excerpt_v2) trên repo NGOÀI mẫu đánh giá agent (14/11/2026).

Quy tắc trích được viết khi xem 60 run / 33 repo của data/results/rca_agent -> kiểm tra trên repo khác:
  mẫu   = run PR còn tải được log (<= 85 ngày), mỗi lá tối đa N_PER_LEAF run, mỗi (lá, repo) tối đa 1 run,
          bỏ 33 repo của mẫu agent; tải log đầy đủ (1 MB cuối mỗi job lỗi) như rca_agent.prepare
  đo    = (1) dòng bằng chứng của quy tắc (cột evidence) có trong đoạn trích cũ (error_context -> chọn đoạn) / mới
          (2) lá test/itest/flaky: tỉ lệ có khối stack trace test lỗi; in dòng nghi là lỗi test ở run không bắt được
          (3) khối test có tiêu đề nhưng thân rỗng (dấu hiệu đọc sai dạng log); (4) độ dài đoạn trích

    python scripts/analysis/agent_excerpt_holdout.py fetch   # tải log -> data/results/agent_excerpt_holdout/logs
    python scripts/analysis/agent_excerpt_holdout.py eval
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from agent_excerpt import excerpt_v2, norm, split_jobs, test_traces  # noqa: E402
from project3.model.inputs import focus_window  # noqa: E402
from project3.pipeline.run_dataset import clean  # noqa: E402
from rca_agent import LOG_BYTES, failed_job_ids  # noqa: E402

# vòng 1 (seed 0): dùng để SỬA quy tắc (thêm dạng Gradle lồng nhau, Android, bảng báo cáo test) -> không còn độc lập;
# vòng 2 (seed 1): repo chưa xuất hiện ở mẫu agent lẫn vòng 1, chỉ để kiểm tra, KHÔNG sửa quy tắc theo vòng này.
ROUND = int(sys.argv[2]) if len(sys.argv) > 2 else 1
OUT = Path("data/results/agent_excerpt_holdout" + ("" if ROUND == 1 else str(ROUND)))
N_PER_LEAF, DAYS, SEED = 20, 85, ROUND - 1
TESTY = {"testfailure", "itestfailure", "flaky"}


def pick() -> pd.DataFrame:
    used = set(pd.read_parquet("data/results/rca_agent/sample.parquet").repository)
    for k in range(1, ROUND):  # bỏ repo của các vòng trước
        used |= set(pd.read_parquet(Path("data/results/agent_excerpt_holdout" + ("" if k == 1 else str(k)))
                                    / "sample.parquet").repository)
    lab = pd.read_parquet("data/kaggle_log_ds/runs.parquet", columns=["run_id", "leaf"])
    r = pd.read_parquet("data/run_dataset/runs.parquet",
                        columns=["run_id", "repository", "event", "created_at", "evidence"]).merge(lab, on="run_id")
    r["created_at"] = pd.to_datetime(r.created_at, utc=True)
    r = r[(r.event == "pull_request") & ~r.repository.isin(used)
          & (r.created_at >= pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=DAYS))]
    r = r[[(Path("data/crawl_pr") / x.replace("/", "__") / "jobs.jsonl").exists() for x in r.repository]]
    r = r.sample(frac=1, random_state=SEED).drop_duplicates(["leaf", "repository"])
    return r.groupby("leaf").head(N_PER_LEAF).reset_index(drop=True)


def fetch() -> None:
    from project3.crawl.github import GitHub, load_token
    gh = GitHub(load_token())
    s = pick()
    (OUT / "logs").mkdir(parents=True, exist_ok=True)
    s.to_parquet(OUT / "sample.parquet", index=False)
    print(len(s), "run,", s.repository.nunique(), "repo;", s.leaf.value_counts().to_dict(), flush=True)
    for r in s.itertuples():
        f = OUT / "logs" / f"{r.run_id}.txt"
        if f.exists():
            continue
        logs = []
        for jid, name, _ in failed_job_ids(r.repository, r.run_id):
            try:
                t = gh.get_log_tail(f"/repos/{r.repository}/actions/jobs/{jid}/logs", tail_bytes=LOG_BYTES)
            except Exception as e:  # lỗi mạng / log hết hạn: bỏ job
                print(r.run_id, f"job {jid}: {type(e).__name__}", flush=True)
                t = None
            if t:
                logs.append(f"===== job: {name} (id {jid}) =====\n{t}")
        if logs:
            f.write_text("\n\n".join(logs), encoding="utf-8")
        else:
            print(r.run_id, "không tải được log", flush=True)


def old_excerpt(run_id: int) -> str:
    ch = pd.read_parquet("data/kaggle_log_ds/chunks.parquet", columns=["run_id", "job_id", "chunk_idx", "text"],
                         filters=[("run_id", "==", run_id)]).sort_values(["job_id", "chunk_idx"])
    return "\n\n".join(focus_window(t, 1600, "split") for t in ch.text)


FAILISH = re.compile(r"<<< (?:FAILURE|ERROR)!|\bFAILED\b|^(?:FAIL|ERROR): |^_{3,} |AssertionError|Tests? failed|"
                     r"\d+ failing|✗|✕|×", re.M)


def evaluate() -> None:
    s = pd.read_parquet(OUT / "sample.parquet")
    rows, misses = [], []
    for r in s.itertuples():
        f = OUT / "logs" / f"{r.run_id}.txt"
        if not f.exists():
            continue
        full = f.read_text(encoding="utf-8")
        new, old = excerpt_v2(full), old_excerpt(r.run_id)
        ev = norm(clean(r.evidence or ""))[:120].strip()
        traces = [tr for t in split_jobs(full) for tr in test_traces([clean(x) for x in t.splitlines()])]
        rows.append(dict(run_id=r.run_id, repo=r.repository, leaf=r.leaf, full_k=len(full) / 1e3, new_k=len(new) / 1e3,
                         ev=bool(ev), ev_full=bool(ev) and ev in norm(full), ev_old=bool(ev) and ev in norm(old),
                         ev_new=bool(ev) and ev in norm(new), n_tests=len(traces),
                         n_empty=sum(not b and "|" not in h for h, b in traces)))
        if r.leaf in TESTY and not traces:
            hits = [clean(x)[:160] for x in full.splitlines() if FAILISH.search(clean(x))][:4]
            misses.append(f"== {r.run_id} {r.repository} {r.leaf}\n" + "\n".join(hits))
    d = pd.DataFrame(rows)
    d.to_csv(OUT / "eval.csv", index=False)
    (OUT / "test_misses.txt").write_text("\n\n".join(misses), encoding="utf-8")
    print(f"{len(d)} run, {d.repo.nunique()} repo (ngoài 33 repo của mẫu agent)")
    e = d[d.ev_full]
    print(f"\n(1) dòng bằng chứng (chỉ run có dòng này trong log đầy đủ: {len(e)}): "
          f"đoạn trích cũ {e.ev_old.mean():.1%}  mới {e.ev_new.mean():.1%}; mới mất mà cũ có: {(e.ev_old & ~e.ev_new).sum()}")
    print(e.groupby("leaf")[["ev_old", "ev_new"]].mean().round(2).T.to_string())
    t = d[d.leaf.isin(TESTY)]
    print(f"\n(2) lá test/itest/flaky: có khối stack trace {(t.n_tests > 0).mean():.1%} ({(t.n_tests > 0).sum()}/{len(t)})")
    print(t.groupby("leaf").n_tests.apply(lambda x: f"{(x > 0).sum()}/{len(x)}").to_string())
    o = d[~d.leaf.isin(TESTY)]
    print(f"    lá khác có khối test: {(o.n_tests > 0).sum()}/{len(o)}")
    print(f"\n(3) khối test thân rỗng: {d.n_empty.sum()} / {d.n_tests.sum()} khối")
    print(f"\n(4) độ dài đoạn trích mới (nghìn ký tự): trung vị {d.new_k.median():.1f}, p95 {d.new_k.quantile(.95):.1f}, "
          f"lớn nhất {d.new_k.max():.1f}")
    print("-> run test không bắt được:", OUT / "test_misses.txt")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    {"fetch": fetch, "eval": evaluate}[sys.argv[1]]()
