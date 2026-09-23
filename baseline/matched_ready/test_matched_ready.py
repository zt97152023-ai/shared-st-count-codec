from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

import h5py
import numpy as np

from baseline.matched_ready.adapter import read_h5ad
from baseline.matched_ready.cli import encode, evaluate
from baseline.matched_ready.archive import read


def make_h5ad(path: Path, changed=False):
    x = np.array([[0, 0, 0, 0], [2, 0, 1, 0], [0, 3, 0, 0], [0, 0, 0, 4],
                  [1, 0, 0, 0], [0, 0, 0, 0], [0, 5, 0, 1], [0, 0, 2, 0]], dtype=np.uint32)
    if changed: x[1, 0] = 3
    with h5py.File(path, "w") as h:
        h.create_dataset("X", data=x)
        obs = h.create_group("obs"); obs.attrs["_index"] = "_index"; obs.create_dataset("_index", data=np.asarray([f"s{i}" for i in range(len(x))], dtype="S"))
        var = h.create_group("var"); var.attrs["_index"] = "_index"; var.create_dataset("_index", data=np.asarray([f"g{i}" for i in range(x.shape[1])], dtype="S"))
        h.create_group("obsm").create_dataset("spatial", data=np.arange(len(x) * 2, dtype=np.float64).reshape(len(x), 2))


class MatchedReadyTests(unittest.TestCase):
    def test_adapter_preserves_duplicate_ids_and_zero_column(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "raw.h5ad"; make_h5ad(p)
            with h5py.File(p, "r+") as h:
                h["obs/_index"][1] = b"s0"
                h["var/_index"][2] = b"g1"
                h["X"][:, 3] = 0
            got = read_h5ad(p)
            self.assertEqual(got.metadata["spot_ids"][0], got.metadata["spot_ids"][1])
            self.assertEqual(got.metadata["gene_ids"][1], got.metadata["gene_ids"][2])
            self.assertEqual(got.matrix.getcol(3).nnz, 0)

    def test_uint32_max_and_overflow_boundaries(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); good = root / "max.h5ad"; bad = root / "overflow.h5ad"
            for p, value in ((good, 0xFFFFFFFF), (bad, 0x100000000)):
                with h5py.File(p, "w") as h:
                    h.create_dataset("X", data=np.array([[value]], dtype=np.uint64))
                    o = h.create_group("obs"); o.attrs["_index"] = "_index"; o.create_dataset("_index", data=np.asarray(["s0"], dtype="S"))
                    v = h.create_group("var"); v.attrs["_index"] = "_index"; v.create_dataset("_index", data=np.asarray(["g0"], dtype="S"))
                    h.create_group("obsm").create_dataset("spatial", data=np.zeros((1, 2)))
            self.assertEqual(int(read_h5ad(good).matrix.data[0]), 0xFFFFFFFF)
            with self.assertRaises(ValueError): read_h5ad(bad)

    def test_s0_and_shared_only_fresh_exact(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = root / "source.h5ad"
            make_h5ad(source)
            self.assertEqual(read_h5ad(source).matrix.shape, (8, 4))
            for mode in ("s0", "shared-only"):
                package = root / (mode + ".cnt"); report = root / (mode + ".json")
                result = encode(source, package, mode)
                self.assertEqual(result["mode"] if mode == "shared-only" else "s0", mode)
                evaluated = evaluate(package, source, report, mode)
                self.assertTrue(evaluated["exact"]["all"])
                self.assertTrue(evaluated["archive_only_decoder"])
                self.assertEqual(evaluated["fees"]["total_package_bytes"], package.stat().st_size)

    def test_bad_reference_corruption_and_output_exists(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = root / "source.h5ad"; other = root / "other.h5ad"; package = root / "shared.cnt"
            make_h5ad(source); make_h5ad(other, changed=True); encode(source, package, "shared-only")
            with self.assertRaises(ValueError): evaluate(package, other, root / "wrong.json", "shared-only")
            tampered = root / "tampered.cnt"
            with zipfile.ZipFile(package) as zin, zipfile.ZipFile(tampered, "w", compression=zipfile.ZIP_STORED) as zout:
                for info in zin.infolist():
                    data = zin.read(info.filename)
                    if info.filename == "support.rans": data = bytes([data[0] ^ 1]) + data[1:]
                    zout.writestr(info.filename, data)
            with self.assertRaises(ValueError): read(tampered)
            existing = root / "existing.json"; existing.write_text("keep", encoding="utf8")
            with self.assertRaises(FileExistsError): evaluate(package, source, existing, "shared-only")


if __name__ == "__main__": unittest.main()
