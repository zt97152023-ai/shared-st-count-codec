# E3 module contribution — phase 0 result

Phase 0 is accepted as an evidence inventory. Direct pilot v1 is now complete on three exposed HEST development slices; it is still not a protected-data or 1000-slice claim.

## Released data

- Full K32 Shared: 1000 accepted archives, 2,353,229,497 total bytes. The physical ledger sums exactly for every row. Payload streams are 94.08% of pooled bytes; identity/coordinates are 3.90%; paid model members are 1.33%; graph/index is 0.56%.
- Production context panel: 50 accepted slices and 150 long-format rows. Full S1V1 is 88,884,058 B pooled; S0V1 (`no_support_context`) is 93,024,988 B (+4.659%); S0V0 (`no_spatial`) is 94,318,085 B (+6.114%). All rows carry exact-recovery success.
- Prior mechanism controls: copied as separate source families and retained under their original semantics.

## Gate outcome

The current data are sufficient for a preliminary component-cost and spatial-context analysis. They are not sufficient for the paper's ideal direct five-arm contribution analysis because direct `no_value` and direct per-gene `no_sharing` rows are absent, and S0V1 is a context removal rather than removal of support coding itself.

The direct five-arm pilot remains the next registered gate. No historical evidence was overwritten and no protected data were accessed.

## Direct pilot v1

All 15 dataset × arm rows passed fresh-process decode, source verification, and exact canonical/metadata recovery. Every physical ledger sums exactly to the archive size.

| arm | pooled archive bytes | increase vs full |
|---|---:|---:|
| full | 13,833,431 | reference |
| no_support | 14,033,591 | +1.447% |
| no_value | 109,510,612 | +691.637% |
| no_spatial | 14,193,215 | +2.601% |
| no_sharing | 13,904,272 | +0.512% |

The `no_value` arm is deliberately a fixed-width lossless positive-value stream, so its large increase is the paid cost of removing the positive-value model, not a claim that a particular alternative entropy model is optimal. The `no_sharing` arm removes cross-gene q1 sharing while retaining the fixed eight tail classes; this is a q1-sharing contribution, not a full independently fitted tail-histogram model.

Fresh-process byte-identical reproductions passed for INT17 `no_support` and `no_sharing`. The `full` arm is the hash-pinned accepted K32 anchor with prior exact fresh-process validation.
