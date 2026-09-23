"""Aggregate effective closure evidence and perform member-level audits."""
from __future__ import annotations
import csv, hashlib, json, statistics, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT / "baseline/evidence/COUNT-PRODUCTION-SHARED-ABLATIONS-50-001"
MANIFEST = ROOT / "baseline/evidence/COUNT-SUPPORT-PREDECESSOR-50-001/DATA_SPLIT.csv"


def read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def good(x):
    return isinstance(x, dict) and x.get("status") == "success" and x.get("verify_all") is True


def effective(stage, sample, arm):
    locations = [HERE / "main" / stage / sample / arm]
    if stage == "b32_width":
        locations = [HERE / "main/b32_width" / sample / arm]
    locations += [HERE / "retry" / stage / sample / arm]
    for folder in locations:
        for name in ("SUCCESS.json", "RESULT.json", "RESULT_REBUILT.json"):
            x = read(folder / name)
            if good(x):
                return x, folder
    return None, None


def rows_for(stage, arms, samples):
    rows = []
    for sample in samples:
        for arm in arms:
            x, folder = effective(stage, sample, arm)
            if x:
                y = dict(x); y["effective_folder"] = str(folder); rows.append(y)
    return rows


def summary(rows, arms, expected=50):
    out = []
    for arm in arms:
        rr = [x for x in rows if x["arm"] == arm]
        def sm(k): return sum(int(x.get(k, 0) or 0) for x in rr)
        vals = [int(x["total_archive_bytes"]) for x in rr]
        out.append({"arm": arm, "n_success": len(rr), "n_expected": expected,
                    "coverage_complete": len(rr) == expected,
                    "pooled_total_bytes": sm("total_archive_bytes"),
                    "mean_total_bytes": statistics.mean(vals) if vals else None,
                    "median_total_bytes": statistics.median(vals) if vals else None,
                    **{k: sm(k) for k in ("support_stream", "value_stream", "support_model",
                                          "value_model_and_group_map", "graph_index",
                                          "identity_coordinates_metadata", "mapping", "manifest", "zip_framing")}})
    return out


def write_csv(path, rows):
    if not rows:
        return
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=fields); w.writeheader(); w.writerows(rows)


def archive_path(stage, sample, arm, folder):
    for name in ("archive.cnt", "archive_rebuilt.cnt"):
        p = Path(folder) / name
        if p.is_file(): return p
    # Retry folders intentionally reuse the immutable main archive instead of copying it.
    for root in (HERE / "main" / stage / sample / arm,
                 HERE / "main" / "value" / sample / arm):
        for name in ("archive.cnt", "archive_rebuilt.cnt"):
            p = root / name
            if p.is_file(): return p
    return None


def member_hashes(path):
    with zipfile.ZipFile(path) as z:
        return {n: hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()}


def member_audit(samples):
    audits = []
    contexts = [("B16_base", "value", OLD / "main_v3/bucket", "B16"),
                ("B32_base", "b32_value", HERE / "main/bucket", "B32")]
    for context, stage, base_root, bucket in contexts:
      for sample in samples:
        base = base_root / sample / f"{bucket}/archive.cnt"
        if not base.is_file():
            continue
        bh = member_hashes(base)
        for arm in ("MV0", "MV6"):
            x, folder = effective(stage, sample, arm)
            if not x: continue
            cand = archive_path(stage, sample, arm, folder)
            if not cand: continue
            ch = member_hashes(cand)
            common = sorted(set(bh) & set(ch))
            equal = [n for n in common if bh[n] == ch[n]]
            changed = [n for n in common if bh[n] != ch[n]]
            audits.append({"context": context, "sample_id": sample, "arm": arm, "base_member_count": len(bh),
                           "candidate_member_count": len(ch), "common_member_count": len(common),
                           "equal_member_count": len(equal), "changed_member_count": len(changed),
                           "added_members": sorted(set(ch) - set(bh)),
                           "removed_members": sorted(set(bh) - set(ch)),
                           "changed_members": changed,
                           "all_members_equal": bh == ch})
    return audits


def main():
    samples = [r["id"] for r in csv.DictReader(MANIFEST.open(encoding="utf-8-sig", newline=""))]
    b32 = rows_for("bucket", ["B32"], samples)
    b32w = rows_for("b32_width", ["B32_M4", "B32_M8"], samples)
    joint = rows_for("joint", ["B16_M4", "B16_M8"], samples)
    value = rows_for("value", [f"MV{x}" for x in (0, 2, 4, 6, 8, 12)], samples)
    b32_value = rows_for("b32_value", [f"MV{x}" for x in (0, 2, 4, 6, 8, 12)], samples)
    write_csv(HERE / "B32_SUMMARY.csv", summary(b32, ["B32"]))
    write_csv(HERE / "B32_SUPPORT_WIDTH_SUMMARY.csv", summary(b32w, ["B32_M4", "B32_M8"]))
    write_csv(HERE / "JOINT_SUPPORT_SUMMARY.csv", summary(joint, ["B16_M4", "B16_M8"]))
    write_csv(HERE / "VALUE_CONTEXT_SUMMARY.csv", summary(value, [f"MV{x}" for x in (0, 2, 4, 6, 8, 12)]))
    write_csv(HERE / "B32_VALUE_SUMMARY.csv", summary(b32_value, [f"MV{x}" for x in (0, 2, 4, 6, 8, 12)]))
    audit = member_audit(samples)
    (HERE / "VALUE_MEMBER_AUDIT.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    (HERE / "EFFECTIVE_COVERAGE.json").write_text(json.dumps({
        "bucket_B32": len(b32), "b32_width": len(b32w), "joint_B16_M4_M8": len(joint),
        "value_context": len(value), "b32_value_context": len(b32_value), "expected": {"bucket_B32": 50, "b32_width": 100,
        "joint_B16_M4_M8": 100, "value_context": 300}}, indent=2), encoding="utf-8")
    print(json.dumps({"b32": len(b32), "b32_width": len(b32w), "joint": len(joint), "value": len(value), "b32_value": len(b32_value), "member_audit": len(audit)}, indent=2))


if __name__ == "__main__":
    main()
