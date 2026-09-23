"""Fixed shared-context count coding, isolated workers, original100 evidence."""
import argparse
import bz2
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import numpy as np
import psutil

HERE=Path(__file__).resolve().parent;B=HERE.parent;E=B/'evidence/COUNT-SHARED-001'
sys.path.insert(0,str(HERE/'frozen_runtime'))
import codec as legacy
import entropy
import io047 as io
import model

MAP={'P1_shared_prefix':'S1_prefix','P2_shared_spatial':'S2_spatial','P2_shared_shuffle11':'S2_shuffle_11'}
EXPECTED_MODEL={'base':'original S0 Q12 per-gene probability fitted per slide and transmitted',
    'buckets_edges_q12':[1,4,16,64,256,1024,2048,3072,4096],
    'contexts':'first6 rows usebase; later k=0..6 positives among6 causal predecessors',
    'parameters':56,
    'fit':'independent shared log-odds intercept perbucket/k; sum Bernoulli NLL with fixed gene offset, L2beta penalty coefficient1; bounded[-8,8],48 bisection steps, empty contexts beta0',
    'serialization':'positive odds multiplier R=round(exp(beta)*65536) uint32,56 entries=224bytes, no learned shared weights outside archive',
    'cdf':'integer q=clip(floor((4096*q0*R+den//2)/den),1,4095),den=q0*R+(4096-q0)*65536; exact uint64 arithmetic'}

def validate_config(cfg,check_inputs=True):
    if cfg['methods']!=list(MAP) or cfg['contract']['methods']!=list(MAP) or cfg['contract']['model']!=EXPECTED_MODEL:raise ValueError('model/config drift')
    if cfg['contract']['resource_ceiling']!={'parallel_samples':1,'worker_seconds':600,'sampled_worker_rss_GiB':12,'run_seconds':7200,'minimum_disk_free_GiB':12}:raise ValueError('resource config drift')
    if cfg['contract']['fit_conventions']!='Objective sum NLL + beta^2/2 (gradient plusbeta); bins left-inclusive/right-exclusive; serialize bucket-major thenk; R=floor(exp(beta)*65536+0.5); if no interior derivative root choose corresponding bound; emptycontext beta0':raise ValueError('fitting convention drift')
    if check_inputs:
        for p,h in cfg['input_sha256'].items():
            if io.sha(Path(p))!=h:raise ValueError('frozen reference ledger changed')
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def dump(p,obj):
    with Path(p).open('x',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2)

def load_reference(entry):
    p=Path(entry['path'])
    if io.sha(p)!=entry['sha256']:raise ValueError('reference archive changed')
    return legacy.read_archive(p)

def prefix_graph(n):
    graph=np.full((n,6),-1,np.int32)
    for i in range(1,n):graph[i,:min(i,6)]=np.arange(max(0,i-6),i)
    return graph

def encode(sample,method,target):
    t=time.perf_counter();source=Path(sample['path'])
    if io.sha(source)!=sample['source_sha256']:raise ValueError('source hash mismatch')
    x,_=io.read_x(source);n,g=x.shape
    if n*g>300000000:raise ValueError('symbol budget')
    s0,base=load_reference(sample['references']['S0_gene'])
    if s0['canonical_sha256']!=io.csr_sha(x) or s0['metadata_sha256']!=legacy.digest(io.jbytes(io.metadata(source,x.shape))):raise ValueError('source identity mismatch')
    q0=np.frombuffer(bz2.decompress(base['probability.bz2']),'<u2').copy()
    expected=np.clip(np.floor((np.bincount(x.indices,minlength=g)+.5)/(n+1.)*4096+.5),1,4095).astype('<u2')
    if not np.array_equal(q0,expected):raise ValueError('base differs from original gene marginal')
    parent,old=load_reference(sample['references'][MAP[method]])
    if parent['canonical_sha256']!=s0['canonical_sha256'] or old['values.pco']!=base['values.pco'] or old['metadata.bz2']!=base['metadata.bz2']:raise ValueError('reference component identity')
    graph=prefix_graph(n) if method=='P1_shared_prefix' else np.frombuffer(bz2.decompress(old['graph.bz2']),'<i4').reshape(n,6).copy()
    legacy.validate_graph(graph,n)
    m=entropy.packed_support(x.indptr,x.indices,n,g)
    fit_start=time.perf_counter();multipliers,stats=model.fit(m,graph,q0);stats['fit_seconds']=time.perf_counter()-fit_start
    q=model.cdf(q0,multipliers);blob,nll=entropy.encode(m,graph,q,g)
    parts={'metadata.bz2':base['metadata.bz2'],'values.pco':base['values.pco'],
        'base_probability.bz2':base['probability.bz2'],'shared_odds.u32':multipliers.tobytes(),'support.rans':blob.tobytes()}
    if method!='P1_shared_prefix':parts['graph.bz2']=old['graph.bz2']
    info={'schema':'shared-count-v1','method':method,'shape':[n,g],'nnz':int(x.nnz),
        'canonical_sha256':s0['canonical_sha256'],'metadata_sha256':s0['metadata_sha256'],
        'precision':12,'odds_scale':65536,'bucket_edges_q12':model.EDGES.tolist(),
        'model':'gene-Q12-base+8x7-shared-odds;startup6-base;uint64-round-nearest',
        'positive_codec':'pcodec1.0.3 uint32 level8'}
    comp=legacy.write_archive(target,parts,info)
    stats.update(package_bytes=target.stat().st_size,package_sha256=io.sha(target),components=comp,
        framing_and_manifest_bytes=target.stat().st_size-sum(comp.values()),canonical_sha256=s0['canonical_sha256'],
        support_nll_bits=nll,q_cdf_sha256=legacy.digest(q.tobytes()),encode_seconds_including_source=time.perf_counter()-t,
        original_support_bytes=len(old['support.rans']),original_probability_bytes=len(old['probability.bz2']),
        effective_model_bytes=len(parts['base_probability.bz2'])+224)
    return stats

def decode(package,out):
    # Standalone decoder cannot read source matrices or previous experiment archives.
    import zipfile
    with zipfile.ZipFile(package) as z:
        man=json.loads(z.read('manifest.json'));names=z.namelist()
        if man.get('schema')!='shared-count-v1' or man.get('method') not in MAP:raise ValueError('schema/method')
        expected={'metadata.bz2','values.pco','base_probability.bz2','shared_odds.u32','support.rans'}
        if man['method']!='P1_shared_prefix':expected.add('graph.bz2')
        if len(names)!=len(set(names)) or set(names)!=expected|{'manifest.json'} or set(man['files'])!=expected:raise ValueError('members')
        if man['precision']!=12 or man['odds_scale']!=65536 or man['bucket_edges_q12']!=model.EDGES.tolist():raise ValueError('model descriptor')
        n,g=map(int,man['shape']);nnz=int(man['nnz'])
        if not (0<n<=2000000 and 0<g<=2000000 and n*g<=300000000 and 0<=nnz<=min(n*g,100000000)):raise ValueError('shape budget')
        parts={}
        for key in expected:
            if z.getinfo(key).file_size>2**31:raise ValueError('member budget')
            v=z.read(key)
            if len(v)!=man['files'][key]['bytes'] or legacy.digest(v)!=man['files'][key]['sha256']:raise ValueError('integrity')
            parts[key]=v
    q0raw=bz2.decompress(parts['base_probability.bz2'])
    if len(q0raw)!=g*2 or len(parts['shared_odds.u32'])!=224:raise ValueError('model lengths')
    q0=np.frombuffer(q0raw,'<u2');r=np.frombuffer(parts['shared_odds.u32'],'<u4').reshape(8,7)
    q=model.cdf(q0,r)
    graph=prefix_graph(n) if man['method']=='P1_shared_prefix' else np.frombuffer(bz2.decompress(parts['graph.bz2']),'<i4').reshape(n,6).copy()
    legacy.validate_graph(graph,n)
    m=entropy.decode(np.frombuffer(parts['support.rans'],np.uint8),graph,q,n,g)
    ptr,idx=entropy.indices_from_support(m,g,nnz)
    values=legacy.pdecompress(parts['values.pco'],nnz)
    if np.any(values==0):raise ValueError('positive values')
    x=io.from_parts((n,g),ptr,idx,values)
    if io.csr_sha(x)!=man['canonical_sha256']:raise ValueError('count hash mismatch')
    meta=bz2.decompress(parts['metadata.bz2']);metaobj=json.loads(meta)
    if legacy.digest(meta)!=man['metadata_sha256'] or len(metaobj['spot_ids'])!=n or len(metaobj['gene_ids'])!=g:raise ValueError('metadata')
    out.mkdir(exist_ok=False);np.savez(out/'decoded.npz',shape=np.array(x.shape),indptr=x.indptr,indices=x.indices,values=x.data)
    (out/'metadata.json').write_bytes(meta)
    return {'archive_only':True,'canonical_sha256':man['canonical_sha256'],'metadata_sha256':man['metadata_sha256'],
        'q_cdf_sha256':legacy.digest(q.tobytes())}

def source_guard():
    def hook(event,args):
        if event=='open' and isinstance(args[0],(str,bytes)):
            p=str(args[0]).lower().replace('\\','/')
            if p.endswith('.h5ad') or '/hestdata/' in p or '/count-e1-100/' in p:raise PermissionError('source forbidden')
    sys.addaudithook(hook)

def execute(cmd,log):
    env=os.environ.copy()
    for key in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMBA_NUM_THREADS']:env[key]='1'
    peak=0;t=time.monotonic()
    with log.open('xb') as f:
        p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,env=env)
        while p.poll() is None:
            try:peak=max(peak,psutil.Process(p.pid).memory_info().rss)
            except psutil.NoSuchProcess:pass
            if peak>12*2**30 or time.monotonic()-t>600:
                p.kill();p.wait();raise RuntimeError('worker limit')
            time.sleep(.1)
    if p.returncode:raise RuntimeError(f'worker exit{p.returncode}; see {log}')
    return {'seconds_including_import':time.monotonic()-t,'sampled_peak_rss_bytes':peak}

def main(args):
    cfgpath=E/'config.json';cfg=read(cfgpath);validate_config(cfg);samples=cfg['samples']
    if args.smoke:samples=[s for s in samples if s['id'] in ['SPA108','NCBI807','TENX132']]
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=False);dump(out/'config.json',cfg)
    sources=list(HERE.glob('*.py'))+list((HERE/'frozen_runtime').glob('*.py'))
    dump(out/'environment.json',{'config_sha256':io.sha(cfgpath),'python':sys.version,'numpy':np.__version__,
        'numba':legacy.numba.__version__,'source_hashes':{str(p):io.sha(p) for p in sources},
        'pcodec_hashes':{str(p):io.sha(p) for p in Path(sys.modules['pcodec'].__file__).parent.glob('*.pyd')}})
    records=[];started=time.monotonic();base=[sys.executable,'-X','utf8','-B',str(Path(__file__).resolve())]
    for sample in samples:
        source=Path(sample['path']);sid=sample['id']
        # Source errors generate explicit failure rows for every method in that sample.
        try:
            if io.sha(source)!=sample['source_sha256']:raise ValueError('source hash')
            ref,_=io.read_x(source);meta=io.jbytes(io.metadata(source,ref.shape));source_error=None
        except Exception as error:source_error=str(error)
        for method in cfg['methods']:
            case=out/sid/method;case.mkdir(parents=True);row={'sample':sid,'method':method,'status':'failed','package_bytes':None}
            try:
                if source_error:raise ValueError(source_error)
                if time.monotonic()-started>7200 or shutil.disk_usage(out).free<12*2**30:raise RuntimeError('run resource ceiling')
                row['encode_process']=execute(base+['--worker','encode','--sample',sid,'--method',method,'--package',str(case/'count.cnt'),'--result',str(case/'encode.json')],case/'encode.log')
                row.update(read(case/'encode.json'))
                row['decode_process']=execute(base+['--worker','decode','--package',str(case/'count.cnt'),'--output',str(case/'decoded'),'--result',str(case/'decode.json')],case/'decode.log')
                with np.load(case/'decoded/decoded.npz',allow_pickle=False) as d:
                    checks={k:bool(np.array_equal(d[k],v)) for k,v in [('shape',ref.shape),('indptr',ref.indptr),('indices',ref.indices),('values',ref.data)]}
                checks['metadata']=(case/'decoded/metadata.json').read_bytes()==meta
                dec=read(case/'decode.json')
                if not all(checks.values()) or row['q_cdf_sha256']!=dec['q_cdf_sha256']:raise ValueError('exactness orCDF mismatch')
                row.update(status='success',checks=checks,decode=dec)
                # Generated scratch array only; retain archive, hashes, metadata and checks.
                (case/'decoded/decoded.npz').unlink()
            except Exception as error:row.update(error=str(error),unverified_package_bytes=row['package_bytes'],package_bytes=None)
            dump(case/'result.json',row);records.append(row)
            print(f'{sid} {method}: {row["status"]}; {len(records)}/{len(samples)*3}',flush=True)
    dump(out/'results.json',records);dump(out/'completion.json',{'expected':len(samples)*3,'success':sum(r['status']=='success' for r in records)})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output');p.add_argument('--smoke',action='store_true');p.add_argument('--worker',choices=['encode','decode']);p.add_argument('--sample');p.add_argument('--method');p.add_argument('--package');p.add_argument('--result');args=p.parse_args()
    if args.worker=='decode':source_guard();dump(Path(args.result),decode(Path(args.package),Path(args.output)))
    elif args.worker=='encode':
        cfg=read(E/'config.json');validate_config(cfg,check_inputs=False);sample=next(s for s in cfg['samples'] if s['id']==args.sample)
        dump(Path(args.result),encode(sample,args.method,Path(args.package)))
    else:main(args)
