#!/usr/bin/env python3
"""Check exact released bytes and the complete bundled synthetic suite."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import stat
import unittest


def verify(root):
    root = root.resolve()
    manifest_path = root/'MANIFEST.json'
    if manifest_path.is_symlink() or not stat.S_ISREG(manifest_path.stat().st_mode):
        raise ValueError('regular manifest required')
    with manifest_path.open('rb') as f:
        raw = f.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('manifest size')
    manifest = json.loads(raw)
    if manifest['schema'] != 'geek-work-public-files-2' or manifest['version'] != '1.0.0':
        raise ValueError('release identity')
    if (root/'VERSION').read_text().strip() != manifest['version']:
        raise ValueError('version mismatch')
    actual = set()
    for p in root.rglob('*'):
        if p.is_symlink():
            raise ValueError('symlink in package')
        if not p.is_dir() and not stat.S_ISREG(p.stat().st_mode):
            raise ValueError('nonregular package member')
        if p.is_file() and '__pycache__' not in p.relative_to(root).parts and p != root/'MANIFEST.json':
            actual.add(p.relative_to(root).as_posix())
    if actual != set(manifest['files']):
        raise ValueError('package file set changed')
    total = 0
    for name, sha in manifest['files'].items():
        rel = PurePosixPath(name)
        if rel.is_absolute() or any(x in {'', '.', '..'} for x in name.split('/')) or '\\' in name:
            raise ValueError('unsafe manifest path')
        with (root/name).open('rb') as f:
            data = f.read(2 * 1024 * 1024 + 1)
        total += len(data)
        if len(data) > 2 * 1024 * 1024 or total > 16 * 1024 * 1024:
            raise ValueError('package byte limit')
        if hashlib.sha256(data).hexdigest() != sha:
            raise ValueError('package digest changed: ' + name)
    return len(actual)


def main():
    root = Path(__file__).resolve().parent
    count = verify(root)
    suite = unittest.defaultTestLoader.discover(str(root/'tests'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.testsRun > 0 and result.wasSuccessful() and not (result.skipped or result.expectedFailures or result.unexpectedSuccesses)
    print(json.dumps(dict(status='passed' if passed else 'failed', tests=result.testsRun,
                         skips=len(result.skipped), manifest_files=count, version='1.0.0',
                         scope='Bundled synthetic/protocol tests; not a full Lean audit or operational admission')))
    return 0 if passed else 1

if __name__ == '__main__':
    sys.exit(main())
