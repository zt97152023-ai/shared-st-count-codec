# Data availability and accession semantics

The evaluated cohort comprises 1000 frozen HEST samples, identified in DATA_ACCESSIONS_1000.csv. For each sample, the table records `MahmoodLab/hest:st/<ID>.h5ad`, repository revision, pinned download URL, original study/download link when supplied, historical input SHA256 and the local download receipt's ETag. All 1000 provider identifiers, revisions and ETag/hash agreements are present.

Provider: https://huggingface.co/datasets/MahmoodLab/hest

Frozen file revision: `8b42ca7f80bc475644ac9a520bba7b9cccbce10d`.

The local HEST_v1_0_0.csv was a separately downloaded metadata table; its checksum is recorded in DATA_PROVENANCE_SUMMARY.json. Do not infer that its filename denotes the revision of every matrix. The 1000 evaluated files are a fixed cohort, not all samples in the latest provider release.

Only one evaluated sample has an explicit GEO/SRA-like token in the currently available provider metadata; UPSTREAM_ACCESSION_EVIDENCE.csv retains the source field and raw value. Such tokens have not been individually confirmed against the upstream landing page. Remaining original accessions are unresolved, although all HEST processed-file accessions are pinned. Study URLs/DOIs and provider file IDs are distinct columns and must not be presented as sample-level GEO accessions.

Data and original license labels retain provider provenance. HEST currently declares CC BY-NC-SA 4.0 and requires acceptance of its access conditions. The manuscript should cite HEST and retained original studies as appropriate. This source release contains no real matrices or images and makes no full-H5AD recovery claim.

Suggested manuscript wording:

“We evaluated a fixed cohort of 1,000 spatial-transcriptomic count matrices obtained from HEST-1k (MahmoodLab/hest, file revision 8b42ca7f80bc475644ac9a520bba7b9cccbce10d). Per-sample provider identifiers, source-study links where available, and input checksums are listed in the data-accession manifest. Access is subject to the provider's conditions and applicable licenses.”

## Additional single-cell exploration

SINGLECELL_ACCESSIONS_3.csv records the three 10x official dataset URLs, historical download hashes and converted matrix hashes, with CC BY 4.0 declarations verified on official pages. This is separate from the HEST1000 spatial cohort. Historical WSI-only and other exploratory branches remain in the full experiment inventory; this source release does not claim a new complete upstream-accession audit of every WSI experiment.
