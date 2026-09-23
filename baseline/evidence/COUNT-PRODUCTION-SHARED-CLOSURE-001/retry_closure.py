"""Fresh-process retries for failed closure arms; preserves raw failures."""
from __future__ import annotations
import csv, hashlib, json, os, shutil, subprocess, sys
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
        raise RuntimeError(f"worker failed rc={p.returncode}: {cmd}")


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def effective_success(folder):
    for name in ("SUCCESS.json", "RESULT.json"):
        p = folder / name
        if p.is_file():
            try:
                x = load_json(p)
                if x.get("status") == "success" and x.get("verify_all") is True:
                    return x
            except Exception:
                pass
    return None


def retry_one(stage, sample, arm, main_folder):
    retry_folder = HERE / "retry" / stage / sample / arm
    retry_folder.mkdir(parents=True, exist_ok=True)
    saved = effective_success(retry_folder)
    if saved:
        return saved
    archive = main_folder / "archive.cnt"
    if not archive.is_file():
        return {"stage": stage, "sample_id": sample, "arm": arm, "status": "failed",
                "error": "missing main archive"}
    # Preserve an earlier retry failure, then refresh only disposable retry outputs.
    old_failure = retry_folder / "RESULT.json"
    if old_failure.is_file() and not (retry_folder / "FAILURE.previous.json").is_file():
        shutil.copy2(old_failure, retry_folder / "FAILURE.previous.json")
    decoded = retry_folder / "decoded"
    if decoded.exists():
        shutil.rmtree(decoded)
    env = os.environ.copy()
    env.pop("NUMBA_DISABLE_CACHING", None)
    env["NUMBA_CACHE_DIR"] = str(HERE / "numba_cache_retry" / stage / sample / arm)
    env["PYTHONHASHSEED"] = "0"
    try:
        run([WORKER, "decode", "--package", archive, "--output", decoded,
             "--report", retry_folder / "decode.json"], env, retry_folder / "decode.log")
        run([WORKER, "verify", "--sample", sample, "--source",
             SOURCE_ROOT / f"{sample}.h5ad", "--output", decoded,
             "--report", retry_folder / "verify.json"], env, retry_folder / "verify.log")
        run([WORKER, "ledger", "--package", archive,
             "--report", retry_folder / "ledger.json"], env, retry_folder / "ledger.log")
        verified = load_json(retry_folder / "verify.json")
        ledger = load_json(retry_folder / "ledger.json")["ledger"][0]
        row = {"stage": stage, "sample_id": sample, "arm": arm, "status": "success",
               "verify_all": bool(verified.get("all")),
               "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
               "total_archive_bytes": archive.stat().st_size, **ledger}
        (retry_folder / "RESULT.json").write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        (retry_folder / "SUCCESS.json").write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        return row
    except Exception as exc:
        row = {"stage": stage, "sample_id": sample, "arm": arm, "status": "failed",
               "error": repr(exc)}
        (retry_folder / "FAILURE.json").write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        (retry_folder / "RESULT.json").write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        return row


def main():
    samples = [r["id"] for r in csv.DictReader(MANIFEST.open(encoding="utf-8-sig", newline=""))]
    parser = __import__("argparse").ArgumentParser()
    parser.add_argument("--stage", choices=["bucket", "joint", "value", "all"], default="all")
    args = parser.parse_args()
    stages = ["bucket", "joint", "value"] if args.stage == "all" else [args.stage]
    rows = []
    for stage in stages:
        for sample in samples:
            arms = ["B32"] if stage == "bucket" else (["B16_M4", "B16_M8"] if stage == "joint" else [f"MV{x}" for x in (0, 2, 4, 6, 8, 12)])
            for arm in arms:
                main_folder = HERE / "main" / stage / sample / arm
                main_result = main_folder / "RESULT.json"
                should_retry = True
                if main_result.is_file():
                    try:
                        should_retry = load_json(main_result).get("status") != "success"
                    except Exception:
                        pass
                if not should_retry:
                    continue
                rows.append(retry_one(stage, sample, arm, main_folder))
    out = HERE / "RETRY_COUNTS.json"
    out.write_text(json.dumps({"rows": len(rows), "success": sum(x.get("status") == "success" for x in rows),
                               "failed": sum(x.get("status") != "success" for x in rows)}, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
