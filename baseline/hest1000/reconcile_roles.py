"""Reconcile historical metadata only; never infer an unseen role from absence."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'baseline/evidence/COUNT-HEST-1000-001'
READINESS = ROOT / 'baseline/reports/validation_readiness_v0_1/validation_candidates.csv'

def rows(p):
    with p.open(encoding='utf-8-sig', newline='') as f: return list(csv.DictReader(f))

def main():
    metadata = rows(OUT / 'SELECTED.csv')
    prior = {r['sample_id']: r for r in rows(READINESS)}
    subsequent = {'MEND33', 'MEND37', 'MEND26', 'NCBI692', 'NCBI715', 'NCBI618'}
    result = []
    for r in metadata:
        h = prior.get(r['id'], {})
        exposed = r['historical_role'] == 'known_exposed' or r['id'] in subsequent or h.get('candidate_status') == 'exclude_prior_compression_exposure'
        result.append(dict(sample_id=r['id'], species=r['species'], platform=r['st_technology'], organ=r['organ'],
                           historical_role='known_exposed' if exposed else 'historical_role_unresolved',
                           source_group=h.get('source_group', 'UNKNOWN'),
                           source_scoped_donor_key=h.get('source_scoped_donor_key', ''),
                           prior_candidate_flag=r['prior_candidate_flag'],
                           prior_readiness_status=h.get('candidate_status', 'known_development_or_unresolved'),
                           strict_unseen_eligible=False, evaluation_released=False))
    with (OUT / 'COHORT_ROLES.csv').open('x', encoding='utf-8-sig', newline='') as f:
        w=csv.DictWriter(f, fieldnames=list(result[0])); w.writeheader(); w.writerows(result)
    summary = dict(selected=len(result), role_counts=dict(Counter(r['historical_role'] for r in result)),
                   prior_readiness_counts=dict(Counter(r['prior_readiness_status'] for r in result)),
                   prior_candidate_n=sum(r['prior_candidate_flag']=='True' for r in result),
                   strict_unseen_eligible=0, matrix_contents_read=False,
                   source_sha256=hashlib.sha256(READINESS.read_bytes()).hexdigest(),
                   cohort_roles_sha256=hashlib.sha256((OUT/'COHORT_ROLES.csv').read_bytes()).hexdigest())
    with (OUT / 'ROLE_AUDIT.json').open('x', encoding='utf-8') as f: json.dump(summary,f,indent=2)
    print(json.dumps(summary))

if __name__=='__main__': main()
