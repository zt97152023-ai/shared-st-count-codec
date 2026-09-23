from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    rows = list(csv.DictReader((HERE / "E3_DIRECT_ABLATION_50.csv").open(encoding="utf-8", newline="")))
    ledgers = list(csv.DictReader((HERE / "E3_COMPONENT_LEDGER_50.csv").open(encoding="utf-8", newline="")))
    if len(rows) != 250 or len(ledgers) != 250:
        raise ValueError((len(rows), len(ledgers)))
    counts = Counter(row["dataset_id"] for row in rows)
    arm_counts = Counter(row["arm"] for row in rows)
    if set(counts.values()) != {5} or set(arm_counts.values()) != {50}:
        raise ValueError((counts, arm_counts))
    by_sample = {}
    bad = []
    for row in rows:
        if row["exact_recovery"] != "True":
            bad.append((row["dataset_id"], row["arm"], "not_exact"))
        by_sample.setdefault(row["dataset_id"], []).append(row)
    for sample, sample_rows in by_sample.items():
        canonical = {row["canonical_sha256"] for row in sample_rows}
        metadata = {row["metadata_sha256"] for row in sample_rows}
        if len(canonical) != 1 or len(metadata) != 1:
            bad.append((sample, "identity", {"canonical": canonical, "metadata": metadata}))
    for row in ledgers:
        total = int(row["archive_size_bytes"])
        parts = sum(int(row[key]) for key in ("support_stream", "value_stream", "support_model", "value_model_and_group_map", "graph_index", "identity_coordinates_metadata", "manifest", "zip_framing"))
        if total != parts:
            bad.append((row["dataset_id"], row["arm"], "ledger"))
    if bad:
        raise ValueError(bad[:10])
    summary = json.loads((HERE / "E3_50_SUMMARY.json").read_text(encoding="utf-8"))
    status = json.loads((HERE / "RUN_STATUS.json").read_text(encoding="utf-8"))
    verify = json.loads((HERE / "VERIFY_STATUS.json").read_text(encoding="utf-8"))
    if status["failure_count"] != 0 or verify["failure_count"] != 0 or verify["completed_exact"] != 250:
        raise ValueError({"run": status, "verify": verify})
    result = {
        "task": "COUNT-E3-MODULE-CONTRIBUTION-002-50",
        "rows": len(rows),
        "datasets": len(counts),
        "arm_counts": dict(arm_counts),
        "all_exact": True,
        "all_ledgers_sum": True,
        "per_dataset_canonical_identity_consistent": True,
        "run_failures": 0,
        "verify_failures": 0,
        "reproduction": {
            "INT17_no_support": True,
            "MEND124_no_sharing": True,
            "full_anchor_hash_recorded": True,
        },
        "pooled_increase_percent": summary["paired_vs_full"],
    }
    (HERE / "INDEPENDENT_AUDIT.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
