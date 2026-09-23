import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import numpy as np
from scipy import sparse
from baseline.hest1000.pilot import compare


class PilotChecks(unittest.TestCase):
    def test_corruptions(self):
        x=sparse.csr_matrix(np.array([[0,2],[3,0]],dtype=np.int64))
        meta=b'{"gene_ids":["A","B"],"spot_ids":["s1","s2"]}\n'
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); (p/'metadata.json').write_bytes(meta)
            sparse.save_npz(p/'counts.npz',x)
            self.assertTrue(compare(x,meta,p)['all'])
            sparse.save_npz(p/'counts.npz',x.astype(np.uint32))
            self.assertFalse(compare(x,meta,p)['dtype'])
            sparse.save_npz(p/'counts.npz',x)
            (p/'metadata.json').write_bytes(meta.replace(b'"A"',b'"C"'))
            self.assertFalse(compare(x,meta,p)['metadata'])
            (p/'metadata.json').write_bytes(meta.replace(b'"s1"',b'"sX"'))
            self.assertFalse(compare(x,meta,p)['metadata'])
            (p/'metadata.json').write_bytes(meta)
            y=x.copy(); y.data[0]+=1; sparse.save_npz(p/'counts.npz',y)
            self.assertFalse(compare(x,meta,p)['counts'])
            sparse.save_npz(p/'counts.npz',sparse.csr_matrix((2,3),dtype=np.int64))
            self.assertFalse(compare(x,meta,p)['shape'])

    def test_fresh_process_reference_guard(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'reference'; root.mkdir(); (root/'counts.npz').write_bytes(b'private')
            code=('from baseline.hest1000.pilot import install_guard; import sys; '
                  'install_guard([sys.argv[1]]); open(sys.argv[1]+"/counts.npz","rb")')
            proc=subprocess.run([sys.executable,'-B','-c',code,str(root)],capture_output=True,text=True)
            self.assertNotEqual(proc.returncode,0)
            self.assertIn('decoder reference access denied',proc.stderr)
            allowed=Path(td)/'archive.bin'; allowed.write_bytes(b'archive')
            code=('from baseline.hest1000.pilot import install_guard; import sys; '
                  'install_guard([sys.argv[1]]); assert open(sys.argv[2],"rb").read()==b"archive"')
            proc=subprocess.run([sys.executable,'-B','-c',code,str(root),str(allowed)],capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)


if __name__=='__main__': unittest.main()
