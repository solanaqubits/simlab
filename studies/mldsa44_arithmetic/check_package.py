#!/usr/bin/env python3
"""Offline replay of the frozen Stage 11 patch on its selected baseline subset."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile

BASE = '78c83599f57ecb28847ba3ebc4528598318129b8'
PATCH = '068f95d97bd1aa44940eaebe5e46e665653e780e1ce999be7fe5bde44460497e'
BASE_LIB = '8a18ad33d01c108dc32a3bb0f07e924eca0c356f287dc4b012902c84336b4fc6'
PREFIX = 'crates/ml_dsa_44/src/'
PATHS = {PREFIX + name + '.cairo' for name in
         ('ct', 'encx', 'k2', 'kc0', 'lib', 'nt0', 'nttu', 'pk0', 'sa0', 'verx', 'x2', 'zread')}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_path(root, name):
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or str(p) != name:
        raise ValueError('Unsafe package path')
    result = root.joinpath(*p.parts)
    if result.is_symlink() or not result.resolve().is_relative_to(root):
        raise ValueError('Unsafe package path')
    return result


def check(root):
    root = Path(root).resolve()
    manifest = json.loads((root / 'manifest.json').read_text())
    if manifest['upstream_base'] != BASE:
        raise ValueError('Wrong selected upstream base')
    if digest(root / 'candidate.patch') != PATCH or manifest['patch_sha256'] != PATCH:
        raise ValueError('Wrong selected Stage 11 patch')
    paths = manifest['paths']
    if set(paths) != PATHS:
        raise ValueError('Unexpected production paths')
    for name, row in paths.items():
        expected = BASE_LIB if name == PREFIX + 'lib.cairo' else None
        if row['base_sha256'] != expected:
            raise ValueError('Wrong pinned baseline hash')
    for name, expected in manifest['files'].items():
        if digest(checked_path(root, name)) != expected:
            raise ValueError('Changed package file: ' + name)
    with tempfile.TemporaryDirectory(prefix='mldsa-subset-replay-') as tmp:
        work = Path(tmp)
        subprocess.run(['git', 'init', '-q', str(work)], check=True, capture_output=True)

        def git(*args):
            return subprocess.check_output(['git', '-c', 'core.hooksPath=/dev/null',
                                            '-C', str(work), *args], text=True,
                                           stderr=subprocess.PIPE).strip()

        for name, row in paths.items():
            if row['base_sha256'] is not None:
                source = checked_path(root, 'baseline/' + name)
                if digest(source) != row['base_sha256']:
                    raise ValueError('Baseline subset mismatch: ' + name)
                target = work / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        git('add', '--', 'crates')
        baseline_tree = git('write-tree')
        git('apply', '--check', '--index', str(root / 'candidate.patch'))
        git('apply', '--index', str(root / 'candidate.patch'))
        actual = set(git('diff', '--cached', '--name-only', baseline_tree).splitlines())
        if actual != PATHS:
            raise ValueError('Patch changed unexpected source set')
        for name, row in paths.items():
            candidate = checked_path(root, 'candidate/' + name)
            if digest(work / name) != row['candidate_sha256']:
                raise ValueError('Replayed source mismatch: ' + name)
            if (work / name).read_bytes() != candidate.read_bytes():
                raise ValueError('Candidate source mismatch: ' + name)
        candidate_tree = git('write-tree')
    return {'ok': True, 'files_checked': len(manifest['files']),
            'source_paths_replayed': len(paths), 'patch_sha256': PATCH,
            'baseline_subset_tree': baseline_tree, 'candidate_subset_tree': candidate_tree,
            'replay_scope': 'selected-source-subset', 'full_upstream_checkout': False,
            'fresh_cairo_build': False, 'fresh_benchmark': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    print(json.dumps(check(parser.parse_args().root), indent=2))
