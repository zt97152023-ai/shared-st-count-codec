"""Negative integrity tests against the real public evidence bundle."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile
import csv

from verify_evidence_bridge import verify

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT/'provenance/evidence_20260928'


class EvidenceIntegrityTests(unittest.TestCase):
    def test_e3_label_corrections_preserve_all_numeric_results_and_hashes(self):
        corrections = json.loads((ROOT/'provenance/E3_DESCRIPTION_CORRECTIONS.json').read_text(encoding='utf-8'))
        for correction in corrections:
            if not correction['path'].endswith('.csv'):
                continue
            with (ROOT/correction['historical_path']).open(encoding='utf-8-sig', newline='') as f:
                old = list(csv.DictReader(f))
            with (ROOT/correction['path']).open(encoding='utf-8-sig', newline='') as f:
                new = list(csv.DictReader(f))
            self.assertEqual(len(old), len(new))
            for a, b in zip(old, new):
                a.pop('definition'); definition = b.pop('definition')
                self.assertEqual(a, b)
                if b['arm'] == 'no_sharing':
                    self.assertIn('K32', definition)

    def test_valid_public_bundle(self):
        self.assertEqual(verify(ROOT, BUNDLE)['status'], 'passed')

    def test_changed_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            # The manifest check must reject the changed file before attempting
            # to trust its contents or access other bundle members.
            first = json.loads((BUNDLE/'ARTIFACT_SHA256.json').read_text(encoding='utf-8'))[0]
            (out/'ARTIFACT_SHA256.json').write_text(json.dumps([first]), encoding='utf-8')
            (out/first['path']).write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'artifact hash'):
                verify(ROOT, out)

    def test_receipt_tampering_is_rejected_even_with_new_outer_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            shutil.copyfile(BUNDLE/'RECEIPT_INDEX.json', out/'RECEIPT_INDEX.json')
            with zipfile.ZipFile(BUNDLE/'receipts.zip') as source:
                name = source.namelist()[0]
            with zipfile.ZipFile(out/'receipts.zip', 'w') as target:
                target.writestr(name, b'{"checks":{"all":true}}')
            manifest = [{'path': p.name, 'bytes': p.stat().st_size,
                         'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in out.iterdir()]
            (out/'ARTIFACT_SHA256.json').write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'receipt content hash'):
                verify(ROOT, out)


if __name__ == '__main__':
    unittest.main()
