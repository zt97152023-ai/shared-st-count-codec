"""Copy frozen provenance and user-facing instructions to the chosen D output."""
from pathlib import Path
import shutil
P=Path(__file__).resolve().parent;OUT=Path('D:/HEST1000BenchRun/COUNT-HEST-SHARED-K32-001')
assert OUT.is_dir()
(OUT/'code').mkdir(exist_ok=True)
for f in P.iterdir():
 if f.is_file() and f.suffix in ['.py','.json','.csv','.md']:
  shutil.copyfile(f,OUT/'code'/f.name)
for name in ['README.md','REVIEW_RELEASE.json','REVIEW.md','PROTOCOL.json','RUN_PINS.json']:
 if (P/name).exists():shutil.copyfile(P/name,OUT/name)
print(OUT)
