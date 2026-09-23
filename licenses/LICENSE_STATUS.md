# License status, 2026-09-23

## Original Shared implementation

No original project-wide LICENSE or authoritative copyright-holder declaration was located in the supplied source tree. The user's requested open-source license choice and copyright-holder identity are pending. No MIT/BSD grant has been applied. Code origin is recorded by SOURCE_MANIFEST.json and historical pin checks; a hash is not evidence of copyright ownership.

This status document is not a license grant. Original source has been archived unchanged. An institutional/author rights confirmation is still required before attaching an original-code license. The local Git commit is an archival operation, not an authorship claim.

## HEST data and library

Official sources checked:
- https://github.com/mahmoodlab/HEST
- https://github.com/mahmoodlab/HEST/blob/main/LICENSE.md
- https://huggingface.co/datasets/MahmoodLab/hest

The provider currently declares CC BY-NC-SA 4.0 for HEST-1k/HEST-Library. The official license text is retained as HEST_CC_BY_NC_SA_4.0.txt. Access currently requires accepting the provider's conditions. This does not change the license of independently written Shared code automatically; no HEST library code is represented as relicensed here.

Original sample-level license labels are preserved separately in DATA_ACCESSIONS_1000.csv. 24 rows say Internal and 433 lack an original license label; 4 explicitly refer to a BY-NC-ND license. The provider's collection license and these original labels are separate evidence. This package does not claim that every original sample's downstream redistribution/derivative use has been individually cleared. No raw matrix, WSI or count archive is redistributed in this release candidate.

## Dependencies

Exact installed versions and upstream metadata are in environment/ENVIRONMENT_LOCK.json. 13 installed license/notice files for NumPy, SciPy, h5py, Numba and llvmlite are copied verbatim under dependencies, with SHA256 in DEPENDENCY_LICENSE_INDEX.json. Native binaries are not redistributed. Bundled third-party notices inside dependency licenses must not be replaced by the top-level Shared license.

## Publication blockers

1. Original Shared code copyright holder and selected license.
2. Public repository URL/release DOI if the manuscript claims public code availability.
3. Individual upstream accession/rights clarification where original-source metadata is absent, if making original-source redistribution claims.

## Three exploratory single-cell datasets

The official 10x dataset pages for pbmc_1k_v3, pbmc3k and neuron_1k_v3 explicitly declare CC BY 4.0, checked 2026-09-23. URLs and historical source/converted matrix hashes are in data/SINGLECELL_ACCESSIONS_3.csv. These three provider identifiers are not GEO accessions.
