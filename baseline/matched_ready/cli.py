"""CLI for formal S0 and Qpatch-matched Shared-only paths."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from .adapter import read_h5ad
from .archive import ledger, read
from .runtime import load_qpatch_runtime, load_s0_codec
from .shared import encode as encode_shared


def _j(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


def _exclusive(path: Path, value: dict):
    if path.exists(): raise FileExistsError(str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as f: f.write(_j(value))


def encode(source, output, mode):
    raw = read_h5ad(source)
    if mode == "s0":
        codec = load_s0_codec()
        target = Path(output)
        if target.exists(): raise FileExistsError(str(target))
        target.parent.mkdir(parents=True, exist_ok=True)
        return codec.encode_case(raw.path, "S0_gene", target)
    if mode == "shared-only":
        return encode_shared(raw, output)
    raise ValueError("only modes s0 and shared-only are implemented")


def evaluate(package, reference, output, mode, timeout=600):
    if mode not in ("s0", "shared-only"):
        raise ValueError("only modes s0 and shared-only are implemented")
    report = Path(output)
    if report.exists(): raise FileExistsError(str(report))
    man, parts, manifest_bytes, actual_mode = read(package)
    if actual_mode != mode: raise ValueError("package mode does not match --mode")
    raw = read_h5ad(reference)
    with tempfile.TemporaryDirectory(prefix="matched_ready_decode_") as td:
        decoded = Path(td) / "decoded"
        cmd = [sys.executable, "-m", "baseline.matched_ready", "_decode-worker", "--package", str(package), "--output", str(decoded)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(Path(__file__).resolve().parents[2]))
        if proc.returncode != 0:
            raise RuntimeError(f"archive-only decoder failed ({proc.returncode}): {proc.stderr[-2000:]}")
        with np.load(decoded / "decoded.npz", allow_pickle=False) as got:
            checks = {
                "shape": tuple(int(v) for v in got["shape"]) == tuple(raw.matrix.shape),
                "indptr": np.array_equal(got["indptr"], raw.matrix.indptr),
                "indices": np.array_equal(got["indices"], raw.matrix.indices),
                "values": np.array_equal(got["values"], raw.matrix.data),
            }
        checks["metadata"] = (decoded / "metadata.json").read_bytes() == raw.metadata_bytes
    if not all(checks.values()): raise ValueError("decoded archive does not match frozen io047 reference")
    fees = ledger(man, parts, manifest_bytes, Path(package))
    io, *_ = load_qpatch_runtime()
    report_obj = {
        "schema": "matched-ready-report-v0.1", "status": "success", "mode": mode,
        "archive_only_decoder": True, "package": str(package), "reference": str(reference),
        "package_sha256": fees["package_sha256"], "canonical_sha256": man["canonical_sha256"],
        "metadata_sha256": man["metadata_sha256"], "reference_canonical_sha256": io.csr_sha(raw.matrix),
        "reference_metadata_sha256": hashlib.sha256(raw.metadata_bytes).hexdigest(),
        "exact": {**checks, "all": True}, "fees": fees,
        "consistency": {"manifest_sha256": fees["manifest_sha256"], "actual_package_sha256": fees["package_sha256"]},
    }
    _exclusive(report, report_obj)
    return report_obj


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="matched-ready")
    subs = parser.add_subparsers(dest="cmd", required=True)
    for name in ("encode", "evaluate"):
        p = subs.add_parser(name); p.add_argument("--input", required=True); p.add_argument("--output", required=True); p.add_argument("--mode", required=True)
        if name == "evaluate": p.add_argument("--reference", required=True); p.add_argument("--timeout", type=int, default=600)
    p = subs.add_parser("_decode-worker"); p.add_argument("--package", required=True); p.add_argument("--output", required=True)
    a = parser.parse_args(argv)
    if a.cmd == "_decode-worker":
        from .decoder import decode
        print(json.dumps(decode(a.package, a.output), sort_keys=True)); return 0
    result = encode(a.input, a.output, a.mode) if a.cmd == "encode" else evaluate(a.input, a.reference, a.output, a.mode, a.timeout)
    print(json.dumps(result, sort_keys=True, ensure_ascii=False)); return 0
