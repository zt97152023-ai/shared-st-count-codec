"""Bounded fixed-candidate completion; never replace samples based on results."""
from pathlib import Path
import csv,json,hashlib,random,sys,subprocess,traceback
import run_core as core
P=Path(core.PRO['output_root']);P50=core.HERE.parent/'VALUE_GROUP_K_50_002'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):
 p=Path(p);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(x,indent=2),encoding='utf-8');tmp.replace(p)
def audit(folder,s):
 r=json.loads((folder/'RESULT.json').read_text());assert r['status']=='success' and r['exact']['checks']['all']
 assert r['sample_id']==s['id']
 expected_K=int(next(a.name for a in [folder,*folder.parents] if a.name.startswith('VALUE_K')).replace('VALUE_K',''))
 assert r['requested_K']==expected_K
 assert (r['n_obs'],r['n_vars'],r['n_nonzero'])==tuple(int(s[n]) for n in ['n_spots','n_genes','n_nonzero'])
 assert r['source_sha256']==s['source_sha256'];assert sha(folder/'archive.cnt')==r['archive_sha256']
 fees,members=core.ledger(folder/'archive.cnt');assert fees==r['ledger'] and members==r['members'];assert sum(fees.values())==r['total_archive_bytes']
 dec=json.loads((folder/'decode.json').read_text());assert dec['archive_only'] and dec['value_cdf_sha256']==r['value_cdf_sha256'] and dec['canonical_sha256']==r['exact']['canonical_sha256']
 return r
def runone(s,K,branch='main'):
 for attempt in [1,2]:
  f=P/branch/s['id']/f'VALUE_K{K:02d}'/f'attempt{attempt:02d}'
  if (f/'RESULT.json').exists():
   r=json.loads((f/'RESULT.json').read_text())
  else:
   try:core.real(s,K,f)
   except Exception:
    if not (f/'RESULT.json').exists():raise
   r=json.loads((f/'RESULT.json').read_text())
  if r['status']=='success':
   audit(f,s)
   npz=(f/'decoded/decoded.npz').resolve();assert npz.is_relative_to(P.resolve())
   if npz.exists():write(f/'DECODED_RETENTION.json',{'bytes':npz.stat().st_size,'sha256':sha(npz),'policy':'remove generated matrix after exact verification; final archive retained'});npz.unlink()
   return str(f/'RESULT.json')
  log=(f/'encode.log').read_text(errors='replace').replace('\x00','') if (f/'encode.log').exists() else ''
  if any(json.loads(receipt.read_text()).get('failure') for receipt in f.glob('*_resource.json')):
   write(f/'FAILURE.json',{'status':r['status'],'error':r.get('error'),'retry_eligible':False,'attempt':attempt,'reason':'resource ceiling'})
   raise RuntimeError('resource ceiling stop: '+str(f))
  retry=r['status']=='ENCODE_FAILED' and ('access violation' in log or ('numba' in log and 'ImportError' in log) or ('Assertion failed' in log and 'llvm' in log))
  write(f/'FAILURE.json',{'status':r['status'],'error':r.get('error'),'retry_eligible':retry,'attempt':attempt})
  if not retry or attempt==2:raise RuntimeError('failed case retained: '+str(f))
 raise AssertionError('unreachable')
def main():
 assert json.loads((P/'REVIEW_RELEASE.json').read_text())['approved']
 for name,h in json.loads((P/'RUN_PINS.json').read_text()).items():assert sha(P/name)==h,name
 for name,h in json.loads((P/'PINS.json').read_text()).items():assert sha(core.ROOT/name)==h,name
 samples=list(csv.DictReader((P/'DATA_SPLIT.csv').open(encoding='utf-8-sig')));old=json.loads((P50/'INDEX.json').read_text())
 index=json.loads((P/'INDEX.json').read_text()) if (P/'INDEX.json').exists() else {s['id']:{str(k):{'status':'PENDING'} for k in core.PRO['K']} for s in samples}
 for s in samples:
  for K in [8,16]:
   path=Path(old[s['id']][str(K)]['record_path']);audit(path.parent,s);index[s['id']][str(K)]={'status':'success','record_path':str(path),'reused':True}
 write(P/'INDEX.json',index)
 for i,s in enumerate(samples):
  base=audit(Path(index[s['id']]['8']['record_path']).parent,s)
  order=list(core.PRO['fresh_K']);random.Random(20260920+i).shuffle(order)
  for K in order:
   path=runone(s,K);r=audit(Path(path).parent,s)
   for name in ['support.rans','base_probability.bz2','shared_odds.u32','graph.bz2','metadata.bz2']:assert r['members'][name]==base['members'][name]
   assert r['exact']['canonical_sha256']==base['exact']['canonical_sha256']
   index[s['id']][str(K)]={'status':'success','record_path':path,'reused':False};write(P/'INDEX.json',index)
   n=sum(v['status']=='success' and not v.get('reused',False) for a in index.values() for v in a.values());write(P/'PROGRESS.json',{'fresh_completed':n,'fresh_planned':70,'sample':s['id'],'K':K});print(s['id'],K,r['total_archive_bytes'],flush=True)
 repeat=[]
 for K in [4,8]:
  path=runone(samples[0],K,'reproduction');r=audit(Path(path).parent,samples[0]);base=json.loads(Path(index[samples[0]['id']][str(K)]['record_path']).read_text());assert r['archive_sha256']==base['archive_sha256']
  repeat.append({'K':K,'record_path':path,'archive_byte_identical':True})
 write(P/'REPRODUCTION.json',repeat)
 subprocess.run([sys.executable,'-X','utf8',str(P/'analyze.py')],check=True);write(P/'DONE.json',{'fresh':70,'reused':20,'reproduction':2,'all_exact':True})
if __name__=='__main__':
 try:main()
 except Exception:write(P/'RUN_ERROR.json',{'traceback':traceback.format_exc()});raise
