"""Portable verification of the published receipts and source correspondence."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import zipfile


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def verify(root, bundle):
    for entry in read(bundle/'ARTIFACT_SHA256.json'):
        file = bundle/entry['path']
        require(file.parent == bundle and file.is_file(), 'missing/invalid artifact '+entry['path'])
        require(file.stat().st_size == entry['bytes'] and digest(file) == entry['sha256'], 'artifact hash '+entry['path'])
    index = read(bundle/'RECEIPT_INDEX.json')
    refs = {(r['path'], r['sha256'], r['bytes']) for r in index}
    with zipfile.ZipFile(bundle/'receipts.zip') as z:
        require(len(z.namelist()) == len(set(z.namelist())), 'duplicate receipt member')
        for info in z.infolist():
            require(info.filename == hashlib.sha256(z.read(info)).hexdigest()+'.json', 'receipt content hash '+info.filename)
        for ref in index:
            require(z.getinfo(ref['sha256']+'.json').file_size == ref['bytes'], 'receipt size '+ref['path'])
        counts = Counter()
        seen = set()
        for file in sorted(bundle.glob('*CASES.jsonl')) + sorted(bundle.glob('COMPARATOR_*.jsonl')):
            with file.open(encoding='utf-8') as f:
                for line in f:
                    row = json.loads(line)
                    method = row.get('method', 'E3_'+row['arm'] if 'arm' in row else 'K32')
                    key = row['sample_id'], method
                    require(key not in seen, 'duplicate case '+str(key))
                    seen.add(key)
                    counts[method] += 1
                    receipts = row['receipt_refs']
                    require(bool(receipts), 'missing case receipts '+str(key))
                    for ref in receipts:
                        require((ref['path'], ref['sha256'], ref['bytes']) in refs, 'unindexed receipt '+ref['path'])
                    names = {ref['path'].replace('\\', '/').rsplit('/', 1)[-1].lower(): ref for ref in receipts}
                    expected = 'accepted_exact.json' if 'arm' in row else ('verify.json' if method == 'K32' else 'exact.json')
                    # Completion runners sometimes embed EXACT in RESULT.json.
                    if expected in names:
                        obj = json.loads(z.read(names[expected]['sha256']+'.json'))
                    else:
                        require('result.json' in names, 'missing recovery receipt '+str(key))
                        obj = json.loads(z.read(names['result.json']['sha256']+'.json'))
                        obj = obj.get('exact', obj)
                    checks = obj.get('checks', obj)
                    legacy_ivcsc = (obj.get('method') in ('IVCSC', 'IVCSC_bz2')
                                    and bool(obj.get('package_sha256')) and obj.get('status') == 'success'
                                    and all(checks.get(k) is True for k in ('shape', 'indptr', 'indices', 'values', 'metadata')))
                    require(checks.get('all') is True or legacy_ivcsc, 'recovery not recorded as exact '+str(key))
                    archives = row.get('charged_files', [row.get('archive')])
                    for archive in archives:
                        require(archive and len(archive.get('sha256', '')) == 64, 'missing archive identity '+str(key))
                        require(archive.get('matches_record') is not False, 'archive mismatch '+str(key))
        require(counts['K32'] == 1000, 'K32 coverage')
        for arm in ('full', 'no_support', 'no_value', 'no_spatial', 'no_sharing'):
            require(counts['E3_'+arm] == 50, 'E3 coverage '+arm)
        methods = ('BP_gene_none', 'BP_spot_mean', 'IVCSC', 'IVCSC_bz2', 'CSR_ZSTD19', 'CSC_ZSTD19', 'H5AD_GZIP4', 'CSR_BZIP2_9', 'Pcodec')
        for method in methods:
            require(counts[method] == 1000, 'comparator coverage '+method)
    for entry in read(bundle/'RELEASE_DEPENDENCIES.json'):
        require(digest(root/entry['path']) == entry['release_sha256'], 'release dependency '+entry['path'])
    summary = read(bundle/'SUMMARY.json')
    require(not summary['archive_integrity_issues'], 'archive integrity issues')
    require(summary['historical_execution_commit'] is None, 'historical commit must not be invented')
    require(dict(counts) == summary['counts'], 'summary coverage differs')
    for entry in read(bundle/'SOURCE_PIN_BRIDGE.json'):
        if entry['release_sha256']:
            require(digest(root/entry['release_path']) == entry['release_sha256'], 'source pin bridge '+entry['release_path'])
    if (bundle/'CONFIGURATION_RECEIPT_INDEX.json').exists():
        with zipfile.ZipFile(bundle/'configuration_receipts.zip') as z:
            for entry in read(bundle/'CONFIGURATION_RECEIPT_INDEX.json'):
                blob = z.read(entry['sha256']+'.json')
                require(len(blob) == entry['bytes'] and hashlib.sha256(blob).hexdigest() == entry['sha256'], 'configuration receipt '+entry['path'])
        for entry in read(bundle/'COMPARATOR_SOURCE_PIN_BRIDGE.json'):
            if entry['release_sha256']:
                require(digest(root/entry['release_path']) == entry['release_sha256'], 'comparator source bridge '+entry['release_path'])
    validation = summary.get('current_release_validation')
    if validation:
        require(digest(root/validation['report']) == validation['sha256'], 'current E3 validation report')
    if (bundle/'E3_DESCRIPTION_CORRECTIONS.json').exists():
        for correction in read(bundle/'E3_DESCRIPTION_CORRECTIONS.json'):
            require(digest(root/correction['path']) == correction['published_sha256'], 'E3 corrected description')
            require(digest(root/correction['historical_path']) == correction['historical_sha256'], 'E3 historical description')
    return {'status': 'passed', 'case_counts': dict(counts), 'receipt_paths': len(index),
            'scope': 'public evidence integrity and recorded exact recovery; no cohort decode replay'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle', type=Path)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = verify(root, args.bundle or root/'provenance/evidence_20260928')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
