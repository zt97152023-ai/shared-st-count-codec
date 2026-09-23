import unittest
from .limits import validate_shape

class LimitsTest(unittest.TestCase):
    def test_boundary(self):
        validate_shape([10_000, 50_000], 1)
        validate_shape([14_332, 32_589], 15_013_701)
        validate_shape([14_110, 32_589], 30_792_580)
        validate_shape([10_000, 50_000], 100_000_000)
        with self.assertRaisesRegex(ValueError, "shape budget"):
            validate_shape([166_667, 3_000], 1)
        with self.assertRaisesRegex(ValueError, "nnz budget"):
            validate_shape([10_000, 50_000], 100_000_001)
    def test_original_type_semantics(self):
        for shape in ((10, 10), [10.0, 10], [10], [10, 10, 10]):
            with self.assertRaisesRegex(ValueError, "shape budget"):
                validate_shape(shape, 1)
        # bool is an int subclass and the production predicate accepts it.
        validate_shape([True, 10], 1)
        for nnz in (1.0, "1"):
            with self.assertRaisesRegex(ValueError, "nnz budget"):
                validate_shape([10, 10], nnz)

if __name__ == '__main__': unittest.main()
