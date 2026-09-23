"""Serial guarded runner; outputs live on D: and never overwrite prior evidence."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PYTHON = ROOT / "baseline" / "evidence" / "COUNT-MATCHED-READY-001" / "venv" / "Scripts" / "python.exe"
OUTPUT = Path("D:/HEST1000BenchRun/COUNT-SUPPORT-PREDECESSOR-50-001")
PROTOCOL = json.loads((HERE / "PROTOCOL.json").read_text(encoding="utf-8"))
RUN_START = time.monotonic()
ARMS = [("SPATIAL_M00", "spatial", 0), ("SPATIAL_M02", "spatial", 2), ("SPATIAL_M04", "spatial", 4),
        ("SPATIAL_M06", "spatial", 6), ("SPATIAL_M08", "spatial", 8), ("SPATIAL_M12", "spatial", 12),
        ("SPATIAL_M16", "spatial", 16), ("ROW_M06", "row", 6)]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def call(stage, folder, **kwargs):
    command = [str(PYTHON), "-X", "utf8", "-B", str(HERE / "worker.py"), stage, "--report", str(folder / f"{stage}.json")]
    for key, value in kwargs.items():
        if value is not None:
            command.extend(["--" + key.replace("_", "-"), str(value)])
    environment = os.environ.copy()
    environment.update({key: "1" for key in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"]})
    environment["PYTHONUTF8"] = "1"
    start = time.monotonic()
    peak = 0
    failure = None
    with (folder / f"{stage}.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
        while process.poll() is None:
            try:
                parent = psutil.Process(process.pid)
                rss = 0
                for item in [parent, *parent.children(recursive=True)]:
                    try:
                        rss += item.memory_info().rss
                    except psutil.NoSuchProcess:
                        pass
                peak = max(peak, rss)
            except psutil.NoSuchProcess:
                pass
            if (time.monotonic() - start > 1800 or time.monotonic() - RUN_START > 43200 or
                    peak > 8 * 2**30 or shutil.disk_usage(OUTPUT.parent).free < 30 * 2**30):
                failure = "resource ceiling"
                try:
                    for child in psutil.Process(process.pid).children(recursive=True):
                        child.kill()
                except psutil.NoSuchProcess:
                    pass
                process.kill()
                process.wait()
                break
            time.sleep(0.2)
    write(folder / f"{stage}_resource.json", {"command": command, "returncode": process.returncode,
          "elapsed_seconds": time.monotonic() - start, "sampled_peak_rss_bytes": peak, "failure": failure})
    if process.returncode:
        raise RuntimeError(f"{stage} failed: {folder / (stage + '.log')}")
    return json.loads((folder / f"{stage}.json").read_text(encoding="utf-8"))


def run_arm(sample, anchor, arm, kind, width, attempt, branch="main"):
    folder = OUTPUT / branch / sample["id"] / arm / f"attempt{attempt:02d}"
    folder.mkdir(parents=True, exist_ok=False)
    result = {"sample_id": sample["id"], "arm": arm, "kind": kind, "width": width, "status": "PENDING"}
    write(folder / "RESULT.json", result)
    stage = "encode"
    try:
        if sha(sample["source_path"]) != sample["source_sha256"] or sha(anchor["archive_path"]) != anchor["archive_sha256"]:
            raise ValueError("source or anchor drift")
        encoded = call("encode", folder, source=sample["source_path"], anchor=anchor["archive_path"], archive=folder / "archive.cnt", kind=kind, width=width)
        stage = "decode"
        decoded = call("decode", folder, archive=folder / "archive.cnt", output=folder / "decoded")
        stage = "verify"
        verified = call("verify", folder, source=sample["source_path"], output=folder / "decoded")
        stage = "ledger"
        paid = call("ledger", folder, archive=folder / "archive.cnt")
        if paid["total_archive_bytes"] != encoded["total_archive_bytes"] or sum(paid["categories"].values()) != paid["total_archive_bytes"]:
            raise ValueError("ledger total")
        if kind == "spatial" and width == 6 and (not encoded["m6_anchor_support_stream_identical"] or not encoded["m6_anchor_support_model_identical"]):
            raise ValueError("M6 anchor regression")
        result.update(status="success", source_sha256=sample["source_sha256"], anchor_archive_sha256=anchor["archive_sha256"],
                      total_archive_bytes=encoded["total_archive_bytes"], archive_sha256=encoded["archive_sha256"],
                      support_nll_bits=encoded["support_nll_bits"], diagnostics=encoded["diagnostics"],
                      m6_anchor_support_stream_identical=encoded["m6_anchor_support_stream_identical"],
                      m6_anchor_support_model_identical=encoded["m6_anchor_support_model_identical"],
                      ledger=paid["categories"], members=paid["members"], decode=decoded, exact=verified,
                      n_obs=int(sample["n_spots"]), n_vars=int(sample["n_genes"]), n_nonzero=int(sample["n_nonzero"]),
                      platform=sample["st_technology"], species=sample["species"], organ=sample["organ"])
        npz = folder / "decoded" / "decoded.npz"
        write(folder / "DECODED_RETENTION.json", {"bytes": npz.stat().st_size, "sha256": sha(npz), "removed_after_exact": True})
        npz.unlink()
    except Exception as error:
        result.update(status={"decode": "DECODE_FAILED", "verify": "EXACT_MISMATCH", "ledger": "LEDGER_FAILED"}.get(stage, "ENCODE_FAILED"), error=repr(error), stage=stage)
    write(folder / "RESULT.json", result)
    return result, folder


def main():
    if not json.loads((HERE / "REVIEW_RELEASE.json").read_text(encoding="utf-8")).get("approved"):
        raise RuntimeError("review not released")
    preflight = json.loads((HERE / "PREFLIGHT.json").read_text(encoding="utf-8"))
    if not preflight.get("all_pass"):
        raise RuntimeError("preflight not accepted")
    for name, expected in json.loads((HERE / "RUN_PINS.json").read_text(encoding="utf-8")).items():
        if sha(HERE / name) != expected:
            raise RuntimeError("pin drift: " + name)
    samples = list(csv.DictReader((HERE / "DATA_SPLIT.csv").open(encoding="utf-8-sig")))
    anchors = json.loads((HERE / "ANCHORS.json").read_text(encoding="utf-8"))
    OUTPUT.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(HERE / "PROTOCOL.json", OUTPUT / "PROTOCOL.json")
    index = {sample["id"]: {arm: {"status": "PENDING"} for arm, _, _ in ARMS} for sample in samples}
    write(OUTPUT / "INDEX.json", index)
    failures = []
    started = time.monotonic()
    for sample in samples:
        for arm, kind, width in ARMS:
            accepted = None
            for attempt in (1, 2):
                result, folder = run_arm(sample, anchors[sample["id"]], arm, kind, width, attempt)
                if result["status"] == "success":
                    accepted = folder / "RESULT.json"
                    break
                failed_stage = result.get("stage", "encode")
                failed_log = folder / f"{failed_stage}.log"
                logs = failed_log.read_text(errors="replace") if failed_log.exists() else ""
                logs_lower = logs.lower()
                receipts = [json.loads(path.read_text()) for path in folder.glob("*_resource.json")]
                resource_failure = any(receipt.get("failure") for receipt in receipts)
                retry = (not resource_failure and result["status"] in ("ENCODE_FAILED", "DECODE_FAILED") and
                         ("access violation" in logs_lower or
                          ("numba" in logs_lower and ("import" in logs_lower or "cache" in logs_lower))))
                failures.append({"sample_id": sample["id"], "arm": arm, "attempt": attempt, "retry_eligible": retry, "record_path": str(folder / "RESULT.json")})
                if not retry:
                    break
            if accepted is None:
                write(OUTPUT / "FAILURES.json", failures)
                raise RuntimeError(f"failed without accepted archive: {sample['id']} {arm}")
            index[sample["id"]][arm] = {"status": "success", "record_path": str(accepted)}
            write(OUTPUT / "INDEX.json", index)
            complete = sum(v["status"] == "success" for arms in index.values() for v in arms.values())
            write(OUTPUT / "PROGRESS.json", {"status": "running", "success": complete, "planned": len(samples) * len(ARMS),
                  "failed_attempts": len(failures), "sample_id": sample["id"], "arm": arm, "wall_seconds": time.monotonic() - started})
            print(sample["id"], arm, json.loads(accepted.read_text())["total_archive_bytes"], flush=True)
    write(OUTPUT / "FAILURES.json", failures)
    write(OUTPUT / "PROGRESS.json", {"status": "encoded_decoded_exact", "success": 400, "planned": 400,
          "failed_attempts": len(failures), "wall_seconds": time.monotonic() - started})
    subprocess.run([str(PYTHON), "-X", "utf8", "-B", str(HERE / "analyze.py")], cwd=ROOT, check=True)
    selection = json.loads((HERE / "SELECTION.json").read_text(encoding="utf-8"))["selected"]
    chosen = next(item for item in ARMS if item[0] == selection["arm"])
    sample = samples[0]
    reproduced, folder = run_arm(sample, anchors[sample["id"]], *chosen, attempt=1, branch="reproduction")
    main_record = json.loads(Path(index[sample["id"]][chosen[0]]["record_path"]).read_text(encoding="utf-8"))
    reproduction = {"sample_id": sample["id"], "arm": chosen[0], "main_sha256": main_record["archive_sha256"],
                    "reproduction_sha256": reproduced["archive_sha256"],
                    "byte_identical": main_record["archive_sha256"] == reproduced["archive_sha256"],
                    "record_path": str(folder / "RESULT.json")}
    write(HERE / "REPRODUCTION.json", reproduction)
    if not reproduction["byte_identical"]:
        raise RuntimeError("reproduction mismatch")
    subprocess.run([str(PYTHON), "-X", "utf8", "-B", str(HERE / "audit_final.py")], cwd=ROOT, check=True)
    write(OUTPUT / "DONE.json", {"archives": 400, "selected_arm": chosen[0], "reproduction": reproduction,
          "failed_attempts": len(failures), "wall_seconds": time.monotonic() - started})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        write(OUTPUT / "RUN_ERROR.json", {"traceback": traceback.format_exc()})
        raise
