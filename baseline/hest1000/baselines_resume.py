"""Resume COUNT-HEST-BASELINES-1000-004 without retrying terminal cases."""
import json, os, time
from pathlib import Path
from baseline.hest1000 import baselines_runner as r

DEST = Path(os.environ.get('COUNT_BASELINE_DEST', str(r.OUT / 'main_v1')))

def terminal_rows(case):
    rows=[]
    for m in r.METHODS:
        p=case/m/'RESULT.json'
        if not p.exists(): return None
        rows.append(json.loads(p.read_text(encoding='utf-8')))
    return rows

def finish_partial(sample, case, frozen, deadline):
    source=Path(sample['source_path']).resolve(); before=r.sha(source)
    scratch=case/'scratch'; canonical=json.loads((scratch/'canonical.json').read_text(encoding='utf-8'))
    rows=[]
    for method in r.METHODS:
        folder=case/method; result=folder/'RESULT.json'
        if result.exists(): rows.append(json.loads(result.read_text(encoding='utf-8'))); continue
        folder.mkdir(exist_ok=True)
        row=dict(sample_id=sample['id'],method=method,status='failed',total_file_bytes=None,source_sha256=before,**{k:canonical[k] for k in ['n_spots','n_genes','n_counts','n_nonzero','canonical_dtype','source_storage_dtype']})
        try:
            if frozen!=r.pins() or r.sha(source)!=before: raise r.StopRun('hash drift')
            archive=folder/'archive'; decoded=folder/'decoded'; method_py=r.ANACONDA if method=='H5AD_GZIP4' else r.PY
            # If an interrupted stage already left both archive and decoded
            # objects, validate them directly instead of retrying the codec.
            reusable = archive.exists() and decoded.exists() and (decoded/'metadata.json').exists()
            if not reusable:
                r.stage(['-m','baseline.hest1000.pilot','worker','encode',method,scratch,archive],folder/'encode',case,deadline,py=method_py)
                r.stage(['-m','baseline.hest1000.pilot','worker','decode',method,archive,decoded,'--blocked','E:/Hestdata/st',scratch],folder/'decode',case,deadline,py=method_py)
            r.stage(['-m','baseline.hest1000.main','compare',scratch,decoded,folder/'EXACT.json'],folder/'check',case,deadline)
            exact=json.loads((folder/'EXACT.json').read_text(encoding='utf-8'))
            if not exact['checks']['all']: row.update(status='invalid_exactness',exact=exact); raise r.StopRun('exactness failure')
            row.update(r.pilot.fee_report(archive,method),status='success',exact=exact)
            row['full_archive_bits_per_count']=8*row['total_file_bytes']/row['n_counts']; row['full_archive_bits_per_nonzero']=8*row['total_file_bytes']/row['n_nonzero'] if row['n_nonzero'] else None
            r.clean(decoded,case)
        except r.StopRun: raise
        except r.StageFailure as ex:
            row['error']=repr(ex); row['resource_failure']=ex.resource.get('failure')
            if ex.resource.get('failure') in ('timeout','rss','cleanup') or ex.resource.get('cleanup_errors'): raise r.StopRun('resource failure')
        except Exception as ex: row['error']=repr(ex)
        finally:
            row['source_sha256_after']=r.sha(source); row['code_unchanged']=frozen==r.pins()
            if row['source_sha256_after']!=before or not row['code_unchanged']: row.update(status='invalid_hash_drift',total_file_bytes=None)
            r.atomic(result,row); rows.append(row)
    return rows

def main():
    if not DEST.exists(): raise RuntimeError('main_v1 does not exist')
    # Rebind the resource budget to the destination volume for a resumed run.
    r.OUT = DEST.parent
    frozen=json.loads((DEST/'PINS.json').read_text(encoding='utf-8'))
    if frozen != r.pins(): raise RuntimeError('code pin drift')
    sample_list=r.samples(); deadline=time.monotonic()+72*3600
    success=failed=completed=0
    runs=DEST/'RUNS.jsonl'
    for i,s in enumerate(sample_list,1):
        if time.monotonic()>=deadline: raise RuntimeError('wall budget')
        case=DEST/s['id']; existing=terminal_rows(case) if case.exists() else None
        if existing is None and case.exists():
            prior_methods={m for m in r.METHODS if (case/m/'RESULT.json').exists()}
            rows=finish_partial(s,case,frozen,deadline)
            if len(rows)!=len(r.METHODS): raise RuntimeError('partial case did not reach terminal rows')
            with runs.open('a',encoding='utf-8') as f:
                for row in rows:
                    if row['method'] not in prior_methods: f.write(json.dumps(row,ensure_ascii=False)+'\n')
        elif existing is None:
            rows=r.run_sample(s,case,deadline,frozen)
            with runs.open('a',encoding='utf-8') as f:
                for row in rows: f.write(json.dumps(row,ensure_ascii=False)+'\n')
        else:
            rows=existing
        completed += 1
        success += sum(x.get('status')=='success' for x in rows)
        failed += sum(x.get('status')!='success' for x in rows)
        r.atomic(DEST/'PROGRESS.json',{'samples_completed':completed,'selected':1000,'methods':r.METHODS,'success_rows':success,'failed_rows':failed,'last_sample':s['id'],'resume':True})
    r.atomic(DEST/'RESULT.json',{'status':'completed','methods':r.METHODS,'success_rows':success,'failed_rows':failed,'selected':1000,'code_pins':frozen,'resume':True})

if __name__=='__main__': main()
