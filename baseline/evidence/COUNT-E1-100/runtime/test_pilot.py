import tempfile
import unittest
import zipfile
from pathlib import Path
import numpy as np
from scipy import sparse
import codec
import entropy
import io047 as io

class TestPilot(unittest.TestCase):
    def test_extremes_and_random_support(self):
        for a in [np.zeros((4,9),int),np.ones((7,17),int),np.eye(13,dtype=int),np.random.default_rng(14).integers(0,2,(19,23))]:
            x=sparse.csr_matrix(a);m=entropy.packed_support(x.indptr,x.indices,*x.shape)
            graph=codec.graph_for(np.random.default_rng(4).random((len(a),2)),'S2_spatial')
            codec.validate_graph(graph,len(a))
            for flag in [True,False]:
                q=entropy.fit(m,graph,x.shape[1],flag);b,nll=entropy.encode(m,graph,q,x.shape[1]);d=entropy.decode(b,graph,q,*x.shape)
                ptr,idx=entropy.indices_from_support(d,x.shape[1],x.nnz)
                np.testing.assert_array_equal(ptr,x.indptr);np.testing.assert_array_equal(idx,x.indices)
                self.assertLess(abs(len(b)*8-nll),50)
                with self.assertRaises(ValueError): entropy.decode(np.r_[b,np.uint8(0)],graph,q,*x.shape)

    def test_causality_and_count_matching(self):
        coords=np.random.default_rng(3).random((25,2))
        for method in ['S1_prefix','S2_spatial']:
            gr=codec.graph_for(coords,method);codec.validate_graph(gr,25)
            np.testing.assert_array_equal((gr>=0).sum(axis=1),np.minimum(np.arange(25),6))
            alt=coords.copy();alt[16:]+=1000
            np.testing.assert_array_equal(codec.graph_for(alt,method)[:16],gr[:16])
        gr[1,0]=2
        with self.assertRaises(ValueError):codec.validate_graph(gr,25)

    def test_symbol_context_no_future(self):
        a=np.random.default_rng(6).integers(0,2,(12,11));graph=codec.graph_for(np.zeros((12,2)),'S1_prefix')
        x=sparse.csr_matrix(a);m=entropy.packed_support(x.indptr,x.indices,*x.shape)
        other=m.copy();other[7:]=255
        for g in range(11):self.assertEqual(entropy.context(m,graph,7,g),entropy.context(other,graph,7,g))

    def test_integer_bounds_and_duplicates(self):
        for a in [np.array([1.5]),np.array([-1]),np.array([np.nan]),np.array([2**32],dtype=np.float32)]:
            with self.assertRaises(ValueError):io.valid_values(a)
        io.valid_values(np.array([0,2**32-1],np.uint32))
        with self.assertRaises(ValueError):io.from_parts([1,2],[0,2],[0,0],[2**32-1,1],canonical=True)

    def test_full_archives_metadata_and_damage(self):
        import h5py
        a=np.array([[0,0,0],[1,0,2**32-1],[0,4,0]],np.uint64);x=sparse.csr_matrix(a)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'source.h5ad'
            with h5py.File(source,'w') as h:
                z=h.create_group('X');z.attrs['encoding-type']='csr_matrix';z.attrs['shape']=x.shape
                for k,v in [('data',x.data),('indices',x.indices),('indptr',x.indptr)]:z[k]=v
                for key,labels in [('obs',['s0','s1','s2']),('var',['dup','dup','tail'])]:
                    group=h.create_group(key);group.attrs['_index']='_index';group.create_dataset('_index',data=labels,dtype=h5py.string_dtype())
                h.create_group('obsm')['spatial']=np.array([[0.,-0.],[2.,3.],[2.,3.]],dtype=np.float32)
            for method in ['S0_gene','S1_prefix','S2_spatial','S2_shuffle_11','Pcodec','CSR_bz2']:
                pack=root/(method+'.cnt');stats=codec.encode_case(source,method,pack)
                result=codec.decode_case(pack,root/(method+'_dec'))
                self.assertEqual(result['canonical_sha256'],io.csr_sha(x))
                self.assertEqual(stats['package_bytes'],sum(stats['components'].values())+stats['framing_and_manifest_bytes'])
                self.assertEqual((root/(method+'_dec/metadata.json')).read_bytes(),io.jbytes(io.metadata(source,x.shape)))
            pack=root/'bad.cnt';codec.encode_case(source,'S0_gene',pack)
            with zipfile.ZipFile(pack) as z:parts={n:z.read(n) for n in z.namelist()}
            parts['support.rans']=parts['support.rans'][:-1]+bytes([parts['support.rans'][-1]^1])
            corrupt=root/'corrupt.cnt'
            with zipfile.ZipFile(corrupt,'w') as z:
                for n,b in parts.items():z.writestr(n,b)
            with self.assertRaises(ValueError):codec.decode_case(corrupt,root/'bad_dec')

            # Empty Pcodec arrays decode as None upstream. Only the explicit
            # canonical empty stream with expected length zero may be accepted.
            with h5py.File(source,'r+') as h:
                for key in ['data','indices','indptr']: del h['X'][key]
                h['X/data']=np.array([],np.uint32);h['X/indices']=np.array([],np.int32);h['X/indptr']=np.zeros(4,np.int32)
            for method in ['S0_gene','S1_prefix','S2_spatial','S2_shuffle_11','S2_shuffle_29','S2_shuffle_47','Pcodec','CSR_bz2']:
                pack=root/(method+'_empty.cnt');codec.encode_case(source,method,pack)
                codec.decode_case(pack,root/(method+'_empty_dec'))
            with self.assertRaises(ValueError):codec.pdecompress(codec.pcompress(np.array([],np.uint32)),1)

if __name__=='__main__':unittest.main()
