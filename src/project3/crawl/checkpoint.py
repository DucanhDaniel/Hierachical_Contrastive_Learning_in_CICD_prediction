"""Kiểm tra checkpoint trên đĩa; phục hồi dòng JSONL cuối bị ngắt khi dừng cứng."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path


def valid_prefix(raw: bytes) -> int:
    """Chỉ cho phép dòng cuối bị cắt; lỗi ở giữa file phải báo để kiểm tra."""
    lines = raw.splitlines(keepends=True)
    offset = 0
    for i, line in enumerate(lines):
        if line.strip():
            try:
                json.loads(line)
            except (ValueError, UnicodeDecodeError):
                if i != len(lines) - 1:
                    raise ValueError(f'JSONL hỏng ở dòng {i + 1}, không tự sửa')
                return offset
        offset += len(line)
    return offset


def main(roots: list[Path], repair: bool):
    rows = []
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    for root in roots:
        if not root.exists():
            continue
        for d in sorted(root.iterdir()):
            if not d.is_dir() or not (d / 'runs.jsonl').exists():
                continue
            counts = {}
            for name in ('runs.jsonl', 'jobs.jsonl'):
                p = d / name
                if not p.exists():
                    counts[name] = 0
                    continue
                raw = p.read_bytes()
                end = valid_prefix(raw)
                if end != len(raw):
                    if not repair:
                        raise ValueError(f'{p}: dòng cuối chưa hoàn chỉnh; dùng --repair trước khi resume')
                    backup = p.with_name(f'{p.name}.interrupted.{stamp}')
                    backup.write_bytes(raw)
                    partial = p.with_name(f'{p.name}.repair.part')
                    partial.write_bytes(raw[:end])
                    partial.replace(p)
                    print(f'Phục hồi {p}; giữ bản gốc tại {backup}')
                    raw = raw[:end]
                elif repair and raw and not raw.endswith(b'\n'):
                    # Dòng cuối đủ JSON nhưng chưa ghi newline: không để lần append sau nối hai record.
                    with p.open('ab') as f:
                        f.write(b'\n')
                counts[name] = sum(bool(line.strip()) for line in raw.splitlines())
            rows.append({'root': str(root), 'repo': d.name.replace('__', '/'),
                         'runs': counts['runs.jsonl'], 'runs_with_jobs': counts['jobs.jsonl'],
                         'logs': len(list((d / 'logs').glob('*.txt'))),
                         'missing': len(list((d / 'logs').glob('*.missing'))),
                         'partial_logs': len(list((d / 'logs').glob('*.txt.part')))})
    snapshot = {'updated_utc': datetime.now(timezone.utc).isoformat(), 'repos': rows}
    out = Path('data/crawl_checkpoint.json')
    partial = out.with_suffix('.json.part')
    partial.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
    partial.replace(out)
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('roots', nargs='*', type=Path, default=[Path('data/validate'), Path('data/crawl_pr')])
    ap.add_argument('--repair', action='store_true')
    a = ap.parse_args()
    main(a.roots, a.repair)
