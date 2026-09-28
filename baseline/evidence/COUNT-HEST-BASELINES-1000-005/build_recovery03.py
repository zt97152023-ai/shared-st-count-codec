import json, time
from pathlib import Path
HERE=Path(r"E:\count压缩\baseline\evidence\COUNT-HEST-BASELINES-1000-005")
BASE=json.loads((HERE/'runner_plan.json').read_text(encoding='utf-8'))
OLD1=Path(r"D:\HEST1000BenchRun\COUNT-HEST-BASELINES-1000-005")
OLD2=Path(r"D:\HEST1000BenchRun\COUNT-HEST-BASELINES-1000-005-RECOVERED-01")
NEW=Path(r"D:\HEST1000BenchRun\COUNT-HEST-BASELINES-1000-005-RECOVERED-03")
accepted=dict(BASE['reuse'])
for old in [OLD1,OLD2]:
 for rp in (old/'main').rglob('RESULT.json'):
  try:r=json.loads(rp.read_text(encoding='utf-8'))
  except Exception:continue
  if r.get('status')=='success' and r.get('exact',{}).get('checks',{}).get('all'):
   accepted[f"{r['sample_id']}::{r['method']}"]={'status':'success','reused':True,'record_path':str(rp),'total_file_bytes':r.get('total_file_bytes')}
plan=dict(BASE); plan['output_root']=str(NEW); plan['reuse']=accepted; plan['reused_pairs']=len(accepted); plan['missing_pairs']=9000-len(accepted); plan['recovery_note']='Built from frozen historical reuse plus verified per-pair results from original and recovered runs.'
NEW.mkdir(parents=True,exist_ok=True)
(HERE/'runner_plan_recovered03.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
state={'started_epoch':time.time(),'plan_sha256':'pending','pairs':{k:{'status':'success','record_path':v['record_path'],'reused':True,'total_file_bytes':v.get('total_file_bytes')} for k,v in accepted.items()}}
(NEW/'STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
(NEW/'PROGRESS.json').write_text(json.dumps({'pid':None,'planned_pairs':9000,'status_counts':{'success':len(accepted)},'recorded_pairs':len(accepted),'pending_pairs':9000-len(accepted),'recovery':'RECOVERED-03'},ensure_ascii=False,indent=2),encoding='utf-8')
print(len(accepted),9000-len(accepted),str(NEW))
