"""Synthetic only: frozen adapters are not released to HEST by these tests."""
import bz2
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

import numpy as np
from scipy import sparse
from baseline.hest1000 import general_baselines as codec

SCRIPT = Path(codec.__file__)
FROZEN = SCRIPT.parents[1]/'evidence/COUNT-MATCHED-READY-001/venv/Scripts/python.exe'


def cli(*args):
    proc = subprocess.run([str(FROZEN), '-X', 'utf8', '-B', str(SCRIPT), *map(str,args)],
                          capture_output=True, text=True)
    return proc


def rewrite(archive, changes, refresh=False):
    with zipfile.ZipFile(archive) as z:
        parts = {name:z.read(name) for name in z.namelist()}
    parts.update(changes)
    if refresh:
        man = json.loads(parts['manifest.json'])
        for name, raw in changes.items():
            man['files'][name] = {'bytes':len(raw),'sha256':codec.digest(raw)}
        parts['manifest.json'] = codec.jbytes(man)
    target = archive.with_name(archive.stem+'-corrupt.zip')
    with zipfile.ZipFile(target,'w') as z:
        for name, raw in parts.items(): z.writestr(name,raw)
    return target


class GeneralBaselines(unittest.TestCase):
    def source(self, root, dense):
        root.mkdir()
        x = sparse.csr_matrix(np.asarray(dense,dtype=np.int64))
        sparse.save_npz(root/'counts.npz',x)
        # Duplicate labels and opaque metadata are intentionally preserved.
        meta = json.dumps({'gene_ids':['duplicate']*x.shape[1],
                           'spot_ids':[f's{i}' for i in range(x.shape[0])],
                           'extra':{'unicode':'组织', 'coordinates':[1.5,2.5]}},
                          ensure_ascii=False,indent=3).encode()+b'\n'
        (root/'metadata.json').write_bytes(meta)
        return x,meta

    def test_roundtrips_and_determinism_fresh_process(self):
        cases = [np.zeros((0,0),np.int64),np.zeros((0,3),np.int64),
                 np.zeros((3,0),np.int64),np.zeros((3,4),np.int64),
                 np.array([[7]],np.int64),
                 np.array([[0,codec.MAX_U32,0,2],[0,0,0,0],[1,0,3,0]],np.int64)]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for i, dense in enumerate(cases):
                source=root/f'input{i}'; x,meta=self.source(source,dense)
                for method in codec.METHODS:
                    archives=[]
                    for repeat in [0,1]:
                        archive=root/f'{i}-{method}-{repeat}.zip'
                        proc=cli('encode',source,method,archive)
                        self.assertEqual(proc.returncode,0,proc.stderr)
                        archives.append(archive)
                    self.assertEqual(archives[0].read_bytes(),archives[1].read_bytes())
                    # Physically hide reference directory during independent decode.
                    hidden=source.with_name(source.name+'-hidden');source.rename(hidden)
                    output=root/f'output{i}-{method}'
                    proc=cli('decode',archives[0],output)
                    source=hidden.rename(source)
                    self.assertEqual(proc.returncode,0,proc.stderr)
                    y=sparse.load_npz(output/'counts.npz')
                    self.assertEqual(y.dtype,x.dtype);self.assertEqual(y.shape,x.shape)
                    self.assertTrue(y.has_canonical_format)
                    for name in ['data','indices','indptr']:
                        np.testing.assert_array_equal(getattr(x,name),getattr(y,name))
                    self.assertEqual(meta,(output/'metadata.json').read_bytes())

    def test_payload_corruption_both_methods(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'input';self.source(source,[[1,0],[0,2]])
            for method in codec.METHODS:
                archive=root/f'{method}.zip'
                proc=cli('encode',source,method,archive);self.assertEqual(proc.returncode,0,proc.stderr)
                with zipfile.ZipFile(archive) as z: raw=z.read('metadata.bz2')
                corrupted=rewrite(archive,{'metadata.bz2':raw[:-1]+bytes([raw[-1]^1])})
                proc=cli('decode',corrupted,root/f'bad-{method}')
                self.assertNotEqual(proc.returncode,0)
                self.assertFalse((root/f'bad-{method}').exists())

    def test_rehashed_csr_domain_and_length_corruptions(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'input';self.source(source,[[1,0],[0,2]])
            archive=root/'csr.zip';codec.encode(source,'CSR_BZIP2_9',archive)
            with zipfile.ZipFile(archive) as z: original=codec.unframe(bz2.decompress(z.read('csr.bz2')))
            variants=[('indices.u32',np.array([2,1],dtype='<u4').tobytes()),
                      ('values.u32',np.array([0,2],dtype='<u4').tobytes()),
                      ('indptr.u64',np.array([0,2,1],dtype='<u8').tobytes()),
                      ('values.u32',b'\x00')]
            for i,(name,raw) in enumerate(variants):
                streams={**original,name:raw}
                corrupt=rewrite(archive,{'csr.bz2':bz2.compress(codec.frame(streams),9)},True)
                with self.assertRaises(ValueError):codec.decode(corrupt,root/f'out{i}')

    def test_reject_noncanonical_dtype_and_count_domain(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'input';x,_=self.source(source,[[1,0],[0,2]])
            for bad in [x.astype(np.float64),x.astype(np.uint32),
                        sparse.csr_matrix(np.array([[-1,0]],np.int64)),
                        sparse.csr_matrix(np.array([[codec.MAX_U32+1,0]],np.int64)),
                        sparse.csr_matrix((np.array([1,2],np.int64),[0,0],[0,2]),shape=(1,2))]:
                with self.assertRaises(ValueError):codec.validate(bad)

    def test_rehashed_pcodec_corruptions(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'input';self.source(source,[[1,2],[0,3]])
            archive=root/'pco.zip';proc=cli('encode',source,'Pcodec',archive)
            self.assertEqual(proc.returncode,0,proc.stderr)
            # Generate uint32 streams using exactly the frozen runtime.
            for i,(name,arr) in enumerate([('lengths.pco',[4,0]),('gaps.pco',[0,0,1]),('values.pco',[1,0,3])]):
                pco=root/f'{i}.pco'
                code=('import sys,numpy as np; from baseline.hest1000.general_baselines import pcompress; '
                      'open(sys.argv[1],"wb").write(pcompress(np.array('+repr(arr)+',dtype="uint32")))')
                proc=subprocess.run([str(FROZEN),'-B','-c',code,str(pco)],capture_output=True,text=True)
                self.assertEqual(proc.returncode,0,proc.stderr)
                corrupt=rewrite(archive,{name:pco.read_bytes()},True)
                proc=cli('decode',corrupt,root/f'out{i}')
                self.assertNotEqual(proc.returncode,0)


if __name__=='__main__':
    unittest.main()
