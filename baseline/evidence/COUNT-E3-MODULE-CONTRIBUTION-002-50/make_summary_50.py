from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

import e3_codec as codec

HERE = Path(__file__).resolve().parent
ARCHIVES = HERE / "archives"
PANEL = HERE.parent / "COUNT-SUPPORT-PREDECESSOR-50-001" / "DATA_SPLIT.csv"
SAMPLES = []
ARMS = ("full", "no_support", "no_value", "no_spatial", "no_sharing")
DEFINITIONS = {
    "full": "Production Shared K32 anchor, support M6, value context M6",
    "no_support": "Gene-only support probabilities; value spatial context retained",
    "no_value": "Fixed-width lossless positive uint32 stream; no positive-value model",
    "no_spatial": "No support or value spatial predecessors; active model families retained",
    "no_sharing": "Independent per-gene q1 exceptions; fixed eight tail classes retained",
}


def panel_rows():
    with PANEL.open(encoding="utf-8-sig", newline="") as handle:
        return [row for row in csv.DictReader(handle) if row.get("selected", "").lower() == "true"]


def main():
    panel = panel_rows()
    if len(panel) != 50:
        raise ValueError(len(panel))
    metadata = {row["id"]: row for row in panel}
    rows = []
    ledgers = []
    for row in panel:
        sample = row["id"]
        for arm in ARMS:
            package = ARCHIVES / sample / arm / "archive.cnt"
            accepted = ARCHIVES / sample / arm / "ACCEPTED_EXACT.json"
            if not package.is_file() or not accepted.is_file():
                raise FileNotFoundError(f"missing {sample} {arm}")
            manifest, _, _ = codec.lib.zip_read(package)
            categories, members = codec.ledger(package)
            if sum(categories.values()) != package.stat().st_size:
                raise ValueError(f"ledger mismatch: {package}")
            exact = json.loads(accepted.read_text(encoding="utf-8"))
            if not exact.get("checks", {}).get("all", False):
                raise ValueError(f"not exact: {accepted}")
            n_counts = int(row["n_counts"]); n_nonzero = int(row["n_nonzero"])
            rows.append({
                "dataset_id": sample, "platform": "HEST_exposed_development", "organ": row["organ"], "species": row["species"], "arm": arm,
                "archive_size_bytes": int(package.stat().st_size), "bits_per_count": 8.0 * package.stat().st_size / n_counts,
                "bits_per_nonzero": 8.0 * package.stat().st_size / n_nonzero, "n_spots": int(row["n_spots"]), "n_genes": int(row["n_genes"]),
                "n_counts": n_counts, "n_nonzero": n_nonzero, "exact_recovery": True, "definition": DEFINITIONS[arm],
                "archive_sha256": codec.lib.sha_path(package), "canonical_sha256": manifest["canonical_sha256"], "metadata_sha256": manifest["metadata_sha256"],
            })
            ledgers.append({"dataset_id": sample, "arm": arm, **categories, "archive_size_bytes": int(package.stat().st_size), "exact_recovery": True})

    row_fields = list(rows[0]); ledger_fields = list(ledgers[0])
    with (HERE / "E3_DIRECT_ABLATION_50.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=row_fields); writer.writeheader(); writer.writerows(rows)
    with (HERE / "E3_COMPONENT_LEDGER_50.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ledger_fields); writer.writeheader(); writer.writerows(ledgers)

    lookup = {(r["dataset_id"], r["arm"]): int(r["archive_size_bytes"]) for r in rows}
    deltas = []
    for row in panel:
        sample = row["id"]; full = lookup[(sample, "full")]
        out = {"dataset_id": sample, "full_bytes": full}
        for arm in ARMS[1:]:
            value = lookup[(sample, arm)]; out[f"{arm}_bytes"] = value; out[f"{arm}_delta_bytes"] = value - full; out[f"{arm}_increase_percent"] = 100.0 * (value - full) / full
        deltas.append(out)
    delta_fields = list(deltas[0])
    with (HERE / "E3_PAIRED_DELTAS_50.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=delta_fields); writer.writeheader(); writer.writerows(deltas)

    pooled = {}
    for arm in ARMS:
        values = [lookup[(sample, arm)] for sample in metadata]
        pooled[arm] = {"n": len(values), "total_archive_bytes": sum(values), "mean_archive_bytes": statistics.mean(values), "median_archive_bytes": statistics.median(values), "all_exact": True}
    full_values = [lookup[(sample, "full")] for sample in metadata]
    paired = {}
    for arm in ARMS[1:]:
        values = [lookup[(sample, arm)] - lookup[(sample, "full")] for sample in metadata]
        paired[arm] = {"total_delta_bytes": sum(values), "mean_delta_bytes": statistics.mean(values), "median_delta_bytes": statistics.median(values), "min_delta_bytes": min(values), "max_delta_bytes": max(values), "n_increase": sum(value > 0 for value in values), "n_decrease": sum(value < 0 for value in values), "n_tie": sum(value == 0 for value in values), "pooled_increase_percent": 100.0 * sum(values) / sum(full_values)}
    component_pooled = {}
    for key in ("support_stream", "value_stream", "support_model", "value_model_and_group_map", "graph_index", "identity_coordinates_metadata", "manifest", "zip_framing"):
        component_pooled[key] = {"total_bytes": sum(int(row[key]) for row in ledgers if row["arm"] == "full"), "share_of_full_pooled_archive": sum(int(row[key]) for row in ledgers if row["arm"] == "full") / pooled["full"]["total_archive_bytes"]}
    summary = {"task": "COUNT-E3-MODULE-CONTRIBUTION-002-50", "phase": "direct_50_expansion", "samples": list(metadata), "planned_rows": 250, "observed_rows": len(rows), "pooled": pooled, "paired_vs_full": paired, "full_component_ledger": component_pooled, "all_exact": True, "all_ledgers_sum": True, "protected_data_used": False}
    (HERE / "E3_50_SUMMARY.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
