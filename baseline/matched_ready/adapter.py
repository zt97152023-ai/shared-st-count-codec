"""Shared raw adapter: use the already reviewed execution-ready contract."""
from __future__ import annotations

import hashlib
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
EXECUTION_READY = BASE / "execution_ready"
_PINS = {
    EXECUTION_READY / "adapter.py": "d387b6282edd7b48fddfddf1aec2904f6290addf44e54d1a30c0117b9dd2174f",
    EXECUTION_READY / "runtime.py": "dfae8a5e8dd23e0025e59ada951e2d8907e58853c18b0358cf78f0b2858d81ed",
}
for _path, _expected in _PINS.items():
    if hashlib.sha256(_path.read_bytes()).hexdigest() != _expected:
        raise RuntimeError(f"execution_ready adapter pin mismatch: {_path}")

from baseline.execution_ready.adapter import (  # noqa: E402
    CanonicalInput,
    _validate_metadata,
    read_h5ad,
)


def validate_metadata(metadata: dict, shape: tuple[int, int]) -> None:
    from .runtime import load_qpatch_runtime
    io, *_ = load_qpatch_runtime()
    return _validate_metadata(io, metadata, shape)

__all__ = ["CanonicalInput", "validate_metadata", "read_h5ad"]
