"""Full coverage and paired physical accounting; missing values stay missing."""
from pathlib import Path
import json,csv
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import common as u
OUT=u.OUT;index=json.loads((OUT/'INDEX.json').read_text());rows=[];ledgers=[]
for s in u.samples():
 item=index[s['id']];row={'sample_id':s['id'],'platform':s['st_technology'],'species':s['species'],'organ':s['organ'],'status':item['status'],'K':32,'source_path':s['source_path'],'source_sha256':s['source_sha256'],'record_path':item.get('record_path'),'error':item.get('error'),'n_spots':int(s['n_spots']),'n_genes':int(s['n_genes']),'n_counts':int(s['n_counts']),'n_nonzero':int(s['n_nonzero']),'K8_archive_bytes':int(s['archive_bytes'])}
 if item['status']=='success':
  f=Path(item['record_path']).parent;r=u.h.audit(f,s);u.compare_old(s,r);fee=r['ledger'];total=r['total_archive_bytes'];stream=fee['support_stream']+fee['value_stream'];csr=r['exact']['decoded_canonical_csr_arrays']
  row.update(total_archive_bytes=total,count_stream_bytes=stream,archive_path=str(f/'archive.cnt'),archive_sha256=r['archive_sha256'],exact_count_identity_metadata=True,independent_decode=True,effective_value_groups=r['diagnostics']['effective_K'],saved_vs_K8_bytes=int(s['archive_bytes'])-total,saved_vs_K8_percent=100*(int(s['archive_bytes'])-total)/int(s['archive_bytes']),count_stream_bits_per_count=8*stream/int(s['n_counts']),count_stream_bits_per_nonzero=8*stream/int(s['n_nonzero']) if int(s['n_nonzero']) else None,full_archive_bits_per_count=8*total/int(s['n_counts']),full_archive_bits_per_nonzero=8*total/int(s['n_nonzero']) if int(s['n_nonzero']) else None,source_h5ad_bytes=Path(s['source_path']).stat().st_size,dense_int64_bytes=8*int(s['n_counts']),canonical_csr_bytes=sum(x['nbytes'] for x in csr.values()),canonical_csr_arrays=json.dumps(csr),encode_attempts=len(list(f.parent.glob('attempt*/encode_resource.json'))),encode_seconds_all_attempts=sum(json.loads(z.read_text())['elapsed_seconds'] for z in f.parent.glob('attempt*/encode_resource.json')),decode_seconds=json.loads((f/'decode_resource.json').read_text())['elapsed_seconds'],peak_process_tree_rss_bytes=max(json.loads(z.read_text())['sampled_peak_rss_bytes'] for z in f.glob('*_resource.json')))
  for key in ['source_h5ad','dense_int64','canonical_csr']:row[f'archive_over_{key}_ratio']=total/row[key+'_bytes']
  categories={'payload_streams':stream,'paid_model_members':fee['support_model']+fee['value_model_and_group_map'],'graph_index':fee['graph'],'identity_coordinates':fee['identity_coordinate_metadata'],'manifest':fee['manifest'],'zip_framing':fee['container_overhead']}
  assert sum(categories.values())==total
  ledgers.append({'sample_id':s['id'],**categories,'total_archive_bytes':total})
 rows.append(row)
d=pd.DataFrame(rows);d.to_csv(OUT/'ALL_SAMPLES.csv',index=False,encoding='utf-8-sig');pd.DataFrame(ledgers).to_csv(OUT/'PHYSICAL_LEDGER.csv',index=False)
ok=d[d.status.eq('success')];summaries=[]
for field in ['all','platform','species','organ']:
 groups=[('all',ok)] if field=='all' else list(ok.groupby(field))
 for label,x in groups:
  if not len(x):continue
  summaries.append({'category':field,'label':label,'n_accepted':len(x),'n_planned':len(d) if field=='all' else int(d[field].eq(label).sum()),'K8_archive_bytes':int(x.K8_archive_bytes.sum()),'K32_archive_bytes':int(x.total_archive_bytes.sum()),'saved_bytes':int(x.saved_vs_K8_bytes.sum()),'pooled_saved_percent':100*x.saved_vs_K8_bytes.sum()/x.K8_archive_bytes.sum(),'wins':int((x.saved_vs_K8_bytes>0).sum()),'losses':int((x.saved_vs_K8_bytes<0).sum()),'ties':int((x.saved_vs_K8_bytes==0).sum()),'median_saved_percent':x.saved_vs_K8_percent.median(),'weighted_count_stream_bpc':8*x.count_stream_bytes.sum()/x.n_counts.sum(),'weighted_count_stream_bpnz':8*x.count_stream_bytes.sum()/x.n_nonzero.sum(),'weighted_archive_bpc':8*x.total_archive_bytes.sum()/x.n_counts.sum(),'weighted_archive_bpnz':8*x.total_archive_bytes.sum()/x.n_nonzero.sum()})
summary=pd.DataFrame(summaries);summary.to_csv(OUT/'GROUP_SUMMARY.csv',index=False,encoding='utf-8-sig')
u.h.write(OUT/'SUMMARY.json',{'planned':1000,'accepted':len(ok),'status_counts':d.status.value_counts().to_dict(),'groups':summaries,'missing_or_failed_ids':d[~d.status.eq('success')].sample_id.tolist()})
if len(ok):
 plt.rcParams.update({'svg.fonttype':'none','pdf.fonttype':42,'axes.spines.top':False,'axes.spines.right':False})
 fig,ax=plt.subplots(1,3,figsize=(15,4.5),layout='constrained')
 ax[0].scatter(ok.K8_archive_bytes/1e6,ok.total_archive_bytes/1e6,s=10,alpha=.5);hi=max(ok.K8_archive_bytes.max(),ok.total_archive_bytes.max())/1e6;ax[0].plot([0,hi],[0,hi],'--',color='gray');ax[0].set(xlabel='Historical K8 archive (MB)',ylabel='New fixed K32 archive (MB)',title='Paired full-file sizes')
 ax[1].hist(ok.saved_vs_K8_percent,bins=40,color='#4477aa');ax[1].axvline(0,color='gray',ls='--');ax[1].set(xlabel='Full archive saving versus K8 (%)',ylabel='Slices',title='Keep gains and regressions')
 for i,(name,x) in enumerate(ok.groupby('platform')):ax[2].scatter([i]*len(x),x.saved_vs_K8_percent,s=8,alpha=.4)
 ax[2].set_xticks(range(ok.platform.nunique()),sorted(ok.platform.unique()),rotation=20,fontsize=8);ax[2].axhline(0,color='gray',ls='--');ax[2].set(ylabel='Saving versus K8 (%)',title='Platform heterogeneity')
 for ext in ['png','svg','pdf']:fig.savefig(OUT/f'K32_VS_K8.{ext}',dpi=320)
text=f'# Fixed K32 HEST rerun\n\nAccepted {len(ok)}/1000; all accepted records passed real encoding, fresh archive-only decoding and exact canonical recovery. No per-sample K selection.\n\n'
if summaries:
 a=summaries[0];text+=f"Paired accepted K8 bytes: {a['K8_archive_bytes']:,}; K32: {a['K32_archive_bytes']:,}; savings: {a['saved_bytes']:,} B ({a['pooled_saved_percent']:.4f}%). Wins/losses/ties: {a['wins']}/{a['losses']}/{a['ties']}.\n\n"
text+='Recovery covers canonical integer count matrix, full axis identities/order and coordinates/contract metadata, not every H5AD field or original sparse storage bytes. H5AD size comparison is physical only. Canonical CSR bytes use actual decoded array shapes and dtypes, not assumed index width. Ratios are archive/reference. Count-stream bpc divides by n_spots*n_genes; bpnz divides by number of nonzero entries, not sum of counts.\n\nK32 was selected using an exposed50 panel contained within this1000. This is an exploratory fixed-configuration full-cohort rerun, not strict unseen validation or evidence that all biological donors are independent. Historical K8 remains unchanged. Times mix different sessions for historical comparison; no fair speed-rank claim. Failed and pending samples remain in ALL_SAMPLES.csv; summaries use explicitly accepted pairs only. Independent final audit is recorded separately in FINAL_VERIFICATION.json.\n'
(OUT/'RESULT.md').write_text(text,encoding='utf-8');print(text)
