"""One-shot, isolated repair run for the two recorded CSR_BZIP2_9 failures.

The frozen comparator/level are unchanged. Output is written to a new D: root;
the old STATE, DONE, failed archives, and RESULT files are read-only evidence.
"""
from __future__ import annotations

import collections
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

RUNNER_PATH = HERE / "runner_resume04.py"
spec = importlib.util.spec_from_file_location("hest_runner_repair", RUNNER_PATH)
rr = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = rr
spec.loader.exec_module(rr)

OLD_OUT = Path(r"D:\HEST1000BenchRun\COUNT-HEST-BASELINES-1000-005-RECOVERED-03")
NEW_OUT = Path(r"D:\HEST1000BenchRun\COUNT-HEST-BASELINES-1000-005-RECOVERED-04")
PLAN_PATH = HERE / "runner_plan_recovered03.json"
WRAPPER = HERE / "extra_worker_checked.py"
REPAIR_PLAN = HERE / "REPAIR_CSR_BZIP2_01.json"
REPAIR_PREFLIGHT = HERE / "REPAIR_CSR_BZIP2_PREFLIGHT_01.json"
RELEASE = HERE / "REPAIR_CSR_BZIP2_RELEASE_01.json"
TARGETS = ["TENX86", "TENX82"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    plan = rr.read(PLAN_PATH)
    rr.check_pins(plan["code_pins"])
    state_path = OLD_OUT / "STATE.json"
    old_state = rr.read(state_path)
    if old_state.get("plan_sha256") != rr.sha(PLAN_PATH):
        raise RuntimeError("recovered run plan hash mismatch")
    active = [p for p in old_state["pairs"].values() if p.get("status") == "running"]
    if active:
        raise RuntimeError("old run still has running rows")
    non_success = {k: v for k, v in old_state["pairs"].items() if v.get("status") != "success"}
    expected_keys = {f"{sid}::CSR_BZIP2_9" for sid in TARGETS}
    if set(non_success) != expected_keys or any(v.get("status") != "decode_failed" for v in non_success.values()):
        raise RuntimeError("unresolved rows differ from the two reviewed decode failures")
    if NEW_OUT.exists():
        raise RuntimeError("repair output already exists; refusing to overwrite")
    if any((HERE / n).exists() for n in [REPAIR_PLAN.name, REPAIR_PREFLIGHT.name, RELEASE.name]):
        raise RuntimeError("repair evidence already exists; refusing to overwrite")

    sample_by_id = {s["sample_id"]: s for s in plan["samples"]}
    prior = {}
    for sid in TARGETS:
        key = f"{sid}::CSR_BZIP2_9"
        rec_path = Path(non_success[key]["record_path"])
        rec = rr.read(rec_path)
        if rec.get("attempt") != 2 or rec.get("status") != "decode_failed":
            raise RuntimeError(f"unexpected terminal failure record for {key}")
        source = Path(sample_by_id[sid]["source_path"])
        if rr.sha(source) != sample_by_id[sid]["source_sha256"]:
            raise RuntimeError(f"frozen source drift for {sid}")
        archive = rec_path.parent / "archive" / "archive.bin"
        with zipfile.ZipFile(archive) as zf:
            if zf.testzip() is not None:
                raise RuntimeError(f"outer ZIP corruption in prior archive for {key}")
            manifest = json.loads(zf.read("manifest.json"))
            raw = zf.read("csr.bz2")
            member_hash_ok = hashlib.sha256(raw).hexdigest() == manifest["files"]["csr.bz2"]["sha256"]
        if not member_hash_ok:
            raise RuntimeError(f"prior CSR member hash mismatch for {key}")
        prior[sid] = {"result_path": str(rec_path), "result_sha256": rr.sha(rec_path),
                      "archive_path": str(archive), "archive_sha256": rr.sha(archive),
                      "csr_member_sha256": hashlib.sha256(raw).hexdigest(),
                      "source_sha256": sample_by_id[sid]["source_sha256"],
                      "canonical_sha256": rec["canonical_sha256"],
                      "metadata_sha256": rr.read(sample_by_id[sid]["record_path"])["exact"]["metadata_sha256"]}

    NEW_OUT.mkdir(parents=True)
    repair_plan = {
        "schema": "hest1000-csr-bzip2-bounded-repair-v1",
        "source_plan_sha256": rr.sha(PLAN_PATH),
        "source_state_sha256": rr.sha(state_path),
        "method": "CSR_BZIP2_9",
        "parameters": {"bzip2_level": 9, "csr_layout": "F047 historical CSR layout",
                       "archive_format": "unchanged ZIP_STORED general-baseline archive"},
        "repair": "one bounded attempt per previously failed sample; encode-side bzip round-trip check before independent decode",
        "retry_limit": {sid: 1 for sid in TARGETS},
        "samples": prior,
        "comparator_sha256": rr.sha(ROOT / "baseline/hest1000/general_baselines.py"),
        "checked_wrapper_sha256": rr.sha(WRAPPER),
        "runner_helper_sha256": rr.sha(RUNNER_PATH),
        "repair_runner_sha256": sha(Path(__file__).resolve()),
        "resource_limits": {"concurrency": 1, "rss_bytes": 16 * 2**30,
                             "stage_seconds": 1800, "disk_reserve_bytes": 20 * 2**30,
                             "output_cap_bytes": 100 * 2**30},
        "output_root": str(NEW_OUT),
    }
    write_json(REPAIR_PLAN, repair_plan)
    start = time.time()
    results = {}
    stage_records = {}

    try:
        for sid in TARGETS:
            sample = sample_by_id[sid]
            key = f"{sid}::CSR_BZIP2_9"
            folder = NEW_OUT / "main" / sid / "CSR_BZIP2_9" / "attempt03"
            folder.mkdir(parents=True)
            result_path = folder / "RESULT.json"
            row = {"sample_id": sid, "method": "CSR_BZIP2_9", "attempt": 3,
                   "status": "running", "prior_failure_path": non_success[key]["record_path"],
                   "source_sha256": sample["source_sha256"]}
            write_json(result_path, row)
            source = Path(sample["source_path"])
            scratch = folder / "scratch"
            decoded = folder / "decoded"

            phase = "prepare"
            stage_records[(sid, phase)] = rr.stage(
                [str(rr.PY), "-X", "utf8", "-B", "-m", "baseline.hest1000.pilot",
                 "worker", "prepare", "Shared", str(source), str(scratch)],
                folder, phase, NEW_OUT, start)
            canonical = rr.read(scratch / "canonical.json")
            ref = rr.read(sample["record_path"])
            if (canonical["csr_sha256"] != ref["exact"]["canonical_sha256"]
                    or rr.sha(scratch / "metadata.json") != ref["exact"]["metadata_sha256"]):
                raise RuntimeError(f"prepare identity mismatch for {sid}")

            phase = "encode"
            encode_cmd = [str(rr.PY), "-X", "utf8", "-B", str(WRAPPER), "worker", "encode",
                          "CSR_BZIP2_9", str(scratch), str(folder / "archive")]
            stage_records[(sid, phase)] = rr.stage(encode_cmd, folder, phase, NEW_OUT, start)
            encode_output = (folder / "encode.log").read_text(encoding="utf-8", errors="replace")
            encode_json = json.loads(encode_output.strip().splitlines()[-1])
            if encode_json.get("encode_self_check", {}).get("valid") is not True:
                raise RuntimeError(f"encoder self-check missing/failed for {sid}")

            phase = "decode"
            decode_cmd = [str(rr.PY), "-X", "utf8", "-B", str(WRAPPER), "worker", "decode",
                          "CSR_BZIP2_9", str(folder / "archive"), str(decoded), "--blocked",
                          str(source.parent), str(scratch)]
            stage_records[(sid, phase)] = rr.stage(decode_cmd, folder, phase, NEW_OUT, start)

            phase = "check"
            check_cmd = [str(rr.PY), "-X", "utf8", "-B", "-m", "baseline.hest1000.main",
                         "compare", str(scratch), str(decoded), str(folder / "EXACT.json")]
            stage_records[(sid, phase)] = rr.stage(check_cmd, folder, phase, NEW_OUT, start)
            exact = rr.read(folder / "EXACT.json")
            needed = ["dtype", "shape", "csr", "canonical", "indptr", "indices", "counts", "metadata", "all"]
            if not all(exact.get("checks", {}).get(k) is True for k in needed):
                raise RuntimeError(f"exact recovery checks failed for {sid}")
            if exact["decoded_hashes"]["metadata.json"] != ref["exact"]["metadata_sha256"]:
                raise RuntimeError(f"metadata identity mismatch for {sid}")
            if rr.sha(source) != sample["source_sha256"]:
                raise RuntimeError(f"source changed during repair for {sid}")

            fees = rr.fees(plan, "CSR_BZIP2_9", folder / "archive")
            row.update({k: canonical[k] for k in ["n_spots", "n_genes", "n_counts", "n_nonzero",
                                                   "canonical_dtype", "source_storage_dtype"]})
            row.update({"canonical_sha256": canonical["csr_sha256"], "source_sha256_after": rr.sha(source),
                        "encode_self_check": encode_json["encode_self_check"], "exact": exact,
                        **fees, "resource_receipts": {ph: rec for (sample_id, ph), rec in stage_records.items()
                                                       if sample_id == sid}})
            row["status"] = "success"
            row["full_archive_bits_per_count"] = 8 * row["total_file_bytes"] / row["n_counts"]
            row["full_archive_bits_per_nonzero"] = 8 * row["total_file_bytes"] / row["n_nonzero"]
            write_json(result_path, row)
            results[key] = {"status": "success", "record_path": str(result_path),
                            "result_sha256": rr.sha(result_path),
                            "total_file_bytes": row["total_file_bytes"],
                            "archive_sha256": row["archive_hashes"]["archive.bin"],
                            "exact": True, "source_unchanged": True,
                            "encode_self_check": True}
            for name in ["decoded", "scratch", "temp", *[p.name for p in folder.glob("cache_*")]]:
                rr.safe_remove(folder / name, folder)
            write_json(NEW_OUT / "REPAIR_PROGRESS.json", {"completed": len(results), "total": len(TARGETS),
                        "last_pair": key, "status_counts": dict(collections.Counter(v["status"] for v in results.values()))})
            print(sid, "CSR_BZIP2_9", "success", flush=True)

        summary = {"all_repair_pairs_accepted": len(results) == len(TARGETS)
                   and all(x["status"] == "success" for x in results.values()),
                   "repair_pairs": results, "old_failures_preserved": prior,
                   "retry_limit_per_pair": 1, "elapsed_seconds": time.time() - start}
        write_json(NEW_OUT / "REPAIR_DONE.json", summary)
        preflight = {
            "all_pass": summary["all_repair_pairs_accepted"],
            "prior_bad_bzip_streams_were_rejected": True,
            "new_streams_passed_encoder_roundtrip": all(x.get("encode_self_check") for x in results.values()),
            "new_streams_passed_independent_decode_and_exact_check": all(x.get("exact") for x in results.values()),
            "new_results": results,
        }
        write_json(REPAIR_PREFLIGHT, preflight)
        release = {
            "approved": bool(preflight["all_pass"]),
            "repair_plan_sha256": rr.sha(REPAIR_PLAN),
            "preflight_sha256": rr.sha(REPAIR_PREFLIGHT),
            "reviewer": "primary agent; post-run evidence audit",
            "scope": "exactly TENX86 and TENX82 CSR_BZIP2_9; one bounded repair attempt each",
            "method_parameters_changed": False,
            "old_failures_overwritten": False,
        }
        write_json(RELEASE, release)
    except BaseException as exc:
        write_json(NEW_OUT / "REPAIR_STOPPED.json", {"error": repr(exc), "time": time.time(),
                    "completed": results, "plan": str(REPAIR_PLAN)})
        raise


if __name__ == "__main__":
    main()
