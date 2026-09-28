# E3 direct module contribution — 50-slice expansion

The direct five-arm E3 expansion completed on the fixed 50-slice exposed HEST development panel. All 250 dataset × arm rows passed fresh-process decode, exact source verification, and physical-ledger closure. No protected data were accessed.

## Pooled archive cost

| arm | pooled archive bytes | delta vs full | increase |
|---|---:|---:|---:|
| full | 88,884,058 | reference | reference |
| no_support | 93,017,038 | +4,132,980 | +4.650% |
| no_value | 648,131,973 | +559,247,915 | +629.188% |
| no_spatial | 94,318,085 | +5,434,027 | +6.114% |
| no_sharing | 89,735,290 | +851,232 | +0.958% |

Per-slice direction was consistent for `no_value` (50/50 increases), mostly consistent for `no_support` (46/50), `no_spatial` (36/50), and `no_sharing` (48/50). Negative per-slice deltas are retained in `E3_PAIRED_DELTAS_50.csv` rather than excluded.

## Full-arm physical ledger

Within the full arm, pooled bytes are distributed as follows:

- support stream: 42,717,492 B (48.06%)
- value stream: 39,464,206 B (44.40%)
- identity/coordinates metadata: 4,222,029 B (4.75%)
- support model: 898,355 B (1.01%)
- graph/index: 930,262 B (1.05%)
- value model/group map: 485,053 B (0.55%)

These are descriptive full-arm costs. The ablation deltas are the module-contribution measurements.

## Interpretation boundary

`no_value` is a fixed-width lossless positive-uint32 stream and therefore measures the cost of removing the current positive-value model under this explicit raw fallback; it is not a claim that raw coding is the strongest alternative model. `no_sharing` removes cross-gene q1 sharing while retaining the fixed K32 tail groups, so it measures q1-sharing contribution rather than independently refitting every tail histogram.

## Verification

- 250/250 rows exact;
- 250/250 ledgers sum exactly to archive size;
- 0 encode failures;
- 0 decode/verification failures;
- INT17 `no_support` and MEND124 `no_sharing` fresh-process reproductions were byte-identical;
- full arm is the hash-pinned accepted K32 anchor with prior fresh-process validation.

Primary outputs are `E3_DIRECT_ABLATION_50.csv`, `E3_COMPONENT_LEDGER_50.csv`, `E3_PAIRED_DELTAS_50.csv`, `E3_50_SUMMARY.json`, and `INDEPENDENT_AUDIT.json`.
