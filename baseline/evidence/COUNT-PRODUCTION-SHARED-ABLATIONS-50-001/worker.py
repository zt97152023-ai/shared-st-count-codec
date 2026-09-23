"""Fresh-process worker for the Production Shared ablation task."""
from __future__ import annotations
import argparse
import json
import time
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ablation_lib as lib


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["context", "bucket", "value_context", "order", "decode", "verify", "ledger"])
    parser.add_argument("--sample")
    parser.add_argument("--width", type=int)
    parser.add_argument("--value-context", type=int)
    parser.add_argument("--buckets", type=int)
    parser.add_argument("--arm")
    parser.add_argument("--source")
    parser.add_argument("--package")
    parser.add_argument("--output")
    parser.add_argument("--scratch")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    try:
        if args.stage == "context":
            result = lib.context_archive(args.sample, args.width, args.value_context, Path(args.output))
        elif args.stage == "bucket":
            result = lib.bucket_archive(args.sample, args.buckets, Path(args.output), args.width or 6)
        elif args.stage == "value_context":
            result = lib.value_context_archive(args.sample, args.value_context, Path(args.package), Path(args.output))
        elif args.stage == "order":
            result = lib.order_archive(args.sample, args.arm, Path(args.output), Path(args.scratch))
        elif args.stage == "decode":
            result = lib.decode_custom(Path(args.package), Path(args.output))
        elif args.stage == "verify":
            result = lib.verify_source(Path(args.source), Path(args.output))
        else:
            result = {"ledger": lib.physical_ledger(Path(args.package))}
        result["worker_seconds"] = time.perf_counter() - started
        Path(args.report).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        result = {"status": "failed", "error": repr(exc), "worker_seconds": time.perf_counter() - started}
        Path(args.report).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
