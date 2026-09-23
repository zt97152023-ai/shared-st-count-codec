"""Integer binary rANS; row-major causal contexts, packed support storage."""
import math
import numpy as np
from numba import njit

PREC = 12
TOTAL = 1 << PREC
LOWER = 1 << 23

@njit(cache=True)
def bit(m, i, g):
    return (m[i, g >> 3] >> (g & 7)) & 1

@njit(cache=True)
def packed_support(ptr, idx, n, g):
    m = np.zeros((n, (g+7)//8), np.uint8)
    for i in range(n):
        for j in range(ptr[i], ptr[i+1]):
            c = idx[j]
            m[i, c >> 3] |= np.uint8(1 << (c & 7))
    return m

@njit(cache=True)
def context(m, graph, i, g):
    n = 0
    k = 0
    for j in range(graph.shape[1]):
        p = graph[i, j]
        if p >= 0:
            n += 1
            k += bit(m, p, g)
    return n*7+k

@njit(cache=True)
def fit(m, graph, genes, gene_only):
    nrows = len(m)
    contexts = 1 if gene_only else 49
    seen = np.zeros((genes, contexts), np.int64)
    ones = np.zeros((genes, contexts), np.int64)
    for i in range(nrows):
        for g in range(genes):
            c = 0 if gene_only else context(m, graph, i, g)
            seen[g,c] += 1
            ones[g,c] += bit(m,i,g)
    q = np.zeros((genes,contexts), np.uint16)
    for g in range(genes):
        prior = (ones[g].sum()+0.5)/(nrows+1.0)
        for c in range(contexts):
            p = prior if gene_only else (ones[g,c]+8.0*prior)/(seen[g,c]+8.0)
            q[g,c] = max(1,min(TOTAL-1,int(p*TOTAL+0.5)))
    return q

@njit(cache=True)
def encode(m, graph, q, genes):
    # A binary symbol has at most 12 information bits: two bytes/symbol suffice.
    out=np.empty(m.shape[0]*genes*2+8,np.uint8)
    used=0
    state=np.uint64(LOWER)
    nll=0.0
    for i in range(len(m)-1,-1,-1):
        for g in range(genes-1,-1,-1):
            c=0 if q.shape[1]==1 else context(m,graph,i,g)
            p1=int(q[g,c]); p0=TOTAL-p1
            one=bit(m,i,g)
            freq=np.uint64(p1 if one else p0)
            start=np.uint64(p0 if one else 0)
            nll += PREC-math.log2(float(freq))
            threshold=np.uint64((LOWER >> PREC) << 8)*freq
            while state >= threshold:
                out[used]=np.uint8(state & np.uint64(255)); used+=1
                state >>= np.uint64(8)
            state=((state//freq)<<np.uint64(PREC))+(state%freq)+start
    result=np.empty(used+4,np.uint8)
    for k in range(4): result[k]=np.uint8((state >> np.uint64(k*8)) & np.uint64(255))
    for j in range(used): result[4+j]=out[used-1-j]
    return result,nll

@njit(cache=True)
def decode(blob, graph, q, nrows, genes):
    if len(blob)<4: raise ValueError('truncated rANS')
    state=np.uint64(0)
    for k in range(4): state |= np.uint64(blob[k]) << np.uint64(k*8)
    if state < LOWER: raise ValueError('invalid initial rANS state')
    m=np.zeros((nrows,(genes+7)//8),np.uint8)
    pos=4
    for i in range(nrows):
        for g in range(genes):
            c=0 if q.shape[1]==1 else context(m,graph,i,g)
            p1=int(q[g,c]); p0=TOTAL-p1
            rem=int(state & np.uint64(TOTAL-1))
            one=rem>=p0
            freq=np.uint64(p1 if one else p0)
            start=np.uint64(p0 if one else 0)
            state=freq*(state >> np.uint64(PREC))+np.uint64(rem)-start
            if one: m[i,g>>3] |= np.uint8(1<<(g&7))
            while state < LOWER:
                if pos>=len(blob): raise ValueError('truncated rANS payload')
                state=(state<<np.uint64(8)) | np.uint64(blob[pos]);pos+=1
    if pos!=len(blob) or state!=LOWER: raise ValueError('rANS termination mismatch')
    return m

@njit(cache=True)
def indices_from_support(m, genes, nnz):
    ptr=np.empty(len(m)+1,np.int64);ptr[0]=0
    idx=np.empty(nnz,np.int64);p=0
    for i in range(len(m)):
        for g in range(genes):
            if bit(m,i,g):
                if p>=nnz: raise ValueError('support exceeds nnz')
                idx[p]=g;p+=1
        ptr[i+1]=p
    if p!=nnz: raise ValueError('support nnz mismatch')
    return ptr,idx
