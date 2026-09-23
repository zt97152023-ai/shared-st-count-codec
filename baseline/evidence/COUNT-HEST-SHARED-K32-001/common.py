"""Frozen fixed-K32 runner utilities; all data outputs live on D."""
from pathlib import Path
import json,csv,zipfile,shutil,ctypes
import helpers as h
P=Path(__file__).resolve().parent;OUT=h.P;C=h.core
ctypes.windll.kernel32.SetErrorMode(3)
def samples():return list(csv.DictReader((P/'DATA_SPLIT.csv').open(encoding='utf-8-sig')))
def pins():
 for n,v in json.loads((P/'RUN_PINS.json').read_text()).items():assert h.sha(P/n)==v,n
 for n,v in json.loads((P/'PINS.json').read_text()).items():assert h.sha(C.ROOT/n)==v,n
def old_archive(s):return Path(s['result_path']).parent/'archive/count.cnt'
def compare_old(s,r):
 a=old_archive(s);assert a.stat().st_size==int(s['archive_bytes']) and h.sha(a)==s['archive_sha256']
 fees,members=C.ledger(a)
 for n in ['support.rans','base_probability.bz2','shared_odds.u32','graph.bz2','metadata.bz2']:assert members[n]==r['members'][n],n
 with zipfile.ZipFile(a) as z:m=json.loads(z.read('manifest.json'))
 assert m.get('value_group_count',8)==8
 assert m['canonical_sha256']==r['exact']['canonical_sha256']
 return {'historical_K8_archive':str(a),'archive_sha256':s['archive_sha256'],'K8_bytes':int(s['archive_bytes']),'source_sha256':s['source_sha256'],'support_graph_metadata_identical':True,'canonical_identity_equal':True,'K8_ledger':fees}
def clean_verified(folder,r):
 f=(folder/'decoded/decoded.npz').resolve();assert f.is_relative_to(OUT.resolve())
 if f.exists():h.write(folder/'DECODED_RETENTION.json',{'bytes':f.stat().st_size,'sha256':h.sha(f),'policy':'generated matrix removed only after exact verification; source and archive retained'});f.unlink()
def case(s,K=32,branch='main'):
 pins();base=OUT/branch/s['id']/f'VALUE_K{K:02d}'
 for attempt in [1,2]:
  f=base/f'attempt{attempt:02d}'
  if not (f/'RESULT.json').exists():
   try:C.real(s,K,f)
   except Exception:
    if not (f/'RESULT.json').exists():raise
  r=json.loads((f/'RESULT.json').read_text())
  if r['status']=='success':
   h.audit(f,s);paired=compare_old(s,r);h.write(f/'K8_COMPARISON.json',paired);clean_verified(f,r);return r,f
  resources=[json.loads(z.read_text()) for z in f.glob('*_resource.json')]
  if any(z.get('failure') for z in resources):raise RuntimeError('GLOBAL_RESOURCE_STOP '+str(f))
  if r['status'] in ['EXACT_MISMATCH','DECODE_FAILED'] or 'drift' in r.get('error',''):raise RuntimeError('GLOBAL_INTEGRITY_STOP '+str(f))
  log=(f/'encode.log').read_text(errors='replace').replace('\x00','') if (f/'encode.log').exists() else ''
  rc=json.loads((f/'encode_resource.json').read_text()).get('returncode') if (f/'encode_resource.json').exists() else None
  native=r['status']=='ENCODE_FAILED' and (rc in [3221225477,3221226505,-1073741819,-1073740791] or 'access violation' in log or ('Assertion failed' in log and 'llvm' in log) or ('numba' in log and 'ImportError' in log))
  h.write(f/'FAILURE.json',{'attempt':attempt,'status':r['status'],'returncode':rc,'native_retry_eligible':native,'error':r.get('error')})
  if not native or attempt==2:return r,f
 raise AssertionError('unreachable')
