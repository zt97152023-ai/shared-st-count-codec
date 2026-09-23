"""Run M_v scan on the selected B32/M_s=6 development candidate."""
from __future__ import annotations
import csv, hashlib, json, os, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT / "baseline/evidence/COUNT-PRODUCTION-SHARED-ABLATIONS-50-001"
WORKER = OLD / "worker.py"
MANIFEST = ROOT / "baseline/evidence/COUNT-SUPPORT-PREDECESSOR-50-001/DATA_SPLIT.csv"
SOURCE_ROOT = Path(r"E:/Hestdata/st")


def run(cmd, env, log, timeout=600):
    p = subprocess.run([sys.executable, "-X", "utf8", *map(str, cmd)], env=env,
                       text=True, capture_output=True, timeout=timeout)
    log.write_text((p.stdout or "") + (p.stderr or ""), encoding="utf-8")
    if p.returncode:
        raise RuntimeError(f"rc={p.returncode}: {cmd}")


def one(sample, mv):
    arm = f"MV{mv}"
    folder = HERE / "main/b32_value" / sample / arm
    folder.mkdir(parents=True, exist_ok=True)
    prior = folder / "RESULT.json"
    try:
        x = json.loads(prior.read_text(encoding="utf-8"))
        if x.get("status") == "success" and x.get("verify_all") is True:
            return x
    except Exception:
        pass
    env = os.environ.copy(); env.pop("NUMBA_DISABLE_CACHING", None)
    env["NUMBA_CACHE_DIR"] = str(HERE / "numba_cache_b32_value" / sample / arm)
    env["PYTHONHASHSEED"] = "0"
    archive = folder / "archive.cnt"
    base = HERE / "main/bucket" / sample / "B32/archive.cnt"
    try:
        if not archive.is_file():
            run([WORKER, "value_context", "--sample", sample, "--output", archive,
                 "--scratch", folder / "scratch", "--report", folder / "encode.json",
                 "--value-context", str(mv), "--package", base], env, folder / "encode.log")
        decoded = folder / "decoded"
        if decoded.exists(): shutil.rmtree(decoded)
        run([WORKER, "decode", "--package", archive, "--output", decoded,
             "--report", folder / "decode.json"], env, folder / "decode.log")
        run([WORKER, "verify", "--sample", sample, "--source", SOURCE_ROOT / f"{sample}.h5ad",
             "--output", decoded, "--report", folder / "verify.json"], env, folder / "verify.log")
        run([WORKER, "ledger", "--package", archive, "--report", folder / "ledger.json"], env, folder / "ledger.log")
        verified = json.loads((folder / "verify.json").read_text(encoding="utf-8"))
        ledger = json.loads((folder / "ledger.json").read_text(encoding="utf-8"))["ledger"][0]
        row = {"stage": "b32_value", "sample_id": sample, "arm": arm, "status": "success",
               "verify_all": bool(verified.get("all")),
               "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
               "total_archive_bytes": archive.stat().st_size, **ledger}
        prior.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        return row
    except Exception as exc:
        row = {"stage": "b32_value", "sample_id": sample, "arm": arm, "status": "failed", "error": repr(exc)}
        (folder / "FAILURE.json").write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        prior.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        return row


def main():
    samples = [r["id"] for r in csv.DictReader(MANIFEST.open(encoding="utf-8-sig", newline=""))]
    jobs = [(s, mv) for s in samples for mv in (0, 2, 4, 6, 8, 12)]
    rows = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = [ex.submit(one, s, mv) for s, mv in jobs]
        for f in as_completed(futures): rows.append(f.result())
    (HERE / "B32_VALUE_COUNTS.json").write_text(json.dumps({"rows": len(rows), "success": sum(x["status"] == "success" for x in rows), "failed": sum(x["status"] != "success" for x in rows)}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
