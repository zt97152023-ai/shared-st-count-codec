# COUNT-MATCHED-READY-001

This directory adds two explicit raw H5AD paths:

```text
python -X utf8 -B -m baseline.matched_ready encode --input source.h5ad --output s0.cnt --mode s0
python -X utf8 -B -m baseline.matched_ready encode --input source.h5ad --output shared.cnt --mode shared-only
python -X utf8 -B -m baseline.matched_ready evaluate --input s0.cnt --reference source.h5ad --output s0.json --mode s0
```

`s0` loads the formal frozen `COUNT-E1-100/runtime/codec.py` and invokes its
`S0_gene` implementation. `shared-only` derives the same support graph, q0,
56 support odds, value groups, base tails, value odds and conditional tails as
Qpatch12, then changes only QSH1 to mode0 (all genes use the shared center) and
re-encodes `values.rans`. It does not invoke or regenerate Qpatch12.

Both modes use the frozen io047 adapter, deterministic ZIP_STORED accounting,
fresh archive-only decoding, and parent-process exact CSR/identity/coordinate
comparison. Existing outputs, wrong references, malformed members, and mode
mismatches fail closed. The Shared-only archive has no historical golden; its
historical acceptance requires two deterministic SPA108 outputs and equality
of all non-target members against the immutable Qpatch12 package.

