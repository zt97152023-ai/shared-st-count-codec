"""Checked CLI bridge for CSR_BZIP2_9 repair attempts.

The comparator and its level-9 byte stream are unchanged. This wrapper adds an
encode-side round-trip integrity check before the separate decoder stage runs.
"""
import argparse
import bz2
import hashlib
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
from scipy import sparse

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from baseline.hest1000 import general_baselines as codec
from baseline.hest1000 import pilot


def check_bzip_member(source: Path, archive: Path) -> dict:
    with zipfile.ZipFile(archive, "r") as zf:
        bad_member = zf.testzip()
        if bad_member is not None:
            raise ValueError(f"ZIP CRC failed for {bad_member}")
        manifest = json.loads(zf.read("manifest.json"))
        raw = zf.read("csr.bz2")
        if hashlib.sha256(raw).hexdigest() != manifest["files"]["csr.bz2"]["sha256"]:
            raise ValueError("CSR bzip2 member hash mismatch")

    decoded_frame = bz2.decompress(raw)
    x = codec.validate(sparse.load_npz(source / "counts.npz"))
    expected_streams = {
        "shape.u64": np.asarray(x.shape, dtype="<u8").tobytes(),
        "indptr.u64": x.indptr.astype("<u8").tobytes(),
        "indices.u32": x.indices.astype("<u4").tobytes(),
        "values.u32": x.data.astype("<u4").tobytes(),
    }
    expected_frame = codec.frame(expected_streams)
    if decoded_frame != expected_frame:
        raise ValueError("CSR bzip2 output did not round-trip to the source frame")
    return {
        "valid": True,
        "member_bytes": len(raw),
        "decoded_frame_bytes": len(decoded_frame),
        "decoded_frame_sha256": hashlib.sha256(decoded_frame).hexdigest(),
        "source_csr_sha256": codec.csr_hash(x),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("worker")
    parser.add_argument("stage", choices=["encode", "decode"])
    parser.add_argument("method", choices=codec.METHODS)
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("--blocked", nargs="*", default=[])
    args = parser.parse_args()
    if args.worker != "worker":
        parser.error("expected worker")
    if args.method != "CSR_BZIP2_9":
        parser.error("checked repair wrapper is scoped to CSR_BZIP2_9")

    output = Path(args.output)
    if args.stage == "encode":
        output.mkdir(exist_ok=False)
        result = codec.encode(args.source, args.method, output / "archive.bin")
        result["encode_self_check"] = check_bzip_member(Path(args.source), output / "archive.bin")
    else:
        pilot.install_guard(args.blocked)
        for root in args.blocked:
            try:
                open(Path(root) / "guard-probe", "rb")
            except PermissionError:
                pass
            else:
                raise RuntimeError("decoder guard probe failed")
        result = codec.decode(Path(args.source) / "archive.bin", output)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
