"""Serial fixed-panel IVCSC benchmark with immutable evidence and independent decode."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import numpy as np
import adapter as a

B=Path(__file__).resolve().parents[1]

def main(args):
    config=Path(args.config).resolve();c=json.loads(config.read_text(encoding='utf-8'))
    if (c['methods']!=a.METHODS or c['upstream_commit']!=a.COMMIT or c['value_dtype']!='uint32' or c['index_dtype']!='uint32'
        or c['orientation']!='CSC of original spots-by-genes matrix; columns are genes; no reorder/oracle'
        or c['resource_ceiling']!={'per_worker_seconds':600,'rss_gib':12,'parallel_samples':1}):raise ValueError('unsupported config')
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=False);a.dump(out/'config.json',c)
    files=list(Path(__file__).parent.glob('*.py'))+list(Path(__file__).parent.glob('*.cpp'))+[a.EXE,B/'pilot/io047.py']+list((B/'vendor/IVSparse/IVSparse').rglob('*.hpp'))+[B/'vendor/IVSparse/IVSparse/SparseMatrix']
    a.dump(out/'environment.json',{'python':sys.version,'platform':platform.platform(),'numpy':np.__version__,
          'config_sha256':a.io.sha(config),'source_hashes':{str(p):a.io.sha(p) for p in files}})
    records=[]
    for sample in c['samples']:
        sid=sample['id'];folder=out/sid;folder.mkdir();rows=[]
        try:
            source=Path(sample['path'])
            if a.io.sha(source)!=sample['source_sha256']:raise ValueError('source hash mismatch')
            x,_=a.io.read_x(source);meta=a.io.jbytes(a.io.metadata(source,x.shape));a.exchange_write(folder/'input.csc',x)
            enc=a.execute([str(a.EXE),'encode','input.csc','matrix.ivcsc'],folder,folder/'native_encode.log')
            for method in c['methods']:
                case=folder/method;case.mkdir();r={'sample':sid,'method':method,'status':'failed','package_bytes':None}
                try:
                    r.update(a.write_archive(case/'count.cnt',folder/'matrix.ivcsc',meta,x,method));r['native_encode']=enc
                    r['decode_process']=a.execute([sys.executable,'-X','utf8','-B',str(Path(__file__).resolve()),'--decode',str(case/'count.cnt'),'--output',str(case/'decoded')],case,case/'decode.log')
                    with np.load(case/'decoded/decoded.npz',allow_pickle=False) as d:
                        checks={k:bool(np.array_equal(d[k],v)) for k,v in [('shape',x.shape),('indptr',x.indptr),('indices',x.indices),('values',x.data)]}
                    checks['metadata']=(case/'decoded/metadata.json').read_bytes()==meta
                    if not all(checks.values()):raise ValueError('source comparison failed')
                    r.update(status='success',checks=checks)
                except Exception as error:
                    r['error']=str(error);r['unverified_package_bytes']=r['package_bytes'];r['package_bytes']=None
                a.dump(case/'result.json',r);rows.append(r)
        except Exception as error:
            rows=[{'sample':sid,'method':m,'status':'failed','package_bytes':None,'error':str(error)} for m in c['methods']]
        a.dump(folder/'results.json',rows);records+=rows
        print(f"{sid}: {sum(r['status']=='success' for r in rows)}/2; {len(records)}/{len(c['samples'])*2}",flush=True)
    a.dump(out/'results.json',records);a.dump(out/'completion.json',{'successes':sum(r['status']=='success' for r in records),'expected':len(c['samples'])*2})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',default=str(B/'configs/COUNT-IVCSC-100.json'));p.add_argument('--output',required=True);p.add_argument('--decode');args=p.parse_args()
    if args.decode:
        a.source_guard();r=a.decode(Path(args.decode),Path(args.output));a.dump(Path(args.output)/'decode_result.json',r)
    else:main(args)
