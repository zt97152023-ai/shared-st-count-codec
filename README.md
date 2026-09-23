# Shared: lossless spatial transcriptomic count compression

Shared is a statistical codec for spatial transcriptomic count matrices. It separates support from positive values, shares selected probability parameters across genes, and uses a stored causal spatial-predecessor graph. Compression is evaluated using the complete physical archive size.

This repository archives the implementation corresponding to the **support B8 / value K32** HEST1000 configuration. It does not require a pretrained neural checkpoint. Historical K8 and experimental variants are retained for provenance and must not be substituted for this configuration.

## Start here

- [Version boundaries and commands (中文)](START_HERE.md)
- [Method-to-source map (中文)](SOURCE_MAP.md)
- [Environment and release notes](RELEASE_README.md)
- [Data availability and accessions](data/DATA_AVAILABILITY.md)
- [Code provenance](provenance/CODE_AVAILABILITY.md)
- [License status](licenses/LICENSE_STATUS.md)

The original research overview is preserved without changes in [docs/HISTORICAL_PROJECT_README.md](docs/HISTORICAL_PROJECT_README.md). It contains historical states and links to files outside this source release; use the guides above for the present package.

## Environment

The recorded environment is Windows, Python 3.11.5, with fixed NumPy, SciPy, h5py, Numba and llvmlite versions. The supplied environment recipe has not yet been validated by a clean installation on every supported platform.

```sh
conda env create -f environment/environment.yml
conda activate shared-count
python tools/check_release.py
```

Run the commands from the repository root. No GPU is required for this statistical codec.

## Encode, independently decode, and verify

Replace the input filename and use new output paths:

```sh
python -B -X utf8 baseline/evidence/COUNT-HEST-SHARED-K32-001/worker.py encode INPUT.h5ad OUTPUT.cnt --K 32 --report encode.json
python -B -X utf8 baseline/evidence/COUNT-HEST-SHARED-K32-001/worker.py decode OUTPUT.cnt DECODED_DIRECTORY --report decode.json
python -B -X utf8 baseline/evidence/COUNT-HEST-SHARED-K32-001/worker.py verify INPUT.h5ad DECODED_DIRECTORY --report verify.json
```

**Keep `--K 32`: the historical worker defaults to K8.** Decode obtains the value-group configuration from the archive. Do not use `--shuffle` for the production configuration.

The decoder uses the archive and the specified software environment; it does not require the source H5AD. Only verification reads the input again.

The recovery contract covers canonical integer counts, complete gene/observation identities and order, spatial coordinates, and contract metadata. It does not reconstruct the original count-storage dtype, original sparse storage bytes, all H5AD annotations, or histology images.

## Validation and evidence boundaries

- The source manifest tracks 233 byte-preserved original source/configuration/document files. The relocated historical README retains its original hash.
- Existing K8/K32 synthetic tests used real encoding, separate-process archive-only decoding, and exact canonical recovery. Records are retained under `validation/`.
- Source packaging and publication did not rerun the full HEST cohort.
- The HEST1000 configuration was selected using a development panel contained in the cohort. It is not an independent held-out test or evidence of universal K32 optimality.
- Historical batch scripts may contain original machine paths and resource settings. Use the single-sample commands above; do not run old experiment schedulers as installation commands.

Optional synthetic smoke test, using a new empty output directory:

```sh
python tools/smoke_test.py --output NEW_EMPTY_SMOKE_DIRECTORY
```

## Data and licensing

Raw H5AD matrices, count archives, WSI, pretrained weights, Python interpreters and dependency binaries are not distributed here. The `data/` directory records provider accessions, pinned HEST revision and historical source hashes. Obtain data from the provider under its access conditions.

**The original Shared code license and copyright holder are pending. Public source availability is not an MIT/BSD or other open-source license grant.** Third-party license notices are retained separately. No publication DOI or author list has been invented.
