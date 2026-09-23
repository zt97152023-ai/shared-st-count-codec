import bz2
import itertools
import struct
import unittest
import numpy as np
from qshare_model import share,cdf,bound,encode,decode,gate,HEADER

class Tests(unittest.TestCase):
    def test_blob_roundtrip_boundaries(self):
        rng=np.random.default_rng(17)
        for G in [0,1,7,8,9,21]:
            groups=rng.integers(0,8,G,dtype=np.uint8);q=rng.integers(1,4096,G,dtype=np.uint16)
            shared=np.array([1,4095,2048,2,4094,1024,3000,10],dtype='<u2')
            for mask in [None,np.zeros(G,bool),np.ones(G,bool),np.arange(G)%2==0]:
                expected=shared[groups].copy()
                if mask is not None:expected[mask]=q[mask]
                self.assertTrue(np.array_equal(decode(encode(shared,groups,q,mask),groups),expected))

    def test_reject_corrupt(self):
        groups=np.zeros(1,np.uint8);s=np.full(8,2048,np.uint16);q=np.array([4095],np.uint16)
        good=encode(s,groups,q,np.ones(1,bool));raw=bz2.decompress(good)
        bad=[good[:-1],good+b'x',good+good,bz2.compress(raw+b'x')]
        for idx,v in [(0,0),(4,3),(9,0),(10,0),(25,128),(26,2),(31,240)]:
            r=bytearray(raw);r[idx]=v
            # Zero shared q needs both bytes zero; current value2048 has low byte0.
            if idx==9:r[10]=0
            bad.append(bz2.compress(r))
        r=bytearray(raw);r[30]=r[31]=0;bad.append(bz2.compress(r))
        for b in bad:
            with self.assertRaises(ValueError):decode(b,groups)
        with self.assertRaises(ValueError):decode(good,np.array([8]))
        with self.assertRaises(ValueError):decode(good,np.array([0,0]))

    def test_integer_cdf_and_shared(self):
        groups=np.array([0,0,1,7]);q=np.array([1,4095,2051,1753],np.uint16)
        odds=np.array([[22,50,65536,100000,195000000,35000,500000]]*8,dtype=np.uint32)
        result=cdf(q,groups,odds)
        for g in range(4):
            for c in range(7):
                a=int(q[g]);r=int(odds[groups[g],c]);den=a*r+(4096-a)*65536
                self.assertEqual(int(result[g,c]),min(4095,max(1,(4096*a*r+den//2)//den)))
        self.assertTrue(np.array_equal(result[:,7],q))
        s=share(np.array([0,2,100,100]),np.array([0,2,0,100]),groups)
        self.assertEqual(int(s[0]),3413);self.assertEqual(int(s[2]),2048)

    def test_all_context_assignments(self):
        groups=np.zeros(1,np.uint8);odds=np.array([[22,512,8192,65536,100000,500000,195000000]]*8,np.uint32)
        for oldq,newq in [(1000,3000),(3000,1000),(4095,1),(1500,1500)]:
            old=cdf(np.array([oldq]),groups,odds);new=cdf(np.array([newq]),groups,odds)
            for symbols in itertools.product([0,1],repeat=3):
                a=sum(symbols);u,safe,eps=bound(np.array([3]),np.array([a]),old,new)
                for contexts in itertools.product(range(8),repeat=3):
                    delta=0.
                    for symbol,c in zip(symbols,contexts):
                        po=int(old[0,c])/4096;pn=int(new[0,c])/4096
                        delta+=np.log2(po/pn) if symbol else np.log2((1-po)/(1-pn))
                    self.assertLessEqual(delta,float(safe[0])+1e-12)
            self.assertEqual(float(bound(np.array([0]),np.array([0]),old,new)[1][0]),0.)
        # A high shared probability can strictly help a singleton-only gene: retain negative bounds.
        old=cdf(np.array([1000]),groups,np.full((8,7),65536,np.uint32));new=cdf(np.array([3000]),groups,np.full((8,7),65536,np.uint32))
        self.assertLess(bound(np.array([3]),np.array([3]),old,new)[0][0],0)

    def test_three_way_gate(self):
        def rows(a,b):return [dict(status='success',lower_bytes=a,upper_bytes=b)]*100
        self.assertEqual(gate(rows(1,2)),'supported')
        self.assertEqual(gate(rows(-2,-1)),'not_supported_by_bound')
        self.assertEqual(gate(rows(-1,1)),'numerically_inconclusive')
        self.assertEqual(gate(rows(0,0)),'numerically_inconclusive')
        self.assertEqual(gate([]),'inconclusive_coverage')

if __name__=='__main__':unittest.main(verbosity=2)
