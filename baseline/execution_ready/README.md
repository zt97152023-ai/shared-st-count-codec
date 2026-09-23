# COUNT-EXECUTION-READY-001

This directory provides the bounded `qpatch12` execution and validation slice.
It does not modify the frozen codec or read candidate matrices.

The format adapter calls the frozen `COUNT-E1-100/runtime/io047.py` contract
with `canonical=True`. Dense, CSR, and CSC inputs therefore share the same
canonical CSR semantics: duplicate entries are summed, stored zeros removed,
indices sorted, and values remain exact nonnegative uint32-domain integers.
Missing `X`, labels, or finite two-dimensional spatial coordinates are rejected;
duplicate identifiers are retained in their original order as required by
`io047`.

Preparation is a separate phase. It derives the six-predecessor spatial graph
by extracting only `graph_for` from the frozen runtime AST, fits support with
`sharedcodec/model.py fit/cdf` and frozen entropy, and derives the paid positive
model with the frozen Qpatch model, QSH1 patch, and value stream. No V2 archive,
profile, screen result, Pcodec, or Rust dependency is used by `encode`.

Suggested commands (from the repository root):

```text
python -X utf8 -B -m baseline.execution_ready encode --input source.h5ad --output package.cnt --mode qpatch12
python -X utf8 -B -m baseline.execution_ready evaluate --input package.cnt --reference source.h5ad --output report.json --mode qpatch12
python -X utf8 -B -m unittest discover -s baseline/execution_ready -p 'test_*.py' -v
```

`evaluate` starts a fresh subprocess that receives only the package and writes
temporary decoded arrays. The parent then reads the reference through frozen
`io047`, compares CSR arrays and metadata bytes exactly, rebuilds the value CDF
from archive members, and reports member bytes, hashes, framing, symbol counts,
and package SHA. Existing report/package paths are rejected.

Release gate v0.3 has four required doors (data P4 plus frozen manifest SHA and
signature range; code hash and review; environment authentication; preregistered
full results and failure policy). The data door is pending, so this directory
reports `candidate_ready: false` and never creates `VALIDATION_FROZEN.flag`;
even a future all-door result remains orchestrator-controlled.
