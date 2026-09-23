"""Freeze declared sources and implementation before smoke/main; exclusive outputs."""
import hashlib,json
from pathlib import Path
B=Path(__file__).resolve().parents[1];E=B/'evidence/COUNT-QPATCH-001'
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
vdir=B/'evidence/COUNT-VALUE-001';sdir=B/'evidence/COUNT-QSHARE-SCREEN-001'
vc=read(vdir/'config.json');sc=read(sdir/'config.json')
vrows={r['sample']:r for r in read(vdir/'main/results.json') if r['method']=='V2_spatial'}
srows={r['sample']:r for r in read(sdir/'main/results.json') if r['method']=='Qpatch12'}
sp={r['id']:r for r in sc['samples']};samples=[]
for original in vc['samples']:
    sid=original['id'];v=vrows[sid];s=sp[sid];screen=srows[sid]
    for run in ['main','reproduction']:
        assert sha(sdir/run/sid/'Qpatch12.bz2')==screen['blob_sha256']
    samples.append({**original,'v2':{'path':s['archive'],'sha256':s['archive_sha256'],'package_bytes':v['package_bytes']},
                    'profile':s['profile'],'profile_sha256':s['profile_sha256'],'screen':screen,
                    'old_value_nll_bits':v['value_nll_bits'],'original_stratum':s['original_stratum']})
assert len(samples)==100 and len({s['id'] for s in samples})==100
inputs=[vdir/'config.json',vdir/'main/results.json',vdir/'VERIFICATION.json',sdir/'config.json',sdir/'main/results.json',sdir/'VERIFICATION.json']
code=list((B/'qpatchcodec').glob('*.py'))+list((B/'qpatchcodec/frozen_runtime').glob('*.py'))
cfg={'task':read(B/'.ai/tasks/COUNT-QPATCH-001.json'),'methods':['Qpatch12'],'samples':samples,
     'code_sha256':{str(p):sha(p) for p in code},'input_sha256':{str(p):sha(p) for p in inputs}}
with (E/'config.json').open('x',encoding='utf8') as f:json.dump(cfg,f,ensure_ascii=False,indent=2)
with (E/'config.sha256').open('x',encoding='ascii') as f:f.write(sha(E/'config.json')+'\n')
print(sha(E/'config.json'))
