"""Read retained experiment evidence; never execute a codec or modify a run.

Raw JSON receipts are stored byte-for-byte in a content-addressed ZIP. Matrix,
metadata payloads, models and archives remain external; their hashes are public.
"""
import argparse
import bz2
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from threading import RLock


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def charged_paths(record, result, selected):
    """Keep both recorded archive schemas; do not invent a missing hash."""
    if result.get('archive_hashes'):
        return [(record.parent/'archive'/name, h) for name, h in sorted(result['archive_hashes'].items())]
    if result.get('package_sha256') and result.get('method') in ('IVCSC', 'IVCSC_bz2'):
        return [(record.parent/'count.cnt', result['package_sha256'])]
    if selected.get('archive_sha256'):
        return [(record.parent/'archive/archive.bin', selected['archive_sha256'])]
    return []


class Audit:
    def __init__(self, out):
        self.out = out
        self.blobs = zipfile.ZipFile(out / 'receipts.zip', 'w', zipfile.ZIP_DEFLATED)
        self.seen = set()
        self.paths = {}
        self.issues = []
        self.environments = {}
        self.configs = defaultdict(lambda: {'commands': set(), 'runtime_receipts': set(), 'manifests': set()})
        self.lock = RLock()

    def receipt(self, path):
        key = str(path)
        if key in self.paths:
            return self.paths[key]
        if not path.is_file():
            return None
        blob = path.read_bytes()
        digest = hashlib.sha256(blob).hexdigest()
        with self.lock:
            if digest not in self.seen:
                zi = zipfile.ZipInfo(digest + '.json', (1980, 1, 1, 0, 0, 0))
                zi.compress_type = zipfile.ZIP_DEFLATED
                self.blobs.writestr(zi, blob)
                self.seen.add(digest)
        ref = {'path': key, 'sha256': digest, 'bytes': len(blob)}
        self.paths[key] = ref
        return ref

    def check(self, condition, kind, path):
        if not condition:
            self.issues.append({'kind': kind, 'path': str(path)})
        return bool(condition)

    def archive(self, path, expected=None, members=False):
        if not path.is_file():
            self.check(False, 'missing_archive', path)
            return {'path': str(path), 'present': False}
        digest = sha(path)
        result = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest,
                  'recorded_sha256': expected, 'matches_record': digest == expected if expected else None}
        if expected:
            self.check(digest == expected, 'archive_hash_mismatch', path)
        if members:
            with zipfile.ZipFile(path) as z:
                infos = z.infolist()
                self.check(len(infos) == len({i.filename for i in infos}), 'duplicate_zip_members', path)
                manifest_blob = z.read('manifest.json')
                manifest = json.loads(manifest_blob)
                result['manifest'] = manifest
                result['manifest_sha256'] = hashlib.sha256(manifest_blob).hexdigest()
                result['members'] = {}
                recorded = manifest.get('files', manifest.get('members', {}))
                self.check(set(recorded) == set(z.namelist()) - {'manifest.json'}, 'manifest_member_set', path)
                for info in infos:
                    if info.filename == 'manifest.json':
                        continue
                    blob = z.read(info.filename)
                    h = hashlib.sha256(blob).hexdigest()
                    entry = {'bytes': len(blob), 'sha256': h}
                    if info.filename in ('value_base_k.bz2', 'value_cond_k.bz2'):
                        entry['uncompressed_bytes'] = len(bz2.decompress(blob))
                    result['members'][info.filename] = entry
                    rec = recorded.get(info.filename, {})
                    self.check(rec.get('sha256') == h and rec.get('bytes') == len(blob), 'manifest_member_hash', str(path) + ':' + info.filename)
                result['zip_framing_bytes'] = path.stat().st_size - sum(i.file_size for i in infos)
        return result

    def case_receipts(self, folder, method):
        result = []
        for path in sorted(folder.glob('*.json')):
            ref = self.receipt(path)
            obj = read(path)
            result.append(ref)
            if isinstance(obj, dict) and 'command' in obj:
                command = obj['command']
                self.configs[method]['commands'].add(json.dumps(command, ensure_ascii=False))
            if isinstance(obj, dict) and 'packages' in obj and 'executable' in obj:
                self.configs[method]['runtime_receipts'].add(ref['sha256'])
                self.environments[ref['sha256']] = obj
        return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project', type=Path, required=True)
    p.add_argument('--runs', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    release = Path(__file__).resolve().parents[1]
    a.output.mkdir(parents=True, exist_ok=False)
    audit = Audit(a.output)
    kroot = a.runs / 'COUNT-HEST-SHARED-K32-001'
    broot = a.runs / 'COUNT-HEST-BASELINES-1000-005-RESULTS-REPAIRED-20260923'
    eroot = a.project / 'baseline/evidence/COUNT-E3-MODULE-CONTRIBUTION-002-50'
    # Preserve raw selection tables and repair accounting, not just aggregate counts.
    for src, name in [(kroot/'ALL_SAMPLES.csv', 'K32_SELECTION.csv'),
                      (broot/'PAIR_RESULTS_9000.csv', 'COMPARATOR_SELECTION.csv'),
                      (broot/'REPAIR_AUDIT.csv', 'COMPARATOR_REPAIRS.csv')]:
        (a.output/name).write_bytes(src.read_bytes())
    pin_rows = []
    pin_sources = [kroot/'PINS.json', kroot/'RUN_PINS.json',
                   a.project/'baseline/evidence/VALUE_BEST_OF_9_50_005/PINS.json',
                   a.project/'baseline/evidence/COUNT-HEST-BASELINES-1000-004/PINS.json']
    for pin_path in pin_sources:
        audit.receipt(pin_path)
        for name, expected in read(pin_path).items():
            n = name.replace('\\', '/')
            original = Path(n) if ':' in n else (a.project/n if n.startswith('baseline/') else kroot/'code'/n)
            try:
                rel = original.relative_to(a.project)
            except ValueError:
                rel = Path('baseline/evidence/COUNT-HEST-SHARED-K32-001')/name if original.parent == kroot/'code' else None
            candidate = release/rel if rel else None
            actual = sha(original) if original.is_file() else None
            released = sha(candidate) if candidate and candidate.is_file() else None
            pin_rows.append({'pin_record': str(pin_path), 'name': name, 'historical_sha256': expected,
                             'retained_sha256': actual, 'release_path': rel.as_posix() if rel else None,
                             'release_sha256': released, 'historical_matches_retained': actual == expected,
                             'historical_matches_release': released == expected if released else None})
    dump(a.output/'SOURCE_PIN_BRIDGE.json', pin_rows)
    # Current inventory is explicitly not a historical execution lock.
    source_inventory = []
    for src in sorted((release/'baseline').rglob('*.py')):
        rel = src.relative_to(release)
        original = a.project/rel
        source_inventory.append({'path': rel.as_posix(), 'release_sha256': sha(src),
                                 'retained_source_sha256': sha(original) if original.is_file() else None})
    dump(a.output/'RELEASE_DEPENDENCIES.json', source_inventory)
    counts = Counter()
    krows = rows(kroot/'ALL_SAMPLES.csv')
    assert len(krows) == 1000 and len({r['sample_id'] for r in krows}) == 1000
    with (a.output/'K32_CASES.jsonl').open('w', encoding='utf-8') as out:
        for row in krows:
            record = Path(row['record_path'])
            result = read(record)
            item = {'sample_id': row['sample_id'], 'status': row['status'],
                    'source_sha256_recorded': row['source_sha256'], 'historical_commit': None,
                    'receipt_refs': audit.case_receipts(record.parent, 'Shared_K32'),
                    'archive': audit.archive(Path(row['archive_path']), row['archive_sha256']),
                    'historical_exact': result.get('exact', result.get('checks', row['exact_count_identity_metadata'])),
                    'fresh_decode_performed': False}
            audit.check(item['archive'].get('bytes') == int(row['total_archive_bytes']), 'K32_byte_count', record)
            out.write(json.dumps(item, ensure_ascii=False) + '\n')
            counts['K32'] += 1
            if counts['K32'] % 250 == 0:
                print(dict(counts), flush=True)
    brows = rows(broot/'PAIR_RESULTS_9000.csv')
    assert len(brows) == 9000 and len({(r['sample_id'], r['method']) for r in brows}) == 9000
    handles = {}
    def comparator_case(row):
            method = row['method']
            record = Path(row['record_path'])
            result = read(record)
            ref = audit.receipt(record)
            audit.check(ref['sha256'] == row['result_sha256'], 'selected_result_hash', record)
            folder = record.parent
            archive = folder/'archive'
            charged = charged_paths(record, result, row)
            audit.check(bool(charged), 'missing_charged_archive_hashes', record)
            files = [audit.archive(path, expected) for path, expected in charged]
            audit.check(sum(f.get('bytes', 0) for f in files) == int(row['total_archive_bytes']), 'comparator_charged_bytes', record)
            manifest = None
            if (archive/'manifest.json').is_file():
                manifest = read(archive/'manifest.json')
                audit.receipt(archive/'manifest.json')
            elif len(charged) == 1 and charged[0][0].is_file() and zipfile.is_zipfile(charged[0][0]):
                with zipfile.ZipFile(charged[0][0]) as z:
                    if 'manifest.json' in z.namelist():
                        manifest = json.loads(z.read('manifest.json'))
            item = {'sample_id': row['sample_id'], 'method': method, 'status': row['status'],
                    'source_sha256_recorded': result.get('source_sha256'),
                    'canonical_dtype_recorded': result.get('canonical_dtype'),
                    'source_storage_dtype_recorded': result.get('source_storage_dtype'),
                    'receipt_refs': audit.case_receipts(folder, method), 'charged_files': files,
                    'manifest': manifest, 'historical_exact': result.get('exact', result.get('checks')),
                    'repair_selected': row['repaired_attempt'], 'fresh_decode_performed': False}
            return method, item
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for method, item in pool.map(comparator_case, brows):
                if method not in handles:
                    handles[method] = (a.output/('COMPARATOR_' + method + '.jsonl')).open('w', encoding='utf-8')
                handles[method].write(json.dumps(item, ensure_ascii=False) + '\n')
                counts[method] += 1
                if sum(counts.values()) % 500 == 0:
                    print(dict(counts), flush=True)
    finally:
        for handle in handles.values():
            handle.close()
    # Include failed predecessor receipts used in the repaired comparison.
    for repair in rows(broot/'REPAIR_AUDIT.csv'):
        audit.case_receipts(Path(repair['prior_failure_record_path']).parent, repair['method'] + '_prior_failure')
    with (a.output/'E3_CASES.jsonl').open('w', encoding='utf-8') as out:
        for path in sorted((eroot/'archives').glob('*/*/archive.cnt')):
            folder = path.parent
            encode = read(folder/'encode.json') if (folder/'encode.json').exists() else {}
            runner = read(folder/'runner.json')
            expected = encode.get('archive_sha256') or runner.get('result', {}).get('archive_sha256')
            item = {'sample_id': folder.parent.name, 'arm': folder.name,
                    'receipt_refs': audit.case_receipts(folder, 'E3_' + folder.name),
                    'archive': audit.archive(path, expected, members=True), 'fresh_decode_performed': False}
            if folder.name == 'no_sharing':
                man = item['archive']['manifest']
                audit.check(man.get('value_group_count') == 32 and man.get('support_bucket_count') == 8 and man.get('q1_sharing') is False, 'E3_B8_K32_q1_contract', path)
                m = item['archive']['members']
                audit.check(m['value_base_k.bz2']['uncompressed_bytes'] == 32*32*2 and m['value_cond_k.bz2']['uncompressed_bytes'] == 32*7*32*2 and m['value_odds.u32']['bytes'] == 32*7*4, 'E3_model_shapes', path)
            out.write(json.dumps(item, ensure_ascii=False) + '\n')
            counts['E3_' + folder.name] += 1
    for src in [kroot/'PROTOCOL.json', kroot/'FINAL_VERIFICATION.json', kroot/'REPRODUCTION.json',
                a.project/'baseline/evidence/COUNT-MATCHED-READY-001/wheel_manifest.json']:
        audit.receipt(src)
    audit.blobs.close()
    dump(a.output/'RECEIPT_INDEX.json', list(audit.paths.values()))
    dump(a.output/'HISTORICAL_RUNTIME_RECEIPTS.json', audit.environments)
    dump(a.output/'COMMANDS_BY_CONFIGURATION.json', {k: {n: sorted(v) for n, v in value.items()} for k, value in audit.configs.items()})
    summary = {'schema': 'shared-evidence-bridge-v1', 'base_release_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=release, text=True).strip(),
               'historical_execution_commit': None, 'historical_commit_status': 'not recorded; packaging commit is not an execution commit',
               'counts': dict(counts), 'receipt_blobs': len(audit.seen), 'receipt_paths': len(audit.paths),
               'archive_integrity_issues': audit.issues, 'new_codec_runs': 0,
               'claim_limit': 'Recorded configurations only; no complete historical software reproduction chain, fairness certification, or universal superiority.'}
    dump(a.output/'SUMMARY.json', summary)
    dump(a.output/'ARTIFACT_SHA256.json', [{'path': f.name, 'bytes': f.stat().st_size, 'sha256': sha(f)} for f in sorted(a.output.iterdir()) if f.is_file()])
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    if audit.issues:
        raise SystemExit('Evidence inconsistencies found: inspect SUMMARY.json')


if __name__ == '__main__':
    main()
