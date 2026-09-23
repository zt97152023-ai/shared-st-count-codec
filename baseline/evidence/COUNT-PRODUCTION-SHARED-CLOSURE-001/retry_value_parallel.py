"""Bounded parallel value-context retries; each arm uses isolated processes/caches."""
from __future__ import annotations
import csv, json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import retry_closure as rc


def main():
    samples = [r["id"] for r in csv.DictReader(rc.MANIFEST.open(encoding="utf-8-sig", newline=""))]
    pending = []
    for sample in samples:
        for mv in (0, 2, 4, 6, 8, 12):
            arm = f"MV{mv}"
            main_folder = rc.HERE / "main" / "value" / sample / arm
            main_result = main_folder / "RESULT.json"
            try:
                main_saved = rc.load_json(main_result)
                if main_saved.get("status") == "success" and main_saved.get("verify_all") is True:
                    continue
            except Exception:
                pass
            if rc.effective_success(rc.HERE / "retry" / "value" / sample / arm):
                continue
            pending.append((sample, arm, main_folder))
    rows = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(rc.retry_one, "value", sample, arm, folder): (sample, arm)
                   for sample, arm, folder in pending}
        for fut in as_completed(futures):
            rows.append(fut.result())
    out = rc.HERE / "RETRY_VALUE_PARALLEL_COUNTS.json"
    out.write_text(json.dumps({"pending": len(pending), "rows": len(rows),
                               "success": sum(x.get("status") == "success" for x in rows),
                               "failed": sum(x.get("status") != "success" for x in rows)}, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
