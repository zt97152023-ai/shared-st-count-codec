"""Isolated Production Shared ablation library.

This module never edits historical archives.  It reads the frozen support
calibration archives on D:, builds only new task-local archives, and exposes
fresh-process encode/decode/verify helpers for the runner.
"""
from __future__ import annotations

import base64
import bz2
import hashlib
import importlib.util
import json
import os
import sys
import types
import zipfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

SUPPORT_ROOT = Path(r"D:\HEST1000BenchRun\COUNT-SUPPORT-PREDECESSOR-50-001")
MANIFEST = ROOT / "baseline/evidence/COUNT-SUPPORT-PREDECESSOR-50-001/DATA_SPLIT.csv"
SUPPORT_TEMPLATE = ROOT / "baseline/evidence/COUNT-SUPPORT-PREDECESSOR-50-001/support_dynamic.py"
VALUE_WORKER_PATH = ROOT / "baseline/evidence/VALUE_BEST_OF_9_50_005/worker.py"
K32_WORKER_PATH = ROOT / "baseline/evidence/COUNT-HEST-SHARED-K32-001/worker.py"
if str(SUPPORT_TEMPLATE.parent) not in sys.path:
    sys.path.insert(0, str(SUPPORT_TEMPLATE.parent))

BASE_PARTS = {
    "metadata.bz2", "support.rans", "graph.bz2", "base_probability.bz2",
    "shared_odds.u32", "value_q1.bz2", "value_group.bz2",
    "value_base_k.bz2", "value_odds.u32", "value_cond_k.bz2", "values.rans",
}


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_path(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def dump_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def runtime_io():
    from baseline.hest_large_runtime.runtime import load_qpatch_runtime
    return load_qpatch_runtime()[0]


def read_csv_rows():
    import csv
    with MANIFEST.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_VALUE_WORKER = None
_VALUE_RUNTIME = None
_VALUE_RUNTIME_WIDTH: dict[int, tuple] = {}
_SUPPORT_MODULES: dict[int, types.ModuleType] = {}


def value_worker():
    global _VALUE_WORKER
    if _VALUE_WORKER is None:
        _VALUE_WORKER = load_module(VALUE_WORKER_PATH, "production_ablation_value_worker")
    return _VALUE_WORKER


def value_runtime():
    global _VALUE_RUNTIME
    if _VALUE_RUNTIME is None:
        _VALUE_RUNTIME = value_worker().load(32)
    return _VALUE_RUNTIME


def value_runtime_width(width: int):
    """Load the frozen value model with only its predecessor width varied."""
    width = int(width)
    if width == 6:
        return value_runtime()
    if width in _VALUE_RUNTIME_WIDTH:
        return _VALUE_RUNTIME_WIDTH[width]
    rt = list(value_worker().load(32))
    q_model = rt[3]
    model_src = Path(q_model.__file__).read_text(encoding="utf-8")
    k_replacements = [
        ("pooled=np.zeros((8,32)", "pooled=np.zeros((K,32)"),
        ("seen=np.zeros((8,7,4096)", "seen=np.zeros((K,7,4096)"),
        ("tail=np.zeros((8,7,32)", "tail=np.zeros((K,7,32)"),
        ("np.full((8,7)", "np.full((K,7)"),
        ("np.empty((8,7,32)", "np.empty((K,7,32)"),
        ("range(8)", "range(K)"),
        ("groups>7", "groups>=K"),
        ("shape!=(8,32)", "shape!=(K,32)"),
        ("shape!=(8,7)", "shape!=(K,7)"),
        ("shape!=(8,7,32)", "shape!=(K,7,32)"),
        ("np.zeros((8,8,33)", "np.zeros((K,8,33)"),
    ]
    for old, new in k_replacements:
        if old in model_src:
            model_src = model_src.replace(old, new)
    model_src = model_src.replace("enumerate(BOUNDS) if int(tail_sum[g])<=u*nt),7)", "enumerate(BOUNDS) if int(tail_sum[g])<=u*nt),K-1)")
    model_src = model_src.replace("@njit(cache=True)", "@njit(cache=False)")
    model_src = model_src.replace("if row<6:return 7", f"if row<{width}:return 7")
    model_src = model_src.replace("for j in range(6):s+=find_value", f"for j in range({width}):s+=find_value")
    model_src = model_src.replace("for row in range(6,len(ptr)-1):", f"for row in range({width},len(ptr)-1):")
    model_name = f"production_ablation_value_model_M{width}"
    model_module = types.ModuleType(model_name)
    model_module.__file__ = q_model.__file__
    model_module.K = 32
    sys.modules[model_name] = model_module
    exec(compile(model_src, q_model.__file__, "exec"), model_module.__dict__)
    rt[3] = model_module
    values = rt[5]
    values_src = Path(values.__file__).read_text(encoding="utf-8").replace("@njit(cache=True)", "@njit(cache=False)")
    values_name = f"production_ablation_value_rans_M{width}"
    values_module = types.ModuleType(values_name)
    values_module.__file__ = values.__file__
    old_model = sys.modules.get("model")
    sys.modules["model"] = model_module
    try:
        sys.modules[values_name] = values_module
        exec(compile(values_src, values.__file__, "exec"), values_module.__dict__)
    finally:
        if old_model is None:
            sys.modules.pop("model", None)
        else:
            sys.modules["model"] = old_model
    rt[5] = values_module
    _VALUE_RUNTIME_WIDTH[width] = tuple(rt)
    return _VALUE_RUNTIME_WIDTH[width]


def support_edges(B: int) -> list[int]:
    fixed8 = [1, 4, 16, 64, 256, 1024, 2048, 3072, 4096]
    if B == 1:
        return [1, 4096]
    if B == 2:
        return [1, 256, 4096]
    if B == 4:
        return [1, 16, 256, 2048, 4096]
    if B == 8:
        return fixed8
    if B == 16:
        return [1, 2, 4, 10, 16, 40, 64, 160, 256, 640, 1024,
                1536, 2048, 2560, 3072, 3584, 4096]
    if B == 32:
        b16 = [1, 2, 4, 10, 16, 40, 64, 160, 256, 640, 1024,
               1536, 2048, 2560, 3072, 3584, 4096]
        return sorted(set(b16 + [int((a + b) // 2) for a, b in zip(b16, b16[1:])]))
    raise ValueError(B)


def support_module(B: int):
    if B in _SUPPORT_MODULES:
        return _SUPPORT_MODULES[B]
    src = SUPPORT_TEMPLATE.read_text(encoding="utf-8")
    # Each B gets a distinct generated module. Disable Numba disk caches so a
    # compiled function from B8 cannot be unpickled as B1/B2/B4/B16.
    src = src.replace("@njit(cache=True)", "@njit(cache=False)")
    edges = repr(support_edges(B))
    replacements = [
        ("EDGES = np.asarray([1, 4, 16, 64, 256, 1024, 2048, 3072, 4096])", f"EDGES = np.asarray({edges})"),
        ("np.zeros((8, width + 1, 4096)", f"np.zeros(({B}, width + 1, 4096)"),
        ("np.full((8, width + 1), 65536", f"np.full(({B}, width + 1), 65536"),
        ("np.zeros((8, width + 1), np.float64)", f"np.zeros(({B}, width + 1), np.float64)"),
        ("for bucket in range(8):", f"for bucket in range({B}):"),
        ('"parameter_count": 8', f'"parameter_count": {B}'),
        ("multipliers.shape[0] != 8", f"multipliers.shape[0] != {B}"),
    ]
    for old, new in replacements:
        if old not in src:
            raise RuntimeError(f"support template replacement missing: {old}")
        src = src.replace(old, new)
    name = f"production_ablation_support_B{B}"
    module = types.ModuleType(name)
    module.__file__ = str(SUPPORT_TEMPLATE)
    sys.modules[name] = module
    exec(compile(src, str(SUPPORT_TEMPLATE), "exec"), module.__dict__)
    _SUPPORT_MODULES[B] = module
    return module


def zip_read(path: Path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or "manifest.json" not in names:
            raise ValueError("duplicate or missing members")
        manifest_bytes = archive.read("manifest.json")
        manifest = json.loads(manifest_bytes)
        files = manifest.get("files")
        if not isinstance(files, dict) or set(names) != set(files) | {"manifest.json"}:
            raise ValueError("manifest member set")
        parts = {}
        for name, desc in files.items():
            data = archive.read(name)
            info = archive.getinfo(name)
            if info.compress_type != zipfile.ZIP_STORED or len(data) != desc.get("bytes") or sha_bytes(data) != desc.get("sha256"):
                raise ValueError(f"member integrity: {name}")
            parts[name] = data
    return manifest, parts, manifest_bytes


def zip_write(path: Path, parts: dict[str, bytes], info: dict) -> dict:
    if path.exists():
        raise FileExistsError(path)
    if not set(parts).issuperset(BASE_PARTS - {"graph.bz2"}):
        raise ValueError("incomplete payload")
    manifest = dict(info)
    manifest["files"] = {name: {"bytes": len(data), "sha256": sha_bytes(data)} for name, data in sorted(parts.items())}
    payload = dict(parts)
    payload["manifest.json"] = (json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(payload.items()):
            zi = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            zi.external_attr = 0o100644 << 16
            archive.writestr(zi, data)
    return manifest


def physical_ledger(path: Path):
    manifest, parts, manifest_bytes = zip_read(path)
    groups = {
        "support_stream": {"support.rans"},
        "value_stream": {"values.rans"},
        "support_model": {"base_probability.bz2", "shared_odds.u32"},
        "value_model_and_group_map": {"value_q1.bz2", "value_group.bz2", "value_base_k.bz2", "value_odds.u32", "value_cond_k.bz2"},
        "graph_index": {"graph.bz2", "support_graph.bz2", "value_graph_tail.bz2"},
        "identity_coordinates_metadata": {"metadata.bz2"},
        "mapping": {"order_map.u32"},
    }
    categories = {k: sum(len(parts[n]) for n in names if n in parts) for k, names in groups.items()}
    categories["manifest"] = len(manifest_bytes)
    categories["zip_framing"] = path.stat().st_size - sum(categories.values()) - sum(len(v) for v in parts.values()) + sum(categories[k] for k in groups)
    # The formula above is deliberately written from the physical members so
    # no member is accidentally omitted when an optional mapping is present.
    categories["zip_framing"] = path.stat().st_size - sum(len(v) for v in parts.values()) - len(manifest_bytes)
    if sum(categories.values()) != path.stat().st_size:
        raise ValueError("physical ledger does not sum")
    return categories, {name: {"bytes": len(data), "sha256": sha_bytes(data)} for name, data in sorted(parts.items())}


def anchor_path(sample_id: str, width: int) -> Path:
    direct = SUPPORT_ROOT / "main" / sample_id / f"SPATIAL_M{width:02d}" / "attempt01" / "archive.cnt"
    if direct.is_file():
        return direct
    index = json.loads((SUPPORT_ROOT / "INDEX.json").read_text(encoding="utf-8"))
    record = index[sample_id][f"SPATIAL_M{width:02d}"]["record_path"]
    result = Path(record).parent / "archive.cnt"
    if not result.is_file():
        raise FileNotFoundError(result)
    return result


def raw_input(source: str | Path):
    from baseline.execution_ready.adapter import read_h5ad
    return read_h5ad(source)


def metadata_for_order(raw, permutation: np.ndarray):
    meta = dict(raw.metadata)
    meta["spot_ids"] = [raw.metadata["spot_ids"][int(i)] for i in permutation]
    coords = np.frombuffer(base64.b64decode(raw.metadata["coordinates_base64"], validate=True), np.dtype(raw.metadata["coordinates_dtype"]))
    coords = coords.reshape(tuple(raw.metadata["coordinates_shape"]))[permutation]
    meta["coordinates_base64"] = base64.b64encode(np.ascontiguousarray(coords).tobytes()).decode()
    return meta


def permuted_input(raw, permutation: np.ndarray):
    from baseline.execution_ready.adapter import CanonicalInput
    io = runtime_io()
    meta = metadata_for_order(raw, permutation)
    matrix = raw.matrix[permutation].tocsr()
    return CanonicalInput(raw.path, matrix, meta, io.jbytes(meta), raw.encoding)


def verify_anchor_identity(raw, archive: Path):
    manifest, parts, _ = zip_read(archive)
    io = runtime_io()
    if list(map(int, manifest["shape"])) != list(map(int, raw.matrix.shape)):
        raise ValueError("anchor shape")
    if int(manifest["nnz"]) != int(raw.matrix.nnz) or manifest["canonical_sha256"] != io.csr_sha(raw.matrix):
        raise ValueError("anchor canonical identity")
    if manifest["metadata_sha256"] != sha_bytes(raw.metadata_bytes):
        raise ValueError("anchor metadata identity")
    return manifest, parts


def read_support_anchor(raw, width: int):
    if str(SUPPORT_TEMPLATE.parent) not in sys.path:
        sys.path.insert(0, str(SUPPORT_TEMPLATE.parent))
    support_codec = load_module(SUPPORT_TEMPLATE.parent / "codec.py", "production_ablation_support_archive_codec")
    archive = anchor_path(raw.path.stem, width)
    manifest, parts, _ = support_codec.read_archive(archive)
    io = runtime_io()
    if manifest.get("value_group_count") != 32 or manifest.get("canonical_sha256") != io.csr_sha(raw.matrix) or manifest.get("metadata_sha256") != sha_bytes(raw.metadata_bytes):
        raise ValueError(f"support anchor mismatch {archive}")
    return archive, manifest, dict(parts)


def value_v0_parts(raw, graph):
    io, entropy, shared_model, q_model, qshare, values = value_runtime()
    x = raw.matrix
    oldq, groups, tail_prob, base_freq, profile = q_model.base(x.indices, x.data, int(x.shape[1]))
    shared = qshare.share(profile["npositive"], profile["nones"], groups)
    qblob = qshare.encode(shared, groups, oldq, None)
    q_final = qshare.decode(qblob, groups)
    odds = np.full((32, 7), 65536, dtype="<u4")
    conditional = np.repeat(base_freq[:, None, :], 7, axis=1).astype("<u2", copy=False)
    binary, tail, cdf = q_model.tables(q_final, groups, base_freq, odds, conditional)
    dummy = np.empty((x.shape[0], 0), dtype=np.int32) if graph is None else graph
    value_blob, value_nll, tail_events, remainder_bits = values.encode(
        x.indptr, x.indices, x.data, dummy, groups, binary, tail, cdf, False
    )
    parts = {
        "value_q1.bz2": qblob,
        "value_group.bz2": bz2.compress(np.asarray(groups, np.uint8).tobytes(), 9),
        "value_base_k.bz2": bz2.compress(np.asarray(base_freq, "<u2").tobytes(), 9),
        "value_odds.u32": odds.tobytes(),
        "value_cond_k.bz2": bz2.compress(np.asarray(conditional, "<u2").tobytes(), 9),
        "values.rans": value_blob.tobytes(),
    }
    return parts, {"value_nll_bits": float(value_nll), "tail_events": int(tail_events), "remainder_bits": int(remainder_bits),
                   "value_cdf_sha256": sha_bytes(binary.tobytes() + tail.tobytes() + cdf.tobytes())}


def value_context_parts(raw, graph, width: int):
    io, entropy, shared_model, q_model, qshare, values = value_runtime_width(width)
    x = raw.matrix
    oldq, groups, tail_prob, base_freq, profile = q_model.base(x.indices, x.data, int(x.shape[1]))
    shared = qshare.share(profile["npositive"], profile["nones"], groups)
    qblob = qshare.encode(shared, groups, oldq, None)
    q_final = qshare.decode(qblob, groups)
    odds, conditional = q_model.conditional(x.indptr, x.indices, x.data, graph, oldq, groups, tail_prob)
    binary, tail, cdf = q_model.tables(q_final, groups, base_freq, odds, conditional)
    value_blob, value_nll, tail_events, remainder_bits = values.encode(
        x.indptr, x.indices, x.data, graph, groups, binary, tail, cdf, True
    )
    parts = {
        "value_q1.bz2": qblob,
        "value_group.bz2": bz2.compress(np.asarray(groups, np.uint8).tobytes(), 9),
        "value_base_k.bz2": bz2.compress(np.asarray(base_freq, "<u2").tobytes(), 9),
        "value_odds.u32": np.asarray(odds, "<u4").tobytes(),
        "value_cond_k.bz2": bz2.compress(np.asarray(conditional, "<u2").tobytes(), 9),
        "values.rans": value_blob.tobytes(),
    }
    return parts, {"value_nll_bits": float(value_nll), "tail_events": int(tail_events), "remainder_bits": int(remainder_bits),
                   "value_context_predecessors": int(width),
                   "value_cdf_sha256": sha_bytes(binary.tobytes() + tail.tobytes() + cdf.tobytes())}


def spatial_graph_width(raw, width: int, production_graph: np.ndarray) -> np.ndarray:
    if width == 0:
        return np.empty((production_graph.shape[0], 0), dtype=np.int32)
    if width <= 6:
        return np.asarray(production_graph[:, :width], dtype=np.int32).copy()
    codec = load_module(SUPPORT_TEMPLATE.parent / "codec.py", f"production_ablation_graph_M{width}")
    return np.asarray(codec.spatial_graph(codec.coordinates(raw.metadata), width, production_graph), dtype=np.int32)


def context_archive(sample_id: str, width: int, value_context: int, output: Path):
    raw = raw_input(next(r["source_path"] for r in read_csv_rows() if r["id"] == sample_id))
    _, anchor_manifest, anchor_parts = read_support_anchor(raw, width)
    parts = dict(anchor_parts)
    parts["metadata.bz2"] = bz2.compress(raw.metadata_bytes, 9)
    graph = bz2.decompress(parts["graph.bz2"]) if "graph.bz2" in parts else None
    if value_context == 0:
        vparts, diagnostics = value_v0_parts(raw, np.frombuffer(graph, "<i4").reshape(raw.matrix.shape[0], 6) if graph else None)
        for key, value in vparts.items():
            parts[key] = value
    else:
        diagnostics = {"value_context": 6, "reused_value_members": True}
    if width == 0 and value_context == 0:
        parts.pop("graph.bz2", None)
    elif "graph.bz2" not in parts:
        raise ValueError("graph required by an active context")
    info = {
        "schema": "production-shared-ablation-v1", "method": "Production Shared ablation",
        "shape": list(map(int, raw.matrix.shape)), "nnz": int(raw.matrix.nnz), "precision": 12,
        "support_predecessors": int(width), "support_bucket_count": 8, "support_bucket_edges_q12": support_edges(8),
        "value_context_predecessors": int(6 if value_context else 0),
        "support_context_kind": "spatial" if width else "none",
        "value_context_kind": "spatial" if value_context else "none",
        "canonical_sha256": runtime_io().csr_sha(raw.matrix), "metadata_sha256": sha_bytes(raw.metadata_bytes),
        "tail_events": int(diagnostics.get("tail_events", anchor_manifest.get("tail_events", 0))),
        "remainder_bits": int(diagnostics.get("remainder_bits", anchor_manifest.get("remainder_bits", 0))),
        "value_group_count": 32, "value_group_rule": "fixed-log-axis-v1",
        "value_anchor_archive_sha256": sha_path(anchor_path(sample_id, width)),
    }
    manifest = zip_write(output, parts, info)
    categories, members = physical_ledger(output)
    return {"sample_id": sample_id, "arm": f"S{1 if width else 0}V{1 if value_context else 0}", "status": "success",
            "archive_sha256": sha_path(output), "total_archive_bytes": output.stat().st_size,
            "ledger": categories, "members": members, "diagnostics": diagnostics, "manifest": manifest}


def bucket_archive(sample_id: str, B: int, output: Path, support_width: int = 6):
    raw = raw_input(next(r["source_path"] for r in read_csv_rows() if r["id"] == sample_id))
    anchor, anchor_manifest, anchor_parts = read_support_anchor(raw, 6)
    if B == 8:
        # The caller records this as an immutable anchor audit; no copy is made here.
        raise ValueError("B8 is historical anchor, not a new encode")
    support = support_module(B)
    io = runtime_io(); x = raw.matrix; n, genes = map(int, x.shape)
    production_graph = np.frombuffer(bz2.decompress(anchor_parts["graph.bz2"]), "<i4").reshape(n, 6).copy()
    graph = spatial_graph_width(raw, int(support_width), production_graph)
    q0 = np.frombuffer(bz2.decompress(anchor_parts["base_probability.bz2"]), "<u2")
    mask = support.packed_support(x.indptr, x.indices, n, genes)
    odds, conditional, diag = support.fit(mask, graph, q0, int(support_width))
    stream, nll = support.encode(mask, graph, conditional, q0, int(support_width))
    parts = dict(anchor_parts)
    parts["metadata.bz2"] = bz2.compress(raw.metadata_bytes, 9)
    parts["support.rans"] = stream.tobytes()
    parts["shared_odds.u32"] = np.asarray(odds, "<u4").tobytes()
    if int(support_width) > 6:
        parts["support_graph.bz2"] = bz2.compress(np.asarray(graph[:, 6:], "<i4").tobytes(), 9)
    else:
        parts.pop("support_graph.bz2", None)
    info = {
        "schema": "production-shared-ablation-v1", "method": "Production Shared support bucket ablation",
        "shape": list(map(int, x.shape)), "nnz": int(x.nnz), "precision": 12,
        "support_predecessors": int(support_width), "support_bucket_count": int(B), "support_bucket_edges_q12": support_edges(B),
        "value_context_predecessors": 6, "support_context_kind": "spatial", "value_context_kind": "spatial",
        "canonical_sha256": io.csr_sha(x), "metadata_sha256": sha_bytes(raw.metadata_bytes),
        "tail_events": int(anchor_manifest.get("tail_events", 0)), "remainder_bits": int(anchor_manifest.get("remainder_bits", 0)),
        "value_group_count": 32, "value_group_rule": "fixed-log-axis-v1",
        "support_nll_bits": float(nll), "support_diagnostics": diag,
        "value_anchor_archive_sha256": sha_path(anchor),
    }
    manifest = zip_write(output, parts, info)
    categories, members = physical_ledger(output)
    return {"sample_id": sample_id, "arm": f"B{B}", "status": "success", "archive_sha256": sha_path(output),
            "total_archive_bytes": output.stat().st_size, "ledger": categories, "members": members,
            "diagnostics": {"support_nll_bits": float(nll), "support_predecessors": int(support_width), **diag}, "manifest": manifest}


def value_context_archive(sample_id: str, value_width: int, base_package: Path, output: Path):
    raw = raw_input(next(r["source_path"] for r in read_csv_rows() if r["id"] == sample_id))
    base_manifest, base_parts, _ = zip_read(base_package)
    if int(base_manifest.get("value_group_count", 0)) != 32:
        raise ValueError("value group count")
    support_width = int(base_manifest["support_predecessors"])
    B = int(base_manifest["support_bucket_count"])
    parts = dict(base_parts)
    production_graph = np.frombuffer(bz2.decompress(parts["graph.bz2"]), "<i4").reshape(raw.matrix.shape[0], 6).copy()
    parts.pop("value_graph_tail.bz2", None)
    if int(value_width) == 0:
        vparts, diagnostics = value_v0_parts(raw, None)
    else:
        value_graph = spatial_graph_width(raw, int(value_width), production_graph)
        vparts, diagnostics = value_context_parts(raw, value_graph, int(value_width))
        if int(value_width) > 6:
            parts["value_graph_tail.bz2"] = bz2.compress(np.asarray(value_graph[:, 6:], "<i4").tobytes(), 9)
    parts.update(vparts)
    info = {
        "schema": "production-shared-ablation-v1", "method": "Production Shared value-context closure",
        "shape": list(map(int, raw.matrix.shape)), "nnz": int(raw.matrix.nnz), "precision": 12,
        "support_predecessors": support_width, "support_bucket_count": B, "support_bucket_edges_q12": base_manifest["support_bucket_edges_q12"],
        "value_context_predecessors": int(value_width), "support_context_kind": "spatial", "value_context_kind": "spatial" if value_width else "none",
        "canonical_sha256": runtime_io().csr_sha(raw.matrix), "metadata_sha256": sha_bytes(raw.metadata_bytes),
        "tail_events": int(diagnostics.get("tail_events", base_manifest.get("tail_events", 0))),
        "remainder_bits": int(diagnostics.get("remainder_bits", base_manifest.get("remainder_bits", 0))),
        "value_group_count": 32, "value_group_rule": "fixed-log-axis-v1",
        "support_base_archive_sha256": sha_path(base_package),
    }
    manifest = zip_write(output, parts, info)
    categories, members = physical_ledger(output)
    return {"sample_id": sample_id, "arm": f"MV{value_width}", "status": "success", "archive_sha256": sha_path(output),
            "total_archive_bytes": output.stat().st_size, "ledger": categories, "members": members,
            "diagnostics": diagnostics, "manifest": manifest}


def order_permutation(raw, arm: str):
    n = raw.matrix.shape[0]
    if arm == "ORIGINAL":
        return np.arange(n, dtype=np.int64)
    if arm == "CANONICAL_SPATIAL":
        coords = np.frombuffer(base64.b64decode(raw.metadata["coordinates_base64"], validate=True), np.dtype(raw.metadata["coordinates_dtype"])).reshape(tuple(raw.metadata["coordinates_shape"]))
        ids = np.asarray(raw.metadata["spot_ids"], dtype=str)
        return np.lexsort((np.arange(n), ids, coords[:, 1], coords[:, 0])).astype(np.int64)
    if arm.startswith("RANDOM_SEED_"):
        seed = int(arm.rsplit("_", 1)[1])
        return np.random.default_rng(seed).permutation(n).astype(np.int64)
    raise ValueError(arm)


def order_archive(sample_id: str, arm: str, output: Path, scratch: Path):
    raw = raw_input(next(r["source_path"] for r in read_csv_rows() if r["id"] == sample_id))
    permutation = order_permutation(raw, arm)
    ordered = permuted_input(raw, permutation)
    worker = load_module(K32_WORKER_PATH, "production_ablation_k32_worker")
    scratch.mkdir(parents=True, exist_ok=True)
    standard = scratch / "standard.cnt"
    result = worker.encode(ordered, standard, 32, False)
    base_manifest, parts, _ = zip_read(standard)
    parts["order_map.u32"] = np.asarray(permutation, "<u4").tobytes()
    # The ORIGINAL arm has an identity map only as a manifest-free control;
    # storing no mapping avoids charging bytes for information not needed.
    if arm == "ORIGINAL":
        parts.pop("order_map.u32")
    info = dict(base_manifest)
    info.pop("files", None)
    info.update({"schema": "production-shared-ablation-v1", "method": "Production Shared traversal ablation",
                 "traversal_arm": arm, "order_mapping": arm != "ORIGINAL",
                 "original_metadata_sha256": sha_bytes(raw.metadata_bytes),
                 "support_predecessors": 6, "support_bucket_count": 8, "support_bucket_edges_q12": support_edges(8),
                 "value_context_predecessors": 6, "value_group_count": 32, "value_group_rule": "fixed-log-axis-v1"})
    manifest = zip_write(output, parts, info)
    categories, members = physical_ledger(output)
    return {"sample_id": sample_id, "arm": arm, "status": "success", "archive_sha256": sha_path(output),
            "total_archive_bytes": output.stat().st_size, "ledger": categories, "members": members,
            "mapping_bytes": len(parts.get("order_map.u32", b"")), "permutation_sha256": sha_bytes(np.asarray(permutation, "<u4").tobytes()),
            "manifest": manifest, "base_standard_archive_sha256": sha_path(standard), "base_result": result}


def _dynamic_value_decode(parts, man, output):
    n, genes = map(int, man["shape"]); nnz = int(man["nnz"])
    production_graph = np.empty((n, 0), dtype=np.int32)
    if "graph.bz2" in parts:
        production_graph = np.frombuffer(bz2.decompress(parts["graph.bz2"]), "<i4").reshape(n, 6).copy()
    B = int(man["support_bucket_count"]); width = int(man["support_predecessors"])
    support = support_module(B)
    q0 = np.frombuffer(bz2.decompress(parts["base_probability.bz2"]), "<u2")
    if width == 0:
        conditional = q0[:, None]
        support_graph = np.empty((n, 0), dtype=np.int32)
    else:
        if width <= 6:
            support_graph = production_graph[:, :width]
        else:
            if "support_graph.bz2" not in parts:
                raise ValueError("missing support graph tail")
            tail = np.frombuffer(bz2.decompress(parts["support_graph.bz2"]), "<i4")
            if tail.size != n * (width - 6):
                raise ValueError("support graph tail bytes")
            support_graph = np.concatenate([production_graph, tail.reshape(n, width - 6)], axis=1)
        odds = np.frombuffer(parts["shared_odds.u32"], "<u4").reshape(B, width + 1)
        conditional = support.cdf(q0, odds)
    mask = support.decode(np.frombuffer(parts["support.rans"], np.uint8), support_graph, conditional, q0, n, genes, width)
    ptr, idx = support.indices_from_support(mask, genes, nnz)
    value_width = int(man["value_context_predecessors"])
    io, entropy, shared_model, q_model, qshare, values = value_runtime_width(value_width if value_width else 6)
    groups = np.frombuffer(bz2.decompress(parts["value_group.bz2"]), np.uint8)
    q = qshare.decode(parts["value_q1.bz2"], groups)
    base = np.frombuffer(bz2.decompress(parts["value_base_k.bz2"]), "<u2").reshape(32, 32)
    odds = np.frombuffer(parts["value_odds.u32"], "<u4").reshape(32, 7)
    cond = np.frombuffer(bz2.decompress(parts["value_cond_k.bz2"]), "<u2").reshape(32, 7, 32)
    binary, tail, cdf = q_model.tables(q, groups, base, odds, cond)
    use_value_context = value_width > 0
    if not use_value_context:
        value_graph = np.empty((n, 0), dtype=np.int32)
    elif value_width <= 6:
        value_graph = production_graph[:, :value_width]
    else:
        if "value_graph_tail.bz2" not in parts:
            raise ValueError("missing value graph tail")
        tail_graph = np.frombuffer(bz2.decompress(parts["value_graph_tail.bz2"]), "<i4")
        if tail_graph.size != n * (value_width - 6):
            raise ValueError("value graph tail bytes")
        value_graph = np.concatenate([production_graph, tail_graph.reshape(n, value_width - 6)], axis=1)
    values_out, tail_events, remainder_bits = values.decode(np.frombuffer(parts["values.rans"], np.uint8), ptr, idx, value_graph, groups, binary, tail, cdf, use_value_context)
    if int(tail_events) != int(man["tail_events"]) or int(remainder_bits) != int(man["remainder_bits"]):
        raise ValueError("value counters")
    matrix = io.from_parts((n, genes), ptr, idx, values_out)
    if io.csr_sha(matrix) != man["canonical_sha256"]:
        raise ValueError("canonical identity")
    metadata = bz2.decompress(parts["metadata.bz2"])
    if sha_bytes(metadata) != man["metadata_sha256"]:
        raise ValueError("metadata identity")
    meta = json.loads(metadata)
    mapping = None
    if "order_map.u32" in parts:
        mapping = np.frombuffer(parts["order_map.u32"], "<u4").astype(np.int64)
        if mapping.shape != (n,) or not np.array_equal(np.sort(mapping), np.arange(n)):
            raise ValueError("invalid order map")
        restore = np.argsort(mapping)
        matrix = matrix[restore].tocsr()
        coords = np.frombuffer(base64.b64decode(meta["coordinates_base64"], validate=True), np.dtype(meta["coordinates_dtype"])).reshape(tuple(meta["coordinates_shape"]))
        meta["spot_ids"] = [meta["spot_ids"][int(i)] for i in restore]
        coords = np.ascontiguousarray(coords[restore])
        meta["coordinates_base64"] = base64.b64encode(coords.tobytes()).decode()
        metadata = io.jbytes(meta)
        if sha_bytes(metadata) != man["original_metadata_sha256"]:
            raise ValueError("restored metadata identity")
    output.mkdir(parents=True, exist_ok=False)
    np.savez(output / "decoded.npz", shape=np.asarray(matrix.shape), indptr=matrix.indptr, indices=matrix.indices, values=matrix.data)
    (output / "metadata.json").write_bytes(metadata)
    return {"archive_only": True, "canonical_sha256": io.csr_sha(matrix), "metadata_sha256": sha_bytes(metadata),
            "mapping_inverted": mapping is not None, "restored_shape": list(matrix.shape)}


def decode_custom(package: Path, output: Path):
    def guard(event, args):
        if event == "open" and args and isinstance(args[0], (str, bytes)):
            p = str(args[0]).lower().replace("\\", "/")
            if p.endswith(".h5ad") or "/hestdata/" in p:
                raise PermissionError("archive-only decoder forbids raw source")
    sys.addaudithook(guard)
    manifest, parts, _ = zip_read(package)
    if manifest.get("schema") != "production-shared-ablation-v1":
        raise ValueError("schema")
    return _dynamic_value_decode(parts, manifest, output)


def verify_source(source: Path, decoded: Path):
    from baseline.hest_large_runtime.adapter import read_h5ad
    from baseline.hest1000.pilot import compare
    raw = read_h5ad(source)
    checks = compare(raw.matrix, raw.metadata_bytes, decoded)
    metadata = json.loads((decoded / "metadata.json").read_text(encoding="utf-8"))
    for key in ["gene_ids", "spot_ids", "coordinates_dtype", "coordinates_shape", "coordinates_base64"]:
        checks[key] = metadata[key] == raw.metadata[key]
    checks["all"] = all(checks.values())
    if not checks["all"]:
        raise ValueError(checks)
    return {"checks": checks, "all": True, "canonical_sha256": runtime_io().csr_sha(raw.matrix), "metadata_sha256": sha_bytes(raw.metadata_bytes)}
