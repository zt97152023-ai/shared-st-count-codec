import bz2,json,subprocess,sys,tempfile,unittest
from pathlib import Path
import numpy as np
import run as codec
import model,values,entropy
io=codec.io

def graph(n):
    a=np.full((n,6),-1,np.int32)
    for i in range(n):a[i,:min(i,6)]=np.arange(max(0,i-6),i)
    return a

class ValueTests(unittest.TestCase):
    def test_heterogeneous_bases(self):
        idx=np.array([0,0,0,1,1,2,3]);v=np.array([1,1,1,2,2,257,4294967295],np.uint32)
        q,g,p,f,profile=model.base(idx,v,5)
        pg=3.5/8
        expected=[max(1,min(4095,int(np.floor(4096*(a+.5+16*pg)/(n+17)+.5)))) for n,a in zip([3,2,1,1,0],[3,0,0,0,0])]
        np.testing.assert_array_equal(q,expected);np.testing.assert_array_equal(g,[0,0,6,7,0])
        np.testing.assert_array_equal(profile['tail_sum'],[0,2,256,4294967294,0])
        np.testing.assert_array_equal(f.sum(axis=1),4096)
        np.testing.assert_array_equal(model.quantize(np.ones(32)/32),128)
        expected=np.ones(32,np.uint16);expected[0]=4065
        np.testing.assert_array_equal(model.quantize(np.eye(1,32)[0]),expected)

    def test_integer_tables(self):
        q=np.array([1,3,16,2048,4095],'<u2');g=np.array([0,1,2,3,7],np.uint8)
        odds=np.full((8,7),65536,'<u4');odds[0,0]=22;odds[7,6]=int(np.floor(np.exp(8)*65536+.5))
        freq=np.full((8,32),128,'<u2');cf=np.repeat(freq[:,None,:],7,axis=1)
        b,t,c=model.tables(q,g,freq,odds,cf)
        for j,a in enumerate(map(int,q)):
            for k in range(7):
                r=int(odds[g[j],k]);den=a*r+(4096-a)*65536
                self.assertEqual(int(b[j,k]),min(4095,max(1,(4096*a*r+den//2)//den)))
        np.testing.assert_array_equal(c[:,:,-1],4096)
        with self.assertRaises(ValueError):model.tables(q,g,np.zeros((8,32),np.uint16))

    def test_causal_context_and_roundtrip(self):
        rng=np.random.default_rng(191);dense=rng.choice([0,1,2,3,7,256,4294967295],size=(14,9)).astype(np.uint32)
        x=io.sparse.csr_matrix(dense);gr=graph(14)
        q,g,p,f,_=model.base(x.indices,x.data,9);odds,cf=model.conditional(x.indptr,x.indices,x.data,gr,q,g,p)
        for row in range(6,14):
            for gene in range(9):
                s=sum(int(dense[r,gene]) for r in gr[row]);ref=0 if s==0 else next((c for c,upper in enumerate([12,24,48,96,384],1) if s<upper),6)
                self.assertEqual(model.context(x.indptr,x.indices,x.data,gr,row,gene),ref)
        for conditional in [False,True]:
            binary,tail,cdf=model.tables(q,g,f,odds if conditional else None,cf if conditional else None)
            blob,nll,te,rb=values.encode(x.indptr,x.indices,x.data,gr,g,binary,tail,cdf,conditional)
            restored,te2,rb2=values.decode(blob,x.indptr,x.indices,gr,g,binary,tail,cdf,conditional)
            np.testing.assert_array_equal(restored,x.data);self.assertEqual((te,rb),(te2,rb2))
            self.assertLess(abs(len(blob)*8-nll),80)
            with self.assertRaises(ValueError):values.decode(blob[:-1],x.indptr,x.indices,gr,g,binary,tail,cdf,conditional)
            with self.assertRaises(ValueError):values.decode(np.append(blob,np.uint8(0)),x.indptr,x.indices,gr,g,binary,tail,cdf,conditional)

    def test_uint32_unused_leaf(self):
        ptr=np.array([0,1]);idx=np.array([0]);g=np.array([0],np.uint8);q=np.array([2048],np.uint16)
        b,t,c=model.tables(q,g,np.full((8,32),128,np.uint16));gr=graph(1)
        blob,*_=values.encode(ptr,idx,np.array([2**32],np.uint64),gr,g,b,t,c,False)
        with self.assertRaisesRegex(ValueError,'overflow'):values.decode(blob,ptr,idx,gr,g,b,t,c,False)

    def test_archive_only_full_decode(self):
        for data in [np.zeros((8,3),np.uint32),np.ones((8,3),np.uint32),np.array([[1,2,0],[3,0,4294967295]]*4,np.uint32)]:
            x=io.sparse.csr_matrix(data);n,g=x.shape;gr=graph(n)
            base=np.full(g,2048,'<u2');mask=entropy.packed_support(x.indptr,x.indices,n,g)
            support,*_=entropy.encode(mask,gr,np.repeat(base[:,None],49,axis=1),g)
            q,groups,prior,f,profile=model.base(x.indices,x.data,g);odds,cf=model.conditional(x.indptr,x.indices,x.data,gr,q,groups,prior)
            qblob,q,*_=codec.patch_model(q,groups,odds,profile['npositive'],profile['nones'])
            binary,tail,cdf=model.tables(q,groups,f,odds,cf);blob,_,te,rb=values.encode(x.indptr,x.indices,x.data,gr,groups,binary,tail,cdf,True)
            meta=io.jbytes({'spot_ids':['duplicate']*n,'gene_ids':['g']*g})
            parts={'metadata.bz2':bz2.compress(meta),'support.rans':support.tobytes(),'graph.bz2':bz2.compress(gr.astype('<i4').tobytes()),
                   'base_probability.bz2':bz2.compress(base.tobytes()),'shared_odds.u32':np.full((8,7),65536,'<u4').tobytes(),
                   'value_q1.bz2':qblob,'value_group.bz2':bz2.compress(groups.tobytes()),'value_base_k.bz2':bz2.compress(f.tobytes()),
                   'value_odds.u32':odds.tobytes(),'value_cond_k.bz2':bz2.compress(cf.tobytes()),'values.rans':blob.tobytes()}
            man={'schema':'qpatch-count-v1','method':'Qpatch12','q1_layout':'QSH1-mode1-12bit-exceptions-bz2-v1','shape':[n,g],'nnz':int(x.nnz),'precision':12,'value_layout':'singleton-K32-uniform-remainder;one-rANS;v1',
                 'support_model':'frozen-P2-shared-spatial-Q12-v1','tail_events':int(te),'remainder_bits':int(rb),'canonical_sha256':io.csr_sha(x),'metadata_sha256':codec.sha(meta)}
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);codec.write_archive(root/'count.cnt',parts,man)
                result=subprocess.run([sys.executable,'-X','utf8','-B',str(Path(codec.__file__)),'--worker','decode','--package',str(root/'count.cnt'),'--output',str(root/'decoded'),'--result',str(root/'result.json')],capture_output=True,text=True,timeout=120)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                with np.load(root/'decoded/decoded.npz') as restored:np.testing.assert_array_equal(restored['values'],x.data)
                self.assertTrue(json.loads((root/'result.json').read_text())['archive_only'])

    def test_mode_and_source_guard(self):
        groups=np.zeros(3,np.uint8);shared=np.full(8,2048,'<u2')
        with self.assertRaisesRegex(ValueError,'mode1'):
            codec.decode_q(codec.qm.encode(shared,groups,shared[:3]),groups)
        code="import run;run.source_guard();open('E:/Hestdata/st/forbidden.h5ad','rb')"
        result=subprocess.run([sys.executable,'-X','utf8','-B','-c',code],cwd=Path(codec.__file__).parent,capture_output=True,text=True,timeout=30)
        self.assertNotEqual(result.returncode,0);self.assertIn('source forbidden',result.stderr)

if __name__=='__main__':unittest.main(verbosity=2)
