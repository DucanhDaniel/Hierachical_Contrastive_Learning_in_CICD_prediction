"""Extract reproducible review excerpts; this script never assigns assessments."""
import argparse
import json
import random
import re
from collections import defaultdict
from pathlib import Path

from project3.crawl.gold_labels import diagnostic_text

ROOT = Path('data/rule_eval/dependency-eval-20261018-v6')


def prepare():
    records={}
    with (ROOT/'run_results.jsonl').open(encoding='utf-8') as f:
        for line in f:
            r=json.loads(line)
            records[r['run_id']]=r
    samples=json.loads((ROOT/'samples.json').read_text(encoding='utf-8'))
    selected=[dict(r) for group,rows in samples.items() if not group.startswith('signal/') for r in rows]
    q3=defaultdict(list)
    for r in records.values():
        if r['labels'][0]!=r['labels'][1] and not r['non_build'][0]:
            q3['proposal/'+r['rules'][1]].append(r)
    rng=random.Random(20261018)
    for group,rows in sorted(q3.items()):
        for r in rng.sample(rows,min(30,len(rows))):
            selected.append({'group':group,'repo':r['repo'],'run_id':r['run_id'],'label':r['labels'][0], 'rule':r['rules'][1],'evidence':r['evidence'][1]})
    for r in selected:
        record=records[r['run_id']]
        evidence=r['evidence']
        matches=[]
        paths=record['paths']
        index=record['job']
        if index is not None:
            paths=[paths[index]]+[p for i,p in enumerate(paths) if i!=index]
        for path in paths:
            text=diagnostic_text(Path(path).read_text(encoding='utf-8',errors='ignore'))
            at=text.find(evidence) if evidence else -1
            if at>=0:
                matches.append((path,text[max(0,at-250):at+4200]))
                break
        if matches:
            r['deciding_path'],r['deciding_context']=matches[0]
        else:
            r['deciding_path']=r.get('path','')
            r['deciding_context']=r.get('excerpt','')
        r['seed']=20261018
    (ROOT/'review_samples.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def show(group,offset,limit,chars):
    rows=json.loads((ROOT/'review_samples.json').read_text(encoding='utf-8'))
    if group is None:
        groups=defaultdict(int)
        for r in rows:groups[r['group']]+=1
        print(json.dumps(groups,ensure_ascii=False,indent=2))
        return
    rows=[r for r in rows if r['group']==group]
    for i,r in enumerate(rows[offset:offset+limit],offset):
        text=r['deciding_context']
        # Always include the actual winning evidence plus nearby diagnostic lines.
        lines=[line.strip() for line in text.splitlines() if re.search(r'error|fail|not found|could not|couldn.t|missing|lockfile|resolve|version|timed|reset|401|403|404|429|5\d\d|PKIX|SSL|Exception|dependency',line,re.I)]
        digest='\n'.join(lines)
        print(json.dumps({'index':i,'run_id':r['run_id'],'repo':r['repo'],'label':r['label'],'evidence':r['evidence'],'context':digest[:chars]},ensure_ascii=False))


if __name__=='__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepare',action='store_true')
    p.add_argument('--group')
    p.add_argument('--offset',type=int,default=0)
    p.add_argument('--limit',type=int,default=30)
    p.add_argument('--chars',type=int,default=650)
    a=p.parse_args()
    if a.prepare:prepare()
    show(a.group,a.offset,a.limit,a.chars)
