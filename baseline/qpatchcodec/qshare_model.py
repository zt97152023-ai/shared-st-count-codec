"""Paid Q12 shared probabilities and exact exceptions; no count codec."""
import bz2
import struct
import numpy as np

HEADER=struct.Struct('<4sBI8H')

def share(n,a,groups):
    out=[]
    for b in range(8):
        N=int(n[groups==b].sum());A=int(a[groups==b].sum())
        out.append(min(4095,max(1,(4096*(2*A+1)+N+1)//(2*(N+1)))))
    return np.array(out,dtype='<u2')

def cdf(q,groups,odds):
    q=np.asarray(q,dtype=np.uint64)
    if np.any(q<1) or np.any(q>4095):raise ValueError('q domain')
    r=np.asarray(odds,dtype=np.uint64)[groups]
    num=q[:,None]*r;den=num+(4096-q[:,None])*65536
    out=np.empty((len(q),8),dtype='<u2')
    out[:,:7]=np.clip((4096*num+den//2)//den,1,4095)
    out[:,7]=q
    return out

def bound(n,a,old,new):
    different=np.any(old!=new,axis=1)
    old=old.astype(np.float64);new=new.astype(np.float64)
    u=a*np.max(np.log2(old/new),axis=1)+(n-a)*np.max(np.log2((4096-old)/(4096-new)),axis=1)
    eps=np.where(different,1e-10*n,0.)
    u=np.where(different,u,0.)
    if not np.all(np.isfinite(u)):raise ValueError('nonfinite bound')
    return u,u+eps,eps

def encode(shared,groups,oldq,mask=None):
    raw=bytearray(HEADER.pack(b'QSH1',int(mask is not None),len(groups),*map(int,shared)))
    if mask is not None:
        raw.extend(np.packbits(mask,bitorder='little').tobytes())
        values=oldq[mask];raw.extend(struct.pack('<I',len(values)))
        acc=bits=0
        for q in values:
            acc|=int(q)<<bits;bits+=12
            while bits>=8:
                raw.append(acc&255);acc>>=8;bits-=8
        if bits:raw.append(acc)
    return bz2.compress(bytes(raw),compresslevel=9)

def decode(blob,groups):
    groups=np.asarray(groups)
    if groups.ndim!=1 or not np.issubdtype(groups.dtype,np.integer) or np.any(groups<0) or np.any(groups>7):raise ValueError('groups')
    G=len(groups);limit=HEADER.size+(G+7)//8+4+(12*G+7)//8
    dec=bz2.BZ2Decompressor()
    try:raw=dec.decompress(blob,max_length=limit+1)
    except (OSError,EOFError) as e:raise ValueError('compressed blob') from e
    if not dec.eof or dec.unused_data or len(raw)>limit or len(raw)<HEADER.size:raise ValueError('compressed framing')
    magic,mode,g,*s=HEADER.unpack_from(raw)
    if magic!=b'QSH1' or mode not in (0,1) or g!=G or min(s)<1 or max(s)>4095:raise ValueError('header')
    q=np.array(s,dtype='<u2')[groups]
    if mode==0:
        if len(raw)!=HEADER.size:raise ValueError('trailing raw')
        return q
    pos=HEADER.size;mlen=(G+7)//8
    if len(raw)<pos+mlen+4:raise ValueError('short mask')
    maskraw=raw[pos:pos+mlen];pos+=mlen
    if G%8 and maskraw[-1]>>(G%8):raise ValueError('mask padding')
    mask=np.unpackbits(np.frombuffer(maskraw,dtype=np.uint8),bitorder='little')[:G].astype(bool)
    count=struct.unpack_from('<I',raw,pos)[0];pos+=4
    packed=raw[pos:]
    if count!=int(mask.sum()) or len(packed)!=(12*count+7)//8:raise ValueError('exception length')
    if count%2 and packed[-1]>>4:raise ValueError('packed padding')
    values=[];acc=bits=offset=0
    for _ in range(count):
        while bits<12:
            acc|=packed[offset]<<bits;bits+=8;offset+=1
        v=acc&4095;acc>>=12;bits-=12
        if not v:raise ValueError('zero q')
        values.append(v)
    q[mask]=values
    return q

def gate(rows):
    if len(rows)!=100 or any(r['status']!='success' for r in rows):return 'inconclusive_coverage'
    lo=np.array([r['lower_bytes'] for r in rows]);hi=np.array([r['upper_bytes'] for r in rows])
    if lo.sum()>0 and np.median(lo)>0:return 'supported'
    if hi.sum()<0 or np.median(hi)<0:return 'not_supported_by_bound'
    return 'numerically_inconclusive'
