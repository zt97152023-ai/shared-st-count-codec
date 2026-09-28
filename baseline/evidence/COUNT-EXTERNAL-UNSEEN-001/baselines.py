"""Native frozen external adapters. Only full logical count recovery is ranked."""
import argparse,base64,bz2,hashlib,io,json,os,subprocess,sys,zipfile
from pathlib import Path
import numpy as np
import scipy.sparse as sp
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parents[1]
sys.path.insert(0,str(BASE.parent))
def j(o):return (json.dumps(o,sort_keys=True,ensure_ascii=False,separators=(',',':'))+'\n').encode()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,o):
    with Path(p).open('xb') as f:f.write(j(o))
def npbytes(a):
    f=io.BytesIO();np.save(f,a,allow_pickle=False);return f.getvalue()
def pack(out,parts,m):
    m['members']={k:{'bytes':len(v),'sha256':hashlib.sha256(v).hexdigest()} for k,v in parts.items()}
    with zipfile.ZipFile(out,'x',compression=zipfile.ZIP_STORED) as z:
        for name,blob in sorted({**parts,'manifest.json':j(m)}.items()):
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.external_attr=0o100644<<16;z.writestr(info,blob)
def unpack(path):
    with zipfile.ZipFile(path) as z:
        m=json.loads(z.read('manifest.json'));parts={k:z.read(k) for k in m['members']}
        assert set(z.namelist())==set(parts)|{'manifest.json'}
    for k,b in parts.items():assert len(b)==m['members'][k]['bytes'] and hashlib.sha256(b).hexdigest()==m['members'][k]['sha256']
    return m,parts
def bp():
    sys.path.insert(0,str(BASE/'evidence/COUNT-HYBRID-EXTERNAL-001/bpcells/python_lib'))
    import bpcells,bpcells.cpp
    return bpcells
def encode(method,source,out):
    source=source.resolve();out=out.resolve();out.mkdir(parents=True,exist_ok=False)
    x=sp.load_npz(source/'counts.npz');raw=(source/'metadata.json').read_bytes()
    assert x.dtype==np.int64 and x.has_canonical_format and x.data.min()>0 and x.data.max()<=2**32-1
    m=dict(schema='external-count-v1',method=method,shape=list(x.shape),dtype='int64',metadata_sha256=hashlib.sha256(raw).hexdigest())
    if method.startswith('BP_'):
        b=bp();transpose='spot' in method
        y=x.T.tocsc() if transpose else x.tocsc()
        p=np.argsort(np.asarray(y.mean(axis=1)).ravel(),kind='stable') if method.endswith('_mean') else None
        if p is not None:y=y[p,:].tocsc()
        os.chdir(out);b.cpp.write_matrix_dir_from_memory(y.astype(np.uint32),'matrix',True)
        (out/'metadata.bz2').write_bytes(bz2.compress(raw,9))
        if p is not None:(out/'permutation.bz2').write_bytes(bz2.compress(np.asarray(p,dtype='<u4').tobytes(),9))
        m.update(transpose=transpose,bpcells_version=b.__version__,native_rows=y.shape[0],native_cols=y.shape[1],sorted=p is not None)
        m['members']={p.relative_to(out).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in out.rglob('*') if p.is_file()}
        write(out/'manifest.json',m)
    elif method.startswith('IVCSC'):
        from baseline.ivcsc import adapter as a
        a.exchange_write(out/'exchange.csc',x)
        subprocess.run([str(a.EXE),'encode','exchange.csc','native.ivcsc'],cwd=out,check=True,timeout=600)
        a.write_archive(out/'archive.bin',out/'native.ivcsc',raw,x,'IVCSC_bz2' if method.endswith('bz2') else 'IVCSC')
    elif method in ('CSR_ZSTD19','CSC_ZSTD19'):
        import zstandard as zstd
        y=x.tocsr() if method.startswith('CSR') else x.tocsc();idx=y.indices.astype('<u4').copy()
        for lo,hi in zip(y.indptr[:-1],y.indptr[1:]):
            if hi>lo+1:idx[lo+1:hi]=np.diff(y.indices[lo:hi])
        f=io.BytesIO();np.savez(f,indptr=y.indptr.astype('<u4'),indices=idx,values=y.data.astype('<u4'))
        parts={'matrix.zst':zstd.ZstdCompressor(level=19,threads=0).compress(f.getvalue()),'metadata.bz2':bz2.compress(raw,9)}
        m['layout']='csr' if method.startswith('CSR') else 'csc';pack(out/'archive.bin',parts,m)
    elif method=='H5AD_GZIP4':
        import anndata as ad
        meta=json.loads(raw);a=ad.AnnData(x.astype(np.uint32));a.obs_names=meta['spot_ids'];a.var_names=meta['gene_ids']
        a.obsm['spatial']=np.frombuffer(base64.b64decode(meta['coordinates_base64']),dtype=meta['coordinates_dtype']).reshape(meta['coordinates_shape']).copy()
        a.write_h5ad(out/'matrix.h5ad',compression='gzip',compression_opts=4)
        m['members']={'matrix.h5ad':dict(bytes=(out/'matrix.h5ad').stat().st_size,sha256=sha(out/'matrix.h5ad'))};write(out/'manifest.json',m)
    else:raise ValueError(method)
def decode(method,source,out):
    source=source.resolve();out=out.resolve()
    blocked=(ROOT/'inputs').resolve()
    def guard(event,args):
        if event=='open' and args and isinstance(args[0],(str,bytes,os.PathLike)):
            p=Path(os.fsdecode(args[0])).resolve()
            if p==blocked or blocked in p.parents:raise PermissionError('reference blocked')
    sys.addaudithook(guard)
    try:open(blocked/'probe','rb')
    except PermissionError:pass
    else:raise RuntimeError('source guard')
    if method.startswith('IVCSC'):
        from baseline.ivcsc import adapter as a
        a.decode(source/'archive.bin',out)
        with np.load(out/'decoded.npz') as f:x=sp.csr_matrix((f['values'],f['indices'],f['indptr']),shape=tuple(f['shape']))
        sp.save_npz(out/'counts.npz',x.astype(np.int64),compressed=False);return
    if method.startswith('BP_') or method=='H5AD_GZIP4':
        m=json.loads((source/'manifest.json').read_bytes())
        for k,v in m['members'].items():assert (source/k).stat().st_size==v['bytes'] and sha(source/k)==v['sha256']
    if method.startswith('BP_'):
        b=bp();os.chdir(source)
        y=sp.hstack(b.cpp.load_matrix_dir_subset('matrix',None,list(range(m['native_cols'])),1)).tocsc()
        assert y.shape==(m['native_rows'],m['native_cols'])
        if m['sorted']:
            p=np.frombuffer(bz2.decompress((source/'permutation.bz2').read_bytes()),dtype='<u4');y=y[np.argsort(p),:]
        x=y.T.tocsr() if m['transpose'] else y.tocsr();raw=bz2.decompress((source/'metadata.bz2').read_bytes())
    elif method in ('CSR_ZSTD19','CSC_ZSTD19'):
        import zstandard as zstd
        m,parts=unpack(source/'archive.bin')
        with np.load(io.BytesIO(zstd.ZstdDecompressor().decompress(parts['matrix.zst'])),allow_pickle=False) as f:
            ptr=f['indptr'];idx=f['indices'].copy();values=f['values'].astype(np.int64)
        for lo,hi in zip(ptr[:-1],ptr[1:]):idx[lo:hi]=np.cumsum(idx[lo:hi],dtype=np.uint64)
        cls=sp.csr_matrix if m['layout']=='csr' else sp.csc_matrix
        x=cls((values,idx,ptr),shape=m['shape']).tocsr();raw=bz2.decompress(parts['metadata.bz2'])
    elif method=='H5AD_GZIP4':
        # Read the standard h5ad CSR layout directly.  Importing anndata pulls
        # zarr entry-point discovery into the decoder and fails on the pinned
        # Windows environment; this preserves the historical representation
        # and metadata byte schema while removing that optional dependency.
        import h5py
        def texts(ds):
            out=[]
            for v in ds[...].tolist():
                if isinstance(v, bytes): out.append(v.decode('utf-8'))
                else: out.append(str(v))
            return out
        with h5py.File(source/'matrix.h5ad','r') as h:
            gx=h['X']
            if isinstance(gx,h5py.Group) and gx.attrs.get('encoding-type',b'') in ('csr_matrix',b'csr_matrix'):
                shape=tuple(int(v) for v in gx.attrs['shape'])
                x=sp.csr_matrix((np.asarray(gx['data']),np.asarray(gx['indices']),np.asarray(gx['indptr'])),shape=shape)
            else:
                x=sp.csr_matrix(np.asarray(gx))
            spots=texts(h['obs']['_index']); genes=texts(h['var']['_index']); c=np.asarray(h['obsm']['spatial'])
        raw=j(dict(schema='047-exact-metadata-v1',spot_ids=spots,gene_ids=genes,
            coordinates_dtype=c.dtype.str,coordinates_shape=list(c.shape),coordinates_base64=base64.b64encode(c.tobytes()).decode()))
    else:raise ValueError(method)
    x=x.astype(np.int64);x.sort_indices()
    assert list(x.shape)==m['shape'] and hashlib.sha256(raw).hexdigest()==m['metadata_sha256']
    out.mkdir(parents=True,exist_ok=False);sp.save_npz(out/'counts.npz',x,compressed=False);(out/'metadata.json').write_bytes(raw)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage');p.add_argument('method');p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    (encode if a.stage=='encode' else decode)(a.method,a.source,a.output)
