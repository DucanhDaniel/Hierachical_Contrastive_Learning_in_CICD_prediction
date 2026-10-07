"""Báo cáo số liệu crawl và các tiêu chí, không tự suy đoán kết quả đọc mẫu."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import duckdb

from .gold_labels import AGG_JOB, NON_BUILD_WF
from .review_sample import LABELS


def table(headers, rows):
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')
    return '\n'.join(['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |'] +
                     ['| ' + ' | '.join(map(cell, row)) + ' |' for row in rows])


def read_csv(path):
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def main(roots, parquet, out):
    con = duckdb.connect()
    con.read_parquet(str(parquet)).create_view('commits')
    by_repo = con.sql("""SELECT repository, event, count(*), sum((outcome='fail')::int),
        round(100*avg((outcome='fail')::int),2), sum(first_failure::int),
        min(first_run_at), max(first_run_at) FROM commits GROUP BY 1,2 ORDER BY 1,2""").fetchall()
    by_label = con.sql("""SELECT cause,label_group,label,count(*),
        round(100*count(*)/sum(count(*)) OVER (),2),sum(first_failure::int)
        FROM commits WHERE outcome='fail' GROUP BY 1,2,3 ORDER BY 1,2,3""").fetchall()
    counts = dict(con.sql("SELECT label,count(*) FROM commits WHERE outcome='fail' GROUP BY 1").fetchall())
    failed = sum(counts.values())
    code = con.sql("SELECT count(*) FROM commits WHERE outcome='fail' AND cause='code'").fetchone()[0]
    coverage = []
    unknown = Counter()
    for root in roots:
        for row in read_csv(root / 'gold_labels.csv'):
            if row['non_build'].lower() == 'false' and row['gold'] == '?':
                unknown[(str(root), row['repo'], row['workflow'])] += 1
        if not root.exists():
            continue
        for d in sorted(root.iterdir()):
            if not d.is_dir() or not (d / 'runs.jsonl').exists():
                continue
            runs = {r['id']: r for r in map(json.loads, (d / 'runs.jsonl').read_text(encoding='utf-8').splitlines())
                    if r['conclusion'] == 'failure' and not NON_BUILD_WF.search(r['name'] or '')}
            jobs = {}
            if (d / 'jobs.jsonl').exists():
                jobs = {r['run_id']: r['jobs'] for r in map(json.loads, (d / 'jobs.jsonl').read_text(encoding='utf-8').splitlines())}
            no_log = no_jobs = partial = missing = 0
            for run_id in runs:
                eligible = [j for j in jobs.get(run_id, []) if j['conclusion'] == 'failure' and not AGG_JOB.search(j['name'])]
                no_jobs += run_id not in jobs
                paths = [d / 'logs' / f"{j['id']}.txt" for j in eligible]
                available = sum(p.exists() and bool(p.read_text(encoding='utf-8', errors='replace').strip()) for p in paths)
                no_log += available == 0
                partial += 0 < available < len(paths)
                missing += any((d / 'logs' / f"{j['id']}.missing").exists() for j in eligible)
            coverage.append((str(root), d.name.replace('__', '/'), len(runs), no_log, no_jobs, missing, partial,
                             round(100 * no_log / max(1, len(runs)), 2)))
    total_runs = sum(r[2] for r in coverage)
    no_log = sum(r[3] for r in coverage)
    manifest = read_csv(Path('data/label_review_manifest.csv'))
    judgments = {(r['repo'], r['run_id'], r['gold'], r['fingerprint']): r
                 for r in read_csv(Path('data/label_review_assessments.csv'))}
    reviews = []
    examples = []
    for label in LABELS:
        samples = [r for r in manifest if r['gold'] == label]
        verdicts = [judgments.get((r['repo'], r['run_id'], r['gold'], r['fingerprint']), {}).get('verdict', 'pending') for r in samples]
        ok = verdicts.count('correct')
        bad = verdicts.count('incorrect')
        unsure = verdicts.count('uncertain')
        pending = verdicts.count('pending')
        reviews.append((label, len(samples), ok, bad, unsure, pending, f'{100*ok/max(1,len(samples)):.1f}%',
                        'đạt mẫu' if len(samples) == 20 and ok >= 19 and pending == 0 else 'chưa đạt/chưa đủ'))
        for row in samples:
            judgment = judgments.get((row['repo'], row['run_id'], row['gold'], row['fingerprint']))
            if judgment and judgment['verdict'] != 'correct':
                examples.append((label, row['repo'], row['run_id'], judgment['verdict'], judgment['reason']))
    state_path = Path('data/crawl_expand_state.json')
    state = json.loads(state_path.read_text(encoding='utf-8-sig')) if state_path.exists() else {}
    errors = []
    for log in ('data/crawl_pr.log', 'data/crawl_extra.log', 'data/crawl_extra_push.log', 'data/crawl_extra_pr.log'):
        p = Path(log)
        if p.exists():
            raw = p.read_bytes()
            if raw.startswith(b'\xff\xfe'):
                # Log cũ do PowerShell ghi UTF-16; lượt resume mới có thể nối UTF-8.
                boundary = raw.rfind(b'\r\x00\n\x00') + 4
                text = raw[:boundary].decode('utf-16', errors='replace') + raw[boundary:].decode('utf-8', errors='replace')
            else:
                text = raw.decode('utf-8-sig', errors='replace')
            errors.extend(line for line in text.splitlines() if '] LỖI ' in line)
    unknown_pct = 100 * counts.get('?', 0) / max(1, failed)
    missing_pct = 100 * no_log / max(1, total_runs)
    gates = [('Commit fail cause=code', code, '>= 2000', code >= 2000)]
    gates += [(f'Commit fail {label}', counts.get(label, 0), '>= 300', counts.get(label, 0) >= 300)
              for label in ('test', 'compile', 'lint')]
    gates += [('Commit fail ?', f'{unknown_pct:.2f}%', '< 5%', unknown_pct < 5),
              ('Run fail không có log sử dụng được', f'{no_log}/{total_runs} ({missing_pct:.2f}%)', '< 5%', total_runs > 0 and missing_pct < 5)]
    now = datetime.now(timezone(timedelta(hours=7)))
    parallel_path = Path('data/crawl_extra_push_state.json')
    parallel = json.loads(parallel_path.read_text(encoding='utf-8-sig')) if parallel_path.exists() else {}
    elapsed = 'chưa có thời gian bắt đầu'
    if state.get('started'):
        end = datetime.fromisoformat(state['updated']) if state.get('status') == 'completed' else now
        elapsed = str(end - datetime.fromisoformat(state['started']))
    chunks = ['# Báo cáo crawl mở rộng dữ liệu',
              f'Cập nhật {now:%Y-%m-%d %H:%M:%S %z}. Pipeline: `{state.get("stage", "unknown")}` / `{state.get("status", "unknown")}`. Thời gian từ lúc khởi chạy: {elapsed}.',
              f'Worker mở rộng song song: `{parallel.get("stage", "chưa khởi chạy")}` / `{parallel.get("status", "chưa khởi chạy")}`; theo dõi `data/crawl_extra_push.log` hoặc `data/crawl_extra_pr.log`. Checkpoint/điều khiển: `docs/codex/crawl-control.md`.',
              f'Số liệu commit đọc trực tiếp từ `{parquet}` (mtime: {datetime.fromtimestamp(parquet.stat().st_mtime, now.tzinfo).isoformat()}). Khi crawl còn chạy, đây là ảnh chụp tạm thời; chưa phải bộ dữ liệu hoàn tất.',
              '## Repo × event', table(['repo', 'event', 'commit', 'fail', '% fail', 'fail đầu', 'từ (UTC)', 'đến (UTC)'], by_repo),
              '## Nhãn commit fail', table(['cause', 'label_group', 'label', 'commit fail', '%', 'fail đầu'], by_label),
              '## Tiêu chí số lượng và coverage', table(['chỉ số', 'thực tế', 'mục tiêu', 'kết quả'],
                  [(a,b,c,'đạt tại ảnh chụp' if d else 'chưa đạt') for a,b,c,d in gates]),
              '## Kiểm chứng mẫu thủ công',
              'Phạm vi mẫu đã lưu: ' + ', '.join(sorted({r['root'] for r in manifest})) + '. Các đánh giá thuộc đúng mẫu/fingerprint này; chưa phải kết quả kiểm chứng mẫu mới cho toàn bộ dữ liệu PR và repo mở rộng.',
              'Seed `20261007`; mỗi nhãn tối đa 20 run riêng biệt. Kết quả chỉ được công nhận khi fingerprint đoạn log trùng với đánh giá đã lưu. `uncertain` không được tính là đúng. Đây là độ phù hợp với bằng chứng log giữ lại, chưa chứng minh nguyên nhân của mọi lần fail hoặc accuracy toàn quần thể.',
              table(['nhãn', 'mẫu / 20', 'đúng', 'sai', 'chưa đủ bằng chứng', 'chưa đọc', '% đúng trên mẫu', 'kết quả'], reviews),
              table(['nhãn', 'repo', 'run', 'đánh giá', 'lý do'], examples) if examples else 'Chưa có ví dụ sai/chưa đủ bằng chứng đã ghi nhận.',
              '## Run thiếu log',
              'Mẫu số gồm mọi run failure của workflow build đã lưu, kể cả run chưa tải jobs. Run có ít nhất một log không rỗng được tính có log; `thiếu một phần` ghi riêng (PR chủ ý chỉ tải tối đa 2 job). `.missing` có thể là hết hạn hoặc tải thất bại, không thể phân biệt từ marker hiện tại.',
              table(['root', 'repo', 'run fail', 'không log', 'chưa có jobs', 'có marker missing', 'thiếu một phần', '% không log'], coverage),
              '## Nhãn ? theo repo và workflow', table(['root', 'repo', 'workflow', 'run ?'], [(*k,v) for k,v in unknown.most_common()]),
              '## Repo lỗi', '\n'.join('- ' + line for line in errors) if errors else 'Chưa ghi nhận LỖI repo trong log của lượt mở rộng; các repo chưa chạy chưa được xem là thành công.',
              '## Thay đổi luật và giới hạn',
              '- Sửa hai ký tự backspace thành `\\b` trong luật test: `369 PASSED, 1 FAILED, 0 FLAKY` giờ khớp. Giữ nguyên ưu tiên compile → lint → infra mạnh → flaky → test → dependency → infra yếu.',
              '- RAT license: `Counter(s) UNAPPROVED exceeded minimum or maximum values` → lint (Druid run 36682779402).',
              '- Japicmp: `E: There is at least one incompatibility: ...` → lint (Pinot run 35823974157); log xác nhận kiểu trả về getCrc đổi String sang long. Không bắt dòng lệnh `--error-on-binary-incompatibility` làm evidence.',
              '- Test Ant/shell: `Some tests completed with an Error` (Tomcat 31521893807), `4 tests, 3 passed, 1 failed` và `ERROR: Test execution of ozone/test.sh is FAILED` (Ozone 29421150227) → test. Loại ANSI trước khi match và xuất evidence để không mất chẩn đoán do màu console.',
              '- Lỗi tải JDK/action: `Java setup process failed due to: error code: 504` và `Failed to resolve action download info` → infra (Druid 31828775776; Kafka 31103727160).',
              '- JVM crash: `A fatal error has been detected by the Java Runtime Environment` → infra (Pinot 32173121221).',
              '- Đọc mẫu phát hiện Kafka 29031051636 và 29317284895 có flaky nhưng nguyên nhân làm job fail là `Gradle task had a timeout. ... These are partial results!`. Thêm timeout này vào infra mạnh trước flaky; không dùng kết quả test chưa đầy đủ để kết luận flaky.',
              '- Artifact đứng riêng / plugin không tồn tại: `Could not find artifact ...` và `No plugin found for prefix` → dependency khi không có dấu hiệu mạng (Druid 34426182770).',
              '- Thêm dấu hiệu mạng `Premature end of Content-Length`, SSL handshake; tránh chuyển lỗi tải file bị cắt dở thành dependency chỉ vì một mirror khác báo missing artifact (Paimon 29811570144, 29811954183).',
              '- Thêm mẫu compiler Scala/Kotlin, Gradle checkstyle/spotless, license header, revapi/japicmp compatibility; các mẫu chưa xuất hiện trong dữ liệu đang đọc chưa được xác nhận bằng log PR. Chỉ có tên task compile hoặc tên plugin compatibility chưa đủ để kết luận lỗi code.',
              '- NON_BUILD_WF thêm benchmark, PR labels, dependency review, Dependency Submission (Pulsar push chỉ có CI - Gradle Dependency Submission, không xem là build pass). Cần kiểm tra lại theo workflow thực tế khi crawl mở rộng hoàn tất.',
              '- Sửa evidence cuối file không có newline; gold_labels xuất được CSV rỗng. Công cụ review không tự đánh giá đúng/sai.',
              '## Việc còn lại',
              '- Chờ T1/T2 hoàn tất; pipeline sẽ tự chạy gán nhãn và tạo commits_all.parquet. Công cụ kết thúc sẽ cập nhật mẫu và báo cáo; mẫu mới cần đọc thủ công.',
              '- Kiểm tra các workflow nhãn ?, sửa luật dựa vào log PR/extra, đọc đủ 20 mẫu/nhãn; nếu số lượng chưa đạt thì mở rộng repo JVM theo tài liệu nhiệm vụ.',
              '- T5: người dùng trả lời "Chưa tạo lịch" ngày 2026-10-07. Không tạo Windows Task Scheduler.',
              '## Theo dõi và tiếp tục',
              '- Trạng thái pipeline: `data/crawl_expand_state.json`; PID: `data/crawl_expand.pid`. T1 ghi `data/crawl_pr.log`; T2 ghi `data/crawl_extra.log`; gán nhãn và báo cáo ghi `data/crawl_expand.log`.',
              '- Pipeline chính T1 → T2 push → T2 PR → gold_labels → commits_all.parquet; worker phụ đã xong push và chuyển sang T2 PR. Khóa theo repo ngăn ghi trùng khi pipeline chính đến T2; có bước chờ worker phụ trước khi gán nhãn. `scripts/crawl_finish.ps1` chờ T4 xong rồi xuất mẫu mới và cập nhật báo cáo; các mẫu mới không được tự động tính là đã đọc.',
              '- Nếu tiến trình bị ngắt, xác nhận tiến trình cũ đã dừng rồi chạy `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/crawl_expand.ps1`; crawler bỏ qua run/jobs/log đã lưu. Chạy thêm `scripts/crawl_finish.ps1` để cập nhật báo cáo sau khi xong.',
              '- Dùng `scripts/crawl_control.ps1 -Action Status`, `-Action Pause` hoặc `-Action Resume` để quản lý các worker; checkpoint nằm tại `data/crawl_checkpoint.json`. Không tạm dừng lượt thật trong quá trình kiểm tra tính năng.',
              '- 14 kiểm tra unittest đạt, gồm khóa giữa hai tiến trình, JSONL bị cắt và repo không có run fail/workflow; sửa lỗi đọc jobs.jsonl chưa tồn tại của Pulsar. Kiểm tra CSV root rỗng đạt; lấy mẫu hai lần cùng seed cho manifest/fingerprint giống nhau; các script PowerShell đã kiểm tra cú pháp. Resume đã chạy thật; chưa chủ động Pause.']
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n\n'.join(chunks) + '\n', encoding='utf-8')
    print(f'Đã lưu {out}: {failed} commit fail, code={code}, ?={unknown_pct:.2f}%')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('roots', nargs='+', type=Path)
    ap.add_argument('--parquet', type=Path, default=Path('data/processed/commits_all.parquet'))
    ap.add_argument('--out', type=Path, default=Path('docs/codex/bao-cao-crawl.md'))
    a = ap.parse_args()
    main(a.roots, a.parquet, a.out)
