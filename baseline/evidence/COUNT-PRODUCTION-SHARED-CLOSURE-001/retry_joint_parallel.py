"""Bounded parallel retries for the B16 x support-width joint scan."""
from __future__ import annotations
import csv, json
from concurrent.futures import ThreadPoolExecutor, as_completed
import retry_closure as rc


def main():
    samples = [r["id"] for r in csv.DictReader(rc.MANIFEST.open(encoding="utf-8-sig", newline=""))]
    pending = []
    for sample in samples:
        for width in (4, 8):
            arm = f"B16_M{width}"
            main_folder = rc.HERE / "main/joint" / sample / arm
            try:
                x = rc.load_json(main_folder / "RESULT.json")
                if x.get("status") == "success" and x.get("verify_all") is True:
                    continue
            except Exception:
                pass
            if rc.effective_success(rc.HERE / "retry/joint" / sample / arm):
                continue
            pending.append((sample, arm, main_folder))
    rows = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(rc.retry_one, "joint", sample, arm, folder): (sample, arm)
                   for sample, arm, folder in pending}
        for fut in as_completed(futures):
            rows.append(fut.result())
    out = rc.HERE / "RETRY_JOINT_PARALLEL_COUNTS.json"
    out.write_text(json.dumps({"pending": len(pending), "rows": len(rows),
                               "success": sum(x.get("status") == "success" for x in rows),
                               "failed": sum(x.get("status") != "success" for x in rows)}, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
