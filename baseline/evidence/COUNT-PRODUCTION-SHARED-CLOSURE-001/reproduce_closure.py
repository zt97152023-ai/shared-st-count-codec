"""Fresh-process decode/verify/ledger reproductions for final candidate evidence."""
from __future__ import annotations
import hashlib, json, os, subprocess, sys, shutil
from pathlib import Path
import analyze_closure as ac

HERE = ac.HERE
ROOT = ac.ROOT
WORKER = ac.WORKER if hasattr(ac, "WORKER") else ROOT / "baseline/evidence/COUNT-PRODUCTION-SHARED-ABLATIONS-50-001/worker.py"
SOURCE_ROOT = Path(r"E:/Hestdata/st")


def run(cmd, env, log):
    p = subprocess.run([sys.executable, "-X", "utf8", *map(str, cmd)], env=env,
                       text=True, capture_output=True, timeout=600)
    log.write_text((p.stdout or "") + (p.stderr or ""), encoding="utf-8")
    if p.returncode:
        raise RuntimeError(f"rc={p.returncode}: {cmd}")


def main():
    cases = [("bucket_B32", "bucket", "NCBI180", "B32"),
             ("joint_B16_M8", "joint", "NCBI180", "B16_M8"),
             ("b32_value_MV6", "b32_value", "NCBI180", "MV6")]
    out = []
    for name, stage, sample, arm in cases:
        expected, folder = ac.effective(stage, sample, arm)
        if not expected:
            raise RuntimeError(f"missing effective case {name}")
        archive = ac.archive_path(stage, sample, arm, folder)
        if not archive:
            raise RuntimeError(f"missing archive {name}")
        dest = HERE / "reproduction" / name
        dest.mkdir(parents=True, exist_ok=True)
        decoded = dest / "decoded"
        if decoded.exists(): shutil.rmtree(decoded)
        env = os.environ.copy(); env.pop("NUMBA_DISABLE_CACHING", None)
        env["NUMBA_CACHE_DIR"] = str(HERE / "numba_cache_reproduction" / name)
        env["PYTHONHASHSEED"] = "0"
        run([WORKER, "decode", "--package", archive, "--output", decoded,
             "--report", dest / "decode.json"], env, dest / "decode.log")
        run([WORKER, "verify", "--sample", sample, "--source", SOURCE_ROOT / f"{sample}.h5ad",
             "--output", decoded, "--report", dest / "verify.json"], env, dest / "verify.log")
        run([WORKER, "ledger", "--package", archive, "--report", dest / "ledger.json"], env, dest / "ledger.log")
        verified = json.loads((dest / "verify.json").read_text(encoding="utf-8"))
        row = {"case": name, "stage": stage, "sample_id": sample, "arm": arm,
               "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
               "archive_sha_matches_effective": hashlib.sha256(archive.read_bytes()).hexdigest() == expected.get("archive_sha256"),
               "verify_all": bool(verified.get("all")), "fresh_process": True}
        row["pass"] = bool(row["archive_sha_matches_effective"] and row["verify_all"])
        out.append(row)
        shutil.rmtree(decoded)
    (HERE / "REPRODUCTION.json").write_text(json.dumps({"all": all(x["pass"] for x in out), "cases": out}, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
