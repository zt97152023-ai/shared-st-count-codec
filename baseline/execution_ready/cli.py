"""CLI for raw-only encoding and parent-process exact evaluation."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from .adapter import read_h5ad
from .archive import cdf_sha, manifest_bytes, read
from .prepare import prepare
from .runtime import load_runtime


def _json(value) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


def _write_exclusive(path: Path, value: dict) -> None:
    if path.exists():
        raise FileExistsError(str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as f:
        f.write(_json(value))


def evaluate(package: str | Path, reference: str | Path, report: str | Path, mode: str = "qpatch12", timeout: int = 600) -> dict:
    if mode != "qpatch12":
        raise ValueError("only mode qpatch12 is implemented")
    package = Path(package)
    report = Path(report)
    if report.exists():
        raise FileExistsError(str(report))
    # Read and validate the archive before starting the worker.  This is still
    # independent of the raw reference and gives a complete fee ledger.
    man, parts = read(package)
    raw = read_h5ad(reference)
    io, *_ = load_runtime()
    with tempfile.TemporaryDirectory(prefix="execution_ready_decode_") as td:
        out = Path(td) / "decoded"
        cmd = [sys.executable, "-m", "baseline.execution_ready", "_decode-worker",
               "--package", str(package), "--output", str(out)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              cwd=str(Path(__file__).resolve().parents[2]))
        if proc.returncode != 0:
            raise RuntimeError(f"archive-only decoder failed ({proc.returncode}): {proc.stderr[-2000:]}")
        worker = json.loads((out / "worker_result.json").read_text(encoding="utf8"))
        with np.load(out / "decoded.npz", allow_pickle=False) as got:
            shape = tuple(int(v) for v in got["shape"])
            exact_shape = shape == tuple(raw.matrix.shape)
            exact_ptr = np.array_equal(got["indptr"], raw.matrix.indptr)
            exact_idx = np.array_equal(got["indices"], raw.matrix.indices)
            exact_val = np.array_equal(got["values"], raw.matrix.data)
        expected_meta = raw.metadata_bytes
        exact_meta = (out / "metadata.json").read_bytes() == expected_meta
    package_sha = io.sha(package)
    value_cdf = cdf_sha(parts)
    if value_cdf != worker.get("value_cdf_sha256"):
        raise ValueError("value CDF identity mismatch")
    exact = exact_shape and exact_ptr and exact_idx and exact_val and exact_meta
    if not exact:
        raise ValueError("decoded archive does not exactly match frozen io047 reference")
    payload_bytes = sum(len(v) for v in parts.values())
    package_bytes = package.stat().st_size
    framing = package_bytes - payload_bytes
    report_obj = {
        "schema": "execution-ready-report-v0.3", "status": "success", "mode": "qpatch12",
        "archive_only_decoder": True, "package": str(package), "reference": str(reference),
        "package_bytes": package_bytes, "package_sha256": package_sha,
        "manifest_sha256": hashlib.sha256(manifest_bytes(package)).hexdigest(),
        "canonical_sha256": man["canonical_sha256"], "metadata_sha256": man["metadata_sha256"],
        "reference_canonical_sha256": io.csr_sha(raw.matrix),
        "reference_metadata_sha256": hashlib.sha256(expected_meta).hexdigest(),
        "exact": {"shape": exact_shape, "indptr": exact_ptr, "indices": exact_idx,
                  "values": exact_val, "metadata": exact_meta, "all": exact},
        "fees": {"payload_bytes": payload_bytes, "framing_and_manifest_bytes": framing,
                 "total_package_bytes": package_bytes,
                 "members": {name: {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}
                             for name, blob in sorted(parts.items())}},
        "symbols": {"nnz": int(man["nnz"]), "tail_events": int(worker["tail_events"]),
                    "remainder_bits": int(worker["remainder_bits"])},
        "consistency": {"actual_package_sha256": package_sha, "value_cdf_sha256": value_cdf,
                         "worker_archive_only": bool(worker.get("archive_only")),
                         "manifest_canonical_matches_worker": man["canonical_sha256"] == worker["canonical_sha256"],
                         "manifest_metadata_matches_worker": man["metadata_sha256"] == worker["metadata_sha256"]},
    }
    _write_exclusive(report, report_obj)
    return report_obj


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="execution-ready")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("encode", "evaluate"):
        p = sub.add_parser(command)
        p.add_argument("--input", required=True)
        p.add_argument("--output", required=True)
        p.add_argument("--mode", default="qpatch12")
        if command == "evaluate":
            p.add_argument("--reference", required=True)
            p.add_argument("--timeout", type=int, default=600)
        else:
            p.add_argument("--reference")
    w = sub.add_parser("_decode-worker")
    w.add_argument("--package", required=True)
    w.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "_decode-worker":
        from .decoder import decode
        result = decode(args.package, args.output)
        sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
        return 0
    if args.mode != "qpatch12":
        parser.error("only mode qpatch12 is implemented")
    if args.command == "encode":
        result = prepare(read_h5ad(args.input), args.output)
    else:
        result = evaluate(args.input, args.reference, args.output, args.mode, args.timeout)
    sys.stdout.write(json.dumps(result, sort_keys=True, ensure_ascii=False) + "\n")
    return 0
