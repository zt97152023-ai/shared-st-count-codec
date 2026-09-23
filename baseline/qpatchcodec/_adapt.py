"""One-time pre-freeze runner adaptation; retained as build provenance."""
from pathlib import Path
p=Path(__file__).with_name('run.py')
s=p.read_text(encoding='utf8')
start=s.index('def encode(sample,method,target):')
end=s.index('\ndef decode(package,out):',start)
s=s[:start]+'''def patch_model(oldq,groups,odds,n,a):
    centers=qm.share(n,a,groups)
    oldcdf=qm.cdf(oldq,groups,odds);sharedcdf=qm.cdf(centers[groups],groups,odds)
    raw,safe,eps=qm.bound(n,a,oldcdf,sharedcdf);mask=safe>12
    blob=qm.encode(centers,groups,oldq,mask)
    q=decode_q(blob,groups)
    return blob,q,oldcdf,mask,raw,safe,eps

def decode_q(blob,groups):
    q=qm.decode(blob,groups)  # bounded parser validates full stream first
    header=bz2.BZ2Decompressor().decompress(blob,max_length=qm.HEADER.size)
    if qm.HEADER.unpack(header)[1]!=1:raise ValueError('Qpatch12 requires mode1')
    return q

def encode(sample,method,target):
    if method!='Qpatch12':raise ValueError('method')
    stage('source_read');source=Path(sample['path'])
    if io.sha(source)!=sample['source_sha256']:raise ValueError('matrix hash')
    x,_=io.read_x(source);n,g=x.shape
    if n*g>300000000 or x.nnz>100000000:raise ValueError('symbol budget')
    man,old=load_reference(sample['v2'])
    if man['schema']!='value-count-v1' or man['method']!='V2_spatial':raise ValueError('reference method')
    if io.csr_sha(x)!=man['canonical_sha256'] or sha(io.jbytes(io.metadata(source,x.shape)))!=man['metadata_sha256']:raise ValueError('raw identity')
    graph=graph_from(old['graph.bz2'],n)
    oldq=np.frombuffer(bz2.decompress(old['value_q1.bz2']),'<u2')
    groups=np.frombuffer(bz2.decompress(old['value_group.bz2']),np.uint8)
    freq=np.frombuffer(bz2.decompress(old['value_base_k.bz2']),'<u2').reshape(8,32)
    odds=np.frombuffer(old['value_odds.u32'],'<u4').reshape(8,7)
    cond=np.frombuffer(bz2.decompress(old['value_cond_k.bz2']),'<u2').reshape(8,7,32)
    stage('raw_gene_counts');npos,ones,_,_=model.gene_counts(x.indices,x.data,g)
    if io.sha(Path(sample['profile']))!=sample['profile_sha256']:raise ValueError('profile hash')
    with np.load(sample['profile'],allow_pickle=False) as profile:
        if not np.array_equal(npos,profile['npositive']) or not np.array_equal(ones,profile['nones']) or not np.array_equal(groups,profile['group']):raise ValueError('raw profile mismatch')
    qblob,q,oldcdf,patch,raw,safe,eps=patch_model(oldq,groups,odds,npos,ones)
    if sha(qblob)!=sample['screen']['blob_sha256'] or sha(q.tobytes())!=sample['screen']['candidate_q_sha256']:raise ValueError('fixed screen candidate mismatch')
    binary,tail,cdf=model.tables(q,groups,freq,odds,cond)
    delta=float(nll_delta(x.indptr,x.indices,x.data,graph,oldcdf,binary))
    safe_bound=float(safe[~patch].sum());raw_bound=float(raw[~patch].sum())
    tolerance=max(1e-6,1e-9*x.nnz)
    if delta>safe_bound+tolerance:raise ValueError('realized NLL exceeds fixed bound')
    stage('value_encode');blob,nll,te,rb=values.encode(x.indptr,x.indices,x.data,graph,groups,binary,tail,cdf,True)
    parts=dict(old);parts['value_q1.bz2']=qblob;parts['values.rans']=blob.tobytes()
    info={k:v for k,v in man.items() if k!='files'}
    info.update(schema='qpatch-count-v1',method='Qpatch12',q1_layout='QSH1-mode1-12bit-exceptions-bz2-v1')
    if int(te)!=man['tail_events'] or int(rb)!=man['remainder_bits']:raise ValueError('tail identity')
    stage('archive_write');write_archive(target,parts,info)
    package_bytes=target.stat().st_size
    framing=package_bytes-sum(map(len,parts.values()))
    oldframing=sample['v2']['package_bytes']-sum(map(len,old.values()))
    model_saved=len(old['value_q1.bz2'])-len(qblob)
    stream_delta=len(parts['values.rans'])-len(old['values.rans'])
    frame_delta=framing-oldframing
    saved=sample['v2']['package_bytes']-package_bytes
    if saved!=model_saved-stream_delta-frame_delta:raise ValueError('byte conservation')
    return {'package_bytes':package_bytes,'package_sha256':io.sha(target),'components':{k:len(v) for k,v in parts.items()},
            'framing_bytes':framing,'framing_delta_bytes':frame_delta,'model_saved_bytes':model_saved,
            'positive_stream_bytes':len(parts['values.rans']),'positive_stream_delta_bytes':stream_delta,
            'old_v2_package_bytes':sample['v2']['package_bytes'],'saved_vs_v2_bytes':saved,
            'fraction_saved_vs_v2':saved/sample['v2']['package_bytes'],
            'value_cdf_sha256':sha(binary.tobytes()+tail.tobytes()+cdf.tobytes()),
            'candidate_q_sha256':sha(q.tobytes()),'qblob_sha256':sha(qblob),'exceptions':int(patch.sum()),
            'raw_counts_sha256':sha(npos.astype('<i8').tobytes()+ones.astype('<i8').tobytes()),
            'value_nll_bits':float(nll),'realized_nll_delta_bits':delta,
            'ledger_nll_delta_bits':float(nll)-sample['old_value_nll_bits'],
            'safe_bound_bits':safe_bound,'raw_bound_bits':raw_bound,'bound_tolerance_bits':tolerance,
            'rans_delta_minus_nll_bits':8*stream_delta-delta,
            'screen_budget_bytes':sample['screen']['budget_bytes'],
            'canonical_sha256':man['canonical_sha256'],'metadata_sha256':man['metadata_sha256']}
''' +s[end:]
s=s.replace("man.get('schema')!='value-count-v1'", "man.get('schema')!='qpatch-count-v1' or man.get('q1_layout')!='QSH1-mode1-12bit-exceptions-bz2-v1'")
s=s.replace("q=np.frombuffer(bz2.decompress(parts['value_q1.bz2']),'<u2');groups=np.frombuffer(bz2.decompress(parts['value_group.bz2']),np.uint8)","groups=np.frombuffer(bz2.decompress(parts['value_group.bz2']),np.uint8)\n    q=decode_q(parts['value_q1.bz2'],groups)")
s=s.replace("or '/count-e1-100/' in p:","or '/count-e1-100/' in p or '/count-value-001/' in p or '/count-qshare-screen-001/' in p or 'gene_profile' in p:")
s=s.replace("'config_sha256':CONFIG_SHA", "'config_sha256':io.sha(E/'config.json')")
s=s.replace('len(samples)*3','len(samples)*len(METHODS)')
p.write_text(s,encoding='utf8')
