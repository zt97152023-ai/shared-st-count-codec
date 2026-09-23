# Archive and source links

The consolidated package uses directory junctions for large archive payloads.
No raw archive directory was deleted or moved.

| consolidated path | source path | purpose |
| --- | --- | --- |
| `pilot_v1/archives` | `../COUNT-E3-MODULE-CONTRIBUTION-001/pilot_v1` | three-slice pilot outputs and archive payloads |
| `expansion_50/archives` | `../COUNT-E3-MODULE-CONTRIBUTION-002-50/archives` | 50 slices × 5 arms = 250 archive payloads |

The source paths are relative to the parent `baseline/evidence` directory.
The authoritative summary and verification files are copied into this package
so that the package can be reviewed without following the junctions.

Original evidence directories retained:

- `baseline/evidence/COUNT-E3-MODULE-CONTRIBUTION-001`
- `baseline/evidence/COUNT-E3-MODULE-CONTRIBUTION-002-50`
