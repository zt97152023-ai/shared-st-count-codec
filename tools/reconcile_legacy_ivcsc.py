"""Reconcile already-collected legacy IVCSC receipts without rescanning other runs."""
import json
from pathlib import Path
import zipfile
from concurrent.futures import ThreadPoolExecutor
from build_evidence_bridge import read, rows, sha, dump, charged_paths


def main():
    out = Path(__file__).resolve().parents[1]/'provenance/evidence_20260928'
    summary = read(out/'SUMMARY.json')
    selection = {(r['sample_id'], r['method']): r for r in rows(out/'COMPARATOR_SELECTION.csv')}
    resolved = set()
    details = []
    def reconcile(row):
        if row['charged_files']:
            return row, None
        selected = selection[row['sample_id'], row['method']]
        record = Path(selected['record_path'])
        old = read(record)
        assert old['method'] in ('IVCSC', 'IVCSC_bz2') and old.get('package_sha256')
        [(path, expected)] = charged_paths(record, old, selected)
        actual = sha(path)
        assert actual == expected and path.stat().st_size == int(selected['total_archive_bytes']) == old['package_bytes']
        with zipfile.ZipFile(path) as z:
            row['manifest'] = json.loads(z.read('manifest.json'))
        row['charged_files'] = [{'path': str(path), 'bytes': path.stat().st_size,
                                 'sha256': actual, 'recorded_sha256': expected, 'matches_record': True}]
        row['receipt_schema'] = 'legacy_ivcsc_package_sha256'
        row['historical_check_limit'] = 'shape/indptr/indices/values/metadata checks; dtype and source hash not separately recorded in this case receipt'
        return row, {'result_path': str(record), 'package_path': str(path), 'sha256': actual,
                     'reason': 'legacy count.cnt/package_sha256 schema, not missing archive'}
    for method in ('IVCSC', 'IVCSC_bz2'):
        path = out/('COMPARATOR_'+method+'.jsonl')
        data = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        with ThreadPoolExecutor(max_workers=8) as pool:
            fixed = list(pool.map(reconcile, data))
        for row, detail in fixed:
            if detail:
                resolved.add(detail['result_path']); details.append(detail)
        path.write_text(''.join(json.dumps(row, ensure_ascii=False)+'\n' for row,_ in fixed), encoding='utf-8')
    assert len(resolved) == 113, len(resolved)
    summary['archive_integrity_issues'] = [i for i in summary['archive_integrity_issues']
        if not (i['path'] in resolved and i['kind'] in ('missing_charged_archive_hashes', 'comparator_charged_bytes'))]
    summary['legacy_ivcsc_cases'] = 113
    dump(out/'LEGACY_IVCSC_SCHEMA_RECONCILIATION.json', details)
    dump(out/'SUMMARY.json', summary)
    print('113 legacy IVCSC archives rehashed and reconciled; remaining issues:', len(summary['archive_integrity_issues']))


if __name__ == '__main__':
    main()
