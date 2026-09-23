from pathlib import Path
import json,hashlib,importlib.metadata as md
R=Path(__file__).resolve().parents[1]
for row in json.loads((R/'SOURCE_MANIFEST.json').read_text(encoding='utf-8')):
    assert hashlib.sha256((R/row['path']).read_bytes()).hexdigest()==row['sha256'],row['path']
env=json.loads((R/'environment/ENVIRONMENT_LOCK.json').read_text(encoding='utf-8'))
for p in env['packages']:
    actual=md.version(p['name']);assert actual==p['version'],(p['name'],actual,p['version'])
print('Original source hashes and exact core installed versions match.')
