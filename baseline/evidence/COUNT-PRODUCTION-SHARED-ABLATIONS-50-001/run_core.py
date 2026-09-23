"""Bounded main runner and report builder for the methods-ablation contract."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import ablation_lib as lib

OUT = HERE / "main_v3"
REPRO = HERE / "reproduction"
PY = Path(sys.executable)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def source_for(sample_id):
    return next(r["source_path"] for r in lib.read_csv_rows() if r["id"] == sample_id)


def run_worker(args, folder, report_name, timeout=1800):
    folder.mkdir(parents=True, exist_ok=True)
    report = folder / report_name
    log = folder / (Path(report_name).stem + ".log")
    env = os.environ.copy()
    env.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMBA_NUM_THREADS": "1", "PYTHONUTF8": "1"})
    env["NUMBA_CACHE_DIR"] = str(HERE / "numba_cache_v3")
    # The first main invocation was interrupted while a stale cross-task
    # Numba cache process held an import/compile path.  Disable cache writes in
    # the resumed contract; the interruption and its evidence remain under
    # main/ and the result is scientifically unchanged.
    env["NUMBA_DISABLE_CACHING"] = "1"
    cmd = [str(PY), "-X", "utf8", str(HERE / "worker.py"), *args, "--report", str(report)]
    started = time.perf_counter()
    with log.open("w", encoding="utf-8") as handle:
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT)
        try:
            rc = proc.wait(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            proc.kill(); rc = proc.wait(); timed_out = True
    receipt = {"command": cmd, "returncode": rc, "timed_out": timed_out, "elapsed_seconds": time.perf_counter() - started}
    write(folder / (Path(report_name).stem + "_resource.json"), receipt)
    if rc != 0 or not report.exists():
        raise RuntimeError(f"worker failed: {cmd}")
    return json.loads(report.read_text(encoding="utf-8")), receipt


def run_case(stage, sample_id, case_name, folder, **kwargs):
    result_path = folder / "RESULT.json"
    if result_path.exists():
        old = json.loads(result_path.read_text(encoding="utf-8"))
        if old.get("status") == "success" and (folder / "verify.json").exists():
            return old
    folder.mkdir(parents=True, exist_ok=False)
    source = source_for(sample_id)
    try:
        archive = folder / "archive.cnt"
        if stage == "context":
            encode_args = ["context", "--sample", sample_id, "--width", str(kwargs["width"]), "--value-context", str(kwargs["value_context"]), "--output", str(archive)]
        elif stage == "bucket":
            encode_args = ["bucket", "--sample", sample_id, "--buckets", str(kwargs["B"]), "--output", str(archive)]
        elif stage == "order":
            encode_args = ["order", "--sample", sample_id, "--arm", case_name, "--output", str(archive), "--scratch", str(folder / "scratch")]
        else:
            raise ValueError(stage)
        encoded, _ = run_worker(encode_args, folder, "encode.json")
        decoded, _ = run_worker(["decode", "--package", str(archive), "--output", str(folder / "decoded")], folder, "decode.json")
        verified, _ = run_worker(["verify", "--source", source, "--output", str(folder / "decoded")], folder, "verify.json")
        if not verified.get("all"):
            raise RuntimeError("exact recovery gate failed")
        result = dict(encoded)
        result.update({"stage": stage, "case": case_name, "sample_id": sample_id,
                       "source_path": source, "source_sha256": lib.sha_path(Path(source)),
                       "decode": decoded, "verify": verified})
        write(result_path, result)
        # Generated CSR payloads are removed only after the independent exact
        # check. Metadata and all receipts remain for audit.
        npz = folder / "decoded" / "decoded.npz"
        if npz.exists():
            write(folder / "DECODED_RETENTION.json", {"path": str(npz), "bytes": npz.stat().st_size, "sha256": lib.sha_path(npz), "removed_after_exact": True})
            npz.unlink()
        return result
    except Exception as exc:
        failure = {"stage": stage, "case": case_name, "sample_id": sample_id, "error": repr(exc), "source_path": source}
        write(folder / "FAILURE.json", failure)
        write(result_path, {"stage": stage, "case": case_name, "sample_id": sample_id, "status": "failed", "error": repr(exc)})
        return json.loads(result_path.read_text(encoding="utf-8"))


def anchor_result(sample_id, width):
    path = lib.anchor_path(sample_id, width)
    result = json.loads((path.parent / "RESULT.json").read_text(encoding="utf-8"))
    # The support runner's ledger uses the same physical categories plus a
    # support-graph increment field. Keep the raw categories and normalize only
    # for cross-arm tables.
    result = dict(result)
    result["archive_path"] = str(path)
    result["total_archive_bytes"] = int(path.stat().st_size)
    result["status"] = "historical_anchor_semantic_audit"
    return result


def semantic_audit(rows):
    import importlib.util
    support_codec = lib.load_module(lib.SUPPORT_TEMPLATE.parent / "codec.py", "production_ablation_support_audit_codec")
    audit = []
    for row in rows:
        raw = lib.raw_input(row["source_path"])
        p0 = lib.anchor_path(row["id"], 0); p6 = lib.anchor_path(row["id"], 6)
        m0, a0, _ = support_codec.read_archive(p0); m6, a6, _ = support_codec.read_archive(p6)
        fixed = ["value_q1.bz2", "value_group.bz2", "value_base_k.bz2", "value_odds.u32", "value_cond_k.bz2", "values.rans", "graph.bz2", "metadata.bz2", "base_probability.bz2"]
        equal = {name: a0[name] == a6[name] for name in fixed}
        audit.append({"sample_id": row["id"], "S0V1_archive": str(p0), "S1V1_archive": str(p6),
                      "S0V1_bytes": p0.stat().st_size, "S1V1_bytes": p6.stat().st_size,
                      "canonical_sha256": m6["canonical_sha256"], "metadata_sha256": m6["metadata_sha256"],
                      "value_members_equal": all(equal[name] for name in fixed[:6]),
                      "value_member_checks": {name: equal[name] for name in fixed[:6]},
                      "graph_equal": equal["graph.bz2"], "metadata_equal": equal["metadata.bz2"],
                      "anchor_identity_ok": m0["canonical_sha256"] == m6["canonical_sha256"] == lib.runtime_io().csr_sha(raw.matrix)})
    if not all(x["value_members_equal"] and x["anchor_identity_ok"] for x in audit):
        raise RuntimeError("S0V1/S1V1 semantic audit failed")
    write(HERE / "SEMANTIC_AUDIT.json", {"n": len(audit), "all_pass": True, "rows": audit})
    return audit


def flatten_rows(stage, rows):
    out = []
    for r in rows:
        if r.get("status") != "success":
            out.append({"stage": stage, "sample_id": r.get("sample_id"), "arm": r.get("arm") or r.get("case"), "status": r.get("status"), "total_archive_bytes": "", "error": r.get("error", "")})
            continue
        line = {"stage": stage, "sample_id": r.get("sample_id"), "arm": r.get("arm") or r.get("case"), "status": r.get("status"), "total_archive_bytes": r.get("total_archive_bytes"), "archive_sha256": r.get("archive_sha256"), "source_sha256": r.get("source_sha256", ""), "mapping_bytes": r.get("mapping_bytes", 0)}
        for key, value in r.get("ledger", {}).items():
            line[key] = value
        line["verify_all"] = r.get("verify", {}).get("all", "")
        out.append(line)
    return out


def write_csv(path, rows):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = []
    for row in rows:
        for key in row:
            if key not in fields: fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def stratified(rows, manifest_rows):
    by_id = {r["id"]: r for r in manifest_rows}
    out = []
    arms = sorted({r["arm"] for r in rows if r.get("status") == "success"})
    for arm in arms:
        selected = [r for r in rows if r.get("arm") == arm and r.get("status") == "success"]
        for field in ["st_technology", "species", "organ"]:
            for value in sorted({by_id[r["sample_id"]].get(field, "") for r in selected}):
                group = [r for r in selected if by_id[r["sample_id"]].get(field, "") == value]
                out.append({"arm": arm, "stratum_type": field, "stratum": value, "n": len(group), "total_archive_bytes": sum(int(x["total_archive_bytes"]) for x in group), "mean_archive_bytes": sum(int(x["total_archive_bytes"]) for x in group) / len(group)})
    return out


def run_all():
    rows = lib.read_csv_rows()
    write(HERE / "INPUT_PINS.json", {"manifest_sha256": lib.sha_path(lib.MANIFEST), "sources": {r["id"]: {"path": r["source_path"], "sha256": lib.sha_path(Path(r["source_path"]))} for r in rows}, "protocol_sha256": lib.sha_path(HERE / "PROTOCOL.json")})
    semantic_audit(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    order_arms = ["ORIGINAL", "CANONICAL_SPATIAL", "RANDOM_SEED_11", "RANDOM_SEED_23", "RANDOM_SEED_37"]
    context_results = []
    order_results = []
    bucket_results = []
    for row in rows:
        sid = row["id"]
        for arm in order_arms:
            order_results.append(run_case("order", sid, arm, OUT / "order" / sid / arm))
        for width, value_context, arm in [(0, 0, "S0V0"), (6, 0, "S1V0")]:
            context_results.append(run_case("context", sid, arm, OUT / "context" / sid / arm, width=width, value_context=value_context))
        for B in [1, 2, 4, 16]:
            bucket_results.append(run_case("bucket", sid, f"B{B}", OUT / "bucket" / sid / f"B{B}", B=B))
    # Existing S0V1/S1V1 and B8 are retained as explicit historical arms.
    context_all = []
    for row in rows:
        context_all.extend([anchor_result(row["id"], 0) | {"sample_id": row["id"], "arm": "S0V1"}, anchor_result(row["id"], 6) | {"sample_id": row["id"], "arm": "S1V1"}])
    bucket_all = list(bucket_results)
    for row in rows:
        bucket_all.append(anchor_result(row["id"], 6) | {"sample_id": row["id"], "arm": "B8"})
    all_order = flatten_rows("order", order_results)
    all_context = flatten_rows("context", context_results) + flatten_rows("context_anchor", context_all)
    all_bucket = flatten_rows("bucket", bucket_all)
    write_csv(HERE / "ORDER_PER_SAMPLE.csv", all_order)
    write_csv(HERE / "CONTEXT_PER_SAMPLE.csv", all_context)
    write_csv(HERE / "BUCKET_PER_SAMPLE.csv", all_bucket)
    write_csv(HERE / "ORDER_STRATIFIED.csv", stratified(all_order, rows))
    write_csv(HERE / "CONTEXT_STRATIFIED.csv", stratified(all_context, rows))
    write_csv(HERE / "BUCKET_STRATIFIED.csv", stratified(all_bucket, rows))
    write(HERE / "MAIN_COUNTS.json", {"order": len(order_results), "context_new": len(context_results), "bucket_new": len(bucket_results), "samples": len(rows), "context_anchor": len(context_all), "bucket_anchor": len(rows)})
    return order_results, context_results, bucket_results, context_all, bucket_all


if __name__ == "__main__":
    run_all()
