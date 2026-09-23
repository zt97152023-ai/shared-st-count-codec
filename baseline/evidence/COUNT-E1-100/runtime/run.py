"""Frozen subprocess benchmark; failures remain explicit and outputs never overwritten."""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
import numpy as np
import psutil
import codec
import io047 as io

def dump(p,obj):
    with p.open('x',encoding='utf-8') as f: json.dump(obj,f,ensure_ascii=False,indent=2)

def worker(args):
    codec.warmup()
    if args.worker=='decode':
        codec.forbid_source_access()
        r=codec.decode_case(Path(args.package),Path(args.decoded))
    else:
        r=codec.encode_case(Path(args.source),args.method,Path(args.package))
    dump(Path(args.result),r)

def subprocess_run(cmd,log,config):
    env=os.environ.copy()
    for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMBA_NUM_THREADS']: env[k]='1'
    start=time.perf_counter();peak=0
    with log.open('xb') as f:
        p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,env=env)
        while p.poll() is None:
            try: peak=max(peak,psutil.Process(p.pid).memory_info().rss)
            except psutil.NoSuchProcess: pass
            if peak>config['resource_ceiling']['rss_gib']*2**30 or time.perf_counter()-start>config['resource_ceiling']['per_case_seconds']:
                p.kill();p.wait();raise RuntimeError('resource ceiling exceeded')
            time.sleep(.1)
    if p.returncode: raise RuntimeError(f'worker exited {p.returncode}; see {log.name}')
    return {'process_seconds_including_warmup':time.perf_counter()-start,'peak_rss_bytes':peak}

def main(args):
    config_path=Path(args.config).resolve();c=json.loads(config_path.read_text(encoding='utf-8'))
    expected={'schema':'support-pilot-v1','neighbors':6,'precision':12,'prior_strength':8,'positive_codec':'pcodec1.0.3 uint32 level8'}
    if any(c.get(k)!=v for k,v in expected.items()): raise ValueError('unsupported configuration; frozen codec constants must match')
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=False)
    dump(out/'config.json',c)
    source_files=sorted(Path(__file__).parent.glob('*.py'))
    dump(out/'environment.json',{'python':sys.version,'platform':platform.platform(),'numpy':np.__version__,
         'numba':codec.numba.__version__,'pcodec_runtime':str(sys.modules['pcodec'].__file__),
         'config_sha256':io.sha(config_path),'source_hashes':{p.name:io.sha(p) for p in source_files},
         'pcodec_files':{p.name:io.sha(p) for p in Path(sys.modules['pcodec'].__file__).parent.glob('*.pyd')}})
    records=[];started=time.perf_counter()
    base=[sys.executable,'-X','utf8','-B',str(Path(__file__).resolve())]
    for sample in c['samples']:
        source=Path(sample['path']);sid=sample['id']
        if io.sha(source)!=sample['source_sha256']: raise ValueError('source hash mismatch '+sid)
        ref,_=io.read_x(source);meta=io.metadata(source,ref.shape)
        for method in c['methods']:
            if time.perf_counter()-started>c['resource_ceiling']['total_seconds']: raise RuntimeError('total resource ceiling')
            case=out/sid/method;case.mkdir(parents=True)
            package=case/'count.cnt';row={'sample':sid,'method':method,'status':'failed','package_bytes':None}
            try:
                row['encode_process']=subprocess_run(base+['--worker','encode','--source',str(source),'--method',method,'--package',str(package),'--result',str(case/'encode.json')],case/'encode.log',c)
                row.update(json.loads((case/'encode.json').read_text(encoding='utf-8')))
                row['decode_process']=subprocess_run(base+['--worker','decode','--package',str(package),'--decoded',str(case/'decoded'),'--result',str(case/'decode.json')],case/'decode.log',c)
                with np.load(case/'decoded/decoded.npz',allow_pickle=False) as d:
                    checks={k:bool(np.array_equal(d[k],v)) for k,v in [('shape',ref.shape),('indptr',ref.indptr),('indices',ref.indices),('values',ref.data)]}
                checks['metadata']=(case/'decoded/metadata.json').read_bytes()==io.jbytes(meta)
                if not all(checks.values()): raise ValueError('source comparison failed')
                row['checks']=checks;row['status']='success'
                row['decode']=json.loads((case/'decode.json').read_text(encoding='utf-8'))
            except Exception as exc:
                row['error']=str(exc);row['unverified_package_bytes']=row['package_bytes'];row['package_bytes']=None
            dump(case/'result.json',row);records.append(row)
            print(sid,method,row['status'],row['package_bytes'],row.get('error',''),flush=True)
    dump(out/'results.json',records)
    report=['# COUNT-E1-001 三样本结果','', '新容器同场比较；全片拟合并计费，不是留出预测或确认性研究。G0未本机重跑，仍保留历史参照。', '',
            '|样本|方法|完整包 bytes|support bytes|概率表 bytes|图 bytes|相对本轮 Pcodec 节省|状态|',
            '|---|---|---:|---:|---:|---:|---:|---|']
    for r in records:
        pc=next(x for x in records if x['sample']==r['sample'] and x['method']=='Pcodec')
        saving=1-r['package_bytes']/pc['package_bytes'] if r['status']==pc['status']=='success' else None
        comp=r.get('components',{})
        report.append('|'+ '|'.join(map(str,[r['sample'],r['method'],r['package_bytes'],comp.get('support.rans','—'),comp.get('probability.bz2','—'),comp.get('graph.bz2','—'),f'{saving:.2%}' if saving is not None else 'NA',r['status']]))+'|')
    totals={m:sum(r['package_bytes'] for r in records if r['method']==m) for m in c['methods'] if all(r['status']=='success' for r in records if r['method']==m)}
    gate={}
    if len(totals)==len(c['methods']):
        savings=[1-next(r['package_bytes'] for r in records if r['sample']==s['id'] and r['method']=='S2_spatial')/next(r['package_bytes'] for r in records if r['sample']==s['id'] and r['method']=='S1_prefix') for s in c['samples']]
        gate={'spatial_pooled_saving_vs_prefix':1-totals['S2_spatial']/totals['S1_prefix'],
              'spatial_median_saving_vs_prefix':float(np.median(savings)),
              'spatial_better_than_shuffle_mean':bool(totals['S2_spatial']<np.mean([totals[m] for m in totals if m.startswith('S2_shuffle')])),
              'spatial_pooled_saving_vs_pcodec':1-totals['S2_spatial']/totals['Pcodec']}
        gate['development_gate_passed']=bool(gate['spatial_pooled_saving_vs_prefix']>=c['effect_gate']['mechanism_pooled_saving_vs_S1'] and gate['spatial_median_saving_vs_prefix']>0 and gate['spatial_better_than_shuffle_mean'])
    dump(out/'summary.json',{'totals':totals,'gate':gate,'successes':sum(r['status']=='success' for r in records),'expected':len(c['samples'])*len(c['methods'])})
    report+=['','```json',json.dumps(gate,ensure_ascii=False,indent=2),'```']
    (out/'REPORT.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    print(json.dumps(gate,ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config');p.add_argument('--output')
    p.add_argument('--worker',choices=['encode','decode']);p.add_argument('--source');p.add_argument('--method')
    p.add_argument('--package');p.add_argument('--decoded');p.add_argument('--result');a=p.parse_args()
    if a.worker: worker(a)
    else: main(a)
