import bz2
from pathlib import Path
import tempfile
import unittest
import numpy as np
from scipy import sparse
import run as r

class SharedTests(unittest.TestCase):
    def test_integer_cdf_independent_scalar_and_identity(self):
        q0=np.arange(1,4096,dtype='<u2');identity=np.full((8,7),65536,dtype='<u4')
        q=r.model.cdf(q0,identity)
        np.testing.assert_array_equal(q,np.repeat(q0[:,None],49,axis=1))
        mul=np.tile(np.array([r.model.RMIN,33,10000,65536,90000,10000000,r.model.RMAX],dtype='<u4'),(8,1))
        q=r.model.cdf(q0,mul)
        for a in [1,3,4,15,16,63,64,255,256,1023,1024,2047,2048,3071,3072,4095]:
            for k in range(7):
                value=int(mul[0,k]);den=a*value+(4096-a)*65536
                self.assertEqual(int(q[a-1,42+k]),max(1,min(4095,(4096*a*value+den//2)//den)))
        self.assertEqual(r.model.buckets(np.array([1,4,16,64,256,1024,2048,3072,4095])).tolist(),[0,1,2,3,4,5,6,7,7])

    def test_statistics_and_fit(self):
        x=sparse.csr_matrix(np.random.default_rng(9).integers(0,2,(24,8)))
        graph=r.prefix_graph(24);m=r.entropy.packed_support(x.indptr,x.indices,24,8)
        base=np.array([2,8,32,128,512,1500,2500,3500],dtype='<u2');group=r.model.buckets(base)
        seen,ones=r.model.counts(m,graph,base,group)
        for g in range(8):
            for k in range(7):
                events=[i for i in range(6,24) if sum(int(x[j,g]) for j in range(i-6,i))==k]
                self.assertEqual(int(seen[group[g],k,base[g]]),len(events))
                self.assertEqual(int(ones[group[g],k,base[g]]),sum(int(x[i,g]) for i in events))
        odds,stats=r.model.fit(m,graph,base)
        self.assertEqual(stats['fitted_events'],18*8)
        # For each occupied group test the regularized logistic objective vs beta=0.
        for b in range(8):
            for k in range(7):
                ii=np.flatnonzero(seen[b,k]);n=seen[b,k,ii];y=ones[b,k,ii]
                offset=np.log(ii/(4096.-ii));beta=np.log(int(odds[b,k])/65536)
                loss=lambda z: float(np.sum(n*np.logaddexp(0,offset+z)-y*(offset+z))+z*z/2)
                self.assertLessEqual(loss(beta),loss(0)+.001)

    def test_startup_and_roundtrip_count(self):
        for data in [np.zeros((4,3),dtype=np.uint32),np.ones((8,3),dtype=np.uint32),np.array([[0,4294967295,0],[1,0,2],[1,4,0],[0,0,0],[3,1,2],[1,1,0],[0,2,1],[3,0,2]],dtype=np.uint32)]:
            x=sparse.csr_matrix(data);n,g=x.shape;graph=r.prefix_graph(n)
            base=np.clip(np.floor((np.bincount(x.indices,minlength=g)+.5)/(n+1)*4096+.5),1,4095).astype('<u2')
            m=r.entropy.packed_support(x.indptr,x.indices,n,g);odds,_=r.model.fit(m,graph,base);q=r.model.cdf(base,odds)
            blob,_=r.entropy.encode(m,graph,q,g);decoded=r.entropy.decode(blob,graph,q,n,g)
            np.testing.assert_array_equal(m,decoded)
            if n<7:np.testing.assert_array_equal(odds,np.full((8,7),65536,dtype='<u4'))
            meta=r.io.jbytes({'spot_ids':[str(i) for i in range(n)],'gene_ids':['duplicate']*g})
            parts={'metadata.bz2':bz2.compress(meta,9),'values.pco':r.legacy.pcompress(x.data),
                'base_probability.bz2':bz2.compress(base.tobytes(),9),'shared_odds.u32':odds.tobytes(),'support.rans':blob.tobytes()}
            man={'schema':'shared-count-v1','method':'P1_shared_prefix','shape':[n,g],'nnz':int(x.nnz),'precision':12,'odds_scale':65536,
                'bucket_edges_q12':r.model.EDGES.tolist(),'canonical_sha256':r.io.csr_sha(x),'metadata_sha256':r.legacy.digest(meta)}
            with tempfile.TemporaryDirectory() as folder:
                p=Path(folder);r.legacy.write_archive(p/'count.cnt',parts,man);r.decode(p/'count.cnt',p/'decoded')
                with np.load(p/'decoded/decoded.npz') as d:
                    np.testing.assert_array_equal(d['values'],x.data)
                    np.testing.assert_array_equal(d['indices'],x.indices)
                parts['shared_odds.u32']=b'bad';r.legacy.write_archive(p/'bad.cnt',parts,man)
                with self.assertRaises(ValueError):r.decode(p/'bad.cnt',p/'badout')

    def test_invalid_model_and_graph(self):
        with self.assertRaises(ValueError):r.model.cdf(np.array([0]),np.ones((8,7),dtype='<u4'))
        with self.assertRaises(ValueError):r.model.cdf(np.array([20]),np.zeros((8,7),dtype='<u4'))
        graph=r.prefix_graph(8);graph[7,0]=7
        with self.assertRaises(ValueError):r.legacy.validate_graph(graph,8)

if __name__=='__main__':unittest.main(verbosity=2)
