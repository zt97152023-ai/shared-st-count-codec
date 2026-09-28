# E3 module contribution — consolidated package

Publication correction (2026-09-28): see the
[frozen-run and E3 contract](../../../provenance/REPRODUCIBILITY_CONTRACT.md).
The unedited historical README is retained in
`docs/historical/E3_CONSOLIDATED_README.md`. Historical archive junctions below
describe the original local evidence layout; they are not shipped in Git.

This directory is the single entry point for the E3 direct ablation evidence.
It combines the three-slice direct pilot and the 50-slice expansion while
preserving the original evidence directories and their paths.

## Contents

- `pilot_v1/` — three-slice direct pilot summaries, ledgers, and a junction to
  the original pilot outputs.
- `expansion_50/` — 50-slice direct ablation summaries, paired deltas,
  independent audit, gate status, and a junction to all 250 archive files.
- `source_families/` — source-family and component-ledger CSVs used by the
  pilot and the production 50-slice context analysis.
- `reproduction_50/` — fresh-process reproduction outputs for the two
  representative checks.
- `scripts/` — the pilot and 50-slice generation, verification, summary, and
  audit scripts.
- `contracts/` — the two task contracts and their acceptance evidence.
- `ARCHIVE_LINKS.md` — exact source locations and storage policy.
- `ARTIFACT_MANIFEST.csv` — manifest of the consolidated evidence artifacts.

## Headline direct-ablation results

All values below are pooled archive bytes across the 50-slice panel. The
comparison is against the same `full` arm and uses the exact 5-arm design.

| arm | archive bytes | change vs full |
| --- | ---: | ---: |
| full | 88,884,058 | reference |
| w/o support | 93,017,038 | +4.650% |
| w/o value | 648,131,973 | +629.188% |
| w/o spatial | 94,318,085 | +6.114% |
| singleton probability replacement (`no_sharing`) | 89,735,290 | +0.958% |

The 50-slice panel contains 250 exact arm-level rows, with zero failed
verification rows. The `no_value` arm is the strongest cost driver in this
implementation; `no_spatial` and `no_support` provide smaller but consistent
penalties. The retained expansion manifests and model dimensions establish
support B8 / value K32. The `no_sharing` arm stores per-gene singleton
probability exceptions while retaining K32 tail/conditional sharing, support
sharing and paid shared-centre headers. Its +0.958% effect applies to that
specific replacement, not removal of all sharing. The historical phrase
“fixed eight-class tail control” was incorrect.

## Storage and provenance

The directories named `pilot_v1/archives` and `expansion_50/archives` are
NTFS directory junctions, not duplicated copies. They point to the original
evidence locations documented in `ARCHIVE_LINKS.md`. This keeps the package
single-entry and reproducible while preserving the original evidence folders
for historical references.

The consolidated package is an index-and-analysis layer; the original
evidence directories remain authoritative for raw archive payloads.
