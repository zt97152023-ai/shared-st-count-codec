# Production Shared count codec ablations

## Outcome

This is a finite development-panel study on 50 exposed HEST slices. It uses fixed value-group count K=32 and support predecessor count M_s=6. No protected confirmatory data were accessed. All accepted archives passed fresh decode and exact canonical/metadata recovery; the independent audit reports `all_pass=True` after incorporating one isolated successful retry for the preserved SPA8/ORIGINAL decode failure.

The pooled byte minima under the preregistered full-physical-byte rule are: order arm `ORIGINAL` (88883108 bytes among the accepted order rows), context arm `S1V1`, and support bucket `B16`. The final frozen Production Shared configuration is therefore K=32, M_s=6, the selected bucket `B16`, and the production order policy remains ORIGINAL unless an external protocol explicitly requires a different order; order sensitivity is reported rather than generalized away.

## Evidence coverage

- New main combinations: 250 order, 100 context, 200 support-bucket cases.
- Historical semantic anchors: 100 context rows (S0V1/S1V1) and 50 B8 rows, hash-verified and unchanged.
- Exact recovery: every accepted row has `verify_all=true`; `FINAL_VERIFICATION.json` contains the independent archive/ledger/member audit.
- Reproduction: `REPRODUCTION.json` contains three fresh-process re-encodes whose archive SHA-256 values exactly match their main-run counterparts.
- Failures are preserved: the original main_v3 SPA8/ORIGINAL failure remains in `main_v3/order/SPA8/ORIGINAL`; the successful retry is isolated under `retry/SPA8/ORIGINAL`.

## Interpretation

The order experiment measures physical archive sensitivity to spot traversal, including paid mapping and inverse restoration. The context experiment reports the full S0V0/S1V0/S0V1/S1V1 byte ledger; its decomposition is descriptive of this codec and panel, not a biological causal estimate. The bucket experiment uses nested, pre-frozen Q12 boundaries and includes model, stream, graph, identity/metadata, manifest, and ZIP framing bytes; B8 reuses the verified Production anchor rather than being re-encoded.

## Method coverage and limits

`METHOD_COVERAGE_AUDIT.csv` classifies each relevant parameter/module as 50-sample verified, inherited from 3-sample/mechanism or earlier verified evidence, a design constant, an invariant, or unverified. No low-value hyperparameter search was added after seeing results. The panel is exposed development data with unresolved donor independence and finite technology/organ coverage; no claim of universal order invariance, pan-tissue optimality, or protected-data confirmation is made.

## Output files

- `ORDER_SUMMARY.csv`, `ORDER_PAIRED_COMPARISON.csv`
- `CONTEXT_SUMMARY.csv`, `CONTEXT_DECOMPOSITION.csv`
- `BUCKET_SUMMARY.csv`
- `METHOD_COVERAGE_AUDIT.csv`
- `FINAL_VERIFICATION.json`, `REPRODUCTION.json`, `SEMANTIC_AUDIT.json`
