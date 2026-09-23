"""Serial guarded execution with immutable per-run evidence and archive-only decode."""
from pathlib import Path
import csv,json,os,subprocess,time,hashlib,zipfile,random,shutil,sys
import psutil
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
PY=ROOT/'baseline/evidence/COUNT-MATCHED-READY-001/venv/Scripts/python.exe'
PRO=json.loads((HERE/'PROTOCOL.json').read_text()); START=time.monotonic()
def write(p,v):Path(p).write_text(json.dumps(v,indent=2),encoding='utf-8')
def call(stage,source,out,k,folder,shuffle=None):
    env=os.environ.copy();env.update({x:'1' for x in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']});env['PYTHONUTF8']='1'
    env.pop('VALUE_GROUP_SHUFFLE_SEED',None)
    cmd=[str(PY),'-X','utf8',str(HERE/'worker.py'),stage,str(source),str(out),'--K',str(k),'--report',str(folder/(stage+'.json'))]
    if shuffle is not None:cmd.extend(['--shuffle',str(shuffle)])
    t=time.monotonic();peak=0
    with (folder/(stage+'.log')).open('w',encoding='utf-8') as log:
        p=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        failure=None
        while p.poll() is None:
            try:
                parent=psutil.Process(p.pid);rss=0
                for child in [parent,*parent.children(recursive=True)]:
                    try:rss+=child.memory_info().rss
                    except psutil.NoSuchProcess:pass
                peak=max(peak,rss)
            except psutil.NoSuchProcess:pass
            if time.monotonic()-t>PRO['resource_ceiling']['run_seconds'] or peak>PRO['resource_ceiling']['rss_bytes'] or time.monotonic()-START>PRO['resource_ceiling']['total_seconds'] or shutil.disk_usage(Path(PRO["output_root"])).free<PRO['resource_ceiling']['free_disk_min_bytes']:
                failure='resource ceiling'
                for child in psutil.Process(p.pid).children(recursive=True):
                    try:child.kill()
                    except psutil.NoSuchProcess:pass
                p.kill();p.wait();break
            time.sleep(.15)
    write(folder/(stage+'_resource.json'),{'command':cmd,'returncode':p.returncode,'elapsed_seconds':time.monotonic()-t,'sampled_peak_rss_bytes':peak,'failure':failure})
    if p.returncode:raise RuntimeError(stage+' failed: '+str(folder/(stage+'.log')))
    return json.loads((folder/(stage+'.json')).read_text())
def members(p):
    with zipfile.ZipFile(p) as z:return {n:z.read(n) for n in z.namelist()}
def ledger(p):
    b=members(p); cats={'support_stream':['support.rans'],'value_stream':['values.rans'],'support_model':['base_probability.bz2','shared_odds.u32'],
    'value_model_and_group_map':['value_q1.bz2','value_group.bz2','value_base_k.bz2','value_odds.u32','value_cond_k.bz2'],'graph':['graph.bz2'],'identity_coordinate_metadata':['metadata.bz2'],'manifest':['manifest.json']}
    sums={key:sum(len(b[n]) for n in names) for key,names in cats.items()};sums['container_overhead']=p.stat().st_size-sum(sums.values())
    assert sum(sums.values())==p.stat().st_size
    return sums,{n:{'bytes':len(v),'sha256':hashlib.sha256(v).hexdigest()} for n,v in b.items()}
def real(sample,K,folder,original=False,shuffle=None):
    folder.mkdir(parents=True,exist_ok=False);result={'sample_id':sample['id'],'requested_K':K,'arm':'ORIGINAL' if original else f'VALUE_K{K:02d}','status':'PENDING','n_obs':int(sample['n_spots']),'n_vars':int(sample['n_genes']),'n_nonzero':int(sample['n_nonzero']),'platform':sample['st_technology']}
    write(folder/'RESULT.json',result)
    stage='encode'
    try:
        source_sha=hashlib.sha256(Path(sample['source_path']).read_bytes()).hexdigest()
        assert source_sha==sample['source_sha256'],'source drift'
        stage='original' if original else 'encode';enc=call(stage,sample['source_path'],folder/'archive.cnt',K,folder,shuffle)
        stage='decode';dec=call(stage,folder/'archive.cnt',folder/'decoded',K,folder)
        stage='verify';ver=call(stage,sample['source_path'],folder/'decoded',K,folder)
        assert hashlib.sha256(Path(sample['source_path']).read_bytes()).hexdigest()==source_sha,'source drift after run'
        fee,mem=ledger(folder/'archive.cnt');result.update(status='success',source_sha256=source_sha,total_archive_bytes=(folder/'archive.cnt').stat().st_size,ledger=fee,members=mem,exact=ver,diagnostics=enc.get('group_diagnostics'),value_cdf_sha256=enc.get('value_cdf_sha256'),archive_sha256=hashlib.sha256((folder/'archive.cnt').read_bytes()).hexdigest())
        result['value_subsystem_bytes']=fee['value_stream']+fee['value_model_and_group_map'];result['value_stream_bits_per_nonzero']=8*fee['value_stream']/result['n_nonzero'] if result['n_nonzero'] else None
        result['count_stream_bits_per_nonzero']=8*(fee['support_stream']+fee['value_stream'])/result['n_nonzero'] if result['n_nonzero'] else None
        result['archive_bits_per_matrix_entry']=8*result['total_archive_bytes']/(result['n_obs']*result['n_vars'])
        result['shuffle_seed']=shuffle
    except Exception as e:result.update(status={'decode':'DECODE_FAILED','verify':'EXACT_MISMATCH'}.get(stage,'ENCODE_FAILED'),error=repr(e))
    write(folder/'RESULT.json',result)
    if result['status']!='success':raise RuntimeError(result['error'])
    return result
def main(mode):
    rows=list(csv.DictReader((HERE/'DATA_SPLIT.csv').open(encoding='utf-8-sig')))
    if mode in ['main','supplement']:
        assert json.loads((HERE/'REVIEW_RELEASE.json').read_text())['approved']
        for name,h in json.loads((HERE/'EXPERIMENT_PINS.json').read_text()).items():assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==h,name
    if mode=='regression':
        folder=HERE/'regression';folder.mkdir(exist_ok=False)
        a=real(rows[0],8,folder/'original',True);b=real(rows[0],8,folder/'parameterized')
        ma=members(folder/'original/archive.cnt');mb=members(folder/'parameterized/archive.cnt')
        checks={n:ma[n]==mb[n] for n in ma};assert all(checks.values())
        assert a['archive_sha256']==b['archive_sha256'] and a['value_cdf_sha256']==b['value_cdf_sha256']
        write(HERE/'BASELINE_REGRESSION.json',{'sample_id':rows[0]['id'],'full_archive_identical':True,'archive_sha256':a['archive_sha256'],'member_bytes_identical':checks,'value_cdf_identical':True,'canonical_sha_identical':a['exact']['canonical_sha256']==b['exact']['canonical_sha256'],'independent_decodes_exact':True,'bytes':a['total_archive_bytes']})
        print('REGRESSION PASSED',flush=True)
    elif mode=='synthetic':
        for K in PRO['K']:
            if K==8 and (HERE/'synthetic_K08.json').exists():continue
            f=HERE/f'synthetic_worker_K{K:02d}';f.mkdir(exist_ok=False)
            call('synthetic','unused',f/'cases',K,f)
            print('SYNTHETIC',K,flush=True)
    elif mode=='main':
        assert json.loads((HERE/'BASELINE_REGRESSION.json').read_text())['full_archive_identical']
        assert (HERE/'REVIEW_RELEASE.json').exists() and json.loads((HERE/'REVIEW_RELEASE.json').read_text())['approved']
        for name,h in json.loads((HERE/'EXPERIMENT_PINS.json').read_text()).items():assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==h,name
        output=HERE/'main_v2';output.mkdir(exist_ok=False)
        for i,s in enumerate(rows):
            order=[k for k in PRO['K'] if k!=8];random.Random(20260920+i).shuffle(order);order=[8]+order
            base=None
            for K in order:
                f=output/s['id']/f'VALUE_K{K:02d}';r=real(s,K,f)
                if K==8:base=r
                for n in ['support.rans','base_probability.bz2','shared_odds.u32','graph.bz2','metadata.bz2']:
                    assert r['members'][n]==base['members'][n],n
                write(HERE/'PROGRESS.json',{'sample':s['id'],'K':K,'completed':len(list(output.glob('*/*/RESULT.json'))),'planned':len(rows)*len(PRO['K'])})
                print(s['id'],K,r['total_archive_bytes'],flush=True)
    elif mode=='supplement':
        assert len(list((HERE/'main_v2').glob('*/*/RESULT.json')))==len(rows)*len(PRO['K'])
        assert all(json.loads(p.read_text())['status']=='success' for p in (HERE/'main_v2').glob('*/*/RESULT.json'))
        for i in range(2):
            order=list(PRO['K']);random.Random(30+i).shuffle(order)
            for K in order:
                r=real(rows[0],K,HERE/'timing_repeats'/f'repeat{i+2}'/f'VALUE_K{K:02d}')
                b=json.loads((HERE/'main_v2'/rows[0]['id']/f'VALUE_K{K:02d}'/'RESULT.json').read_text())
                assert b['archive_sha256']==r['archive_sha256']
        for s in rows:
            base=json.loads((HERE/'main_v2'/s['id']/'VALUE_K08/RESULT.json').read_text())
            for seed in PRO['random_group_seeds']:
                r=real(s,8,HERE/'random_groups'/s['id']/f'SEED{seed}',shuffle=seed)
                assert r['diagnostics']['gene_counts']==base['diagnostics']['gene_counts']
                for n in ['support.rans','base_probability.bz2','shared_odds.u32','graph.bz2','metadata.bz2']:assert r['members'][n]==base['members'][n]
                print('RANDOM',s['id'],seed,r['total_archive_bytes'],flush=True)
    else:raise ValueError(mode)
if __name__=='__main__':main(sys.argv[1])
