"""Separate numeric HTTP 401/403 signals from broad Unauthorized/Forbidden words."""
import csv
import json
import re
from pathlib import Path

from project3.crawl.gold_labels import diagnostic_text
from project3.pipeline.rule_eval import SIGNAL_RX, iter_scope, sha


def main():
    scope=Path('data/rule_eval/scope_r1_20261018.csv')
    manifest=json.loads(scope.with_suffix('.manifest.json').read_text(encoding='utf-8'))
    wanted=set()
    for root, expected in manifest['gold_labels_csv_sha256'].items():
        p=Path(root)/'gold_labels.csv'
        if sha(p)!=expected:
            raise ValueError('CSV drift; use recomputed evaluator labels instead')
        with p.open(encoding='utf-8-sig') as f:
            wanted.update((root,r['repo'],int(r['run_id'])) for r in csv.DictReader(f) if r['non_build']=='False' and r['gold']=='infra')
    strict=re.compile(r'(?:status code[: ]{1,8}|error code[: ]{1,8}|HTTP[/\d.]{0,10}\s{1,8})(?:401|403)\b')
    broad=SIGNAL_RX['status_401_403']
    matches=[]
    total=0
    for row,run,jobs,available,missing in iter_scope(scope):
        if (row['root'],row['repo'],int(row['run_id'])) not in wanted or not available:
            continue
        total+=1
        texts=[]
        for job,p in available:
            raw=p.read_text(encoding='utf-8',errors='ignore')
            texts.append((p,diagnostic_text(raw)))
        b=any(broad.search(text) for _,text in texts)
        s=any(strict.search(text) for _,text in texts)
        if b:
            matches.append({'repo':row['repo'],'run_id':int(row['run_id']),'numeric_http':s,'paths':[str(p) for p,text in texts]})
    output={'scope_sha256':sha(scope),'baseline_source':'Frozen CSV verified by SHA256; deduplicated scope, non-aggregate failed jobs.',
            'infra_runs_with_logs':total,'broad_status_or_words':len(matches),'numeric_http_401_403':sum(r['numeric_http'] for r in matches),
            'words_only_without_numeric_http':sum(not r['numeric_http'] for r in matches),'strict_regex':strict.pattern,'runs':matches}
    Path('data/rule_eval/dependency-eval-20261018-v6/http_status_stats.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in output.items() if k!='runs'}))


if __name__=='__main__':
    main()
