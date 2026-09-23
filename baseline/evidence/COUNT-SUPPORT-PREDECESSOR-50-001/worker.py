"""Fresh-process entry points for encode, archive-only decode, and exact verify."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
import codec


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def archive_only_guard():
    def guard(event, args):
        if event == "open" and args and isinstance(args[0], (str, bytes)):
            path = str(Path(os.fsdecode(args[0])).resolve()).lower().replace("\\", "/")
            if path.endswith(".h5ad") or "/hestdata/" in path:
                raise PermissionError("archive-only decoder forbids source access")
    sys.addaudithook(guard)


def verify(source, decoded):
    from baseline.matched_ready.adapter import read_h5ad
    from baseline.hest1000.pilot import compare

    raw = read_h5ad(source)
    checks = compare(raw.matrix, raw.metadata_bytes, Path(decoded))
    metadata = json.loads((Path(decoded) / "metadata.json").read_text(encoding="utf-8"))
    for key in ["gene_ids", "spot_ids", "coordinates_dtype", "coordinates_shape", "coordinates_base64"]:
        checks[key] = metadata[key] == raw.metadata[key]
    checks["all"] = all(checks.values())
    if not checks["all"]:
        raise ValueError(checks)
    return {"checks": checks}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["encode", "decode", "verify", "ledger"])
    parser.add_argument("--source")
    parser.add_argument("--anchor")
    parser.add_argument("--archive")
    parser.add_argument("--output")
    parser.add_argument("--kind", choices=["spatial", "row"])
    parser.add_argument("--width", type=int)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    start = time.perf_counter()
    if args.stage == "encode":
        result = codec.encode(Path(args.source), Path(args.anchor), Path(args.archive), args.kind, args.width)
    elif args.stage == "decode":
        archive_only_guard()
        result = codec.decode(Path(args.archive), Path(args.output))
    elif args.stage == "verify":
        result = verify(Path(args.source), Path(args.output))
    else:
        categories, members = codec.ledger(Path(args.archive))
        result = {"categories": categories, "members": members, "total_archive_bytes": Path(args.archive).stat().st_size}
    result["worker_seconds"] = time.perf_counter() - start
    write(args.report, result)


if __name__ == "__main__":
    main()
