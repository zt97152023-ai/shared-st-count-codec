"""Official native IVCSC adapter; common metadata and physical archive accounting."""
import bz2
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
import zipfile
import numpy as np
import psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pilot'))
import io047 as io

HERE=Path(__file__).resolve().parent
EXE=HERE/'ivcsc.exe'
COMMIT='ab406eb51dd2ea358eba5236720fb5d3acdaa6e5'
METHODS=['IVCSC','IVCSC_bz2']

def dump(path,obj):
    with Path(path).open('x',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2)

def execute(cmd,cwd,log,seconds=600,rss_gib=12):
    start=time.perf_counter();peak=0
    env=os.environ.copy()
    for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:env[key]='1'
    with Path(log).open('xb') as output:
        p=subprocess.Popen(cmd,cwd=cwd,env=env,stdout=output,stderr=subprocess.STDOUT)
        while p.poll() is None:
            try:
                process=psutil.Process(p.pid);members=[process]+process.children(recursive=True)
                peak=max(peak,sum(q.memory_info().rss for q in members if q.is_running()))
            except psutil.NoSuchProcess:pass
            if peak>rss_gib*2**30 or time.perf_counter()-start>seconds:
                for child in psutil.Process(p.pid).children(recursive=True):
                    try:child.kill()
                    except psutil.NoSuchProcess:pass
                p.kill();p.wait();raise RuntimeError('worker resource ceiling')
            time.sleep(.1)
    if p.returncode:raise RuntimeError(f'worker exit {p.returncode}; {log}')
    return {'process_seconds':time.perf_counter()-start,'sampled_peak_tree_rss_bytes':peak}

def exchange_write(path,x):
    c=x.tocsc();c.sort_indices()
    with Path(path).open('xb') as f:
        f.write(struct.pack('<4I',0x49564331,*c.shape,c.nnz))
        for a in [c.indptr,c.indices,c.data]:f.write(np.asarray(a,dtype='<u4').tobytes())

def exchange_read(path):
    with Path(path).open('rb') as f:
        h=f.read(16)
        if len(h)!=16:raise ValueError('exchange header truncated')
        magic,n,g,k=struct.unpack('<4I',h)
        if magic!=0x49564331 or max(n,g)>io.MAX_DIM or k>io.MAX_NNZ:raise ValueError('invalid exchange header')
        if Path(path).stat().st_size!=16+4*(g+1+2*k):raise ValueError('exchange size mismatch')
        ptr=np.fromfile(f,dtype='<u4',count=g+1);idx=np.fromfile(f,dtype='<u4',count=k);val=np.fromfile(f,dtype='<u4',count=k)
    return io.from_parts((n,g),ptr,idx,val,encoding='csc_matrix')

def write_archive(path,native,metadata,x,method):
    if method not in METHODS:raise ValueError('unknown method')
    data=Path(native).read_bytes();parts={'metadata.bz2':bz2.compress(metadata,9)}
    parts['matrix.ivcsc' if method=='IVCSC' else 'matrix.ivcsc.bz2']=data if method=='IVCSC' else bz2.compress(data,9)
    info={'schema':'count-e1-v1','method':method,'shape':list(x.shape),'nnz':int(x.nnz),'upstream_commit':COMMIT,
          'orientation':'CSC original spots-by-genes','value_dtype':'uint32','index_dtype':'uint32',
          'canonical_sha256':io.csr_sha(x),'metadata_sha256':hashlib.sha256(metadata).hexdigest(),
          'files':{name:{'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest()} for name,blob in parts.items()}}
    with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_STORED) as z:
        for name,blob in sorted({**parts,'manifest.json':io.jbytes(info)}.items()):
            zi=zipfile.ZipInfo(name,(1980,1,1,0,0,0));zi.external_attr=0o100644<<16;z.writestr(zi,blob)
    components={k:len(v) for k,v in parts.items()}
    return {'package_bytes':Path(path).stat().st_size,'package_sha256':io.sha(path),'components':components,
            'framing_and_manifest_bytes':Path(path).stat().st_size-sum(components.values()),
            'native_file_bytes':len(data),'canonical_sha256':info['canonical_sha256']}

def source_guard():
    def guard(event,args):
        if event=='open' and args and isinstance(args[0],(str,bytes,Path)):
            name=str(args[0]).lower().replace('\\','/')
            if '.h5ad' in name or '/hestdata/' in name:raise PermissionError('decoder source access forbidden')
    sys.addaudithook(guard)

def decode(package,out):
    out=Path(out).resolve();out.mkdir(exist_ok=False)
    with zipfile.ZipFile(package) as z:
        names=z.namelist()
        if len(names)!=len(set(names)):raise ValueError('duplicate archive members')
        info=json.loads(z.read('manifest.json'))
        method=info['method']
        if method not in METHODS or info['schema']!='count-e1-v1' or info['upstream_commit']!=COMMIT:raise ValueError('archive schema')
        key='matrix.ivcsc' if method=='IVCSC' else 'matrix.ivcsc.bz2'
        if set(names)!={'manifest.json','metadata.bz2',key} or set(info['files'])!={'metadata.bz2',key}:raise ValueError('archive entries')
        parts={}
        for name,expected in info['files'].items():
            if expected['bytes']>2**31:raise ValueError('member budget')
            blob=z.read(name)
            if len(blob)!=expected['bytes'] or hashlib.sha256(blob).hexdigest()!=expected['sha256']:raise ValueError('member integrity')
            parts[name]=blob
    metadata=bz2.decompress(parts['metadata.bz2'])
    if hashlib.sha256(metadata).hexdigest()!=info['metadata_sha256']:raise ValueError('metadata hash')
    native=parts[key] if method=='IVCSC' else bz2.decompress(parts[key])
    if len(native)>2**31:raise ValueError('native budget')
    (out/'matrix.ivcsc').write_bytes(native)
    timing=execute([str(EXE),'decode','matrix.ivcsc','decoded.csc'],out,out/'native_decode.log')
    x=exchange_read(out/'decoded.csc')
    if list(x.shape)!=info['shape'] or x.nnz!=info['nnz'] or io.csr_sha(x)!=info['canonical_sha256']:raise ValueError('canonical mismatch')
    np.savez(out/'decoded.npz',shape=x.shape,indptr=x.indptr,indices=x.indices,values=x.data)
    (out/'metadata.json').write_bytes(metadata)
    return {'archive_only':True,'canonical_sha256':io.csr_sha(x),'native_decode':timing}
