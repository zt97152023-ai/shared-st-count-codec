"""Fresh small and large real regressions, before full1000 execution."""
from pathlib import Path
import json,shutil
import common as u
P=u.P;OUT=u.OUT;u.pins()
OUT.mkdir(parents=True,exist_ok=False)
for n in ['PROTOCOL.json','DATA_SPLIT.csv','PINS.json','RUN_PINS.json']:shutil.copyfile(P/n,OUT/n)
byid={s['id']:s for s in u.samples()};records=[]
old50=json.loads((P.parent/'VALUE_BEST_OF_9_50_005/INDEX.json').read_text())
for sid,K in [('NCBI180',8),('NCBI180',32),('NCBI792',8),('NCBI792',32),('NCBI793',32)]:
 r,f=u.case(byid[sid],K,'preflight');assert r['status']=='success'
 if K==8:assert r['archive_sha256']==byid[sid]['archive_sha256']
 if sid=='NCBI180' and K==32:assert r['archive_sha256']==json.loads(Path(old50[sid]['32']['record_path']).read_text())['archive_sha256']
 records.append({'sample_id':sid,'K':K,'record_path':str(f/'RESULT.json'),'exact':True,'historical_byte_identical':K==8 or sid=='NCBI180'})
 print('PREFLIGHT',sid,K,r['total_archive_bytes'],flush=True)
u.h.write(OUT/'PREFLIGHT.json',{'all_pass':True,'records':records});u.h.write(P/'PREFLIGHT_POINTER.json',{'path':str(OUT/'PREFLIGHT.json')})
