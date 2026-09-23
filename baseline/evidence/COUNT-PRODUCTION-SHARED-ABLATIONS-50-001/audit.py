"""Independent read-only audit for the completed main_v3 evidence."""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import ablation_lib as lib


def load_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as h:
        return list(csv.DictReader(h))


def check_result(path):
    r = json.loads(path.read_text(encoding="utf-8"))
    checks = {"status_success": r.get("status") == "success", "verify_all": r.get("verify", {}).get("all") is True}
    archive = path.parent / "archive.cnt"
    checks["archive_exists"] = archive.is_file()
    if archive.is_file():
        cats, members = lib.physical_ledger(archive)
        checks["ledger_exact"] = sum(cats.values()) == archive.stat().st_size
        checks["archive_sha"] = r.get("archive_sha256") == lib.sha_path(archive)
        receipts = r.get("members", {})
        if not receipts:
            ledger_path = path.parent / "ledger.json"
            if ledger_path.is_file():
                ledger = json.loads(ledger_path.read_text(encoding="utf-8"))["ledger"]
                receipts = ledger[1]
        checks["member_receipts"] = all(receipts.get(name, {}).get("sha256") == rec["sha256"] for name, rec in members.items())
    else:
        checks.update(ledger_exact=False, archive_sha=False, member_receipts=False)
    checks["all"] = all(checks.values())
    return checks


def main():
    root = HERE / "main_v3"
    result_paths = sorted(root.glob("**/RESULT.json"))
    rows = []
    for path in result_paths:
        checks = check_result(path)
        rows.append({"path": str(path), **checks})
    retry_paths = sorted((HERE / "retry").glob("**/RESULT.json")) if (HERE / "retry").exists() else []
    retry_rows = [{"path": str(path), **check_result(path)} for path in retry_paths]
    effective_rows = [r for r in rows if r["status_success"] and r["verify_all"]] + retry_rows
    all_pass = bool(effective_rows) and all(r["all"] for r in effective_rows)
    # No partial result is silently accepted as a complete arm.
    expected = {"order": 50 * 5, "context": 50 * 2, "bucket": 50 * 4}
    observed = {}
    for k in expected:
        main_ok = sum(1 for r in rows if r["path"].replace("\\", "/").split("/main_v3/")[-1].startswith(k + "/") and r["status_success"] and r["verify_all"])
        retry_ok = len(retry_rows) if k == "order" else 0
        observed[k] = main_ok + retry_ok
    coverage = {k: {"expected_new": v, "observed": observed[k], "complete": observed[k] == v} for k, v in expected.items()}
    all_pass = all_pass and all(x["complete"] for x in coverage.values())
    out = {"all_pass": all_pass, "result_count": len(rows), "effective_result_count": len(effective_rows), "coverage": coverage, "rows": rows, "retry_rows": retry_rows,
           "preserved_failed_result_dirs": len(list((HERE / "main_v2").glob("**/FAILURE.json"))) if (HERE / "main_v2").exists() else 0,
           "main_v3_failed_result_dirs": sum(1 for r in rows if not r["all"]),
           "semantic_audit": json.loads((HERE / "SEMANTIC_AUDIT.json").read_text(encoding="utf-8"))["all_pass"]}
    out["all_pass"] = out["all_pass"] and out["semantic_audit"]
    (HERE / "FINAL_VERIFICATION.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    if not out["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
