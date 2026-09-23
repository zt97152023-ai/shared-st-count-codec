# Production Shared closure — fixed K=32, 50 exposed HEST slices

## Final result

The historical 1000-sample K32 Shared B8 headline remains unchanged. This closure did not rerun the full 1000-sample headline, so the new development configuration is not relabeled as the headline.

The best complete development candidate is **K32 Shared B32 / M_s=6 / M_v=6**.

- B32 pooled archive: **88,784,525 B**.
- Historical B16 pooled archive: **88,793,409 B**.
- B32 vs B16: **0.010005% smaller**; B32 vs historical B8: **0.111981% smaller**.
- Adding value context M_v=6 on the B32 base gives **88,773,345 B**, another **0.012592%** reduction.

## Pre-registered stops

B64 was not run: B32 did not beat B16 by more than 0.05% (0.010005%). M_v=16 was not run: M_v=12 was not better than M_v=6; it was **-1.511403%** worse relative to M_v=6. Threshold/binning escalation was not justified because the remaining gains were below the 0.05% escalation threshold.

## Coverage and validation

All required arms are complete: B32 50/50, B32×M_s 100/100, B16×M_s 100/100, B16-base M_v 300/300, and B32-base M_v 300/300. Every effective arm has `verify_all=true`; three independent fresh-process reproductions passed.

The M_v=0/6 member audits cover both B16 and B32 bases (50 samples each). M_v=6 changes only `manifest.json` relative to its base; M_v=0 changes the expected value members (`value_cond_k.bz2`, `value_odds.u32`, `values.rans`) plus manifest metadata.

Raw failures, including transient Numba/cache failures and three disk-truncated TENX96 archives, remain in the evidence tree. Repaired successes are explicitly marked in retry/rebuilt evidence and were not silently substituted.

No protected data or external baseline rerun was used; K=32 and canonical recovery were held fixed.
