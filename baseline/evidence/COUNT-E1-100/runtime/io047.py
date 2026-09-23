"""Bounded full-count adapters and deterministic framing for panel047 only."""
import base64
import bz2
import hashlib
import json
from pathlib import Path, PurePosixPath
import struct
import zipfile

import h5py
import numpy as np
from scipy import sparse

MAX_NNZ = 100_000_000
MAX_DIM = 2_000_000


def jbytes(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))+'\n').encode()


def save(path, value):
    with Path(path).open('xb') as f:
        f.write(jbytes(value))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(8*1024**2), b''):
            h.update(chunk)
    return h.hexdigest()


def valid_values(a):
    # Python scalar comparisons avoid NumPy2 weak scalar promotion rounding
    # uint32_max up to2**32 when compared with float32 arrays.
    if (a.dtype.kind not in 'iuf' or not np.all(np.isfinite(a))
            or a.min(initial=0).item() < 0 or a.max(initial=0).item() > 2**32-1
            or (a.dtype.kind == 'f' and not np.array_equal(a,np.floor(a)))):
        raise ValueError('Counts must be exact uint32-range nonnegative integers')


def shape2(raw):
    a = np.asarray(raw)
    if a.shape != (2,) or a.dtype.kind not in 'iu' or np.any(a <= 0) or np.any(a > MAX_DIM):
        raise ValueError('Invalid integer matrix shape')
    return tuple(int(v) for v in a)


def from_parts(shape, ptr, idx, val, encoding='csr_matrix', canonical=False):
    shape = shape2(shape)
    if encoding not in ('csr_matrix', 'csc_matrix'):
        raise ValueError('Unknown storage')
    major, minor = shape if encoding == 'csr_matrix' else shape[::-1]
    ptr, idx, val = map(np.asarray, (ptr, idx, val))
    if any(a.ndim != 1 for a in (ptr, idx, val)) or ptr.dtype.kind not in 'iu' or idx.dtype.kind not in 'iu':
        raise ValueError('Sparse arrays require 1D integer pointers/indices')
    if len(val) > MAX_NNZ or len(idx) != len(val) or len(ptr) != major+1:
        raise ValueError('Sparse lengths disagree or exceed budget')
    if ptr[0] != 0 or ptr[-1] != len(val) or np.any(ptr < 0) or np.any(ptr > len(val)) or np.any(ptr[1:] < ptr[:-1]):
        raise ValueError('Malformed pointers')
    if np.any(idx < 0) or np.any(idx >= minor):
        raise ValueError('Index out of range')
    valid_values(val)
    ctor = sparse.csr_matrix if encoding == 'csr_matrix' else sparse.csc_matrix
    x = ctor((val.astype(np.int64), idx.astype(np.int64), ptr.astype(np.int64)), shape=shape)
    if canonical:
        x.sum_duplicates()
        x.eliminate_zeros()
        x = x.tocsr()
        x.sort_indices()
    else:
        # Format conversion is permitted; reordering/repair of malformed decoded
        # sparse entries is not. BPCells AnnData export is canonical CSR.
        if not x.has_canonical_format or np.any(x.data == 0):
            raise ValueError('Decoded sparse arrays are noncanonical')
        x = x.tocsr()
    valid_values(x.data)
    return x


def read_x(path, canonical=True):
    with h5py.File(path, 'r') as h:
        raw = h['X']
        if isinstance(raw, h5py.Dataset):
            shape = shape2(raw.shape)
            # Chunk dense sources to avoid a full dense copy in memory.
            parts, nnz = [], 0
            step = max(1, 32*1024**2 // max(1, shape[1]*raw.dtype.itemsize))
            for start in range(0, shape[0], step):
                a = raw[start:start+step]
                valid_values(a)
                part = sparse.csr_matrix(a.astype(np.int64))
                nnz += part.nnz
                if nnz > MAX_NNZ:
                    raise ValueError('Dense nnz budget exceeded')
                parts.append(part)
            return sparse.vstack(parts, format='csr'), 'dense_array'
        enc = raw.attrs.get('encoding-type', '')
        if isinstance(enc, bytes):
            enc = enc.decode()
        shape = raw.attrs.get('shape')
        if shape is None and 'shape' in raw:
            shape = raw['shape'][:]
        shape = shape2(shape)
        if enc not in ('csr_matrix','csc_matrix'):
            raise ValueError('Unsupported sparse encoding')
        arrays = [raw[k] for k in ('data','indices','indptr')]
        if any(not isinstance(a,h5py.Dataset) or a.ndim != 1 for a in arrays):
            raise ValueError('Malformed sparse dataset dimensions')
        data,idx,ptr = arrays
        major = shape[0] if enc == 'csr_matrix' else shape[1]
        if data.size > MAX_NNZ or idx.size != data.size or ptr.size != major+1 or idx.dtype.kind not in 'iu' or ptr.dtype.kind not in 'iu':
            raise ValueError('Sparse dataset metadata exceeds bounds or disagrees')
        return from_parts(shape, raw['indptr'][:], raw['indices'][:], raw['data'][:], enc, canonical), enc


def csr_sha(x):
    h = hashlib.sha256()
    for a in (x.shape, x.indptr, x.indices, x.data):
        h.update(np.asarray(a, dtype='<u8').tobytes())
    return h.hexdigest()


def labels(group):
    key = group.attrs.get('_index', '_index')
    if isinstance(key, bytes):
        key = key.decode()
    item = group[key]
    if isinstance(item, h5py.Group):
        cats = item['categories'].asstr()[:].tolist()
        codes = item['codes'][:]
        if codes.dtype.kind not in 'iu' or np.any(codes < 0) or np.any(codes >= len(cats)):
            raise ValueError('Invalid categorical identifiers')
        return [cats[int(c)] for c in codes]
    return item.asstr()[:].tolist()


def metadata(path, shape):
    with h5py.File(path, 'r') as h:
        spots, genes = labels(h['obs']), labels(h['var'])
        coords = h['obsm/spatial'][:]
    if len(spots) != shape[0] or len(genes) != shape[1] or coords.ndim != 2 or coords.shape[0] != shape[0] or coords.dtype.kind not in 'iuf':
        raise ValueError('Metadata dimension or dtype mismatch')
    return {'schema':'047-exact-metadata-v1', 'spot_ids':spots, 'gene_ids':genes,
            'coordinates_shape':list(coords.shape), 'coordinates_dtype':coords.dtype.str,
            'coordinates_base64':base64.b64encode(coords.tobytes(order='C')).decode()}


def safe_name(name):
    p = PurePosixPath(name)
    if not name or p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or str(p) != name:
        raise ValueError('Unsafe member name')
    return name


def frame(streams):
    """Same sorted named-stream framing for CSR and BPCells backend controls."""
    out = bytearray(b'F047')
    out.extend(struct.pack('<I', len(streams)))
    for name, blob in sorted(streams.items()):
        name = safe_name(name).encode('utf8')
        out.extend(struct.pack('<IQ', len(name), len(blob)))
        out.extend(name)
        out.extend(blob)
    return bytes(out)


def unframe(blob):
    if blob[:4] != b'F047' or len(blob) < 8:
        raise ValueError('Invalid frame')
    count, = struct.unpack_from('<I', blob, 4)
    pos, streams = 8, {}
    if count > 100000:
        raise ValueError('Too many streams')
    for _ in range(count):
        if pos+12 > len(blob):
            raise ValueError('Truncated frame')
        n, size = struct.unpack_from('<IQ', blob, pos)
        pos += 12
        if pos+n+size > len(blob):
            raise ValueError('Truncated frame member')
        name = safe_name(blob[pos:pos+n].decode('utf8'))
        pos += n
        if name in streams:
            raise ValueError('Duplicate frame name')
        streams[name] = blob[pos:pos+size]
        pos += size
    if pos != len(blob):
        raise ValueError('Trailing frame bytes')
    return streams


def csr_streams(x):
    return {'shape.u64':np.asarray(x.shape, dtype='<u8').tobytes(),
            'indptr.u64':x.indptr.astype('<u8').tobytes(),
            'indices.u32':x.indices.astype('<u4').tobytes(),
            'values.u32':x.data.astype('<u4').tobytes()}


def read_csr_streams(s):
    if set(s) != {'shape.u64','indptr.u64','indices.u32','values.u32'}:
        raise ValueError('Unexpected CSR streams')
    return from_parts(np.frombuffer(s['shape.u64'], '<u8'), np.frombuffer(s['indptr.u64'], '<u8'),
                      np.frombuffer(s['indices.u32'], '<u4'), np.frombuffer(s['values.u32'], '<u4'))


def compress(blob, backend):
    if backend == 'bz2':
        return bz2.compress(blob, 9)
    if backend == 'zstd':
        import zstandard
        return zstandard.ZstdCompressor(level=9, threads=0).compress(blob)
    raise ValueError('Unknown backend')


def decompress(blob, backend):
    if backend == 'bz2':
        return bz2.decompress(blob)
    if backend == 'zstd':
        import zstandard
        return zstandard.ZstdDecompressor().decompress(blob)
    raise ValueError('Unknown backend')


def ledger(root):
    result = []
    for p in sorted(Path(root).rglob('*')):
        if p.is_symlink():
            raise ValueError('Symlink in encoded payload')
        if p.is_file():
            result.append({'path':p.relative_to(root).as_posix(), 'bytes':p.stat().st_size, 'sha256':sha(p)})
    if not result:
        raise ValueError('Empty codec payload')
    return result


def pack(path, codec_root, meta, method):
    entries = ledger(codec_root)
    mb = jbytes(meta)
    manifest = {'schema':'047-package-v1','method':method,'files':entries,
                'metadata_sha256':hashlib.sha256(mb).hexdigest()}
    with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_STORED) as z:
        def put(name, blob):
            info = zipfile.ZipInfo(name, (1980,1,1,0,0,0))
            info.external_attr = 0o100644 << 16
            z.writestr(info, blob)
        put('metadata.json', mb)
        put('manifest.json', jbytes(manifest))
        for entry in entries:
            put('matrix/'+entry['path'], (codec_root/entry['path']).read_bytes())
    return entries


def extract(path, dest):
    dest.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(path) as z:
        man = json.loads(z.read('manifest.json'))
        mb = z.read('metadata.json')
        if man['schema'] != '047-package-v1' or hashlib.sha256(mb).hexdigest() != man['metadata_sha256']:
            raise ValueError('Metadata/schema integrity failure')
        names = ['matrix/'+safe_name(f['path']) for f in man['files']]
        expected = ['manifest.json','metadata.json']+names
        if len(set(expected)) != len(expected) or len(z.namelist()) != len(expected) or set(z.namelist()) != set(expected):
            raise ValueError('Duplicate or unexpected package entries')
        for entry, name in zip(man['files'], names):
            blob = z.read(name)
            if len(blob) != entry['bytes'] or hashlib.sha256(blob).hexdigest() != entry['sha256']:
                raise ValueError('Stream hash/length mismatch')
            p = dest/entry['path']
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open('xb') as f:
                f.write(blob)
    return man['method'], json.loads(mb)
