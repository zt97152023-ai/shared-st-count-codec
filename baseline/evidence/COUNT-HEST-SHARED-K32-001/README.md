# Fixed support8 / value32: complete HEST1000 rerun

User-confirmed scope: all1000 previously accepted HEST slices, fresh encoding at fixedK32. Outputs: `D:/HEST1000BenchRun/COUNT-HEST-SHARED-K32-001`. Source H5ADs and historical K8 archives are not overwritten. No other comparator, training, adaptation or image experiment is launched.

This is the new fixed-K32 experiment configuration. Historical Production Shared K8 remains a separate immutable reference. Candidate selection is not performed per sample. The threshold family is exactly the previously tested fixed-log-axis-v1; support still uses8 buckets and six causal spatial predecessors. Count integers are recovered exactly under the canonical recovery contract.

All1000 source IDs/hashes are frozen in DATA_SPLIT.csv. Platform composition:497 Spatial Transcriptomics,463 Visium,37 Xenium,3 VisiumHD;484 human and516 mouse. The previous tuning50 are contained in this panel, so results cannot be described as1000 strictly unseen independent samples. Biological donor independence is not assumed.

Four small samples run in parallel; after the pool finishes,45 samples with nnz>20M OR matrix elements>300M run serially. Existing hash-pinned500M-capacity runtime handles NCBI792/793 without changing probability rules. Worker threads are1; sampled per-process-tree RSS ceiling16GiB, stage1800s, invocation24h, D disk reserve40GiB. These limits are sampled and are not a hard total-machine memory reservation. Native encode retry is bounded to one; other failures remain visible; integrity/resource failures stop. Original H5AD count values stored as floats may normalize to canonical int64 only if valid integer counts, as in the historical codec.

Existing environment command from `E:/count压缩`: `python -X utf8 baseline/evidence/COUNT-HEST-SHARED-K32-001/run.py`. Independent REVIEW_RELEASE.json and passing D-drive PREFLIGHT.json are required. RUNNING.lock prevents simultaneous runners. Resume audits successful archives and does not reencode them. A stale lock requires checking the recorded process identity before manual recovery; never launch duplicate runs.

On D:
- PROGRESS.json / INDEX.json: live complete1000 coverage, including failures/pending.
- main/<sample>/VALUE_K32/attemptNN/: actual archive.cnt, sourcehash, full ledger, encode/decode/verify process receipts, historical K8 comparison and decoded metadata.
- ALL_SAMPLES.csv: every selected sample's status, size, stream/full bpc,bpnz, physical ratios and resource records.
- PHYSICAL_LEDGER.csv: six categories exactly sum to each physical archive size.
- GROUP_SUMMARY.csv / SUMMARY.json / RESULT.md: full-cohort and platform/species/organ results.
- K32_VS_K8 PNG/SVG/PDF: real paired sizes and all slice changes, including regressions.
- reproduction/: separately re-encoded smallNCBI180 and largeNCBI792, archiveSHA matched.
- FINAL_VERIFICATION.json: independent post-run audit, copied from the reviewer evidence on E after completion.

Only regenerated decoded.npz is deleted after successful exact verification and SHA/length recording. The decoded canonical CSR payload bytes and each array dtype are extracted from NPZ headers before cleanup. No int32 index assumption is made. SourceH5AD physical-size ratios do not claim fullH5AD reconstruction. Recovery covers canonical counts, complete axes/order/identities, coordinates and the defined metadata contract.

The `code/` copy on D is a provenance snapshot for the current project/environment, not a standalone decoder distribution. Execute using the original E-project entrypoint and pinned codec venv. No modelcheckpoint is needed because Shared is a statistical entropy model with paid per-archive parameters.
