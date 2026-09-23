"""Sequential bounded fresh-process runner. Main requires independent gate."""
import argparse,json,os,sys,time,subprocess,shutil
from pathlib import Path
import psutil
import codec
import numpy as np
import numba
from scipy import sparse
ROOT=Path(__file__).resolve().parent

def disk(p):return sum(f.stat().st_size for f in p.rglob('*') if f.is_file())
def execute(cmd,log,deadline,out):
 start=time.monotonic();peak=0;env=os.environ.copy();env.update(NUMBA_CACHE_DIR=str(out/'numba_cache'),NUMBA_NUM_THREADS='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
 with log.open('xb') as f:
  p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,env=env)
  try:
   while p.poll() is None:
    try:peak=max(peak,psutil.Process(p.pid).memory_info().rss)
    except psutil.NoSuchProcess:pass
    if peak>8*2**30 or time.monotonic()-start>600 or time.monotonic()>deadline or disk(out)>8*2**30:raise RuntimeError('budget')
    time.sleep(.2)
   if p.returncode:raise RuntimeError(f'child exit {p.returncode}: {log}')
  finally:
   if p.poll() is None:p.kill();p.wait()
 return time.monotonic()-start

def run(output):
 out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False);start=time.monotonic();deadline=start+7200;panel=json.loads((ROOT/'PANEL.json').read_text(encoding='utf8'));sources=list(ROOT.glob('*.py'))+list((ROOT/'runtime').glob('*.py'))+[ROOT/'PANEL.json',ROOT/'PROTOCOL.md',ROOT.parents[1]/'.ai/tasks/COUNT-SHARED-MDL-GROUP-001.json',Path(sys.executable)];pins={str(p):codec.io.sha(p) for p in sources};inputs={e[k]:e['file_hashes'][k] for e in panel for k in ('counts','metadata','shared')};pins.update(inputs)
 def check():
  if pins!={p:codec.io.sha(p) for p in pins}:raise ValueError('pin drift')
  if time.monotonic()>deadline or disk(out)>8*2**30:raise RuntimeError('overall budget')
 check();codec.io.save(out/'PINS.json',pins);codec.io.save(out/'ENVIRONMENT.json',dict(python=sys.version,executable=sys.executable,numpy=np.__version__,numba=numba.__version__));rows=[];base=[sys.executable,'-X','utf8','-B',str(ROOT/'codec.py')]
 try:
  for e in panel:
   x=sparse.load_npz(e['counts']);meta=Path(e['metadata']).read_bytes();cases=[('FIXED_SHARED',0,False),('GLOBAL_SHARED',1,False),('PER_GENE',x.shape[1],False)]+[('ADAPTIVE',k,flag) for k in (1,2,4,8,16,32) for flag in (False,True)]
   for arm,k,flag in cases:
    check();case=out/e['sid']/f'{arm}_K{k}_E{int(flag)}';case.mkdir(parents=True);entry=case/'entry.json';codec.io.save(entry,e);archive=case/'count.cnt';row=dict(sample_id=e['sid'],arm=arm,K=k,exceptionsflag=flag,status='failed',artifact_path=str(archive));rows.append(row);print(json.dumps(dict(stage='case',sample=e['sid'],arm=arm,K=k,exceptions=flag)),flush=True)
    if arm=='FIXED_SHARED':
     shutil.copyfile(e['shared'],archive);m,p=codec.archive(archive);row.update(total_bytes=archive.stat().st_size,archive_sha256=codec.io.sha(archive),modelblob_bytes=len(p['value_q1.bz2']),value_stream_bytes=len(p['values.rans']),components={k:len(v) for k,v in p.items()},framing_bytes=archive.stat().st_size-sum(map(len,p.values())),n_spots=x.shape[0],n_genes=x.shape[1],n_counts=x.shape[0]*x.shape[1],n_nonzero=x.nnz,encode_seconds=0)
    else:
     cmd=base+['encode','--entry',str(entry),'--arm',arm,'--k',str(k),'--archive',str(archive),'--result',str(case/'encode.json')]+(['--exceptions'] if flag else []);row['encode_seconds']=execute(cmd,case/'encode.log',deadline,out);row.update(json.loads((case/'encode.json').read_text()))
    cmd=base+['decode','--archive',str(archive),'--output',str(case/'decoded'),'--result',str(case/'decode.json')]
    for blocked in (e['counts'],e['metadata'],e['shared'],str(Path(e['counts']).parent.parent),'E:/Hestdata'):cmd+=['--block',blocked]
    row['decode_seconds']=execute(cmd,case/'decode.log',deadline,out);dec=json.loads((case/'decode.json').read_text());y=sparse.load_npz(case/'decoded/counts.npz');checks=dict(dtype=y.dtype==x.dtype,shape=y.shape==x.shape,indptr=np.array_equal(y.indptr,x.indptr),indices=np.array_equal(y.indices,x.indices),values=np.array_equal(y.data,x.data),metadata=(case/'decoded/metadata.json').read_bytes()==meta,cdf=arm=='FIXED_SHARED' or row['value_cdf_sha256']==dec['value_cdf_sha256'])
    if not all(checks.values()):raise ValueError('source comparison')
    row.update(checks=checks,status='success');check();codec.io.save(case/'RUN.json',row)
  codec.io.save(out/'RESULTS.json',dict(rows=rows,seconds=time.monotonic()-start,status='passed',new_disk_bytes=disk(out)))
 except BaseException as exc:codec.io.save(out/'FAILURE.json',dict(error=repr(exc),rows=rows,seconds=time.monotonic()-start));raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);run(p.parse_args().output)
