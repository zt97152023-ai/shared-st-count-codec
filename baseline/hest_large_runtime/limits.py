"""Capacity-only extension for the two preregistered large HEST matrices."""
MAX_SHARED_SYMBOLS = 500_000_000
MAX_SHARED_NNZ = 100_000_000

def validate_shape(shape, nnz):
    if (not isinstance(shape, list) or len(shape) != 2
            or any(not isinstance(v, int) or v <= 0 or v > 2_000_000 for v in shape)
            or shape[0] * shape[1] > MAX_SHARED_SYMBOLS):
        raise ValueError("shape budget")
    if not isinstance(nnz, int) or not 0 <= nnz <= min(MAX_SHARED_NNZ, shape[0] * shape[1]):
        raise ValueError("nnz budget")
