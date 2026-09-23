"""Descriptive snapshot; preserves planned denominator and pending comparators."""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from baseline.hest1000 import main as runner

def writecsv(path, rows, fields):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def report(run):
    run=Path(run).resolve()
    if run.parent!=runner.MAIN_ROOT.resolve():raise ValueError('report scope')
    with (runner.EVIDENCE/'SELECTED.csv').open(encoding='utf-8-sig',newline='') as f:samples=list(csv.DictReader(f))
    with (runner.EVIDENCE/'COHORT_ROLES.csv').open(encoding='utf-8-sig',newline='') as f:roles={r['sample_id']:r for r in csv.DictReader(f)}
    for sample in samples:
        sample.update(source_group=roles[sample['id']]['source_group'],historical_role=roles[sample['id']]['historical_role'])
    lookup={}
    incomplete=0
    ledger=run/'RUNS.jsonl'
    if ledger.exists():
        for line in ledger.read_text(encoding='utf-8').splitlines():
            try:r=json.loads(line)
            except json.JSONDecodeError:incomplete+=1;continue
            key=r['sample_id'],r['method']
            if key in lookup:raise ValueError('duplicate result '+str(key))
            lookup[key]=r
    rows=[];by_method=defaultdict(list)
    for sample in samples:
        for method in runner.ALL_METHODS:
            r=dict(lookup.get((sample['id'],method),dict(sample_id=sample['id'],method=method,status='not_run' if method in runner.pilot.METHODS else 'pending_adapter',total_file_bytes=None)))
            r.update(species=sample['species'],platform=sample['st_technology'],organ=sample['organ'])
            r.update(source_group=sample['source_group'],historical_role=sample['historical_role'])
            r['failure_category']=r['status']
            if r['status']=='failed':
                for stage in ['encode','decode','check']:
                    p=run/sample['id']/method/(stage+'.resource.json')
                    if p.exists():
                        failure=json.loads(p.read_text(encoding='utf-8')).get('failure')
                        if failure:r['failure_category']=stage+':'+failure;break
            rows.append(r);by_method[method].append(r)
    writecsv(run/'ALL_RUNS.csv',rows,['sample_id','method','species','platform','organ','source_group','historical_role','status','failure_category','n_spots','n_genes','n_counts','n_nonzero','total_file_bytes','full_archive_bits_per_count','full_archive_bits_per_nonzero','source_sha256','error'])
    summary=[]
    for method,records in by_method.items():
        successful=[r for r in records if r['status']=='success']
        summary.append(dict(method=method,selected=1000,success=len(successful),status_counts=json.dumps(Counter(r['status'] for r in records)),bytes_sum_success_only=sum(r['total_file_bytes'] for r in successful)))
    writecsv(run/'COVERAGE.csv',summary,['method','selected','success','status_counts','bytes_sum_success_only'])
    pairwise=[]
    for method in runner.ALL_METHODS:
        if method=='Shared':continue
        for axis in ['ALL','platform','species','organ','source_group','historical_role']:
            grouped=defaultdict(list)
            for s in samples:
                a=lookup.get((s['id'],'Shared'));b=lookup.get((s['id'],method))
                if a and b and a['status']==b['status']=='success':grouped['ALL' if axis=='ALL' else s['st_technology' if axis=='platform' else axis]].append((a,b))
            for label,pairs in grouped.items():
                x=sum(a['total_file_bytes'] for a,b in pairs);y=sum(b['total_file_bytes'] for a,b in pairs)
                pairwise.append(dict(method=method,stratum_axis=axis,stratum=label,matched_n=len(pairs),shared_bytes=x,baseline_bytes=y,saving_percent=100*(1-x/y),shared_wins=sum(a['total_file_bytes']<b['total_file_bytes'] for a,b in pairs)))
    writecsv(run/'PAIRWISE.csv',pairwise,['method','stratum_axis','stratum','matched_n','shared_bytes','baseline_bytes','saving_percent','shared_wins'])
    status=dict(selected=1000,planned_runs=11000,recorded_runs=len(lookup),success_runs=sum(r['status']=='success' for r in lookup.values()),incomplete_lines=incomplete,complete_scientific_suite=False,interpretation='descriptive mixed historical-role panel; unmatched/pending rows not defeated methods')
    (run/'SNAPSHOT.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
    print(json.dumps(status))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run');a=p.parse_args();report(a.run)
