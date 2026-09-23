"""Rerun each of the frozen1000 slices at valueK32, never select per-sliceK."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import json,threading,time,subprocess,sys,shutil,traceback,os
import common as u
P=u.P;OUT=u.OUT;START=time.monotonic();lock=threading.Lock();stop=threading.Event()
def main():
 u.pins();release=json.loads((P/'REVIEW_RELEASE.json').read_text());assert release['approved']
 assert json.loads((OUT/'PREFLIGHT.json').read_text())['all_pass']
 # Exclusive lock prevents simultaneous resumptions; a crash leaves evidence.
 fd=os.open(OUT/'RUNNING.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd)
 try:
  samples=u.samples();index=json.loads((OUT/'INDEX.json').read_text()) if (OUT/'INDEX.json').exists() else {s['id']:{'status':'PENDING'} for s in samples}
  for s in samples:
   if index[s['id']]['status']=='success':u.h.audit(Path(index[s['id']]['record_path']).parent,s)
  u.h.write(OUT/'INDEX.json',index);consecutive=0
  def run_one(s):
   nonlocal consecutive
   if stop.is_set() or index[s['id']]['status']=='success':return
   try:
    r,f=u.case(s)
    with lock:
     index[s['id']]={'status':r['status'],'record_path':str(f/'RESULT.json'),'error':r.get('error')}
     u.h.write(OUT/'INDEX.json',index)
     consecutive=0 if r['status']=='success' else consecutive+1
     if consecutive>=4:stop.set()
     success=sum(x['status']=='success' for x in index.values());failed=sum(x['status'] not in ['success','PENDING'] for x in index.values())
     u.h.write(OUT/'PROGRESS.json',{'status':'running','planned':1000,'success':success,'failed':failed,'pending':1000-success-failed,'last_sample':s['id'],'K':32,'wall_seconds_this_invocation':time.monotonic()-START})
     print(s['id'],r['status'],r.get('total_archive_bytes'),success,flush=True)
   except Exception:
    stop.set()
    with lock:index[s['id']]={'status':'STOPPED','error':traceback.format_exc()};u.h.write(OUT/'INDEX.json',index)
    raise
  small=[s for s in samples if int(s['n_nonzero'])<=20_000_000 and int(s['n_counts'])<=300_000_000]
  large=[s for s in samples if s not in small]
  with ThreadPoolExecutor(max_workers=4) as pool:
   for f in as_completed([pool.submit(run_one,s) for s in small]):f.result()
  if stop.is_set():raise RuntimeError('stopped after failure gate')
  for s in large:
   run_one(s)
   if stop.is_set():raise RuntimeError('large sample stop gate')
  repeats=[]
  if all(x['status']=='success' for x in index.values()):
   for sid in ['NCBI180','NCBI792']:
    s=next(s for s in samples if s['id']==sid);r,f=u.case(s,32,'reproduction');assert r['status']=='success'
    old=json.loads(Path(index[sid]['record_path']).read_text());assert r['archive_sha256']==old['archive_sha256']
    repeats.append({'sample_id':sid,'record_path':str(f/'RESULT.json'),'archive_byte_identical':True})
  u.h.write(OUT/'REPRODUCTION.json',repeats)
  u.h.write(OUT/'EXECUTION_TIME.json',{'wall_seconds_this_invocation':time.monotonic()-START,'all1000fresh':True,'small_concurrency':4,'large_concurrency':1,'preflight_excluded':True})
  subprocess.run([sys.executable,'-X','utf8',str(P/'summarize.py')],check=True)
  success=sum(x['status']=='success' for x in index.values());u.h.write(OUT/'DONE.json',{'complete':success==1000,'accepted':success,'planned':1000,'reproductions':len(repeats)})
 finally:(OUT/'RUNNING.lock').unlink()
if __name__=='__main__':
 try:main()
 except Exception:u.h.write(OUT/'RUN_ERROR.json',{'traceback':traceback.format_exc()});raise
