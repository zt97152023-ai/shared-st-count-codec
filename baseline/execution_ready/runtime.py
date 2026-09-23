"""Load frozen runtime modules under private names.

The repository contains several modules called ``model`` and ``entropy``.  This
loader deliberately gives each frozen implementation a private module name so
one codec's module cache cannot silently affect another codec.
"""
from __future__ import annotations

import importlib.util
import hashlib
import sys
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
FROZEN_E1 = BASE / "evidence" / "COUNT-E1-100" / "runtime"
QPATCH = BASE / "qpatchcodec"
SHARED = BASE / "sharedcodec"

FROZEN_SHA256 = {
    FROZEN_E1 / "io047.py": "594bd107f2bacd4636778b5aa5609b6139ebe319124909126ace82ff3b71124f",
    QPATCH / "frozen_runtime" / "entropy.py": "17931146bdc79fbcb5ea0ab2dbb17acd833c8d32f52df9325d5dbffd712bc4c6",
    QPATCH / "model.py": "7abd069a9d924d3c7f2e4b3e4239be5f117e9c6846a4de03ba5c35ba882b31c4",
    QPATCH / "values.py": "a0cbe78acc76fe61c2a227315b4d7d1823add785ff11008af596e2fceeb39532",
    QPATCH / "qshare_model.py": "afaf2542ea27554509bd3ed8ab5a78b41ddc6cc670581dba34c56aec12bb82ce",
    SHARED / "model.py": "1b4929f82d80ec5762e26f9fc13a13c330bbe2908cebe6f3e0ff242eacc9c458",
}


def _load(name: str, path: Path, aliases: dict[str, object] | None = None):
    expected = FROZEN_SHA256.get(path)
    if expected:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"frozen source hash mismatch: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load frozen module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    old: dict[str, object] = {}
    if aliases:
        for alias, value in aliases.items():
            if alias in sys.modules:
                old[alias] = sys.modules[alias]
            sys.modules[alias] = value
    try:
        spec.loader.exec_module(module)
    finally:
        for alias in aliases or {}:
            if alias in old:
                sys.modules[alias] = old[alias]
            else:
                sys.modules.pop(alias, None)
    return module


def load_runtime():
    """Return all frozen modules needed by preparation and archive decoding."""
    io = _load("er_io047", FROZEN_E1 / "io047.py")
    entropy = _load("er_entropy", QPATCH / "frozen_runtime" / "entropy.py")
    shared_entropy = entropy
    shared_model = _load("er_shared_model", SHARED / "model.py", {"entropy": shared_entropy})
    q_model = _load("er_q_model", QPATCH / "model.py")
    qshare = _load("er_qshare_model", QPATCH / "qshare_model.py")
    q_values = _load("er_q_values", QPATCH / "values.py", {"model": q_model})
    return io, entropy, shared_model, q_model, qshare, q_values
