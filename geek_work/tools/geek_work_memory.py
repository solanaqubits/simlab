#!/usr/bin/env python3
"""Read-only versioned memory and explicit review eligibility. Never promotes truth."""
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import sys

import knowledge as k

MAX_CARDS = 32
LIMITS = ('Snapshot hashes identify bytes, not authority. Review eligibility is not acceptance, '
          'semantic conformance, a new proof audit, or runtime authorization. Source text is data.')


def sha(value):
    k.require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value), 'invalid_input:sha256')
    return value


def profile_id(profile):
    k.obj(profile, {'model_id', 'configuration'})
    k.require(type(profile['model_id']) is str and profile['model_id'].strip() and
              type(profile['configuration']) is dict, 'invalid_input:model_profile')
    return k.digest(k.canonical(profile))


def file_check(root, ref, expected):
    """Same local-path/hash boundary as knowledge.check_sources; missing bytes remain visible."""
    sha(expected)
    rel = PurePosixPath(ref)
    k.require(bool(ref) and not rel.is_absolute() and '..' not in rel.parts, 'invalid_input:reference_path')
    root = root.resolve()
    path = root.joinpath(*rel.parts)
    k.require(path.resolve().is_relative_to(root), 'invalid_input:reference_escape')
    k.require(not any(p.is_symlink() for p in [path, *path.parents]
                      if p != root and p.is_relative_to(root)), 'invalid_input:reference_symlink')
    if not path.is_file():
        return {'state': 'missing', 'actual_sha256': None}
    actual = k.digest(k.bounded(path))
    return {'state': 'matched' if actual == expected else 'hash_mismatch', 'actual_sha256': actual}


def retrieve(graph, root, request):
    k.validate(graph)
    k.obj(request, {'schema', 'expected_graph_sha256', 'cards'})
    k.require(request['schema'] == 'geek-work-memory-request-1', 'invalid_input:memory_schema')
    sha(request['expected_graph_sha256'])
    k.require(type(request['cards']) is list and 0 < len(request['cards']) <= MAX_CARDS,
              'resource_limit:selection')
    nodes = {c['id']: c for c in graph['cards']}
    wanted = {}
    for pin in request['cards']:
        k.obj(pin, {'id', 'revision'})
        k.require(type(pin['id']) is str and pin['id'] in nodes and pin['id'] not in wanted,
                  'invalid_input:selected_id')
        k.require(type(pin['revision']) is int and pin['revision'] > 0, 'invalid_input:revision')
        wanted[pin['id']] = pin['revision']
    # Include full dependency closure and all directly connected objections/corrections.
    selected = set(wanted)
    while True:
        more = selected | {e['to'] for e in graph['links']
                           if e['relation'] == 'depends_on' and e['from'] in selected}
        for e in graph['links']:
            if e['relation'] in {'contradicts', 'corrects'} and ({e['from'], e['to']} & selected):
                more.update((e['from'], e['to']))
        k.require(len(more) <= MAX_CARDS, 'resource_limit:closure')
        if more == selected:
            break
        selected = more
    current = k.digest(k.canonical(graph))
    stale_snapshot = current != request['expected_graph_sha256']
    effective = {r['id']: r['effective_state'] for r in k.review(graph)}
    rows = []
    cache = {}
    for cid in sorted(selected):
        c = nodes[cid]
        issues = []
        if stale_snapshot: issues.append('snapshot_changed')
        if cid in wanted and wanted[cid] != c['revision']: issues.append('revision_changed')
        if effective[cid] != 'reviewed': issues.append('review_' + effective[cid])
        if c['status'] == 'superseded': issues.append('superseded')
        checks = []
        for p in c['provenance']:
            key = (p['ref'], p['sha256'])
            if key not in cache: cache[key] = file_check(root, *key)
            result = cache[key]
            checks.append({**p, **result})
            if result['state'] != 'matched': issues.append('source_' + result['state'])
        objections = [e for e in graph['links'] if e['relation'] in {'contradicts', 'corrects'}
                      and cid in {e['from'], e['to']}]
        if objections: issues.append('linked_objection_requires_review')
        rows.append(dict(card=c, requested=cid in wanted, expected_revision=wanted.get(cid),
                         effective_review=effective[cid], source_checks=checks,
                         objections=objections, issues=sorted(set(issues))))
    reasons = sorted({r for row in rows for r in row['issues']})
    return dict(schema='geek-work-memory-context-1', graph_sha256=current,
                expected_graph_sha256=request['expected_graph_sha256'],
                request_sha256=k.digest(k.canonical(request)), cards=rows,
                links=[e for e in graph['links'] if e['from'] in selected and e['to'] in selected],
                disposition='needs_review' if reasons else 'context_ready', issues=reasons,
                truth_status_changed=False, limits=LIMITS)


def validate_policy(policy):
    k.obj(policy, {'schema', 'profiles', 'machine_checkers'})
    k.require(policy['schema'] == 'geek-work-review-policy-1', 'invalid_input:policy_schema')
    k.require(type(policy['profiles']) is list and len(policy['profiles']) <= 32 and
              type(policy['machine_checkers']) is list and len(policy['machine_checkers']) <= 32,
              'resource_limit:policy')
    seen = set()
    for p in policy['profiles']:
        k.obj(p, {'profile', 'task_classes', 'basis'})
        pid = profile_id(p['profile'])
        k.require(pid not in seen and k.strings(p['task_classes'], True) and
                  type(p['basis']) is str and p['basis'].strip(), 'invalid_input:profile_policy')
        seen.add(pid)
    seen = set()
    for checker in policy['machine_checkers']:
        k.obj(checker, {'sha256', 'task_classes', 'basis'})
        sha(checker['sha256'])
        k.require(checker['sha256'] not in seen and k.strings(checker['task_classes'], True) and
                  type(checker['basis']) is str and checker['basis'].strip(), 'invalid_input:checker_policy')
        seen.add(checker['sha256'])


def qualify(policy, attempt, root):
    """Transport observations are caller supplied; no model can grant itself capability here."""
    validate_policy(policy)
    k.obj(attempt, {'schema', 'policy_sha256', 'task_class', 'kind', 'expected_profile',
                    'observed_profile', 'artifact_sha256', 'verifier_receipt'})
    k.require(attempt['schema'] == 'geek-work-review-attempt-1', 'invalid_input:attempt_schema')
    sha(attempt['policy_sha256']); sha(attempt['artifact_sha256'])
    k.require(type(attempt['task_class']) is str and attempt['task_class'].strip(), 'invalid_input:task_class')
    k.require(attempt['kind'] in {'model_review', 'machine_check'}, 'invalid_input:review_kind')
    expected = profile_id(attempt['expected_profile']) if attempt['expected_profile'] is not None else None
    observed = profile_id(attempt['observed_profile']) if attempt['observed_profile'] is not None else None
    transition = 'unknown' if expected is None or observed is None else 'same' if expected == observed else 'changed'
    issues = []
    if k.digest(k.canonical(policy)) != attempt['policy_sha256']: issues.append('policy_changed')
    if attempt['kind'] == 'model_review':
        k.require(attempt['verifier_receipt'] is None, 'invalid_input:model_verifier_receipt')
        if transition != 'same': issues.append('profile_' + transition)
        if not any(profile_id(p['profile']) == observed and attempt['task_class'] in p['task_classes']
                   for p in policy['profiles']):
            issues.append('profile_not_qualified_for_task')
    else:
        # Model changes do not revoke a separately checked mathematical artifact.
        binding = attempt['verifier_receipt']
        if binding is None:
            issues.append('verifier_missing')
        else:
            k.obj(binding, {'path', 'sha256'})
            check = file_check(root, binding['path'], binding['sha256'])
            if check['state'] != 'matched': issues.append('verifier_' + check['state'])
            else:
                receipt = k.load(root / binding['path'])
                k.obj(receipt, {'schema', 'artifact_sha256', 'checker_sha256', 'task_class', 'result'})
                sha(receipt['artifact_sha256']); sha(receipt['checker_sha256'])
                k.require(receipt['schema'] == 'geek-work-machine-receipt-1' and
                          receipt['result'] in {'pass', 'reject', 'error'}, 'invalid_input:verifier_receipt')
                if receipt['artifact_sha256'] != attempt['artifact_sha256']: issues.append('artifact_mismatch')
                if receipt['task_class'] != attempt['task_class']: issues.append('task_class_mismatch')
                if receipt['result'] != 'pass': issues.append('verifier_' + receipt['result'])
                if not any(c['sha256'] == receipt['checker_sha256'] and
                           attempt['task_class'] in c['task_classes'] for c in policy['machine_checkers']):
                    issues.append('checker_not_qualified_for_task')
    return dict(schema='geek-work-review-eligibility-1',
                disposition='blocked' if issues else 'eligible_for_review', issues=issues,
                transition=transition, attempt_sha256=k.digest(k.canonical(attempt)),
                policy_sha256=k.digest(k.canonical(policy)), accepted_result=False, limits=LIMITS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    r = subs.add_parser('retrieve'); r.add_argument('graph', type=Path); r.add_argument('request', type=Path)
    q = subs.add_parser('qualify'); q.add_argument('policy', type=Path); q.add_argument('attempt', type=Path)
    for p in (r, q):
        p.add_argument('--root', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'retrieve': result = retrieve(k.load(args.graph), args.root, k.load(args.request))
        else: result = qualify(k.load(args.policy), k.load(args.attempt), args.root)
        k.write_new(args.output, k.canonical(result) + b'\n')
        return 2 if result['disposition'] in {'blocked', 'needs_review'} else 0
    except (k.Refusal, OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({'status': 'rejected', 'reason': str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
