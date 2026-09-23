"""Retained synthetic full archives, independent decode, deterministic repeat."""
import argparse,bz2,json,subprocess,sys
from pathlib import Path
import numpy as np
from scipy import sparse
import codec,model
from runtime import model as base,entropy,values,qshare_model as qm

def fixture(p,dense):
 x=sparse.csr_matrix(dense.astype(np.int64));n,g=x.shape;gr=np.full((n,6),-1,np.int32)
 for i in range(n):gr[i,:min(i,6)]=np.arange(max(0,i-6),i)
 q,groups,prior,f,prof=base.base(x.indices,x.data,g);odds,cond=base.conditional(x.indptr,x.indices,x.data,gr,q,groups,prior);centers=qm.share(prof['npositive'],prof['nones'],groups);qblob=qm.encode(centers,groups,q);q=qm.decode(qblob,groups);binary,tail,cdf=base.tables(q,groups,f,odds,cond);stream,_,te,rb=values.encode(x.indptr,x.indices,x.data,gr,groups,binary,tail,cdf,True);support,*_=entropy.encode(entropy.packed_support(x.indptr,x.indices,n,g),gr,np.full((g,49),2048,np.uint16),g);meta=codec.io.jbytes(dict(spot_ids=[str(i) for i in range(n)],gene_ids=[str(i) for i in range(g)]));parts={'metadata.bz2':bz2.compress(meta),'support.rans':support.tobytes(),'graph.bz2':bz2.compress(gr.astype('<i4').tobytes()),'base_probability.bz2':bz2.compress(np.full(g,2048,'<u2').tobytes()),'shared_odds.u32':np.full((8,7),65536,'<u4').tobytes(),'value_q1.bz2':qblob,'value_group.bz2':bz2.compress(groups.tobytes()),'value_base_k.bz2':bz2.compress(f.tobytes()),'value_odds.u32':odds.tobytes(),'value_cond_k.bz2':bz2.compress(cond.tobytes()),'values.rans':stream.tobytes()};man=dict(schema='qpatch-count-v1',method='Shared-only',q1_layout='QSH1-mode0-shared-v1',shape=[n,g],nnz=int(x.nnz),precision=12,value_layout='singleton-K32-uniform-remainder;one-rANS;v1',support_model='frozen-P2-shared-spatial-Q12-v1',tail_events=int(te),remainder_bits=int(rb),canonical_sha256=codec.io.csr_sha(x),metadata_sha256=codec.sha(meta));codec.write_archive(p/'shared.cnt',parts,man);sparse.save_npz(p/'counts.npz',x);(p/'metadata.json').write_bytes(meta);return x,dict(counts=str(p/'counts.npz'),metadata=str(p/'metadata.json'),shared=str(p/'shared.cnt'))

def main(output):
 out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False);records=[]
 for i,dense in enumerate([np.zeros((8,9),np.int64),np.ones((8,9),np.int64),np.random.default_rng(4).choice([0,1,2,257,2**32-1],(14,9))]):
  p=out/str(i);p.mkdir();x,e=fixture(p,dense)
  cases=[('GLOBAL_SHARED',1,False),('PER_GENE',9,False)]+[('ADAPTIVE',k,flag) for k in (1,2,4,8,16,32) for flag in (False,True)]
  for arm,k,flag in cases:
   d=p/f'{arm}_{k}_{int(flag)}';d.mkdir();r=codec.encode(e,arm,k,flag,d/'a.cnt');codec.encode(e,arm,k,flag,d/'b.cnt');assert codec.io.sha(d/'a.cnt')==codec.io.sha(d/'b.cnt');decoded=codec.decode(d/'a.cnt',d/'decoded');y=sparse.load_npz(d/'decoded/counts.npz');assert y.dtype==x.dtype and (y!=x).nnz==0;assert decoded['value_cdf_sha256']==r['value_cdf_sha256'];records.append(dict(fixture=i,arm=arm,K=k,exceptions=flag,sha256=codec.io.sha(d/'a.cnt')))
  # Independent archive-only decoder for each numerical domain, sources actively blocked.
  d=p/'fresh';cmd=[sys.executable,'-B',str(Path(codec.__file__)),'decode','--archive',str(p/'ADAPTIVE_32_1/a.cnt'),'--output',str(d),'--result',str(p/'fresh.json')]
  for v in e.values():cmd+=['--block',v]
  with (p/'fresh.log').open('wb') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
 # Strict model parser: truncation, trailing bytes, invalid label and mask padding.
 b=model.pack(np.array([2048],'<u2'),np.zeros(3,np.uint32),np.array([True,False,False]),np.array([1,2,3],'<u2'));raw=bz2.decompress(b)
 bad=[b[:-1],b+b'x',bz2.compress(raw+b'x')];v=bytearray(raw);v[model.HEADER.size+2:model.HEADER.size+6]=(9).to_bytes(4,'little');bad.append(bz2.compress(v));v=bytearray(raw);v[model.HEADER.size+2+12]|=128;bad.append(bz2.compress(v))
 for blob in bad:
  try:model.unpack(blob,3)
  except ValueError:pass
  else:raise AssertionError('corrupt model accepted')
 # PER_GENE uint32 mapping exceeds uint16 range.
 g=70000;blob=model.pack(np.full(g,2048,'<u2'),np.arange(g,dtype='<u4'),None,None);q,_=model.unpack(blob,g);assert q.shape==(g,)
 codec.io.save(out/'RESULT.json',dict(status='passed',cases=records,independent_fresh_decodes=3,repeat_archive_sha=True,parser_corruption_rejected=True,wide_gene_mapping=True,source_hashes={str(p):codec.io.sha(p) for p in Path(__file__).parent.glob('*.py')}))
 print('PASS',flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);main(p.parse_args().output)
