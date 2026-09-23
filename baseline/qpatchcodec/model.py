"""Paid per-gene singleton rates and tail scales, shared conditional corrections."""
import math
import numpy as np
from numba import njit

BOUNDS=(1,2,4,8,16,64,256)

@njit(cache=True)
def gene_counts(idx,val,genes):
    n=np.zeros(genes,np.int64);one=np.zeros(genes,np.int64)
    tail_sum=np.zeros(genes,np.int64);hist=np.zeros((genes,32),np.int64)
    for j in range(len(val)):
        g=idx[j];x=int(val[j]);n[g]+=1
        if x==1:one[g]+=1
        else:
            y=x-1;tail_sum[g]+=y;k=0
            while y>1:y>>=1;k+=1
            hist[g,k]+=1
    return n,one,tail_sum,hist

@njit(cache=True)
def find_value(ptr,idx,val,row,g):
    lo=ptr[row];hi=ptr[row+1]
    while lo<hi:
        mid=(lo+hi)//2
        if idx[mid]<g:lo=mid+1
        else:hi=mid
    if lo<ptr[row+1] and idx[lo]==g:return int(val[lo])
    return 0

@njit(cache=True)
def context(ptr,idx,val,graph,row,g):
    if row<6:return 7
    s=np.int64(0)
    for j in range(6):s+=find_value(ptr,idx,val,graph[row,j],g)
    if s==0:return 0
    if s<12:return 1
    if s<24:return 2
    if s<48:return 3
    if s<96:return 4
    if s<384:return 5
    return 6

def quantize(p):
    p=np.asarray(p,np.float64)
    if p.shape!=(32,) or np.any(p<0) or not np.all(np.isfinite(p)) or abs(p.sum()-1)>1e-10:raise ValueError('distribution')
    raw=4064*p;floor=np.floor(raw).astype(np.int64);freq=floor+1
    remaining=4096-int(freq.sum())
    if not 0<=remaining<=32:raise ValueError('rounding')
    order=np.argsort(-(raw-floor),kind='stable');freq[order[:remaining]]+=1
    return freq.astype('<u2')

def base(idx,val,genes):
    n,one,tail_sum,hist=gene_counts(idx,val,genes)
    global_one=(int(one.sum())+.5)/(int(n.sum())+1)
    q=np.clip(np.floor(4096*(one+.5+16*global_one)/(n+17)+.5),1,4095).astype('<u2')
    groups=np.zeros(genes,np.uint8)
    for g in range(genes):
        nt=int(n[g]-one[g])
        if nt:
            groups[g]=next((b for b,u in enumerate(BOUNDS) if int(tail_sum[g])<=u*nt),7)
    pooled=np.zeros((8,32),np.int64)
    np.add.at(pooled,groups,hist)
    prob=(pooled+1/32)/(pooled.sum(axis=1)[:,None]+1)
    freq=np.stack([quantize(p) for p in prob])
    profile=dict(npositive=n,nones=one,tail_sum=tail_sum,tail_hist=hist,group=groups)
    return q,groups,prob,freq,profile

@njit(cache=True)
def conditional_counts(ptr,idx,val,graph,q,groups):
    seen=np.zeros((8,7,4096),np.int64);one=np.zeros_like(seen);tail=np.zeros((8,7,32),np.int64)
    for row in range(6,len(ptr)-1):
        for j in range(ptr[row],ptr[row+1]):
            g=idx[j];b=groups[g];c=context(ptr,idx,val,graph,row,g);prior=q[g]
            seen[b,c,prior]+=1;x=int(val[j])
            if x==1:one[b,c,prior]+=1
            else:
                y=x-1;k=0
                while y>1:y>>=1;k+=1
                tail[b,c,k]+=1
    return seen,one,tail

def conditional(ptr,idx,val,graph,q,groups,prior):
    seen,one,tail=conditional_counts(ptr,idx,val,graph,q,groups)
    odds=np.full((8,7),65536,dtype='<u4');freq=np.empty((8,7,32),'<u2')
    for b in range(8):
        for c in range(7):
            occupied=np.flatnonzero(seen[b,c])
            if len(occupied):
                n=seen[b,c,occupied].astype(float);a=one[b,c,occupied].astype(float)
                offset=np.log(occupied/(4096.-occupied))
                def derivative(beta):return float(np.sum(n/(1+np.exp(-(offset+beta)))-a)+beta)
                lo,hi=-8.,8.
                if derivative(lo)>=0:beta=lo
                elif derivative(hi)<=0:beta=hi
                else:
                    for _ in range(48):
                        mid=(lo+hi)/2
                        if derivative(mid)>0:hi=mid
                        else:lo=mid
                    beta=(lo+hi)/2
                odds[b,c]=int(math.floor(math.exp(beta)*65536+.5))
            prob=(tail[b,c]+16*prior[b])/(int(tail[b,c].sum())+16)
            freq[b,c]=quantize(prob)
    return odds,freq

def tables(q,groups,base_freq,odds=None,conditional_freq=None):
    if q.ndim!=1 or groups.shape!=q.shape or np.any(q<1) or np.any(q>4095) or np.any(groups>7):raise ValueError('gene model')
    if base_freq.shape!=(8,32):raise ValueError('base tail shape')
    tail=np.repeat(base_freq[:,None,:],8,axis=1)
    binary=np.repeat(q[:,None],8,axis=1).astype('<u2')
    if odds is not None:
        if odds.shape!=(8,7) or np.any(odds<22) or np.any(odds>int(math.floor(math.exp(8)*65536+.5))):raise ValueError('odds')
        if conditional_freq.shape!=(8,7,32):raise ValueError('conditional shape')
        a=q.astype(np.uint64)[:,None];r=odds[groups].astype(np.uint64)
        num=a*r;den=num+(4096-a)*65536
        binary[:,:7]=np.clip((4096*num+den//2)//den,1,4095).astype('<u2')
        tail[:,:7]=conditional_freq
    if np.any(tail<1) or np.any(tail.astype(np.uint32).sum(axis=2)!=4096):raise ValueError('tail frequencies')
    cumulative=np.zeros((8,8,33),np.uint32);cumulative[:,:,1:]=np.cumsum(tail,axis=2,dtype=np.uint32)
    return binary,tail,cumulative
