"""Actual eight-codec synthetic roundtrips; never reads HEST evaluation data."""
import json
import os
from pathlib import Path
import sys
import time
import numpy as np
from scipy import sparse
import anndata as ad
from baseline.hest1000 import pilot


def main():
    root=pilot.EVIDENCE/'synthetic_v1'; root.mkdir(exist_ok=False)
    env=os.environ.copy(); env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',
        NUMBA_CACHE_DIR=str(root/'numba_cache'),TEMP=str(root/'temp'),TMP=str(root/'temp'))
    for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMBA_NUM_THREADS']: env[k]='1'
    (root/'temp').mkdir()
    reference=root/'reference'; reference.mkdir()
    x=sparse.csr_matrix(np.array([[0,1,0,4294967295],[2,0,3,0],[0,4,1,8],
                                  [17,0,0,2],[0,0,0,0],[5,1,1,0]],dtype=np.int64))
    a=ad.AnnData(x); a.obs_names=['s0','s1','s2','s3','s4','s5']
    a.var_names=['GENE_DUP','GENE_DUP','GENE_C','GENE_D']
    a.obsm['spatial']=np.array([[0.,0.],[1.,0.],[2.,0.],[0.,1.],[1.,1.],[2.,1.]],dtype=np.float64)
    source=reference/'synthetic.h5ad'; a.write_h5ad(source)
    pins=pilot.source_pins(); pilot.write(root/'PINS.json',pins)
    pilot.write(root/'INPUT.json',{'sha256':pilot.sha(source),'counts_dtype':'int64',
        'coordinates_dtype':'float64','duplicate_gene_labels':True,'includes_uint32_max':True})
    scratch=reference/'canonical'
    args=['-B','-m','baseline.hest1000.pilot','worker']
    pilot.execute([sys.executable,*args,'prepare','Shared',source,scratch],root/'prepare.log',env,pilot.EVIDENCE)
    canonical=sparse.load_npz(scratch/'counts.npz'); metadata=(scratch/'metadata.json').read_bytes()
    rows=[]; start=time.monotonic()
    for method in pilot.METHODS:
        folder=root/method; folder.mkdir(); archive=folder/'archive'; decoded=folder/'decoded'
        py=pilot.SHARED_PY if method=='Shared' else Path(sys.executable)
        row={'method':method,'status':'failed','exact':None,'total_file_bytes':None}
        try:
            if method=='Shared': archive.mkdir()
            enc_source=source if method=='Shared' else scratch
            enc_out=archive/'count.cnt' if method=='Shared' else archive
            pilot.execute([py,*args,'encode',method,enc_source,enc_out],folder/'encode.log',env,pilot.EVIDENCE)
            dec_source=enc_out if method=='Shared' else archive
            pilot.execute([py,*args,'decode',method,dec_source,decoded,'--blocked',reference],
                          folder/'decode.log',env,pilot.EVIDENCE)
            row['exact']=pilot.compare(canonical,metadata,decoded)
            pilot.write(folder/'EXACT.json',row['exact'])
            if not row['exact']['all']: raise ValueError('synthetic exact recovery failure')
            row.update(pilot.fee_report(archive,method)); row['status']='success'
        except Exception as exc:
            row['error']=type(exc).__name__+': '+str(exc)
        row['input_unchanged']=pilot.sha(source)==json.loads((root/'INPUT.json').read_bytes())['sha256']
        row['code_unchanged']=pilot.source_pins()==pins
        pilot.write(folder/'RESULT.json',row); rows.append(row)
    passed=all(r['status']=='success' and r['input_unchanged'] and r['code_unchanged'] for r in rows)
    pilot.write(root/'RESULT.json',{'status':'passed' if passed else 'failed','rows':rows,
        'seconds':time.monotonic()-start,'synthetic_only':True,'hest_counts_read':False,
        'decoder_is_fresh_process':True,'guard':'Python audit only; not OS isolation'})
    print(json.dumps({'status':'passed' if passed else 'failed','methods':len(rows),'output':str(root)}))
    return 0 if passed else 1


if __name__=='__main__': sys.exit(main())
