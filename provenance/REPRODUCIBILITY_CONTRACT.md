# Frozen-run evidence and release correspondence

This document resolves the reporting defects labelled **EXP-001**, **EXP-002**
and **E3 dependency/member identity** in the review. These are review issue IDs,
not the older experiment-registry IDs with the same names.

## EXP-001: what is linked, and what remains unavailable

The [evidence bundle](evidence_20260928/SUMMARY.json) links all 1,000 selected
`COUNT-HEST-SHARED-K32-001` cases, the 9,000 recorded comparator cases and the
250 E3 expansion cases to retained reports and archive hashes. The builder
rehashes the retained charged archive files. For E3 it also reads the actual ZIP
manifest, checks the complete member set, hashes each member and checks model
table dimensions. It performs **no new count decoding or codec experiment**.
Separately, `validation/E3_VALIDATION_20260928.json` records five new
archive-only decodes of NCBI180 (one per E3 arm) with the repaired release;
recovered CSR and metadata hashes match the stored manifests. It also checks all
50 no_sharing QSH1 headers for all-gene exceptions and retained 32 centres.
These are current release checks, not a historical environment replay.

- `K32_CASES.jsonl`: sample, historical source hash, archive location, actual
  archive SHA256, and references to encode/decode/verify/resource/retention
  receipts. Missing historical commit is JSON `null`.
- `COMPARATOR_*.jsonl`: selected attempt, logical/source dtypes where recorded,
  physical charged files, hashes, manifest, recovery evidence and receipt refs.
- `COMPARATOR_CONTRACTS.json`: one contract per recorded method, with observed
  dtype/configuration distributions, runtime variants, charged-file layouts and
  explicit coverage of environment receipts.
- `E3_CASES.jsonl`: all five arms, real manifest and individual member identity.
- `receipts.zip`: original JSON bytes, named `<SHA256>.json`, without rewriting
  their contents. `RECEIPT_INDEX.json` maps original location to hash and length.
- `SOURCE_PIN_BRIDGE.json`: historical declared pin → retained file hash →
  release-relative file hash. A missing release file or a mismatch remains
  explicit; a current match alone is not evidence of historical execution.
- `RELEASE_DEPENDENCIES.json`: current release Python source inventory, including
  the previously omitted E3 worker. This inventory is not a historical lock.
- `HISTORICAL_RUNTIME_RECEIPTS.json`: environments actually recorded alongside
  comparator stages; `COMMANDS_BY_CONFIGURATION.json` locates recorded commands.
- `configuration_receipts.zip` and `CONFIGURATION_RECEIPT_INDEX.json`: original
  comparator plans and repair configuration, including the initial/recovered
  run identities. `COMPARATOR_SOURCE_PIN_BRIDGE.json` maps their code pins.
- `ARTIFACT_SHA256.json`: public evidence-file integrity manifest.

The base public release is commit
`39acc115e3abb0d13eeb12edf636f53309fceba6`. Git history began at packaging;
**the historical execution commit was not recorded**. The commit containing this
repair identifies the repaired publication only. Neither commit is substituted
for the missing historical execution commit. Historical pins and the retained
K32 `code/` snapshot provide a file-level bridge, not a reconstructed Git history.

The actual K32 command receipts identify the matched-ready Python executable.
Its historical dependency lock is now included at
`baseline/evidence/COUNT-MATCHED-READY-001/requirements.lock.txt` (with wheel
hashes). The existing `environment/` inventory describes the packaging/smoke
environment and must not be relabelled as the K32 or all-comparator environment.
Per-stage environment receipts take precedence over a current environment
snapshot. Missing stage-level environment captures, including E3's historical
interpreter/dependency versions where unrecorded, remain unknown.

Archive paths identify locally retained artifacts; **compressed count archives,
source H5ADs, native comparator binaries and complete environment installations
are not distributed in this Git repository**. Receipt hashes and rehash results
are not a substitute for access to those artifacts. Thus the complete historical
software reproduction chain remains open, even after these publication repairs.

## EXP-002: recorded comparator contract

All configurations target canonical integer `int64` CSR counts, complete spot
and gene labels/order, coordinates (shape/dtype/bytes), and the agreed 047
metadata. This does not preserve arbitrary source H5AD `obs`, `var`, `layers`,
`uns`, storage layout, or source floating-point dtype. Source storage dtype is
reported separately from the canonical dtype. Physical uint32 conversion is
range checked; decoding is compared against the canonical object.

| Recorded configuration | Version/parameters and representation | Charged object |
|---|---|---|
| `BP_gene_none` | BPCells 0.3.0rc2; spots × genes CSC, uint32; no sorting or transpose | All files in matrix directory, metadata.bz2 and manifest.json |
| `BP_spot_mean` | BPCells 0.3.0rc2; transpose to genes × spots, stable mean sort of native rows (genes), stored/inverted permutation | Matrix directory, permutation.bz2, metadata.bz2 and manifest.json |
| `IVCSC` | upstream ab406eb51dd2ea358eba5236720fb5d3acdaa6e5; CSC; uint32 values/indices; executable identified by historical pins | archive.bin: native matrix, metadata, manifest and ZIP framing |
| `IVCSC_bz2` | Same native representation, additionally BZip2 level 9 | archive.bin: compressed native matrix, metadata, manifest and ZIP framing |
| `CSR_ZSTD19` | zstandard 0.19.0 in recorded runtime; level 19, threads=0; uint32 pointer/index-gap/value arrays in NPZ | archive.bin: matrix.zst, metadata.bz2, manifest and ZIP framing |
| `CSC_ZSTD19` | Same settings with CSC orientation | Same complete archive accounting |
| `H5AD_GZIP4` | AnnData writer version from each runtime receipt; gzip level 4; canonical count uint32 H5AD with labels and spatial coordinates; direct h5py decoder | matrix.h5ad plus manifest.json |
| `CSR_BZIP2_9` | F047 frame; BZip2 level 9; uint64 shape/indptr, uint32 indices/values | archive.bin: csr.bz2, metadata.bz2, manifest and ZIP framing |
| `Pcodec` | pcodec 1.0.3, level 8; uint32 row lengths, within-row index gaps and values | archive.bin: three pco streams, metadata.bz2, manifest and ZIP framing |

For IVCSC, temporary `exchange.csc` and `native.ivcsc` are encoder working files,
not decoder dependencies; only `archive.bin` is charged. Directory archives use
the sum of file byte lengths, not filesystem allocation size. Every selected
case lists the exact charged files and their actual hashes and reconciles their
sizes with the reported archive total.

Actual commands, executable identities and version receipts are preserved per
case. Typical historical command forms (paths supplied by the receipts) are:

```text
<python> -X utf8 -B -m baseline.hest1000.pilot worker encode <method> <prepared> <archive>
<python> -X utf8 -B -m baseline.hest1000.pilot worker decode <method> <archive> <decoded> --blocked <source-root> <prepared>
<python> -X utf8 -B -m baseline.hest1000.main compare <prepared> <decoded> <EXACT.json>
<python> -X utf8 -B -m baseline.evidence.COUNT-HEST-BASELINES-1000-005.extra_worker worker <encode|decode> <CSR_BZIP2_9|Pcodec> <input> <output>
```

The two CSR_BZIP2_9 repair cases, TENX86 and TENX82, use
`extra_worker_checked.py`, which adds an encode-side round-trip check. They are
not silently represented as the original failed attempts. Original failure
receipts, selected repair receipts, attempt identifiers and the repair table
are included. Historical recovery records are retained evidence, not newly
replayed independent validation. Python file-access guards are not OS isolation.

The selection reuses 113 older IVCSC cases whose receipts use `count.cnt` and
`package_sha256`. Their archive bytes and hashes are checked under that original
schema. The original run-level `config.json` and `environment.json` are included
in `configuration_receipts.zip`; their source hashes match the corresponding K32
selection. Per-case shape/indptr/indices/values/metadata checks are preserved.
These older receipts did not record a separate dtype-check boolean or every
stage command: those missing fields remain explicit, alongside the run-level
source/environment links. They are not presented as newer receipt schemas.

Comparisons are restricted to **these recorded configurations and this exposed
panel**. Common recovery fields do not establish exhaustive parameter tuning,
equal engineering effort, timing comparability, comprehensive fairness, or
universal superiority. The packaging environment is not sufficient to run every
external comparator; native dependency pins describe identity, not availability.
The retained initial H5AD runtime reports AnnData 0.12.19 and h5py 3.9.0;
the per-case receipts remain authoritative for later attempts. The BZip2/zlib
library builds linked into Python/HDF5 were not separately captured for every
historical stage; do not infer those builds from the current packaging snapshot.

## E3: dependency closure and meaning of no_sharing

`ablation_lib.value_worker()` loads
`baseline/evidence/VALUE_BEST_OF_9_50_005/worker.py`. The omitted original worker
and its `PINS.json` are now included byte-for-byte. It loads the matched-ready
Qpatch primitives, constructs K32 value-model code and a K32 QSH1 header; the
support model retains B8. `SOURCE_PIN_BRIDGE.json`, `RELEASE_DEPENDENCIES.json`
and the E3 validation report identify the relevant files and hashes.

The 50 retained `no_sharing` manifests declare `support_bucket_count=8`,
`value_group_count=32`, `q1_sharing=false`. The actual model members include:

| Member | Observed interpretation |
|---|---|
| base_probability.bz2, shared_odds.u32 | retained shared support parameters; support odds are 8 × 7 uint32 |
| value_group.bz2 | retained per-gene K32 group map |
| value_base_k.bz2 | retained 32 × 32 uint16 tail table (2,048 uncompressed bytes) |
| value_cond_k.bz2 | retained 32 × 7 × 32 uint16 table (14,336 uncompressed bytes) |
| value_odds.u32 | retained 32 × 7 uint32 singleton odds (896 bytes) |
| value_q1.bz2 | QSH1 centres remain in the paid header; mode 1 stores per-gene exceptions |

The code sets the exception mask for every gene, replacing the effective shared
singleton probability with each gene's old quantized singleton probability.
It retains tail-group sharing, conditional tables, support sharing and the
shared-centre header. Therefore `no_sharing` means **the confirmed singleton
probability replacement**, not removal of all sharing. The older consolidated
README's “fixed eight-class tail control” was erroneous: the retained expansion
archives establish K32, with B8 referring to support buckets.
The three retained pilot no_sharing archives also report B8/K32; their identities
are recorded in `validation/E3_PILOT_MANIFEST_CHECKS_20260928.json`. The erroneous
eight-class wording is corrected in both pilot/expansion reports and CSV
definition fields. `E3_DESCRIPTION_CORRECTIONS.json` preserves the before/after
hashes; every numeric result and archive hash in those tables is unchanged.
Historical report generators retain their original bytes; the finalization
script applies `tools/correct_e3_descriptions.py` to their published output.

The measured +0.958% archive-size change is tied to this implementation and
50-case panel, including its paid exception/header representation. It does not
measure a hypothetical codec with every form of parameter sharing removed.

## Verification

```text
python tools/verify_evidence_bridge.py
python tools/check_release.py
```

The first checks the portable public bundle, raw receipt hashes, case coverage,
archive mappings and dependency hashes without the original D/E drives. The
second additionally requires the pinned packaging environment. Rebuilding the
archive audit requires the retained historical project and run directories:

```text
python tools/build_evidence_bridge.py --project <historical-project> --runs <historical-run-root> --output <new-empty-directory>
```

For a maintained release checkout, `tools/finalize_evidence_bridge.py --project
<historical-project>` adds the original comparator plan receipts to the default
`provenance/evidence_20260928` bundle, refreshes the restored-source inventory and
seals its hash manifest. It requires the current E3 validation report produced by
`tools/validate_e3_dependencies.py`; it does not run the historical cohort.
