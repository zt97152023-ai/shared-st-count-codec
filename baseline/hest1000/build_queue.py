"""Freeze full selected sample-method denominator before result inspection."""
import csv
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'baseline/evidence/COUNT-HEST-1000-001'

def main():
    task=json.loads((ROOT/'baseline/.ai/tasks/COUNT-HEST-1000-001.json').read_text(encoding='utf-8-sig'))
    with (OUT/'SELECTED.csv').open(encoding='utf-8-sig',newline='') as f: samples=list(csv.DictReader(f))
    ready={'Shared','BP_gene_none','BP_spot_mean','IVCSC','IVCSC_bz2','CSR_ZSTD19','CSC_ZSTD19','H5AD_GZIP4'}
    with (OUT/'QUEUE.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['sample_id','method','status','reason']);w.writeheader()
        for sample in samples:
            for method in task['baselines']:
                w.writerow(dict(sample_id=sample['id'],method=method,status='queued_gate_closed' if method in ready else 'pending_adapter',reason='vertical_slice_review_pending' if method in ready else 'no_new_cohort_accepted_adapter_yet'))
    summary={'samples':len(samples),'methods':len(task['baselines']),'planned_runs':len(samples)*len(task['baselines']),'local_queue_runs':len(samples)*len(ready),'pending_adapter_runs':len(samples)*(len(task['baselines'])-len(ready)),'performed_runs':0,'full_suite_complete':False}
    with (OUT/'QUEUE.json').open('x',encoding='utf-8') as f:json.dump(summary,f,indent=2)
    print(json.dumps(summary))

if __name__=='__main__':main()
