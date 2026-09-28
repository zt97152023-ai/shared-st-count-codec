"""Add configuration history and finalize the evidence manifest after collection."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from collections import Counter

from build_evidence_bridge import sha, read, dump
from correct_e3_descriptions import main as correct_descriptions


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--project', type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    correct_descriptions()
    out = root/'provenance/evidence_20260928'
    summary = read(out/'SUMMARY.json')
    assert not summary['archive_integrity_issues']
    # Copied E3 arms record their archive hash in runner.json rather than an
    # encode.json. Reconcile those receipts against the archive hashes just read.
    e3_rows = [json.loads(line) for line in (out/'E3_CASES.jsonl').read_text(encoding='utf-8').splitlines()]
    with zipfile.ZipFile(out/'receipts.zip') as receipts:
        for row in e3_rows:
            runner_ref = next(r for r in row['receipt_refs'] if r['path'].replace('\\', '/').endswith('/runner.json'))
            runner = json.loads(receipts.read(runner_ref['sha256']+'.json'))
            expected = runner['result']['archive_sha256']
            if row['archive']['sha256'] != expected:
                raise ValueError('E3 runner/archive mismatch: '+row['sample_id']+'/'+row['arm'])
            row['archive']['recorded_sha256'] = expected
            row['archive']['matches_record'] = True
    (out/'E3_CASES.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in e3_rows), encoding='utf-8')
    folder = args.project/'baseline/evidence/COUNT-HEST-BASELINES-1000-005'
    configs = [folder/n for n in ('runner_plan.json', 'runner_plan_recovered.json',
                                  'runner_plan_recovered03.json', 'REPAIR_CSR_BZIP2_01.json')]
    legacy_root = args.project/'baseline/evidence/COUNT-IVCSC-100'
    configs += [legacy_root/'main/config.json', legacy_root/'main/environment.json', legacy_root/'BUILD_PROVENANCE.json']
    legacy_samples = {r['id']: r for r in read(legacy_root/'main/config.json')['samples']}
    k32_samples = {r['sample_id']: r for r in __import__('build_evidence_bridge').rows(out/'K32_SELECTION.csv')}
    index, bridge = [], []
    with zipfile.ZipFile(out/'configuration_receipts.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for path in configs:
            blob = path.read_bytes()
            h = hashlib.sha256(blob).hexdigest()
            zi = zipfile.ZipInfo(h+'.json', (1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, blob)
            index.append({'path': str(path), 'bytes': len(blob), 'sha256': h})
            obj = json.loads(blob)
            pins = obj.get('code_pins', obj.get('source_hashes', {}))
            if path.name == 'REPAIR_CSR_BZIP2_01.json':
                pins = {str(args.project/'baseline/hest1000/general_baselines.py'): obj['comparator_sha256'],
                        str(folder/'extra_worker_checked.py'): obj['checked_wrapper_sha256'],
                        str(folder/'repair_csr_bzip2_failures.py'): obj['repair_runner_sha256']}
            for name, expected in pins.items():
                original = Path(name)
                try:
                    rel = original.relative_to(args.project)
                except ValueError:
                    rel = None
                published = root/rel if rel else None
                actual = sha(original) if original.is_file() else None
                public_hash = sha(published) if published and published.is_file() else None
                bridge.append({'configuration_receipt_sha256': h, 'source_path': name,
                               'historical_sha256': expected, 'retained_sha256': actual,
                               'release_path': rel.as_posix() if rel else None,
                               'release_sha256': public_hash,
                               'historical_matches_retained': actual == expected,
                               'historical_matches_release': public_hash == expected if public_hash else None})
    dump(out/'CONFIGURATION_RECEIPT_INDEX.json', index)
    dump(out/'COMPARATOR_SOURCE_PIN_BRIDGE.json', bridge)
    # Configuration contracts summarize only values in retained records.
    contracts = []
    environments = read(out/'HISTORICAL_RUNTIME_RECEIPTS.json')
    commands = read(out/'COMMANDS_BY_CONFIGURATION.json')
    for config in commands.values():
        config['commands'] = [json.loads(c) if isinstance(c, str) else c for c in config['commands']]
    dump(out/'COMMANDS_BY_CONFIGURATION.json', commands)
    for path in sorted(out.glob('COMPARATOR_*.jsonl')):
        cases = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        method = cases[0]['method']
        layouts, variants = Counter(), Counter()
        for case in cases:
            if method in ('IVCSC', 'IVCSC_bz2') and any(f['path'].replace('\\', '/').endswith('/count.cnt') for f in case['charged_files']):
                sid = case['sample_id']
                source_hash = legacy_samples[sid]['source_sha256']
                assert source_hash == k32_samples[sid]['source_sha256'], ('legacy source mismatch', sid)
                case['source_sha256_from_run_config'] = source_hash
                case['run_config_receipt_sha256'] = sha(legacy_root/'main/config.json')
                case['run_environment_receipt_sha256'] = sha(legacy_root/'main/environment.json')
                case['historical_check_limit'] = 'shape/indptr/indices/values/metadata checked; dtype not a separate boolean in this legacy receipt'
            charged = tuple(sorted(f['path'].replace('\\', '/').split('/archive/', 1)[-1] if '/archive/' in f['path'].replace('\\', '/') else Path(f['path']).name for f in case['charged_files']))
            layouts[charged] += 1
            man = case['manifest'] or {}
            config = {k: man[k] for k in ('schema', 'method', 'dtype', 'value_dtype', 'index_dtype',
                      'bpcells_version', 'upstream_commit', 'parameters', 'orientation',
                      'transpose', 'sorted', 'layout') if k in man}
            variants[json.dumps(config, sort_keys=True)] += 1
        path.write_text(''.join(json.dumps(c, ensure_ascii=False)+'\n' for c in cases), encoding='utf-8')
        contracts.append({'method': method, 'case_file': path.name, 'selected_cases': len(cases),
                          'canonical_dtype_observations': dict(Counter(str(r['canonical_dtype_recorded']) for r in cases)),
                          'source_storage_dtype_observations': dict(Counter(str(r['source_storage_dtype_recorded']) for r in cases)),
                          'manifest_configurations': [{'configuration': json.loads(k), 'cases': v} for k,v in sorted(variants.items())],
                          'charged_file_layouts': [{'files': list(k), 'cases': v} for k,v in sorted(layouts.items())],
                          'runtime_variants': [environments[h] for h in commands.get(method, {}).get('runtime_receipts', [])],
                          'cases_with_encode_runtime_receipt': sum(any(r['path'].replace('\\','/').endswith('/encode_runtime.json') for r in c['receipt_refs']) for c in cases),
                          'cases_with_legacy_run_environment': sum('run_environment_receipt_sha256' in c for c in cases),
                          'commands': 'COMMANDS_BY_CONFIGURATION.json#'+method,
                          'recovery_records': 'Per-case receipt_refs, including EXACT.json or RESULT.json.exact; raw bytes in receipts.zip',
                          'preserved_fields': ['canonical integer counts', 'axis labels and order', 'coordinate shape/dtype/bytes', '047 contract metadata'],
                          'excluded_fields': ['arbitrary source H5AD obs/var/layers/uns', 'source file byte layout'],
                          'claim_limit': 'Recorded configuration only; missing runtime observations are not filled from current installations.'})
    dump(out/'COMPARATOR_CONTRACTS.json', contracts)
    # Refresh inventory to include all restored comparator adapters.
    inventory = []
    for path in sorted((root/'baseline').rglob('*.py')):
        rel = path.relative_to(root)
        original = args.project/rel
        inventory.append({'path': rel.as_posix(), 'release_sha256': sha(path),
                          'retained_source_sha256': sha(original) if original.is_file() else None})
    dump(out/'RELEASE_DEPENDENCIES.json', inventory)
    # Every added historical source file is recorded without changing its bytes.
    manifest = read(root/'SOURCE_MANIFEST.json')
    known = {r['path'] for r in manifest}
    for path in sorted((root/'baseline').rglob('*')):
        rel = path.relative_to(root).as_posix()
        original = args.project/rel
        if path.suffix not in ('.py', '.json', '.txt') or rel in known or not original.is_file():
            continue
        if sha(path) != sha(original):
            raise ValueError('Added historical source differs: '+rel)
        manifest.append({'path': rel, 'source': str(original), 'bytes': path.stat().st_size,
                         'sha256': sha(path)})
    dump(root/'SOURCE_MANIFEST.json', manifest)
    # The original consolidated README remains covered by SOURCE_MANIFEST at
    # docs/historical/E3_CONSOLIDATED_README.md, rather than its corrected path.
    original_doc = root/'docs/historical/E3_CONSOLIDATED_README.md'
    corrected_doc = root/'baseline/evidence/COUNT-E3-MODULE-CONTRIBUTION-CONSOLIDATED/README.md'
    dump(out/'DOCUMENTATION_CORRECTIONS.json', {
        'historical_document': original_doc.relative_to(root).as_posix(),
        'historical_sha256': sha(original_doc),
        'corrected_document': corrected_doc.relative_to(root).as_posix(),
        'corrected_sha256': sha(corrected_doc),
        'reason': 'Replace incorrect eight-class tail attribution with measured B8/K32 and singleton-only semantics.'})
    dump(out/'E3_DESCRIPTION_CORRECTIONS.json', read(root/'provenance/E3_DESCRIPTION_CORRECTIONS.json'))
    validation = read(root/'validation/E3_VALIDATION_20260928.json')
    summary['current_release_validation'] = {
        'report': 'validation/E3_VALIDATION_20260928.json',
        'sha256': sha(root/'validation/E3_VALIDATION_20260928.json'),
        'q1_headers_checked': len(validation['q1_archives']),
        'fresh_archive_only_decodes': len(validation['decode_checks']),
        'new_encodes': 0, 'scope': 'NCBI180 five E3 arms; current release environment'}
    summary['archive_audit_new_codec_runs'] = summary.pop('new_codec_runs', 0)
    summary['configuration_pin_mismatches'] = [r for r in bridge if not r['historical_matches_retained']]
    dump(out/'SUMMARY.json', summary)
    dump(out/'ARTIFACT_SHA256.json', [{'path': f.name, 'bytes': f.stat().st_size, 'sha256': sha(f)}
                                    for f in sorted(out.iterdir()) if f.is_file() and f.name != 'ARTIFACT_SHA256.json'])
    print(json.dumps({'configuration_pins': len(bridge), 'retained_pin_mismatches': len(summary['configuration_pin_mismatches']),
                      'release_source_files': len(inventory), 'source_manifest_entries': len(manifest)}, indent=2))


if __name__ == '__main__':
    main()
