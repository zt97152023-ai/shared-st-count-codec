# Shared source and reproducibility release candidate

Repository: https://github.com/zt97152023-ai/shared-st-count-codec

Status: source archive; original-code license grant remains pending. This is not a validated cross-platform software release.

The [2026-09-28 evidence repair](provenance/REPRODUCIBILITY_CONTRACT.md) adds
per-case archive/receipt hashes, recorded comparator contracts, and the missing
E3 worker. Historical execution commits remain unrecorded; the complete
historical software reproduction chain is not closed by this publication.

## Entry points

- `START_HERE.md`: K8/K32 version boundaries and single-file encode/decode/verify commands.
- `SOURCE_MAP.md`: method-to-code map.
- `environment/`: observed environment, pinned core dependencies, native binary hashes and historical environment audit.
- `data/DATA_ACCESSIONS_1000.csv`: one row per frozen HEST sample, provider accession, immutable download URL and historical matrix SHA256.
- `licenses/`: dependency license texts, HEST license and unresolved original-code license status.
- `provenance/`: source provenance and release limitations.

## Rebuild recipe

```text
conda env create -f environment/environment.yml
conda activate shared-count
python tools/check_release.py
python tools/smoke_test.py --output NEW_EMPTY_OUTPUT_DIRECTORY
```

The environment recipe has exact core package versions. It has NOT been installed from scratch during this packaging task. The existing Windows Python 3.11.5 environment has passed the synthetic tests. `installed-distributions.json` records its full package inventory, while the core lock only covers the Shared encode/decode/verify path. Comparator runtimes, plot generation and full-cohort runners have extra dependencies and are not covered by this minimal recipe.

## Data access

All 1000 files have an HF download receipt pinned to commit `8b42ca7f80bc475644ac9a520bba7b9cccbce10d`. All receipt ETags match historical source SHA256 values. This packaging task did not rehash all large H5AD files. Obtain the HEST data through the provider and accept its current access conditions; do not assume anonymous download works.

The source cohort is fixed by the included original DATA_SPLIT.csv and its SHA256, not by the current size of HEST. The HEST sample identifier is not a GEO accession. Original GEO/SRA accessions are only recorded where explicit in available metadata; missing identifiers are not invented from an NCBI-prefixed HEST ID.

## Publication status

The local Git history begins with this packaging operation. It is not the historical development history. The repository is https://github.com/zt97152023-ai/shared-st-count-codec. The original-code copyright holder and license choice remain pending; no release DOI has been assigned. No matrix or image payload is included.
