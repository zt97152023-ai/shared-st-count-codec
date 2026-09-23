"""Strict archive reader and mutually exclusive physical fee ledger."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

S0_MEMBERS = {"metadata.bz2", "values.pco", "probability.bz2", "support.rans"}
SHARED_MEMBERS = {"metadata.bz2", "support.rans", "graph.bz2", "base_probability.bz2", "shared_odds.u32", "value_q1.bz2", "value_group.bz2", "value_base_k.bz2", "value_odds.u32", "value_cond_k.bz2", "values.rans"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(path: str | Path):
    p = Path(path)
    with zipfile.ZipFile(p) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or "manifest.json" not in names:
            raise ValueError("duplicate or missing archive member")
        manifest_bytes = z.read("manifest.json")
        try:
            man = json.loads(manifest_bytes)
        except Exception as exc:
            raise ValueError("invalid manifest") from exc
        schema = man.get("schema")
        if schema == "count-e1-v1":
            entries = man.get("files")
            if not isinstance(entries, dict):
                raise ValueError("invalid S0 file ledger")
            expected = set(entries)
            expected_names = {"manifest.json"} | expected
            if expected != S0_MEMBERS:
                raise ValueError("unsupported S0 member ledger")
            if man.get("method") != "S0_gene" or man.get("precision") != 12 or man.get("value_codec") != "pcodec1.0.3-level8":
                raise ValueError("unsupported formal S0 metadata")
            if set(names) != expected_names:
                raise ValueError("S0 member mismatch")
            parts = {}
            for name, entry in entries.items():
                info = z.getinfo(name)
                if info.compress_type != zipfile.ZIP_STORED or info.file_size > 2**31:
                    raise ValueError("invalid S0 member storage/budget")
                data = z.read(name)
                if len(data) != entry.get("bytes") or sha(data) != entry.get("sha256"):
                    raise ValueError("S0 member integrity")
                parts[name] = data
            return man, parts, manifest_bytes, "s0"
        if schema == "qpatch-count-v1":
            files = man.get("files")
            if not isinstance(files, dict) or set(names) != set(files) | {"manifest.json"}:
                raise ValueError("Shared-only member mismatch")
            if man.get("method") != "Shared-only" or man.get("precision") != 12 or man.get("q1_layout") != "QSH1-mode0-shared-v1":
                raise ValueError("unsupported Shared-only layout")
            if man.get("support_model") != "frozen-P2-shared-spatial-Q12-v1" or man.get("value_layout") != "singleton-K32-uniform-remainder;one-rANS;v1":
                raise ValueError("unsupported Shared-only model")
            if set(files) != SHARED_MEMBERS:
                raise ValueError("incomplete Shared-only payload")
            parts = {}
            for name, desc in files.items():
                info = z.getinfo(name)
                if not isinstance(desc, dict) or not isinstance(desc.get("bytes"), int) or desc["bytes"] < 0 or desc["bytes"] > 2**31 or info.compress_type != zipfile.ZIP_STORED or info.file_size != desc["bytes"]:
                    raise ValueError("member budget/storage mismatch")
                data = z.read(name)
                if sha(data) != desc.get("sha256"):
                    raise ValueError(f"member integrity: {name}")
                parts[name] = data
            shape = man.get("shape")
            if not isinstance(shape, list) or len(shape) != 2 or any(not isinstance(v, int) or v <= 0 or v > 2_000_000 for v in shape) or shape[0] * shape[1] > 300_000_000:
                raise ValueError("shape budget")
            if not isinstance(man.get("nnz"), int) or not 0 <= man["nnz"] <= min(100_000_000, shape[0] * shape[1]):
                raise ValueError("nnz budget")
            return man, parts, manifest_bytes, "shared-only"
    raise ValueError("unsupported archive schema")


def ledger(man: dict, parts: dict, manifest_bytes: bytes, package: Path) -> dict:
    payload = sum(len(x) for x in parts.values())
    total = package.stat().st_size
    mode = "s0" if man.get("method") == "S0_gene" else "shared-only"
    categories = {
        "payload_streams": {"s0": {"support.rans", "values.pco"}, "shared-only": {"support.rans", "values.rans"}}[mode],
        "paid_model_members": {"s0": {"probability.bz2"}, "shared-only": {"base_probability.bz2", "shared_odds.u32", "value_q1.bz2", "value_group.bz2", "value_base_k.bz2", "value_odds.u32", "value_cond_k.bz2"}}[mode],
        "identity_coordinates": {"metadata.bz2"}, "graph_index": {"graph.bz2"},
    }
    categories_bytes = {k: sum(len(parts[x]) for x in names if x in parts) for k, names in categories.items()}
    categories_bytes["manifest"] = len(manifest_bytes)
    categories_bytes["zip_framing"] = total - payload - len(manifest_bytes)
    if sum(categories_bytes.values()) != total:
        raise ValueError("physical fee ledger does not sum to archive bytes")
    return {"members": {k: {"bytes": len(v), "sha256": sha(v)} for k, v in sorted(parts.items())},
            "payload_bytes_excluding_manifest": payload, "manifest_bytes": len(manifest_bytes),
            "zip_framing_bytes": categories_bytes["zip_framing"], "categories": categories_bytes,
            "total_package_bytes": total,
            "package_sha256": sha(package.read_bytes()), "manifest_sha256": sha(manifest_bytes)}


def _write_shared(path, parts, info):
    p = Path(path)
    if p.exists():
        raise FileExistsError(str(p))
    if set(parts) != SHARED_MEMBERS:
        raise ValueError("incomplete Shared-only payload")
    manifest = dict(info)
    manifest["files"] = {k: {"bytes": len(v), "sha256": sha(v)} for k, v in sorted(parts.items())}
    p.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(p, "x", compression=zipfile.ZIP_STORED) as z:
        payload = {**parts, "manifest.json": (json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode()}
        for name, data in sorted(payload.items()):
            zi = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)); zi.external_attr = 0o100644 << 16
            z.writestr(zi, data)
    return manifest


write_shared = _write_shared
