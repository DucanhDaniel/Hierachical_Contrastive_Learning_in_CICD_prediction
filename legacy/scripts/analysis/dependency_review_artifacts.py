"""Build the local review report and XLSX; no human labels or datasets are edited."""
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

EVAL = Path("data/rule_eval/dependency-eval-20261018-v6")
PROPOSED = Path("configs/label_rules_dependency_proposed.json")
REVIEW = Path("data/human_labels/codex_review_dependency_2026-10-18.jsonl")


def column(n):
    result = ""
    while n:
        n, k = divmod(n-1,26)
        result = chr(65+k)+result
    return result


def cell(ref, value, style=0):
    if isinstance(value, (int,float)):
        return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value or ""))[:32000]
    return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(value)}</t></is></c>'


def workbook(path, sheets):
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    relns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    with ZipFile(path,"w",ZIP_DEFLATED) as z:
        types = ['<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>','<Default Extension="xml" ContentType="application/xml"/>','<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>','<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
        for i in range(1,len(sheets)+1):
            types.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        z.writestr("[Content_Types].xml",'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'+''.join(types)+'</Types>')
        z.writestr("_rels/.rels",'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="'+relns+'/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml",f'<workbook xmlns="{ns}" xmlns:r="{relns}"><sheets>'+''.join(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>' for i,(name,_,_) in enumerate(sheets,1))+'</sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i}" Type="{relns}/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(sheets)+1))+f'<Relationship Id="styles" Type="{relns}/styles" Target="styles.xml"/></Relationships>')
        z.writestr("xl/styles.xml",f'<styleSheet xmlns="{ns}"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF17365D"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFF2CC"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="3"><xf fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf><xf fontId="1" fillId="2" borderId="0" xfId="0" applyFill="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf><xf fontId="0" fillId="3" borderId="0" xfId="0" applyFill="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf></cellXfs></styleSheet>')
        for i,(name, rows, human_col) in enumerate(sheets,1):
            xml = f'<worksheet xmlns="{ns}"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>'
            for k in range(1,len(rows[0])+1):
                width = 20 if k<5 else 45
                xml += f'<col min="{k}" max="{k}" width="{width}" customWidth="1"/>'
            xml += '</cols><sheetData>'
            for r,row in enumerate(rows,1):
                xml += f'<row r="{r}" ht="{30 if r==1 else 80}" customHeight="1">'
                for c,value in enumerate(row,1):
                    xml += cell(f"{column(c)}{r}",value,1 if r==1 else (2 if c==human_col else 0))
                xml += '</row>'
            xml += f'</sheetData><autoFilter ref="A1:{column(len(rows[0]))}{len(rows)}"/>'
            if human_col and len(rows)>1:
                col=column(human_col)
                xml += f'<dataValidations count="1"><dataValidation type="list" allowBlank="1" sqref="{col}2:{col}{len(rows)}"><formula1>"dependency,infra,buildconfig,compile,lint,test,flaky,non_build,unclear"</formula1></dataValidation></dataValidations>'
            z.writestr(f"xl/worksheets/sheet{i}.xml",xml+'</worksheet>')


def main():
    summary=json.loads((EVAL/'summary.json').read_text(encoding='utf-8'))
    proposal=json.loads(PROPOSED.read_text(encoding='utf-8'))
    examples=json.loads((EVAL/'rule_examples.json').read_text(encoding='utf-8'))
    conflicts=json.loads((EVAL/'human_conflicts.json').read_text(encoding='utf-8'))
    clusters=json.loads((EVAL/'clusters.json').read_text(encoding='utf-8'))
    reviews=[json.loads(x) for x in REVIEW.read_text(encoding='utf-8').splitlines()] if REVIEW.exists() else []
    review_groups=defaultdict(Counter)
    for r in reviews:
        review_groups[r['group']][r['assessment']]+=1
    results={}
    for line in (EVAL/'run_results.jsonl').open(encoding='utf-8'):
        r=json.loads(line)
        results[r['run_id']]=r
    # Preserve the exact semantic input evaluated before adding reporting metadata.
    archived=EVAL/'proposal.input.json'
    if not archived.exists():
        archived.write_bytes(PROPOSED.read_bytes())
    for rule in proposal['rules']:
        key=rule['id']
        rule['matches_unlabeled']=summary['rule_unknown_hits'].get(key,0)
        rule['matches_all_build_runs']=summary['rule_hits'].get(key,0)
        rule['effective_changes']=sum(not r['non_build'][0] and r['labels'][0]!=r['labels'][2] and r['rules'][2]==key for r in results.values())
        rule['conflicts_in_human_sample']=[{'run_id':r['run_id'],'source':r['source'],'label':r['label'],'introduced':r['introduced']} for r in conflicts if results[r['run_id']]['rules'][2]==key and r['full']!=r['label']]
        rule['note'] = rule['note'].split(' Match counts are raw regex hits')[0] + ' Match counts are raw regex hits before guards; effective_changes measures final labels.'
        c=review_groups.get('proposal/'+key)
        if c:
            rule['codex_review']={'phu_hop':c['phu_hop'],'khong_phu_hop':c['khong_phu_hop'],'chua_ro':c['chua_ro'],'not_human_precision':True}
        if key=='Q3-missing-class-pair':
            rule['note']+=' Needs explicit human review: missing own-project class may be packaging rather than dependency conflict.'
    PROPOSED.write_text(json.dumps(proposal,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    manifest=json.loads((EVAL/'manifest.json').read_text(encoding='utf-8'))
    manifest['proposal_input_path']='proposal.input.json'
    manifest['proposal_report_sha256']=hashlib.sha256(PROPOSED.read_bytes()).hexdigest()
    manifest['proposal_report_note']='The proposed config adds measured counts and conflict notes after evaluation; exact evaluated rules are archived in proposal.input.json.'
    (EVAL/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    approval=[['Quy tắc','Nhãn đề xuất (tầng 2)','Nhãn người chọn','Run khớp regex','Run ? khớp','Run thực đổi nhãn','Lớp / điều kiện','Regex','Log mẫu (2–3 dòng)','Nguồn log mẫu','Ghi chú','Xung đột nhãn người','Rà soát Codex (không phải precision)']]
    exrows=[['Quy tắc','Repo','Run ID','Nhãn hiện hành','Log','Trích đoạn']]
    for r in proposal['rules']:
        ex=examples.get(r['id'],[])[:3]
        logs=[]
        for e in ex:
            lines=[line for line in e['excerpt'].splitlines() if re.search(r'ERROR|error|Exception|Could not|incompatible|not found|version|failed|ERR_PNPM',line)]
            logs.append('\n'.join(lines[:3]) or e['excerpt'][:350])
            exrows.append([r['id'],e['repo'],str(e['run_id']),e['label'],e['path'],e['excerpt']])
        conflict_text='\n'.join(f"{c['run_id']}: {c['label']} ({c['source']}), introduced={c['introduced']}" for c in r['conflicts_in_human_sample'])
        approval.append([r['id'],r['label'],'',r['matches_all_build_runs'],r['matches_unlabeled'],r['effective_changes'],r['layer']+' / '+r.get('guard','none'),r['regex'],'\n---\n'.join(logs) or '[Chưa có log khớp trong phạm vi]', '\n'.join(e['path'] for e in ex),r['note'],conflict_text,json.dumps(r.get('codex_review',{}),ensure_ascii=False)])
    notes=[['Mục','Nội dung'],['Trạng thái','Đề xuất của Codex; chưa tích hợp. Cột C của sheet Quy tac để người duyệt chọn; trùng nhãn đề xuất là đồng ý.'],['Phạm vi',f"{summary['runs']} run; cố định scope_r1_20261018.csv; số commit chỉ là ước tính trên run trong scope."],['Tỉ lệ rà soát','Không phải precision kiểm chứng, không phải nhãn người.'],['Q2','401/403 giữ infra/network. Không tạo auth.'],['Q4','Artifact descriptor không rõ nguyên nhân giữ ?.'],['Số run','Run khớp regex chưa xét guard và ưu tiên; Run thực đổi nhãn là thay đổi cuối cùng.'],['Human conflicts',f"{summary['new_human_conflicts']} bản ghi xung đột mới; xem human_conflicts.json, phân biệt thay đổi chính sách Q1/Q3."],['Q3 giới hạn',f"{summary['q3_other_job_limit']} run có tín hiệu Q3 ở job khác job quyết định; giữ nguyên nhãn."],['Hồi quy',f"parity_errors={summary['parity_errors']}; baseline + Q3-only + full được đối chiếu riêng."]]
    assessed=[]
    by_rule={r['id']:r for r in proposal['rules']}
    for c in clusters:
        outcomes=[results[int(e['run_id'])] for e in c['examples']]
        matched=sorted({r['rules'][2] for r in outcomes if r['rules'][2] in by_rule})
        assessed.append({**c,'sample_labels_full':[r['labels'][2] for r in outcomes],
                         'candidate_rules':matched,'candidate_regexes':[by_rule[k]['regex'] for k in matched],
                         'note':'Counts describe the signal cluster, not final changes. Sample labels are evaluator proposals, not human labels. Unchanged ? needs more causal evidence.'})
    (EVAL/'cluster_assessment.json').write_text(json.dumps(assessed,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    unresolved=[['Nhóm','Chữ ký','Run chứa tín hiệu','Nhãn mẫu theo đề xuất','Quy tắc ứng viên','Regex ứng viên','Log mẫu','Ghi chú']]
    for c in assessed[:100]:
        unresolved.append([c['signal'],c['signature'],c['count'],', '.join(c['sample_labels_full']),', '.join(c['candidate_rules']) or 'Giữ ? / cần thêm bằng chứng','\n'.join(c['candidate_regexes']),'\n'.join(e['path']+'\n'+e['excerpt'][:600] for e in c['examples']),c['note']])
    review_rows=[['Nhóm','Repo','Run ID','Nhận định Codex','Lý do','Log','Bằng chứng']]
    review_rows.extend([r['group'],r['repo'],str(r['run_id']),r['assessment'],r['reason'],r['log_path'],r['evidence']] for r in reviews)
    workbook(Path('docs/duyet-quy-tac-dependency-2026-10-18.xlsx'), [('Quy tac',approval,3),('Log mau',exrows,None),('Cum chua ro',unresolved,None),('Ra soat Codex',review_rows,None),('Huong dan',notes,None)])
    lines=['# Rà soát dependency — 18/10/2026','', '**Trạng thái: đề xuất chờ người duyệt; chưa tích hợp quy tắc và chưa relabel/export dataset.**','',
           f"Phạm vi cố định: {summary['runs']:,} run; phiên bản `2026-10-15-buildconfig-doc`. Seed `{summary['seed']}`. Bộ chạy chỉ ghi vào `{EVAL}`. Manifest và danh sách log nằm trong thư mục này.", '',
           '## Cách đo','', 'Ba cấu hình: bộ hiện hành (0), hiện hành + Q3 (1), bộ đề xuất đầy đủ (2). Bộ truy vết được so cả nhãn và bằng chứng với `gold_label` gốc trên từng run có log. Job fail tổng hợp được loại như bộ hiện hành. Không ghép nguyên nhân giữa các job. Các nhận định Codex là ghi chú rà soát; không phải nhãn người hay precision kiểm chứng.', '',
           f"Thời gian chạy: {summary['elapsed_seconds']:.1f} giây. Sai khác truy vết so bộ gốc: **{summary['parity_errors']}**. Run có tín hiệu Q3 ở job khác job quyết định: **{summary['q3_other_job_limit']}**, được giữ nguyên nhãn.", '',
           '## Phân bố nhãn và chuyển nhãn','', '| Nhãn | Hiện hành | Chỉ Q3 | Đầy đủ |','|---|---:|---:|---:|']
    labs=sorted({k.split(':',1)[1] for k in summary['labels']})
    for lab in labs:
        lines.append('| '+lab+' | '+' | '.join(str(summary['labels'].get(f'{i}:{lab}',0)) for i in range(3))+' |')
    slow=summary['slowest'][0]
    lines+=['',f"Run chậm nhất: `{slow[2]}` / `{slow[1]}` — **{slow[0]:.2f} giây** (gồm đọc log, phân loại và đối chiếu với hàm gốc; không phải thời gian riêng của một regex). Danh sách 20 run chậm nằm trong `summary.json`."]
    added_infra=Counter(str(r['leaves'][2]) for r in results.values() if not r['non_build'][0] and r['labels'][0]=='?' and r['labels'][2]=='infra')
    lines+=['',f"Trong các run mới từ ? sang infra, subtype hiện hành ánh xạ {added_infra['network']} run vào network và để trống {added_infra['None']} run. Không tự gán lá network bằng trường leaf_proposed."]
    lines+=['', 'Mẫu số `?` sau khử trùng là **19.630 run duy nhất**, khác 19.632 dòng ban đầu: hai run apache/ozone `29313822431` và `29246957748` mỗi run xuất hiện hai lần trong CSV/jobs. Chi tiết ở `scope_dedup_note.json`; không phải hai run đã được quy tắc mới giải quyết.', '', 'Thống kê tín hiệu dưới đây dùng `SIGNALS` trong bộ chạy (một số mẫu chặt hơn hoặc bổ sung so với script thống kê ban đầu), không xem số hợp các tín hiệu là bản sao y hệt mẫu rộng ban đầu.', '', '| Tín hiệu | ? | dependency | infra |','|---|---:|---:|---:|']
    for signal in ('resolve_summary','artifact_descriptor','transfer','enforcer','jdk_version','gradle_conflict','plugin_resolve','lockfile','runtime_linkage','status_401_403','js_deps'):
        lines.append('| '+signal+' | '+' | '.join(str(summary['signal_counts'].get(f'{lab}:{signal}',0)) for lab in ('?','dependency','infra'))+' |')
    http_path=EVAL/'http_status_stats.json'
    if http_path.exists():
        http=json.loads(http_path.read_text(encoding='utf-8'))
        lines+=['',f"Nhóm infra: mẫu rộng có {http['broad_status_or_words']} run chứa mã hoặc chữ Unauthorized/Forbidden; regex mã HTTP 401/403 tường minh chỉ khớp **{http['numeric_http_401_403']}** run, {http['words_only_without_numeric_http']} run còn lại chỉ khớp chữ. `Forbidden method invocation` là ví dụ không phải HTTP. Đây là tín hiệu xuất hiện trong log, chưa phải kết luận mã đó gây fail. Xem `http_status_stats.json`."]
    lines+=['','| So sánh | Cũ → mới | Run |','|---|---|---:|']
    for key,n in summary['run_matrix'].items():
        comp,a,b=key.split('|')
        if a!=b:lines.append(f'| {comp} | {a} → {b} | {n} |')
    changed=list(csv.DictReader((EVAL/'run_changes.csv').open(encoding='utf-8-sig')))
    for old in ('compile','test','?'):
        chosen=[r for r in changed if r['comparison']=='baseline_to_q3' and r['old']==old and r['new']=='dependency'][:10]
        lines+=['',f'### Ví dụ Q3: {old} → dependency ({len(chosen)} ví dụ có trong phạm vi)','', '| Repo | Run ID | Bằng chứng mới | Log |','|---|---|---|---|']
        for r in chosen:
            paths=results[int(r['run_id'])]['paths']
            evidence=r['new_evidence'].replace('|','/').replace('`','')[:180]
            lines.append(f"| {r['repo']} | {r['run_id']} | {evidence} | {'; '.join(paths)} |")
    lines+=['', 'Chi tiết tầng 2 và lá tầng 3: `summary.json`, `run_changes.csv`. Chuyển nhãn commit: `commit_changes.csv`; đây là **ước tính** theo `(repo, sequence, head_sha)` chỉ từ run fail có trong scope, chưa phải bản xuất dataset đầy đủ. Không dùng các số run này để suy thẳng tỷ lệ commit hoặc đối chiếu trực tiếp với 375 job trong paper.', '', '## Rà soát mẫu Codex','', '| Nhóm | Phù hợp | Không phù hợp | Chưa rõ | Tổng đã đọc | Phù hợp / mẫu đã rõ |','|---|---:|---:|---:|---:|---:|']
    for group,c in sorted(review_groups.items()):
        clear=c['phu_hop']+c['khong_phu_hop']
        ratio=f"{c['phu_hop']}/{clear} ({100*c['phu_hop']/clear:.1f}%)" if clear else 'Chưa đủ bằng chứng'
        lines.append(f"| {group} | {c['phu_hop']} | {c['khong_phu_hop']} | {c['chua_ro']} | {sum(c.values())} | {ratio} |")
    lines+=['', f'Ghi chú từng mẫu: `{REVIEW}`. Quần thể từng nhóm và mẫu seed cố định: `sample_population.json`, `samples.json`; đoạn log của job quyết định và mẫu Q3 có trong `review_samples.json`, trích bằng `scripts/analysis/dependency_review_samples.py`. “Chưa rõ” tách riêng; không coi là đúng hoặc sai. Các nhóm infra/resolve và infra/401 có thể chồng lặp. Không cộng các tầng để suy precision chung.', '',
            'Đã rà soát 342 lượt mẫu: 243 mẫu baseline + 99 mẫu Q3, có thể trùng run giữa các nhóm. Có 280 lượt phù hợp và 62 lượt chưa rõ; không có đủ cơ sở để xác nhận các lượt chưa rõ là đúng hoặc sai. Fallback 71 chỉ có 6 run trong quần thể, fallback 75 có 27 nên lấy toàn bộ. Nhóm Q3 target/linkage chỉ có một trường hợp mỗi nhóm, không đủ để suy chất lượng ngoài scope.', '',
            'Điểm cần người duyệt chú ý: cả 30 mẫu yarn fallback 74 và 27 mẫu pnpm fallback 75 chỉ thấy summary/exit code, chưa đủ loại trừ mạng hoặc cấu hình; không dùng chúng để công bố precision cao. Ba trường hợp Gradle version rỗng và một artifact bị ràng buộc repo cũng cần phân biệt buildconfig/quyền truy cập với dependency. Một mẫu missing-class của chính GregTech chưa chứng minh xung đột thư viện.', '',
            '## Bộ quy tắc đề xuất','', '| ID | Lớp | Nhãn | Regex khớp run ? | Run thực đổi nhãn |','|---|---|---|---:|---:|']
    for r in proposal['rules']:
        lines.append(f"| {r['id']} | {r['layer']} | {r['label']} | {r['matches_unlabeled']} | {r['effective_changes']} |")
    lines+=['', 'Regex, guard, số khớp và tối đa ba log mẫu mỗi quy tắc nằm trong `configs/label_rules_dependency_proposed.json`, `rule_examples.json` và bảng XLSX. Số regex khớp là trước guard/ưu tiên; số thực đổi nhãn là quyết định cuối cùng. Quy tắc chưa có log khớp chưa được xác nhận bằng dữ liệu scope này.', '',
            'Q1: đổi bốn fallback 34/36/44/45; 36 và 44 bỏ tên artifact. Quy tắc mới chỉ xét enforcer báo lỗi, không xét `passed` hay tên plugin đơn thuần. Đã loại ứng viên `has been banned from the build`: Maven có thể chỉ đang bỏ qua module do lỗi trước đó, không phải banned dependency. Q3: bytecode/target JDK, lỗi liên kết trong ngữ cảnh thất bại, xung đột version/JVM Gradle. Không thêm ClassNotFoundException hay NoClassDefFoundError tổng quát: chỉ xét cặp NoClassDefFoundError → ClassNotFoundException cùng lớp, nguyên nhân cuối gần BUILD FAILED; static initialization bị loại. Các dạng còn lại giữ ? khi chưa chứng minh nguyên nhân.', '',
            'Q2 giữ 401/403 trong NETWORK. Lỗi GET/HEAD chỉ đề xuất infra khi ngữ cảnh khớp NETWORK. Q4 giữ `Failed to read artifact descriptor` không rõ nguyên nhân là ?. Plugin thiếu chỉ đề xuất khi có ngữ cảnh không tồn tại và không có NETWORK. `No matching variant` không được tự động coi là thiếu artifact.', '',
            '## Các cụm chưa gán nhãn','', '| Tín hiệu | Chữ ký | Run |','|---|---|---:|']
    for c in clusters[:35]:
        lines.append(f"| {c['signal']} | {c['signature'].replace('|','/').replace('`','')[:180]} | {c['count']} |")
    lines+=['', 'Toàn bộ cụm và tối đa ba log mẫu/cụm được lưu ở `clusters.json`; `cluster_assessment.json` nối từng cụm với nhãn mẫu theo bộ đề xuất và regex ứng viên. Số run của cụm là số chứa tín hiệu, không suy từ ba mẫu thành số run đổi nhãn. Một run có thể thuộc nhiều cụm tín hiệu. Tên dependency, lockfile, enforcer hoặc ngoại lệ đơn thuần chưa chứng minh nguyên nhân làm fail.', '',
            'Các cụm đáng chú ý còn giữ ?: 109 thông báo plugin ru.vyarus.pom bị rút gọn không có mã mạng hoặc bằng chứng artifact thiếu; 50 thông báo detekt test-fixtures không có capability/variant phù hợp (không tự coi là lệch JVM); thông báo trợ giúp `No matching variant errors are explained` và Yarn hardened-mode/lockfile chỉ là mô tả, không phải nguyên nhân. Artifact descriptor của Maven extension thiếu cause tiếp tục giữ ? theo Q4. Cặp missing-class đủ guard vẫn cần người duyệt: thiếu class của chính project có thể là lỗi đóng gói, chưa chứng minh xung đột thư viện.', '',
            '## Nhãn người, giới hạn và kiểm tra','',f"Có {summary['human_conflict_records']} bản ghi đối chiếu không khớp ít nhất một cấu hình; **{summary['new_human_conflicts']}** bản ghi xung đột mới so baseline. Xem `human_conflicts.json`, gồm nguồn và nhãn từng cấu hình. Đọc labels/adjudication theo dòng cuối và ưu tiên adjudication; blind3 giữ lá tầng 3; round3/4 đối chiếu bằng thành viên cụm, chỉ để báo xung đột, không tích hợp rule các vòng này.", '',
            'Hàm subtype hiện hành có thể chưa nhận HTTP 401/403 từ dòng bằng chứng, và timeout có thể vào lá crash trước network. Báo lá thực tế theo code hiện hành; `leaf_proposed` không ghi đè kết quả subtype. Cần người duyệt riêng thay đổi subtype nếu muốn thống nhất toàn bộ lỗi tải vào network.', '',
            'CSV khác manifest được cảnh báo; nhãn baseline luôn tính lại từ log. `csv_drift.json` ghi khác biệt theo run. `missing_logs.json` ghi log thiếu, không suy nguyên nhân từ file không tồn tại. Manifest hash danh sách đường dẫn log không chứng minh nội dung file bất biến; cần giữ snapshot log khi tái lập.', '',
            'Kiểm tra bộ chạy: `python -B -m unittest discover -s tests -p test_rule_eval.py -v`. Test chặn mở file để ghi ngoài output và kiểm tra quy tắc chọn job/giới hạn Q3. Các test ranh giới mới của gold_labels chỉ thêm sau duyệt.', '',
            'Chạy lại vào thư mục **mới**: `python -B -m project3.pipeline.rule_eval --proposed configs/label_rules_dependency_proposed.json --out data/rule_eval/dependency-rerun-20261018`. Bảng cần người duyệt: `docs/duyet-quy-tac-dependency-2026-10-18.xlsx` (cột Nhãn người chọn để trống). Sau duyệt mới tích hợp, đổi RULE_VERSION, sao lưu rồi relabel/export.']
    lines+=['', '### Xung đột mới theo nguồn và quy tắc','', '| Nguồn | Quy tắc | Bản ghi xung đột mới |','|---|---|---:|']
    new_conflicts=Counter((r['source'],results[r['run_id']]['rules'][2]) for r in conflicts if r['introduced'])
    for (source,rule),n in sorted(new_conflicts.items()):
        lines.append(f'| {source} | {rule} | {n} |')
    lines+=['', 'Thay đổi do Q1/Q3 có thể trái nhãn người theo chính sách cũ; đây là trường hợp phải duyệt lại theo chính sách mới, không tự coi mọi xung đột là quy tắc sai. Một run có thể có nhiều nguồn nhãn tham chiếu.', '',
            'Bộ đề xuất đúng lúc chạy được lưu nguyên ở `proposal.input.json`; file JSON bàn giao chỉ bổ sung số đếm và xung đột sau đánh giá. Hai hash được phân biệt trong manifest. Các lượt thử chưa hoàn tất ở thư mục không có manifest completed không được dùng làm kết quả.']
    Path('docs/codex/ra-soat-dependency-2026-10-18.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
