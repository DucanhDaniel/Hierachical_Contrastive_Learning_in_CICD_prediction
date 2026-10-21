"""Lấy mẫu run theo nhãn, xuất evidence và 30 dòng quanh lỗi để đọc thủ công.

uv run python -m project3.crawl.review_sample data/validate data/crawl_pr
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import random
import re

from .gold_labels import AGG_JOB

LABELS = ('compile', 'lint', 'dependency', 'test', 'infra', 'flaky')
ANSI = re.compile(r'\x1b\[[0-9;]*m')


def clean(line: str) -> str:
    return re.sub(r'^\S+Z ', '', ANSI.sub('', line)).strip()


def main(roots: list[Path], out: Path, count: int, seed: int) -> None:
    out.mkdir(parents=True, exist_ok=True)
    rows = {}
    jobs = {}
    for root in roots:
        if not (root / 'gold_labels.csv').exists():
            continue
        with (root / 'gold_labels.csv').open(encoding='utf-8-sig', newline='') as f:
            for row in csv.DictReader(f):
                if row['non_build'].lower() == 'false' and row['gold'] in LABELS:
                    row['root'] = str(root)
                    rows.setdefault((row['repo'], row['run_id']), row)
        for d in sorted(root.iterdir()):
            if not d.is_dir() or not (d / 'jobs.jsonl').exists():
                continue
            for line in (d / 'jobs.jsonl').read_text(encoding='utf-8').splitlines():
                record = json.loads(line)
                jobs[(str(root), d.name.replace('__', '/'), str(record['run_id']))] = record['jobs']
    manifest = []
    for label in LABELS:
        candidates = sorted((r for r in rows.values() if r['gold'] == label),
                            key=lambda r: (r['repo'], int(r['run_id'])))
        sample = random.Random(f'{seed}:{label}').sample(candidates, min(count, len(candidates)))
        blocks = [f'Nhãn: {label}; seed={seed}; mẫu={len(sample)}/{count}; tổng={len(candidates)}\n']
        for row in sample:
            blocks.append(f"\n=== {row['repo']} run={row['run_id']} workflow={row['workflow']} ===\n"
                          f"root={row['root']}\nevidence={row['evidence']}\n")
            matched = False
            excerpts = []
            for job in jobs.get((row['root'], row['repo'], row['run_id']), []):
                if job['conclusion'] != 'failure' or AGG_JOB.search(job['name']):
                    continue
                path = Path(row['root']) / row['repo'].replace('/', '__') / 'logs' / f"{job['id']}.txt"
                if not path.exists():
                    continue
                lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
                hits = [i for i, line in enumerate(lines) if row['evidence'] and clean(line).startswith(row['evidence'])]
                if not hits:
                    continue
                matched = True
                i = hits[0]
                excerpt = f"job={job['id']} {job['name']} file={path}\n" + '\n'.join(
                    f'{k + 1:5d} {lines[k]}' for k in range(max(0, i - 15), min(len(lines), i + 16)))
                excerpts.append(excerpt)
                break
            blocks.extend(excerpts)
            if not matched:
                blocks.append('KHÔNG TÌM THẤY DÒNG EVIDENCE — cần kiểm tra thủ công.\n')
            blocks.append('\nĐánh giá: [đúng / sai / chưa đủ bằng chứng]; lý do:\n')
            manifest.append({**{k: row[k] for k in ('root', 'repo', 'run_id', 'workflow', 'gold', 'evidence')},
                             'context_found': matched,
                             'fingerprint': hashlib.sha256('\n'.join(excerpts).encode()).hexdigest()})
        (out / f'label_review_{label}.txt').write_text('\n'.join(blocks), encoding='utf-8')
        print(f'{label}: {len(sample)}/{count} mẫu, tổng {len(candidates)}')
    with (out / 'label_review_manifest.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['root', 'repo', 'run_id', 'workflow', 'gold', 'evidence', 'context_found', 'fingerprint'])
        w.writeheader()
        w.writerows(manifest)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('roots', nargs='+', type=Path)
    ap.add_argument('--out', type=Path, default=Path('data'))
    ap.add_argument('--count', type=int, default=20)
    ap.add_argument('--seed', type=int, default=20261007)
    args = ap.parse_args()
    if args.count < 1:
        ap.error('--count phải >= 1')
    main(args.roots, args.out, args.count, args.seed)
