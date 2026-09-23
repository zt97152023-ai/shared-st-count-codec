"""COUNT-E1-001 native archive codecs. Decoder requires only archive and libraries."""
import base64
import bz2
import hashlib
import json
import sys
import time
import zipfile
from pathlib import Path
import numpy as np
from scipy import sparse
import h5py
import numba
import io047 as io
import entropy

# Load installed numpy/scipy first: the legacy directory contains other versions.
sys.path.append(r'F:\STCompressBench_CONTINUATION\.runtime\count_native_028')
from pcodec import standalone, ChunkConfig

def digest(b): return hashlib.sha256(b).hexdigest()

def pcompress(a):
    return bytes(standalone.simple_compress(np.ascontiguousarray(a,dtype='<u4'),ChunkConfig(compression_level=8)))

def pdecompress(b,expected_len):
    raw=standalone.simple_decompress(b)
    if raw is None:
        if expected_len==0 and b==pcompress(np.array([],dtype='<u4')):
            return np.array([],dtype='<u4')
        raise ValueError('unexpected empty Pcodec stream')
    a=np.asarray(raw)
    if a.dtype.kind!='u' or a.ndim!=1: raise ValueError('unexpected Pcodec array')
    if len(a)!=expected_len: raise ValueError('Pcodec array length mismatch')
    return a

def graph_for(coords, kind, seed=None):
    n=len(coords); graph=np.full((n,6),-1,np.int32)
    if kind=='S0_gene': return graph
    xy=coords.astype(np.float64)
    if seed is not None: xy=xy[np.random.default_rng(seed).permutation(n)]
    for i in range(1,n):
        take=min(i,6)
        if kind=='S1_prefix':
            js=np.arange(i-take,i)
        else:
            d=((xy[:i]-xy[i])**2).sum(axis=1)
            js=np.lexsort((np.arange(i),d))[:take]
        graph[i,:take]=js
    return graph

def validate_graph(graph,n):
    if graph.shape!=(n,6) or graph.dtype.kind!='i': raise ValueError('graph shape/type')
    for i,row in enumerate(graph):
        k=min(i,6)
        if np.any(row[:k]<0) or np.any(row[:k]>=i) or len(set(map(int,row[:k])))!=k or np.any(row[k:]!=-1):
            raise ValueError('noncausal/invalid predecessor graph')

def gaps(x):
    a=x.indices.astype('<u4').copy()
    for i in range(x.shape[0]):
        lo,hi=x.indptr[i:i+2]
        if hi>lo+1: a[lo+1:hi]=np.diff(x.indices[lo:hi])
    return a

def write_archive(path,parts,info):
    manifest={**info,'files':{k:{'bytes':len(v),'sha256':digest(v)} for k,v in sorted(parts.items())}}
    with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_STORED) as z:
        for name,b in sorted({**parts,'manifest.json':io.jbytes(manifest)}.items()):
            zi=zipfile.ZipInfo(name,(1980,1,1,0,0,0));zi.external_attr=0o100644<<16
            z.writestr(zi,b)
    return {k:len(v) for k,v in parts.items()}

def read_archive(path):
    with zipfile.ZipFile(path) as z:
        if len(z.namelist())!=len(set(z.namelist())): raise ValueError('duplicate zip entries')
        man=json.loads(z.read('manifest.json'))
        if man['schema']!='count-e1-v1' or set(z.namelist())!=set(man['files'])|{'manifest.json'}:
            raise ValueError('schema/member mismatch')
        n,g=map(int,man['shape'])
        if n<1 or g<1 or n>2000000 or g>2000000 or n*g>300000000: raise ValueError('matrix exceeds pilot budget')
        parts={}
        for name,f in man['files'].items():
            if f['bytes']>2**31: raise ValueError('member exceeds pilot budget')
            b=z.read(name)
            if len(b)!=f['bytes'] or digest(b)!=f['sha256']: raise ValueError('payload integrity failure')
            parts[name]=b
    return man,parts

def encode_case(source,method,target):
    begin=time.perf_counter()
    x,_=io.read_x(source);meta=io.metadata(source,x.shape)
    coords=np.frombuffer(base64.b64decode(meta['coordinates_base64']),np.dtype(meta['coordinates_dtype'])).reshape(meta['coordinates_shape'])
    if coords.shape!=(x.shape[0],2) or not np.isfinite(coords).all(): raise ValueError('requires finite 2D coordinates')
    if x.shape[0]*x.shape[1]>300000000: raise ValueError('pilot symbols limit')
    parts={'metadata.bz2':bz2.compress(io.jbytes(meta),9)}
    info={'schema':'count-e1-v1','shape':list(x.shape),'nnz':int(x.nnz),'method':method,'precision':12,'value_codec':'csr-u32-bzip2-level9' if method=='CSR_bz2' else 'pcodec1.0.3-level8',
          'canonical_sha256':io.csr_sha(x),'metadata_sha256':digest(io.jbytes(meta))}
    stats={'source_read_seconds':time.perf_counter()-begin}
    start=time.perf_counter()
    if method=='CSR_bz2':
        parts['csr.bz2']=bz2.compress(io.frame(io.csr_streams(x)),9)
    else:
        parts['values.pco']=pcompress(x.data)
        if method=='Pcodec':
            parts['lengths.pco']=pcompress(np.diff(x.indptr))
            parts['gaps.pco']=pcompress(gaps(x))
        else:
            seed=int(method.rsplit('_',1)[1]) if method.startswith('S2_shuffle_') else None
            graph=graph_for(coords,method,seed)
            if method!='S0_gene': validate_graph(graph,x.shape[0])
            if method!='S0_gene':
                xy=coords.astype(np.float64)
                if seed is not None: xy=xy[np.random.default_rng(seed).permutation(len(xy))]
                rows,cols=np.nonzero(graph>=0)
                distance=np.sqrt(((xy[rows]-xy[graph[rows,cols]])**2).sum(axis=1))
                stats['predecessor_distance_in_stored_coordinate_units']={'mean':float(distance.mean()) if len(distance) else 0.,'median':float(np.median(distance)) if len(distance) else 0.,'max':float(distance.max(initial=0))}
            if method.startswith('S2'):
                parts['graph.bz2']=bz2.compress(graph.astype('<i4').tobytes(),9)
            m=entropy.packed_support(x.indptr,x.indices,*x.shape)
            fit_start=time.perf_counter()
            q=entropy.fit(m,graph,x.shape[1],method=='S0_gene')
            stats['fit_seconds']=time.perf_counter()-fit_start
            parts['probability.bz2']=bz2.compress(q.astype('<u2').tobytes(),9)
            blob,nll=entropy.encode(m,graph,q,x.shape[1])
            parts['support.rans']=blob.tobytes()
            stats['support_nll_bits']=nll
            stats['context_neighbor_counts']={str(k):int(np.sum(np.sum(graph>=0,axis=1)==k)) for k in range(7)}
    stats['encode_seconds_including_fit']=time.perf_counter()-start
    stats['components']=write_archive(target,parts,info)
    stats['package_bytes']=target.stat().st_size
    stats['framing_and_manifest_bytes']=stats['package_bytes']-sum(stats['components'].values())
    stats['canonical_sha256']=info['canonical_sha256']
    stats['package_sha256']=io.sha(target)
    return stats

def decode_case(path,out):
    start=time.perf_counter();man,parts=read_archive(path)
    n,g=map(int,man['shape']);nnz=int(man['nnz']);method=man['method']
    if not 0<=nnz<=n*g: raise ValueError('invalid nnz')
    meta=json.loads(bz2.decompress(parts['metadata.bz2']))
    if digest(io.jbytes(meta))!=man['metadata_sha256']: raise ValueError('metadata mismatch')
    if len(meta['spot_ids'])!=n or len(meta['gene_ids'])!=g: raise ValueError('label dimensions')
    coord=np.frombuffer(base64.b64decode(meta['coordinates_base64']),np.dtype(meta['coordinates_dtype'])).reshape(meta['coordinates_shape'])
    if coord.shape!=(n,2) or not np.isfinite(coord).all(): raise ValueError('coordinates invalid')
    if method=='CSR_bz2':
        x=io.read_csr_streams(io.unframe(bz2.decompress(parts['csr.bz2'])))
    else:
        values=pdecompress(parts['values.pco'],nnz)
        if len(values)!=nnz or np.any(values==0): raise ValueError('positive count stream mismatch')
        if method=='Pcodec':
            lengths=pdecompress(parts['lengths.pco'],n); gap=pdecompress(parts['gaps.pco'],nnz)
            if len(lengths)!=n or int(lengths.astype(np.uint64).sum())!=nnz or len(gap)!=nnz: raise ValueError('Pcodec lengths')
            ptr=np.r_[0,np.cumsum(lengths,dtype=np.int64)];idx=np.empty(nnz,np.int64)
            for i in range(n):
                lo,hi=ptr[i:i+2];idx[lo:hi]=np.cumsum(gap[lo:hi],dtype=np.int64)
        else:
            if method not in ['S0_gene','S1_prefix','S2_spatial','S2_shuffle_11','S2_shuffle_29','S2_shuffle_47']: raise ValueError('unknown method')
            if method.startswith('S2'):
                graph=np.frombuffer(bz2.decompress(parts['graph.bz2']),'<i4').reshape(n,6).copy()
            else: graph=graph_for(coord,method)
            if method!='S0_gene': validate_graph(graph,n)
            q=np.frombuffer(bz2.decompress(parts['probability.bz2']),'<u2').reshape(g,1 if method=='S0_gene' else 49).copy()
            if np.any(q<1) or np.any(q>=4096): raise ValueError('invalid binary probability')
            m=entropy.decode(np.frombuffer(parts['support.rans'],np.uint8),graph,q,n,g)
            ptr,idx=entropy.indices_from_support(m,g,nnz)
        x=io.from_parts((n,g),ptr,idx,values)
    if x.shape!=(n,g) or x.nnz!=nnz or io.csr_sha(x)!=man['canonical_sha256']: raise ValueError('decoded canonical mismatch')
    out.mkdir(exist_ok=False)
    np.savez(out/'decoded.npz',shape=np.array(x.shape),indptr=x.indptr,indices=x.indices,values=x.data)
    (out/'metadata.json').write_bytes(io.jbytes(meta))
    return {'canonical_sha256':io.csr_sha(x),'metadata_sha256':digest(io.jbytes(meta)),'decode_seconds_including_export':time.perf_counter()-start,'archive_only':True}

def warmup():
    x=sparse.csr_matrix(np.array([[0,2,0],[3,0,1]],np.int64))
    m=entropy.packed_support(x.indptr,x.indices,*x.shape);graph=graph_for(np.zeros((2,2)),'S1_prefix')
    for flag in (True,False):
        q=entropy.fit(m,graph,3,flag);b,_=entropy.encode(m,graph,q,3);d=entropy.decode(b,graph,q,2,3)
        entropy.indices_from_support(d,3,3)

def forbid_source_access():
    def hook(event,args):
        if event=='open' and isinstance(args[0],(str,bytes)):
            p=str(args[0]).lower().replace('\\','/')
            if p.endswith('.h5ad') or '/hestdata/' in p:
                raise PermissionError('archive-only decoder forbids source-data access')
    sys.addaudithook(hook)
