"""Resume the immutable 50-slice support calibration after an orchestrator interruption.

This script never overwrites an accepted arm.  It finishes the single interrupted
TENX135/ROW_M06 attempt from its already written archive and decoded object, then
executes only INDEX entries that remain PENDING.
"""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
import time
from pathlib import Path

import run as core


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def finalize_interrupted(sample, anchor, arm, kind, width, folder: Path):
    """Re-run decode, then finish verify/ledger for an interrupted accepted archive."""
    required = [folder / "archive.cnt", folder / "encode.json"]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError({"interrupted_attempt_missing": missing})
    result = load(folder / "RESULT.json")
    if result.get("status") != "PENDING":
        raise RuntimeError("interrupted attempt is not PENDING")
    if core.sha(sample["source_path"]) != sample["source_sha256"] or core.sha(anchor["archive_path"]) != anchor["archive_sha256"]:
        raise RuntimeError("source or anchor drift during resume")
    encoded = load(folder / "encode.json")
    if core.sha(folder / "archive.cnt") != encoded["archive_sha256"]:
        raise RuntimeError("interrupted archive hash drift")
    preserved = {}
    for name in ["decode.json", "decode.log"]:
        source = folder / name
        target = folder / ("interrupted_" + name)
        if not source.exists() or target.exists():
            raise RuntimeError("cannot preserve interrupted decode evidence: " + name)
        shutil.copyfile(source, target)
        preserved[name] = {"preserved_as": target.name, "sha256": core.sha(target)}
    resumed_output = folder / "decoded_resume"
    if resumed_output.exists():
        raise RuntimeError("decoded_resume already exists")
    decoded = core.call("decode", folder, archive=folder / "archive.cnt", output=resumed_output)
    verified = core.call("verify", folder, source=sample["source_path"], output=resumed_output)
    paid = core.call("ledger", folder, archive=folder / "archive.cnt")
    if paid["total_archive_bytes"] != encoded["total_archive_bytes"] or sum(paid["categories"].values()) != paid["total_archive_bytes"]:
        raise RuntimeError("interrupted ledger total mismatch")
    result.update(status="success", source_sha256=sample["source_sha256"], anchor_archive_sha256=anchor["archive_sha256"],
                  total_archive_bytes=encoded["total_archive_bytes"], archive_sha256=encoded["archive_sha256"],
                  support_nll_bits=encoded["support_nll_bits"], diagnostics=encoded["diagnostics"],
                  m6_anchor_support_stream_identical=encoded["m6_anchor_support_stream_identical"],
                  m6_anchor_support_model_identical=encoded["m6_anchor_support_model_identical"],
                  ledger=paid["categories"], members=paid["members"], decode=decoded, exact=verified,
                  n_obs=int(sample["n_spots"]), n_vars=int(sample["n_genes"]), n_nonzero=int(sample["n_nonzero"]),
                  platform=sample["st_technology"], species=sample["species"], organ=sample["organ"],
                  orchestration_resume="fresh_decode_then_verify_and_ledger_of_the_hash_verified_interrupted_archive",
                  interrupted_decode_evidence=preserved)
    npz = resumed_output / "decoded.npz"
    core.write(folder / "DECODED_RETENTION.json", {"bytes": npz.stat().st_size, "sha256": core.sha(npz), "removed_after_exact": True})
    npz.unlink()
    core.write(folder / "RESULT.json", result)
    return result


def main():
    if not load(core.HERE / "REVIEW_RELEASE.json").get("approved"):
        raise RuntimeError("review not released")
    if not load(core.HERE / "PREFLIGHT.json").get("all_pass"):
        raise RuntimeError("preflight not accepted")
    for name, expected in load(core.HERE / "RUN_PINS.json").items():
        if core.sha(core.HERE / name) != expected:
            raise RuntimeError("pin drift: " + name)
    resume_pins = load(core.HERE / "RESUME_PIN.json")
    for name, expected in resume_pins.items():
        if core.sha(core.HERE / name) != expected:
            raise RuntimeError("resume pin drift: " + name)
    if not core.OUTPUT.exists():
        raise RuntimeError("nothing to resume")

    samples = list(csv.DictReader((core.HERE / "DATA_SPLIT.csv").open(encoding="utf-8-sig")))
    sample_map = {sample["id"]: sample for sample in samples}
    anchors = load(core.HERE / "ANCHORS.json")
    index = load(core.OUTPUT / "INDEX.json")
    failures = load(core.OUTPUT / "FAILURES.json") if (core.OUTPUT / "FAILURES.json").exists() else []
    previous = load(core.OUTPUT / "PROGRESS.json")
    prior_wall = float(previous.get("wall_seconds", 0.0))
    started = time.monotonic()
    interruptions = [{"type": "orchestrator_session_termination", "accepted_arms_before_resume": 311,
                      "incomplete_arm": "TENX135/ROW_M06/attempt01", "codec_failure": False}]

    for sample in samples:
        for arm, kind, width in core.ARMS:
            if index[sample["id"]][arm].get("status") == "success":
                continue
            arm_root = core.OUTPUT / "main" / sample["id"] / arm
            partial = arm_root / "attempt01"
            if partial.exists():
                if sample["id"] != "TENX135" or arm != "ROW_M06":
                    raise RuntimeError("unexpected partial attempt: " + str(partial))
                result = finalize_interrupted(sample, anchors[sample["id"]], arm, kind, width, partial)
                accepted = partial / "RESULT.json"
            else:
                accepted = None
                for attempt in (1, 2):
                    result, folder = core.run_arm(sample, anchors[sample["id"]], arm, kind, width, attempt=attempt)
                    if result["status"] == "success":
                        accepted = folder / "RESULT.json"
                        break
                    failed_stage = result.get("stage", "encode")
                    failed_log = folder / f"{failed_stage}.log"
                    logs = failed_log.read_text(errors="replace") if failed_log.exists() else ""
                    logs_lower = logs.lower()
                    receipts = [load(path) for path in folder.glob("*_resource.json")]
                    resource_failure = any(receipt.get("failure") for receipt in receipts)
                    retry = (attempt == 1 and not resource_failure and
                             result["status"] in ("ENCODE_FAILED", "DECODE_FAILED") and
                             ("access violation" in logs_lower or
                              ("numba" in logs_lower and ("import" in logs_lower or "cache" in logs_lower))))
                    failures.append({"sample_id": sample["id"], "arm": arm, "attempt": attempt,
                                     "retry_eligible": retry, "record_path": str(folder / "RESULT.json"),
                                     "resume_phase": True})
                    if not retry:
                        break
                if accepted is None:
                    core.write(core.OUTPUT / "FAILURES.json", failures)
                    raise RuntimeError(f"resume arm failed: {sample['id']} {arm}")
            index[sample["id"]][arm] = {"status": "success", "record_path": str(accepted)}
            core.write(core.OUTPUT / "INDEX.json", index)
            complete = sum(value.get("status") == "success" for arms in index.values() for value in arms.values())
            core.write(core.OUTPUT / "PROGRESS.json", {"status": "running", "success": complete, "planned": 400,
                       "failed_attempts": len(failures), "sample_id": sample["id"], "arm": arm,
                       "wall_seconds": prior_wall + time.monotonic() - started, "resumed": True})
            print(sample["id"], arm, result["total_archive_bytes"], flush=True)

    core.write(core.OUTPUT / "FAILURES.json", failures)
    core.write(core.OUTPUT / "INTERRUPTIONS.json", interruptions)
    core.write(core.OUTPUT / "PROGRESS.json", {"status": "encoded_decoded_exact", "success": 400, "planned": 400,
               "failed_attempts": len(failures), "wall_seconds": prior_wall + time.monotonic() - started, "resumed": True})
    subprocess.run([str(core.PYTHON), "-X", "utf8", "-B", str(core.HERE / "analyze.py")], cwd=core.ROOT, check=True)
    selection = load(core.HERE / "SELECTION.json")["selected"]
    chosen = next(item for item in core.ARMS if item[0] == selection["arm"])
    first = samples[0]
    reproduced, folder = core.run_arm(first, anchors[first["id"]], *chosen, attempt=1, branch="reproduction")
    main_record = load(Path(index[first["id"]][chosen[0]]["record_path"]))
    reproduction = {"sample_id": first["id"], "arm": chosen[0], "main_sha256": main_record["archive_sha256"],
                    "reproduction_sha256": reproduced["archive_sha256"],
                    "byte_identical": main_record["archive_sha256"] == reproduced["archive_sha256"],
                    "record_path": str(folder / "RESULT.json")}
    core.write(core.HERE / "REPRODUCTION.json", reproduction)
    if not reproduction["byte_identical"]:
        raise RuntimeError("reproduction mismatch")
    subprocess.run([str(core.PYTHON), "-X", "utf8", "-B", str(core.HERE / "audit_final.py")], cwd=core.ROOT, check=True)
    core.write(core.OUTPUT / "DONE.json", {"archives": 400, "selected_arm": chosen[0], "reproduction": reproduction,
               "failed_attempts": len(failures), "orchestration_interruptions": interruptions,
               "wall_seconds": prior_wall + time.monotonic() - started})


if __name__ == "__main__":
    main()
