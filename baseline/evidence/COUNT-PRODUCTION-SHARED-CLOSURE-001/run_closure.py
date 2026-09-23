"""Run the pre-registered closure arms in isolated fresh subprocesses."""
from __future__ import annotations
import csv, json, os, subprocess, sys, time
import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT / "baseline/evidence/COUNT-PRODUCTION-SHARED-ABLATIONS-50-001"
WORKER = OLD / "worker.py"
MANIFEST = ROOT / "baseline/evidence/COUNT-SUPPORT-PREDECESSOR-50-001/DATA_SPLIT.csv"
SOURCE_ROOT = Path(r"E:\Hestdata\st")


def run(cmd, env, log):
    p = subprocess.run([sys.executable, "-X", "utf8", *map(str, cmd)], env=env, text=True, capture_output=True, timeout=120)
    log.write_text((p.stdout or "") + (p.stderr or ""), encoding="utf-8")
    if p.returncode:
        raise RuntimeError(f"worker failed rc={p.returncode}: {cmd}")


def result_for(stage, sample, arm, folder, extra):
    folder.mkdir(parents=True, exist_ok=True)
    prior = folder / "RESULT.json"
    if prior.is_file():
        try:
            saved = json.loads(prior.read_text(encoding="utf-8"))
            if saved.get("status") == "success" and saved.get("verify_all") is True:
                return saved
            if saved.get("status") == "failed":
                return saved
        except Exception:
            pass
    retry_prior = HERE / "retry" / stage / sample / arm / "RESULT.json"
    if retry_prior.is_file():
        try:
            saved = json.loads(retry_prior.read_text(encoding="utf-8"))
            if saved.get("status") == "success" and saved.get("verify_all") is True:
                return saved
        except Exception:
            pass
    env = os.environ.copy()
    env.pop("NUMBA_DISABLE_CACHING", None)
    env["NUMBA_CACHE_DIR"] = str(HERE / "numba_cache" / stage / sample / arm)
    env["PYTHONHASHSEED"] = "0"
    archive = folder / "archive.cnt"
    scratch = folder / "scratch"
    worker_stage = "bucket" if stage == "joint" else stage
    encode = [WORKER, worker_stage, "--sample", sample, "--output", archive, "--scratch", scratch, "--report", folder / "encode.json"] + extra
    try:
        if not archive.is_file():
            run(encode, env, folder / "encode.log")
        run([WORKER, "decode", "--package", archive, "--output", folder / "decoded", "--report", folder / "decode.json"], env, folder / "decode.log")
        run([WORKER, "verify", "--sample", sample, "--source", SOURCE_ROOT / f"{sample}.h5ad", "--output", folder / "decoded", "--report", folder / "verify.json"], env, folder / "verify.log")
        run([WORKER, "ledger", "--package", archive, "--report", folder / "ledger.json"], env, folder / "ledger.log")
        encoded = json.loads((folder / "encode.json").read_text(encoding="utf-8"))
        verified = json.loads((folder / "verify.json").read_text(encoding="utf-8"))
        ledger = json.loads((folder / "ledger.json").read_text(encoding="utf-8"))["ledger"][0]
        row = {"stage": stage, "sample_id": sample, "arm": arm, "status": "success", "verify_all": bool(verified.get("all")),
               "archive_sha256": encoded["archive_sha256"], "total_archive_bytes": int(encoded["total_archive_bytes"]), **ledger}
        (folder / "RESULT.json").write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        return row
    except Exception as exc:
        row = {"stage": stage, "sample_id": sample, "arm": arm, "status": "failed", "error": repr(exc)}
        (folder / "FAILURE.json").write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        (folder / "RESULT.json").write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["all", "bucket", "joint", "value"], default="all")
    args = parser.parse_args()
    samples = [r["id"] for r in csv.DictReader(MANIFEST.open(encoding="utf-8-sig", newline=""))]
    rows = []
    if args.phase in ("all", "bucket"):
        for sample in samples:
            rows.append(result_for("bucket", sample, "B32", HERE / "main/bucket" / sample / "B32", ["--buckets", "32", "--width", "6"]))
    if args.phase in ("all", "joint"):
        for sample in samples:
            for width in (4, 8):
                rows.append(result_for("joint", sample, f"B16_M{width}", HERE / "main/joint" / sample / f"B16_M{width}", ["--buckets", "16", "--width", str(width)]))
    if args.phase in ("all", "value"):
        for sample in samples:
            base = OLD / "main_v3/bucket" / sample / "B16/archive.cnt"
            for mv in (0, 2, 4, 6, 8, 12):
                rows.append(result_for("value_context", sample, f"MV{mv}", HERE / "main/value" / sample / f"MV{mv}", ["--value-context", str(mv), "--package", base]))
    (HERE / "RUN_COUNTS.json").write_text(json.dumps({"bucket_B32": 50, "joint_B16_M4_M8": 100, "value_context_Mv0_2_4_6_8_12": 300, "rows": len(rows), "failures": sum(r["status"] != "success" for r in rows)}, indent=2), encoding="utf-8")
    with (HERE / "PER_CASE_RESULTS.csv").open("w", encoding="utf-8", newline="") as h:
        fields = ["stage", "sample_id", "arm", "status", "verify_all", "archive_sha256", "total_archive_bytes", "support_stream", "value_stream", "support_model", "value_model_and_group_map", "graph_index", "identity_coordinates_metadata", "mapping", "manifest", "zip_framing"]
        w = csv.DictWriter(h, fieldnames=fields); w.writeheader(); w.writerows({k: r.get(k, "") for k in fields} for r in rows)


if __name__ == "__main__":
    main()
