"""Shared-free continuation runner for the seven registered HEST baselines."""
import csv, hashlib, json, os, shutil, subprocess, sys, time
from pathlib import Path
from baseline.hest1000 import pilot

ROOT=pilot.WORK
EVIDENCE=pilot.EVIDENCE
TASK=pilot.BASE/'.ai/tasks/COUNT-HEST-BASELINES-1000-004.json'
GUARD=pilot.BASE/'evidence/COUNT-HEST-SHARED-RESUME-001/guard.py'
METHODS=['BP_gene_none','BP_spot_mean','IVCSC','IVCSC_bz2','CSR_ZSTD19','CSC_ZSTD19','H5AD_GZIP4']
OUT=pilot.BASE/'evidence/COUNT-HEST-BASELINES-1000-004'
PY=pilot.SHARED_PY
ANACONDA=Path(r'C:\Users\zhang\anaconda3\python.exe')
class StopRun(RuntimeError): pass
class StageFailure(RuntimeError):
    def __init__(self, resource): self.resource=resource; super().__init__(str(resource))

def sha(p): return pilot.sha(p)
def atomic(p,v):
    t=p.with_suffix('.tmp'); t.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8'); t.replace(p)
def pins():
    files=[Path(__file__).resolve(),TASK,GUARD,EVIDENCE/'SELECTED.csv',Path(pilot.OLD),Path(__file__).resolve(),ROOT/'baseline/hest1000/pilot.py',ROOT/'baseline/hest1000/main.py',ANACONDA]
    files += [Path(p) for p in pilot.source_pins()]
    return {str(p.resolve()):sha(p) for p in sorted(set(files))}
def budget():
    if shutil.disk_usage(OUT).free<20*2**30 or pilot.bytes_used(OUT)>32*2**30: raise StopRun('disk reserve/cap')
def clean(p,case):
    p=p.resolve(); case=case.resolve()
    if case not in p.parents: raise StopRun('cleanup scope')
    if p.exists(): shutil.rmtree(p)
def stage(args,prefix,case,deadline,py=PY):
    budget(); remain=deadline-time.monotonic()
    if remain<=0: raise StopRun('wall budget')
    # Cache names must be scoped to the method folder.  Sharing case/cache_encode
    # across methods makes the second baseline fail before its encoder starts.
    cache=prefix.parent/('cache_'+prefix.name); cache.mkdir(exist_ok=False); (case/'temp').mkdir(exist_ok=True)
    env=os.environ.copy(); env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',TEMP=str(case/'temp'),TMP=str(case/'temp'),NUMBA_CACHE_DIR=str(cache),OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',NUMBA_NUM_THREADS='1')
    cmd=[str(PY),'-X','utf8','-B',str(GUARD),'--prefix',str(prefix),'--seconds',str(min(1800,remain)),'--rss',str(16*2**30),'--',str(py),'-X','utf8','-B',*map(str,args)]
    proc=subprocess.run(cmd,cwd=ROOT,env=env)
    resource=json.loads(prefix.with_suffix('.resource.json').read_text(encoding='utf-8'))
    if proc.returncode: raise StageFailure(resource)
    budget()
def samples():
    with (EVIDENCE/'SELECTED.csv').open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def run_sample(s,case,deadline,frozen):
    case.mkdir(exist_ok=False); source=Path(s['source_path']).resolve(); before=sha(source)
    rows=[]; scratch=case/'scratch'
    try:
        stage(['-m','baseline.hest1000.pilot','worker','prepare','Shared',source,scratch],case/'prepare',case,deadline)
        canonical=json.loads((scratch/'canonical.json').read_text(encoding='utf-8'))
        for method in METHODS:
            folder=case/method; folder.mkdir(); row=dict(sample_id=s['id'],method=method,status='failed',total_file_bytes=None,source_sha256=before,**{k:canonical[k] for k in ['n_spots','n_genes','n_counts','n_nonzero','canonical_dtype','source_storage_dtype']})
            try:
                if frozen!=pins() or sha(source)!=before:raise StopRun('hash drift')
                archive=folder/'archive'; decoded=folder/'decoded'
                method_py=ANACONDA if method=='H5AD_GZIP4' else PY
                stage(['-m','baseline.hest1000.pilot','worker','encode',method,scratch,archive],folder/'encode',case,deadline,py=method_py)
                stage(['-m','baseline.hest1000.pilot','worker','decode',method,archive,decoded,'--blocked','E:/Hestdata/st',scratch],folder/'decode',case,deadline,py=method_py)
                stage(['-m','baseline.hest1000.main','compare',scratch,decoded,folder/'EXACT.json'],folder/'check',case,deadline)
                exact=json.loads((folder/'EXACT.json').read_text(encoding='utf-8'))
                if not exact['checks']['all']: row.update(status='invalid_exactness',exact=exact); raise StopRun('exactness failure')
                row.update(pilot.fee_report(archive,method),status='success',exact=exact)
                row['full_archive_bits_per_count']=8*row['total_file_bytes']/row['n_counts'];row['full_archive_bits_per_nonzero']=8*row['total_file_bytes']/row['n_nonzero'] if row['n_nonzero'] else None
                clean(decoded,case)
            except StopRun: raise
            except StageFailure as ex:
                row['error']=repr(ex); row['resource_failure']=ex.resource.get('failure')
                if (folder/'EXACT.json').exists():
                    check=json.loads((folder/'EXACT.json').read_text(encoding='utf-8'))
                    if check.get('checks',{}).get('all') is not True:
                        row.update(status='invalid_exactness',exact=check,total_file_bytes=None)
                        atomic(folder/'RESULT.json',row)
                        raise StopRun('exactness failure')
                if ex.resource.get('failure') in ('timeout','rss','cleanup') or ex.resource.get('cleanup_errors'): raise StopRun('resource failure')
            except Exception as ex: row['error']=repr(ex)
            finally:
                row['source_sha256_after']=sha(source); row['code_unchanged']=frozen==pins()
                if row['source_sha256_after']!=before or not row['code_unchanged']:row.update(status='invalid_hash_drift',total_file_bytes=None)
                atomic(folder/'RESULT.json',row); rows.append(row)
                if row['status']=='invalid_hash_drift':raise StopRun('hash drift')
        clean(scratch,case); clean(case/'temp',case)
    except StopRun: raise
    except StageFailure as ex:
        if ex.resource.get('failure') in ('timeout','rss','cleanup') or ex.resource.get('cleanup_errors'):
            raise StopRun('preparation resource failure')
        # Preserve an ordinary preparation failure for every method so coverage
        # accounting never silently drops a sample.
        for m in METHODS:
            if not any(r['method']==m for r in rows):
                folder=case/m; folder.mkdir(exist_ok=True);atomic(folder/'RESULT.json',dict(sample_id=s['id'],method=m,status='preparation_failed',error=repr(ex),total_file_bytes=None))
    except Exception as ex:
        for m in METHODS:
            if not any(r['method']==m for r in rows):
                folder=case/m; folder.mkdir(exist_ok=True);atomic(folder/'RESULT.json',dict(sample_id=s['id'],method=m,status='preparation_failed',error=repr(ex),total_file_bytes=None))
    return rows
def preflight():
    if not OUT.exists(): OUT.mkdir(exist_ok=False)
    elif any(OUT.iterdir()): raise StopRun('preflight evidence directory is not empty')
    frozen=pins(); atomic(OUT/'PINS.json',frozen)
    s=next(x for x in samples() if x['id']=='INT13'); rows=run_sample(s,OUT/'preflight_INT13',time.monotonic()+3600,frozen)
    ok=len(rows)==len(METHODS) and all(r['status']=='success' for r in rows)
    atomic(OUT/'PREFLIGHT.json',{'status':'success' if ok else 'failed','sample_id':'INT13','rows':rows,'code_pins':frozen})
    if not ok: raise SystemExit('preflight failed')
def main():
    if not OUT.exists(): OUT.mkdir(exist_ok=False)
    preflight_path=OUT/'PREFLIGHT.json'; release_path=OUT/'RELEASE.json'; frozen=pins()
    if not preflight_path.exists() or not release_path.exists(): raise StopRun('independent preflight/release required')
    preflight=json.loads(preflight_path.read_text(encoding='utf-8')); release=json.loads(release_path.read_text(encoding='utf-8'))
    if preflight.get('status')!='success' or preflight.get('code_pins')!=frozen: raise StopRun('preflight pin/status gate')
    if not release.get('released') is True or release.get('code_pins')!=frozen: raise StopRun('independent release gate')
    if len(preflight.get('rows',[]))!=len(METHODS) or not all(r.get('status')=='success' and r.get('exact',{}).get('checks',{}).get('all') is True for r in preflight['rows']): raise StopRun('preflight exactness gate')
    dest=OUT/'main_v1'; dest.mkdir(exist_ok=False)
    atomic(dest/'PINS.json',frozen); atomic(dest/'CONFIG.json',{'methods':METHODS,'selected_sha256':sha(EVIDENCE/'SELECTED.csv'),'task_sha256':sha(TASK),'release_sha256':sha(release_path)})
    deadline=time.monotonic()+72*3600; allrows=[]; success=0; failed=0
    for i,s in enumerate(samples(),1):
        if time.monotonic()>=deadline: raise StopRun('wall budget')
        case=dest/s['id'];
        if case.exists():
            existing=[]
            for m in METHODS:
                try: existing.append(json.loads((case/m/'RESULT.json').read_text(encoding='utf-8')))
                except Exception: existing=[]; break
            if len(existing)==len(METHODS) and all(r.get('status')=='success' and r.get('exact',{}).get('checks',{}).get('all') is True for r in existing): continue
            raise StopRun('incomplete existing sample case; use a fresh output directory')
        rows=run_sample(s,case,deadline,frozen); allrows.extend(rows)
        success+=sum(r['status']=='success' for r in rows);failed+=sum(r['status']!='success' for r in rows)
        with (dest/'RUNS.jsonl').open('a',encoding='utf-8') as f:
            for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')
        atomic(dest/'PROGRESS.json',{'samples_completed':i,'selected':1000,'methods':METHODS,'success_rows':success,'failed_rows':failed,'last_sample':s['id']})
    atomic(dest/'RESULT.json',{'status':'completed','methods':METHODS,'success_rows':success,'failed_rows':failed,'selected':1000,'code_pins':frozen})
if __name__=='__main__':
    (preflight if len(sys.argv)>1 and sys.argv[1]=='preflight' else main)()
