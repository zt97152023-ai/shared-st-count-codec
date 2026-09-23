"""Fresh-process decode and exact source verification for E3 expansion."""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARCHIVES = HERE / "archives"
PANEL = HERE.parent / "COUNT-SUPPORT-PREDECESSOR-50-001" / "DATA_SPLIT.csv"
WORKER = HERE / "e3_worker.py"
ARMS = ("full", "no_support", "no_value", "no_spatial", "no_sharing")
FOLDERS = {"full": "full", "no_support": "no_support", "no_value": "no_value", "no_spatial": "no_spatial", "no_sharing": "no_sharing"}


def rows():
    with PANEL.open(encoding="utf-8-sig", newline="") as handle:
        return [row for row in csv.DictReader(handle) if row.get("selected", "").lower() == "true"]


def write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def run_worker(command, stdout_path: Path, stderr_path: Path):
    completed = subprocess.run(command, cwd=HERE.parents[2], capture_output=True, text=True)
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    return completed.returncode


def main():
    panel = rows()
    failures = []
    consecutive = {arm: 0 for arm in ARMS}
    completed = 0
    for index, row in enumerate(panel, start=1):
        sample = row["id"]
        source = Path(row["source_path"])
        for arm in ARMS:
            arm_dir = ARCHIVES / sample / FOLDERS[arm]
            package = arm_dir / "archive.cnt"
            decoded = arm_dir / "decoded_verify"
            decode_report = arm_dir / "decode_verify.json"
            verify_report = arm_dir / "verify_source.json"
            try:
                if not package.is_file():
                    raise FileNotFoundError(package)
                if decoded.exists():
                    raise FileExistsError(decoded)
                decode_op = "decode_no_value" if arm == "no_value" else "decode_standard"
                decode_command = [sys.executable, str(WORKER), decode_op, "--package", str(package), "--output", str(decoded), "--report", str(decode_report)]
                code = run_worker(decode_command, arm_dir / "decode.stdout.log", arm_dir / "decode.stderr.log")
                if code != 0:
                    raise RuntimeError(f"decode exit={code}")
                verify_command = [sys.executable, str(WORKER), "verify", "--source", str(source), "--output", str(decoded), "--package", str(package), "--report", str(verify_report)]
                code = run_worker(verify_command, arm_dir / "verify.stdout.log", arm_dir / "verify.stderr.log")
                if code != 0:
                    raise RuntimeError(f"verify exit={code}")
                result = json.loads(verify_report.read_text(encoding="utf-8"))
                if not result.get("all", False):
                    raise RuntimeError("exact source verification returned all=false")
                write_json(arm_dir / "ACCEPTED_EXACT.json", {"sample_id": sample, "arm": arm, "sample_index": index, "decode_report": str(decode_report), "verify_report": str(verify_report), "checks": result.get("checks", {})})
                shutil.rmtree(decoded)
                consecutive[arm] = 0
                completed += 1
            except Exception as exc:
                consecutive[arm] += 1
                failure = {"sample_index": index, "sample_id": sample, "arm": arm, "error": repr(exc), "traceback": traceback.format_exc(), "consecutive_failures": consecutive[arm]}
                failures.append(failure)
                write_json(arm_dir / "VERIFY_FAILURE.json", failure)
                if consecutive[arm] >= 3:
                    write_json(HERE / "VERIFY_STOP.json", {"reason": "three consecutive verification failures", "failure": failure, "failures": failures})
                    raise RuntimeError(failure["error"])
    write_json(HERE / "VERIFY_STATUS.json", {"status": "complete_with_failures" if failures else "complete", "planned_rows": 250, "completed_exact": completed, "failure_count": len(failures), "failures": failures})


if __name__ == "__main__":
    main()
