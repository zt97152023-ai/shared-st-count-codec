"""Correct published E3 descriptions, preserving the original bytes and pins.

Historical generators remain unchanged. Apply this publication correction
after generating their reports; numeric results and archive hashes are untouched.
"""
from pathlib import Path
import hashlib
import json


def main():
    root = Path(__file__).resolve().parents[1]
    manifest_path = root/'SOURCE_MANIFEST.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    changes = []
    for family, names in [('COUNT-E3-MODULE-CONTRIBUTION-001', ['README.md', 'RESULT.md', 'E3_DIRECT_ABLATION.csv']),
                          ('COUNT-E3-MODULE-CONTRIBUTION-002-50', ['RESULT.md', 'E3_DIRECT_ABLATION_50.csv'])]:
        for name in names:
            relative = f'baseline/evidence/{family}/{name}'
            current = root/relative
            archived = root/f'docs/historical/{family}_{name}'
            if not archived.exists():
                archived.write_bytes(current.read_bytes())
            old = archived.read_bytes()
            new = old.replace(b'fixed eight tail classes', b'fixed K32 tail groups')
            if name == 'README.md':
                old_definition = b'and `no_sharing` as per-gene parameter fitting/serialization.'
                new_definition = b'and the implemented `no_sharing` as per-gene singleton probability exceptions; shared tail/conditional/support parameters remain.'
                if old_definition not in old:
                    raise ValueError('Historical definition was not found')
                new = old.replace(old_definition, new_definition)
                note = (b'Publication correction (2026-09-28): this is a historical phase-0 inventory. '
                        b'The retained direct pilot and expansion use B8/K32; see '
                        b'[the evidence contract](../../../provenance/REPRODUCIBILITY_CONTRACT.md) '
                        b'for the implemented singleton-only intervention.\n\n')
                first, rest = new.split(b'\n', 1)
                new = first+b'\n\n'+note+rest
            elif new == old:
                raise ValueError('Expected historical eight-class phrase was not found: '+relative)
            current.write_bytes(new)
            original_rel = archived.relative_to(root).as_posix()
            entry = next((r for r in manifest if r['path'] in (relative, original_rel)), None)
            if entry:
                if hashlib.sha256(old).hexdigest() != entry['sha256']:
                    raise ValueError('Historical document hash mismatch: '+relative)
                entry['path'] = original_rel
            changes.append({'path': relative, 'historical_path': original_rel,
                            'historical_sha256': hashlib.sha256(old).hexdigest(),
                            'published_sha256': hashlib.sha256(new).hexdigest(),
                            'numeric_results_changed': False})
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (root/'provenance/E3_DESCRIPTION_CORRECTIONS.json').write_text(json.dumps(changes, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Corrected five E3 descriptions; original document/table bytes preserved.')


if __name__ == '__main__':
    main()
