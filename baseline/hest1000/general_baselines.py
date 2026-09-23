"""Frozen general comparators; archive-only decoding, no training or cohort access.

CSR_BZIP2_9 retains the historical F047 CSR layout. Pcodec retains the
historical uint32 row-length/index-gap/value streams (1.0.3, level 8).
Only ZIP/manifest schema and exact metadata preservation are new plumbing.
"""
import argparse
import bz2
import hashlib
import importlib.metadata
import json
from pathlib import Path
import struct
import zipfile

import numpy as np
from scipy import sparse

METHODS = ('CSR_BZIP2_9', 'Pcodec')
SCHEMA = 'hest1000-general-v1'
MAX_BYTES = 8 * 2**30
MAX_U32 = 2**32 - 1


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def jbytes(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf8')


def csr_hash(x):
    h = hashlib.sha256()
    for a in (x.shape, x.indptr, x.indices, x.data):
        h.update(np.asarray(a, dtype='<u8').tobytes())
    return h.hexdigest()


def validate(x):
    if not sparse.isspmatrix_csr(x) or x.dtype != np.dtype('int64'):
        raise ValueError('requires int64 CSR')
    if any(d < 0 or d > MAX_U32 for d in x.shape):
        raise ValueError('shape outside uint32 domain')
    if x.nnz > MAX_U32 or not x.has_canonical_format:
        raise ValueError('requires bounded canonical CSR')
    x.check_format(full_check=True)
    if np.any(x.data <= 0) or np.any(x.data > MAX_U32):
        raise ValueError('stored values must be positive uint32 counts')
    return x


def validate_metadata(raw, shape):
    meta = json.loads(raw)
    if not isinstance(meta, dict):
        raise ValueError('metadata must be an object')
    for key, length in [('spot_ids', shape[0]), ('gene_ids', shape[1])]:
        if not isinstance(meta.get(key), list) or len(meta[key]) != length:
            raise ValueError('metadata axis length mismatch')
    return meta


def frame(parts):
    out = bytearray(b'F047' + struct.pack('<I', len(parts)))
    for name, raw in sorted(parts.items()):
        name = name.encode('utf8')
        out.extend(struct.pack('<IQ', len(name), len(raw)))
        out.extend(name); out.extend(raw)
    return bytes(out)


def unframe(raw):
    if len(raw) < 8 or raw[:4] != b'F047':
        raise ValueError('invalid frame')
    count = struct.unpack_from('<I', raw, 4)[0]
    if count != 4:
        raise ValueError('invalid CSR frame member count')
    pos, parts = 8, {}
    for _ in range(count):
        if pos + 12 > len(raw):
            raise ValueError('truncated frame header')
        namelen, size = struct.unpack_from('<IQ', raw, pos); pos += 12
        if pos + namelen + size > len(raw) or namelen > 64:
            raise ValueError('truncated/invalid frame member')
        name = raw[pos:pos+namelen].decode('utf8'); pos += namelen
        if name in parts:
            raise ValueError('duplicate frame member')
        parts[name] = raw[pos:pos+size]; pos += size
    if pos != len(raw):
        raise ValueError('trailing frame bytes')
    return parts


def pcodec_runtime():
    if importlib.metadata.version('pcodec') != '1.0.3':
        raise RuntimeError('Pcodec requires frozen version 1.0.3')
    from pcodec import standalone, ChunkConfig
    return standalone, ChunkConfig


def pcompress(a):
    standalone, config = pcodec_runtime()
    return bytes(standalone.simple_compress(np.ascontiguousarray(a, dtype='<u4'),
                                         config(compression_level=8)))


def pdecompress(raw, length):
    standalone, _ = pcodec_runtime()
    a = standalone.simple_decompress(raw)
    if a is None:
        if length == 0 and raw == pcompress(np.array([], dtype='<u4')):
            return np.array([], dtype='<u4')
        raise ValueError('unexpected empty Pcodec output')
    a = np.asarray(a)
    if a.ndim != 1 or a.dtype != np.dtype('uint32') or len(a) != length:
        raise ValueError('Pcodec dtype/length mismatch')
    return a


def bounded_bz2(raw, limit):
    dec = bz2.BZ2Decompressor()
    out = dec.decompress(raw, max_length=limit + 1)
    if len(out) > limit or not dec.eof or dec.unused_data:
        raise ValueError('bzip2 decoded length/trailing bytes')
    return out


def encode(source, method, target):
    source, target = Path(source), Path(target)
    if method not in METHODS:
        raise ValueError('unknown method')
    x = validate(sparse.load_npz(source/'counts.npz'))
    raw_meta = (source/'metadata.json').read_bytes()
    if len(raw_meta) > MAX_BYTES or (x.shape[0]+1)*8+x.nnz*16+512 > MAX_BYTES:
        raise ValueError('decoded metadata/matrix resource bound')
    validate_metadata(raw_meta, x.shape)
    parts = {'metadata.bz2': bz2.compress(raw_meta, 9)}
    if method == 'CSR_BZIP2_9':
        streams = {'shape.u64': np.asarray(x.shape, dtype='<u8').tobytes(),
                   'indptr.u64': x.indptr.astype('<u8').tobytes(),
                   'indices.u32': x.indices.astype('<u4').tobytes(),
                   'values.u32': x.data.astype('<u4').tobytes()}
        parts['csr.bz2'] = bz2.compress(frame(streams), 9)
    else:
        gap = x.indices.astype('<u4').copy()
        for lo, hi in zip(x.indptr[:-1], x.indptr[1:]):
            if hi > lo + 1:
                gap[lo+1:hi] = np.diff(x.indices[lo:hi])
        parts.update({'lengths.pco': pcompress(np.diff(x.indptr)),
                      'gaps.pco': pcompress(gap), 'values.pco': pcompress(x.data)})
    man = {'schema': SCHEMA, 'method': method, 'shape': list(x.shape),
           'nnz': int(x.nnz), 'dtype': 'int64', 'canonical_sha256': csr_hash(x),
           'metadata_sha256': digest(raw_meta), 'metadata_raw_bytes': len(raw_meta),
           'parameters': {'bzip2_level': 9, **({'pcodec_version': '1.0.3', 'pcodec_level': 8}
                                            if method == 'Pcodec' else {})},
           'files': {k: {'bytes': len(v), 'sha256': digest(v)} for k, v in sorted(parts.items())}}
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_STORED) as z:
        for name, raw in sorted({**parts, 'manifest.json': jbytes(man)}.items()):
            zi = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            zi.external_attr = 0o100644 << 16
            z.writestr(zi, raw)
    return {'method': method, 'package_bytes': target.stat().st_size,
            'components': {k: len(v) for k, v in parts.items()},
            'framing_and_manifest_bytes': target.stat().st_size-sum(map(len, parts.values())),
            'package_sha256': digest(target.read_bytes())}


def decode(archive, output):
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or z.getinfo('manifest.json').file_size > 65536:
            raise ValueError('duplicate members/manifest bound')
        man = json.loads(z.read('manifest.json'))
        if man['schema'] != SCHEMA or man['method'] not in METHODS or man['dtype'] != 'int64':
            raise ValueError('unsupported manifest')
        params = {'bzip2_level': 9, **({'pcodec_version': '1.0.3', 'pcodec_level': 8}
                                     if man['method'] == 'Pcodec' else {})}
        if man.get('parameters') != params:
            raise ValueError('frozen parameters mismatch')
        shape = man['shape']; nnz = man['nnz']
        if (not isinstance(shape, list) or len(shape) != 2
                or any(type(d) is not int or not 0 <= d <= MAX_U32 for d in shape)
                or type(nnz) is not int or not 0 <= nnz <= min(MAX_U32, shape[0]*shape[1])):
            raise ValueError('invalid dimensions')
        expected = {'metadata.bz2', 'csr.bz2'} if man['method'] == 'CSR_BZIP2_9' else {
            'metadata.bz2', 'lengths.pco', 'gaps.pco', 'values.pco'}
        if set(man['files']) != expected or set(names) != expected | {'manifest.json'}:
            raise ValueError('unexpected archive members')
        parts = {}
        for name, info in man['files'].items():
            if type(info['bytes']) is not int or not 0 <= info['bytes'] <= MAX_BYTES:
                raise ValueError('member length bound')
            if z.getinfo(name).file_size != info['bytes']:
                raise ValueError('member length mismatch')
            raw = z.read(name)
            if digest(raw) != info['sha256']:
                raise ValueError('payload hash mismatch')
            parts[name] = raw
    n, g = shape
    meta_size = man['metadata_raw_bytes']
    if type(meta_size) is not int or not 0 <= meta_size <= MAX_BYTES:
        raise ValueError('metadata size bound')
    meta = bounded_bz2(parts['metadata.bz2'], meta_size)
    if len(meta) != meta_size or digest(meta) != man['metadata_sha256']:
        raise ValueError('metadata integrity mismatch')
    validate_metadata(meta, shape)
    if man['method'] == 'CSR_BZIP2_9':
        frame_size = 8 + sum(12+len(k) for k in ['shape.u64','indptr.u64','indices.u32','values.u32']) + 16 + (n+1)*8 + nnz*8
        if frame_size > MAX_BYTES:
            raise ValueError('decoded matrix resource bound')
        streams = unframe(bounded_bz2(parts['csr.bz2'], frame_size))
        sizes = {'shape.u64':16, 'indptr.u64':(n+1)*8, 'indices.u32':nnz*4, 'values.u32':nnz*4}
        if set(streams) != set(sizes) or any(len(streams[k]) != v for k,v in sizes.items()):
            raise ValueError('CSR stream lengths mismatch')
        if list(np.frombuffer(streams['shape.u64'], '<u8')) != shape:
            raise ValueError('CSR shape mismatch')
        ptr = np.frombuffer(streams['indptr.u64'], '<u8')
        idx = np.frombuffer(streams['indices.u32'], '<u4')
        values = np.frombuffer(streams['values.u32'], '<u4')
    else:
        if (n+1)*8+nnz*16 > MAX_BYTES:
            raise ValueError('decoded matrix resource bound')
        lengths = pdecompress(parts['lengths.pco'], n)
        if np.any(lengths > g) or int(lengths.astype(np.uint64).sum()) != nnz:
            raise ValueError('row lengths mismatch')
        ptr = np.r_[0, np.cumsum(lengths, dtype=np.int64)]
        gap = pdecompress(parts['gaps.pco'], nnz)
        values = pdecompress(parts['values.pco'], nnz)
        idx = np.empty(nnz, dtype=np.int64)
        for lo, hi in zip(ptr[:-1], ptr[1:]):
            if np.any(gap[lo+1:hi] == 0):
                raise ValueError('nonpositive internal gap')
            idx[lo:hi] = np.cumsum(gap[lo:hi], dtype=np.int64)
    if ptr[0] != 0 or ptr[-1] != nnz or np.any(ptr[1:] < ptr[:-1]) or np.any(ptr > nnz):
        raise ValueError('invalid CSR pointer domain')
    if np.any(idx >= g) or np.any(values == 0):
        raise ValueError('invalid CSR index/value domain')
    x = sparse.csr_matrix((values.astype(np.int64), idx.astype(np.int64), ptr.astype(np.int64)), shape=tuple(shape))
    validate(x)
    if csr_hash(x) != man['canonical_sha256']:
        raise ValueError('decoded count hash mismatch')
    output = Path(output); output.mkdir(exist_ok=False)
    sparse.save_npz(output/'counts.npz', x)
    (output/'metadata.json').write_bytes(meta)
    return {'decode_success': True, 'canonical_sha256': csr_hash(x), 'metadata_sha256': digest(meta)}


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='action', required=True)
    en = sp.add_parser('encode'); en.add_argument('source'); en.add_argument('method', choices=METHODS); en.add_argument('target')
    de = sp.add_parser('decode'); de.add_argument('archive'); de.add_argument('output')
    args = ap.parse_args()
    print(json.dumps(encode(args.source, args.method, args.target) if args.action == 'encode'
                     else decode(args.archive, args.output), sort_keys=True))


if __name__ == '__main__':
    main()
