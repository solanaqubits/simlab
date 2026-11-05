"""Validate reported task telemetry; never infer unavailable usage or currency rates."""
from decimal import Decimal, localcontext
import re


def require(ok, message):
    if not ok:
        raise ValueError(message)


def count(value):
    require(value is None or (type(value) is int and value >= 0), 'Expected null or nonnegative integer')


def validate(doc):
    require(doc['schema'] == 'geek-work-ledger-1', 'Unknown ledger schema')
    require(re.fullmatch(r'[A-Z]{3}', doc['currency']) is not None, 'Currency required')
    require(doc['cost_scope'] == 'attempt_including_verification', 'Cost scope must include verification')
    require(isinstance(doc['tasks'], list), 'Tasks must be a list')
    seen = set()
    for task in doc['tasks']:
        tid = task['task_id']
        require(isinstance(tid, str) and tid.strip() and tid not in seen, 'Duplicate/empty task ID')
        seen.add(tid)
        require(task['outcome'] in ('accepted', 'rejected'), 'Task must have terminal outcome')
        attempts = task['attempts']
        require(isinstance(attempts, list) and len(attempts) > 0, 'Task needs attempts')
        require(type(task['attempts_count']) is int and task['attempts_count'] == len(attempts),
                'Attempt count mismatch')
        previous = None
        for i, a in enumerate(attempts):
            require(a['attempt_id'] == i + 1 and type(a['attempt_id']) is int, 'Attempts must be sequential')
            profile = a['model_profile']
            require(profile is None or (isinstance(profile, dict) and
                    isinstance(profile.get('model_id'), str) and profile['model_id'].strip() and
                    isinstance(profile.get('configuration'), dict)), 'Invalid model profile')
            transition = a['model_transition']
            require(transition in ('initial', 'same', 'changed', 'downgrade', 'unknown'), 'Invalid model transition')
            require((i == 0) == (transition == 'initial'), 'Initial transition mismatch')
            if i and transition == 'same':
                require(profile is not None and profile == previous, 'Same model requires known identical profile')
            previous = profile
            usage = a['token_usage']
            require(usage is None or isinstance(usage, dict), 'Invalid token usage')
            if usage is not None:
                require(set(usage) == {'input_tokens', 'output_tokens'}, 'Token fields mismatch')
                for v in usage.values(): count(v)
            cost = a['monetary_cost']
            require(cost is None or (isinstance(cost, str) and
                    re.fullmatch(r'\d{1,15}(\.\d{1,12})?', cost) is not None),
                    'Cost must be null or nonnegative decimal string')
            count(a['verification_wall_time_ms'])
            require(isinstance(a['failure_classes'], list) and
                    all(isinstance(c, str) and c.strip() for c in a['failure_classes']), 'Invalid failures')
            events = a['human_interventions']
            require(events is None or (isinstance(events, list) and all(
                isinstance(e, dict) and isinstance(e.get('type'), str) and e['type'].strip() and
                isinstance(e.get('description'), str) and e['description'].strip() for e in events)),
                'Invalid intervention events')
        acceptance = task['acceptance']
        if task['outcome'] == 'accepted':
            require(isinstance(acceptance, dict) and acceptance.get('kind') in
                    ('machine_check', 'human_review', 'independent_review'),
                    'Acceptance requires a checker/reviewer, not model self-report')
            require(isinstance(acceptance.get('evidence'), list) and acceptance['evidence'], 'Acceptance evidence required')
            if acceptance['kind'] != 'machine_check':
                require(isinstance(acceptance.get('reviewer'), str) and acceptance['reviewer'].strip(),
                        'Reviewer identity label required')
            for e in acceptance['evidence']:
                require(isinstance(e, dict) and isinstance(e.get('path'), str) and
                        isinstance(e.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', e['sha256']),
                        'Evidence needs path and SHA-256')
        else:
            require(acceptance is None, 'Rejected task cannot carry acceptance')
    return doc


def summarize(documents):
    with localcontext() as context:
        context.prec = 64
        return _summarize(documents)


def _summarize(documents):
    groups = {}
    tasks_seen = set()
    for doc in documents:
        validate(doc)
        g = groups.setdefault(doc['currency'], dict(tasks=0, accepted_results=0, attempts=0,
            known_cost_total=Decimal(0), unknown_cost_attempts=0, known_verification_wall_time_ms=0,
            unknown_verification_time_attempts=0, known_human_interventions=0,
            unknown_human_intervention_attempts=0, known_input_tokens=0, known_output_tokens=0,
            unknown_token_attempts=0))
        for task in doc['tasks']:
            require(task['task_id'] not in tasks_seen, 'Duplicate task across committed ledgers')
            tasks_seen.add(task['task_id']); g['tasks'] += 1
            g['accepted_results'] += task['outcome'] == 'accepted'
            for a in task['attempts']:
                g['attempts'] += 1
                if a['monetary_cost'] is None: g['unknown_cost_attempts'] += 1
                else: g['known_cost_total'] += Decimal(a['monetary_cost'])
                if a['verification_wall_time_ms'] is None: g['unknown_verification_time_attempts'] += 1
                else: g['known_verification_wall_time_ms'] += a['verification_wall_time_ms']
                if a['human_interventions'] is None: g['unknown_human_intervention_attempts'] += 1
                else: g['known_human_interventions'] += len(a['human_interventions'])
                usage = a['token_usage']
                if usage is None or any(v is None for v in usage.values()): g['unknown_token_attempts'] += 1
                if usage:
                    for k in ['input_tokens', 'output_tokens']:
                        if usage[k] is not None: g['known_' + k] += usage[k]
        # Verification time/interventions are not silently converted into money.
    for g in groups.values():
        total = g['known_cost_total']; complete = g['unknown_cost_attempts'] == 0
        g['cost_complete'] = complete
        g['total_cost'] = str(total) if complete else None
        g['cost_per_accepted_result'] = str(total / g['accepted_results']) if complete and g['accepted_results'] else None
        g['known_cost_total'] = str(total)
    return dict(schema='geek-work-cost-summary-1', by_currency=groups,
                scope='Only committed, explicitly reported task telemetry; no inferred human wage or historical backfill',
                division_precision=64,
                acceptance_authenticity_verified=False)
