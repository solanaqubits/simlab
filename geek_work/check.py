#!/usr/bin/env python3
"""Verify packaged bytes and run all synthetic tests; reject skips and failures."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
root=Path(__file__).resolve().parent
manifest=json.loads((root/'MANIFEST.json').read_text())
assert manifest['schema']=='geek-work-public-files-1'
actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()
        and '__pycache__' not in p.parts and p.name!='MANIFEST.json'}
assert actual==set(manifest['files']), 'package file set changed'
for name,sha in manifest['files'].items():
    path=root/name
    assert not path.is_symlink() and path.resolve().is_relative_to(root)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==sha, name
suite=unittest.defaultTestLoader.discover(str(root/'tests'))
result=unittest.TextTestRunner(verbosity=2).run(suite)
assert result.testsRun>0
assert result.wasSuccessful() and not result.skipped and not result.expectedFailures and not result.unexpectedSuccesses
print(json.dumps(dict(status='passed',tests=result.testsRun,skips=0,manifest_files=len(actual),
                     scope='Synthetic protocol tests and packaged bytes; no private graph or scientific audit')))
