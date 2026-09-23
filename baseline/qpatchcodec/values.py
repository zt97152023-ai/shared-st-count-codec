"""Byte rANS for positive uint32 values; only decoded earlier rows are context."""
import math
import numpy as np
from numba import njit
import model

LOWER=1<<23

@njit(cache=True)
def put(state,start,freq,out,pos):
    f=np.uint64(freq)
    while state>=np.uint64((LOWER>>12)<<8)*f:
        out[pos]=np.uint8(state&np.uint64(255));pos+=1;state>>=np.uint64(8)
    return ((state//f)<<np.uint64(12))+(state%f)+np.uint64(start),pos

@njit(cache=True)
def take(state,start,freq,blob,pos):
    state=np.uint64(freq)*(state>>np.uint64(12))+(state&np.uint64(4095))-np.uint64(start)
    while state<LOWER:
        if pos>=len(blob):raise ValueError('truncated value rANS')
        state=(state<<np.uint64(8))|np.uint64(blob[pos]);pos+=1
    return state,pos

@njit(cache=True)
def encode(ptr,idx,val,graph,groups,q,tail,cdf,conditional):
    out=np.empty(len(val)*8+4,np.uint8);pos=0;state=np.uint64(LOWER)
    nll=0.;tails=0;bits=0
    for row in range(len(ptr)-2,-1,-1):
        for j in range(ptr[row+1]-1,ptr[row]-1,-1):
            g=idx[j];b=groups[g];c=model.context(ptr,idx,val,graph,row,g) if conditional else 7
            x=int(val[j]);p=int(q[g,c]);one=x==1
            if not one:
                y=x-1;k=0;tmp=y
                while tmp>1:tmp>>=1;k+=1
                rem=y-(np.int64(1)<<k);tails+=1;bits+=k;nll+=k
                for bit in range(k):
                    state,pos=put(state,2048*((rem>>bit)&1),2048,out,pos)
                f=int(tail[b,c,k]);state,pos=put(state,int(cdf[b,c,k]),f,out,pos)
                nll+=12-math.log2(f)
            f=p if one else 4096-p;start=4096-p if one else 0
            state,pos=put(state,start,f,out,pos);nll+=12-math.log2(f)
    result=np.empty(pos+4,np.uint8)
    for i in range(4):result[i]=np.uint8((state>>np.uint64(8*i))&np.uint64(255))
    for i in range(pos):result[4+i]=out[pos-i-1]
    return result,nll,tails,bits

@njit(cache=True)
def decode(blob,ptr,idx,graph,groups,q,tail,cdf,conditional):
    if len(blob)<4:raise ValueError('truncated value header')
    state=np.uint64(0)
    for i in range(4):state|=np.uint64(blob[i])<<np.uint64(8*i)
    if state<LOWER:raise ValueError('invalid value state')
    val=np.zeros(len(idx),np.uint32);pos=4;tails=0;bits=0
    for row in range(len(ptr)-1):
        for j in range(ptr[row],ptr[row+1]):
            g=idx[j];b=groups[g];c=model.context(ptr,idx,val,graph,row,g) if conditional else 7
            p=int(q[g,c]);one=int(state&np.uint64(4095))>=4096-p
            f=p if one else 4096-p;start=4096-p if one else 0
            state,pos=take(state,start,f,blob,pos)
            if one:val[j]=1
            else:
                symbol=int(state&np.uint64(4095));k=0
                while k<31 and symbol>=cdf[b,c,k+1]:k+=1
                state,pos=take(state,int(cdf[b,c,k]),int(tail[b,c,k]),blob,pos)
                rem=np.int64(0);tails+=1;bits+=k
                for bit in range(k-1,-1,-1):
                    onebit=int(state&np.uint64(4095))>=2048
                    state,pos=take(state,2048 if onebit else 0,2048,blob,pos)
                    if onebit:rem|=np.int64(1)<<bit
                x=(np.int64(1)<<k)+rem+1
                if x>4294967295:raise ValueError('unused uint32 overflow codeword')
                val[j]=x
    if pos!=len(blob) or state!=LOWER:raise ValueError('value rANS termination mismatch')
    return val,tails,bits
