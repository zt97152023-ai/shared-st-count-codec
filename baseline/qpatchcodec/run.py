"""Fixed Qpatch12 complete count experiment; archive-only decode workers."""
import argparse,bz2,faulthandler,hashlib,json,os,shutil,subprocess,sys,time,zipfile
from pathlib import Path
faulthandler.enable()
def stage(name):print(json.dumps({'stage':name,'pid':os.getpid(),'time':time.time()}),flush=True)
stage('imports_start')
import numpy as np
import numba
import psutil
HERE=Path(__file__).resolve().parent;B=HERE.parent;E=B/'evidence/COUNT-QPATCH-001'
sys.path.insert(0,str(HERE/'frozen_runtime'))
import io047 as io
import entropy
import model
import values
import qshare_model as qm
from metrics import nll_delta
stage('imports_done')
METHODS=['Qpatch12']
FIXED={'metadata.bz2','support.rans','graph.bz2','base_probability.bz2','shared_odds.u32'}
VALUE_BASE={'value_q1.bz2','value_group.bz2','value_base_k.bz2','values.rans'}

def sha(data):return hashlib.sha256(data).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def dump(p,obj):
    with Path(p).open('x',encoding='utf8') as f:json.dump(obj,f,ensure_ascii=False,indent=2)
def config():
    p=E/'config.json'
    if io.sha(p)!=(E/'config.sha256').read_text().strip():raise ValueError('frozen config drift')
    cfg=read(p)
    if cfg['methods']!=METHODS:raise ValueError('method drift')
    for path,h in cfg['code_sha256'].items():
        if io.sha(Path(path))!=h:raise ValueError('frozen code drift')
    return cfg

def archive(path):
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or 'manifest.json' not in names:raise ValueError('archive members')
        man=json.loads(z.read('manifest.json'))
        if set(names)!=set(man['files'])|{'manifest.json'}:raise ValueError('manifest members')
        parts={}
        for name,desc in man['files'].items():
            zi=z.getinfo(name)
            if zi.file_size>2**31 or zi.compress_type!=zipfile.ZIP_STORED:raise ValueError('member budget/compression')
            data=z.read(name)
            if len(data)!=desc['bytes'] or sha(data)!=desc['sha256']:raise ValueError('member integrity')
            parts[name]=data
    return man,parts

def load_reference(entry):
    p=Path(entry['path'])
    if p.stat().st_size!=entry['package_bytes'] or io.sha(p)!=entry['sha256']:raise ValueError('source archive hash')
    return archive(p)

def write_archive(path,parts,info):
    man={**info,'files':{k:{'bytes':len(v),'sha256':sha(v)} for k,v in sorted(parts.items())}}
    with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_STORED) as z:
        for name,data in sorted({**parts,'manifest.json':io.jbytes(man)}.items()):
            zi=zipfile.ZipInfo(name,(1980,1,1,0,0,0));zi.external_attr=0o100644<<16;z.writestr(zi,data)

def graph_from(raw,n):
    data=bz2.decompress(raw)
    if len(data)!=n*6*4:raise ValueError('graph bytes')
    graph=np.frombuffer(data,'<i4').reshape(n,6).copy()
    for row,v in enumerate(graph):
        k=min(row,6)
        if np.any(v[:k]<0) or np.any(v[:k]>=row) or len(set(map(int,v[:k])))!=k or np.any(v[k:]!=-1):raise ValueError('causal graph')
    return graph

def support_model(parts,genes):
    base=np.frombuffer(bz2.decompress(parts['base_probability.bz2']),'<u2')
    r=np.frombuffer(parts['shared_odds.u32'],'<u4')
    if base.shape!=(genes,) or r.shape!=(56,) or np.any(base<1) or np.any(base>4095) or np.any(r<22) or np.any(r>195360063):raise ValueError('support model')
    bucket=np.searchsorted([1,4,16,64,256,1024,2048,3072,4096],base,side='right')-1
    a=base.astype(np.uint64)[:,None];num=a*r.reshape(8,7)[bucket].astype(np.uint64);den=num+(4096-a)*65536
    q=np.repeat(base[:,None],49,axis=1);q[:,42:49]=np.clip((4096*num+den//2)//den,1,4095)
    return q.astype('<u2')

def patch_model(oldq,groups,odds,n,a):
    centers=qm.share(n,a,groups)
    oldcdf=qm.cdf(oldq,groups,odds);sharedcdf=qm.cdf(centers[groups],groups,odds)
    raw,safe,eps=qm.bound(n,a,oldcdf,sharedcdf);mask=safe>12
    blob=qm.encode(centers,groups,oldq,mask)
    q=decode_q(blob,groups)
    return blob,q,oldcdf,mask,raw,safe,eps

def decode_q(blob,groups):
    q=qm.decode(blob,groups)  # bounded parser validates full stream first
    header=bz2.BZ2Decompressor().decompress(blob,max_length=qm.HEADER.size)
    if qm.HEADER.unpack(header)[1]!=1:raise ValueError('Qpatch12 requires mode1')
    return q

def encode(sample,method,target):
    if method!='Qpatch12':raise ValueError('method')
    stage('source_read');source=Path(sample['path'])
    if io.sha(source)!=sample['source_sha256']:raise ValueError('matrix hash')
    x,_=io.read_x(source);n,g=x.shape
    if n*g>300000000 or x.nnz>100000000:raise ValueError('symbol budget')
    man,old=load_reference(sample['v2'])
    if man['schema']!='value-count-v1' or man['method']!='V2_spatial':raise ValueError('reference method')
    if io.csr_sha(x)!=man['canonical_sha256'] or sha(io.jbytes(io.metadata(source,x.shape)))!=man['metadata_sha256']:raise ValueError('raw identity')
    graph=graph_from(old['graph.bz2'],n)
    oldq=np.frombuffer(bz2.decompress(old['value_q1.bz2']),'<u2')
    groups=np.frombuffer(bz2.decompress(old['value_group.bz2']),np.uint8)
    freq=np.frombuffer(bz2.decompress(old['value_base_k.bz2']),'<u2').reshape(8,32)
    odds=np.frombuffer(old['value_odds.u32'],'<u4').reshape(8,7)
    cond=np.frombuffer(bz2.decompress(old['value_cond_k.bz2']),'<u2').reshape(8,7,32)
    stage('raw_gene_counts');npos,ones,_,_=model.gene_counts(x.indices,x.data,g)
    if io.sha(Path(sample['profile']))!=sample['profile_sha256']:raise ValueError('profile hash')
    with np.load(sample['profile'],allow_pickle=False) as profile:
        if not np.array_equal(npos,profile['npositive']) or not np.array_equal(ones,profile['nones']) or not np.array_equal(groups,profile['group']):raise ValueError('raw profile mismatch')
    qblob,q,oldcdf,patch,raw,safe,eps=patch_model(oldq,groups,odds,npos,ones)
    if sha(qblob)!=sample['screen']['blob_sha256'] or sha(q.tobytes())!=sample['screen']['candidate_q_sha256']:raise ValueError('fixed screen candidate mismatch')
    binary,tail,cdf=model.tables(q,groups,freq,odds,cond)
    delta=float(nll_delta(x.indptr,x.indices,x.data,graph,oldcdf,binary))
    safe_bound=float(safe[~patch].sum());raw_bound=float(raw[~patch].sum())
    tolerance=max(1e-6,1e-9*x.nnz)
    if delta>safe_bound+tolerance:raise ValueError('realized NLL exceeds fixed bound')
    stage('value_encode');blob,nll,te,rb=values.encode(x.indptr,x.indices,x.data,graph,groups,binary,tail,cdf,True)
    parts=dict(old);parts['value_q1.bz2']=qblob;parts['values.rans']=blob.tobytes()
    info={k:v for k,v in man.items() if k!='files'}
    info.update(schema='qpatch-count-v1',method='Qpatch12',q1_layout='QSH1-mode1-12bit-exceptions-bz2-v1')
    if int(te)!=man['tail_events'] or int(rb)!=man['remainder_bits']:raise ValueError('tail identity')
    stage('archive_write');write_archive(target,parts,info)
    package_bytes=target.stat().st_size
    framing=package_bytes-sum(map(len,parts.values()))
    oldframing=sample['v2']['package_bytes']-sum(map(len,old.values()))
    model_saved=len(old['value_q1.bz2'])-len(qblob)
    stream_delta=len(parts['values.rans'])-len(old['values.rans'])
    frame_delta=framing-oldframing
    saved=sample['v2']['package_bytes']-package_bytes
    if saved!=model_saved-stream_delta-frame_delta:raise ValueError('byte conservation')
    return {'package_bytes':package_bytes,'package_sha256':io.sha(target),'components':{k:len(v) for k,v in parts.items()},
            'framing_bytes':framing,'framing_delta_bytes':frame_delta,'model_saved_bytes':model_saved,
            'positive_stream_bytes':len(parts['values.rans']),'positive_stream_delta_bytes':stream_delta,
            'old_v2_package_bytes':sample['v2']['package_bytes'],'saved_vs_v2_bytes':saved,
            'fraction_saved_vs_v2':saved/sample['v2']['package_bytes'],
            'value_cdf_sha256':sha(binary.tobytes()+tail.tobytes()+cdf.tobytes()),
            'candidate_q_sha256':sha(q.tobytes()),'qblob_sha256':sha(qblob),'exceptions':int(patch.sum()),
            'raw_counts_sha256':sha(npos.astype('<i8').tobytes()+ones.astype('<i8').tobytes()),
            'value_nll_bits':float(nll),'realized_nll_delta_bits':delta,
            'ledger_nll_delta_bits':float(nll)-sample['old_value_nll_bits'],
            'safe_bound_bits':safe_bound,'raw_bound_bits':raw_bound,'bound_tolerance_bits':tolerance,
            'rans_delta_minus_nll_bits':8*stream_delta-delta,
            'screen_budget_bytes':sample['screen']['budget_bytes'],
            'canonical_sha256':man['canonical_sha256'],'metadata_sha256':man['metadata_sha256']}

def decode(package,out):
    stage('archive_read');man,parts=archive(package);method=man.get('method')
    if man.get('schema')!='qpatch-count-v1' or man.get('q1_layout')!='QSH1-mode1-12bit-exceptions-bz2-v1' or method not in METHODS or man['precision']!=12 or man['value_layout']!='singleton-K32-uniform-remainder;one-rANS;v1' or man['support_model']!='frozen-P2-shared-spatial-Q12-v1':raise ValueError('schema')
    expected=FIXED|VALUE_BASE
    if method!='V1_gene':expected|={'value_odds.u32','value_cond_k.bz2'}
    if method=='V2_shuffle11':expected|={'values_graph.bz2'}
    if set(parts)!=expected:raise ValueError('unexpected payload')
    n,g=io.shape2(man['shape']);nnz=man['nnz']
    if not isinstance(nnz,int) or not 0<=nnz<=min(100000000,n*g) or n*g>300000000:raise ValueError('shape/nnz budget')
    graph=graph_from(parts['graph.bz2'],n);value_graph=graph_from(parts['values_graph.bz2'],n) if method=='V2_shuffle11' else graph
    stage('support_decode');q_support=support_model(parts,g)
    mask=entropy.decode(np.frombuffer(parts['support.rans'],np.uint8),graph,q_support,n,g)
    ptr,idx=entropy.indices_from_support(mask,g,nnz)
    groups=np.frombuffer(bz2.decompress(parts['value_group.bz2']),np.uint8)
    q=decode_q(parts['value_q1.bz2'],groups)
    base=np.frombuffer(bz2.decompress(parts['value_base_k.bz2']),'<u2').reshape(8,32)
    if q.shape!=(g,) or groups.shape!=(g,):raise ValueError('gene lengths')
    odds=cond=None
    if method!='V1_gene':
        odds=np.frombuffer(parts['value_odds.u32'],'<u4').reshape(8,7)
        cond=np.frombuffer(bz2.decompress(parts['value_cond_k.bz2']),'<u2').reshape(8,7,32)
    binary,tail,cdf=model.tables(q,groups,base,odds,cond)
    stage('value_decode');val,te,rb=values.decode(np.frombuffer(parts['values.rans'],np.uint8),ptr,idx,value_graph,groups,binary,tail,cdf,method!='V1_gene')
    if te!=man['tail_events'] or rb!=man['remainder_bits']:raise ValueError('value symbol counts')
    x=io.from_parts((n,g),ptr,idx,val)
    if io.csr_sha(x)!=man['canonical_sha256']:raise ValueError('count identity')
    meta=bz2.decompress(parts['metadata.bz2']);obj=json.loads(meta)
    if sha(meta)!=man['metadata_sha256'] or len(obj['spot_ids'])!=n or len(obj['gene_ids'])!=g:raise ValueError('metadata identity')
    out.mkdir();np.savez(out/'decoded.npz',shape=np.array(x.shape),indptr=x.indptr,indices=x.indices,values=x.data);(out/'metadata.json').write_bytes(meta)
    stage('decode_exact_export')
    return {'archive_only':True,'canonical_sha256':man['canonical_sha256'],'metadata_sha256':man['metadata_sha256'],
            'value_cdf_sha256':sha(binary.tobytes()+tail.tobytes()+cdf.tobytes())}

def source_guard():
    def hook(event,args):
        if event=='open' and isinstance(args[0],(str,bytes)):
            p=str(args[0]).lower().replace('\\','/')
            if p.endswith('.h5ad') or '/hestdata/' in p or '/count-shared-001/' in p or '/count-e1-100/' in p or '/count-value-001/' in p or '/count-qshare-screen-001/' in p or 'gene_profile' in p:raise PermissionError('source forbidden')
    sys.addaudithook(hook)

def execute(cmd,log):
    env=os.environ.copy()
    for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMBA_NUM_THREADS']:env[k]='1'
    env['PYTHONFAULTHANDLER']='1';t=time.monotonic();peak=0
    with log.open('xb') as f:
        p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,env=env)
        while p.poll() is None:
            try:peak=max(peak,psutil.Process(p.pid).memory_info().rss)
            except psutil.NoSuchProcess:pass
            if peak>12*2**30 or time.monotonic()-t>600:
                p.kill();p.wait();raise RuntimeError('worker resource limit')
            time.sleep(.1)
    if p.returncode:raise RuntimeError(f'worker exit{p.returncode}; see {log}')
    return {'seconds':time.monotonic()-t,'sampled_peak_rss_bytes':peak}

def main(args):
    cfg=config()
    for p,h in cfg['input_sha256'].items():
        if io.sha(Path(p))!=h:raise ValueError('input evidence drift')
    samples=cfg['samples']
    if args.smoke:samples=[s for s in samples if s['id'] in ['SPA108','NCBI807','TENX132']]
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=False);dump(out/'config.json',cfg)
    sources=list(HERE.glob('*.py'))+list((HERE/'frozen_runtime').glob('*.py'))
    dump(out/'environment.json',{'config_sha256':io.sha(E/'config.json'),'python':sys.version,'numpy':np.__version__,'numba':numba.__version__,
                               'source_hashes':{str(p):io.sha(p) for p in sources},'no_pcodec_import':not any(k=='pcodec' or k.startswith('pcodec.') for k in sys.modules)})
    base=[sys.executable,'-X','utf8','-B',str(Path(__file__).resolve())];records=[];start=time.monotonic()
    for sample in samples:
        sid=sample['id']
        try:
            source=Path(sample['path'])
            if io.sha(source)!=sample['source_sha256']:raise ValueError('matrix hash')
            x,_=io.read_x(source);meta=io.jbytes(io.metadata(source,x.shape));error=None
        except Exception as e:error=str(e)
        for method in METHODS:
            case=out/sid/method;case.mkdir(parents=True);row={'sample':sid,'method':method,'status':'failed','package_bytes':None}
            try:
                if error:raise ValueError(error)
                if time.monotonic()-start>7200 or shutil.disk_usage(out).free<12*2**30:raise RuntimeError('run budget')
                row['encode_process']=execute(base+['--worker','encode','--sample',sid,'--method',method,'--package',str(case/'count.cnt'),'--result',str(case/'encode.json')],case/'encode.log')
                row.update(read(case/'encode.json'))
                row['decode_process']=execute(base+['--worker','decode','--package',str(case/'count.cnt'),'--output',str(case/'decoded'),'--result',str(case/'decode.json')],case/'decode.log')
                with np.load(case/'decoded/decoded.npz',allow_pickle=False) as d:
                    checks={k:bool(np.array_equal(d[k],v)) for k,v in [('shape',x.shape),('indptr',x.indptr),('indices',x.indices),('values',x.data)]}
                checks['metadata']=(case/'decoded/metadata.json').read_bytes()==meta
                dec=read(case/'decode.json')
                if not all(checks.values()) or dec['value_cdf_sha256']!=row['value_cdf_sha256']:raise ValueError('source/CDF exactness')
                row.update(status='success',checks=checks);(case/'decoded/decoded.npz').unlink()
            except Exception as e:row.update(error=str(e),unverified_package_bytes=row['package_bytes'],package_bytes=None)
            dump(case/'result.json',row);records.append(row);print(f'{sid} {method} {row["status"]} {len(records)}/{len(samples)*len(METHODS)}',flush=True)
    dump(out/'results.json',records);dump(out/'completion.json',{'expected':len(samples)*len(METHODS),'success':sum(r['status']=='success' for r in records)})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output');p.add_argument('--smoke',action='store_true');p.add_argument('--worker',choices=['encode','decode']);p.add_argument('--sample');p.add_argument('--method',choices=METHODS);p.add_argument('--package');p.add_argument('--result');a=p.parse_args()
    if a.worker=='decode':source_guard();dump(Path(a.result),decode(Path(a.package),Path(a.output)))
    elif a.worker=='encode':
        cfg=config();sample=next(s for s in cfg['samples'] if s['id']==a.sample);dump(Path(a.result),encode(sample,a.method,Path(a.package)))
    else:main(a)
