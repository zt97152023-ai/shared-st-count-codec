"""Sequential, immutable missing-pair runner. Builder code; independent release required."""
from pathlib import Path
import argparse,collections,csv,ctypes,hashlib,json,os,shutil,subprocess,sys,time,zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
from baseline.hest1000 import pilot
METHODS=['BP_gene_none','BP_spot_mean','IVCSC','IVCSC_bz2','CSR_ZSTD19','CSC_ZSTD19','H5AD_GZIP4']
DEFAULT_OUT=Path('D:/HEST1000BenchRun/COUNT-HEST-BASELINES-1000-005')
K32=Path('D:/HEST1000BenchRun/COUNT-HEST-SHARED-K32-001/ALL_SAMPLES.csv')
PAYLOAD=Path('D:/HEST1000BenchRun/HEST_K32_Publication_20260921/06_Provenance/external_payload.json')
EXTRA_MODULE='baseline.evidence.COUNT-HEST-BASELINES-1000-005.extra_worker'
PY=pilot.SHARED_PY
ANACONDA=Path('C:/Users/zhang/anaconda3/python.exe')
PIN_STATS={}
class StopRun(RuntimeError):pass
class StageFailure(RuntimeError):
 def __init__(self,receipt):self.receipt=receipt;super().__init__(str(receipt))
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return pilot.sha(Path(p))
def atomic(p,obj):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp')
 tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf8');tmp.replace(p)
def key(sid,method):return sid+'::'+method
def safe_remove(path,scope):
 path=Path(path).resolve();scope=Path(scope).resolve()
 if path==scope or not path.is_relative_to(scope):raise StopRun('cleanup outside attempt')
 if path.exists():shutil.rmtree(path)
def byte_count(root):
 total=0
 for base,dirs,files in os.walk(root):
  for name in files:
   try:total+=(Path(base)/name).stat().st_size
   except FileNotFoundError:pass
 return total
def budget(out,start,now=None):
 now=time.time() if now is None else now
 if now-start>=72*3600:raise StopRun('72 hour wall budget')
 if shutil.disk_usage(out).free<20*2**30:raise StopRun('20 GiB free reserve')
 if byte_count(out)>100*2**30:raise StopRun('100 GiB new output cap')
def pin_files(extra=()):
 files=set(map(Path,pilot.source_pins()))
 files.update([Path(__file__),ROOT/'baseline/hest1000/main.py',ROOT/'baseline/hest1000/baselines_runner.py',ROOT/'baseline/.ai/tasks/COUNT-HEST-BASELINES-1000-005.json',PY,ANACONDA])
 files.update(map(Path,extra))
 return {str(p.resolve()):sha(p) for p in sorted(files)}
def check_pins(pins):
 for p,digest in pins.items():
  if sha(p)!=digest:raise StopRun('code/config drift: '+p)
  stat=Path(p).stat();PIN_STATS[p]=(stat.st_size,stat.st_mtime_ns)
def cheap_pin_guard(pins):
 for p,digest in pins.items():
  stat=Path(p).stat()
  if PIN_STATS.get(p)!=(stat.st_size,stat.st_mtime_ns):
   actual=sha(p)
   raise StopRun('pinned file stat changed: '+p+'; hash_matches='+str(actual==digest))
def reuse_valid(r,s):
 """Trust the prior independent physical-hash audit, then check unchanged receipt/lengths."""
 if not r.get('chosen_for_comparison') or not r.get('eligible_full_archive_pair'):return False
 if r.get('sample_id')!=s['sample_id'] or r.get('K32_archive_bytes')!=int(s['total_archive_bytes']):return False
 old=read(r['record_path'])
 if sha(r['record_path'])!=r['result_sha256'] or old.get('status')!='success':return False
 md=read(s['record_path'])['exact']['metadata_sha256']
 if r.get('metadata_sha256')!=md:return False
 if not r.get('physical_files') or any(not p.get('hash_matches') or not Path(p['path']).is_file() or Path(p['path']).stat().st_size!=p['bytes'] for p in r['physical_files']):return False
 if sum(p['bytes'] for p in r['physical_files'])!=r['total_file_bytes']:return False
 # Older IVCSC100 records use direct canonical+metadata hash matching instead of raw SHA.
 if r.get('source_sha256') is not None:
  return r['source_sha256']==s['source_sha256'] and r.get('source_sha256_after')==s['source_sha256']
 return bool(r.get('source_identity_basis')) and old.get('canonical_sha256')==read(s['record_path'])['exact']['canonical_sha256']
def plan(args):
 samples=list(csv.DictReader(Path(args.samples).open(encoding='utf-8-sig')))
 if len(samples)!=1000 or len({s['sample_id'] for s in samples})!=1000:raise StopRun('frozen 1000 unique samples required')
 if any(s['status']!='success' for s in samples):raise StopRun('K32 reference not accepted')
 adapters=read(args.adapters) if args.adapters else {m:{'module':EXTRA_MODULE,'fee_kind':'zip','archive_name':'archive.bin','pin_files':[str(HERE/'extra_worker.py'),str(ROOT/'baseline/hest1000/general_baselines.py')]} for m in ['CSR_BZIP2_9','Pcodec']}
 methods=METHODS+sorted(adapters)
 if len(set(methods))!=len(methods):raise StopRun('adapter overwrites existing method')
 payload=read(args.payload);by={s['sample_id']:s for s in samples};reuse={};rejected=[]
 for r in payload['rows']:
  if not r.get('chosen_for_comparison') or r.get('method') not in methods:continue
  try:ok=r['sample_id'] in by and reuse_valid(r,by[r['sample_id']])
  except Exception:ok=False
  if ok:reuse[key(r['sample_id'],r['method'])]=r
  else:rejected.append({'sample_id':r.get('sample_id'),'method':r.get('method'),'reason':'prior selected evidence changed or insufficient'})
 extra=[args.samples,args.payload]
 if args.adapters:extra.append(args.adapters)
 for cfg in adapters.values():extra.extend(cfg.get('pin_files',[]))
 obj={'schema':'baseline-completion-plan-v1','output_root':str(Path(args.output).resolve()),'samples':sorted(samples,key=lambda s:(int(s['n_nonzero']),s['sample_id'])),'methods':methods,'adapters':adapters,'reuse':reuse,'reuse_rejected':rejected,
 'reuse_policy':'Prior independently hashed physical files, frozen payload+RESULT SHA, current physical lengths and exact K32 metadata/source-or-semantic identity; no repeated full archive rehash. Historical archives never modified.',
 'code_pins':pin_files(extra),'samples_sha256':sha(args.samples),'payload_sha256':sha(args.payload),'planned_pairs':len(samples)*len(methods),'reused_pairs':len(reuse),'missing_pairs':len(samples)*len(methods)-len(reuse),'retry_rule':'at most2 total attempts for ordinary failed prepare/encode/decode; no resource/integrity retry','resources':{'concurrent':1,'stage_seconds':1800,'rss_bytes':16*2**30,'reserve_bytes':20*2**30,'output_cap_bytes':100*2**30,'wall_seconds':72*3600}}
 atomic(args.plan,obj);print(json.dumps({n:obj[n] for n in ['planned_pairs','reused_pairs','missing_pairs']}))
def stage(cmd,folder,name,out,start):
 import psutil
 budget(out,start);prefix=folder/name;log=prefix.with_suffix('.log');receipt=prefix.with_suffix('.resource.json')
 if log.exists() or receipt.exists():raise StopRun('immutable stage path exists')
 progress=read(out/'PROGRESS.json') if (out/'PROGRESS.json').exists() else {}
 progress.update(pid=os.getpid(),current_stage=name,current_attempt=str(folder),stage_started_epoch=time.time());atomic(out/'PROGRESS.json',progress)
 cache=folder/('cache_'+name);cache.mkdir();temp=folder/'temp';temp.mkdir(exist_ok=True)
 env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',PYTHONFAULTHANDLER='1',TEMP=str(temp),TMP=str(temp),NUMBA_CACHE_DIR=str(cache))
 for n in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMBA_NUM_THREADS']:env[n]='1'
 if os.name=='nt':ctypes.windll.kernel32.SetErrorMode(3)
 owned={};failure=None;peak=0;cleanup=[];t=time.monotonic();last_disk=0;proc=None
 try:
  with log.open('xb') as f:
   proc=subprocess.Popen(list(map(str,cmd)),cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT)
   parent=psutil.Process(proc.pid);owned[(parent.pid,parent.create_time())]=parent
   while proc.poll() is None:
    for parent in list(owned.values()):
     try:
      for child in parent.children(recursive=True):owned[(child.pid,child.create_time())]=child
     except psutil.NoSuchProcess:pass
    rss=0
    for child in owned.values():
     try:rss+=child.memory_info().rss
     except psutil.NoSuchProcess:pass
    peak=max(peak,rss)
    if rss>16*2**30:failure='rss';break
    if time.monotonic()-t>1800:failure='timeout';break
    if time.monotonic()-last_disk>2:budget(out,start);last_disk=time.monotonic()
    time.sleep(.15)
 except StopRun as e:failure='budget:'+str(e)
 except BaseException as e:failure='monitor_exception:'+repr(e)
 finally:
  # Only process instances whose creation identities were observed belong to this stage.
  for child in reversed(list(owned.values())):
   try:
    if child.is_running():
     if proc is not None and proc.poll()==0 and child.pid!=proc.pid:failure=failure or 'live_descendant_after_root_exit'
     child.kill();child.wait(timeout=5)
   except psutil.NoSuchProcess:pass
   except psutil.Error as e:cleanup.append(repr(e))
  if proc is not None:
   try:proc.wait(timeout=5)
   except subprocess.TimeoutExpired:cleanup.append('root wait timeout')
  r={'command':list(map(str,cmd)),'seconds':time.monotonic()-t,'returncode':None if proc is None else proc.returncode,'failure':failure,'sampled_tree_peak_rss_bytes':peak,'cleanup_errors':cleanup,'observed_identities':[{'pid':p,'created':c} for p,c in owned]}
  atomic(receipt,r)
 if failure or cleanup:raise StopRun('resource/monitor stop: '+str(receipt))
 if r['returncode']!=0:raise StageFailure(r)
 budget(out,start)
 return r
def worker_args(plan,method,phase,source,target,blocked=()):
 cfg=plan['adapters'].get(method,{})
 py=cfg.get('python',str(ANACONDA if method=='H5AD_GZIP4' else PY))
 module=cfg.get('module','baseline.hest1000.pilot')
 return [py,'-X','utf8','-B','-m',module,'worker',phase,method,str(source),str(target)]+(['--blocked',*map(str,blocked)] if blocked else [])
def fees(plan,method,folder):
 cfg=plan['adapters'].get(method)
 if not cfg:return pilot.fee_report(folder,method)
 if cfg['fee_kind']=='directory':
  files=[p for p in folder.rglob('*') if p.is_file()];return {'total_file_bytes':sum(p.stat().st_size for p in files),'archive_hashes':{p.relative_to(folder).as_posix():sha(p) for p in files},'components':None}
 archive=folder/cfg.get('archive_name','archive.bin')
 with zipfile.ZipFile(archive) as z:components={i.filename:i.file_size for i in z.infolist()}
 return {'total_file_bytes':archive.stat().st_size,'archive_hashes':{archive.name:sha(archive)},'components':components,'framing_bytes':archive.stat().st_size-sum(components.values())}
def native_retry(folder,status):
 if status!='encode_failed':return False
 try:
  r=read(folder/'encode.resource.json');log=(folder/'encode.log').read_text(errors='replace').replace('\x00','').lower()
  return not r.get('failure') and not r.get('cleanup_errors') and (r.get('returncode') in [3221225477,3221226505,-1073741819,-1073740791] or 'access violation' in log or ('llvm' in log and 'assertion failed' in log) or ('numba' in log and 'importerror' in log))
 except Exception:return False
def accepted(path,s):
 r=read(path)
 if r.get('status')!='success' or not r.get('exact',{}).get('checks',{}).get('all'):raise StopRun('false accepted status')
 if r.get('source_sha256')!=s['source_sha256'] or r.get('source_sha256_after')!=s['source_sha256']:raise StopRun('accepted source drift')
 ref=read(s['record_path'])
 if r['exact']['decoded_hashes']['metadata.json']!=ref['exact']['metadata_sha256']:raise StopRun('accepted metadata drift')
 if r['canonical_sha256']!=ref['exact']['canonical_sha256']:raise StopRun('accepted canonical drift')
 for name,h in r['archive_hashes'].items():
  if sha(Path(path).parent/'archive'/name)!=h:raise StopRun('accepted archive drift')
 for phase in ['prepare','encode','decode','check']:
  res=read(Path(path).parent/(phase+'.resource.json'))
  if res['returncode']!=0 or res.get('failure') or res.get('cleanup_errors'):raise StopRun('accepted failed process')
 return r
def run_pair(plan,s,method,branch,start):
 cheap_pin_guard(plan['code_pins'])
 out=Path(plan['output_root']);base=out/branch/s['sample_id']/method
 for attempt in [1,2]:
  folder=base/f'attempt{attempt:02d}';result=folder/'RESULT.json'
  if folder.exists():
   if not result.exists():raise StopRun('partial immutable attempt; inspect: '+str(folder))
   old=read(result)
   if old['status']=='success':return accepted(result,s),result
   if old.get('global_stop'):raise StopRun('previous resource/integrity failure retained')
   if attempt==1 and old['status'] in ['prepare_failed','encode_failed','decode_failed']:continue
   return old,result
  folder.mkdir(parents=True);scratch=folder/'scratch';source=Path(s['source_path']);phase='prepare'
  row={'sample_id':s['sample_id'],'method':method,'attempt':attempt,'status':'running','total_file_bytes':None,'source_sha256':s['source_sha256']};atomic(result,row)
  try:
   if sha(source)!=s['source_sha256']:raise StopRun('source hash drift before')
   stage([str(PY),'-X','utf8','-B','-m','baseline.hest1000.pilot','worker','prepare','Shared',str(source),str(scratch)],folder,'prepare',out,start)
   canonical=read(scratch/'canonical.json');ref=read(s['record_path'])
   if canonical['csr_sha256']!=ref['exact']['canonical_sha256'] or sha(scratch/'metadata.json')!=ref['exact']['metadata_sha256']:raise StopRun('canonical/metadata preparation identity')
   row.update({k:canonical[k] for k in ['n_spots','n_genes','n_counts','n_nonzero','canonical_dtype','source_storage_dtype']});row['canonical_sha256']=canonical['csr_sha256']
   phase='encode';stage(worker_args(plan,method,'encode',scratch,folder/'archive'),folder,phase,out,start)
   phase='decode';stage(worker_args(plan,method,'decode',folder/'archive',folder/'decoded',[source.parent,scratch]),folder,phase,out,start)
   phase='check';stage([str(PY),'-X','utf8','-B','-m','baseline.hest1000.main','compare',str(scratch),str(folder/'decoded'),str(folder/'EXACT.json')],folder,phase,out,start)
   exact=read(folder/'EXACT.json')
   if not all(exact.get('checks',{}).get(k) is True for k in ['dtype','shape','csr','canonical','indptr','indices','counts','metadata','all']):raise StopRun('exact check failed')
   if exact['decoded_hashes']['metadata.json']!=ref['exact']['metadata_sha256']:raise StopRun('decoded metadata mismatch')
   row.update(fees(plan,method,folder/'archive'),exact=exact)
   row['source_sha256_after']=sha(source)
   if row['source_sha256_after']!=s['source_sha256']:raise StopRun('source hash drift after')
   cheap_pin_guard(plan['code_pins'])
   row.update(status='success',full_archive_bits_per_count=8*row['total_file_bytes']/row['n_counts'],full_archive_bits_per_nonzero=8*row['total_file_bytes']/row['n_nonzero'] if row['n_nonzero'] else None)
   # Receipt precedes deletion and records which independently verified files are removed.
   atomic(folder/'DECODED_RETENTION.json',{'decoded_hashes':exact['decoded_hashes'],'policy':'remove only decoded/scratch/temp/cache after exact verification; archive and logs retained'})
   for name in ['decoded','scratch','temp',*[p.name for p in folder.glob('cache_*')]]:safe_remove(folder/name,folder)
  except StopRun as e:row.update(status='stopped',global_stop=True,error=repr(e))
  except StageFailure as e:row.update(status=phase+'_failed',error=repr(e),global_stop=phase=='check')
  except Exception as e:row.update(status=phase+'_failed',error=repr(e))
  finally:atomic(result,row)
  if row.get('global_stop'):raise StopRun(row['error'])
  if row['status']=='success':return row,result
  if phase=='check':raise StopRun('independent exact checker failed; preserved '+str(result))
  if attempt==1 and row['status'] in ['prepare_failed','encode_failed','decode_failed']:continue
  return row,result
def execute(args,preflight=False):
 plan=read(args.plan);check_pins(plan['code_pins']);out=Path(plan['output_root']);out.mkdir(parents=True,exist_ok=True)
 if not preflight:
  release=read(args.release)
  if release.get('approved') is not True or release.get('plan_sha256')!=sha(args.plan):raise StopRun('review release mismatch')
  pf=read(out/'PREFLIGHT.json')
  if pf.get('all_pass') is not True or pf.get('plan_sha256')!=sha(args.plan):raise StopRun('preflight mismatch')
 lock=out/'RUNNING.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,json.dumps({'pid':os.getpid(),'started':time.time()}).encode());os.close(fd)
 try:
  statefile=out/('PREFLIGHT_STATE.json' if preflight else 'STATE.json')
  state=read(statefile) if statefile.exists() else {'started_epoch':time.time(),'plan_sha256':sha(args.plan),'pairs':{k:{'status':'success','reused':True,'record_path':r['record_path'],'total_file_bytes':r['total_file_bytes']} for k,r in plan['reuse'].items()}}
  if state['plan_sha256']!=sha(args.plan):raise StopRun('state plan changed')
  atomic(out/'PLAN.json',plan);atomic(statefile,state)
  samples=[next(s for s in plan['samples'] if s['sample_id']==args.sample)] if preflight else plan['samples']
  records=[]
  for s in samples:
   for method in plan['methods']:
    k=key(s['sample_id'],method)
    if not preflight and k in state['pairs'] and state['pairs'][k]['status']=='success':continue
    row,path=run_pair(plan,s,method,'preflight' if preflight else 'main',state['started_epoch']);records.append({'record_path':str(path),**row})
    state['pairs'][k]={'status':row['status'],'record_path':str(path),'reused':False,'total_file_bytes':row.get('total_file_bytes')};atomic(statefile,state)
    counts=collections.Counter(v['status'] for v in state['pairs'].values());atomic(out/'PROGRESS.json',{'pid':os.getpid(),'planned_pairs':plan['planned_pairs'],'status_counts':dict(counts),'recorded_pairs':len(state['pairs']),'pending_pairs':plan['planned_pairs']-len(state['pairs']),'last_sample':s['sample_id'],'last_method':method,'elapsed_seconds':time.time()-state['started_epoch']});print(s['sample_id'],method,row['status'],flush=True)
  check_pins(plan['code_pins'])
  if preflight:atomic(out/'PREFLIGHT.json',{'all_pass':len(records)==len(plan['methods']) and all(r['status']=='success' for r in records),'plan_sha256':sha(args.plan),'records':records})
  else:atomic(out/'DONE.json',{'all_pairs_accepted':len(state['pairs'])==plan['planned_pairs'] and all(v['status']=='success' for v in state['pairs'].values()),'planned_pairs':plan['planned_pairs'],'status_counts':dict(collections.Counter(v['status'] for v in state['pairs'].values()))})
 except BaseException as e:atomic(out/'STOPPED.json',{'error':repr(e),'time':time.time(),'plan_sha256':sha(args.plan)});raise
 finally:lock.unlink()
def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['plan','preflight','run','status']);p.add_argument('--plan',default=str(HERE/'runner_plan.json'));p.add_argument('--samples',default=str(K32));p.add_argument('--payload',default=str(PAYLOAD));p.add_argument('--output',default=str(DEFAULT_OUT));p.add_argument('--adapters');p.add_argument('--sample',default='INT13');p.add_argument('--release',default=str(HERE/'REVIEW_RELEASE.json'));args=p.parse_args()
 if args.action=='plan':plan(args)
 elif args.action=='status':
  out=Path(read(args.plan)['output_root']);print(json.dumps({n:read(out/n) if (out/n).exists() else None for n in ['PROGRESS.json','DONE.json','STOPPED.json']},indent=2))
 else:execute(args,args.action=='preflight')
if __name__=='__main__':main()
