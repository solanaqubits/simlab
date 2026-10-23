"""Offline packaging validation; no proof, simulation or independent audit."""
import hashlib
import json
from pathlib import Path
import re

FILES = {'snapshot.json', 'README.md', 'LIMITS.md', 'check.py', 'test_check.py'}
COUNTS = [(16, 36878, 123, 53), (18, 37239, 170, 53),
          (15, 37806, 197, 53), (14, 38331, 178, 53), (14, 38573, 187, 53)]
OBLIGATIONS = {'physical_realizability', 'certified_positive_skr',
               'hardware_wcet', 'third_obligation'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(data):
    require(data['schema'] == 'prometheus-program-metadata-1', 'schema')
    require(data['source_access'] == 'private_provenance_identifiers_not_public_proof_links', 'source access')
    require(data['new_scientific_verification'] is False, 'historical scope')
    require(data['independent_audit'] == 'not_performed', 'audit scope')
    require(set(data['obligations']) == OBLIGATIONS, 'obligation keys')
    require(set(data['obligations'].values()) == {'OPEN'}, 'obligation closure')
    require(data['historical_scenario_projection'] == 38, 'projection scope')
    require(data['negative_predicates'] == 14, 'predicate count')
    require(data['coverage_classification'] == 'historical_8_3_3_separate_from_14_predicates', 'coverage semantics')
    epochs = data['historical_epochs']
    require(len(epochs) == 5, 'epoch count')
    require([(e['lean_tests'], e['declarations'], e['python_tests'], e['brain_tests'])
             for e in epochs] == COUNTS, 'historical counts')
    require(len({e['stage'] for e in epochs}) == 5, 'duplicate stages')
    require(sorted(q for e in epochs for q in e['questions']) == list(range(1, 11)), 'question partition')
    for e in epochs:
        require(e['scope'] == 'historical_scoped_not_rerun', 'epoch scope')
    require(set(data['research_snapshot']) == {'leanbook', 'simlab'}, 'snapshot keys')
    commits = [data['consolidation_commit'], *data['research_snapshot'].values()]
    commits += [e[key] for e in epochs for key in ('lean_sha', 'simlab_sha')]
    require(all(isinstance(c, str) and re.fullmatch('[0-9a-f]{40}', c) for c in commits), 'commit format')
    audits = data['audits']
    require([a['question'] for a in audits] == list(range(1, 11)), 'audit coverage')
    for a in audits:
        e = next(e for e in epochs if a['question'] in e['questions'])
        require(a['stage'] == e['stage'], 'audit-stage relation')
        for key in ('topic', 'premises', 'formal_result', 'historical_numerics', 'limitations'):
            require(isinstance(a[key], str) and bool(a[key].strip()), 'missing ' + key)


def check(root):
    root = Path(root)
    manifest = json.loads((root / 'MANIFEST.json').read_text())
    require(manifest['schema'] == 'prometheus-program-bundle-1', 'bundle schema')
    require(set(manifest['files']) == FILES, 'allowlist')
    actual = {p.name for p in root.iterdir() if p.name != '__pycache__'}
    require(actual == FILES | {'MANIFEST.json'}, 'unexpected package entry')
    for name, digest in manifest['files'].items():
        path = root / name
        require(not path.is_symlink() and path.is_file(), 'unsafe package entry')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, 'hash: ' + name)
    validate(json.loads((root / 'snapshot.json').read_text()))
    return {'status': 'passed', 'scope': 'metadata_packaging_only', 'audits': 10,
            'historical_epochs': 5, 'new_scientific_verification': False,
            'independent_audit': 'not_performed'}


if __name__ == '__main__':
    try:
        print(json.dumps(check(Path(__file__).resolve().parent), indent=2))
    except (ValueError, KeyError, TypeError, OSError, StopIteration) as exc:
        raise SystemExit('REJECTED: ' + str(exc))
