from __future__ import annotations

import unittest
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import support_dynamic as model


class SupportDynamicTests(unittest.TestCase):
    def case(self, width):
        dense = np.asarray([[0, 1, 0, 1], [1, 1, 0, 0], [1, 0, 1, 0], [0, 0, 1, 1], [1, 0, 0, 1]], np.uint8)
        nrows, genes = dense.shape
        mask = np.zeros((nrows, 1), np.uint8)
        for row in range(nrows):
            for gene in range(genes):
                mask[row, 0] |= np.uint8(int(dense[row, gene]) << gene)
        graph = np.full((nrows, width), -1, np.int32)
        for row in range(nrows):
            values = np.arange(max(0, row - width), row, dtype=np.int32)
            graph[row, : len(values)] = values
        q0 = np.asarray([2048, 2300, 1700, 2200], "<u2")
        odds, conditional, _ = model.fit(mask, graph, q0, width)
        blob, _ = model.encode(mask, graph, conditional, q0, width)
        recovered = model.decode(blob, graph, conditional, q0, nrows, genes, width)
        self.assertTrue(np.array_equal(mask, recovered))
        self.assertEqual(odds.shape, (8, width + 1))

    def test_widths(self):
        for width in [0, 1, 2, 4, 6, 8, 12, 16]:
            with self.subTest(width=width):
                self.case(width)


if __name__ == "__main__":
    unittest.main()
