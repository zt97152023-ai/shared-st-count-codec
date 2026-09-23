"""Freeze the exposed 50-slice manifest and the immutable K32 anchor map."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "VALUE_K64_K128_50_006"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


rows = list(csv.DictReader((PARENT / "DATA_SPLIT.csv").open(encoding="utf-8-sig")))
if len(rows) != 50 or len({row["id"] for row in rows}) != 50:
    raise RuntimeError("expected fixed 50")
index = json.loads((PARENT / "INDEX.json").read_text(encoding="utf-8"))
anchors = {}
for row in rows:
    record = Path(index[row["id"]]["32"]["record_path"])
    result = json.loads(record.read_text(encoding="utf-8"))
    archive = record.parent / "archive.cnt"
    if result["status"] != "success" or not result["exact"]["checks"]["all"]:
        raise RuntimeError("bad K32 anchor: " + row["id"])
    if sha(archive) != result["archive_sha256"]:
        raise RuntimeError("anchor hash drift: " + row["id"])
    anchors[row["id"]] = {
        "record_path": str(record),
        "archive_path": str(archive),
        "archive_sha256": result["archive_sha256"],
        "archive_bytes": result["total_archive_bytes"],
        "source_path": row["source_path"],
        "source_sha256": row["source_sha256"],
    }
shutil.copyfile(PARENT / "DATA_SPLIT.csv", HERE / "DATA_SPLIT.csv")
(HERE / "ANCHORS.json").write_text(json.dumps(anchors, indent=2), encoding="utf-8")
pins = {}
pin_names = ["PROTOCOL.json", "support_dynamic.py", "codec.py", "worker.py", "run.py", "analyze.py", "audit_final.py", "preflight.py", "test_support.py", "DATA_SPLIT.csv", "ANCHORS.json"]
if (HERE / "PREFLIGHT.json").exists():
    pin_names.append("PREFLIGHT.json")
for name in pin_names:
    pins[name] = sha(HERE / name)
(HERE / "RUN_PINS.json").write_text(json.dumps(pins, indent=2), encoding="utf-8")
print(json.dumps({"samples": len(rows), "anchors": len(anchors), "pins": pins}, indent=2))
