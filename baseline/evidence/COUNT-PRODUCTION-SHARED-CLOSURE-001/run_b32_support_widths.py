"""Run the preregistered B32 support-width follow-up (M_s=4,8)."""
from __future__ import annotations
import csv, hashlib, json, os, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT / "baseline/evidence/COUNT-PRODUCTION-SHARED-ABLATIONS-50-001"
WORKER = OLD / "worker.py"
MANIFEST = ROOT / "baseline/evidence/COUNT-SUPPORT-PREDECESSOR-50-001/DATA_SPLIT.csv"
SOURCE_ROOT = Path(r"E:/Hestdata/st")


def run(cmd, env, log, timeout=240):
    p = subprocess.run([sys.executable, "-X", "utf8", *map(str, cmd)], env=env,
                       text=True, capture_output=True, timeout=timeout)
    log.write_text((p.stdout or "") + (p.stderr or ""), encoding="utf-8")
    if p.returncode:
        raise RuntimeError(f"worker failed rc={p.returncode}: {cmd}")


def one(sample, width):
    arm = f"B32_M{width}"
    folder = HERE / "main" / "b32_width" / sample / arm
    folder.mkdir(parents=True, exist_ok=True)
    prior = folder / "RESULT.json"
    if prior.is_file():
        try:
            x = json.loads(prior.read_text(encoding="utf-8"))
            if x.get("status") == "success" and x.get("verify_all") is True:
                return x
        except Exception:
            pass
    env = os.environ.copy(); env.pop("NUMBA_DISABLE_CACHING", None)
    env["NUMBA_CACHE_DIR"] = str(HERE / "numba_cache_b32_width" / sample / arm)
    env["PYTHONHASHSEED"] = "0"
    archive = folder / "archive.cnt"
    try:
        if not archive.is_file():
            run([WORKER, "bucket", "--sample", sample, "--output", archive,
                 "--scratch", folder / "scratch", "--report", folder / "encode.json",
                 "--buckets", "32", "--width", str(width)], env, folder / "encode.log")
        decoded = folder / "decoded"
        if decoded.exists(): shutil.rmtree(decoded)
        run([WORKER, "decode", "--package", archive, "--output", decoded,
             "--report", folder / "decode.json"], env, folder / "decode.log")
        run([WORKER, "verify", "--sample", sample, "--source", SOURCE_ROOT / f"{sample}.h5ad",
             "--output", decoded, "--report", folder / "verify.json"], env, folder / "verify.log")
        run([WORKER, "ledger", "--package", archive, "--report", folder / "ledger.json"], env, folder / "ledger.log")
        verified = json.loads((folder / "verify.json").read_text(encoding="utf-8"))
        ledger = json.loads((folder / "ledger.json").read_text(encoding="utf-8"))["ledger"][0]
        row = {"stage": "b32_width", "sample_id": sample, "arm": arm, "status": "success",
               "verify_all": bool(verified.get("all")),
               "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
               "total_archive_bytes": archive.stat().st_size, **ledger}
        prior.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        return row
    except Exception as exc:
        row = {"stage": "b32_width", "sample_id": sample, "arm": arm, "status": "failed", "error": repr(exc)}
        (folder / "FAILURE.json").write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        prior.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        return row


def main():
    samples = [r["id"] for r in csv.DictReader(MANIFEST.open(encoding="utf-8-sig", newline=""))]
    rows = [one(s, w) for s in samples for w in (4, 8)]
    (HERE / "B32_WIDTH_COUNTS.json").write_text(json.dumps({"rows": len(rows), "success": sum(r["status"] == "success" for r in rows), "failed": sum(r["status"] != "success" for r in rows)}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
