#!/usr/bin/env python3
"""Offline bounded ZIP layout inventory. Never executes or certifies circuits."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

MAX_ARCHIVE = 512 * 1024**2
MAX_BYTES = 512 * 1024**2
MAX_FILES = 256
NPZ_KEYS = {'U.npy', 'W.npy', 'H2_I.npy', 'H1_I.npy', 'Hsym_lower.npy', 'tree_edges.npy'}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def inventory(z, budget):
    infos = z.infolist()
    require(len(infos) <= MAX_FILES, 'resource_limit:members')
    seen = set()
    files = {}
    for i in infos:
        n = i.filename
        require(n and '\\' not in n and '\x00' not in n and not n.startswith('/')
                and all(x not in ('', '.', '..') for x in n.rstrip('/').split('/')),
                'invalid_input:path')
        require(n not in seen, 'invalid_input:duplicate'); seen.add(n)
        require(not i.flag_bits & 1, 'invalid_input:encrypted')
        mode = i.external_attr >> 16
        require(stat.S_IFMT(mode) in (0, stat.S_IFREG, stat.S_IFDIR), 'invalid_input:special_file')
        if i.is_dir():
            require(n == 'dfthcsos/', 'invalid_input:directory')
            continue
        require(i.file_size <= budget[0], 'resource_limit:uncompressed')
        budget[0] -= i.file_size
        files[n] = i
    return files


def streamed(z, info, capture=False):
    h = hashlib.sha256(); total = 0; chunks = []
    with z.open(info) as f:
        while True:
            b = f.read(1024 * 1024)
            if not b: break
            total += len(b)
            require(total <= info.file_size, 'resource_limit:actual_size')
            h.update(b)
            if capture: chunks.append(b)
    require(total == info.file_size, 'invalid_input:size')
    return h.hexdigest(), b''.join(chunks) if capture else None


def inspect(path):
    path = Path(path)
    require(path.stat().st_size <= MAX_ARCHIVE, 'resource_limit:archive')
    with path.open('rb') as src:
        archive_sha = hashlib.file_digest(src, 'sha256').hexdigest()
        src.seek(0)
        with zipfile.ZipFile(src) as z:
            budget = [MAX_BYTES]; files = inventory(z, budget)
            for base in ('invsqrt', 'dqi'):
                require(sum(base + ext in files for ext in ('.kmx', '.kmb')) == 1,
                        'invalid_input:missing_or_ambiguous_' + base)
            require('dfthcsos/submission.npz' in files, 'invalid_input:missing_npz')
            indices = []
            for n in files:
                if n in ('invsqrt.kmb','invsqrt.kmx','dqi.kmb','dqi.kmx','dfthcsos/submission.npz'):
                    continue
                m = re.fullmatch(r'dfthcsos/angle_k_(0|[1-9][0-9]*)\.(kmx|kmb)', n)
                require(m is not None, 'invalid_input:unexpected_file')
                require(len(m[1]) <= 6, 'resource_limit:index')
                indices.append(int(m[1]))
            require(indices and sorted(indices) == list(range(len(indices))),
                    'invalid_input:angle_sequence')
            rows = []
            for n, info in sorted(files.items()):
                digest, content = streamed(z, info, n.endswith('.npz'))
                require(info.file_size > 0, 'invalid_input:empty_file')
                rows.append(dict(path=n, bytes=info.file_size, sha256=digest))
                if content is not None:
                    with zipfile.ZipFile(io.BytesIO(content)) as nz:
                        arrays = inventory(nz, budget)
                        require(set(arrays) == NPZ_KEYS, 'invalid_input:npz_keys')
                        for a in arrays.values(): streamed(nz, a)
        src.seek(0)
        require(hashlib.file_digest(src, 'sha256').hexdigest() == archive_sha,
                'invalid_witness:archive_changed')
    return dict(schema='geek-work-quantum-package-1', status='LAYOUT_ONLY',
                archive_sha256=archive_sha, files=rows, angle_count=len(indices),
                official_verifier_run=False, circuit_semantics_checked=False,
                numpy_headers_and_values_checked=False, submission_ready=False,
                scope='ZIP names, CRC, bounded bytes and hashes only; no extraction or code execution',
                source='https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation/overview/evaluation')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path)
    p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    # Refuse existing output before opening any input. A race is still protected by x.
    require(not a.output.exists(),'output_exists')
    try: report=inspect(a.archive); code=0
    except (ValueError,OSError,zipfile.BadZipFile,NotImplementedError,RuntimeError) as e:
        report=dict(schema='geek-work-quantum-package-1',status='REJECTED',reason=str(e),submission_ready=False);code=2
    with a.output.open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print(report['status']);return code


if __name__ == '__main__':raise SystemExit(main())
