"""Reviewed exposed SPA108 vertical slice only; never releases the 1000 cohort.

Decoder audit hooks cover Python filesystem APIs, not native code/OS isolation.
Resource ceilings are sampled watchdogs, not hard disk quotas.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile

WORK = Path(__file__).resolve().parents[2]
BASE = WORK / 'baseline'
EVIDENCE = BASE / 'evidence/COUNT-HEST-1000-001'
OLD = BASE / 'evidence/COUNT-EXTERNAL-UNSEEN-001/baselines.py'
SHARED_PY = BASE / 'evidence/COUNT-MATCHED-READY-001/venv/Scripts/python.exe'
METHODS = ['Shared', 'BP_gene_none', 'BP_spot_mean', 'IVCSC', 'IVCSC_bz2',
           'CSR_ZSTD19', 'CSC_ZSTD19', 'H5AD_GZIP4']


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(8 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def write(path, obj):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def source_pins():
    files = [Path(__file__), OLD, BASE/'ivcsc/adapter.py', BASE/'ivcsc/ivcsc.exe',
             BASE/'pilot/io047.py', BASE/'.ai/tasks/COUNT-HEST-1000-001.json']
    for directory in ['matched_ready', 'execution_ready', 'qpatchcodec', 'sharedcodec',
                      'evidence/COUNT-E1-100/runtime']:
        files.extend((BASE/directory).rglob('*.py'))
    bp = BASE/'evidence/COUNT-HYBRID-EXTERNAL-001/bpcells/python_lib'
    files.extend(p for p in bp.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    return {str(p.resolve()): sha(p) for p in sorted(set(files))}


def install_guard(roots):
    roots = [Path(p).resolve() for p in roots]
    def guard(event, args):
        if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(args[0])).resolve()
            if any(path == root or root in path.parents for root in roots):
                raise PermissionError('decoder reference access denied: '+str(path))
    sys.addaudithook(guard)
    return guard


def compare(x, metadata, decoded):
    import numpy as np
    from scipy import sparse
    decoded = Path(decoded)
    if (decoded/'counts.npz').exists():
        y = sparse.load_npz(decoded/'counts.npz')
    else:
        with np.load(decoded/'decoded.npz', allow_pickle=False) as f:
            # Check value dtype before constructing CSR (construction may coerce).
            values = f['values'].copy()
            y = sparse.csr_matrix((values, f['indices'], f['indptr']), shape=tuple(f['shape']))
    checks = {'dtype': y.dtype == x.dtype == np.dtype('int64'), 'shape': y.shape == x.shape,
              'csr': sparse.isspmatrix_csr(y), 'canonical': y.has_canonical_format,
              'indptr': np.array_equal(y.indptr, x.indptr),
              'indices': np.array_equal(y.indices, x.indices),
              'counts': np.array_equal(y.data, x.data),
              'metadata': (decoded/'metadata.json').read_bytes() == metadata}
    checks['all'] = all(checks.values())
    return checks


def bytes_used(root):
    total = 0
    for p in root.rglob('*'):
        try:
            if p.is_file(): total += p.stat().st_size
        except FileNotFoundError:
            pass
    return total


def budget(root, cap_gib=32, reserve_gib=20):
    import shutil
    if shutil.disk_usage(root).free < reserve_gib*2**30 or bytes_used(root) > cap_gib*2**30:
        raise RuntimeError('disk ceiling/reserve threatened')


def execute(cmd, log, env, root, timeout=600, cap_gib=32, reserve_gib=20, rss_gib=16):
    import psutil
    budget(root,cap_gib,reserve_gib)
    start = time.monotonic(); peak = 0; code = None
    with log.open('xb') as f:
        p = subprocess.Popen(list(map(str, cmd)), cwd=WORK, env=env, stdout=f, stderr=subprocess.STDOUT)
        try:
            while p.poll() is None:
                proc = psutil.Process(p.pid)
                members = [proc]+proc.children(recursive=True)
                rss = 0
                for q in members:
                    try: rss += q.memory_info().rss
                    except psutil.NoSuchProcess: pass
                peak = max(peak, rss)
                budget(root,cap_gib,reserve_gib)
                if peak > rss_gib*2**30: raise MemoryError('process tree RSS ceiling')
                if time.monotonic()-start > timeout: raise TimeoutError('stage time ceiling')
                time.sleep(.25)
            code = p.returncode
        finally:
            if p.poll() is None:
                for q in psutil.Process(p.pid).children(recursive=True):
                    try: q.kill()
                    except psutil.NoSuchProcess: pass
                p.kill(); p.wait()
            write(log.with_suffix('.process.json'), {'command':list(map(str,cmd)),
                  'seconds':time.monotonic()-start, 'returncode':p.returncode,
                  'sampled_peak_tree_rss_bytes':peak})
    budget(root,cap_gib,reserve_gib)
    if code != 0: raise RuntimeError('stage failed; see '+str(log))


def runtime_info():
    import importlib.metadata
    packages = {}
    for name in ['numpy','scipy','h5py','anndata','zstandard','numba','psutil','pcodec']:
        try: packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: packages[name] = None
    return {'executable':sys.executable,'python':sys.version,'packages':packages,
            'executable_sha256':sha(sys.executable)}


def fee_report(folder, method):
    if method.startswith('BP_') or method == 'H5AD_GZIP4':
        files = [p for p in folder.rglob('*') if p.is_file()]
        total = sum(p.stat().st_size for p in files)
        return {'total_file_bytes':total,'components':None,
                'archive_hashes':{p.relative_to(folder).as_posix():sha(p) for p in files}}
    p = folder/('count.cnt' if method == 'Shared' else 'archive.bin')
    with zipfile.ZipFile(p) as z:
        components = {i.filename:i.file_size for i in z.infolist()}
    return {'total_file_bytes':p.stat().st_size,'components':components,
            'framing_bytes':p.stat().st_size-sum(components.values()),
            'archive_hashes':{p.name:sha(p)}}


def worker(stage, method, source, output, blocked):
    write(Path(output).parent/(stage+'_runtime.json'), runtime_info())
    if stage == 'prepare':
        from scipy import sparse
        from baseline.pilot import io047 as io
        x, encoding = io.read_x(source, canonical=True)
        out = Path(output); out.mkdir()
        sparse.save_npz(out/'counts.npz',x,compressed=False)
        (out/'metadata.json').write_bytes(io.jbytes(io.metadata(source,x.shape)))
        import h5py
        with h5py.File(source,'r') as f:
            original=f['X']; source_dtype=str(original.dtype if isinstance(original,h5py.Dataset) else original['data'].dtype)
        write(out/'canonical.json',{'source_encoding':encoding,'csr_sha256':io.csr_sha(x),
              'shape':list(x.shape),'n_spots':int(x.shape[0]),'n_genes':int(x.shape[1]),
              'n_counts':int(x.shape[0])*int(x.shape[1]),'n_nonzero':int(x.nnz),
              'canonical_dtype':str(x.dtype),'source_storage_dtype':source_dtype,
              'canonical_policy':'sum duplicate sparse entries; remove explicit zeros; sort indices; preserve full axes',
              'raw_biological_count_lineage':'unresolved unless separately documented'})
        return
    if stage == 'decode':
        install_guard(blocked)
        for root in blocked:
            try: open(Path(root)/'guard-probe', 'rb')
            except PermissionError: pass
            else: raise RuntimeError('decoder guard probe failed')
    if method == 'Shared':
        if stage == 'encode':
            from baseline.matched_ready.cli import encode
            encode(source, output, 'shared-only')
        else:
            from baseline.matched_ready.decoder import decode
            decode(source, output)
    else:
        spec = importlib.util.spec_from_file_location('frozen_external_baselines', OLD)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        getattr(module, stage)(method, Path(source), Path(output))


def run(release_path, output):
    import numpy as np
    from scipy import sparse
    release = json.loads(Path(release_path).read_text(encoding='utf-8'))
    pins = source_pins()
    source = Path(release['source']).resolve()
    if release.get('released') is not True or release.get('sample_id') != 'SPA108':
        raise ValueError('reviewed SPA108 release required; no cohort release supported')
    if source != Path('E:/Hestdata/st/SPA108.h5ad').resolve(): raise ValueError('SPA108 source only')
    if release.get('code_pins') != pins or sha(source) != release['source_sha256']:
        raise ValueError('release code/input hash mismatch')
    output = Path(output).resolve()
    if output.parent != EVIDENCE.resolve(): raise ValueError('fresh task evidence child required')
    return run_case('SPA108',source,output,pins,release['source_sha256'],release_path)


def run_case(sample_id, source, output, pins, source_sha256, release_path,
             resource_root=None, timeout=600, cap_gib=32, reserve_gib=20, rss_gib=16):
    """Internal callable: caller must implement reviewed cohort release/resource gates.

    Defaults are pilot ceilings. Main wrapper must supply reviewed main limits.
    """
    import numpy as np
    from scipy import sparse
    source=Path(source).resolve(); output=Path(output).resolve()
    resource_root=Path(resource_root or EVIDENCE)
    output.mkdir(exist_ok=False); budget(resource_root,cap_gib,reserve_gib)
    def call(cmd, log):
        return execute(cmd,log,env,resource_root,timeout,cap_gib,reserve_gib,rss_gib)
    write(output/'PINS.json', {'code':pins,'source':str(source),'source_sha256':sha(source),
                             'release_sha256':sha(release_path),'methods':METHODS})
    write(output/'RUNTIME.json',runtime_info())
    env = os.environ.copy()
    env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',NUMBA_CACHE_DIR=str(output/'numba_cache'),
               TEMP=str(output/'temp'),TMP=str(output/'temp'))
    for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMBA_NUM_THREADS']: env[k]='1'
    (output/'temp').mkdir()
    from baseline.pilot import io047 as io
    scratch = output/'reference_scratch'
    call([sys.executable,'-B','-m','baseline.hest1000.pilot','worker','prepare','Shared',
          source,scratch],output/'prepare.log')
    x=sparse.load_npz(scratch/'counts.npz'); metadata=(scratch/'metadata.json').read_bytes()
    encoding=json.loads((scratch/'canonical.json').read_bytes())['source_encoding']
    write(output/'CANONICAL.json',{'shape':list(x.shape),'dtype':str(x.dtype),'nnz':int(x.nnz),
          'source_encoding':encoding,'csr_sha256':io.csr_sha(x),
          'metadata_sha256':hashlib.sha256(metadata).hexdigest(),
          'scratch_hashes':{p.name:sha(p) for p in scratch.iterdir()}})
    for method in METHODS:
        if pins != source_pins() or sha(source) != source_sha256: raise RuntimeError('hash drift')
        folder = output/method; folder.mkdir()
        archive = folder/'archive'; decoded = folder/'decoded'
        row = {'sample_id':sample_id,'method':method,'status':'failed','total_file_bytes':None,
               'n_spots':x.shape[0],'n_genes':x.shape[1],'n_nonzero':x.nnz,
               'n_counts':int(np.prod(x.shape,dtype=np.int64)), 'exact':None}
        try:
            python = SHARED_PY if method == 'Shared' else Path(sys.executable)
            enc_source = source if method == 'Shared' else scratch
            enc_output = archive/'count.cnt' if method == 'Shared' else archive
            if method == 'Shared': archive.mkdir()
            args = ['-B','-m','baseline.hest1000.pilot','worker']
            call([python,*args,'encode',method,enc_source,enc_output],folder/'encode.log')
            dec_source = enc_output if method == 'Shared' else archive
            call([python,*args,'decode',method,dec_source,decoded,'--blocked',
                  'E:/Hestdata/st',scratch],folder/'decode.log')
            checks = compare(x,metadata,decoded); row['exact']=checks
            write(folder/'EXACT.json',checks)
            if not checks['all']: raise ValueError('exact recovery failure')
            row.update(fee_report(archive,method)); row['status']='success'
            row['decoded_hashes']={p.name:sha(p) for p in decoded.iterdir() if p.is_file()}
            row['full_archive_bits_per_count']=row['total_file_bytes']*8/row['n_counts']
            row['full_archive_bits_per_nonzero']=row['total_file_bytes']*8/x.nnz if x.nnz else None
        except Exception as exc:
            row['error']=type(exc).__name__+': '+str(exc)
        finally:
            row['source_hash_after']=sha(source); row['code_unchanged']=pins==source_pins()
            write(folder/'RESULT.json',row)
            with (output/'RUNS.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps(row)+'\n')
        if row['status']!='success': raise RuntimeError('vertical slice stopped on failure; logs retained')
        if row['source_hash_after']!=source_sha256 or not row['code_unchanged']:
            raise RuntimeError('hash drift; stop')
    write(output/'RESULT.json',{'status':'pilot_complete','samples':1,'methods':len(METHODS),
          'full_cohort_released':False,'reference_is_canonical_int64':True,
          'original_storage_dtype_preserved':False,'guard':'Python audit hook, not OS sandbox'})


def main():
    p=argparse.ArgumentParser(description=__doc__); s=p.add_subparsers(dest='command',required=True)
    q=s.add_parser('run'); q.add_argument('--release',required=True); q.add_argument('--output',required=True)
    q=s.add_parser('pins')
    q=s.add_parser('worker'); q.add_argument('stage',choices=['prepare','encode','decode']); q.add_argument('method',choices=METHODS)
    q.add_argument('source'); q.add_argument('output'); q.add_argument('--blocked',nargs='+',default=[])
    a=p.parse_args()
    if a.command=='pins': print(json.dumps(source_pins(),indent=2))
    elif a.command=='run': run(a.release,a.output)
    else: worker(a.stage,a.method,a.source,a.output,a.blocked)


if __name__=='__main__': main()
