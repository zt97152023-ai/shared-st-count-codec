# Shared source and reproducibility release candidate

Status: local release candidate; not yet a published repository or an open-source license grant.

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

The local Git history begins with this packaging operation. It is not the historical development history. No remote repository, public release URL, DOI or original-code license has been fabricated. The owner must supply the public repository URL, copyright holder and license choice before a public release can be finalized. No matrix or image payload is included.
