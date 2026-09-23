"""Raw-only Qpatch12 preparation.

This is intentionally a separate phase from H5AD format normalization.  The
adapter produces canonical data; this module derives the paid support and
positive-value parameters from that data using the frozen implementations.
"""
from __future__ import annotations

import ast
import base64
import bz2
import hashlib
from pathlib import Path

import numpy as np

from .adapter import CanonicalInput
from .archive import write
from .runtime import FROZEN_E1, load_runtime


GRAPH_SOURCE = FROZEN_E1 / "codec.py"
GRAPH_SOURCE_SHA256 = "0cb5669fe8b5bd0fe5439d84fb85f7a00fd9083a3e9a6ea3285497d91e8590bb"


def _graph_function():
    """Extract only graph_for from the frozen source; never import codec.py."""
    if hashlib.sha256(GRAPH_SOURCE.read_bytes()).hexdigest() != GRAPH_SOURCE_SHA256:
        raise RuntimeError("frozen graph source hash mismatch")
    tree = ast.parse(GRAPH_SOURCE.read_text(encoding="utf8"), filename=str(GRAPH_SOURCE))
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "graph_for"), None)
    if fn is None:
        raise RuntimeError("frozen graph_for function is missing")
    module = ast.Module(body=[fn], type_ignores=[])
    ns = {"np": np}
    exec(compile(ast.fix_missing_locations(module), str(GRAPH_SOURCE), "exec"), ns)
    return ns["graph_for"]


def graph_for(coords: np.ndarray, kind: str = "S2_spatial") -> np.ndarray:
    if kind != "S2_spatial":
        raise ValueError("execution-ready Qpatch supports only S2_spatial support graph")
    graph = np.asarray(_graph_function()(np.asarray(coords), kind), dtype=np.int32)
    n = len(coords)
    if graph.shape != (n, 6):
        raise ValueError("frozen graph shape mismatch")
    for i, row in enumerate(graph):
        k = min(i, 6)
        if np.any(row[:k] < 0) or np.any(row[:k] >= i) or len(set(map(int, row[:k]))) != k or np.any(row[k:] != -1):
            raise ValueError("frozen graph is not causal")
    return graph


def prepare(raw: CanonicalInput, target: str | Path) -> dict:
    """Fit and serialize a complete Qpatch12 archive from one raw H5AD."""
    io, entropy, shared, q_model, qshare, values = load_runtime()
    x = raw.matrix
    n, genes = map(int, x.shape)
    if n * genes > 300_000_000 or int(x.nnz) > 100_000_000:
        raise ValueError("symbol budget exceeded")
    meta_bytes = raw.metadata_bytes
    coords = np.frombuffer(
        base64.b64decode(raw.metadata["coordinates_base64"], validate=True),
        dtype=np.dtype(raw.metadata["coordinates_dtype"]),
    ).reshape(tuple(raw.metadata["coordinates_shape"]))

    # Support preparation: q0 is fitted by frozen entropy, then the frozen
    # shared model supplies 56 odds and the exact integer conditional CDF.
    graph = graph_for(coords)
    support = entropy.packed_support(x.indptr, x.indices, n, genes)
    q0 = entropy.fit(support, graph, genes, True)[:, 0].astype("<u2")
    shared_odds, shared_stats = shared.fit(support, graph, q0)
    support_q = shared.cdf(q0, shared_odds)
    support_blob, support_nll = entropy.encode(support, graph, support_q, genes)

    # Positive-value preparation is separate from format adaptation and uses
    # the frozen qpatch value model and integer QSH1 patch rule.
    oldq, groups, tail_prob, base_freq, profile = q_model.base(x.indices, x.data, genes)
    value_odds, value_cond = q_model.conditional(
        x.indptr, x.indices, x.data, graph, oldq, groups, tail_prob
    )
    centers = qshare.share(profile["npositive"], profile["nones"], groups)
    oldcdf = qshare.cdf(oldq, groups, value_odds)
    sharedcdf = qshare.cdf(centers[groups], groups, value_odds)
    raw_bound, safe_bound, epsilon = qshare.bound(
        profile["npositive"], profile["nones"], oldcdf, sharedcdf
    )
    patch = safe_bound > 12
    qblob = qshare.encode(centers, groups, oldq, patch)
    q = qshare.decode(qblob, groups)
    binary, tail, cdf = q_model.tables(q, groups, base_freq, value_odds, value_cond)
    value_blob, value_nll, tail_events, remainder_bits = values.encode(
        x.indptr, x.indices, x.data, graph, groups, binary, tail, cdf, True
    )

    parts = {
        "metadata.bz2": bz2.compress(meta_bytes, 9),
        "support.rans": support_blob.tobytes(),
        "graph.bz2": bz2.compress(graph.astype("<i4").tobytes(), 9),
        "base_probability.bz2": bz2.compress(q0.astype("<u2").tobytes(), 9),
        "shared_odds.u32": np.asarray(shared_odds, dtype="<u4").tobytes(),
        "value_q1.bz2": qblob,
        "value_group.bz2": bz2.compress(np.asarray(groups, dtype=np.uint8).tobytes(), 9),
        "value_base_k.bz2": bz2.compress(np.asarray(base_freq, dtype="<u2").tobytes(), 9),
        "value_odds.u32": np.asarray(value_odds, dtype="<u4").tobytes(),
        "value_cond_k.bz2": bz2.compress(np.asarray(value_cond, dtype="<u2").tobytes(), 9),
        "values.rans": value_blob.tobytes(),
    }
    canonical_sha = io.csr_sha(x)
    metadata_sha = hashlib.sha256(meta_bytes).hexdigest()
    info = {
        "schema": "qpatch-count-v1", "method": "Qpatch12", "q1_layout": "QSH1-mode1-12bit-exceptions-bz2-v1",
        "shape": [n, genes], "nnz": int(x.nnz), "precision": 12,
        "support_model": "frozen-P2-shared-spatial-Q12-v1",
        "value_layout": "singleton-K32-uniform-remainder;one-rANS;v1",
        "canonical_sha256": canonical_sha, "metadata_sha256": metadata_sha,
        "tail_events": int(tail_events), "remainder_bits": int(remainder_bits),
    }
    manifest = write(target, parts, info)
    package = Path(target)
    package_sha = io.sha(package)
    framing = package.stat().st_size - sum(len(v) for v in parts.values())
    return {
        "status": "success", "mode": "qpatch12", "package_bytes": package.stat().st_size,
        "package_sha256": package_sha, "canonical_sha256": canonical_sha,
        "metadata_sha256": metadata_sha, "components": {k: len(v) for k, v in parts.items()},
        "framing_bytes": framing, "support_nll_bits": float(support_nll),
        "value_nll_bits": float(value_nll), "exceptions": int(patch.sum()),
        "raw_counts_sha256": hashlib.sha256(
            np.asarray(profile["npositive"], dtype="<i8").tobytes() +
            np.asarray(profile["nones"], dtype="<i8").tobytes()
        ).hexdigest(),
        "shared_model": shared_stats, "graph_source_sha256": hashlib.sha256(GRAPH_SOURCE.read_bytes()).hexdigest(),
        "manifest_sha256": hashlib.sha256(io.jbytes(manifest)).hexdigest(),
    }
