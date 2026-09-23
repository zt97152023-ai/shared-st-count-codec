"""Rebuild the three TENX96 archives truncated during the earlier disk-full event."""
from __future__ import annotations
import hashlib, json, os, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT / "baseline/evidence/COUNT-PRODUCTION-SHARED-ABLATIONS-50-001"
WORKER = OLD / "worker.py"
SOURCE = Path(r"E:/Hestdata/st/TENX96.h5ad")


def run(cmd, env, log):
    p = subprocess.run([sys.executable, "-X", "utf8", *map(str, cmd)], env=env,
                       text=True, capture_output=True, timeout=900)
    log.write_text((p.stdout or "") + (p.stderr or ""), encoding="utf-8")
    if p.returncode:
        raise RuntimeError(f"rc={p.returncode}: {cmd}")


def main():
    rows = []
    for mv in (0, 2, 4):
        folder = HERE / "retry/value/TENX96" / f"MV{mv}"
        folder.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy(); env.pop("NUMBA_DISABLE_CACHING", None)
        env["NUMBA_CACHE_DIR"] = str(HERE / "numba_cache_repair" / f"MV{mv}")
        env["PYTHONHASHSEED"] = "0"
        archive = folder / "archive_rebuilt.cnt"
        try:
            run([WORKER, "value_context", "--sample", "TENX96", "--output", archive,
                 "--scratch", folder / "scratch_rebuilt", "--report", folder / "encode_rebuilt.json",
                 "--value-context", str(mv), "--package",
                 OLD / "main_v3/bucket/TENX96/B16/archive.cnt"], env, folder / "encode_rebuilt.log")
            decoded = folder / "decoded_rebuilt"
            run([WORKER, "decode", "--package", archive, "--output", decoded,
                 "--report", folder / "decode_rebuilt.json"], env, folder / "decode_rebuilt.log")
            run([WORKER, "verify", "--sample", "TENX96", "--source", SOURCE,
                 "--output", decoded, "--report", folder / "verify_rebuilt.json"], env, folder / "verify_rebuilt.log")
            run([WORKER, "ledger", "--package", archive,
                 "--report", folder / "ledger_rebuilt.json"], env, folder / "ledger_rebuilt.log")
            verified = json.loads((folder / "verify_rebuilt.json").read_text(encoding="utf-8"))
            ledger = json.loads((folder / "ledger_rebuilt.json").read_text(encoding="utf-8"))["ledger"][0]
            row = {"stage": "value", "sample_id": "TENX96", "arm": f"MV{mv}", "status": "success",
                   "verify_all": bool(verified.get("all")),
                   "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                   "total_archive_bytes": archive.stat().st_size, **ledger,
                   "archive_variant": "archive_rebuilt.cnt"}
            (folder / "RESULT_REBUILT.json").write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
            (folder / "SUCCESS.json").write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
            rows.append(row)
        except Exception as exc:
            row = {"stage": "value", "sample_id": "TENX96", "arm": f"MV{mv}", "status": "failed", "error": repr(exc)}
            (folder / "FAILURE_REBUILT.json").write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
            rows.append(row)
    (HERE / "TENX96_REPAIR_COUNTS.json").write_text(json.dumps({"rows": len(rows), "success": sum(r["status"] == "success" for r in rows), "failed": sum(r["status"] != "success" for r in rows)}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
