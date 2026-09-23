"""Raw-only Qpatch-matched Shared-only encoder and archive decoder."""
from __future__ import annotations

import ast
import base64
import bz2
import hashlib
import json
from pathlib import Path

import numpy as np

from .adapter import CanonicalInput, validate_metadata
from .archive import sha
from .runtime import E1, load_qpatch_runtime

GRAPH_SOURCE = E1 / "codec.py"
GRAPH_SHA = "0cb5669fe8b5bd0fe5439d84fb85f7a00fd9083a3e9a6ea3285497d91e8590bb"


def graph_for(coords: np.ndarray) -> np.ndarray:
    if hashlib.sha256(GRAPH_SOURCE.read_bytes()).hexdigest() != GRAPH_SHA:
        raise RuntimeError("frozen graph source hash mismatch")
    tree = ast.parse(GRAPH_SOURCE.read_text(encoding="utf8"), filename=str(GRAPH_SOURCE))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "graph_for")
    ns = {"np": np}
    exec(compile(ast.fix_missing_locations(ast.Module([fn], [])), str(GRAPH_SOURCE), "exec"), ns)
    graph = np.asarray(ns["graph_for"](coords, "S2_spatial"), dtype=np.int32)
    for i, row in enumerate(graph):
        k = min(i, 6)
        if np.any(row[:k] < 0) or np.any(row[:k] >= i) or len(set(map(int, row[:k]))) != k or np.any(row[k:] != -1):
            raise ValueError("noncausal graph")
    return graph


def encode(raw: CanonicalInput, target: str | Path) -> dict:
    io, entropy, shared_model, q_model, qshare, values = load_qpatch_runtime()
    x = raw.matrix; n, genes = map(int, x.shape)
    if n * genes > 300_000_000 or int(x.nnz) > 100_000_000:
        raise ValueError("symbol budget exceeded")
    meta = raw.metadata_bytes
    coords = np.frombuffer(base64.b64decode(raw.metadata["coordinates_base64"], validate=True), np.dtype(raw.metadata["coordinates_dtype"])).reshape(tuple(raw.metadata["coordinates_shape"]))
    graph = graph_for(coords)
    support = entropy.packed_support(x.indptr, x.indices, n, genes)
    q0 = entropy.fit(support, graph, genes, True)[:, 0].astype("<u2")
    shared_odds, _ = shared_model.fit(support, graph, q0)
    support_q = shared_model.cdf(q0, shared_odds)
    support_blob, _ = entropy.encode(support, graph, support_q, genes)
    oldq, groups, tail_prob, base_freq, profile = q_model.base(x.indices, x.data, genes)
    value_odds, value_cond = q_model.conditional(x.indptr, x.indices, x.data, graph, oldq, groups, tail_prob)
    centers = qshare.share(profile["npositive"], profile["nones"], groups)
    qblob = qshare.encode(centers, groups, oldq, None)
    q = qshare.decode(qblob, groups)
    binary, tail, cdf = q_model.tables(q, groups, base_freq, value_odds, value_cond)
    value_blob, value_nll, tail_events, remainder_bits = values.encode(x.indptr, x.indices, x.data, graph, groups, binary, tail, cdf, True)
    parts = {
        "metadata.bz2": bz2.compress(meta, 9), "support.rans": support_blob.tobytes(),
        "graph.bz2": bz2.compress(graph.astype("<i4").tobytes(), 9), "base_probability.bz2": bz2.compress(q0.tobytes(), 9),
        "shared_odds.u32": np.asarray(shared_odds, "<u4").tobytes(), "value_q1.bz2": qblob,
        "value_group.bz2": bz2.compress(np.asarray(groups, np.uint8).tobytes(), 9),
        "value_base_k.bz2": bz2.compress(np.asarray(base_freq, "<u2").tobytes(), 9),
        "value_odds.u32": np.asarray(value_odds, "<u4").tobytes(),
        "value_cond_k.bz2": bz2.compress(np.asarray(value_cond, "<u2").tobytes(), 9), "values.rans": value_blob.tobytes(),
    }
    info = {"schema": "qpatch-count-v1", "method": "Shared-only", "q1_layout": "QSH1-mode0-shared-v1",
            "shape": [n, genes], "nnz": int(x.nnz), "precision": 12,
            "support_model": "frozen-P2-shared-spatial-Q12-v1", "value_layout": "singleton-K32-uniform-remainder;one-rANS;v1",
            "canonical_sha256": io.csr_sha(x), "metadata_sha256": hashlib.sha256(meta).hexdigest(),
            "tail_events": int(tail_events), "remainder_bits": int(remainder_bits)}
    from .archive import write_shared
    manifest = write_shared(target, parts, info)
    p = Path(target)
    return {"status": "success", "mode": "shared-only", "package_bytes": p.stat().st_size, "package_sha256": io.sha(p),
            "canonical_sha256": info["canonical_sha256"], "metadata_sha256": info["metadata_sha256"],
            "components": {k: len(v) for k, v in parts.items()}, "framing_bytes": p.stat().st_size - sum(map(len, parts.values())),
            "value_cdf_sha256": hashlib.sha256(binary.tobytes() + tail.tobytes() + cdf.tobytes()).hexdigest(),
            "value_nll_bits": float(value_nll), "shared_q1_mode": 0, "exceptions": 0}


def write_shared(path, parts, info):
    from .archive import _write_shared
    return _write_shared(path, parts, info)
