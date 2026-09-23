"""Isolated support-predecessor experiment over immutable K32 value anchors."""
from __future__ import annotations

import base64
import bz2
import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
import support_dynamic as support

VALUE_MEMBER_NAMES = {
    "value_q1.bz2",
    "value_group.bz2",
    "value_base_k.bz2",
    "value_odds.u32",
    "value_cond_k.bz2",
    "values.rans",
}
BASE_MEMBER_NAMES = VALUE_MEMBER_NAMES | {
    "metadata.bz2", "support.rans", "graph.bz2", "base_probability.bz2", "shared_odds.u32"
}


def sha(data):
    if isinstance(data, Path):
        h = hashlib.sha256()
        with data.open("rb") as handle:
            for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()
    return hashlib.sha256(data).hexdigest()


def value_worker():
    path = ROOT / "baseline" / "evidence" / "VALUE_BEST_OF_9_50_005" / "worker.py"
    spec = importlib.util.spec_from_file_location("support_calibration_value_worker", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_archive(path):
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or "manifest.json" not in names:
            raise ValueError("archive member set")
        manifest_bytes = archive.read("manifest.json")
        manifest = json.loads(manifest_bytes)
        files = manifest.get("files")
        if not isinstance(files, dict) or set(names) != set(files) | {"manifest.json"}:
            raise ValueError("manifest file set")
        if set(files) not in (BASE_MEMBER_NAMES, BASE_MEMBER_NAMES | {"support_graph.bz2"}):
            raise ValueError("unsupported member set")
        parts = {}
        for name, record in files.items():
            info = archive.getinfo(name)
            data = archive.read(name)
            if info.compress_type != zipfile.ZIP_STORED or len(data) != record.get("bytes") or sha(data) != record.get("sha256"):
                raise ValueError("member integrity: " + name)
            parts[name] = data
    return manifest, parts, manifest_bytes


def write_archive(path, parts, info):
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    manifest = dict(info)
    manifest["files"] = {name: {"bytes": len(data), "sha256": sha(data)} for name, data in sorted(parts.items())}
    payload = dict(parts)
    payload["manifest.json"] = (json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(payload.items()):
            zi = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            zi.external_attr = 0o100644 << 16
            archive.writestr(zi, data)
    return manifest


def coordinates(metadata):
    return np.frombuffer(
        base64.b64decode(metadata["coordinates_base64"], validate=True),
        np.dtype(metadata["coordinates_dtype"]),
    ).reshape(tuple(metadata["coordinates_shape"]))


def validate_graph(graph, width):
    if graph.dtype != np.int32 or graph.ndim != 2 or graph.shape[1] != width:
        raise ValueError("graph dtype/shape")
    for row, values in enumerate(graph):
        valid = min(row, width)
        if np.any(values[:valid] < 0) or np.any(values[:valid] >= row) or len(set(map(int, values[:valid]))) != valid:
            raise ValueError("noncausal graph")
        if np.any(values[valid:] != -1):
            raise ValueError("graph padding")


def spatial_graph(coords, width, production_graph):
    nrows = len(coords)
    if width == 0:
        return np.empty((nrows, 0), np.int32)
    if width <= 6:
        result = np.asarray(production_graph[:, :width], dtype=np.int32).copy()
        validate_graph(result, width)
        return result
    result = np.full((nrows, width), -1, np.int32)
    work = coords.astype(np.float64, copy=False)
    for row in range(nrows):
        if row == 0:
            continue
        distance = np.sum((work[:row] - work[row]) ** 2, axis=1)
        order = np.lexsort((np.arange(row), distance))[:width]
        result[row, : len(order)] = order.astype(np.int32)
    validate_graph(result, width)
    if not np.array_equal(result[:, :6], production_graph):
        raise ValueError("computed graph does not preserve frozen nearest-six prefix")
    return result


def row_graph(nrows, width):
    result = np.full((nrows, width), -1, np.int32)
    for row in range(nrows):
        values = np.arange(max(0, row - width), row, dtype=np.int32)
        result[row, : len(values)] = values
    validate_graph(result, width)
    return result


def support_graph_for(kind, width, metadata, production_graph):
    if kind == "spatial":
        return spatial_graph(coordinates(metadata), width, production_graph)
    if kind == "row":
        return row_graph(len(production_graph), width)
    raise ValueError(kind)


def value_tables(parts, genes):
    worker = value_worker()
    io, entropy, shared_model, value_model, qshare, values = worker.load(32)
    groups = np.frombuffer(bz2.decompress(parts["value_group.bz2"]), np.uint8)
    if groups.shape != (genes,) or np.any(groups >= 32):
        raise ValueError("value groups")
    q = qshare.decode(parts["value_q1.bz2"], groups)
    base = np.frombuffer(bz2.decompress(parts["value_base_k.bz2"]), "<u2").reshape(32, 32)
    odds = np.frombuffer(parts["value_odds.u32"], "<u4").reshape(32, 7)
    conditional = np.frombuffer(bz2.decompress(parts["value_cond_k.bz2"]), "<u2").reshape(32, 7, 32)
    binary, tail, cdf = value_model.tables(q, groups, base, odds, conditional)
    return (io, values), groups, (binary, tail, cdf)


def encode(source, anchor, output, kind, width):
    from baseline.matched_ready.adapter import read_h5ad

    raw = read_h5ad(source)
    x = raw.matrix
    nrows, genes = map(int, x.shape)
    anchor_manifest, anchor_parts, _ = read_archive(anchor)
    if anchor_manifest.get("value_group_count") != 32 or anchor_manifest.get("value_group_rule") != "fixed-log-axis-v1":
        raise ValueError("anchor is not experimental K32")
    if tuple(anchor_manifest["shape"]) != x.shape or int(anchor_manifest["nnz"]) != int(x.nnz):
        raise ValueError("anchor shape/nnz")
    runtime, _, _ = value_tables(anchor_parts, genes)
    io, _ = runtime
    if io.csr_sha(x) != anchor_manifest["canonical_sha256"] or sha(raw.metadata_bytes) != anchor_manifest["metadata_sha256"]:
        raise ValueError("source/anchor identity")
    production_graph = np.frombuffer(bz2.decompress(anchor_parts["graph.bz2"]), "<i4").reshape(nrows, 6).copy()
    validate_graph(production_graph, 6)
    graph = support_graph_for(kind, width, raw.metadata, production_graph)
    mask = support.packed_support(x.indptr, x.indices, nrows, genes)
    q0 = np.frombuffer(bz2.decompress(anchor_parts["base_probability.bz2"]), "<u2")
    if q0.shape != (genes,):
        raise ValueError("q0")
    odds, conditional, diagnostics = support.fit(mask, graph, q0, width)
    support_blob, support_nll = support.encode(mask, graph, conditional, q0, width)

    parts = dict(anchor_parts)
    parts["support.rans"] = support_blob.tobytes()
    parts["shared_odds.u32"] = odds.astype("<u4", copy=False).tobytes()
    parts.pop("support_graph.bz2", None)
    if kind == "spatial" and width <= 6:
        graph_mode = "value_graph_prefix"
    elif kind == "spatial":
        graph_mode = "incremental_tail"
        parts["support_graph.bz2"] = bz2.compress(graph[:, 6:].astype("<i4").tobytes(), 9)
    else:
        graph_mode = "row_generated"
    if width == 0:
        parts["shared_odds.u32"] = b""
    info = {key: value for key, value in anchor_manifest.items() if key != "files"}
    info.update(
        schema="support-predecessor-calibration-v1",
        support_context_kind=kind,
        support_predecessors=int(width),
        support_context_values=int(width + 1),
        support_graph_mode=graph_mode,
        support_graph_member=("graph.bz2" if graph_mode == "value_graph_prefix" else
                              ("support_graph.bz2" if graph_mode == "incremental_tail" else None)),
        support_odds_implicit_unity=bool(width == 0),
        support_warmup_rows=int(width),
        support_model="dynamic-width-P2-shared-spatial-Q12-v1",
        value_anchor_archive_sha256=sha(Path(anchor)),
    )
    write_archive(output, parts, info)
    for name in VALUE_MEMBER_NAMES | {"graph.bz2", "base_probability.bz2", "metadata.bz2"}:
        if parts[name] != anchor_parts[name]:
            raise ValueError("fixed member drift: " + name)
    return {
        "archive_sha256": sha(Path(output)),
        "total_archive_bytes": Path(output).stat().st_size,
        "support_stream_bytes": len(parts["support.rans"]),
        "support_model_bytes": len(parts["base_probability.bz2"]) + len(parts["shared_odds.u32"]),
        "support_graph_bytes": len(parts.get("support_graph.bz2", b"")),
        "fixed_value_graph_bytes": len(parts["graph.bz2"]),
        "support_nll_bits": float(support_nll),
        "diagnostics": diagnostics,
        "m6_anchor_support_stream_identical": bool(width == 6 and kind == "spatial" and parts["support.rans"] == anchor_parts["support.rans"]),
        "m6_anchor_support_model_identical": bool(width == 6 and kind == "spatial" and parts["shared_odds.u32"] == anchor_parts["shared_odds.u32"]),
    }


def graph_from_manifest(manifest, parts, nrows):
    width = int(manifest["support_predecessors"])
    mode = manifest.get("support_graph_mode")
    production = np.frombuffer(bz2.decompress(parts["graph.bz2"]), "<i4").reshape(nrows, 6).copy()
    validate_graph(production, 6)
    if mode == "value_graph_prefix" and width <= 6:
        graph = production[:, :width].copy()
    elif mode == "incremental_tail" and width > 6:
        tail = np.frombuffer(bz2.decompress(parts["support_graph.bz2"]), "<i4")
        if tail.size != nrows * (width - 6):
            raise ValueError("support graph tail bytes")
        graph = np.concatenate([production, tail.reshape(nrows, width - 6)], axis=1)
    elif mode == "row_generated" and width > 0:
        graph = row_graph(nrows, width)
    else:
        raise ValueError("support graph mode")
    validate_graph(graph, width)
    return graph


def decode(package, output):
    manifest, parts, _ = read_archive(package)
    if manifest.get("schema") != "support-predecessor-calibration-v1" or manifest.get("value_group_count") != 32:
        raise ValueError("schema/K")
    nrows, genes = map(int, manifest["shape"])
    nnz = int(manifest["nnz"])
    width = int(manifest["support_predecessors"])
    graph = graph_from_manifest(manifest, parts, nrows)
    q0 = np.frombuffer(bz2.decompress(parts["base_probability.bz2"]), "<u2")
    if width == 0:
        if parts["shared_odds.u32"] or not manifest.get("support_odds_implicit_unity"):
            raise ValueError("zero-width odds")
        conditional = q0[:, None].astype("<u2")
    else:
        odds = np.frombuffer(parts["shared_odds.u32"], "<u4").reshape(8, width + 1)
        conditional = support.cdf(q0, odds)
    mask = support.decode(np.frombuffer(parts["support.rans"], np.uint8), graph, conditional, q0, nrows, genes, width)
    ptr, idx = support.indices_from_support(mask, genes, nnz)

    production_graph = np.frombuffer(bz2.decompress(parts["graph.bz2"]), "<i4").reshape(nrows, 6).copy()
    validate_graph(production_graph, 6)
    runtime, groups, tables = value_tables(parts, genes)
    io, values = runtime
    binary, tail, cdf = tables
    values_out, tail_events, remainder_bits = values.decode(
        np.frombuffer(parts["values.rans"], np.uint8), ptr, idx, production_graph, groups, binary, tail, cdf, True
    )
    if int(tail_events) != int(manifest["tail_events"]) or int(remainder_bits) != int(manifest["remainder_bits"]):
        raise ValueError("value counters")
    matrix = io.from_parts((nrows, genes), ptr, idx, values_out)
    metadata = bz2.decompress(parts["metadata.bz2"])
    if io.csr_sha(matrix) != manifest["canonical_sha256"] or sha(metadata) != manifest["metadata_sha256"]:
        raise ValueError("exact identity")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    np.savez(output / "decoded.npz", shape=np.asarray(matrix.shape), indptr=matrix.indptr, indices=matrix.indices, values=matrix.data)
    (output / "metadata.json").write_bytes(metadata)
    return {
        "archive_only": True,
        "canonical_sha256": manifest["canonical_sha256"],
        "metadata_sha256": manifest["metadata_sha256"],
        "tail_events": int(tail_events),
        "remainder_bits": int(remainder_bits),
    }


def ledger(package):
    manifest, parts, manifest_bytes = read_archive(package)
    categories = {
        "support_stream": len(parts["support.rans"]),
        "value_stream": len(parts["values.rans"]),
        "support_model": len(parts["base_probability.bz2"]) + len(parts["shared_odds.u32"]),
        "value_model_and_group_map": sum(len(parts[name]) for name in VALUE_MEMBER_NAMES - {"values.rans"}),
        "value_graph": len(parts["graph.bz2"]),
        "support_graph_increment": len(parts.get("support_graph.bz2", b"")),
        "identity_coordinates": len(parts["metadata.bz2"]),
        "manifest": len(manifest_bytes),
    }
    categories["zip_framing"] = Path(package).stat().st_size - sum(categories.values())
    if sum(categories.values()) != Path(package).stat().st_size:
        raise ValueError("ledger mismatch")
    return categories, {name: {"bytes": len(data), "sha256": sha(data)} for name, data in sorted(parts.items())}
