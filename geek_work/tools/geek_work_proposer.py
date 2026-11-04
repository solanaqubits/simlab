#!/usr/bin/env python3
"""Isolated single-file proposer and host-controlled handoff to frozen evaluation."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

import geek_work_protected as g

ev = g.ev
MAX_SOURCE = 32768
SCHEMA = 'geek-work-proposer-plan-1'


def pins():
    return dict(g.pins(), **{Path(__file__).name: ev.digest(Path(__file__).read_bytes())})


def source_text(data):
    g.require(isinstance(data, bytes) and 0 < len(data) <= MAX_SOURCE, 'source_size')
    text = data.decode('utf-8')
    g.require('\x00' not in text, 'source_nul')
    return text


def plan(corpus, baseline, proposer, task, image, interpreter='/usr/local/bin/python3',
         repetitions=2, evaluation_limits=None, proposal_limits=None):
    source_text(baseline)
    g.require(isinstance(proposer, bytes) and 0 < len(proposer) <= g.MAX_FILE, 'proposer_size')
    g.require(isinstance(task, str) and task.strip() and len(task.encode('utf-8')) <= 8192, 'task_size')
    limits = dict(proposal_limits if proposal_limits is not None else
                  dict(g.DEFAULT_LIMITS, wall_time_ms=10000, total_wall_time_ms=30000, output_bytes=262144))
    g.validate_limits(limits)
    evaluation = g.make_plan(corpus, baseline, image, interpreter, repetitions, evaluation_limits)
    result = dict(schema=SCHEMA, evaluation=evaluation, proposer_sha256=ev.digest(proposer),
                task=task, proposal_limits=limits, tools=pins(),
                output_contract='one_utf8_candidate.py_no_links_no_metadata', max_candidate_bytes=MAX_SOURCE)
    g.require(len(ev.encoded(result)) <= g.MAX_FILE, 'plan_size')
    return result


def validate(p, baseline, proposer, expected_sha):
    g.require(ev.digest(ev.encoded(p)) == expected_sha, 'expected_plan_mismatch')
    e = p['evaluation']
    g.require(p == plan(e['corpus'], baseline, proposer, p['task'], e['image_id'], e['interpreter'],
                       e['repetitions'], e['limits'], p['proposal_limits']), 'proposal_plan_drift')


def public_request(p, baseline):
    """Explicit allowlist: no gold, evaluator, plan, host paths or evaluation feedback."""
    g.require(ev.digest(baseline) == p['evaluation']['candidate_sha256'], 'baseline_changed')
    return dict(schema='geek-work-proposer-request-1', task=p['task'],
                baseline=dict(path='candidate.py', sha256=ev.digest(baseline), content=source_text(baseline)),
                output_contract=dict(schema='geek-work-proposal-1', allowed_paths=['candidate.py'],
                                     max_bytes=MAX_SOURCE, files_count=1))


def decode_proposal(raw, baseline_sha):
    doc = g.parse(raw)
    g.require(isinstance(doc, dict) and set(doc) == {'schema', 'baseline_sha256', 'files'}, 'proposal_fields')
    g.require(doc['schema'] == 'geek-work-proposal-1' and doc['baseline_sha256'] == baseline_sha,
              'proposal_baseline_or_schema')
    g.require(isinstance(doc['files'], list) and len(doc['files']) == 1, 'proposal_file_count')
    f = doc['files'][0]
    g.require(isinstance(f, dict) and set(f) == {'path', 'content'} and
              f['path'] == 'candidate.py' and isinstance(f['content'], str), 'proposal_file_contract')
    data = f['content'].encode('utf-8'); source_text(data)
    return data


def classify(result, audit, baseline_sha):
    try:
        # Reuse the existing process/cleanup/JSON validity gate, without a gold verdict.
        expected = g.parse(result['stdout'])
    except (ValueError, UnicodeError, RecursionError):
        expected = None
    status = g.verdict(result, audit, expected)
    if status != 'PASS':
        return status, None
    try:
        return 'PROPOSAL_READY', decode_proposal(result['stdout'], baseline_sha)
    except (ValueError, UnicodeError, TypeError, RecursionError):
        return 'INVALID_PROPOSAL', None


def tree_hashes(root):
    result = {}
    for f in sorted(Path(root).rglob('*')):
        g.require(not f.is_symlink(), 'bundle_symlink')
        if f.is_dir():
            continue
        g.require(f.is_file(), 'bundle_special_file')
        rel = f.relative_to(root).as_posix()
        if rel == 'seal.json':
            continue
        result[rel] = ev.digest(g.blob(f))
    return result


def seal(root):
    ev.write(Path(root) / 'seal.json', dict(schema='geek-work-proposer-seal-1', files=tree_hashes(root)))


def check_seal(root):
    doc = g.parse(g.blob(Path(root) / 'seal.json'))
    g.require(doc == dict(schema='geek-work-proposer-seal-1', files=tree_hashes(root)), 'seal_changed')


def proposal_ledger(receipt):
    ready = receipt['status'] == 'PROPOSAL_READY'
    task = dict(task_id=receipt['run_id'] + ':proposal', outcome='accepted' if ready else 'rejected',
                attempts_count=1, acceptance=dict(kind='machine_check', evidence=[dict(path='receipt.json',
                sha256=ev.digest(ev.encoded(receipt)))]) if ready else None,
                attempts=[dict(attempt_id=1, model_profile=None, model_transition='initial',
                    token_usage=None, monetary_cost=None, verification_wall_time_ms=receipt['wall_time_ms'],
                    failure_classes=[] if ready else [receipt['status']], human_interventions=None)])
    doc = dict(schema='geek-work-ledger-1', currency='USD', cost_scope='attempt_including_verification',
               result_unit='proposal_protocol_only', tasks=[task])
    g.ledger.validate(doc)
    return doc


def propose(p, baseline, proposer, expected_sha, output, engine=None):
    validate(p, baseline, proposer, expected_sha)
    root = Path(output).absolute(); root.mkdir(parents=True, exist_ok=False, mode=0o700)
    ev.write(root / 'plan.json', p)
    (root / 'baseline.py').write_bytes(baseline)
    (root / 'proposer.py').write_bytes(proposer)
    for name in ('baseline.py', 'proposer.py'): (root / name).chmod(0o444)
    request = public_request(p, baseline); ev.write(root / 'request.json', request)
    runtime = dict(image_id=p['evaluation']['image_id'], interpreter=p['evaluation']['interpreter'],
                   limits=p['proposal_limits'])
    kind = 'container' if engine is None else 'fixture'
    engine = g.Docker() if engine is None else engine
    started = time.monotonic_ns()
    environment = engine.preflight(runtime)
    remaining = runtime['limits']['total_wall_time_ms'] - (time.monotonic_ns() - started) // 1000000
    g.require(remaining > 0, 'proposal_budget_before_start')
    result, audit = engine.execute(runtime, root / 'proposer.py', request,
                                   min(remaining, runtime['limits']['wall_time_ms']))
    for name in ('stdout', 'stderr'): (root / name).write_bytes(result[name])
    status, candidate = classify(result, audit, ev.digest(baseline))
    drift = pins() != p['tools'] or g.blob(root / 'baseline.py') != baseline or g.blob(root / 'proposer.py') != proposer
    elapsed = (time.monotonic_ns() - started) // 1000000
    if drift: status = 'SOURCE_DRIFT'
    elif elapsed > runtime['limits']['total_wall_time_ms']: status = 'PROPOSAL_BUDGET_EXCEEDED'
    if status == 'PROPOSAL_READY':
        (root / 'candidate.py').write_bytes(candidate); (root / 'candidate.py').chmod(0o444)
    receipt = dict(schema='geek-work-proposer-receipt-1', run_id=uuid.uuid4().hex,
                   plan_sha256=expected_sha, status=status, execution_kind=kind, audit=audit,
                   process={k: v for k, v in result.items() if k not in ('stdout', 'stderr')},
                   wall_time_ms=elapsed, environment=environment, source_drift=drift,
                   candidate_sha256=ev.digest(candidate) if status == 'PROPOSAL_READY' else None,
                   provider_calls_by_harness=0, model_invocations_inside_proposer=None, acceptance_scope='Only proposal syntax/provenance; candidate not evaluated')
    ev.write(root / 'receipt.json', receipt); ev.write(root / 'ledger.json', proposal_ledger(receipt)); seal(root)
    return receipt


def verify_proposal(root, expected_sha):
    root = Path(root); check_seal(root)
    p = g.parse(g.blob(root / 'plan.json')); baseline = g.blob(root / 'baseline.py')
    validate(p, baseline, g.blob(root / 'proposer.py'), expected_sha)
    g.require(g.parse(g.blob(root / 'request.json')) == public_request(p, baseline), 'public_request_changed')
    r = g.parse(g.blob(root / 'receipt.json'))
    g.require(r['schema'] == 'geek-work-proposer-receipt-1' and r['plan_sha256'] == expected_sha, 'receipt_plan')
    g.require(r['execution_kind'] in ('container', 'fixture'), 'execution_kind')
    g.require(type(r['source_drift']) is bool and type(r['wall_time_ms']) is int and r['wall_time_ms'] >= 0,
              'receipt_telemetry')
    result = dict(r['process'], stdout=g.blob(root / 'stdout'), stderr=g.blob(root / 'stderr'))
    if r['execution_kind'] == 'container' and r['audit']['config_checked']:
        runtime = dict(p['evaluation'], limits=p['proposal_limits'])
        g.Docker().check_isolation(r['audit']['configuration'], runtime, Path(r['audit']['snapshot_host_path']))
    status, candidate = classify(result, r['audit'], ev.digest(baseline))
    if r['source_drift']: status = 'SOURCE_DRIFT'
    elif r['wall_time_ms'] > p['proposal_limits']['total_wall_time_ms']: status = 'PROPOSAL_BUDGET_EXCEEDED'
    g.require(r['status'] == status, 'proposal_verdict_changed')
    expected = {'plan.json', 'baseline.py', 'proposer.py', 'request.json', 'stdout', 'stderr',
                'receipt.json', 'ledger.json', 'seal.json'}
    if status == 'PROPOSAL_READY':
        expected.add('candidate.py')
        g.require(g.blob(root / 'candidate.py') == candidate and r['candidate_sha256'] == ev.digest(candidate),
                  'candidate_changed')
    else:
        g.require(r['candidate_sha256'] is None, 'rejected_candidate_hash')
    g.require({f.name for f in root.iterdir()} == expected, 'proposal_artifact_set')
    g.require(g.parse(g.blob(root / 'ledger.json')) == proposal_ledger(r), 'proposal_ledger_changed')
    return r


def evaluation_plans(proposal, expected_sha):
    r = verify_proposal(proposal, expected_sha)
    g.require(r['status'] == 'PROPOSAL_READY', 'proposal_not_ready')
    root = Path(proposal); p = g.parse(g.blob(root / 'plan.json')); e = p['evaluation']
    baseline, candidate = g.blob(root / 'baseline.py'), g.blob(root / 'candidate.py')
    cp = g.make_plan(e['corpus'], candidate, e['image_id'], e['interpreter'], e['repetitions'], e['limits'])
    return p, baseline, candidate, e, cp


def evaluation_report(root, expected_sha):
    root = Path(root)
    p, baseline, candidate, bp, cp = evaluation_plans(root / 'proposal', expected_sha)
    bsha, csha = [ev.digest(ev.encoded(x)) for x in (bp, cp)]
    # An independently changed trial plan cannot redefine acceptance.
    for name, expected in [('baseline', bp), ('candidate', cp)]:
        g.require(g.parse(g.blob(root / name / 'plan.json')) == expected, 'evaluation_plan_changed')
    comparison = g.compare(root / 'baseline', root / 'candidate', bsha, csha)
    proposer = verify_proposal(root / 'proposal', expected_sha)
    costs = dict(proposal_protocol=g.ledger.summarize([g.parse(g.blob(root / 'proposal/ledger.json'))]),
                 case_verification=g.ledger.summarize([g.parse(g.blob(root / name / 'ledger.json'))
                                                      for name in ('baseline', 'candidate')]))
    return dict(schema='geek-work-proposal-evaluation-1', proposal_plan_sha256=expected_sha,
                proposal_receipt_sha256=ev.digest(g.blob(root / 'proposal/receipt.json')),
                baseline_plan_sha256=bsha, candidate_plan_sha256=csha,
                status='CORRECTNESS_PRESERVED' if comparison['correctness_preserved'] else 'EVALUATION_FAILED',
                comparison=comparison, cost_by_result_unit=costs,
                proposer_execution_kind=proposer['execution_kind'], automatic_promotion=False,
                limits='Finite frozen corpus, trusted host/runtime; no model competence, speedup, RSI or scientific claim')


def evaluate(proposal, expected_sha, output, engine=None):
    p, baseline, candidate, bp, cp = evaluation_plans(proposal, expected_sha)
    root = Path(output).resolve()
    g.require(not root.is_relative_to(Path(proposal).resolve()), 'output_inside_proposal')
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    shutil.copytree(proposal, root / 'proposal', symlinks=False)
    verify_proposal(root / 'proposal', expected_sha)
    for name, code, trial_plan in [('baseline', baseline, bp), ('candidate', candidate, cp)]:
        result = g.run(trial_plan, code, root / name, ev.digest(ev.encoded(trial_plan)), engine=engine)
        g.require(all(t['audit']['cleanup_confirmed'] and t['process']['issue'] != 'INFRA_ERROR'
                      for t in result['trials']), 'evaluation_infrastructure_failure')
    report = evaluation_report(root, expected_sha)
    ev.write(root / 'report.json', report); seal(root)
    return report


def verify_evaluation(root, expected_sha):
    root = Path(root); check_seal(root)
    g.require({x.name for x in root.iterdir()} == {'proposal', 'baseline', 'candidate', 'report.json', 'seal.json'},
              'evaluation_artifact_set')
    report = evaluation_report(root, expected_sha)
    g.require(g.parse(g.blob(root / 'report.json')) == report, 'evaluation_report_changed')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare')
    for name in ('corpus', 'baseline', 'proposer', 'task', 'output'):
        prepare.add_argument('--' + name, type=Path, required=True)
    prepare.add_argument('--image-id', required=True); prepare.add_argument('--interpreter', default='/usr/local/bin/python3')
    prepare.add_argument('--repetitions', type=int, default=2)
    prepare.add_argument('--proposal-limits', type=Path); prepare.add_argument('--evaluation-limits', type=Path)
    prop = sub.add_parser('propose')
    for name in ('plan', 'baseline', 'proposer', 'output'): prop.add_argument('--' + name, type=Path, required=True)
    prop.add_argument('--expected-plan-sha256', required=True)
    for name in ('verify-proposal', 'evaluate', 'verify-evaluation'):
        cmd = sub.add_parser(name); cmd.add_argument('--bundle', type=Path, required=True)
        cmd.add_argument('--expected-plan-sha256', required=True)
        if name == 'evaluate': cmd.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            p = plan(g.parse(g.blob(args.corpus)), g.blob(args.baseline), g.blob(args.proposer),
                     g.blob(args.task).decode('utf-8'), args.image_id, args.interpreter, args.repetitions,
                     g.parse(g.blob(args.evaluation_limits)) if args.evaluation_limits else None,
                     g.parse(g.blob(args.proposal_limits)) if args.proposal_limits else None)
            ev.write(args.output, p); result = dict(plan_sha256=ev.digest(ev.encoded(p)))
        elif args.command == 'propose':
            result = propose(g.parse(g.blob(args.plan)), g.blob(args.baseline), g.blob(args.proposer),
                             args.expected_plan_sha256, args.output)
        elif args.command == 'evaluate':
            result = evaluate(args.bundle, args.expected_plan_sha256, args.output)
        elif args.command == 'verify-proposal': result = verify_proposal(args.bundle, args.expected_plan_sha256)
        else: result = verify_evaluation(args.bundle, args.expected_plan_sha256)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get('status', 'PROPOSAL_READY') in ('PROPOSAL_READY', 'CORRECTNESS_PRESERVED') else 1
    except (ValueError, OSError, KeyError, TypeError, RecursionError, subprocess.SubprocessError) as exc:
        print(json.dumps(dict(status='refused', reason=str(exc)), ensure_ascii=False)); return 2


if __name__ == '__main__': sys.exit(main())
