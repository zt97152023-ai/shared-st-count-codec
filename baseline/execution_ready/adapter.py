"""Raw H5AD adapter using the frozen io047 canonicalization contract."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .runtime import load_runtime


@dataclass(frozen=True)
class CanonicalInput:
    path: Path
    matrix: object
    metadata: dict
    metadata_bytes: bytes
    encoding: str

    @property
    def shape(self):
        return tuple(int(v) for v in self.matrix.shape)


def _validate_metadata(io, metadata: dict, shape: tuple[int, int]) -> None:
    required = {
        "schema", "spot_ids", "gene_ids", "coordinates_shape",
        "coordinates_dtype", "coordinates_base64",
    }
    if set(metadata) != required or metadata.get("schema") != "047-exact-metadata-v1":
        raise ValueError("missing or unexpected frozen metadata fields")
    if len(metadata["spot_ids"]) != shape[0] or len(metadata["gene_ids"]) != shape[1]:
        raise ValueError("metadata labels disagree with matrix shape")
    try:
        dtype = np.dtype(metadata["coordinates_dtype"])
        raw = base64.b64decode(metadata["coordinates_base64"], validate=True)
        coords = np.frombuffer(raw, dtype=dtype).reshape(tuple(metadata["coordinates_shape"]))
    except Exception as exc:
        raise ValueError("invalid coordinate metadata") from exc
    if coords.ndim != 2 or coords.shape[0] != shape[0] or coords.shape[1] != 2:
        raise ValueError("coordinates must be finite n-by-2 values")
    if coords.dtype.kind not in "iuf" or not np.isfinite(coords).all():
        raise ValueError("coordinates must be finite numeric values")


def read_h5ad(path: str | Path) -> CanonicalInput:
    """Read one H5AD through io047 and explicitly reject incomplete metadata."""
    p = Path(path)
    if not p.is_file() or p.suffix.lower() != ".h5ad":
        raise ValueError("input must be an existing .h5ad file")
    io, *_ = load_runtime()
    try:
        matrix, encoding = io.read_x(p, canonical=True)
        metadata = io.metadata(p, matrix.shape)
    except (KeyError, OSError, ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"invalid H5AD input: {exc}") from exc
    _validate_metadata(io, metadata, tuple(matrix.shape))
    return CanonicalInput(p, matrix, metadata, io.jbytes(metadata), encoding)
