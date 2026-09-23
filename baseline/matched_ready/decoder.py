"""Fresh archive-only decoders for formal S0 and Shared-only."""
from __future__ import annotations

import bz2
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

from .adapter import validate_metadata
from .archive import read
from .runtime import load_qpatch_runtime, load_s0_codec


def source_guard():
    def guard(event, args):
        if event == "open" and args and isinstance(args[0], (str, bytes)):
            p = str(args[0]).lower().replace("\\", "/")
            if p.endswith(".h5ad") or "/hestdata/" in p or "/profile" in p or "/screen" in p:
                raise PermissionError("archive-only decoder forbids raw source access")
    sys.addaudithook(guard)


def _graph(raw, n):
    graph = np.frombuffer(bz2.decompress(raw), "<i4")
    if graph.size != n * 6:
        raise ValueError("graph bytes")
    graph = graph.reshape(n, 6).copy()
    for i, row in enumerate(graph):
        k = min(i, 6)
        if np.any(row[:k] < 0) or np.any(row[:k] >= i) or len(set(map(int, row[:k]))) != k or np.any(row[k:] != -1):
            raise ValueError("invalid causal graph")
    return graph


def _shared_decode(man, parts, out):
    io, entropy, shared_model, q_model, qshare, values = load_qpatch_runtime()
    n, genes = map(int, man["shape"]); nnz = int(man["nnz"])
    graph = _graph(parts["graph.bz2"], n)
    q0 = np.frombuffer(bz2.decompress(parts["base_probability.bz2"]), "<u2")
    odds = np.frombuffer(parts["shared_odds.u32"], "<u4").reshape(8, 7)
    if q0.shape != (genes,) or np.any(q0 < 1) or np.any(q0 > 4095): raise ValueError("support model")
    support_q = shared_model.cdf(q0, odds)
    mask = entropy.decode(np.frombuffer(parts["support.rans"], np.uint8), graph, support_q, n, genes)
    ptr, idx = entropy.indices_from_support(mask, genes, nnz)
    groups = np.frombuffer(bz2.decompress(parts["value_group.bz2"]), np.uint8)
    if groups.shape != (genes,) or np.any(groups > 7): raise ValueError("value groups")
    q = qshare.decode(parts["value_q1.bz2"], groups)
    rawq = bz2.BZ2Decompressor().decompress(parts["value_q1.bz2"], max_length=qshare.HEADER.size + 1)
    if len(rawq) != qshare.HEADER.size or rawq[4] != 0: raise ValueError("Shared-only requires QSH1 mode0")
    base = np.frombuffer(bz2.decompress(parts["value_base_k.bz2"]), "<u2").reshape(8, 32)
    vo = np.frombuffer(parts["value_odds.u32"], "<u4").reshape(8, 7)
    cond = np.frombuffer(bz2.decompress(parts["value_cond_k.bz2"]), "<u2").reshape(8, 7, 32)
    binary, tail, cdf = q_model.tables(q, groups, base, vo, cond)
    val, te, rb = values.decode(np.frombuffer(parts["values.rans"], np.uint8), ptr, idx, graph, groups, binary, tail, cdf, True)
    if int(te) != man["tail_events"] or int(rb) != man["remainder_bits"]: raise ValueError("value counts")
    x = io.from_parts((n, genes), ptr, idx, val)
    if io.csr_sha(x) != man["canonical_sha256"]: raise ValueError("canonical identity")
    metadata = bz2.decompress(parts["metadata.bz2"])
    if hashlib.sha256(metadata).hexdigest() != man["metadata_sha256"]: raise ValueError("metadata identity")
    validate_metadata(json.loads(metadata), (n, genes))
    out.mkdir(parents=True, exist_ok=False)
    np.savez(out / "decoded.npz", shape=np.asarray(x.shape), indptr=x.indptr, indices=x.indices, values=x.data)
    (out / "metadata.json").write_bytes(metadata)
    return {"archive_only": True, "canonical_sha256": man["canonical_sha256"], "metadata_sha256": man["metadata_sha256"],
            "value_cdf_sha256": hashlib.sha256(binary.tobytes() + tail.tobytes() + cdf.tobytes()).hexdigest(),
            "tail_events": int(te), "remainder_bits": int(rb)}


def decode(package, output):
    source_guard()
    man, parts, _, mode = read(package)
    out = Path(output)
    if mode == "s0":
        codec = load_s0_codec()
        result = codec.decode_case(package, out)
        result["archive_only"] = True
        return result
    return _shared_decode(man, parts, out)
