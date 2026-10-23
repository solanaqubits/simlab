"""Offline validation of the published Prometheus metadata projection, not physics."""
from decimal import Decimal
from pathlib import Path
import argparse
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parent
DATA_SHA256 = '925ff1f88d65dcf063bdaffaca924a068ecd6acd8e5305e10bcaaa4e1d4a500d'
MAX_BYTES = 8 * 1024 * 1024
TYPES = {'integer', 'number', 'string', 'boolean', 'null'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def keys(obj, names):
    require(type(obj) is dict and set(obj) == set(names), 'unexpected object keys')


def text(value):
    require(type(value) is str and bool(value.strip()), 'nonempty text required')


def load(raw):
    require(len(raw) <= MAX_BYTES, 'input byte cap exceeded')
    def pairs(items):
        out = {}
        for k, v in items:
            require(k not in out, 'duplicate JSON key')
            out[k] = v
        return out
    def bad(token):
        raise ValueError('nonfinite number: ' + token)
    return json.loads(raw, object_pairs_hook=pairs, parse_float=Decimal, parse_constant=bad)


def indexed(rows, maximum):
    require(type(rows) is list and 0 < len(rows) <= maximum, 'bounded nonempty registry required')
    out = {}
    for row in rows:
        require(type(row) is dict and type(row.get('id')) is str, 'record ID required')
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', row['id']), 'invalid ID')
        require(row['id'] not in out, 'duplicate ID')
        out[row['id']] = row
    return out


def typed(kind, value):
    require(kind in TYPES, 'unknown scalar type')
    if kind == 'number':
        require(type(value) is str and len(value) <= 4096 and re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?', value), 'decimal string required')
        result = Decimal(value)
        require(result.is_finite() and abs(result.adjusted()) <= 1000, 'bounded finite decimal required')
        return result
    require(type(value) is {'integer': int, 'string': str, 'boolean': bool, 'null': type(None)}[kind], 'scalar type mismatch')
    return value


def literal_type(value):
    for cls, name in [(bool, 'boolean'), (int, 'integer'), (str, 'string')]:
        if type(value) is cls:
            return name
    raise ValueError('requirement scalar outside this fixed projection')


def same(a, b):
    return type(a) is type(b) and a == b


def evaluate(data):
    keys(data, ['schema', 'provenance', 'field_specs', 'scenarios', 'groups', 'claims', 'expected_statuses', 'formal_sources', 'historical_verification'])
    require(data['schema'] == 'prometheus-public-compatibility-1.0.0', 'schema mismatch')
    provenance = data['provenance']
    keys(provenance, ['source_acceptance_sha', 'source_registry_sha256', 'source_crosswalk_sha256', 'public_leanbook_commit', 'export_kind', 'source_validation'])
    for key in ['source_acceptance_sha', 'public_leanbook_commit']:
        require(re.fullmatch(r'[0-9a-f]{40}', provenance[key]), 'full commit required')
    for key in ['source_registry_sha256', 'source_crosswalk_sha256']:
        require(re.fullmatch(r'[0-9a-f]{64}', provenance[key]), 'full digest required')
    require(provenance['export_kind'] == 'selected_metadata_projection_not_full_source_audit', 'scope promotion forbidden')
    text(provenance['source_validation'])
    specs = indexed(data['field_specs'], 96)
    scenarios = indexed(data['scenarios'], 96)
    groups = indexed(data['groups'], 128)
    claims = indexed(data['claims'], 14)
    require(set(claims) == {f'NC{i:02d}' for i in range(1, 15)}, 'complete 14-claim inventory required')
    for spec in specs.values():
        keys(spec, ['id', 'type', 'unit', 'scope'])
        require(spec['type'] in TYPES - {'null'}, 'invalid field type')
        text(spec['unit']); text(spec['scope'])
    resolved = {}
    for name, scenario in scenarios.items():
        keys(scenario, ['id', 'fields'])
        require(type(scenario['fields']) is dict and scenario['fields'], 'scenario fields required')
        resolved[name] = {}
        for field, datum in scenario['fields'].items():
            require(field in specs, 'unknown field')
            keys(datum, ['type', 'value', 'unit', 'scope', 'origin'])
            spec = specs[field]
            require(datum['type'] in {spec['type'], 'null'}, 'field type mismatch')
            require(datum['unit'] == spec['unit'] and datum['scope'] == spec['scope'], 'unit/scope mismatch')
            require(datum['origin'] in {'observed', 'editorial_anchored_mapping'}, 'unknown historical origin')
            resolved[name][field] = typed(datum['type'], datum['value'])
    results = {}
    rules = 0
    for name, group in groups.items():
        keys(group, ['id', 'scenarios', 'fields', 'requirements', 'claim'])
        names, fields = group['scenarios'], group['fields']
        require(type(names) is list and len(names) >= 2 and len(set(names)) == len(names) and all(x in scenarios for x in names), 'invalid scenario selection')
        require(type(fields) is list and fields and len(set(fields)) == len(fields) and all(x in specs for x in fields), 'invalid field selection')
        require(group['claim'] == 'metadata_compatibility_only', 'claim promotion forbidden')
        require(type(group['requirements']) is list, 'requirements list required')
        rules += len(fields) + len(group['requirements'])
        require(rules <= 128, 'rule cap exceeded')
        states = []
        for field in fields:
            values = [resolved[s].get(field) for s in names]
            present = [v for v in values if v is not None]
            mismatch = bool(present) and any(not same(present[0], v) for v in present[1:])
            states.append('mismatch' if mismatch else 'missing_metadata' if len(present) != len(values) else 'metadata_match_only')
        metadata = 'mismatch' if 'mismatch' in states else 'missing_metadata' if 'missing_metadata' in states else 'metadata_match_only'
        requirements, seen = [], set()
        for requirement in group['requirements']:
            keys(requirement, ['scenario', 'field', 'equals'])
            s, f, target = requirement['scenario'], requirement['field'], requirement['equals']
            require(s in names and f in specs and (s, f) not in seen, 'invalid requirement reference')
            seen.add((s, f))
            require(literal_type(target) == specs[f]['type'], 'typed requirement mismatch')
            value = resolved[s].get(f)
            requirements.append('unknown' if value is None else 'satisfied' if same(value, target) else 'false')
        status = 'blocked_requirements' if 'false' in requirements else 'unsupported_requirements' if 'unknown' in requirements else metadata
        req = 'not_requested' if not requirements else 'false' if 'false' in requirements else 'unknown' if 'unknown' in requirements else 'satisfied_metadata_only'
        results[name] = dict(status=status, metadata_status=metadata, requirement_status=req)
    require(data['expected_statuses'] == results, 'published baseline differs from recomputed metadata')
    for claim in claims.values():
        keys(claim, ['id', 'title', 'groups', 'coverage', 'state', 'excluded_conclusion', 'required_bridge'])
        require(claim['state'] == 'not_composable_without_bridge', 'physical claim promotion forbidden')
        require(claim['coverage'] in {'existing_rule', 'additional_editorial_boundary'}, 'invalid coverage')
        require(type(claim['groups']) is list and len(set(claim['groups'])) == len(claim['groups']), 'unique group list required')
        require(claim['groups'] or claim['coverage'] == 'additional_editorial_boundary', 'existing rule coverage needs a rule')
        require(all(g in results and results[g]['status'] != 'metadata_match_only' for g in claim['groups']), 'claim needs blocking or missing-premise group')
        for key in ['title', 'excluded_conclusion', 'required_bridge']: text(claim[key])
    require(len(data['formal_sources']) == 11, 'formal source inventory changed')
    require(len({x['path'] for x in data['formal_sources']}) == 11, 'duplicate formal source')
    require({c['id'] for c in claims.values() if c['coverage'] == 'additional_editorial_boundary'} == {'NC05', 'NC08', 'NC09', 'NC10', 'NC12', 'NC14'}, 'editorial boundaries must remain explicit')
    for source in data['formal_sources']:
        keys(source, ['module', 'path', 'sha256', 'url', 'evidence'])
        require(re.fullmatch(r'Verification/[A-Za-z0-9_]+\.lean', source['path']), 'invalid formal source path')
        require(source['module'] == source['path'][:-5].replace('/', '.'), 'module/path mismatch')
        require(re.fullmatch(r'[0-9a-f]{64}', source['sha256']), 'source digest required')
        require(source['url'] == 'https://github.com/solanaqubits/leanbook/blob/' + provenance['public_leanbook_commit'] + '/' + source['path'], 'public source link mismatch')
        text(source['evidence'])
    require(type(data['historical_verification']) is list, 'historical report list required')
    return dict(schema='prometheus-public-metadata-check-1.0.0', groups=results, claims=len(claims),
                scenarios=len(scenarios), rules=rules, public_source_links=len(data['formal_sources']),
                physical_validation_established=False, composable_security_established=False,
                third_obligation='OPEN', scope='Published selected metadata only; private source/blob audit and historical checks are reported, not reproduced.')


def verify_bundle(root=ROOT):
    manifest = load((root / 'MANIFEST.json').read_bytes())
    keys(manifest, ['schema', 'files', 'scope'])
    require(manifest['schema'] == 'prometheus-public-bundle-1.0.0', 'bundle schema mismatch')
    allowed = {'registry.json', 'check.py', 'test_check.py', 'README.md', 'LIMITS.md'}
    require(set(manifest['files']) == allowed, 'exact public allowlist required')
    for name, digest in manifest['files'].items():
        path = root / name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_BYTES, 'bounded regular bundle file required')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, 'bundle digest mismatch: ' + name)
    raw = (root / 'registry.json').read_bytes()
    require(hashlib.sha256(raw).hexdigest() == DATA_SHA256, 'reviewed snapshot changed')
    return evaluate(load(raw))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='print full recomputed status report')
    args = parser.parse_args()
    report = verify_bundle()
    print(json.dumps(report if args.json else {'claims': report['claims'], 'groups': len(report['groups']), 'scenarios': report['scenarios'], 'rules': report['rules'], 'scope': report['scope'], 'third_obligation': report['third_obligation']}, indent=2))


if __name__ == '__main__':
    main()
