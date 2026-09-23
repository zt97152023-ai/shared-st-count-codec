"""Metadata-only deterministic cohort; never open H5AD contents."""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
META = Path('E:/Hestdata/HEST_v1_0_0.csv')
OUT = ROOT / 'baseline/evidence/COUNT-HEST-1000-001'

def select(rows, target):
    if target > len(rows) or len({r['id'] for r in rows}) != len(rows):
        raise ValueError('Insufficient metadata or duplicate IDs')
    groups = defaultdict(list)
    for r in rows:
        groups[tuple(r.get(k, '') or 'UNKNOWN' for k in ('species', 'st_technology', 'organ'))].append(r)
    if len(groups) > target:
        raise ValueError('Cannot retain every metadata stratum')
    quota = {k: 1 for k in groups}
    while sum(quota.values()) < target:
        eligible = [k for k in sorted(groups) if quota[k] < len(groups[k])]
        key = max(eligible, key=lambda k: target * len(groups[k]) / len(rows) - quota[k])
        quota[key] += 1
    selected = []
    for k in sorted(groups):
        ranked = sorted(groups[k], key=lambda r: hashlib.sha256(('HEST1000-v1:' + r['id']).encode()).hexdigest())
        selected += ranked[:quota[k]]
    return sorted(selected, key=lambda r: r['id']), groups, quota

def writecsv(path, rows, fields):
    with path.open('x', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)

def main():
    with META.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    chosen, groups, quota = select(rows, 1000)
    exposed_cfg = json.loads((ROOT / 'baseline/configs/COUNT-E1-100.json').read_text(encoding='utf-8'))
    exposed = {r['id'] for r in exposed_cfg['samples']} | {'INT7', 'NCBI692', 'NCBI715', 'NCBI618'}
    pending = json.loads((ROOT / 'baseline/reports/matched_extension_v0_1/questionnaire_148.json').read_text(encoding='utf-8'))
    pending_ids = {r['sample_id'] for r in pending}
    fields = ['id', 'species', 'st_technology', 'organ', 'disease_state', 'study_link', 'patient', 'license', 'source_path', 'file_exists', 'source_file_bytes', 'historical_role', 'prior_candidate_flag', 'selected']
    ids = {r['id'] for r in chosen}
    records = []
    for r in sorted(rows, key=lambda r: r['id']):
        p = Path('E:/Hestdata/st') / (r['id'] + '.h5ad')
        item = {k: r.get(k, '') for k in fields}
        item.update(source_path=str(p), file_exists=p.is_file(), source_file_bytes=p.stat().st_size if p.is_file() else None,
                    historical_role='known_exposed' if r['id'] in exposed else 'exposure_unresolved',
                    prior_candidate_flag=r['id'] in pending_ids, selected=r['id'] in ids)
        records.append(item)
    writecsv(OUT / 'ALL_METADATA.csv', records, fields)
    writecsv(OUT / 'SELECTED.csv', [r for r in records if r['selected']], fields)
    strata = [dict(species=k[0], platform=k[1], organ=k[2], available=len(groups[k]), selected=quota[k]) for k in sorted(groups)]
    writecsv(OUT / 'STRATA.csv', strata, ['species', 'platform', 'organ', 'available', 'selected'])
    result = dict(total_metadata=len(rows), selected=len(ids), metadata_strata=len(groups),
                  selected_platform_counts=dict(Counter(r['st_technology'] for r in chosen)),
                  selected_species_counts=dict(Counter(r['species'] for r in chosen)),
                  metadata_sha256=hashlib.sha256(META.read_bytes()).hexdigest(),
                  selected_sha256=hashlib.sha256((OUT / 'SELECTED.csv').read_bytes()).hexdigest(),
                  selected_known_exposed=sum(r['selected'] and r['historical_role']=='known_exposed' for r in records),
                  selected_prior_candidates=sum(r['selected'] and r['prior_candidate_flag'] for r in records),
                  matrix_contents_read=False, full_run_released=False)
    with (OUT / 'SELECTION.json').open('x', encoding='utf-8') as f: json.dump(result, f, indent=2)
    print(json.dumps(result))

if __name__ == '__main__': main()
