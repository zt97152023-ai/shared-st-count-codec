"""Read-only final evidence audit; never repairs results."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = Path("D:/HEST1000BenchRun/COUNT-SUPPORT-PREDECESSOR-50-001")
ANCHORS = json.loads((HERE / "ANCHORS.json").read_text(encoding="utf-8"))
FIXED = {"value_q1.bz2", "value_group.bz2", "value_base_k.bz2", "value_odds.u32", "value_cond_k.bz2", "values.rans",
         "graph.bz2", "base_probability.bz2", "metadata.bz2"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    index = json.loads((RUN / "INDEX.json").read_text(encoding="utf-8"))
    findings = []
    checked = 0
    m6_reproduced = 0
    for sample_id, arms in index.items():
        anchor_record = json.loads(Path(ANCHORS[sample_id]["record_path"]).read_text(encoding="utf-8"))
        for arm, item in arms.items():
            try:
                if item.get("status") != "success":
                    raise ValueError("index status")
                record = json.loads(Path(item["record_path"]).read_text(encoding="utf-8"))
                if record["status"] != "success" or not record["exact"]["checks"]["all"]:
                    raise ValueError("result/exact")
                if sha(Path(item["record_path"]).parent / "archive.cnt") != record["archive_sha256"]:
                    raise ValueError("archive hash")
                if sum(record["ledger"].values()) != record["total_archive_bytes"]:
                    raise ValueError("ledger")
                for name in FIXED:
                    if record["members"][name] != anchor_record["members"][name]:
                        raise ValueError("fixed member drift: " + name)
                if arm == "SPATIAL_M06":
                    if not record["m6_anchor_support_stream_identical"] or not record["m6_anchor_support_model_identical"]:
                        raise ValueError("M6 regression")
                    m6_reproduced += 1
                checked += 1
            except Exception as error:
                findings.append({"sample_id": sample_id, "arm": arm, "error": repr(error)})
    summary_rows = list(csv.DictReader((HERE / "FIXED_M_SUMMARY.csv").open(encoding="utf-8")))
    report = {"all_pass": not findings and checked == 400 and m6_reproduced == 50 and len(summary_rows) == 8,
              "checked_archives": checked, "m6_anchor_reproductions": m6_reproduced, "summary_rows": len(summary_rows), "findings": findings}
    (HERE / "FINAL_VERIFICATION.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not report["all_pass"]:
        raise RuntimeError(report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
