"""Private, hash-pinned loaders for the frozen E1/Qpatch implementations."""
from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
E1 = BASE / "evidence" / "COUNT-E1-100" / "runtime"
QPATCH = BASE / "qpatchcodec"
SHARED = BASE / "sharedcodec"

FROZEN_SHA256 = {
    E1 / "io047.py": "594bd107f2bacd4636778b5aa5609b6139ebe319124909126ace82ff3b71124f",
    E1 / "entropy.py": "17931146bdc79fbcb5ea0ab2dbb17acd833c8d32f52df9325d5dbffd712bc4c6",
    E1 / "codec.py": "0cb5669fe8b5bd0fe5439d84fb85f7a00fd9083a3e9a6ea3285497d91e8590bb",
    QPATCH / "frozen_runtime" / "entropy.py": "17931146bdc79fbcb5ea0ab2dbb17acd833c8d32f52df9325d5dbffd712bc4c6",
    QPATCH / "model.py": "7abd069a9d924d3c7f2e4b3e4239be5f117e9c6846a4de03ba5c35ba882b31c4",
    QPATCH / "values.py": "a0cbe78acc76fe61c2a227315b4d7d1823add785ff11008af596e2fceeb39532",
    QPATCH / "qshare_model.py": "afaf2542ea27554509bd3ed8ab5a78b41ddc6cc670581dba34c56aec12bb82ce",
    SHARED / "model.py": "1b4929f82d80ec5762e26f9fc13a13c330bbe2908cebe6f3e0ff242eacc9c458",
}


def _load(name: str, path: Path, aliases: dict[str, object] | None = None):
    expected = FROZEN_SHA256.get(path)
    if expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise RuntimeError(f"frozen source hash mismatch: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    previous = {}
    for alias, value in (aliases or {}).items():
        if alias in sys.modules:
            previous[alias] = sys.modules[alias]
        sys.modules[alias] = value
    try:
        spec.loader.exec_module(module)
    finally:
        # Numba cache records the import name of the injected dependency in
        # the compiled function environment.  Removing that alias after load
        # makes a fresh worker fail during cache deserialization with
        # ``ModuleNotFoundError: entropy``/``model`` and can escalate to a
        # Windows access violation while recompiling.  Keep the exact loaded
        # alias alive for the worker lifetime.  This does not alter any frozen
        # codec source, parameters, or serialized stream; it only makes the
        # dynamic loader's runtime namespace stable across encode/decode.
        for alias, value in (aliases or {}).items():
            sys.modules[alias] = value
    return module


def load_qpatch_runtime():
    io = _load("matched_io047", E1 / "io047.py")
    entropy = _load("matched_q_entropy", QPATCH / "frozen_runtime" / "entropy.py")
    q_model = _load("matched_q_model", QPATCH / "model.py")
    qshare = _load("matched_qshare", QPATCH / "qshare_model.py")
    shared = _load("matched_shared_model", SHARED / "model.py", {"entropy": entropy})
    values = _load("matched_q_values", QPATCH / "values.py", {"model": q_model})
    # The cached Numba environment records this module under its historical
    # import name as well; keep that name stable for fresh workers.
    sys.modules["values"] = values
    return io, entropy, shared, q_model, qshare, values


def load_s0_codec():
    """Load formal E1 codec with only its import bindings replaced."""
    # Seed the import cache from the active matched-ready venv before the
    # frozen codec appends its historical fallback path.
    import importlib
    import pcodec
    native = Path(importlib.import_module("pcodec.pcodec").__file__).resolve()
    if Path(sys.prefix).resolve() not in native.parents:
        raise RuntimeError(f"pcodec resolved outside matched-ready venv: {native}")
    if hashlib.sha256(native.read_bytes()).hexdigest() != "a2195aa87e4f4ef05374315debf568a64b08a53e6f164351526d9bae5c15aa78":
        raise RuntimeError("pcodec native binary hash mismatch")
    io = _load("matched_s0_io047", E1 / "io047.py")
    entropy = _load("matched_s0_entropy", E1 / "entropy.py")
    aliases = {"io047": io, "entropy": entropy}
    codec = _load("matched_s0_codec", E1 / "codec.py", aliases)
    # The source's historical append is retained for provenance, but cannot
    # affect resolution because pcodec was preloaded from this venv.
    sys.path[:] = [x for x in sys.path if "stcompressbench_continuation" not in str(x).lower()]
    return codec
