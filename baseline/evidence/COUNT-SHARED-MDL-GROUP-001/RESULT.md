# Shared MDL singleton grouping: measured results

Three exposed complete canonical count matrices. Original spatial/support/tail/odds members stay byte-identical. Every new candidate has real rANS and fresh archive-only exact decode. Candidate selection uses total paid archive bytes, not NLL.

| Method | Complete bytes | Saving vs original Shared | No slice worse |
|---|---:|---:|---|
| GLOBAL_SHARED | 18,018,652 | -2.8666% | False |
| PER_GENE | 17,510,904 | +0.0320% | False |
| FIXED_SHARED | 17,516,517 | +0.0000% | True |
| ADAPTIVE_MDL | 17,409,081 | +0.6133% | False |
| ADAPTIVE_WITHOUT_EXCEPTIONS | 17,409,081 | +0.6133% | False |

| Slice | Method | K | Exceptions enabled | Saved bytes | Model saved B | Value stream saved B |
|---|---|---:|---|---:|---:|---:|
| NCBI692 | GLOBAL_SHARED | 1 | False | -16,680 | 2 | -16,553 |
| NCBI692 | PER_GENE | 36601 | False | -43,214 | -51,368 | 8,285 |
| NCBI692 | FIXED_SHARED | 0 | False | 0 | 0 | 0 |
| NCBI692 | ADAPTIVE_MDL | 4 | False | -4,398 | -9,479 | 5,207 |
| NCBI692 | ADAPTIVE_WITHOUT_EXCEPTIONS | 4 | False | -4,398 | -9,479 | 5,207 |
| NCBI715 | GLOBAL_SHARED | 1 | False | -220,019 | -3 | -219,887 |
| NCBI715 | PER_GENE | 32285 | False | 4,129 | -53,331 | 57,591 |
| NCBI715 | FIXED_SHARED | 0 | False | 0 | 0 | 0 |
| NCBI715 | ADAPTIVE_MDL | 16 | False | 37,632 | -14,663 | 52,423 |
| NCBI715 | ADAPTIVE_WITHOUT_EXCEPTIONS | 16 | False | 37,632 | -14,663 | 52,423 |
| NCBI618 | GLOBAL_SHARED | 1 | False | -265,436 | -4 | -265,303 |
| NCBI618 | PER_GENE | 31053 | False | 44,698 | -47,657 | 92,486 |
| NCBI618 | FIXED_SHARED | 0 | False | 0 | 0 | 0 |
| NCBI618 | ADAPTIVE_MDL | 16 | False | 74,202 | -13,009 | 87,339 |
| NCBI618 | ADAPTIVE_WITHOUT_EXCEPTIONS | 16 | False | 74,202 | -13,009 | 87,339 |

Predeclared primary practical gate: **False** (>=1% pooled saving and no slice larger).

ADAPTIVE_MDL selects the shortest actual archive among12 frozen candidates per slice. All candidate encoding and fitting time is counted as encoder search cost; only the selected deployed archive is stored in the logical codec comparison. Experiment evidence retains all candidates. This is a bounded implemented selection rule, not a free oracle, global MDL optimum or held-out validation.
The unconditioned Bernoulli Lloyd proxy generates clusters; integer contextual probabilities and real rANS are used for actual selection. Singleton labels and tail labels are separate. The inherited safe>12-bit exception heuristic is not the true marginal cost of an exception in this new compressed schema (exceptions use uint16); only complete archive selection establishes net value.
Without-exceptions best is reported separately; a with-exceptions gain cannot all be attributed to grouping. No claim of superiority over existing Qpatch12 is made. GLOBAL and adaptiveK1/no-exceptions are redundant distribution controls; PER_GENE pays an identity mapping and is a conservative serialization control, not an optimal per-gene format.
Complete total includes support, positive stream, group mapping, probability parameters, graph, metadata and framing. bpc/bpnz in SUMMARY.csv use full archive bytes; support stays fixed. Dtype/shape/CSR values and exact metadata are checked against original canonical sources. These are three biological slices, not45 independent samples.
Independent final verification and source/byte ledger audit are required for scoped acceptance. Failures and attempts must be disclosed from main logs rather than silently excluded. No image, neural training or protected148 data is used.

## Observed interpretation

All45 planned full-data restoration checks completed with no main failure, in563.531seconds. The parent emitted scheduled120-second traceback diagnostics while waiting for children; these were observer snapshots, not process timeout failures. Runtime/source pins remain frozen.

Selected K values are4 for kidney and16 for brain/liver; all selected candidates disable exceptions. Thus this panel's best finite-set gain is achieved without the inherited exception heuristic. Pooled value streams shrink144,969B; probability/mapping blobs grow37,151B, and framing grows382B, leaving107,436B net saving. Kidney stream improvement5207B is outweighed by9479B extra model/mapping and126B framing. This is a concrete model/data trade-off, not a hypothetical entropy gain.

The pooled0.6133percent gain is below the predeclared1percent threshold and kidney is4398B larger. Brain saves37632B; liver saves74202B. Therefore adaptive singleton grouping shows a limited, distribution-dependent opportunity but fails this iteration's practical gate. It is not added to the default Shared codec. The candidate family, map serialization and unconditioned fitting proxy can all limit the result; this does not refute MDL grouping in general. No tuning or automatic new iteration was performed.

Candidate-level numeric ledger is ALL_RUNS.csv; selected-method per-slice ledger is SUMMARY.csv. Complete grouping sizes and diagnostics remain in main_v1/RESULTS.json and individual RUN.json files. Encoder search pays all12 candidate fit/encode processes per sample; independent evaluation decoding time is not described as deployed encoder latency.
