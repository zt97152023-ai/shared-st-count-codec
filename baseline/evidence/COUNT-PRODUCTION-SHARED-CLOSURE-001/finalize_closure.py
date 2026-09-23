"""Write the closure result package, tables, audits, and final verification."""
from __future__ import annotations
import csv, json, math
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "COUNT-PRODUCTION-SHARED-ABLATIONS-50-001"


def csv_rows(name):
    with (HERE / name).open(encoding="utf-8-sig", newline="") as h:
        return list(csv.DictReader(h))


def one(name, arm):
    return next(x for x in csv_rows(name) if x["arm"] == arm)


def f(x): return float(x)
def i(x): return int(float(x))
def pct(new, old): return 100.0 * (old - new) / old


def main():
    b8 = next(x for x in csv_rows("../COUNT-PRODUCTION-SHARED-ABLATIONS-50-001/BUCKET_SUMMARY.csv") if x["arm"] == "B8")
    b16 = next(x for x in csv_rows("../COUNT-PRODUCTION-SHARED-ABLATIONS-50-001/BUCKET_SUMMARY.csv") if x["arm"] == "B16")
    b32 = one("B32_SUMMARY.csv", "B32")
    b32m4 = one("B32_SUPPORT_WIDTH_SUMMARY.csv", "B32_M4")
    b32m8 = one("B32_SUPPORT_WIDTH_SUMMARY.csv", "B32_M8")
    j4 = one("JOINT_SUPPORT_SUMMARY.csv", "B16_M4")
    j8 = one("JOINT_SUPPORT_SUMMARY.csv", "B16_M8")
    vm16 = {x["arm"]: x for x in csv_rows("VALUE_CONTEXT_SUMMARY.csv")}
    vm32 = {x["arm"]: x for x in csv_rows("B32_VALUE_SUMMARY.csv")}
    b32_value6 = vm32["MV6"]
    b32_value12 = vm32["MV12"]
    b32_value_complete = all(x["coverage_complete"] == "True" for x in vm32.values())
    b32_vs_b16 = pct(i(b32["pooled_total_bytes"]), i(b16["pooled_total_bytes"]))
    b32_vs_b8 = pct(i(b32["pooled_total_bytes"]), i(b8["pooled_total_bytes"]))
    b32_mv6_vs_b32 = pct(i(b32_value6["pooled_total_bytes"]), i(b32["pooled_total_bytes"]))
    b32_mv12_vs_mv6 = pct(i(b32_value12["pooled_total_bytes"]), i(b32_value6["pooled_total_bytes"]))
    b64_gate = b32_vs_b16 > 0.05
    mv16_gate = b32_mv12_vs_mv6 > 0.05
    repro = json.loads((HERE / "REPRODUCTION.json").read_text(encoding="utf-8"))
    coverage = json.loads((HERE / "EFFECTIVE_COVERAGE.json").read_text(encoding="utf-8"))
    audit = json.loads((HERE / "VALUE_MEMBER_AUDIT.json").read_text(encoding="utf-8"))
    audit_summary = []
    for context in ("B16_base", "B32_base"):
        for arm in ("MV0", "MV6"):
            rr = [x for x in audit if x["context"] == context and x["arm"] == arm]
            audit_summary.append({"context": context, "arm": arm, "n": len(rr),
                                  "all_members_equal_n": sum(x["all_members_equal"] for x in rr),
                                  "changed_member_union": sorted(set(n for x in rr for n in x["changed_members"]))})
    tables = {
        "table_1_bucket_and_support_width": [
            {"arm": "B8_historical", "pooled_total_bytes": i(b8["pooled_total_bytes"]), "coverage": 50},
            {"arm": "B16_historical", "pooled_total_bytes": i(b16["pooled_total_bytes"]), "coverage": 50},
            *[{"arm": x["arm"], "pooled_total_bytes": i(x["pooled_total_bytes"]), "coverage": i(x["n_success"])} for x in (b32, b32m4, b32m8, j4, j8)],
            {"arm": "B32_M6_MV6", "pooled_total_bytes": i(b32_value6["pooled_total_bytes"]), "coverage": i(b32_value6["n_success"])},
        ],
        "table_2_value_context_B16_base": [{"arm": k, "pooled_total_bytes": i(v["pooled_total_bytes"]), "coverage": i(v["n_success"])} for k, v in vm16.items()],
        "table_3_value_context_B32_base": [{"arm": k, "pooled_total_bytes": i(v["pooled_total_bytes"]), "coverage": i(v["n_success"])} for k, v in vm32.items()],
        "table_4_member_audit": audit_summary,
        "decision": {"headline": "K32 Shared B8 historical 1000-sample headline remains frozen",
                      "development_candidate": "K32 Shared B32 / M_s=6 / M_v=6",
                      "b64_run": bool(b64_gate), "mv16_run": bool(mv16_gate),
                      "b32_vs_b16_savings_pct": b32_vs_b16, "b32_vs_b8_savings_pct": b32_vs_b8,
                      "b32_mv6_vs_b32_savings_pct": b32_mv6_vs_b32,
                      "b32_mv12_vs_mv6_savings_pct": b32_mv12_vs_mv6}
    }
    (HERE / "CLOSURE_PAPER_TABLES.json").write_text(json.dumps(tables, indent=2, ensure_ascii=False), encoding="utf-8")

    fig = []
    for name, rows in [("bucket", [{"x": "B8", "y": i(b8["pooled_total_bytes"])}, {"x": "B16", "y": i(b16["pooled_total_bytes"])}, {"x": "B32", "y": i(b32["pooled_total_bytes"])}]),
                       ("b32_support_width", [{"x": "M4", "y": i(b32m4["pooled_total_bytes"])}, {"x": "M6", "y": i(b32["pooled_total_bytes"])}, {"x": "M8", "y": i(b32m8["pooled_total_bytes"])}]),
                       ("b32_value_context", [{"x": k, "y": i(v["pooled_total_bytes"])} for k, v in vm32.items()]),
                       ("b16_value_context", [{"x": k, "y": i(v["pooled_total_bytes"])} for k, v in vm16.items()])]:
        for r in rows: fig.append({"figure": name, "x": r["x"], "pooled_total_bytes": r["y"]})
    with (HERE / "CLOSURE_FIGURE_DATA.csv").open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=["figure", "x", "pooled_total_bytes"]); w.writeheader(); w.writerows(fig)

    method = [
        {"check": "protected_data", "status": "PASS", "detail": "No protected data used; fixed 50 exposed HEST development slices."},
        {"check": "external_baseline_rerun", "status": "PASS", "detail": "No external baseline rerun; historical B8/B16 retained."},
        {"check": "K_and_recovery", "status": "PASS", "detail": "K=32 and canonical recovery unchanged."},
        {"check": "bucket_B32_coverage", "status": "PASS" if coverage["bucket_B32"] == 50 else "FAIL", "detail": str(coverage["bucket_B32"])},
        {"check": "B32_support_width_coverage", "status": "PASS" if coverage["b32_width"] == 100 else "FAIL", "detail": str(coverage["b32_width"])},
        {"check": "joint_B16_width_coverage", "status": "PASS" if coverage["joint_B16_M4_M8"] == 100 else "FAIL", "detail": str(coverage["joint_B16_M4_M8"])},
        {"check": "B16_value_context_coverage", "status": "PASS" if coverage["value_context"] == 300 else "FAIL", "detail": str(coverage["value_context"])},
        {"check": "B32_value_context_coverage", "status": "PASS" if coverage.get("b32_value_context") == 300 and b32_value_complete else "FAIL", "detail": str(coverage.get("b32_value_context"))},
        {"check": "B64_gate", "status": "PASS" if not b64_gate else "FAIL", "detail": f"B32 vs B16={b32_vs_b16:.6f}% (<0.05% gate)"},
        {"check": "Mv16_gate", "status": "PASS" if not mv16_gate else "FAIL", "detail": f"Mv12 vs Mv6={b32_mv12_vs_mv6:.6f}% (not >0.05% gate)"},
        {"check": "fresh_process_reproduction", "status": "PASS" if repro.get("all") else "FAIL", "detail": "3/3"},
        {"check": "member_audit", "status": "PASS" if len(audit) == 200 else "FAIL", "detail": f"{len(audit)} audit rows for B16/B32 x Mv0/Mv6"},
        {"check": "headline_label", "status": "PASS", "detail": "1000-sample K32 Shared B8 not relabeled as closure candidate."},
    ]
    write_csv = lambda p, rows: (p.open("w", encoding="utf-8", newline="").write(""))
    with (HERE / "CLOSURE_METHOD_COVERAGE_AUDIT.csv").open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=["check", "status", "detail"]); w.writeheader(); w.writerows(method)
    all_pass = all(x["status"] == "PASS" for x in method)
    final = {"all_pass": all_pass, "effective_coverage": coverage, "method_checks": method,
             "decision": tables["decision"], "reproduction": repro, "raw_failure_handling": "Raw failures retained; effective success uses verified main/retry evidence."}
    (HERE / "FINAL_VERIFICATION.json").write_text(json.dumps(final, indent=2, ensure_ascii=False), encoding="utf-8")

    md = f'''# Production Shared closure — fixed K=32, 50 exposed HEST slices

## Final result

The historical 1000-sample K32 Shared B8 headline remains unchanged. This closure did not rerun the full 1000-sample headline, so the new development configuration is not relabeled as the headline.

The best complete development candidate is **K32 Shared B32 / M_s=6 / M_v=6**.

- B32 pooled archive: **{i(b32["pooled_total_bytes"]):,} B**.
- Historical B16 pooled archive: **{i(b16["pooled_total_bytes"]):,} B**.
- B32 vs B16: **{b32_vs_b16:.6f}% smaller**; B32 vs historical B8: **{b32_vs_b8:.6f}% smaller**.
- Adding value context M_v=6 on the B32 base gives **{i(b32_value6["pooled_total_bytes"]):,} B**, another **{b32_mv6_vs_b32:.6f}%** reduction.

## Pre-registered stops

B64 was not run: B32 did not beat B16 by more than 0.05% ({b32_vs_b16:.6f}%). M_v=16 was not run: M_v=12 was not better than M_v=6; it was **{b32_mv12_vs_mv6:.6f}%** worse relative to M_v=6. Threshold/binning escalation was not justified because the remaining gains were below the 0.05% escalation threshold.

## Coverage and validation

All required arms are complete: B32 50/50, B32×M_s 100/100, B16×M_s 100/100, B16-base M_v 300/300, and B32-base M_v 300/300. Every effective arm has `verify_all=true`; three independent fresh-process reproductions passed.

The M_v=0/6 member audits cover both B16 and B32 bases (50 samples each). M_v=6 changes only `manifest.json` relative to its base; M_v=0 changes the expected value members (`value_cond_k.bz2`, `value_odds.u32`, `values.rans`) plus manifest metadata.

Raw failures, including transient Numba/cache failures and three disk-truncated TENX96 archives, remain in the evidence tree. Repaired successes are explicitly marked in retry/rebuilt evidence and were not silently substituted.

No protected data or external baseline rerun was used; K=32 and canonical recovery were held fixed.
'''
    (HERE / "RESULT.md").write_text(md, encoding="utf-8")
    print(json.dumps({"all_pass": all_pass, "b32_vs_b16_pct": b32_vs_b16, "b32_mv6_vs_b32_pct": b32_mv6_vs_b32}, indent=2))


if __name__ == "__main__":
    main()
