"""Build sample-level, pooled, and descriptive calibration summaries from raw receipts."""
from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = Path("D:/HEST1000BenchRun/COUNT-SUPPORT-PREDECESSOR-50-001")
SPATIAL = ["SPATIAL_M00", "SPATIAL_M02", "SPATIAL_M04", "SPATIAL_M06", "SPATIAL_M08", "SPATIAL_M12", "SPATIAL_M16"]
ARMS = SPATIAL + ["ROW_M06"]


def quantile_linear(values, probability):
    """Return the linearly interpolated quantile at sorted index (n-1)*p."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("quantile of empty sequence")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def write_csv(path, rows):
    rows = list(rows)
    fields = list(rows[0]) if rows else []
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def load_rows():
    index = json.loads((RUN / "INDEX.json").read_text(encoding="utf-8"))
    output = []
    for sample_id, arms in index.items():
        for arm in ARMS:
            record = arms[arm]
            if record.get("status") != "success":
                raise RuntimeError(f"missing {sample_id} {arm}")
            result = json.loads(Path(record["record_path"]).read_text(encoding="utf-8"))
            if result["status"] != "success" or not result["exact"]["checks"]["all"]:
                raise RuntimeError(f"unaccepted {sample_id} {arm}")
            ledger = result["ledger"]
            output.append({
                "sample_id": sample_id,
                "arm": arm,
                "kind": result["kind"],
                "width": result["width"],
                "platform": result["platform"],
                "species": result["species"],
                "organ": result["organ"],
                "n_obs": result["n_obs"],
                "n_vars": result["n_vars"],
                "n_nonzero": result["n_nonzero"],
                "total_archive_bytes": result["total_archive_bytes"],
                "support_stream_bytes": ledger["support_stream"],
                "support_model_bytes": ledger["support_model"],
                "support_graph_increment_bytes": ledger["support_graph_increment"],
                "fixed_value_stream_bytes": ledger["value_stream"],
                "fixed_value_model_bytes": ledger["value_model_and_group_map"],
                "fixed_value_graph_bytes": ledger["value_graph"],
                "identity_coordinates_bytes": ledger["identity_coordinates"],
                "manifest_bytes": ledger["manifest"],
                "zip_framing_bytes": ledger["zip_framing"],
                "support_nll_bits": result["support_nll_bits"],
                "archive_sha256": result["archive_sha256"],
                "record_path": record["record_path"],
            })
    return output


def summarize(rows):
    by_sample = defaultdict(dict)
    for row in rows:
        by_sample[row["sample_id"]][row["arm"]] = row
    summary = []
    for arm in ARMS:
        arm_rows = [entry[arm] for entry in by_sample.values()]
        base_rows = [entry["SPATIAL_M06"] for entry in by_sample.values()]
        deltas = [candidate["total_archive_bytes"] - base["total_archive_bytes"] for candidate, base in zip(arm_rows, base_rows)]
        percents = [100.0 * delta / base["total_archive_bytes"] for delta, base in zip(deltas, base_rows)]
        wins = sum(delta < 0 for delta in deltas)
        losses = sum(delta > 0 for delta in deltas)
        largest_saver = min(range(len(deltas)), key=deltas.__getitem__)
        total = sum(row["total_archive_bytes"] for row in arm_rows)
        base_total = sum(row["total_archive_bytes"] for row in base_rows)
        summary.append({
            "arm": arm,
            "kind": arm_rows[0]["kind"],
            "width": arm_rows[0]["width"],
            "n": len(arm_rows),
            "total_archive_bytes": total,
            "delta_bytes_vs_spatial_m6": total - base_total,
            "percent_change_vs_spatial_m6": 100.0 * (total - base_total) / base_total,
            "wins_vs_spatial_m6": wins,
            "losses_vs_spatial_m6": losses,
            "ties_vs_spatial_m6": len(deltas) - wins - losses,
            "median_percent_change_vs_spatial_m6": statistics.median(percents),
            "q25_percent_change_vs_spatial_m6": quantile_linear(percents, 0.25),
            "q75_percent_change_vs_spatial_m6": quantile_linear(percents, 0.75),
            "min_percent_change_vs_spatial_m6": min(percents),
            "max_percent_change_vs_spatial_m6": max(percents),
            "support_stream_bytes": sum(row["support_stream_bytes"] for row in arm_rows),
            "support_model_bytes": sum(row["support_model_bytes"] for row in arm_rows),
            "support_graph_increment_bytes": sum(row["support_graph_increment_bytes"] for row in arm_rows),
            "support_nll_bits": sum(row["support_nll_bits"] for row in arm_rows),
            "largest_saving_sample": arm_rows[largest_saver]["sample_id"],
            "leave_largest_saver_out_delta_bytes": sum(deltas) - deltas[largest_saver],
        })
    minimum = min(row["total_archive_bytes"] for row in summary if row["arm"] in SPATIAL)
    eligible = [row for row in summary if row["arm"] in SPATIAL and 100.0 * (row["total_archive_bytes"] - minimum) / minimum <= 0.05]
    selected = min(eligible, key=lambda row: row["width"])
    return summary, selected


def strata(rows):
    by_sample = defaultdict(dict)
    for row in rows:
        by_sample[row["sample_id"]][row["arm"]] = row
    arm_summary, selected = summarize(rows)
    selected_arm = selected["arm"]
    output = []
    for field in ["platform", "species", "organ"]:
        groups = defaultdict(list)
        for sample_id, arms in by_sample.items():
            groups[arms["SPATIAL_M06"][field]].append(arms)
        for label, entries in sorted(groups.items()):
            candidate = sum(entry[selected_arm]["total_archive_bytes"] for entry in entries)
            base = sum(entry["SPATIAL_M06"]["total_archive_bytes"] for entry in entries)
            output.append({"stratum_type": field, "stratum": label, "n": len(entries), "selected_arm": selected_arm,
                           "selected_bytes": candidate, "m6_bytes": base, "delta_bytes": candidate - base,
                           "percent_change_vs_m6": 100.0 * (candidate - base) / base})
    return output


def main():
    rows = load_rows()
    if len(rows) != 400:
        raise RuntimeError(len(rows))
    summary, selected = summarize(rows)
    stratified = strata(rows)
    write_csv(HERE / "PER_SAMPLE_RESULTS.csv", rows)
    write_csv(HERE / "FIXED_M_SUMMARY.csv", summary)
    write_csv(HERE / "STRATIFIED_SUMMARY.csv", stratified)
    (HERE / "SELECTION.json").write_text(json.dumps({"selected": selected, "rule": "minimum pooled bytes; within 0.05% prefer smaller M"}, indent=2), encoding="utf-8")
    lines = ["# Support predecessor calibration on 50 exposed HEST development slices", "",
             "Value K was fixed at 32. All 400 arms produced real archives, fresh-process decodes and exact recovery records.", "",
             "|Arm|M|Total archive B|Change vs spatial M6|Change %|Wins/losses|", "|---|---:|---:|---:|---:|---:|"]
    for row in summary:
        lines.append(f"|{row['arm']}|{row['width']}|{row['total_archive_bytes']:,}|{row['delta_bytes_vs_spatial_m6']:+,}|{row['percent_change_vs_spatial_m6']:+.4f}%|{row['wins_vs_spatial_m6']}/{row['losses_vs_spatial_m6']}|")
    lines += ["", f"Frozen selection rule chooses **{selected['arm']}**. This is exposed development calibration within the tested candidates, not a universal optimum.", "",
              "The row-order arm is a mechanism control and is never eligible for spatial-default selection. Value streams, value model members, the production value graph, identities and coordinates remained byte-identical to each sample's K32 anchor."]
    (HERE / "RESULT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"rows": len(rows), "selected": selected["arm"]}, indent=2))


if __name__ == "__main__":
    main()
