"""Background handoff: preserve reviewed audit and completion status on D."""
from pathlib import Path
import json,hashlib,time,subprocess,sys,shutil,datetime
P=Path(__file__).resolve().parent;OUT=Path('D:/HEST1000BenchRun/COUNT-HEST-SHARED-K32-001');ROOT=P.parents[2]
audit=P/'audit_final.py';expected=hashlib.sha256(audit.read_bytes()).hexdigest();start=time.monotonic()
def write(p,v):
 tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(v,indent=2),encoding='utf-8');tmp.replace(p)
write(OUT/'FINALIZER_STARTED.json',{'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'reviewed_audit_sha256':expected,'deadline_seconds':90000,'policy':'wait for runner; prefer independent watcher output; fallback only after watcher45min deadline plusmargin'})
while time.monotonic()-start<90000:
 if (OUT/'RUN_ERROR.json').exists():
  write(OUT/'COMPLETION_STATUS.json',{'complete':False,'status':'needs_attention','reason':'runner failure preserved; no silent retry','error_path':str(OUT/'RUN_ERROR.json')});break
 if (OUT/'DONE.json').exists():
  if not (P/'FINAL_VERIFICATION.json').exists() and time.monotonic()-start>3000:
   assert hashlib.sha256(audit.read_bytes()).hexdigest()==expected
   with (OUT/'FINAL_AUDIT.log').open('w',encoding='utf-8') as log:
    subprocess.run([sys.executable,'-X','utf8',str(audit)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
  if (P/'FINAL_VERIFICATION.json').exists():
   r=json.loads((P/'FINAL_VERIFICATION.json').read_text());complete=r.get('all_accepted_evidence_pass') and r.get('full1000_complete') and len(r.get('reproductions',[]))==2
   shutil.copyfile(P/'FINAL_VERIFICATION.json',OUT/'FINAL_VERIFICATION.json')
   write(OUT/'COMPLETION_STATUS.json',{'complete':bool(complete),'status':'accepted' if complete else 'needs_attention','accepted':r['accepted'],'K8_bytes':r['K8_bytes'],'K32_bytes':r['K32_bytes'],'saved_bytes':r['saved_bytes'],'audit_path':str(OUT/'FINAL_VERIFICATION.json'),'auditor_new_decode':False,'runner_independent_decode_each_sample':True})
   task=ROOT/'baseline/.ai/tasks/COUNT-HEST-SHARED-K32-001.json';t=json.loads(task.read_text());t.update(state='accepted' if complete else 'needs_attention',accepted_samples=r['accepted'],final_audit=str(OUT/'FINAL_VERIFICATION.json'));write(task,t)
   break
 time.sleep(30)
else:write(OUT/'COMPLETION_STATUS.json',{'complete':False,'status':'monitor_timeout','reason':'24h runner limit plus finalization margin expired; inspect live process before resuming'})
