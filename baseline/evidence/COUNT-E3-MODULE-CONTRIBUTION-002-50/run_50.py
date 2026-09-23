"""Bounded fresh-process runner for the 50-slice direct E3 expansion."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "archives"
PANEL = HERE.parent / "COUNT-SUPPORT-PREDECESSOR-50-001" / "DATA_SPLIT.csv"
OLD_CONTEXT = HERE.parent / "COUNT-PRODUCTION-SHARED-ABLATIONS-50-001" / "main_v3" / "context"
WORKER = HERE / "e3_worker.py"
ARMS = ("full", "no_support", "no_value", "no_spatial", "no_sharing")


def sha_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_panel():
    with PANEL.open(encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("selected", "").lower() == "true"]
    if len(rows) != 50 or len({row["id"] for row in rows}) != 50:
        raise ValueError(f"expected 50 unique selected panel rows, got {len(rows)}")
    return rows


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def copy_arm(sample: str, arm: str, source: Path, target: Path):
    if target.exists():
        return {"status": "existing", "archive_sha256": sha_path(target), "source": str(source)}
    if not source.is_file():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return {"status": "copied", "archive_sha256": sha_path(target), "source": str(source), "sample_id": sample, "arm": arm}


def encode_arm(sample: str, arm: str, target: Path):
    if target.exists():
        return {"status": "existing", "archive_sha256": sha_path(target), "sample_id": sample, "arm": arm}
    report = target.with_name("encode.json")
    command = [sys.executable, str(WORKER), {"no_support": "encode_no_support", "no_value": "encode_no_value", "no_sharing": "encode_no_q1_sharing"}[arm], "--sample", sample, "--package", str(target), "--report", str(report)]
    completed = subprocess.run(command, cwd=HERE.parents[2], capture_output=True, text=True)
    target.with_name("encode.stdout.log").write_text(completed.stdout, encoding="utf-8")
    target.with_name("encode.stderr.log").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(f"{arm} encode failed for {sample}: exit={completed.returncode}")
    result = json.loads(report.read_text(encoding="utf-8"))
    if result.get("status") != "success" or not target.is_file():
        raise RuntimeError(f"{arm} encode report invalid for {sample}")
    return result


def main():
    rows = read_panel()
    OUT.mkdir(parents=True, exist_ok=True)
    panel_hash = sha_path(PANEL)
    write_json(HERE / "PANEL.json", {"task": "COUNT-E3-MODULE-CONTRIBUTION-002-50", "n": 50, "panel_sha256": panel_hash, "sample_ids": [row["id"] for row in rows], "arms": list(ARMS)})
    failures = []
    consecutive = {arm: 0 for arm in ARMS}
    for index, row in enumerate(rows, start=1):
        sample = row["id"]
        for arm in ARMS:
            target = OUT / sample / arm / "archive.cnt"
            try:
                if arm == "full":
                    source = Path(r"D:\HEST1000BenchRun\COUNT-SUPPORT-PREDECESSOR-50-001") / "main" / sample / "SPATIAL_M06" / "attempt01" / "archive.cnt"
                    result = copy_arm(sample, arm, source, target)
                elif arm == "no_spatial":
                    source = OLD_CONTEXT / sample / "S0V0" / "archive.cnt"
                    result = copy_arm(sample, arm, source, target)
                else:
                    result = encode_arm(sample, arm, target)
                write_json(target.with_name("runner.json"), {"sample_index": index, "sample_id": sample, "arm": arm, "panel_sha256": panel_hash, "result": result})
                consecutive[arm] = 0
            except Exception as exc:
                consecutive[arm] += 1
                failure = {"sample_index": index, "sample_id": sample, "arm": arm, "error": repr(exc), "traceback": traceback.format_exc(), "consecutive_failures": consecutive[arm]}
                failures.append(failure)
                write_json(target.with_name("FAILURE.json"), failure)
                if consecutive[arm] >= 3:
                    write_json(HERE / "STOP.json", {"reason": "three consecutive failures", "failure": failure, "failures": failures})
                    raise RuntimeError(failure["error"])
    write_json(HERE / "RUN_STATUS.json", {"status": "complete_with_failures" if failures else "complete", "panel_n": 50, "planned_rows": 250, "failure_count": len(failures), "failures": failures})


if __name__ == "__main__":
    main()
