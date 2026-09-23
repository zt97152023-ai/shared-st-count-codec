from __future__ import annotations

import csv
import json
from pathlib import Path

import e3_codec as codec

HERE = Path(__file__).resolve().parent
ROOT = HERE / "pilot_v1"
SAMPLES = ["INT17", "MEND124", "MEND140"]
ARM_DIRS = {
    "full": ("full", "decoded_v2", "verify_v2.json"),
    "no_support": ("no_support_context", "decoded_v1", "verify_v1.json"),
    "no_value": ("no_value", "decoded_v2", "verify_v2.json"),
    "no_spatial": ("no_spatial", "decoded_v1", "verify_v1.json"),
    "no_sharing": ("no_sharing_q1", "decoded_v2", "verify_v2.json"),
}
DEFINITIONS = {
    "full": "Production Shared K32 anchor, support M6, value context M6",
    "no_support": "Gene-only support probabilities; value spatial context retained",
    "no_value": "Fixed-width lossless positive uint32 stream; no positive-value model",
    "no_spatial": "No support or value spatial predecessors; active model families retained",
    "no_sharing": "Independent per-gene q1 exceptions; fixed eight tail classes retained",
}


def load_manifest():
    path = HERE.parent / "COUNT-SUPPORT-PREDECESSOR-50-001" / "DATA_SPLIT.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["id"]: row for row in csv.DictReader(handle)}


def main():
    meta = load_manifest()
    rows = []
    component_rows = []
    for sample in SAMPLES:
        for arm, (folder, decoded, verify_name) in ARM_DIRS.items():
            package = ROOT / sample / folder / "archive.cnt"
            manifest, _, _ = codec.lib.zip_read(package)
            categories, members = codec.ledger(package)
            verify = json.loads((ROOT / sample / folder / verify_name).read_text(encoding="utf-8"))
            total = int(package.stat().st_size)
            n_counts = int(meta[sample]["n_counts"])
            n_nonzero = int(meta[sample]["n_nonzero"])
            if sum(categories.values()) != total:
                raise ValueError(f"ledger mismatch: {package}")
            row = {
                "dataset_id": sample,
                "platform": "HEST_exposed_development",
                "organ": meta[sample]["organ"],
                "species": meta[sample]["species"],
                "arm": arm,
                "archive_size_bytes": total,
                "bits_per_count": 8.0 * total / n_counts,
                "bits_per_nonzero": 8.0 * total / n_nonzero,
                "n_spots": int(meta[sample]["n_spots"]),
                "n_genes": int(meta[sample]["n_genes"]),
                "n_counts": n_counts,
                "n_nonzero": n_nonzero,
                "exact_recovery": bool(verify.get("all", False)),
                "definition": DEFINITIONS[arm],
                "archive_sha256": codec.lib.sha_path(package),
                "canonical_sha256": manifest["canonical_sha256"],
                "metadata_sha256": manifest["metadata_sha256"],
            }
            rows.append(row)
            component = {"dataset_id": sample, "arm": arm, **categories, "archive_size_bytes": total, "exact_recovery": row["exact_recovery"]}
            component_rows.append(component)

    fields = list(rows[0])
    with (HERE / "E3_DIRECT_ABLATION.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    component_fields = list(component_rows[0])
    with (HERE / "E3_COMPONENT_LEDGER.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=component_fields)
        writer.writeheader(); writer.writerows(component_rows)

    pooled = {}
    for arm in ARM_DIRS:
        subset = [r for r in rows if r["arm"] == arm]
        pooled[arm] = {"n": len(subset), "total_archive_bytes": sum(int(r["archive_size_bytes"]) for r in subset), "all_exact": all(r["exact_recovery"] for r in subset)}
    full = pooled["full"]["total_archive_bytes"]
    summary = {
        "task": "COUNT-E3-MODULE-CONTRIBUTION-001",
        "phase": "direct_pilot_v1",
        "samples": SAMPLES,
        "arms": pooled,
        "delta_bytes_vs_full": {arm: pooled[arm]["total_archive_bytes"] - full for arm in ARM_DIRS if arm != "full"},
        "percent_increase_vs_full": {arm: 100.0 * (pooled[arm]["total_archive_bytes"] - full) / full for arm in ARM_DIRS if arm != "full"},
        "all_rows_exact": all(r["exact_recovery"] for r in rows),
        "all_ledgers_sum": True,
    }
    (HERE / "E3_PILOT_SUMMARY.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
