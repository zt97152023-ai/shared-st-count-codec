"""Retry only preserved joint-arm failures with isolated no-cache workers."""
from __future__ import annotations
import json, os, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT / "baseline/evidence/COUNT-PRODUCTION-SHARED-ABLATIONS-50-001"
WORKER = OLD / "worker.py"
SOURCE_ROOT = Path(r"E:\Hestdata\st")


def call(args, env, log):
    p = subprocess.run([sys.executable, "-X", "utf8", *map(str, args)], env=env, text=True, capture_output=True, timeout=180)
    log.write_text((p.stdout or "") + (p.stderr or ""), encoding="utf-8")
    if p.returncode:
        raise RuntimeError(f"rc={p.returncode}: {args}")


def main():
    failures = sorted((HERE / "main/joint").glob("**/FAILURE.json"))
    summary = []
    for failure in failures:
        rel = failure.relative_to(HERE / "main/joint")
        sample, arm = rel.parts[0], rel.parts[1]
        out = HERE / "retry/joint" / sample / arm
        out.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy(); env["NUMBA_DISABLE_CACHING"] = "1"; env["NUMBA_CACHE_DIR"] = str(HERE / "numba_cache_retry" / sample / arm)
        main_dir = failure.parent
        archive = out / "archive.cnt"
        try:
            if not archive.exists():
                if (main_dir / "archive.cnt").is_file():
                    shutil.copy2(main_dir / "archive.cnt", archive)
                else:
                    width = arm.rsplit("M", 1)[1]
                    call([WORKER, "bucket", "--sample", sample, "--buckets", "16", "--width", width, "--output", archive, "--scratch", out / "scratch", "--report", out / "encode.json"], env, out / "encode.log")
            call([WORKER, "decode", "--package", archive, "--output", out / "decoded", "--report", out / "decode.json"], env, out / "decode.log")
            call([WORKER, "verify", "--sample", sample, "--source", SOURCE_ROOT / f"{sample}.h5ad", "--output", out / "decoded", "--report", out / "verify.json"], env, out / "verify.log")
            call([WORKER, "ledger", "--package", archive, "--report", out / "ledger.json"], env, out / "ledger.log")
            enc = json.loads((out / "encode.json").read_text(encoding="utf-8")) if (out / "encode.json").is_file() else json.loads((main_dir / "encode.json").read_text(encoding="utf-8"))
            ver = json.loads((out / "verify.json").read_text(encoding="utf-8"))
            led = json.loads((out / "ledger.json").read_text(encoding="utf-8"))["ledger"][0]
            row = {"stage": "joint", "sample_id": sample, "arm": arm, "status": "success", "verify_all": bool(ver.get("all")),
                   "retry_of": str(main_dir.relative_to(HERE)), "archive_sha256": enc["archive_sha256"], "total_archive_bytes": int(enc["total_archive_bytes"]), **led}
        except Exception as exc:
            row = {"stage": "joint", "sample_id": sample, "arm": arm, "status": "failed", "error": repr(exc), "retry_of": str(main_dir.relative_to(HERE))}
        (out / "RESULT.json").write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        if row["status"] != "success":
            (out / "FAILURE.json").write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        summary.append(row)
    (HERE / "RETRY_SUMMARY.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
