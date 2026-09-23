"""Deterministically classify stopped HEST-1000 failures without changing evidence."""
from __future__ import annotations
import json, re, sys
from pathlib import Path

def classify(row: dict, root: Path) -> dict:
    text = json.dumps(row, ensure_ascii=False)
    sample, method = row.get("sample_id", ""), row.get("method", "")
    for p in [root / sample / method]:
        if p.exists():
            for f in p.rglob("*.log"):
                try: text += "\n" + f.read_text(encoding="utf-8", errors="replace")
                except OSError: pass
    if row.get("status") == "pending_adapter": category = "pending_adapter"
    elif row.get("status") == "success": category = "success"
    elif re.search(r"access violation|Fatal Python error: Aborted|returncode.*3221225477", text, re.I): category = "shared_numba_runtime_crash" if method == "Shared" else "native_runtime_crash"
    elif "duplicate decoded index" in text: category = "ivcsc_native_duplicate_index"
    elif "Invalid index width" in text: category = "ivcsc_native_index_width"
    elif re.search(r"dict_keyiterator|list_iterator.*not callable|anndata.*zarr|zarr.*import", text, re.I): category = "python_package_compatibility"
    elif "SystemError('error return without exception set')" in text: category = "python_extension_nonzero"
    else: category = "unclassified_nonzero_exit"
    return {"sample_id": sample, "method": method, "status": row.get("status"), "category": category, "error": row.get("error", "")[:500]}

def main():
    if len(sys.argv) != 3: raise SystemExit("usage: classify_failures.py RUNS.jsonl OUTPUT.json")
    runs, out = Path(sys.argv[1]), Path(sys.argv[2]); root = runs.parent
    rows = [json.loads(x) for x in runs.read_text(encoding="utf-8").splitlines() if x.strip()]
    classified = [classify(r, root) for r in rows]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"source": str(runs), "records": len(classified), "rows": classified}, ensure_ascii=False, indent=2), encoding="utf-8")
    from collections import Counter
    print(json.dumps(Counter(x["category"] for x in classified), ensure_ascii=False, sort_keys=True))
if __name__ == "__main__": main()
