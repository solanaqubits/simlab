#!/usr/bin/env python3
"""Replay the pinned, source-only orbit pilot. No Lean, Git or network execution."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
import geek_work_claim_transport as t

CASES = {'preserved': 'contract_preserved', 'without-noise-bound': 'review_required',
         'strict-upper-bound': 'review_required', 'unaudited-proof-reference': 'review_required',
         'invalid-quote': 'invalid_input'}


def replay(root, expected_manifest_sha):
    t.claims.digest(expected_manifest_sha)
    raw = t.claims.read_source(root, 'manifest.json')
    t.m.require(t.m.sha(raw) == expected_manifest_sha, 'pilot manifest anchor mismatch')
    manifest = t.strict_json(raw)
    expected_files = {'plan.json'} | {
        'source-bundle/'+name for name in ('manifest.json', 'map.json', 'document-signature.txt',
                                          'material-lean-source.txt', 'report.json', 'review.html')}
    expected_files |= {folder+'/'+name+'.json' for name in CASES for folder in ('candidates','reports')}
    t.m.require(set(manifest['files']) == expected_files, 'pilot file selection mismatch')
    for name, expected in manifest['files'].items():
        t.m.require(t.m.sha(t.claims.read_source(root, name)) == expected, 'pilot file hash: '+name)
    plan_raw = t.claims.read_source(root, 'plan.json')
    results = []
    for name, status in CASES.items():
        result = t.check(root/'source-bundle', manifest['source_bundle_sha256'], plan_raw,
                         manifest['plan_sha256'], t.claims.read_source(root, 'candidates/'+name+'.json'))
        t.m.require(result['status'] == status, 'unexpected status: '+name)
        t.m.require(all(result[flag] is False for flag in t.FLAGS), 'assurance escalation')
        t.m.require(t.m.encoded(result) == t.claims.read_source(root, 'reports/'+name+'.json'),
                    'report reproduction mismatch: '+name)
        results.append(dict(case=name, status=status))
    return dict(status='reproduced', cases=results, reported_evidence_state='source_only',
                **{flag:False for flag in t.FLAGS})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest-sha256', required=True)
    args = parser.parse_args()
    try:
        result = replay(Path(__file__).resolve().parent, args.manifest_sha256)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, 'Pilot refused: '+str(error)+'\n')
    print(t.m.encoded(result).decode(), end='')


if __name__ == '__main__':
    main()
