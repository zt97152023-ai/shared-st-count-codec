# E3 module-contribution evidence package

This directory is the first bounded E3 deliverable. It separates evidence that is already available from the direct five-arm production ablation that is still gated by a new pilot.

## What is available now

1. `source_families/full_shared_physical_ledger_1000.csv` is the accepted K32 Shared 1000-slice physical ledger. It is a full-arm component-cost dataset, not an ablation table. Its categories are mutually exclusive paid archive bytes: payload streams, paid model members, graph/index, identity/coordinates, manifest, and ZIP framing.

   Across the 1000 accepted archives, payload streams account for 2,213,862,706 B (94.08%), identity/coordinates for 91,881,267 B (3.90%), paid model members for 31,279,544 B (1.33%), and graph/index for 13,217,837 B (0.56%). These are descriptive costs of the full arm, not causal ablation effects.

2. `source_families/spatial_context_control_3slice.csv` contains the exact-recovery support-context control on NCBI618, NCBI692, and NCBI715. C0 is no active support predecessor and C2 is the six-neighbor spatial support context. The positive-value branch was held byte-identical in this family, so it is a direct support/spatial mechanism control, not a complete production no-spatial arm.

   In addition, the accepted 50-slice Production Shared context run is pivoted in `source_families/direct_context_pivot_50.csv` and `source_families/direct_context_long_50.csv`. The full S1V1 arm totals 88,884,058 B; gene-only support context S0V1 totals 93,024,988 B (+4.659%); and no support/value spatial context S0V0 totals 94,318,085 B (+6.114%). S0V1 is named `no_support_context`, not `no_support`, because support is still entropy-coded with gene-only probabilities.

3. `source_families/factorization_sharing_tail_controls_3slice.csv` contains exact-recovery structure controls on the same three slices. The `A/B/C/D` rows form a support/value factorization × simplified q1-sharing factorial; the tail rows test alternative positive-tail families. These rows are useful mechanism evidence but must not be renamed as the direct production `no_value` or `no_sharing` arms.

## Current claim boundary

The package supports a full-arm module ledger and two prior three-slice mechanism families. It does **not** yet contain a comparable five-column table with direct production `full`, `no_support`, `no_value`, `no_spatial`, and `no_sharing` rows. The new task contract therefore requires a three-slice direct pilot before any larger rerun or paper claim.

The direct arm definitions are frozen in `baseline/.ai/tasks/COUNT-E3-MODULE-CONTRIBUTION-001.json`. In particular, `no_value` is operationally defined as a fixed-width lossless positive-integer stream, and `no_sharing` as per-gene parameter fitting/serialization. This prevents post-result relabeling of older simplified controls.

## Intended downstream data products

- `E3_DIRECT_ABLATION.csv`: one row per dataset × arm, with archive bytes, bits/count, bits/nonzero, exact recovery, and source/runtime hashes.
- `E3_COMPONENT_LEDGER.csv`: one row per dataset × arm with support stream, value stream, graph, model, metadata, manifest, and ZIP-framing bytes.
- `E3_SCOPE_AUDIT.md`: explicit distinction between direct production arms and mechanism controls.

Old evidence is copied or referenced read-only; no historical archive or result is overwritten.
