"""Fresh archive-only Qpatch12 decoder worker."""
from __future__ import annotations

import bz2
import hashlib
import json
import struct
import sys
from pathlib import Path

import numpy as np

from .adapter import _validate_metadata
from .archive import read
from .runtime import load_runtime


def install_source_guard() -> None:
    def guard(event, args):
        if event != "open" or not args or not isinstance(args[0], (str, bytes)):
            return
        path = str(args[0]).lower().replace("\\", "/")
        if path.endswith(".h5ad") or "/hestdata/" in path or "/gene_profile" in path:
            raise PermissionError("archive-only decoder forbids raw source/profile access")
    sys.addaudithook(guard)


def _graph_from(raw: bytes, n: int) -> np.ndarray:
    graph = np.frombuffer(bz2.decompress(raw), "<i4")
    if graph.size != n * 6:
        raise ValueError("graph bytes")
    graph = graph.reshape(n, 6).copy()
    for i, row in enumerate(graph):
        k = min(i, 6)
        if np.any(row[:k] < 0) or np.any(row[:k] >= i) or len(set(map(int, row[:k]))) != k or np.any(row[k:] != -1):
            raise ValueError("invalid causal graph")
    return graph


def decode(package: str | Path, output: str | Path) -> dict:
    install_source_guard()
    io, entropy, shared, q_model, qshare, values = load_runtime()
    man, parts = read(package)
    shape = man.get("shape")
    if not isinstance(shape, list) or len(shape) != 2:
        raise ValueError("invalid shape")
    n, genes = io.shape2(np.asarray(shape))
    if n * genes > 300_000_000:
        raise ValueError("matrix shape budget")
    nnz = man.get("nnz")
    if not isinstance(nnz, int) or nnz < 0 or nnz > min(100_000_000, n * genes):
        raise ValueError("invalid nnz")
    graph = _graph_from(parts["graph.bz2"], n)
    q0 = np.frombuffer(bz2.decompress(parts["base_probability.bz2"]), "<u2")
    odds = np.frombuffer(parts["shared_odds.u32"], "<u4")
    if q0.shape != (genes,) or odds.shape != (56,) or np.any(q0 < 1) or np.any(q0 > 4095):
        raise ValueError("invalid support model")
    support_q = shared.cdf(q0, odds.reshape(8, 7))
    mask = entropy.decode(np.frombuffer(parts["support.rans"], np.uint8), graph, support_q, n, genes)
    ptr, idx = entropy.indices_from_support(mask, genes, nnz)

    groups = np.frombuffer(bz2.decompress(parts["value_group.bz2"]), np.uint8)
    if groups.shape != (genes,) or np.any(groups > 7):
        raise ValueError("invalid value groups")
    q = qshare.decode(parts["value_q1.bz2"], groups)
    # qshare.decode performs the bounded full-stream validation first; this
    # second bounded read inspects the mode without opening an unbounded bz2
    # decompression path.
    raw_qblob = bz2.BZ2Decompressor().decompress(
        parts["value_q1.bz2"], max_length=qshare.HEADER.size + 1
    )
    if len(raw_qblob) < qshare.HEADER.size or struct.unpack_from("<4sB", raw_qblob)[0] != b"QSH1" or raw_qblob[4] != 1:
        raise ValueError("QSH1 mode1 patch required")
    base = np.frombuffer(bz2.decompress(parts["value_base_k.bz2"]), "<u2")
    cond = np.frombuffer(bz2.decompress(parts["value_cond_k.bz2"]), "<u2")
    odds_value = np.frombuffer(parts["value_odds.u32"], "<u4")
    if base.size != 8 * 32 or cond.size != 8 * 7 * 32 or odds_value.size != 56:
        raise ValueError("invalid value model dimensions")
    binary, tail, cdf = q_model.tables(
        q, groups, base.reshape(8, 32), odds_value.reshape(8, 7), cond.reshape(8, 7, 32)
    )
    val, tail_events, remainder_bits = values.decode(
        np.frombuffer(parts["values.rans"], np.uint8), ptr, idx, graph,
        groups, binary, tail, cdf, True
    )
    if int(tail_events) != man.get("tail_events") or int(remainder_bits) != man.get("remainder_bits"):
        raise ValueError("value symbol counts")
    x = io.from_parts((n, genes), ptr, idx, val)
    canonical_sha = io.csr_sha(x)
    if canonical_sha != man.get("canonical_sha256"):
        raise ValueError("decoded canonical identity mismatch")
    metadata = bz2.decompress(parts["metadata.bz2"])
    if hashlib.sha256(metadata).hexdigest() != man.get("metadata_sha256"):
        raise ValueError("metadata identity mismatch")
    meta_obj = json.loads(metadata)
    _validate_metadata(io, meta_obj, (n, genes))
    out = Path(output)
    if out.exists():
        raise FileExistsError(str(out))
    out.mkdir(parents=True)
    np.savez(out / "decoded.npz", shape=np.asarray(x.shape), indptr=x.indptr, indices=x.indices, values=x.data)
    (out / "metadata.json").write_bytes(metadata)
    result = {
        "archive_only": True, "canonical_sha256": canonical_sha,
        "metadata_sha256": hashlib.sha256(metadata).hexdigest(),
        "value_cdf_sha256": hashlib.sha256(binary.tobytes() + tail.tobytes() + cdf.tobytes()).hexdigest(),
        "tail_events": int(tail_events), "remainder_bits": int(remainder_bits),
    }
    (out / "worker_result.json").write_text(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf8")
    return result
