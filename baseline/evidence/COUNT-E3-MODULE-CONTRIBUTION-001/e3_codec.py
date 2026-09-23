"""Task-local direct E3 pilot codec helpers.

The production source and historical archives are read-only. New no-value and
no-q1-sharing archives use the existing Production Shared runtime primitives,
but a task-local schema/ledger so the ablation semantics remain auditable.
"""
from __future__ import annotations

import base64
import bz2
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
sys.path.insert(0, str(HERE.parent.parent / "evidence" / "COUNT-PRODUCTION-SHARED-ABLATIONS-50-001"))

import ablation_lib as lib


VALUE_MEMBERS = {
    "value_q1.bz2",
    "value_group.bz2",
    "value_base_k.bz2",
    "value_odds.u32",
    "value_cond_k.bz2",
    "values.rans",
    "values.raw.u32",
}


def source_for(sample_id: str):
    for row in lib.read_csv_rows():
        if row["id"] == sample_id:
            return lib.raw_input(row["source_path"])
    raise KeyError(sample_id)


def ledger(path: Path):
    manifest, parts, manifest_bytes = lib.zip_read(path)
    groups = {
        "support_stream": {"support.rans"},
        "value_stream": {"values.rans", "values.raw.u32"},
        "support_model": {"base_probability.bz2", "shared_odds.u32"},
        "value_model_and_group_map": VALUE_MEMBERS - {"values.rans", "values.raw.u32"},
        "graph_index": {"graph.bz2", "support_graph.bz2", "value_graph_tail.bz2"},
        "identity_coordinates_metadata": {"metadata.bz2"},
    }
    categories = {key: sum(len(parts[name]) for name in names if name in parts) for key, names in groups.items()}
    categories["manifest"] = len(manifest_bytes)
    categories["zip_framing"] = path.stat().st_size - sum(len(data) for data in parts.values()) - len(manifest_bytes)
    if sum(categories.values()) != path.stat().st_size:
        raise ValueError("E3 physical ledger does not sum")
    return categories, {name: {"bytes": len(data), "sha256": lib.sha_bytes(data)} for name, data in sorted(parts.items())}


def _base_parts(raw):
    _, _, anchor_parts = lib.read_support_anchor(raw, 6)
    parts = dict(anchor_parts)
    parts["metadata.bz2"] = bz2.compress(raw.metadata_bytes, 9)
    return parts


def _common_info(raw, method: str, value_mode: str):
    x = raw.matrix
    return {
        "schema": "e3-module-ablation-v1",
        "method": method,
        "shape": list(map(int, x.shape)),
        "nnz": int(x.nnz),
        "precision": 12,
        "support_predecessors": 6,
        "support_bucket_count": 8,
        "support_context_kind": "spatial",
        "value_context_predecessors": 6,
        "value_context_kind": "spatial",
        "value_mode": value_mode,
        "canonical_sha256": lib.runtime_io().csr_sha(x),
        "metadata_sha256": lib.sha_bytes(raw.metadata_bytes),
        "value_group_count": 32,
        "value_group_rule": "fixed-log-axis-v1",
    }


def _finish(raw, output: Path, parts: dict[str, bytes], info: dict):
    if output.exists():
        raise FileExistsError(output)
    manifest = dict(info)
    manifest["files"] = {name: {"bytes": len(data), "sha256": lib.sha_bytes(data)} for name, data in sorted(parts.items())}
    payload = dict(parts)
    payload["manifest.json"] = (json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    import zipfile
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(payload.items()):
            zi = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            zi.external_attr = 0o100644 << 16
            archive.writestr(zi, data)
    categories, members = ledger(output)
    return {
        "sample_id": raw.path.stem,
        "status": "success",
        "archive_sha256": lib.sha_path(output),
        "total_archive_bytes": output.stat().st_size,
        "ledger": categories,
        "members": members,
        "manifest": manifest,
    }


def encode_no_value(sample_id: str, output: Path):
    raw = source_for(sample_id)
    parts = _base_parts(raw)
    for name in VALUE_MEMBERS:
        parts.pop(name, None)
    values = np.asarray(raw.matrix.data, dtype="<u4")
    parts["values.raw.u32"] = values.tobytes()
    info = _common_info(raw, "E3 no_value fixed-width positive uint32", "raw_u32")
    info.update({"positive_value_model": False, "value_context_predecessors": 0, "value_context_kind": "none", "raw_positive_value_count": int(values.size)})
    return _finish(raw, output, parts, info)


def encode_no_q1_sharing(sample_id: str, output: Path):
    raw = source_for(sample_id)
    parts = _base_parts(raw)
    for name in VALUE_MEMBERS:
        parts.pop(name, None)
    x = raw.matrix
    io, entropy, shared_model, q_model, qshare, values = lib.value_runtime_width(6)
    graph = np.frombuffer(bz2.decompress(parts["graph.bz2"]), "<i4").reshape(x.shape[0], 6).copy()
    oldq, groups, tail_prob, base_freq, profile = q_model.base(x.indices, x.data, int(x.shape[1]))
    shared = qshare.share(profile["npositive"], profile["nones"], groups)
    all_genes = np.ones(len(oldq), dtype=bool)
    qblob = qshare.encode(shared, groups, oldq, all_genes)
    q_final = qshare.decode(qblob, groups)
    odds, conditional = q_model.conditional(x.indptr, x.indices, x.data, graph, oldq, groups, tail_prob)
    binary, tail, cdf = q_model.tables(q_final, groups, base_freq, odds, conditional)
    value_blob, value_nll, tail_events, remainder_bits = values.encode(
        x.indptr, x.indices, x.data, graph, groups, binary, tail, cdf, True
    )
    parts.update({
        "value_q1.bz2": qblob,
        "value_group.bz2": bz2.compress(np.asarray(groups, np.uint8).tobytes(), 9),
        "value_base_k.bz2": bz2.compress(np.asarray(base_freq, "<u2").tobytes(), 9),
        "value_odds.u32": np.asarray(odds, "<u4").tobytes(),
        "value_cond_k.bz2": bz2.compress(np.asarray(conditional, "<u2").tobytes(), 9),
        "values.rans": value_blob.tobytes(),
    })
    info = _common_info(raw, "E3 no q1-sharing", "shared_tail_independent_q1")
    info["schema"] = "production-shared-ablation-v1"
    info.update({
        "q1_sharing": False,
        "q1_exception_count": int(len(oldq)),
        "value_nll_bits": float(value_nll),
        "tail_events": int(tail_events),
        "remainder_bits": int(remainder_bits),
    })
    return _finish(raw, output, parts, info)


def decode_no_value(package: Path, output: Path):
    """Archive-only decode for the fixed-width no-value arm."""
    manifest, parts, _ = lib.zip_read(package)
    if manifest.get("schema") != "e3-module-ablation-v1" or manifest.get("value_mode") != "raw_u32":
        raise ValueError("not an E3 raw-value archive")
    n, genes = map(int, manifest["shape"])
    B = int(manifest["support_bucket_count"])
    support = lib.support_module(B)
    q0 = np.frombuffer(bz2.decompress(parts["base_probability.bz2"]), "<u2")
    graph = np.frombuffer(bz2.decompress(parts["graph.bz2"]), "<i4").reshape(n, 6).copy()
    odds = np.frombuffer(parts["shared_odds.u32"], "<u4").reshape(B, 7)
    conditional = support.cdf(q0, odds)
    mask = support.decode(np.frombuffer(parts["support.rans"], np.uint8), graph, conditional, q0, n, genes, 6)
    ptr, idx = support.indices_from_support(mask, genes, int(manifest["nnz"]))
    values = np.frombuffer(parts["values.raw.u32"], "<u4").copy()
    if values.size != int(manifest["nnz"]):
        raise ValueError("raw positive value length")
    io = lib.runtime_io()
    matrix = io.from_parts((n, genes), ptr, idx, values)
    metadata = bz2.decompress(parts["metadata.bz2"])
    if io.csr_sha(matrix) != manifest["canonical_sha256"] or lib.sha_bytes(metadata) != manifest["metadata_sha256"]:
        raise ValueError("E3 no-value identity")
    output.mkdir(parents=True, exist_ok=False)
    np.savez(output / "decoded.npz", shape=np.asarray(matrix.shape), indptr=matrix.indptr, indices=matrix.indices, values=matrix.data)
    (output / "metadata.json").write_bytes(metadata)
    return {"archive_only": True, "canonical_sha256": io.csr_sha(matrix), "metadata_sha256": lib.sha_bytes(metadata), "restored_shape": list(matrix.shape)}
