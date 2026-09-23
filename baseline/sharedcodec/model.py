"""56 shared odds corrections over fixed Q12 gene marginals."""
import math
import numpy as np
from numba import njit
import entropy

EDGES=np.array([1,4,16,64,256,1024,2048,3072,4096])
RMIN=int(math.floor(math.exp(-8)*65536+.5))
RMAX=int(math.floor(math.exp(8)*65536+.5))

def buckets(q0):
    q0=np.asarray(q0)
    if q0.ndim!=1 or np.any(q0<1) or np.any(q0>4095):raise ValueError('base Q12 bounds')
    return (np.searchsorted(EDGES,q0,side='right')-1).astype(np.int64)

@njit(cache=True)
def counts(m,graph,q0,group):
    seen=np.zeros((8,7,4096),np.int64);ones=np.zeros_like(seen)
    for i in range(6,len(m)):
        for g in range(len(q0)):
            k=0
            for j in range(6):k+=entropy.bit(m,graph[i,j],g)
            b=group[g];q=q0[g]
            seen[b,k,q]+=1;ones[b,k,q]+=entropy.bit(m,i,g)
    return seen,ones

def fit(m,graph,q0):
    group=buckets(q0);seen,ones=counts(m,graph,q0,group)
    multipliers=np.full((8,7),65536,dtype='<u4');betas=np.zeros((8,7))
    for b in range(8):
        for k in range(7):
            occupied=np.flatnonzero(seen[b,k])
            if not len(occupied):continue
            n=seen[b,k,occupied].astype(np.float64);y=ones[b,k,occupied].astype(np.float64)
            offset=np.log(occupied/(4096.-occupied))
            def derivative(beta):return float(np.sum(n/(1+np.exp(-(offset+beta)))-y)+beta)
            lo,hi=-8.,8.
            if derivative(lo)>=0:beta=lo
            elif derivative(hi)<=0:beta=hi
            else:
                for _ in range(48):
                    mid=(lo+hi)/2
                    if derivative(mid)>0:hi=mid
                    else:lo=mid
                beta=(lo+hi)/2
            betas[b,k]=beta;multipliers[b,k]=int(math.floor(math.exp(beta)*65536+.5))
    return multipliers,{'beta_min':float(betas.min()),'beta_max':float(betas.max()),
        'occupied_bucket_contexts':int(np.sum(seen.sum(axis=2)>0)), 'fitted_events':int(seen.sum()),
        'parameter_count':56,'multiplier_bytes':224}

def cdf(q0,multipliers):
    group=buckets(q0)
    if multipliers.shape!=(8,7) or multipliers.dtype.kind!='u' or np.any(multipliers<RMIN) or np.any(multipliers>RMAX):raise ValueError('multiplier bounds/shape')
    a=np.asarray(q0,dtype=np.uint64)[:,None];r=multipliers[group].astype(np.uint64)
    numerator=a*r;den=numerator+(4096-a)*np.uint64(65536)
    conditional=np.clip((np.uint64(4096)*numerator+den//2)//den,1,4095).astype('<u2')
    q=np.repeat(np.asarray(q0,dtype='<u2')[:,None],49,axis=1);q[:,42:49]=conditional
    return q
