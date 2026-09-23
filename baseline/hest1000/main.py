"""Frozen-manifest local tranche. Pending comparators remain in each ledger."""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from baseline.hest1000 import pilot

WORK=pilot.WORK
EVIDENCE=pilot.EVIDENCE
MAIN_ROOT=Path('D:/HEST1000BenchRun/COUNT-HEST-1000-001')
ALL_METHODS=['Shared','BP_gene_none','BP_spot_mean','IVCSC','IVCSC_bz2','CSR_ZSTD19','CSC_ZSTD19','H5AD_GZIP4','CSR_BZIP2_9','Pcodec','GPress_correctness_patched']
GUARD=pilot.BASE/'evidence/COUNT-MATCHED-READY-001/run_guard.py'

class StopRun(RuntimeError): pass

def pins():
    return {**pilot.source_pins(),str(Path(__file__).resolve()):pilot.sha(__file__),str(GUARD.resolve()):pilot.sha(GUARD)}

def budget(root):
    if shutil.disk_usage(root).free<40*2**30 or pilot.bytes_used(root)>220*2**30:
        raise StopRun('main disk cap/reserve threatened')

def call(cmd, prefix, env, root, deadline):
    budget(root)
    remaining=deadline-time.monotonic()
    if remaining<=0: raise StopRun('24h tranche exhausted')
    guarded=[sys.executable,'-B',str(GUARD),'--prefix',str(prefix),'--seconds',str(min(1800,remaining)),'--rss',str(16*2**30),'--',*map(str,cmd)]
    proc=subprocess.Popen(guarded,cwd=WORK,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        while proc.poll() is None:
            budget(root)
            time.sleep(2)
        resource=json.loads(prefix.with_suffix('.resource.json').read_text(encoding='utf-8'))
        if proc.returncode!=0: raise RuntimeError('monitored stage failed: '+str(resource))
        budget(root)
    except BaseException as exc:
        # Monitor owns the worker; terminate descendants before terminating it.
        import psutil
        observed=[]
        try:
            parent=psutil.Process(proc.pid)
            children=parent.children(recursive=True)
            for q in [parent,*children]:
                try:observed.append(dict(pid=q.pid,created=q.create_time()))
                except psutil.NoSuchProcess:pass
            pilot.write(prefix.with_suffix('.parent_watchdog.json'),dict(failure=repr(exc),observed_identities=observed,reason='outer watchdog; guard finally may be interrupted'))
            for child in reversed(children):
                try: child.kill()
                except psutil.NoSuchProcess: pass
            parent.kill()
        except psutil.NoSuchProcess:
            if not prefix.with_suffix('.parent_watchdog.json').exists():
                pilot.write(prefix.with_suffix('.parent_watchdog.json'),dict(failure=repr(exc),observed_identities=observed))
        proc.wait(timeout=10)
        raise

def scratch_cleanup(path, case):
    target=path.resolve(); bound=case.resolve()
    if bound not in target.parents or target==bound: raise ValueError('cleanup scope escaped case')
    if target.exists(): shutil.rmtree(target)

def compare_worker(scratch, decoded, report):
    from scipy import sparse
    x=sparse.load_npz(Path(scratch)/'counts.npz')
    checks=pilot.compare(x,(Path(scratch)/'metadata.json').read_bytes(),decoded)
    pilot.write(report,dict(checks=checks,decoded_hashes={p.name:pilot.sha(p) for p in Path(decoded).iterdir() if p.is_file()}))
    if not checks['all']: raise ValueError('exact recovery failed')

def run(release_path):
    release=json.loads(Path(release_path).read_text(encoding='utf-8'))
    frozen=pins()
    for name in ['SELECTED.csv','COHORT_ROLES.csv']:
        if release.get(name)!=pilot.sha(EVIDENCE/name): raise ValueError('cohort hash mismatch')
    if release.get('released') is not True or release.get('code_pins')!=frozen:
        raise ValueError('reviewed frozen main release required')
    if release.get('active_methods')!=pilot.METHODS or release.get('allow_mixed_retrospective_evaluation') is not True:
        raise ValueError('eight-method tranche/mixed-role release required')
    output=MAIN_ROOT/release['run_name']
    if output.resolve().parent!=MAIN_ROOT.resolve(): raise ValueError('main output scope')
    output.mkdir(exist_ok=False); budget(MAIN_ROOT)
    pilot.write(output/'PINS.json',dict(code=frozen,release_sha256=pilot.sha(release_path),methods=ALL_METHODS,active=pilot.METHODS))
    pilot.write(output/'RUNTIME.json',pilot.runtime_info())
    with (EVIDENCE/'SELECTED.csv').open(encoding='utf-8-sig',newline='') as f: samples=list(csv.DictReader(f))
    deadline=time.monotonic()+24*3600
    env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
    for key in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMBA_NUM_THREADS']:env[key]='1'
    planned_source_bytes=sum(int(s['source_file_bytes']) for s in samples)
    pilot.write(output/'STORAGE_PLAN.json',dict(source_files_not_copied=True,selected_source_bytes=planned_source_bytes,compressed_output_estimate_is_unknown=True,hard_stop_free_gib=40,output_cap_gib=220))
    completed=0
    with (output/'INITIAL_STATUS.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['sample_id','method','status']);w.writeheader()
        for sample in samples:
            for method in ALL_METHODS:w.writerow(dict(sample_id=sample['id'],method=method,status='not_run' if method in pilot.METHODS else 'pending_adapter'))
    def record(row):
        with (output/'RUNS.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
    for s in samples:
        if time.monotonic()>=deadline:break
        budget(MAIN_ROOT)
        if frozen!=pins():raise RuntimeError('code drift')
        sid=s['id']; source=Path(s['source_path']).resolve()
        if source!=Path('E:/Hestdata/st',sid+'.h5ad').resolve():raise ValueError('source scope')
        case=output/sid;case.mkdir();scratch=case/'scratch';temp=case/'temp';temp.mkdir()
        case_env={**env,'TEMP':str(temp),'TMP':str(temp),'NUMBA_CACHE_DIR':str(case/'numba_cache')}
        before=pilot.sha(source)
        pilot.write(case/'SOURCE.json',dict(path=str(source),sha256_before=before))
        try:
            call([sys.executable,'-B','-m','baseline.hest1000.pilot','worker','prepare','Shared',source,scratch],case/'prepare',case_env,MAIN_ROOT,deadline)
            canonical=json.loads((scratch/'canonical.json').read_text(encoding='utf-8'))
            pilot.write(case/'CANONICAL.json',canonical)
            if pilot.sha(source)!=before:raise StopRun('source drift after preparation')
        except StopRun:
            raise
        except Exception as exc:
            for method in ALL_METHODS:record(dict(sample_id=sid,method=method,status='preparation_failed',total_file_bytes=None,error=repr(exc)))
            if pilot.sha(source)!=before:raise RuntimeError('source drift after failed prepare')
            completed+=1
            (output/'PROGRESS.json').write_text(json.dumps(dict(samples_completed=completed,selected=1000,active_methods=8,pending_methods=3,full_suite_complete=False)),encoding='utf-8')
            scratch_cleanup(scratch,case);scratch_cleanup(temp,case)
            continue
        for method in ALL_METHODS:
            folder=case/method;folder.mkdir()
            row=dict(sample_id=sid,method=method,status='pending_adapter',total_file_bytes=None,source_sha256=before)
            row.update({k:canonical[k] for k in ['n_spots','n_genes','n_counts','n_nonzero','canonical_dtype','source_storage_dtype']})
            if method not in pilot.METHODS:
                pilot.write(folder/'RESULT.json',row);record(row);continue
            archive=folder/'archive';decoded=folder/'decoded'
            row['status']='failed'
            try:
                if pilot.sha(source)!=before or frozen!=pins():raise StopRun('source/code drift before method')
                python=pilot.SHARED_PY if method=='Shared' else Path(sys.executable)
                enc_source=source if method=='Shared' else scratch
                enc_out=archive/'count.cnt' if method=='Shared' else archive
                if method=='Shared':archive.mkdir()
                args=['-B','-m','baseline.hest1000.pilot','worker']
                call([python,*args,'encode',method,enc_source,enc_out],folder/'encode',case_env,MAIN_ROOT,deadline)
                call([python,*args,'decode',method,enc_out,decoded,'--blocked','E:/Hestdata/st',scratch],folder/'decode',case_env,MAIN_ROOT,deadline)
                call([sys.executable,'-B','-m','baseline.hest1000.main','compare',scratch,decoded,folder/'EXACT.json'],folder/'check',case_env,MAIN_ROOT,deadline)
                exact=json.loads((folder/'EXACT.json').read_text(encoding='utf-8'))
                row.update(pilot.fee_report(archive,method));row.update(status='success',exact=exact)
                row['full_archive_bits_per_count']=8*row['total_file_bytes']/row['n_counts']
                row['full_archive_bits_per_nonzero']=8*row['total_file_bytes']/row['n_nonzero'] if row['n_nonzero'] else None
            except StopRun as exc:
                row.update(status='stopped_resource_or_hash',error=repr(exc));pilot.write(folder/'RESULT.json',row);record(row);raise
            except Exception as exc:
                row['error']=repr(exc)
                if (folder/'EXACT.json').exists():
                    check=json.loads((folder/'EXACT.json').read_text(encoding='utf-8'))
                    if not check['checks']['all']:
                        row.update(status='invalid_exactness',total_file_bytes=None,exact=check)
                        pilot.write(folder/'RESULT.json',row);record(row);raise StopRun('exactness failure; investigation required')
                if time.monotonic()>=deadline:
                    row.update(status='stopped_wall_budget',total_file_bytes=None)
                    pilot.write(folder/'RESULT.json',row);record(row);raise StopRun('24h tranche exhausted')
            row['source_sha256_after']=pilot.sha(source)
            row['code_unchanged']=frozen==pins()
            if row['source_sha256_after']!=before or not row['code_unchanged']:
                row['status']='invalid_hash_drift';row['total_file_bytes']=None
            pilot.write(folder/'RESULT.json',row);record(row)
            if row['status']=='invalid_hash_drift':raise RuntimeError('hash drift')
            if row['status']=='success':scratch_cleanup(decoded,case)
        scratch_cleanup(scratch,case);scratch_cleanup(temp,case)
        completed+=1
        (output/'PROGRESS.json').write_text(json.dumps(dict(samples_completed=completed,selected=1000,active_methods=8,pending_methods=3,full_suite_complete=False)),encoding='utf-8')
        print(json.dumps(dict(sample_id=sid,samples_completed=completed)),flush=True)
    pilot.write(output/'TRANCHE_STOP.json',dict(samples_completed=completed,selected=1000,complete_active_queue=completed==1000,full_suite_complete=False))

def main():
    p=argparse.ArgumentParser();subs=p.add_subparsers(dest='command',required=True)
    q=subs.add_parser('run');q.add_argument('--release',required=True)
    q=subs.add_parser('compare');q.add_argument('scratch');q.add_argument('decoded');q.add_argument('report')
    a=p.parse_args()
    if a.command=='run':
        try:run(a.release)
        except BaseException as exc:
            release=json.loads(Path(a.release).read_text(encoding='utf-8'))
            output=MAIN_ROOT/release['run_name']
            if output.resolve().parent==MAIN_ROOT.resolve() and output.exists() and not (output/'TRANCHE_STOP.json').exists():
                pilot.write(output/'TRANCHE_STOP.json',dict(status='stopped',error=repr(exc),full_suite_complete=False,unvisited_status='INITIAL_STATUS.csv minus RUNS.jsonl'))
            raise
    else:compare_worker(a.scratch,a.decoded,a.report)

if __name__=='__main__':main()
