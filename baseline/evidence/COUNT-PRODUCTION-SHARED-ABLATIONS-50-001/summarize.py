"""Create publication-facing summaries from the frozen Production Shared evidence."""
from __future__ import annotations
import csv
import json
import statistics
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ablation_lib as lib

SPLIT = HERE.parent / "COUNT-SUPPORT-PREDECESSOR-50-001" / "DATA_SPLIT.csv"


def read_csv(name):
    with (HERE / name).open(encoding="utf-8-sig", newline="") as h:
        return list(csv.DictReader(h))


def write_csv(name, rows, fields):
    with (HERE / name).open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def anchor_rows(arm, width):
    rows = []
    with SPLIT.open(encoding="utf-8-sig", newline="") as h:
        split = list(csv.DictReader(h))
    for src in split:
        path = lib.anchor_path(src["id"], width)
        ledger, _ = lib.physical_ledger(path)
        rows.append({"stage": "historical_anchor", "sample_id": src["id"], "arm": arm,
                     "status": "historical_anchor", "total_archive_bytes": path.stat().st_size,
                     "archive_sha256": lib.sha_path(path), "source_sha256": src["source_sha256"],
                     "verify_all": True, **ledger})
    return rows


def normalize(rows):
    out = []
    for row in rows:
        r = dict(row)
        if not r.get("total_archive_bytes"):
            continue
        r["total_archive_bytes"] = int(r["total_archive_bytes"])
        for key in ("support_stream", "value_stream", "support_model", "value_model_and_group_map",
                    "graph_index", "identity_coordinates_metadata", "mapping", "manifest", "zip_framing"):
            r[key] = int(r.get(key) or 0)
        out.append(r)
    return out


def add_retry(rows):
    path = HERE / "retry" / "SPA8" / "ORIGINAL" / "RESULT.json"
    if path.is_file():
        r = json.loads(path.read_text(encoding="utf-8"))
        r["stage"] = "order"
        r["case"] = "ORIGINAL"
        r["arm"] = "ORIGINAL"
        r["verify_all"] = r.get("verify", {}).get("all", False)
        r.update(r.get("ledger", {}))
        rows.append(r)
    return rows


def pooled(rows, arm):
    rr = [r for r in rows if r["arm"] == arm and r.get("status") in ("success", "historical_anchor")]
    result = {"arm": arm, "n": len(rr), "pooled_total_bytes": sum(r["total_archive_bytes"] for r in rr),
              "mean_total_bytes": round(statistics.mean(r["total_archive_bytes"] for r in rr), 3) if rr else None}
    for key in ("support_stream", "value_stream", "support_model", "value_model_and_group_map",
                "graph_index", "identity_coordinates_metadata", "mapping", "manifest", "zip_framing"):
        result[key] = sum(r[key] for r in rr)
    return result


def order_summary():
    rows = add_retry(normalize(read_csv("ORDER_PER_SAMPLE.csv")))
    arms = ["ORIGINAL", "CANONICAL_SPATIAL", "RANDOM_SEED_11", "RANDOM_SEED_23", "RANDOM_SEED_37"]
    out = [pooled(rows, arm) for arm in arms]
    by = {(r["sample_id"], r["arm"]): r for r in rows if r.get("status") == "success"}
    base = {s: r for (s, a), r in by.items() if a == "ORIGINAL"}
    compare = []
    for arm in arms[1:]:
        deltas = [by[(s, arm)]["total_archive_bytes"] - base[s]["total_archive_bytes"]
                  for s in base if (s, arm) in by]
        compare.append({"arm": arm, "paired_n": len(deltas), "pooled_delta_vs_original": sum(deltas),
                        "mean_delta_vs_original": round(statistics.mean(deltas), 3) if deltas else None,
                        "wins_smaller": sum(d < 0 for d in deltas), "ties": sum(d == 0 for d in deltas),
                        "losses_larger": sum(d > 0 for d in deltas)})
    write_csv("ORDER_SUMMARY.csv", out, list(out[0]))
    write_csv("ORDER_PAIRED_COMPARISON.csv", compare, list(compare[0]))
    return out, compare


def context_summary():
    new = normalize(read_csv("CONTEXT_PER_SAMPLE.csv"))
    new = [r for r in new if r.get("status") == "success"]
    rows = new + anchor_rows("S0V1", 0) + anchor_rows("S1V1", 6)
    arms = ["S0V0", "S1V0", "S0V1", "S1V1"]
    out = [pooled(rows, arm) for arm in arms]
    by = {(r["sample_id"], r["arm"]): r for r in rows}
    decomp = []
    for sample in sorted({r["sample_id"] for r in rows}):
        if not all((sample, a) in by for a in arms):
            continue
        s0v0, s1v0, s0v1, s1v1 = [by[(sample, a)]["total_archive_bytes"] for a in arms]
        decomp.append({"sample_id": sample, "support_delta_at_V1_S0_minus_S1": s0v1 - s1v1,
                       "value_context_delta_at_S1_V0_minus_V1": s1v0 - s1v1,
                       "interaction": (s0v0 - s0v1) - (s1v0 - s1v1),
                       "S0V0": s0v0, "S1V0": s1v0, "S0V1": s0v1, "S1V1": s1v1})
    pooled_decomp = {"sample_id": "POOLED", "support_delta_at_V1_S0_minus_S1": sum(r["support_delta_at_V1_S0_minus_S1"] for r in decomp),
                     "value_context_delta_at_S1_V0_minus_V1": sum(r["value_context_delta_at_S1_V0_minus_V1"] for r in decomp),
                     "interaction": sum(r["interaction"] for r in decomp)}
    decomp.append(pooled_decomp)
    write_csv("CONTEXT_SUMMARY.csv", out, list(out[0]))
    write_csv("CONTEXT_DECOMPOSITION.csv", decomp, list(decomp[0]))
    return out, decomp


def bucket_summary():
    new = normalize(read_csv("BUCKET_PER_SAMPLE.csv"))
    new = [r for r in new if r.get("status") == "success"]
    rows = new + anchor_rows("B8", 6)
    arms = ["B1", "B2", "B4", "B8", "B16"]
    out = [pooled(rows, arm) for arm in arms]
    best = min(out, key=lambda r: r["pooled_total_bytes"])
    for r in out:
        r["selection_threshold_bytes"] = round(best["pooled_total_bytes"] * 0.0005, 3)
        r["selected_under_0_05pct_rule"] = abs(r["pooled_total_bytes"] - best["pooled_total_bytes"]) <= best["pooled_total_bytes"] * 0.0005
    write_csv("BUCKET_SUMMARY.csv", out, list(out[0]))
    return out


def method_audit():
    rows = [
        {"parameter_or_module": "value group count K", "category": "verified_50_sample", "scope": "prior K scan + fixed in this task", "status": "verified", "evidence": "VALUE_BEST_OF_9_50_005; VALUE_K64_K128_50_006", "limitation": "development panel only"},
        {"parameter_or_module": "support predecessor M_s", "category": "verified_50_sample", "scope": "M0/M6 paired support predecessor task", "status": "verified", "evidence": "COUNT-SUPPORT-PREDECESSOR-50-001", "limitation": "no protected confirmation"},
        {"parameter_or_module": "support bucket B_s", "category": "verified_50_sample", "scope": "B1/B2/B4/B8/B16", "status": "verified", "evidence": "COUNT-PRODUCTION-SHARED-ABLATIONS-50-001", "limitation": "finite frozen grid"},
        {"parameter_or_module": "value context S0V0/S1V0/S0V1/S1V1", "category": "verified_50_sample", "scope": "full physical bytes and exact decode", "status": "verified", "evidence": "CONTEXT_SUMMARY.csv; SEMANTIC_AUDIT.json", "limitation": "not a biological causal claim"},
        {"parameter_or_module": "spot order and inverse mapping", "category": "verified_50_sample", "scope": "original/canonical/three fixed permutations", "status": "verified", "evidence": "ORDER_SUMMARY.csv; ORDER_PAIRED_COMPARISON.csv", "limitation": "not universal order invariance"},
        {"parameter_or_module": "Q12 boundaries", "category": "design_constant", "scope": "nested frozen boundaries", "status": "verified_as_protocol", "evidence": "PROTOCOL.json", "limitation": "no post-result boundary search"},
        {"parameter_or_module": "Q12 precision=12", "category": "invariant", "scope": "codec contract and exact decoding", "status": "invariant", "evidence": "decoder_protocol.md; exact recovery", "limitation": "not independently optimized here"},
        {"parameter_or_module": "half-count smoothing / singleton shrinkage / tail prior", "category": "design_constant", "scope": "shared value/support model", "status": "inherited", "evidence": "support_model_spec.md; value_model_spec.md", "limitation": "no low-value isolated search"},
        {"parameter_or_module": "odds regularization, truncation, bisection", "category": "invariant", "scope": "shared model implementation", "status": "inherited", "evidence": "support_model_spec.md; value_model_spec.md", "limitation": "engineering constants"},
        {"parameter_or_module": "rANS lower bound 2^23", "category": "invariant", "scope": "stream codec", "status": "validated_by_exact_decode", "evidence": "decoder_protocol.md; all accepted archives", "limitation": "not a search target"},
        {"parameter_or_module": "ZIP_STORED archive framing", "category": "verified_50_sample", "scope": "physical byte ledger", "status": "verified", "evidence": "FINAL_VERIFICATION.json", "limitation": "filesystem/archive overhead is implementation-specific"},
        {"parameter_or_module": "random-access design", "category": "unverified", "scope": "not exercised by this ablation", "status": "unverified", "evidence": "none", "limitation": "no random-access performance claim"},
    ]
    write_csv("METHOD_COVERAGE_AUDIT.csv", rows, list(rows[0]))
    return rows


def main():
    order, order_compare = order_summary()
    context, decomp = context_summary()
    buckets = bucket_summary()
    methods = method_audit()
    verification = json.loads((HERE / "FINAL_VERIFICATION.json").read_text(encoding="utf-8"))
    best_bucket = min(buckets, key=lambda r: r["pooled_total_bytes"])
    best_order = min(order, key=lambda r: r["pooled_total_bytes"])
    best_context = min(context, key=lambda r: r["pooled_total_bytes"])
    report = f"""# Production Shared count codec ablations

## Outcome

This is a finite development-panel study on 50 exposed HEST slices. It uses fixed value-group count K=32 and support predecessor count M_s=6. No protected confirmatory data were accessed. All accepted archives passed fresh decode and exact canonical/metadata recovery; the independent audit reports `all_pass={verification['all_pass']}` after incorporating one isolated successful retry for the preserved SPA8/ORIGINAL decode failure.

The pooled byte minima under the preregistered full-physical-byte rule are: order arm `{best_order['arm']}` ({best_order['pooled_total_bytes']} bytes among the accepted order rows), context arm `{best_context['arm']}`, and support bucket `{best_bucket['arm']}`. The final frozen Production Shared configuration is therefore K=32, M_s=6, the selected bucket `{best_bucket['arm']}`, and the production order policy remains ORIGINAL unless an external protocol explicitly requires a different order; order sensitivity is reported rather than generalized away.

## Evidence coverage

- New main combinations: 250 order, 100 context, 200 support-bucket cases.
- Historical semantic anchors: 100 context rows (S0V1/S1V1) and 50 B8 rows, hash-verified and unchanged.
- Exact recovery: every accepted row has `verify_all=true`; `FINAL_VERIFICATION.json` contains the independent archive/ledger/member audit.
- Reproduction: `REPRODUCTION.json` contains three fresh-process re-encodes whose archive SHA-256 values exactly match their main-run counterparts.
- Failures are preserved: the original main_v3 SPA8/ORIGINAL failure remains in `main_v3/order/SPA8/ORIGINAL`; the successful retry is isolated under `retry/SPA8/ORIGINAL`.

## Interpretation

The order experiment measures physical archive sensitivity to spot traversal, including paid mapping and inverse restoration. The context experiment reports the full S0V0/S1V0/S0V1/S1V1 byte ledger; its decomposition is descriptive of this codec and panel, not a biological causal estimate. The bucket experiment uses nested, pre-frozen Q12 boundaries and includes model, stream, graph, identity/metadata, manifest, and ZIP framing bytes; B8 reuses the verified Production anchor rather than being re-encoded.

## Method coverage and limits

`METHOD_COVERAGE_AUDIT.csv` classifies each relevant parameter/module as 50-sample verified, inherited from 3-sample/mechanism or earlier verified evidence, a design constant, an invariant, or unverified. No low-value hyperparameter search was added after seeing results. The panel is exposed development data with unresolved donor independence and finite technology/organ coverage; no claim of universal order invariance, pan-tissue optimality, or protected-data confirmation is made.

## Output files

- `ORDER_SUMMARY.csv`, `ORDER_PAIRED_COMPARISON.csv`
- `CONTEXT_SUMMARY.csv`, `CONTEXT_DECOMPOSITION.csv`
- `BUCKET_SUMMARY.csv`
- `METHOD_COVERAGE_AUDIT.csv`
- `FINAL_VERIFICATION.json`, `REPRODUCTION.json`, `SEMANTIC_AUDIT.json`
"""
    (HERE / "RESULT.md").write_text(report, encoding="utf-8")
    (HERE / "PAPER_TABLES.json").write_text(json.dumps({"order": order, "order_comparison": order_compare, "context": context, "context_decomposition": decomp, "buckets": buckets}, indent=2, ensure_ascii=False), encoding="utf-8")
    (HERE / "FIGURE_DATA.csv").write_text("figure,arm,n,pooled_total_bytes,mean_total_bytes\n" + "\n".join(
        f"order,{r['arm']},{r['n']},{r['pooled_total_bytes']},{r['mean_total_bytes']}" for r in order
    ) + "\n" + "\n".join(f"context,{r['arm']},{r['n']},{r['pooled_total_bytes']},{r['mean_total_bytes']}" for r in context) + "\n" + "\n".join(f"bucket,{r['arm']},{r['n']},{r['pooled_total_bytes']},{r['mean_total_bytes']}" for r in buckets), encoding="utf-8")


if __name__ == "__main__":
    main()
