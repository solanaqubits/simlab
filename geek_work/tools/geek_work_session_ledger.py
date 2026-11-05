#!/usr/bin/env python3
"""Host-recorded reservations and responses; not a provider attestation or cost meter."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile
import time

import geek_work_session_review as review
import knowledge as k

LIMITS = dict(max_attempts=6, max_payload_bytes=100000, max_response_bytes=8192)


def digest(value):
    return k.digest(k.canonical(value))


def tool_sha():
    return k.digest(Path(__file__).read_bytes())


def payload(plan, request):
    return dict(system=plan['system'], response_schema=plan['response_schema'], request=request)


def empty(plan):
    return dict(schema='geek-work-session-responses-1', plan_sha256=digest(plan), records=[])


def initial(plan, anchor, graph, root):
    review.check(plan, anchor, empty(plan), graph, root)
    return dict(schema='geek-work-session-ledger-1', plan=plan, plan_sha256=anchor,
                ledger_tool_sha256=tool_sha(), limits=LIMITS.copy(), attempts=[])


def validate(state, graph, root):
    k.obj(state, {'schema', 'plan', 'plan_sha256', 'ledger_tool_sha256', 'limits', 'attempts'})
    k.require(state['schema'] == 'geek-work-session-ledger-1', 'ledger_schema')
    k.require(state['ledger_tool_sha256'] == tool_sha(), 'ledger_tool_changed')
    k.require(state['limits'] == LIMITS, 'limits_changed')
    plan = state['plan']
    review.check(plan, state['plan_sha256'], empty(plan), graph, root)
    attempts = state['attempts']
    k.require(type(attempts) is list and len(attempts) <= LIMITS['max_attempts'], 'attempt_limit')
    requests = {x['case_id']: x['request'] for x in plan['requests']}
    seen = set(); total = 0
    for a in attempts:
        k.obj(a, {'case_id', 'request_sha256', 'requested_profile', 'reserved_at_ns', 'finished_at_ns',
                  'agent_ref', 'outcome', 'raw_response'})
        cid = a['case_id']
        k.require(type(cid) is str and cid in requests and cid not in seen, 'case_already_reserved_or_unknown')
        seen.add(cid)
        k.require(a['request_sha256'] == digest(requests[cid]), 'request_anchor')
        k.require(a['requested_profile'] == plan['requested_profile'], 'requested_model_changed')
        k.require(type(a['reserved_at_ns']) is int and a['reserved_at_ns'] > 0, 'reserved_time')
        k.require(a['outcome'] in ('reserved', 'response', 'failed'), 'outcome')
        if a['outcome'] == 'reserved':
            k.require(all(a[x] is None for x in ('finished_at_ns', 'agent_ref', 'raw_response')), 'pending_fields')
        else:
            k.require(type(a['finished_at_ns']) is int and a['finished_at_ns'] >= a['reserved_at_ns'], 'finished_time')
            k.require(type(a['agent_ref']) is str and 0 < len(a['agent_ref']) <= 256, 'agent_ref')
            k.require(type(a['raw_response']) is str and len(a['raw_response'].encode()) <= 65536, 'raw_limit')
        total += len(k.canonical(payload(plan, requests[cid])))
    k.require(total <= LIMITS['max_payload_bytes'], 'payload_byte_budget')
    return requests


def reserve(state, cid, profile, graph, root):
    requests = validate(state, graph, root)
    k.require(profile == state['plan']['requested_profile'], 'requested_model_changed')
    k.require(cid in requests and all(a['case_id'] != cid for a in state['attempts']), 'case_already_reserved_or_unknown')
    state['attempts'].append(dict(case_id=cid, request_sha256=digest(requests[cid]),
        requested_profile=profile, reserved_at_ns=time.time_ns(), finished_at_ns=None,
        agent_ref=None, outcome='reserved', raw_response=None))
    validate(state, graph, root)


def finish(state, cid, agent_ref, outcome, raw, graph, root):
    validate(state, graph, root)
    matches = [a for a in state['attempts'] if a['case_id'] == cid]
    k.require(len(matches) == 1 and matches[0]['outcome'] == 'reserved', 'no_pending_reservation')
    k.require(outcome in ('response', 'failed'), 'finish_outcome')
    matches[0].update(finished_at_ns=time.time_ns(), agent_ref=agent_ref, outcome=outcome, raw_response=raw)
    validate(state, graph, root)


def report(state, graph, root):
    validate(state, graph, root)
    responses = empty(state['plan']); rows = []
    for a in state['attempts']:
        errors = []; elapsed = None; verify_ns = time.monotonic_ns()
        if a['outcome'] != 'response':
            errors.append('pending' if a['outcome'] == 'reserved' else 'session_failed')
        else:
            if len(a['raw_response'].encode()) > LIMITS['max_response_bytes']:
                errors.append('response_byte_budget')
            try:
                value = k.strict_json(a['raw_response'].encode())
                row = dict(case_id=a['case_id'], request_sha256=a['request_sha256'], response=value)
                single = empty(state['plan']); single['records'] = [row]
                review.check(state['plan'], state['plan_sha256'], single, graph, root)
                if not errors: responses['records'].append(row)
            except (k.Refusal, ValueError, TypeError, KeyError) as e:
                errors.append(str(e))
        if a['finished_at_ns'] is not None:
            elapsed = (a['finished_at_ns'] - a['reserved_at_ns']) // 1000000
        rows.append(dict(case_id=a['case_id'], errors=errors,
            raw_response_sha256=k.digest(a['raw_response'].encode()) if a['raw_response'] is not None else None,
            reservation_to_record_ms=elapsed, verification_wall_time_ms=(time.monotonic_ns()-verify_ns)//1000000,
            token_usage=None, actual_monetary_cost=None, human_interventions=None))
    checked = review.check(state['plan'], state['plan_sha256'], responses, graph, root)
    return dict(schema='geek-work-session-ledger-report-1', ledger_sha256=digest(state),
        plan_sha256=state['plan_sha256'], attempts_count=len(rows), attempts=rows,
        responses=responses, response_check=checked, accepted_as_gold=False,
        cost_per_accepted_result=None, equal_budget_comparison_eligible=False,
        model_identity_verified=False, token_budget_enforced=False, monetary_budget_enforced=False,
        scope='Host-recorded events; wall interval includes coordination delay. Reservations bound this ledger only, not external calls or a modified host.')


@contextmanager
def locked(path):
    k.require(not path.is_symlink(), 'ledger_symlink')
    lock = path.with_suffix(path.suffix + '.lock')
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def save(path, value):
    # Caller holds the lock; fsync then replace prevents partial JSON after interruption.
    fd, name = tempfile.mkstemp(prefix='.ledger-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(k.canonical(value)+b'\n'); f.flush(); os.fsync(f.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(name): os.unlink(name)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['init', 'reserve', 'finish', 'report'])
    p.add_argument('--ledger', type=Path, required=True)
    p.add_argument('--graph', type=Path, required=True); p.add_argument('--root', type=Path, required=True)
    p.add_argument('--plan', type=Path); p.add_argument('--expected-plan-sha256')
    p.add_argument('--case-id'); p.add_argument('--agent-ref'); p.add_argument('--model', default=review.MODEL)
    p.add_argument('--outcome', choices=['response', 'failed'], default='response')
    p.add_argument('--raw', type=Path); p.add_argument('--output', type=Path)
    a = p.parse_args()
    try:
        graph = k.load(a.graph)
        with locked(a.ledger):
            if a.action == 'init':
                k.require(a.plan is not None and not a.ledger.exists(), 'init_requires_new_ledger')
                state = initial(k.load(a.plan), a.expected_plan_sha256, graph, a.root)
            else:
                state = k.load(a.ledger)
                if a.action == 'reserve':
                    profile = dict(state['plan']['requested_profile']); profile['model_id'] = a.model
                    reserve(state, a.case_id, profile, graph, a.root)
                elif a.action == 'finish':
                    k.require(a.raw is not None, 'raw_required')
                    finish(state, a.case_id, a.agent_ref, a.outcome, k.bounded(a.raw).decode(), graph, a.root)
                else:
                    k.require(a.output is not None, 'output_required')
                    k.write_new(a.output, k.canonical(report(state, graph, a.root))+b'\n')
            if a.action != 'report': save(a.ledger, state)
        print(json.dumps(dict(status='recorded', ledger_sha256=digest(state))))
    except (k.Refusal, OSError, ValueError, TypeError, KeyError) as e:
        print(json.dumps(dict(status='refused', reason=str(e)))); return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
