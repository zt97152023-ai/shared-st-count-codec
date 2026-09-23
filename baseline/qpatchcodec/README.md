# Qpatch12 complete count codec

COUNT-QPATCH-001 fixes the accepted screen candidate and regenerates every positive-count symbol. The original100 exposed sources are the only data allowed. New complete archives contain QSH1 mode1 under `value_q1.bz2` and a new `values.rans`; all other old V2 payload members are byte-identical. The manifest uses `qpatch-count-v1` and declares the changed q representation.

Eight group q values are pooled from raw per-gene singleton/positive counts. Genes with frozen worst-context `U_safe > 12` retain their original Q12 q as paid 12-bit exceptions. The exact candidate blob must match the accepted screen SHA. Spatial odds, graph, tail groups and K tables are frozen; this changes singleton CDFs and therefore requires new rANS encoding. Count values remain lossless.

`model.py`, `values.py` and `frozen_runtime` are exact copies of COUNT-VALUE-001; `qshare_model.py` is the exact screen module. `metrics.py` directly measures realized new-minus-old Bernoulli NLL under unchanged causal contexts, using compensated summation. The decoder receives only the new archive, reconstructs q from the paid model/group members and uses already decoded earlier-row values as context.

Run from workspace:

```powershell
& C:/Users/zhang/anaconda3/python.exe -X utf8 -B -m unittest discover -s baseline/qpatchcodec -p 'test_*.py' -v
& C:/Users/zhang/anaconda3/python.exe -X utf8 -B baseline/qpatchcodec/run.py --output baseline/evidence/COUNT-QPATCH-001/new_run
```

Output must not exist. Configuration and implementation hashes are checked. Each encoder and decoder is a separate process with 600-second/12-GiB sampled-RSS limits; runs are serial, 7200-second budget checked between cases, disk minimum12GiB. Failures retain NULL verified bytes and are never retried. Python source-read audit hooks are an additional guard, not an OS sandbox.

`_adapt.py` is retained one-time build provenance and must not be run again. `freeze.py` creates config files exclusively and also must not be rerun into the fixed evidence directory. Decode does not read config, profiles, original archives or raw matrices.

The primary gate is positive total complete-package saving and positive median per-slide percentage saving versus old V2, conditional on100/100 full exactness in main and independent reproduction plus matching physical archive hashes. The screen NLL bound is diagnostic; physical value-stream and framing differences are explicitly paid. S0/V0 and original34/66 strata are secondary descriptions.
