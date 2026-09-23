"""Deterministic Qpatch archive framing and strict member validation."""
from __future__ import annotations

import bz2
import hashlib
import json
import zipfile
from pathlib import Path

from .runtime import load_runtime


EXPECTED = {
    "metadata.bz2", "support.rans", "graph.bz2", "base_probability.bz2",
    "shared_odds.u32", "value_q1.bz2", "value_group.bz2", "value_base_k.bz2",
    "value_odds.u32", "value_cond_k.bz2", "values.rans",
}


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: object) -> bytes:
    io, *_ = load_runtime()
    return io.jbytes(value)


def read(path: str | Path):
    p = Path(path)
    if not p.is_file():
        raise ValueError("package does not exist")
    with zipfile.ZipFile(p) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or "manifest.json" not in names:
            raise ValueError("duplicate or missing archive members")
        try:
            man = json.loads(z.read("manifest.json"))
        except Exception as exc:
            raise ValueError("invalid manifest JSON") from exc
        if (not isinstance(man, dict) or not isinstance(man.get("files"), dict)
                or set(names) != set(man["files"]) | {"manifest.json"}):
            raise ValueError("manifest members mismatch")
        parts = {}
        for name, desc in man["files"].items():
            if name not in EXPECTED or not isinstance(desc, dict):
                raise ValueError("unexpected archive member")
            info = z.getinfo(name)
            if not isinstance(desc.get("bytes"), int) or desc["bytes"] < 0 or desc["bytes"] > 2**31:
                raise ValueError(f"member budget failure: {name}")
            if info.compress_type != zipfile.ZIP_STORED:
                raise ValueError("archive members must be ZIP_STORED")
            if info.file_size != desc["bytes"]:
                raise ValueError(f"member size mismatch: {name}")
            data = z.read(name)
            if len(data) != desc.get("bytes") or sha_bytes(data) != desc.get("sha256"):
                raise ValueError(f"member integrity failure: {name}")
            parts[name] = data
    if man.get("schema") != "qpatch-count-v1" or man.get("method") != "Qpatch12":
        raise ValueError("unsupported package schema/method")
    shape = man.get("shape")
    if (not isinstance(shape, list) or len(shape) != 2 or any(not isinstance(v, int) for v in shape)
            or any(v <= 0 or v > 2_000_000 for v in shape) or shape[0] * shape[1] > 300_000_000):
        raise ValueError("shape budget")
    if not isinstance(man.get("nnz"), int) or not 0 <= man["nnz"] <= min(100_000_000, shape[0] * shape[1]):
        raise ValueError("nnz budget")
    if (man.get("precision") != 12
            or man.get("q1_layout") != "QSH1-mode1-12bit-exceptions-bz2-v1"
            or man.get("support_model") != "frozen-P2-shared-spatial-Q12-v1"
            or man.get("value_layout") != "singleton-K32-uniform-remainder;one-rANS;v1"):
        raise ValueError("unsupported Qpatch12 layout")
    if set(parts) != EXPECTED:
        raise ValueError("incomplete Qpatch12 payload")
    return man, parts


def manifest_bytes(path: str | Path) -> bytes:
    """Return the exact manifest member bytes for an audit hash."""
    with zipfile.ZipFile(Path(path)) as z:
        return z.read("manifest.json")


def write(path: str | Path, parts: dict[str, bytes], info: dict) -> dict:
    p = Path(path)
    if p.exists():
        raise FileExistsError(str(p))
    if set(parts) != EXPECTED:
        raise ValueError("incomplete Qpatch12 payload")
    manifest = dict(info)
    manifest["files"] = {
        name: {"bytes": len(parts[name]), "sha256": sha_bytes(parts[name])}
        for name in sorted(parts)
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(p, "x", compression=zipfile.ZIP_STORED) as z:
        payload = dict(parts)
        payload["manifest.json"] = json_bytes(manifest)
        for name in sorted(payload):
            zi = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            zi.external_attr = 0o100644 << 16
            z.writestr(zi, payload[name])
    return manifest


def cdf_sha(parts: dict[str, bytes]) -> str:
    """Rebuild the value CDF from paid members, with no source access."""
    io, _, _, q_model, qshare, _ = load_runtime()
    import numpy as np
    groups = np.frombuffer(bz2.decompress(parts["value_group.bz2"]), np.uint8)
    q = qshare.decode(parts["value_q1.bz2"], groups)
    base = np.frombuffer(bz2.decompress(parts["value_base_k.bz2"]), "<u2").reshape(8, 32)
    odds = np.frombuffer(parts["value_odds.u32"], "<u4").reshape(8, 7)
    cond = np.frombuffer(bz2.decompress(parts["value_cond_k.bz2"]), "<u2").reshape(8, 7, 32)
    binary, tail, cdf = q_model.tables(q, groups, base, odds, cond)
    return sha_bytes(binary.tobytes() + tail.tobytes() + cdf.tobytes())
