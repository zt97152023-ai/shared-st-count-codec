from __future__ import annotations

import json
import bz2
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

import h5py
import numpy as np

from baseline.execution_ready.adapter import read_h5ad
from baseline.execution_ready.archive import read
from baseline.execution_ready.cli import evaluate
from baseline.execution_ready.gate import check_gate
from baseline.execution_ready.prepare import prepare
from baseline.execution_ready.runtime import load_runtime


def _labels(group, values):
    group.attrs["_index"] = "_index"
    group.create_dataset("_index", data=np.asarray(values, dtype="S"))


def _make_h5ad(path: Path, encoding="dense", bad=False, missing=False, zero_row=None, zero_column=False):
    dense = np.array([[0, 2, 0], [3, 0, 1], [0, 0, 4]], dtype=np.uint32)
    if zero_row is not None:
        dense[int(zero_row)] = 0
    if zero_column:
        dense[:, 2] = 0
    with h5py.File(path, "w") as h:
        if encoding == "dense":
            h.create_dataset("X", data=(-dense.astype(np.int64) if bad else dense))
        else:
            x = h.create_group("X")
            x.attrs["encoding-type"] = encoding + "_matrix"
            x.attrs["shape"] = dense.shape
            if encoding == "csr":
                # Duplicate column 1 and a stored zero are canonicalized by io047.
                x.create_dataset("data", data=np.array([2, 0, 3, 1, 1, 3], dtype=np.uint32))
                x.create_dataset("indices", data=np.array([1, 1, 0, 2, 2, 2], dtype=np.int32))
                x.create_dataset("indptr", data=np.array([0, 2, 4, 6], dtype=np.int32))
            else:
                x.create_dataset("data", data=np.array([3, 2, 1, 4], dtype=np.uint32))
                x.create_dataset("indices", data=np.array([1, 0, 1, 2], dtype=np.int32))
                x.create_dataset("indptr", data=np.array([0, 1, 2, 4], dtype=np.int32))
        if not missing:
            _labels(h.create_group("obs"), ["s0", "s1", "s2"])
            _labels(h.create_group("var"), ["g0", "g1", "g2"])
            h.create_group("obsm").create_dataset("spatial", data=np.array([[0., 0.], [1., 0.], [0., 1.]], dtype=np.float64))


class AdapterTests(unittest.TestCase):
    def test_dense_csr_csc_and_canonicalization(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _make_h5ad(root / "dense.h5ad")
            _make_h5ad(root / "csr.h5ad", "csr")
            _make_h5ad(root / "csc.h5ad", "csc")
            dense = read_h5ad(root / "dense.h5ad")
            csr = read_h5ad(root / "csr.h5ad")
            csc = read_h5ad(root / "csc.h5ad")
            np.testing.assert_array_equal(csr.matrix.toarray(), dense.matrix.toarray())
            np.testing.assert_array_equal(csc.matrix.toarray(), dense.matrix.toarray())
            self.assertTrue(csr.matrix.has_canonical_format)

    def test_zero_rows_are_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "zero.h5ad"
            _make_h5ad(p, zero_row=True)
            got = read_h5ad(p).matrix
            self.assertEqual(got.getrow(1).nnz, 0)
            q = Path(td) / "zero-column.h5ad"
            _make_h5ad(q, zero_column=True)
            self.assertEqual(read_h5ad(q).matrix.getcol(2).nnz, 0)

    def test_bad_values_and_missing_metadata_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _make_h5ad(root / "bad.h5ad", bad=True)
            _make_h5ad(root / "missing.h5ad", missing=True)
            with self.assertRaises(ValueError): read_h5ad(root / "bad.h5ad")
            with self.assertRaises(ValueError): read_h5ad(root / "missing.h5ad")
            nan = root / "nan.h5ad"
            with h5py.File(nan, "w") as h:
                h.create_dataset("X", data=np.array([[np.nan]], dtype=np.float32))
                _labels(h.create_group("obs"), ["s0"]); _labels(h.create_group("var"), ["g0"])
                h.create_group("obsm").create_dataset("spatial", data=np.array([[0., 0.]]))
            with self.assertRaises(ValueError): read_h5ad(nan)

    def test_uint32_boundary_noninteger_nan_duplicate_id_and_coordinate_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = root / "boundary.h5ad"
            with h5py.File(p, "w") as h:
                h.create_dataset("X", data=np.array([[0xFFFFFFFF]], dtype=np.uint64))
                _labels(h.create_group("obs"), ["s0"]); _labels(h.create_group("var"), ["g0"])
                h.create_group("obsm").create_dataset("spatial", data=np.array([[-0.0, 1.0]], dtype=">f8"))
            got = read_h5ad(p)
            self.assertEqual(int(got.matrix.data[0]), 0xFFFFFFFF)
            self.assertEqual(got.metadata["coordinates_dtype"], ">f8")
            package = root / "boundary.cnt"
            prepare(got, package)
            evaluate(package, p, root / "boundary-report.json")
            bad = root / "badfloat.h5ad"
            with h5py.File(bad, "w") as h:
                h.create_dataset("X", data=np.array([[1.5]], dtype=np.float32))
                _labels(h.create_group("obs"), ["s0"]); _labels(h.create_group("var"), ["g0"])
                h.create_group("obsm").create_dataset("spatial", data=np.array([[0., 0.]]))
            with self.assertRaises(ValueError): read_h5ad(bad)
            dup = root / "dup.h5ad"; _make_h5ad(dup)
            with h5py.File(dup, "r+") as h:
                h["obs/_index"][1] = b"s0"
            self.assertEqual(read_h5ad(dup).metadata["spot_ids"], ["s0", "s0", "s2"])
            overflow = root / "overflow.h5ad"
            with h5py.File(overflow, "w") as h:
                h.create_dataset("X", data=np.array([[0x100000000]], dtype=np.uint64))
                _labels(h.create_group("obs"), ["s0"]); _labels(h.create_group("var"), ["g0"])
                h.create_group("obsm").create_dataset("spatial", data=np.array([[0., 0.]]))
            with self.assertRaises(ValueError): read_h5ad(overflow)


class ValidatorTests(unittest.TestCase):
    def test_synthetic_success_wrong_reference_and_tampered_valid_package(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = root / "source.h5ad"; other = root / "other.h5ad"
            _make_h5ad(source, zero_row=0, zero_column=True); _make_h5ad(other)
            with h5py.File(other, "r+") as h:
                h["X"][0, 1] = 1
            package = root / "package.cnt"
            prepare(read_h5ad(source), package)
            evaluate(package, source, root / "ok.json")
            with self.assertRaises(ValueError): evaluate(package, other, root / "wrong.json")
            tampered = root / "tampered.cnt"
            with zipfile.ZipFile(package) as zin, zipfile.ZipFile(tampered, "w", compression=zipfile.ZIP_STORED) as zout:
                for info in zin.infolist():
                    data = zin.read(info.filename)
                    if info.filename == "support.rans":
                        data = bytes([data[0] ^ 1]) + data[1:]
                    zi = zipfile.ZipInfo(info.filename, (1980, 1, 1, 0, 0, 0)); zi.external_attr = 0o100644 << 16
                    zout.writestr(zi, data)
            with self.assertRaises((ValueError, RuntimeError)): evaluate(tampered, source, root / "tampered.json")

    def test_valid_mode0_qshare_blob_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = root / "source.h5ad"; package = root / "package.cnt"
            _make_h5ad(source); prepare(read_h5ad(source), package)
            mode0 = root / "mode0.cnt"
            with zipfile.ZipFile(package) as zin:
                man = json.loads(zin.read("manifest.json"))
                entries = {name: zin.read(name) for name in zin.namelist() if name != "manifest.json"}
            raw = bz2.decompress(entries["value_q1.bz2"])
            # Preserve the QSH1 shared header but emit a valid mode-0 stream;
            # update its member hash so archive integrity passes first.
            _, _, _, _, qshare, _ = load_runtime()
            header = raw[:qshare.HEADER.size]
            entries["value_q1.bz2"] = bz2.compress(header[:4] + b"\0" + header[5:qshare.HEADER.size], 9)
            man["files"]["value_q1.bz2"] = {"bytes": len(entries["value_q1.bz2"]), "sha256": hashlib.sha256(entries["value_q1.bz2"]).hexdigest()}
            manifest = (json.dumps(man, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
            with zipfile.ZipFile(mode0, "w", compression=zipfile.ZIP_STORED) as zout:
                for name, data in sorted({**entries, "manifest.json": manifest}.items()):
                    zi = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)); zi.external_attr = 0o100644 << 16
                    zout.writestr(zi, data)
            with self.assertRaises((ValueError, RuntimeError)): evaluate(mode0, source, root / "mode0.json")

    def test_empty_column_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "empty-column.h5ad"
            with h5py.File(p, "w") as h:
                h.create_dataset("X", shape=(2, 0), dtype=np.uint32)
                _labels(h.create_group("obs"), ["s0", "s1"]); _labels(h.create_group("var"), [])
                h.create_group("obsm").create_dataset("spatial", data=np.zeros((2, 2)))
            with self.assertRaises(ValueError): read_h5ad(p)

    def test_tampered_archive_and_wrong_reference_fail(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); p = root / "tampered.cnt"
            man = {"schema": "qpatch-count-v1", "method": "Qpatch12", "precision": 12,
                   "q1_layout": "QSH1-mode1-12bit-exceptions-bz2-v1", "files": {"bad": {"bytes": 1, "sha256": "x"}}}
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("manifest.json", json.dumps(man)); z.writestr("bad", b"x")
            with self.assertRaises(ValueError): read(p)
            with self.assertRaises(ValueError): evaluate(p, root / "wrong.h5ad", root / "report.json")

    def test_output_exists_and_mode(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); out = root / "report.json"; out.write_text("keep", encoding="utf8")
            with self.assertRaises(FileExistsError): evaluate(root / "missing.cnt", root / "missing.h5ad", out)


class GateTests(unittest.TestCase):
    def test_data_pending_blocks_validation_flag(self):
        result = check_gate({k: {"status": "passed"} for k in ("code", "environment", "preregistration")} | {"data": {"status": "pending", "missing_reason": "P4 data evidence pending"}})
        self.assertFalse(result["validation_flag_allowed"])
        self.assertEqual(result["status"], "pending")


if __name__ == "__main__":
    unittest.main()
