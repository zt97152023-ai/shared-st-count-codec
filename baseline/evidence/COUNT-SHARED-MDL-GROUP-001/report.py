"""Report finite-set paid selection without replacing the original Shared reference."""
import csv,json
from pathlib import Path
R=Path(__file__).resolve().parent

def main():
    out=R/'main_v1'
    rows=json.loads((out/'RESULTS.json').read_bytes())['rows']
    assert len(rows)==45 and all(r['status'] in ('passed','success') for r in rows)
    result={'per_slice':[],'pooled':{},'claim_scope':'Singleton grouping only; finite candidate search; three exposed slices; no Qpatch superiority claim.'}
    choices={}
    for sid in ['NCBI692','NCBI715','NCBI618']:
        rr=[r for r in rows if r['sample_id']==sid]
        assert len(rr)==15
        fixed=next(r for r in rr if r['arm']=='FIXED_SHARED')
        candidates=[r for r in rr if r['arm']=='ADAPTIVE']
        assert len(candidates)==12
        def key(r):return (r['total_bytes'],r['K'],int(r['exceptionsflag']))
        selected=min(candidates,key=key)
        nomask=min([r for r in candidates if not r['exceptionsflag']],key=key)
        controls={a:next(r for r in rr if r['arm']==a) for a in ['GLOBAL_SHARED','PER_GENE']}
        controls.update(FIXED_SHARED=fixed,ADAPTIVE_MDL=selected,ADAPTIVE_WITHOUT_EXCEPTIONS=nomask)
        choices[sid]=controls
        for arm,r in controls.items():
            delta=fixed['total_bytes']-r['total_bytes']
            modeldelta=fixed['modelblob_bytes']-r['modelblob_bytes']
            streamdelta=fixed['value_stream_bytes']-r['value_stream_bytes']
            framedelta=fixed['framing_bytes']-r['framing_bytes']
            assert delta==modeldelta+streamdelta+framedelta
            result['per_slice'].append(dict(sample_id=sid,arm=arm,K=r['K'],exceptionsflag=r['exceptionsflag'],
                total_bytes=r['total_bytes'],saved_bytes=delta,saved_percent=100*delta/fixed['total_bytes'],
                modelblob_bytes=r['modelblob_bytes'],model_saved_bytes=modeldelta,value_stream_bytes=r['value_stream_bytes'],
                stream_saved_bytes=streamdelta,framing_saved_bytes=framedelta,
                bits_per_count=8*r['total_bytes']/r['n_counts'],bits_per_nonzero=8*r['total_bytes']/r['n_nonzero'],
                selected_artifact=r['artifact_path'],diagnostics=r.get('diagnostics',{}),
                adaptive_search_encode_seconds=sum(c['encode_seconds'] for c in candidates) if arm=='ADAPTIVE_MDL' else None))
    base=sum(v['FIXED_SHARED']['total_bytes'] for v in choices.values())
    for arm in choices['NCBI692']:
        total=sum(v[arm]['total_bytes'] for v in choices.values())
        result['pooled'][arm]=dict(total_bytes=total,saved_bytes=base-total,saved_percent=100*(base-total)/base,
            no_slice_worse=all(v[arm]['total_bytes']<=v['FIXED_SHARED']['total_bytes'] for v in choices.values()))
    a=result['pooled']['ADAPTIVE_MDL']
    result['primary_gate_passed']=a['saved_percent']>=1 and a['no_slice_worse']
    result['primary_hypothesis_status']='supported_on_development_panel' if result['primary_gate_passed'] else 'not_supported_at_practical_gate'
    (R/'SUMMARY.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    flat=[{k:v for k,v in r.items() if not isinstance(v,dict)} for r in result['per_slice']]
    with (R/'SUMMARY.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
    lines=['# Shared MDL singleton grouping: measured results','',
        'Three exposed complete canonical count matrices. Original spatial/support/tail/odds members stay byte-identical. Every new candidate has real rANS and fresh archive-only exact decode. Candidate selection uses total paid archive bytes, not NLL.',
        '', '| Method | Complete bytes | Saving vs original Shared | No slice worse |','|---|---:|---:|---|']
    for arm,p in result['pooled'].items():lines.append(f"| {arm} | {p['total_bytes']:,} | {p['saved_percent']:+.4f}% | {p['no_slice_worse']} |")
    lines+=['','| Slice | Method | K | Exceptions enabled | Saved bytes | Model saved B | Value stream saved B |','|---|---|---:|---|---:|---:|---:|']
    for r in result['per_slice']:lines.append(f"| {r['sample_id']} | {r['arm']} | {r['K']} | {r['exceptionsflag']} | {r['saved_bytes']:,} | {r['model_saved_bytes']:,} | {r['stream_saved_bytes']:,} |")
    lines+=['',f"Predeclared primary practical gate: **{result['primary_gate_passed']}** (>=1% pooled saving and no slice larger).",'',
        'ADAPTIVE_MDL selects the shortest actual archive among12 frozen candidates per slice. All candidate encoding and fitting time is counted as encoder search cost; only the selected deployed archive is stored in the logical codec comparison. Experiment evidence retains all candidates. This is a bounded implemented selection rule, not a free oracle, global MDL optimum or held-out validation.',
        'The unconditioned Bernoulli Lloyd proxy generates clusters; integer contextual probabilities and real rANS are used for actual selection. Singleton labels and tail labels are separate. The inherited safe>12-bit exception heuristic is not the true marginal cost of an exception in this new compressed schema (exceptions use uint16); only complete archive selection establishes net value.',
        'Without-exceptions best is reported separately; a with-exceptions gain cannot all be attributed to grouping. No claim of superiority over existing Qpatch12 is made. GLOBAL and adaptiveK1/no-exceptions are redundant distribution controls; PER_GENE pays an identity mapping and is a conservative serialization control, not an optimal per-gene format.',
        'Complete total includes support, positive stream, group mapping, probability parameters, graph, metadata and framing. bpc/bpnz in SUMMARY.csv use full archive bytes; support stays fixed. Dtype/shape/CSR values and exact metadata are checked against original canonical sources. These are three biological slices, not45 independent samples.',
        'Independent final verification and source/byte ledger audit are required for scoped acceptance. Failures and attempts must be disclosed from main logs rather than silently excluded. No image, neural training or protected148 data is used.']
    (R/'RESULT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'primary_gate':result['primary_gate_passed'],'pooled':result['pooled']},indent=2))
if __name__=='__main__':main()
