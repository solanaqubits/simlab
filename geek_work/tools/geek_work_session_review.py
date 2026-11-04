#!/usr/bin/env python3
"""Prepare and check session annotations offline; never attest model identity or promote gold."""
import argparse
import json
from pathlib import Path
import sys

import geek_work_model_review as base
import geek_work_annotations as annotation
import knowledge as k

MODEL = 'gpt-6-luna'


def pins():
    return {**base.pins(), Path(__file__).name: k.digest(Path(__file__).read_bytes())}


def prepare(packet, graph, root):
    return dict(schema='geek-work-session-review-plan-1', packet=packet,
                requested_profile=dict(model_id=MODEL, configuration=dict(
                    transport='codex-agent-session', reasoning_effort='medium',
                    temperature=None, seed=None)),
                system=base.SYSTEM, response_schema=base.SCHEMA,
                requests=base.requests_for(packet, graph, root), tool_pins=pins(),
                execution=dict(automatic_launch=False, max_cases=6,
                    hard_token_budget_enforced=False, cost_budget_enforced=False),
                scope='Provisional annotation only; no automatic gold or graph promotion')


def check(plan, anchor, responses, graph, root):
    k.require(k.digest(k.canonical(plan)) == anchor, 'plan_anchor')
    k.require(plan == prepare(plan['packet'], graph, root), 'plan_drift')
    k.obj(responses, {'schema', 'plan_sha256', 'records'})
    k.require(responses['schema'] == 'geek-work-session-responses-1', 'response_schema')
    k.require(responses['plan_sha256'] == anchor, 'response_plan_mismatch')
    records = responses['records']
    k.require(type(records) is list and len(records) <= len(plan['requests']), 'record_limit')
    by_id = {x['case_id']: x for x in plan['requests']}
    seen = set()
    review = annotation.template(plan['packet'])
    review['reviewer'].update(id='session-provisional-reviewer', kind='model',
        expected_profile=plan['requested_profile'], observed_profile=None,
        independence_note='Separate session requested. Model identity, independence and semantic accuracy not attested by an imported response.')
    decisions = {x['case_id']: x for x in review['decisions']}
    for row in records:
        k.obj(row, {'case_id', 'request_sha256', 'response'})
        cid = row['case_id']
        k.require(type(cid) is str and cid in by_id and cid not in seen, 'case_id')
        seen.add(cid)
        request = by_id[cid]['request']
        k.require(row['request_sha256'] == k.digest(k.canonical(request)), 'request_anchor')
        value = row['response']
        k.obj(value, {'label', 'rationale', 'citations'})
        k.require(value['label'] is None or type(value['label']) is bool, 'label_type')
        k.require(type(value['rationale']) is str and 0 < len(value['rationale'].strip()) <= 2048, 'rationale')
        k.require(type(value['citations']) is list and 1 <= len(value['citations']) <= 6, 'citation_count')
        converted = dict(accept=value['label'] is True, failure_classes=[] if value['label'] is True else ['missing_premise'],
                         reason=value['rationale'], evidence=value['citations'])
        errors = base.structured.check_request(dict(structured_response=converted), request)
        k.require(not errors, 'invalid_citation')
        decisions[cid].update(expected_with_memory=value['label'], rationale=value['rationale'], citations=value['citations'])
    # No observed profile or policy is invented from a model's own text.
    assessment = annotation.assess(plan['packet'], review, graph, root)
    return dict(schema='geek-work-session-review-check-1', plan_sha256=anchor,
                responses_sha256=k.digest(k.canonical(responses)),
                status='needs_review', imported_records=len(records),
                complete=len(records) == len(by_id), review=review, assessment=assessment,
                token_usage=None, actual_monetary_cost=None, model_identity_verified=False,
                independence_verified=False, accepted_as_gold=False,
                accepted_into_knowledge_graph=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'check'])
    p.add_argument('input', type=Path)
    p.add_argument('--graph', type=Path, required=True)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--responses', type=Path)
    p.add_argument('--expected-plan-sha256')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    try:
        graph = k.load(a.graph)
        if a.action == 'prepare':
            result = prepare(k.load(a.input), graph, a.root)
        else:
            k.require(a.responses is not None and a.expected_plan_sha256 is not None, 'check_arguments')
            result = check(k.load(a.input), a.expected_plan_sha256, k.load(a.responses), graph, a.root)
        k.write_new(a.output, k.canonical(result) + b'\n')
        print(json.dumps(dict(output=str(a.output), canonical_sha256=k.digest(k.canonical(result)))))
    except (k.Refusal, OSError, ValueError, TypeError, KeyError) as e:
        print(json.dumps(dict(status='refused', reason=str(e))))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
