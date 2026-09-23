"""Freeze fixed-K32 full HEST rerun; results are written to the user-selected D drive."""
from pathlib import Path
import json,csv,hashlib,shutil
P=Path(__file__).resolve().parent;ROOT=P.parents[2];OLD=P.parent/'VALUE_K64_K128_50_006'
OUT=Path('D:/HEST1000BenchRun/COUNT-HEST-SHARED-K32-001')
def write(p,x):Path(p).write_text(json.dumps(x,indent=2),encoding='utf-8')
source=P.parent/'COUNT-HEST-SHARED-RESUME-001/HEST_SHARED_1000_SAMPLE_SUMMARY.csv'
shutil.copyfile(source,P/'DATA_SPLIT.csv')
samples=list(csv.DictReader((P/'DATA_SPLIT.csv').open(encoding='utf-8-sig')))
assert len(samples)==len({s['id'] for s in samples})==1000
assert all(s['exact_recovery']=='True' and s['source_sha256'] for s in samples)
pro={'id':P.name,'output_root':str(OUT),'question':'Fixed support8/value32 rerun on the existing1000 HEST slices, paired paid-byte comparison with historicalK8','origin':'K32 chosen on exposed50; full1000 is descriptive extension, not independent confirmatory validation','K':32,'support_buckets':8,'threshold_rule':'fixed-log-axis-v1 unchanged from006','samples':1000,'data_manifest_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'recovery':'canonical int64 integer counts, complete axes/order/identities,coordinates and contract metadata; not fullH5AD byte reconstruction','primary_endpoint':'sum full physical archive bytes K32 versus same-source historicalK8; keep all losing samples','secondary_endpoints':['paired wins/losses/ties and median','platform/species/organ breakdown','count stream and full archive bpc/bpnz separately','six-category physical ledger','source physicalH5AD/dense/explicitlyestimatedCSR references','encode/decode resource timing separately; no cross-session speedrank'],'execution':'four small samples concurrently, large nnz>20M or matrixentries>300M serial afterward; one native thread per subprocess; Windows SetErrorMode3','resource_ceiling':{'run_seconds':1800,'total_seconds':86400,'rss_bytes':16*2**30,'free_disk_min_bytes':40*2**30},'failure_rule':'preserve every attempt; one fresh-process retry for native encode accessviolation/LLVMassert/NumbaImportError only; othercase failures recorded and continue; integrity/resource stop; four consecutive failed samples stop; no fabricated missing bytes','retention':'delete only generated decoded.npz after exact validation+hash receipt; keep archive and all reports','capacity':'reuse hash-pinned hest_large_runtime capacity500M/nnz100M, no newprobability rules','reproduction':'separate K32 encode forNCBI180 andNCBI792, matchmain SHA','preflight':'newworker K8/32 NCBI180 byteidentical previous; K8NCBI792 matches historicallarge archive; K32NCBI792 fresh exact','forbidden':['overwrite historicalarchives','change sourceoraxisorder','pick per-sampleK','newtraining/image/adaptation','skipfailedsamples in1000coverage','claim universallyoptimalK32']}
write(P/'PROTOCOL.json',pro)
worker=(OLD/'worker.py').read_text().replace('baseline.matched_ready','baseline.hest_large_runtime')
(P/'worker.py').write_text(worker,encoding='utf-8')
pins=json.loads((OLD/'PINS.json').read_text())
for folder in ['hest_large_runtime','execution_ready']:
 for f in (ROOT/'baseline'/folder).glob('*.py'):pins[str(f.relative_to(ROOT))]=hashlib.sha256(f.read_bytes()).hexdigest()
write(P/'PINS.json',pins)
core=(OLD/'run_core.py').read_text().replace('shutil.disk_usage(HERE).free','shutil.disk_usage(Path(PRO["output_root"])).free')
(P/'run_core.py').write_text(core,encoding='utf-8')
helper=(OLD/'helpers.py').read_text().replace("P=core.HERE;P50=P.parent/'VALUE_GROUP_K_50_002'", "P=Path(core.PRO['output_root']);P50=core.HERE.parent/'VALUE_GROUP_K_50_002'")
(P/'helpers.py').write_text(helper,encoding='utf-8')
task={'objective':pro['question'],'risk':'high','project_type':'research','state':'specified','inputs':['DATA_SPLIT.csv','historical1000K8 archives','frozen006K32definition'],'allowed_changes':[str(P),str(OUT)],'forbidden_changes':pro['forbidden'],'acceptance_criteria':['independent reviewrelease','capacityregression preflight','1000fresh archives with independentdecode exact or explicitunresolvedfailurecoverage','K8same-sourcephysicalcomparison','separate reproduction smallandlarge','independent final audit'],'required_test_evidence':pro['preflight'],'expected_outputs':['Ddrive mainarchives','sampleCSV','platform/species/organ summaries','RESULT.md','FINAL_VERIFICATION.json']}
write(ROOT/'baseline/.ai/tasks'/f'{P.name}.json',task)
print('Frozen1000; all output files targeted to',OUT)
