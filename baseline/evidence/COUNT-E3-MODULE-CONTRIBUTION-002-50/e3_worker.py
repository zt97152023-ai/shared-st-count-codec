"""Fresh-process worker for the direct E3 pilot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import e3_codec as codec
import ablation_lib as lib


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("op", choices=["encode_no_support", "encode_no_value", "encode_no_q1_sharing", "decode_no_value", "decode_standard", "decode_full_production", "verify", "ledger"])
    parser.add_argument("--sample")
    parser.add_argument("--package", required=True)
    parser.add_argument("--output")
    parser.add_argument("--source")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    package = Path(args.package)
    if args.op == "encode_no_support":
        result = lib.context_archive(args.sample, 0, 6, package)
    elif args.op == "encode_no_value":
        result = codec.encode_no_value(args.sample, package)
    elif args.op == "encode_no_q1_sharing":
        result = codec.encode_no_q1_sharing(args.sample, package)
    elif args.op == "decode_no_value":
        result = codec.decode_no_value(package, Path(args.output))
    elif args.op == "decode_standard":
        manifest, parts, _ = lib.zip_read(package)
        if manifest.get("schema") == "production-shared-ablation-v1":
            result = lib.decode_custom(package, Path(args.output))
        else:
            # The accepted support-predecessor anchor predates the generic
            # ablation schema but carries the same K32 members and decoder
            # semantics. Add only the decoder-local width field in memory.
            manifest = dict(manifest)
            manifest.setdefault("support_bucket_count", 8)
            manifest.setdefault("value_context_predecessors", 6)
            result = lib._dynamic_value_decode(parts, manifest, Path(args.output))
    elif args.op == "decode_full_production":
        import importlib.util
        worker_path = Path(r"D:\HEST1000BenchRun\COUNT-HEST-SHARED-K32-001\code\worker.py")
        spec = importlib.util.spec_from_file_location("e3_full_decode_worker", worker_path)
        worker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(worker)
        result = worker.decode(package, Path(args.output))
    elif args.op == "verify":
        result = lib.verify_source(Path(args.source), Path(args.output))
    else:
        result = {"ledger": codec.ledger(package)}
    Path(args.report).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
