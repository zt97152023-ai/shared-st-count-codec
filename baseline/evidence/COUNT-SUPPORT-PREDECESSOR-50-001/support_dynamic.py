"""Dynamic-width support context with the frozen Production Shared odds model."""
from __future__ import annotations

import math
import numpy as np
from numba import njit

PREC = 12
TOTAL = 1 << PREC
LOWER = 1 << 23
EDGES = np.asarray([1, 4, 16, 64, 256, 1024, 2048, 3072, 4096])
RMIN = int(math.floor(math.exp(-8) * 65536 + 0.5))
RMAX = int(math.floor(math.exp(8) * 65536 + 0.5))


@njit(cache=True)
def bit(mask, row, gene):
    return (mask[row, gene >> 3] >> (gene & 7)) & 1


@njit(cache=True)
def packed_support(ptr, idx, nrows, genes):
    mask = np.zeros((nrows, (genes + 7) // 8), np.uint8)
    for row in range(nrows):
        for pos in range(ptr[row], ptr[row + 1]):
            gene = idx[pos]
            mask[row, gene >> 3] |= np.uint8(1 << (gene & 7))
    return mask


@njit(cache=True)
def indices_from_support(mask, genes, nnz):
    ptr = np.empty(len(mask) + 1, np.int64)
    idx = np.empty(nnz, np.int64)
    ptr[0] = 0
    pos = 0
    for row in range(len(mask)):
        for gene in range(genes):
            if bit(mask, row, gene):
                if pos >= nnz:
                    raise ValueError("support exceeds nnz")
                idx[pos] = gene
                pos += 1
        ptr[row + 1] = pos
    if pos != nnz:
        raise ValueError("support nnz mismatch")
    return ptr, idx


@njit(cache=True)
def context(mask, graph, row, gene):
    total = 0
    for col in range(graph.shape[1]):
        pred = graph[row, col]
        if pred >= 0:
            total += bit(mask, pred, gene)
    return total


@njit(cache=True)
def event_counts(mask, graph, q0, group, width):
    seen = np.zeros((8, width + 1, 4096), np.int64)
    ones = np.zeros_like(seen)
    for row in range(width, len(mask)):
        for gene in range(len(q0)):
            ctx = context(mask, graph, row, gene)
            bucket = group[gene]
            q = q0[gene]
            seen[bucket, ctx, q] += 1
            ones[bucket, ctx, q] += bit(mask, row, gene)
    return seen, ones


def buckets(q0):
    q0 = np.asarray(q0)
    if q0.ndim != 1 or np.any(q0 < 1) or np.any(q0 > 4095):
        raise ValueError("base Q12 bounds")
    return (np.searchsorted(EDGES, q0, side="right") - 1).astype(np.int64)


def fit(mask, graph, q0, width):
    """Fit 8 x (M+1) paid odds multipliers; M=0 is the unconditioned base."""
    if graph.shape != (len(mask), width):
        raise ValueError("graph shape")
    group = buckets(q0)
    multipliers = np.full((8, width + 1), 65536, dtype="<u4")
    if width == 0:
        return multipliers, cdf(q0, multipliers), {
            "parameter_count": 8,
            "multiplier_bytes": int(multipliers.nbytes),
            "occupied_bucket_contexts": 0,
            "fitted_events": 0,
            "beta_min": 0.0,
            "beta_max": 0.0,
        }
    seen, ones = event_counts(mask, graph, q0, group, width)
    betas = np.zeros((8, width + 1), np.float64)
    for bucket in range(8):
        for ctx in range(width + 1):
            occupied = np.flatnonzero(seen[bucket, ctx])
            if not len(occupied):
                continue
            n = seen[bucket, ctx, occupied].astype(np.float64)
            y = ones[bucket, ctx, occupied].astype(np.float64)
            offset = np.log(occupied / (4096.0 - occupied))

            def derivative(beta):
                return float(np.sum(n / (1 + np.exp(-(offset + beta))) - y) + beta)

            lo, hi = -8.0, 8.0
            if derivative(lo) >= 0:
                beta = lo
            elif derivative(hi) <= 0:
                beta = hi
            else:
                for _ in range(48):
                    mid = (lo + hi) / 2
                    if derivative(mid) > 0:
                        hi = mid
                    else:
                        lo = mid
                beta = (lo + hi) / 2
            betas[bucket, ctx] = beta
            multipliers[bucket, ctx] = int(math.floor(math.exp(beta) * 65536 + 0.5))
    return multipliers, cdf(q0, multipliers), {
        "parameter_count": int(multipliers.size),
        "multiplier_bytes": int(multipliers.nbytes),
        "occupied_bucket_contexts": int(np.sum(seen.sum(axis=2) > 0)),
        "fitted_events": int(seen.sum()),
        "beta_min": float(betas.min()),
        "beta_max": float(betas.max()),
    }


def cdf(q0, multipliers):
    width = multipliers.shape[1] - 1
    if multipliers.shape[0] != 8 or multipliers.dtype.kind != "u":
        raise ValueError("multiplier shape/type")
    if np.any(multipliers < RMIN) or np.any(multipliers > RMAX):
        raise ValueError("multiplier bounds")
    group = buckets(q0)
    a = np.asarray(q0, dtype=np.uint64)[:, None]
    odds = multipliers[group].astype(np.uint64)
    numerator = a * odds
    denominator = numerator + (4096 - a) * np.uint64(65536)
    conditional = np.clip((np.uint64(4096) * numerator + denominator // 2) // denominator, 1, 4095)
    if conditional.shape != (len(q0), width + 1):
        raise ValueError("conditional shape")
    return conditional.astype("<u2")


@njit(cache=True)
def encode(mask, graph, conditional, q0, width):
    genes = len(q0)
    out = np.empty(mask.shape[0] * genes * 2 + 8, np.uint8)
    used = 0
    state = np.uint64(LOWER)
    nll = 0.0
    for row in range(len(mask) - 1, -1, -1):
        for gene in range(genes - 1, -1, -1):
            p1 = int(q0[gene] if row < width else conditional[gene, context(mask, graph, row, gene)])
            p0 = TOTAL - p1
            one = bit(mask, row, gene)
            freq = np.uint64(p1 if one else p0)
            start = np.uint64(p0 if one else 0)
            nll += PREC - math.log2(float(freq))
            threshold = np.uint64((LOWER >> PREC) << 8) * freq
            while state >= threshold:
                out[used] = np.uint8(state & np.uint64(255))
                used += 1
                state >>= np.uint64(8)
            state = ((state // freq) << np.uint64(PREC)) + (state % freq) + start
    result = np.empty(used + 4, np.uint8)
    for k in range(4):
        result[k] = np.uint8((state >> np.uint64(k * 8)) & np.uint64(255))
    for pos in range(used):
        result[4 + pos] = out[used - 1 - pos]
    return result, nll


@njit(cache=True)
def decode(blob, graph, conditional, q0, nrows, genes, width):
    if len(blob) < 4:
        raise ValueError("truncated rANS")
    state = np.uint64(0)
    for k in range(4):
        state |= np.uint64(blob[k]) << np.uint64(k * 8)
    if state < LOWER:
        raise ValueError("invalid initial rANS state")
    mask = np.zeros((nrows, (genes + 7) // 8), np.uint8)
    pos = 4
    for row in range(nrows):
        for gene in range(genes):
            p1 = int(q0[gene] if row < width else conditional[gene, context(mask, graph, row, gene)])
            p0 = TOTAL - p1
            rem = int(state & np.uint64(TOTAL - 1))
            one = rem >= p0
            freq = np.uint64(p1 if one else p0)
            start = np.uint64(p0 if one else 0)
            state = freq * (state >> np.uint64(PREC)) + np.uint64(rem) - start
            if one:
                mask[row, gene >> 3] |= np.uint8(1 << (gene & 7))
            while state < LOWER:
                if pos >= len(blob):
                    raise ValueError("truncated payload")
                state = (state << np.uint64(8)) | np.uint64(blob[pos])
                pos += 1
    if pos != len(blob) or state != LOWER:
        raise ValueError("rANS termination mismatch")
    return mask
