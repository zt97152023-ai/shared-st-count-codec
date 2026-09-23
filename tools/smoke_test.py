"""Tiny synthetic archive round trips from copied source in separate processes."""
from pathlib import Path
import os,json,subprocess,sys,time
import numpy as np
import h5py
import argparse
a=argparse.ArgumentParser();a.add_argument('--output',required=True);args=a.parse_args()
B=Path(__file__).resolve().parents[1];T=Path(args.output).resolve();T.mkdir(parents=True,exist_ok=False);P=T
x=np.array([[0,0,0,0,0],[1,1,1,1,0],[0,2,65,257,0],[2**32-1,0,3,4,0],[0,1,0,16,0],[8,0,0,0,0],[3,4,0,2,0],[0,1,1,0,0]],dtype=np.int64)
source=T/'synthetic.h5ad'
with h5py.File(source,'w') as h:
    h.create_dataset('X',data=x)
    h.create_dataset('obs/_index',data=np.array(['s'+str(i) for i in range(8)],dtype='S'))
    h.create_dataset('var/_index',data=np.array(['g0','g1','g1','g3','zero'],dtype='S'))
    h.create_dataset('obsm/spatial',data=np.arange(16,dtype=np.float64).reshape(8,2))
env=dict(os.environ,NUMBA_NUM_THREADS='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PYTHONHASHSEED='0',PYTHONDONTWRITEBYTECODE='1',NUMBA_CACHE_DIR=str(T/'numba_cache'))
worker=B/'baseline/evidence/COUNT-HEST-SHARED-K32-001/worker.py';results=[]
for k in (8,32):
    archive=T/f'K{k}.cnt';decoded=T/f'K{k}_decoded'
    for stage,src,dst in [('encode',source,archive),('decode',archive,decoded),('verify',source,decoded)]:
        report=T/f'K{k}_{stage}.json';cmd=[sys.executable,'-B','-X','utf8',str(worker),stage,str(src),str(dst),'--K',str(k),'--report',str(report)]
        start=time.monotonic()
        with (T/f'K{k}_{stage}.log').open('w',encoding='utf-8') as f:r=subprocess.run(cmd,cwd=B,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=180)
        results.append({'K':k,'stage':stage,'exit_code':r.returncode,'seconds':time.monotonic()-start,'command':cmd,'report':str(report)})
        (P/'SOURCE_SMOKE_PROCESSES.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        assert r.returncode==0,(k,stage)
    checks=json.loads((T/f'K{k}_verify.json').read_text())['checks'];assert checks['all'],checks
print('K8 and K32: synthetic real encode, separate-process archive-only decode and exact canonical recovery passed.',flush=True)
