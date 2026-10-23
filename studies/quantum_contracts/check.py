"""Offline metadata integrity checks; never a substitute for Lean verification."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

FILES = {'README.md', 'LIMITS.md', 'registry.json', 'lean_checks.json', 'check.py', 'test_registry.py'}
EPS = {263, 264, 266, 267, 270, 271, 274, 275, 277, 279, 280, 282}

def require(condition, message):
    if not condition:
        raise ValueError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def validate(root, lean_repo=None, check_manifest=True):
    root = Path(root)
    registry = json.loads((root / 'registry.json').read_text())
    checks_bytes = (root / 'lean_checks.json').read_bytes()
    checks = json.loads(checks_bytes)
    require(registry['schema'] == 'quantum-contract-public-registry-1', 'schema')
    require(registry['lean_repository'] == 'solanaqubits/leanbook', 'repository')
    commit = registry['lean_commit']
    require(re.fullmatch('[0-9a-f]{40}', commit), 'commit')
    require(registry['checks_sha256'] == sha(checks_bytes), 'checks hash')
    require(registry['checks_path'] == 'docs/quantum-series-checks.json', 'checks path')
    require(registry['formal_evidence'] == 'reported_from_pinned_public_lean_checks', 'evidence scope')
    require(registry['third_obligation'] == checks['third_obligation'] == 'OPEN', 'obligation')
    require(registry['hardware_authorization_changed'] is False, 'authorization')
    require(registry['independent_stack_audit'] == checks['independent_stack_audit'] == 'not_performed', 'audit scope')
    require(checks['physical_validation'] is False and checks['violations'] == [], 'check scope')
    require(set(checks['allowed_axioms']) == {'propext', 'Classical.choice', 'Quot.sound'}, 'axioms')
    modules = registry['modules']
    require(len(modules) == 12 and {m['epsilon'] for m in modules} == EPS, 'module inventory')
    require(len({m['module'] for m in modules}) == 12, 'duplicate module')
    require(set(checks['module_hashes']) == {m['module'] for m in modules}, 'check inventory')
    for m in modules:
        require(re.fullmatch('[A-Za-z][A-Za-z0-9]*', m['module']), 'module name')
        require(m['source'] == 'Verification/' + m['module'] + '.lean', 'source path')
        require(re.fullmatch(r'knowledge/[A-Za-z0-9_/-]+\.md', m['card']), 'card path')
        require(m['source_sha256'] == checks['module_hashes'][m['module']], 'source hash')
        for field in ('result', 'assumptions', 'limitations'):
            require(isinstance(m[field], str) and len(m[field].strip()) > 20, field)
        for field in ('source', 'card'):
            require(m[field + '_url'] == f'https://github.com/solanaqubits/leanbook/blob/{commit}/{m[field]}', 'pinned URL')
        if lean_repo:
            for field in ('source', 'card'):
                blob = subprocess.check_output(['git', '-C', str(lean_repo), 'show', f'{commit}:{m[field]}'])
                require(bool(blob), 'empty source')
                if field == 'source':
                    require(sha(blob) == m['source_sha256'], 'Git source bytes')
    if lean_repo:
        blob = subprocess.check_output(['git', '-C', str(lean_repo), 'show', f'{commit}:{registry["checks_path"]}'])
        require(blob == checks_bytes, 'Git checks bytes')
    if check_manifest:
        manifest = json.loads((root / 'MANIFEST.json').read_text())
        require(set(manifest) == FILES, 'manifest inventory')
        require({p.name for p in root.iterdir() if p.is_file()} == FILES | {'MANIFEST.json'}, 'file allowlist')
        for name, digest in manifest.items():
            require(sha((root / name).read_bytes()) == digest, 'manifest hash: ' + name)
    return {'modules': len(modules), 'source_links': 24, 'git_source_blobs': 25 if lean_repo else 0,
            'scope': 'metadata integrity only; reported Lean evidence; no new proof or physical validation'}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lean-repo', type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(Path(__file__).parent, args.lean_repo), indent=2))
