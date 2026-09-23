"""Paid singleton clustering; tail labels never replaced."""
import bz2,struct
import numpy as np
from runtime import model as base
from runtime import qshare_model as qm
HEADER=struct.Struct('<4sIBIB')

def pooled(n,a,labels,k,previous):
 c=previous.copy()
 for j in range(k):
  m=labels==j;N=int(n[m].sum());A=int(a[m].sum())
  if N:c[j]=min(4095,max(1,(4096*(2*A+1)+N+1)//(2*(N+1))))
 return c

def fit(n,a,k):
 g=len(n);order=np.lexsort((np.arange(g),(a+.5)/(n+1)));labels=np.empty(g,np.uint16);labels[order]=np.arange(g)*k//g;c=np.full(k,2048,dtype='<u2')
 for _ in range(20):
  c=pooled(n,a,labels,k,c);p=c.astype(np.float64)/4096;cost=-a[:,None]*np.log(p)-(n-a)[:,None]*np.log1p(-p);labels=cost.argmin(1).astype('<u2');labels[n==0]=0
 return pooled(n,a,labels,k,c),labels

def pack(centers,labels,mask,oldq):
 g=len(labels);raw=HEADER.pack(b'MDG1',g,1,len(centers),int(mask is not None))+np.asarray(centers,'<u2').tobytes()+np.asarray(labels,'<u4').tobytes()
 if mask is not None:raw+=np.packbits(mask,bitorder='little').tobytes()+np.asarray(oldq[mask],'<u2').tobytes()
 return bz2.compress(raw,compresslevel=9)
def unpack(blob,g):
 dec=bz2.BZ2Decompressor();limit=HEADER.size+4*g+2*max(g,32)+(g+7)//8+2*g
 try:raw=dec.decompress(blob,max_length=limit+1)
 except (OSError,EOFError) as e:raise ValueError('blob') from e
 if not dec.eof or dec.unused_data or len(raw)>limit or len(raw)<HEADER.size:raise ValueError('compressed framing')
 magic,G,version,k,flag=HEADER.unpack_from(raw)
 if magic!=b'MDG1' or G!=g or version!=1 or not 1<=k<=max(g,32) or flag not in (0,1):raise ValueError('header')
 pos=HEADER.size;need=pos+2*k+4*g
 if len(raw)<need:raise ValueError('short labels')
 centers=np.frombuffer(raw,'<u2',k,pos);labels=np.frombuffer(raw,'<u4',g,pos+2*k);pos=need
 if np.any(centers<1) or np.any(centers>4095) or np.any(labels>=k):raise ValueError('model domain')
 q=centers[labels].copy();exceptions=0
 if flag:
  mlen=(g+7)//8
  if len(raw)<pos+mlen:raise ValueError('short mask')
  mb=raw[pos:pos+mlen];pos+=mlen
  if g%8 and mb[-1]>>(g%8):raise ValueError('mask padding')
  mask=np.unpackbits(np.frombuffer(mb,np.uint8),bitorder='little')[:g].astype(bool);exceptions=int(mask.sum())
  if len(raw)!=pos+2*exceptions:raise ValueError('exception framing')
  v=np.frombuffer(raw,'<u2',exceptions,pos);pos+=2*exceptions
  if np.any(v<1) or np.any(v>4095):raise ValueError('exception domain')
  q[mask]=v
 if pos!=len(raw):raise ValueError('trailing bytes')
 return q,dict(k=k,exceptions=exceptions,cluster_sizes=np.bincount(labels,minlength=k).tolist())
def make(x,groups,odds,arm,k=1,exceptions=False):
 oldq,_,_,_,profile=base.base(x.indices,x.data,x.shape[1]);n=profile['npositive'];a=profile['nones'];g=len(n)
 if arm=='PER_GENE':centers=oldq;labels=np.arange(g,dtype='<u4')
 elif arm=='GLOBAL_SHARED':centers=pooled(n,a,np.zeros(g,np.uint16),1,np.array([2048],'<u2'));labels=np.zeros(g,np.uint16)
 elif arm=='ADAPTIVE':centers,labels=fit(n,a,k)
 else:raise ValueError('arm')
 mask=None
 if exceptions:
  _,safe,_=qm.bound(n,a,qm.cdf(oldq,groups,odds),qm.cdf(centers[labels],groups,odds));mask=safe>12
 blob=pack(centers,labels,mask,oldq);q,diag=unpack(blob,g)
 return blob,q,diag
