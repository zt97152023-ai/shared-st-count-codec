"""Isolated K-aware experiment worker; original production sources stay immutable."""
import argparse,base64,bz2,hashlib,importlib.util,inspect,json,os,sys,time,types,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[2];sys.path.insert(0,str(ROOT))
import numpy as np
def sha(b):return hashlib.sha256(b).hexdigest()
def write(p,x):Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=False),encoding='utf-8')
def load(K):
    from baseline.matched_ready.runtime import load_qpatch_runtime
    rt=list(load_qpatch_runtime()); qm=rt[3];qs=rt[4]
    replacements=[('pooled=np.zeros((8,32)','pooled=np.zeros((K,32)'),('seen=np.zeros((8,7,4096)','seen=np.zeros((K,7,4096)'),('tail=np.zeros((8,7,32)','tail=np.zeros((K,7,32)'),('np.full((8,7)','np.full((K,7)'),('np.empty((8,7,32)','np.empty((K,7,32)'),('range(8)','range(K)'),('groups>7','groups>=K'),('shape!=(8,32)','shape!=(K,32)'),('shape!=(8,7)','shape!=(K,7)'),('shape!=(8,7,32)','shape!=(K,7,32)'),('np.zeros((8,8,33)','np.zeros((K,8,33)'),('enumerate(BOUNDS) if int(tail_sum[g])<=u*nt),7)','enumerate(BOUNDS) if int(tail_sum[g])<=u*nt),K-1)')]
    src=Path(qm.__file__).read_text();src=src.replace('@njit(cache=True)','@njit(cache=False)')
    for old,new in replacements:
        assert old in src,old
        src=src.replace(old,new)
    # Original inclusive integer boundaries for K8; fixed experimental family elsewhere.
    bounds=(1,2,4,8,16,64,256) if K==8 else tuple(2.**np.interp(j*8/K,np.arange(9),[-1,0,1,2,3,4,6,8,10]) for j in range(1,K))
    m=types.ModuleType('value_k_model');sys.modules[m.__name__]=m;m.__file__=qm.__file__;m.K=K
    exec(compile(src,qm.__file__,'exec'),m.__dict__);m.BOUNDS=bounds
    ss=Path(qs.__file__).read_text().replace("HEADER=struct.Struct('<4sBI8H')",f"HEADER=struct.Struct('<4sBI{K}H')").replace('range(8)','range(K)').replace('groups>7','groups>=K')
    sm=types.ModuleType('value_k_qshare');sm.K=K;exec(compile(ss,qs.__file__,'exec'),sm.__dict__)
    rt[3]=m;rt[4]=sm
    return tuple(rt)

def encode(raw,target,K,original=False):
    from baseline.matched_ready import shared
    if original:return shared.encode(raw,target)
    rt=load(K); io,entropy,support_model,qm,qs,values=rt
    diagnostics={}
    def runtime():return rt
    original_base=qm.base
    def traced_base(*args):
        start=time.perf_counter();result=original_base(*args)
        oldq,groups,prob,freq,prof=result
        if os.environ.get('VALUE_GROUP_SHUFFLE_SEED') is not None:
            groups=np.random.default_rng(int(os.environ['VALUE_GROUP_SHUFFLE_SEED'])).permutation(groups)
            pooled=np.zeros((K,32),np.int64);np.add.at(pooled,groups,prof['tail_hist'])
            prob=(pooled+1/32)/(pooled.sum(axis=1)[:,None]+1)
            freq=np.stack([qm.quantize(p) for p in prob]);prof['group']=groups
            result=(oldq,groups,prob,freq,prof)
        counts=np.bincount(groups,minlength=K);events=np.bincount(groups,weights=prof['npositive'],minlength=K).astype('int64')
        diagnostics.update(requested_K=K,effective_K=int((counts>0).sum()),empty_groups=int((counts==0).sum()),gene_counts=counts.tolist(),positive_events=events.tolist(),tail_events_by_group=np.bincount(groups,weights=prof['npositive']-prof['nones'],minlength=K).astype('int64').tolist(),bounds=list(qm.BOUNDS),base_prepare_seconds=time.perf_counter()-start)
        return result
    qm.base=traced_base
    original_cond=qm.conditional
    def traced_cond(*args):
        start=time.perf_counter();result=original_cond(*args);diagnostics['conditional_prepare_seconds']=time.perf_counter()-start
        seen,_,tail=qm.conditional_counts(*args[:6])
        diagnostics['empty_conditional_cells']=int((seen.sum(axis=2)==0).sum())
        diagnostics['prior_only_tail_cells']=int((tail.sum(axis=2)==0).sum())
        return result
    qm.conditional=traced_cond
    src=inspect.getsource(shared.encode).replace('load_qpatch_runtime()','runtime()')
    src=src.replace('    from .archive import write_shared',"    if K != 8: info.update(value_group_count=K, value_group_rule='fixed-log-axis-v1')\n    from .archive import write_shared")
    ns=dict(shared.__dict__);ns.update(runtime=runtime,K=K);exec(compile(src,str(HERE/'worker.py'),'exec'),ns)
    result=ns['encode'](raw,target);result['group_diagnostics']=diagnostics
    return result

def decode(package,output):
    from baseline.matched_ready import decoder
    from baseline.matched_ready.archive import read
    decoder.source_guard()
    man,parts,_,_=read(package);K=man.get('value_group_count',8)
    if type(K) is not int or K not in [1,2,4,6,8,10,12,16,32]:raise ValueError('unsupported K')
    if K!=8 and man.get('value_group_rule')!='fixed-log-axis-v1':raise ValueError('non8 experimental format rule')
    rt=load(K)
    src=inspect.getsource(decoder._shared_decode).replace('load_qpatch_runtime()','runtime()')
    src=src.replace('groups > 7','groups >= K').replace('.reshape(8, 32)','.reshape(K, 32)').replace('.reshape(8, 7, 32)','.reshape(K, 7, 32)')
    # Only value_odds reshape changes; support odds stays (8,7).
    src=src.replace('parts["value_odds.u32"], "<u4").reshape(8, 7)','parts["value_odds.u32"], "<u4").reshape(K, 7)')
    ns=dict(decoder.__dict__);ns.update(runtime=lambda:rt,K=K);exec(compile(src,str(HERE/'worker.py'),'exec'),ns)
    return ns['_shared_decode'](man,parts,Path(output))

def verify(source,decoded):
    from baseline.matched_ready.adapter import read_h5ad
    from baseline.hest1000.pilot import compare
    raw=read_h5ad(source);checks=compare(raw.matrix,raw.metadata_bytes,Path(decoded))
    md=json.loads((Path(decoded)/'metadata.json').read_text())
    for key in ['gene_ids','spot_ids','coordinates_dtype','coordinates_shape','coordinates_base64']:checks[key]=md[key]==raw.metadata[key]
    checks['all']=all(checks.values())
    if not checks['all']:raise ValueError(str(checks))
    return {'checks':checks,'canonical_sha256':load(8)[0].csr_sha(raw.matrix),'metadata_sha256':sha(raw.metadata_bytes)}

def synthetic(K,out):
    from scipy import sparse
    from baseline.matched_ready.adapter import CanonicalInput
    from baseline.hest1000.pilot import compare
    cases={
      'zero':np.zeros((8,5),np.int64),
      'ones':np.ones((8,5),np.int64),
      'tail':np.array([[0,1,2,2**32-1,0],[0,0,0,0,0],[3,4,8,16,0],[1,0,65,257,0],[0,1,0,0,0],[2,3,4,5,0],[0,0,0,1,0],[3,1,0,0,0]],dtype=np.int64)}
    out=Path(out);out.mkdir(parents=True,exist_ok=False);reports=[]
    for name,x in cases.items():
        x=sparse.csr_matrix(x);coords=np.arange(x.shape[0]*2,dtype=np.float64).reshape(-1,2)
        md={'schema':'047-exact-metadata-v1','spot_ids':[str(i) for i in range(x.shape[0])],'gene_ids':[str(i) for i in range(x.shape[1])],'coordinates_shape':list(coords.shape),'coordinates_dtype':str(coords.dtype),'coordinates_base64':base64.b64encode(coords.tobytes()).decode()}
        io=load(8)[0];raw=CanonicalInput(Path('synthetic'),x,md,io.jbytes(md),'csr_matrix')
        result=encode(raw,out/(name+'.cnt'),K)
        # Same-process synthetic decode used only as unit test; real runs use fresh processes.
        from baseline.matched_ready import decoder
        old=decoder.source_guard;decoder.source_guard=lambda:None
        decode(out/(name+'.cnt'),out/(name+'_decoded'));decoder.source_guard=old
        checks=compare(x,raw.metadata_bytes,out/(name+'_decoded'));assert checks['all']
        reports.append({'case':name,'K':K,'checks':checks,'bytes':result['package_bytes']})
    return reports

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('stage');a.add_argument('source');a.add_argument('output');a.add_argument('--K',type=int,default=8);a.add_argument('--report',required=True);a.add_argument('--shuffle',type=int);args=a.parse_args()
    if args.shuffle is not None:os.environ['VALUE_GROUP_SHUFFLE_SEED']=str(args.shuffle)
    for name,expected in json.loads((HERE/'PINS.json').read_text()).items():assert sha((ROOT/name).read_bytes())==expected,name
    start=time.perf_counter()
    if args.stage in ['encode','original']:
        from baseline.matched_ready.adapter import read_h5ad
        raw=read_h5ad(args.source);result=encode(raw,args.output,args.K,args.stage=='original')
    elif args.stage=='decode':result=decode(args.source,args.output)
    elif args.stage=='verify':result=verify(args.source,args.output)
    elif args.stage=='synthetic':result={'cases':synthetic(args.K,args.output)}
    else:raise ValueError(args.stage)
    result['worker_seconds']=time.perf_counter()-start;write(args.report,result)
