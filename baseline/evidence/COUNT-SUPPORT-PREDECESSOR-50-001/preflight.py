"""One-slice vertical release gate for all frozen support-context arms."""
from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PYTHON = ROOT / "baseline" / "evidence" / "COUNT-MATCHED-READY-001" / "venv" / "Scripts" / "python.exe"
OUT = HERE / "preflight_v3"
ARMS = [("SPATIAL_M00", "spatial", 0), ("SPATIAL_M02", "spatial", 2), ("SPATIAL_M04", "spatial", 4),
        ("SPATIAL_M06", "spatial", 6), ("SPATIAL_M08", "spatial", 8), ("SPATIAL_M12", "spatial", 12),
        ("SPATIAL_M16", "spatial", 16), ("ROW_M06", "row", 6)]


def invoke(stage, folder, **kwargs):
    command = [str(PYTHON), "-X", "utf8", "-B", str(HERE / "worker.py"), stage, "--report", str(folder / f"{stage}.json")]
    for key, value in kwargs.items():
        command.extend(["--" + key, str(value)])
    subprocess.run(command, cwd=ROOT, check=True)
    return json.loads((folder / f"{stage}.json").read_text(encoding="utf-8"))


def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    OUT.mkdir()
    sample = next(csv.DictReader((HERE / "DATA_SPLIT.csv").open(encoding="utf-8-sig")))
    anchor = json.loads((HERE / "ANCHORS.json").read_text(encoding="utf-8"))[sample["id"]]
    rows = []
    for arm, kind, width in ARMS:
        folder = OUT / arm
        folder.mkdir()
        archive = folder / "archive.cnt"
        encoded = invoke("encode", folder, source=sample["source_path"], anchor=anchor["archive_path"], archive=archive, kind=kind, width=width)
        decoded = invoke("decode", folder, archive=archive, output=folder / "decoded")
        verified = invoke("verify", folder, source=sample["source_path"], output=folder / "decoded")
        paid = invoke("ledger", folder, archive=archive)
        members = set(paid["members"])
        expected_increment = kind == "spatial" and width > 6
        checks = {
            "exact": verified["checks"]["all"],
            "ledger": sum(paid["categories"].values()) == paid["total_archive_bytes"],
            "graph_increment_presence": ("support_graph.bz2" in members) == expected_increment,
            "m6_anchor_stream": arm != "SPATIAL_M06" or encoded["m6_anchor_support_stream_identical"],
            "m6_anchor_model": arm != "SPATIAL_M06" or encoded["m6_anchor_support_model_identical"],
            "archive_only": decoded["archive_only"],
        }
        rows.append({"arm": arm, "width": width, "checks": checks, "all": all(checks.values()),
                     "archive_bytes": paid["total_archive_bytes"], "support_graph_increment_bytes": paid["categories"]["support_graph_increment"]})
    report = {"all_pass": all(row["all"] for row in rows), "sample_id": sample["id"], "arms": rows,
              "failed_preflights_retained": ["preflight_m6", "preflight_m6_v2"]}
    (HERE / "PREFLIGHT.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not report["all_pass"]:
        raise RuntimeError(report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
