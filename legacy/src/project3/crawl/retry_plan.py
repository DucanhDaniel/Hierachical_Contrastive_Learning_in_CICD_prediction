"""Chọn repo còn thiếu jobs/log; giữ bản sao marker missing khi thử lại một lần."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from .gha import pick_jobs


def read_rows(path):
    return [json.loads(l) for l in path.read_text(encoding='utf-8').splitlines() if l.strip()] if path.exists() else []


def needs_retry(root: Path, repo: str, limit: int, retry_missing: bool, prepare: bool):
    d = root / repo.replace('/', '__')
    if not (d / 'runs.jsonl').exists():
        return True
    status_path = d / 'crawl_status.json'
    failed = status_path.exists() and json.loads(status_path.read_text(encoding='utf-8'))['status'] == 'failed'
    runs = read_rows(d / 'runs.jsonl')
    jobs = read_rows(d / 'jobs.jsonl')
    done = {r['run_id'] for r in jobs}
    missing_jobs = any(r['conclusion'] == 'failure' and r['id'] not in done for r in runs)
    missing_logs = False
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    for row in jobs:
        for job in pick_jobs(row['jobs'], limit):
            text = d / 'logs' / f"{job['id']}.txt"
            marker = text.with_suffix('.missing')
            if text.exists() and text.stat().st_size > 0:
                continue
            if marker.exists() and not retry_missing:
                continue
            missing_logs = True
            if prepare:
                # Không xóa bằng chứng cũ; chỉ chuyển file trong cùng thư mục dữ liệu.
                for p in (marker, text):
                    if p.exists():
                        p.rename(p.with_name(p.name + '.retry.' + stamp))
    return failed or missing_jobs or missing_logs


def main(retry_missing, prepare):
    def repos(path):
        return [l.strip() for l in Path(path).read_text(encoding='utf-8').splitlines() if l.strip() and not l.startswith('#')]
    groups = [
        ('data/crawl_pr', 'pull_request', repos('configs/repos_core.txt'), 2),
        ('data/crawl_pr', 'pull_request', repos('configs/repos_extra.txt'), 2),
        ('data/validate', 'push', repos('configs/repos_extra.txt'), 0),
    ]
    plans = []
    for root, event, candidates, limit in groups:
        todo = [repo for repo in candidates if needs_retry(Path(root), repo, limit, retry_missing, prepare)]
        if todo:
            plans.append({'root': root, 'event': event, 'repos': todo, 'max_jobs_per_run': limit})
    print(json.dumps(plans, ensure_ascii=False))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--retry-missing', action='store_true')
    ap.add_argument('--prepare', action='store_true')
    a = ap.parse_args()
    main(a.retry_missing, a.prepare)
