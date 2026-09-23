"""Read-only physical archive and recorded-recovery audit; writes evidence on E only."""
from pathlib import Path
import csv,json,hashlib,importlib.util,zipfile,statistics
import numpy as np
P=Path(__file__).resolve().parent
ROOT=P.parents[2]
OUT=Path(json.loads((P/'PROTOCOL.json').read_text())['output_root'])
dep=P.parent/'VALUE_K8_CANDIDATE_SCAN_004/audit_final.py'
spec=importlib.util.spec_from_file_location('archive_review',dep);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
read=old.read
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def physical(path,s,K):
 r=old.inspect(path,s,K);f=Path(path).parent;raw=read(path)
 arrays=raw['exact']['decoded_canonical_csr_arrays']
 checks={}
 for n,length in [('values',int(s['n_nonzero'])),('indices',int(s['n_nonzero'])),('indptr',int(s['n_spots'])+1)]:
  a=arrays[n];checks[n]=a['shape']==[length] and a['nbytes']==length*np.dtype(a['dtype']).itemsize
 checks['int64_values']=np.dtype(arrays['values']['dtype'])==np.dtype('int64')
 checks['integer_indices']=all(np.issubdtype(np.dtype(arrays[n]['dtype']),np.integer) for n in ['indices','indptr'])
 historic=Path(s['result_path']).parent/'archive/count.cnt'
 checks['historical_sha_size']=sha(historic)==s['archive_sha256'] and historic.stat().st_size==int(s['archive_bytes'])
 with zipfile.ZipFile(historic) as z:
  manifest=json.loads(z.read('manifest.json'))
  checks['historical_K8']=manifest.get('value_group_count',8)==8
  checks['canonical_pair']=manifest['canonical_sha256']==r['canonical_sha256']
  checks['fixed_members']=all(hashlib.sha256(z.read(n)).hexdigest()==r['members'][n]['sha256'] for n in old.FIXED)
 r.update(extra_checks=checks,canonical_csr_bytes=sum(a['nbytes'] for a in arrays.values()),K8_bytes=int(s['archive_bytes']))
 r['all_pass'] &= all(checks.values())
 return r
def main():
 assert (OUT/'DONE.json').exists()
 samples=list(csv.DictReader((P/'DATA_SPLIT.csv').open(encoding='utf-8-sig')));idx=read(OUT/'INDEX.json')
 assert len(samples)==len(idx)==1000 and set(idx)=={s['id'] for s in samples}
 records=[];errors=[];excluded=[]
 for s in samples:
  item=idx[s['id']]
  if item['status']!='success':excluded.append({'sample_id':s['id'],**item});continue
  try:records.append(physical(item['record_path'],s,32))
  except Exception as exc:errors.append({'sample_id':s['id'],'error':repr(exc)})
 exported={r['sample_id']:r for r in csv.DictReader((OUT/'ALL_SAMPLES.csv').open(encoding='utf-8-sig'))}
 ledger_export={r['sample_id']:r for r in csv.DictReader((OUT/'PHYSICAL_LEDGER.csv').open(encoding='utf-8-sig'))}
 assert set(exported)==set(idx)
 export_checks=[]
 for r in records:
  row=exported[r['sample_id']];stream=r['ledger']['support_stream']+r['ledger']['value_stream'];s=next(s for s in samples if s['id']==r['sample_id'])
  c={'bytes':int(row['total_archive_bytes'])==r['archive_bytes'],'csr':int(row['canonical_csr_bytes'])==r['canonical_csr_bytes'],
   'stream':int(row['count_stream_bytes'])==stream,'savings':int(row['saved_vs_K8_bytes'])==r['K8_bytes']-r['archive_bytes'],
   'bpc':abs(float(row['count_stream_bits_per_count'])-8*stream/int(s['n_counts']))<1e-10,'dense':int(row['dense_int64_bytes'])==8*int(s['n_counts'])}
  fee=r['ledger'];six={'payload_streams':stream,'paid_model_members':fee['support_model']+fee['value_model_and_group_map'],'graph_index':fee['graph'],'identity_coordinates':fee['identity_coordinate_metadata'],'manifest':fee['manifest'],'zip_framing':fee['container_overhead']}
  c['six_category_ledger']=sum(six.values())==r['archive_bytes'] and all(int(ledger_export[r['sample_id']][n])==v for n,v in six.items())
  c['archive_bpc']=abs(float(row['full_archive_bits_per_count'])-8*r['archive_bytes']/int(s['n_counts']))<1e-10
  if int(s['n_nonzero']):
   c['bpnz']=abs(float(row['count_stream_bits_per_nonzero'])-8*stream/int(s['n_nonzero']))<1e-10
   c['archive_bpnz']=abs(float(row['full_archive_bits_per_nonzero'])-8*r['archive_bytes']/int(s['n_nonzero']))<1e-10
  export_checks.append({'sample_id':r['sample_id'],'checks':c,'pass':all(c.values())})
 summary=read(OUT/'SUMMARY.json');a=next(x for x in summary['groups'] if x['category']=='all')
 k8=sum(r['K8_bytes'] for r in records);k32=sum(r['archive_bytes'] for r in records)
 summary_ok=a['K8_archive_bytes']==k8 and a['K32_archive_bytes']==k32 and a['saved_bytes']==k8-k32 and summary['accepted']==len(records)
 repeats=[]
 for rep in read(OUT/'REPRODUCTION.json'):
  s=next(s for s in samples if s['id']==rep['sample_id']);r=physical(rep['record_path'],s,32)
  r['identical_to_main']=r['archive_sha256']==next(x for x in records if x['sample_id']==s['id'])['archive_sha256'];repeats.append(r)
 pins={n:sha(P/n)==v for n,v in read(P/'RUN_PINS.json').items()};prod={n:sha(ROOT/n)==v for n,v in read(P/'PINS.json').items()}
 report={'all_accepted_evidence_pass':not errors and all(r['all_pass'] for r in records) and all(r['pass'] for r in export_checks) and summary_ok and all(pins.values()) and all(prod.values()) and all(r['all_pass'] and r['identical_to_main'] for r in repeats),
 'full1000_complete':len(records)==1000 and not excluded,'scope':'physical archives plus recorded independent decode/verify evidence, not a new fresh decode by auditor',
 'accepted':len(records),'excluded_or_failed':excluded,'K8_bytes':k8,'K32_bytes':k32,'saved_bytes':k8-k32,'records':records,'export_checks':export_checks,'summary_pass':summary_ok,'reproductions':repeats,'experiment_pins':pins,'production_pins':prod,'errors':errors,'verifier_sha256':sha(__file__)}
 (P/'FINAL_VERIFICATION.json').write_text(json.dumps(report,indent=2),encoding='utf8')
 print(json.dumps({k:report[k] for k in ['all_accepted_evidence_pass','full1000_complete','accepted','K8_bytes','K32_bytes','saved_bytes','errors']}))
if __name__=='__main__':main()
