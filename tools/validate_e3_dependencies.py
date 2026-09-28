"""Validate the repaired E3 dependency and five retained small archives.

Outputs go to a new directory. No source matrices are read or changed.
"""
import argparse
import bz2
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import zipfile


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--archives', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root/'baseline/evidence/COUNT-PRODUCTION-SHARED-ABLATIONS-50-001'))
    import ablation_lib as lib
    rt = lib.value_runtime_width(6)
    assert rt[3].K == 32
    worker = root/'baseline/evidence/COUNT-E3-MODULE-CONTRIBUTION-002-50/e3_worker.py'
    result = {'scope': 'current repaired release: dependency load and five archive-only decodes; not cohort rerun or historical environment reconstruction',
              'python': sys.version, 'executable': sys.executable,
              'value_worker_sha256': hashlib.sha256(lib.VALUE_WORKER_PATH.read_bytes()).hexdigest(),
              'runtime_modules': [{'path': str(getattr(m, '__file__', 'dynamic')), 'name': m.__name__} for m in rt],
              'q1_archives': [], 'decode_checks': []}
    header = struct.Struct('<4sBI32H')
    for archive in sorted(a.archives.glob('*/no_sharing/archive.cnt')):
        with zipfile.ZipFile(archive) as z:
            man = json.loads(z.read('manifest.json'))
            blob = bz2.decompress(z.read('value_q1.bz2'))
            groups = bz2.decompress(z.read('value_group.bz2'))
            magic, mode, genes, *centres = header.unpack_from(blob)
            mask = blob[header.size:header.size+(genes+7)//8]
            count = struct.unpack_from('<I', blob, header.size+len(mask))[0]
            all_set = all((mask[i//8] >> (i%8)) & 1 for i in range(genes))
            assert magic == b'QSH1' and mode == 1 and genes == len(groups)
            assert all_set and count == genes == man['q1_exception_count']
            assert len(centres) == 32 and min(centres) > 0
            result['q1_archives'].append({'sample_id': archive.parents[1].name,
                                        'mode': mode, 'genes': genes, 'exceptions': count,
                                        'all_gene_exceptions': all_set, 'paid_shared_centres': len(centres)})
    assert len(result['q1_archives']) == 50
    for arm in ['full', 'no_support', 'no_value', 'no_spatial', 'no_sharing']:
        archive = a.archives/'NCBI180'/arm/'archive.cnt'
        report = a.output/(arm+'.json')
        op = 'decode_no_value' if arm == 'no_value' else 'decode_standard'
        cmd = [sys.executable, '-B', '-X', 'utf8', str(worker), op, '--package', str(archive),
               '--output', str(a.output/arm), '--report', str(report)]
        process = subprocess.run(cmd, cwd=root, capture_output=True, text=True, encoding='utf-8')
        (a.output/(arm+'.log')).write_text(process.stdout+process.stderr, encoding='utf-8')
        if process.returncode:
            raise RuntimeError(arm + ': ' + process.stderr)
        obj = json.loads(report.read_text(encoding='utf-8'))
        with zipfile.ZipFile(archive) as z:
            man = json.loads(z.read('manifest.json'))
        # Independently compare recovered CSR and metadata hashes to stored manifest.
        import numpy as np
        from scipy import sparse
        with np.load(a.output/arm/'decoded.npz', allow_pickle=False) as f:
            x = sparse.csr_matrix((f['values'], f['indices'], f['indptr']), shape=tuple(f['shape']))
        actual = rt[0].csr_sha(x)
        metadata = hashlib.sha256((a.output/arm/'metadata.json').read_bytes()).hexdigest()
        assert actual == man['canonical_sha256'] and metadata == man['metadata_sha256']
        result['decode_checks'].append({'sample_id': 'NCBI180', 'arm': arm, 'command': cmd,
                                       'returncode': 0, 'report': obj,
                                       'canonical_sha256': actual, 'metadata_sha256': metadata,
                                       'matches_manifest': True})
    (a.output/'E3_VALIDATION.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('50 QSH1 headers and 5 fresh-process archive-only decodes passed.')


if __name__ == '__main__':
    main()
