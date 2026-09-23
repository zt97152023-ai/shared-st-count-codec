"""Standalone MDL archive codec with unchanged Shared support and tail members."""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
os.environ.setdefault('NUMBA_CACHE_DIR',str(ROOT/'numba_cache'))
import argparse,bz2,faulthandler,hashlib,json,zipfile,time
faulthandler.enable();faulthandler.dump_traceback_later(120,repeat=True)
import numpy as np
from scipy import sparse
from runtime import io047 as io,entropy,values,model as base,qshare_model as qm
import model

def stage(s):print(json.dumps(dict(stage=s,time=time.time())),flush=True)
def sha(b):return hashlib.sha256(b).hexdigest()
def archive(path):
 with zipfile.ZipFile(path) as z:
  names=z.namelist()
  if len(names)!=len(set(names)) or 'manifest.json' not in names:raise ValueError('members')
  man=json.loads(z.read('manifest.json'))
  if set(names)!=set(man['files'])|{'manifest.json'}:raise ValueError('manifest members')
  parts={}
  for name,d in man['files'].items():
   zi=z.getinfo(name)
   if zi.file_size>2**31 or zi.compress_type!=zipfile.ZIP_STORED:raise ValueError('budget/compression')
   b=z.read(name)
   if len(b)!=d['bytes'] or sha(b)!=d['sha256']:raise ValueError('integrity')
   parts[name]=b
 return man,parts
def write_archive(path,parts,info):
 m={**info,'files':{k:dict(bytes=len(v),sha256=sha(v)) for k,v in sorted(parts.items())}}
 with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_STORED) as z:
  for k,v in sorted({**parts,'manifest.json':io.jbytes(m)}.items()):
   zi=zipfile.ZipInfo(k,(1980,1,1,0,0,0));zi.external_attr=0o100644<<16;z.writestr(zi,v)
def graph_from(raw,n):
 b=bz2.decompress(raw)
 if len(b)!=n*24:raise ValueError('graph size')
 gr=np.frombuffer(b,'<i4').reshape(n,6).copy()
 for i,row in enumerate(gr):
  k=min(i,6)
  if np.any(row[:k]<0) or np.any(row[:k]>=i) or len(set(row[:k]))!=k or np.any(row[k:]!=-1):raise ValueError('graph')
 return gr
def support_model(parts,g):
 q=np.frombuffer(bz2.decompress(parts['base_probability.bz2']),'<u2');r=np.frombuffer(parts['shared_odds.u32'],'<u4')
 if q.shape!=(g,) or r.shape!=(56,) or np.any(q<1) or np.any(q>4095) or np.any(r<22) or np.any(r>195360063):raise ValueError('support model')
 bucket=np.searchsorted([1,4,16,64,256,1024,2048,3072,4096],q,side='right')-1;a=q.astype(np.uint64)[:,None];num=a*r.reshape(8,7)[bucket];den=num+(4096-a)*65536;out=np.repeat(q[:,None],49,axis=1);out[:,42:]=np.clip((4096*num+den//2)//den,1,4095);return out
EXPECTED={'metadata.bz2','support.rans','graph.bz2','base_probability.bz2','shared_odds.u32','value_q1.bz2','value_group.bz2','value_base_k.bz2','value_odds.u32','value_cond_k.bz2','values.rans'}
def tables(parts,g,mdl):
 groups=np.frombuffer(bz2.decompress(parts['value_group.bz2']),np.uint8)
 if groups.shape!=(g,) or np.any(groups>7):raise ValueError('tail labels')
 q=model.unpack(parts['value_q1.bz2'],g)[0] if mdl else qm.decode(parts['value_q1.bz2'],groups)
 f=np.frombuffer(bz2.decompress(parts['value_base_k.bz2']),'<u2').reshape(8,32);odds=np.frombuffer(parts['value_odds.u32'],'<u4').reshape(8,7);cond=np.frombuffer(bz2.decompress(parts['value_cond_k.bz2']),'<u2').reshape(8,7,32)
 return groups,base.tables(q,groups,f,odds,cond),odds

def encode(entry,arm,k,exceptions,path):
 stage('input_read');raw=sparse.load_npz(entry['counts']);x=io.from_parts(raw.shape,raw.indptr,raw.indices,raw.data);man,old=archive(entry['shared']);meta=Path(entry['metadata']).read_bytes()
 if raw.dtype!=np.int64 or io.csr_sha(x)!=man['canonical_sha256'] or meta!=bz2.decompress(old['metadata.bz2']) or set(old)!=EXPECTED:raise ValueError('source identity')
 if man.get('method')!='Shared-only' or man.get('q1_layout')!='QSH1-mode0-shared-v1':raise ValueError('reference schema')
 n,g=x.shape
 if n*g>300000000:raise ValueError('symbol budget')
 groups,_,odds=tables(old,g,False);stage('fit');qblob,q,diag=model.make(x,groups,odds,arm,k,exceptions);parts=dict(old);parts['value_q1.bz2']=qblob;groups,(binary,tail,cdf),_=tables(parts,g,True);gr=graph_from(parts['graph.bz2'],n);stage('value_encode');stream,nll,te,rb=values.encode(x.indptr,x.indices,x.data,gr,groups,binary,tail,cdf,True)
 if int(te)!=man['tail_events'] or int(rb)!=man['remainder_bits']:raise ValueError('tail mismatch')
 parts['values.rans']=stream.tobytes();info={k:v for k,v in man.items() if k!='files'};info.update(schema='mdl-singleton-count-v1',method=arm,q1_layout='MDG1-bz2-v1',singleton_K=int(k),exceptions_enabled=bool(exceptions),value_cdf_sha256=sha(binary.tobytes()+tail.tobytes()+cdf.tobytes()));write_archive(path,parts,info)
 if any(parts[key]!=old[key] for key in EXPECTED-{'value_q1.bz2','values.rans'}):raise ValueError('fixed member changed')
 return dict(total_bytes=Path(path).stat().st_size,archive_sha256=io.sha(path),modelblob_bytes=len(qblob),value_stream_bytes=len(stream),nll=float(nll),n_spots=n,n_genes=g,n_counts=n*g,n_nonzero=int(x.nnz),components={k:len(v) for k,v in parts.items()},framing_bytes=Path(path).stat().st_size-sum(map(len,parts.values())),value_cdf_sha256=info['value_cdf_sha256'],canonical_sha256=man['canonical_sha256'],metadata_sha256=sha(meta),diagnostics=diag)
def decode(path,out):
 stage('archive_read');man,p=archive(path);mdl=man.get('schema')=='mdl-singleton-count-v1'
 if set(p)!=EXPECTED or (not mdl and (man.get('method')!='Shared-only' or man.get('q1_layout')!='QSH1-mode0-shared-v1')):raise ValueError('schema')
 if mdl and (man.get('q1_layout')!='MDG1-bz2-v1' or man.get('method') not in ('GLOBAL_SHARED','PER_GENE','ADAPTIVE')):raise ValueError('mdl schema')
 if man['precision']!=12 or man['value_layout']!='singleton-K32-uniform-remainder;one-rANS;v1':raise ValueError('value schema')
 n,g=io.shape2(man['shape']);nnz=man['nnz']
 if type(nnz)!=int or not 0<=nnz<=min(100000000,n*g) or n*g>300000000:raise ValueError('budget')
 gr=graph_from(p['graph.bz2'],n);stage('support_decode');mask=entropy.decode(np.frombuffer(p['support.rans'],np.uint8),gr,support_model(p,g),n,g);ptr,idx=entropy.indices_from_support(mask,g,nnz);groups,(binary,tail,cdf),_=tables(p,g,mdl);h=sha(binary.tobytes()+tail.tobytes()+cdf.tobytes())
 if mdl and h!=man['value_cdf_sha256']:raise ValueError('CDF hash')
 stage('value_decode');val,te,rb=values.decode(np.frombuffer(p['values.rans'],np.uint8),ptr,idx,gr,groups,binary,tail,cdf,True);x=io.from_parts((n,g),ptr,idx,val);meta=bz2.decompress(p['metadata.bz2']);obj=json.loads(meta)
 if io.csr_sha(x)!=man['canonical_sha256'] or sha(meta)!=man['metadata_sha256'] or int(te)!=man['tail_events'] or int(rb)!=man['remainder_bits'] or len(obj['spot_ids'])!=n or len(obj['gene_ids'])!=g:raise ValueError('exactness')
 out=Path(out);out.mkdir();sparse.save_npz(out/'counts.npz',x);(out/'metadata.json').write_bytes(meta)
 return dict(exact=True,dtype=str(x.dtype),shape=list(x.shape),canonical_sha256=io.csr_sha(x),metadata_sha256=sha(meta),value_cdf_sha256=h,archive_only=True)
def guard(paths):
 roots=[str(Path(p).resolve()).lower().replace('\\','/') for p in paths]
 def hook(event,args):
  if event=='open' and isinstance(args[0],(str,bytes)):
   p=str(Path(os.fsdecode(args[0])).resolve()).lower().replace('\\','/')
   if any(p==r or p.startswith(r+'/') for r in roots):raise PermissionError('source forbidden')
 sys.addaudithook(hook)
 for p in paths:
  try:open(p,'rb')
  except PermissionError:pass
  else:raise AssertionError('guard probe failed')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('operation',choices=['encode','decode']);p.add_argument('--entry');p.add_argument('--arm');p.add_argument('--k',type=int,default=1);p.add_argument('--exceptions',action='store_true');p.add_argument('--archive',required=True);p.add_argument('--output');p.add_argument('--result',required=True);p.add_argument('--block',action='append',default=[]);a=p.parse_args()
 if a.operation=='decode':guard(a.block);r=decode(a.archive,a.output)
 else:r=encode(json.loads(Path(a.entry).read_text(encoding='utf8')),a.arm,a.k,a.exceptions,Path(a.archive))
 io.save(a.result,r)
