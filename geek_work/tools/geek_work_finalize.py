"""Linux cooperative-writer transaction protocol. The registry rename is the commit point."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
import uuid

from chat_intake import read_source, verify
from geek_work_ledger import validate as validate_ledger, summarize, require


class FinalizeError(ValueError):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def load(path):
    return json.loads(read_source(Path(path)))


def state_identity(stream):
    path = Path(stream['current_queue']).resolve()
    return digest(encoded(dict(queue=str(path), queue_sha256=digest(read_source(path)),
        generation=stream.get('finalize_generation', 0), transaction=stream.get('current_transaction'))))


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def write_new(path, data):
    with path.open('xb') as f:
        f.write(data); f.flush(); os.fsync(f.fileno())


def checkpoint(phase):
    """Test seam for process-crash injection; not an exposed CLI option."""


def pinned(path, pins):
    path = Path(path)
    require(path.is_absolute(), 'References must be absolute paths')
    raw = read_source(path)
    h = digest(raw)
    key = str(path.resolve())
    require(key not in pins or pins[key] == h, 'Input changed while validating')
    pins[key] = h
    return raw


def check_manifest(path, pins):
    entries = {}
    for line in pinned(path, pins).decode('utf-8').splitlines():
        h, name = line.split(maxsplit=1)
        name = name.removeprefix('*')
        p = Path(name)
        require(not p.is_absolute() and '..' not in p.parts and name not in entries,
                'Unsafe or duplicate manifest entry')
        target = Path(path).parent / p
        require(re.fullmatch('[0-9a-f]{64}', h) and digest(pinned(target, pins)) == h,
                'Package manifest mismatch')
        entries[name] = h
    require(entries, 'Empty manifest')
    return {str((Path(path).parent / n).resolve()) for n in entries}


def check_edit_artifacts(ref, review, original, pins):
    # Metadata correction sidecars preserve the location of the original editorial artifacts.
    origin = Path(review.get('metadata_correction', {}).get('original_review', ref))
    output = Path(review.get('edited_output', str(origin.parent / 'edited.md')))
    journal = Path(review.get('edit_journal', str(origin.parent / 'edits.json')))
    raw = pinned(output, pins); patch = json.loads(pinned(journal, pins))
    require(patch['input_sha256'] == digest(original.encode('utf-8')) and
            patch['output_sha256'] == digest(raw), 'Editorial artifact hash mismatch')
    require(isinstance(patch['edits'], list), 'Missing editorial patch list')
    cursor = 0; rebuilt = []
    for edit in patch['edits']:
        lo, hi = edit['start_char'], edit['end_char']
        require(type(lo) is int and type(hi) is int and cursor <= lo < hi <= len(original),
                'Invalid or overlapping edit range')
        require(original[lo:hi] == edit['before'] and isinstance(edit['after'], str) and
                isinstance(edit['reason'], str) and edit['reason'].strip(), 'Invalid editorial patch')
        rebuilt.extend([original[cursor:lo], edit['after']]); cursor = hi
    rebuilt.append(original[cursor:])
    require(''.join(rebuilt).encode('utf-8') == raw, 'Editorial reconstruction mismatch')


def check_reviews(row, prep_path, prep, pins):
    refs = set(row.get('reviews', [])) | ({row['review']} if row.get('review') else set())
    records = [(p, json.loads(pinned(Path(p), pins))) for p in sorted(refs)]
    expected = {c['file']: c for c in prep['chunks']}
    for ref, review in records:
        for field, value in [('source_path', row['path']), ('source_sha256', row['sha256'])]:
            require(field not in review or review[field] == value, 'Review source mismatch')
        if review.get('chunk_path'):
            ch = expected.get(review['chunk_path'])
            require(ch is not None and review.get('chunk_sha256') == ch['sha256'], 'Review chunk hash mismatch')
        if not review.get('chunk_path'):
            check_edit_artifacts(ref, review, pinned(prep_path / 'cleaned.md', pins).decode('utf-8'), pins)
    for chunk in row.get('reviewed_chunks', []):
        content = pinned(prep_path / chunk, pins).decode('utf-8')
        windows = []
        for ref, r in records:
            if r.get('chunk_path') != chunk: continue
            interval = r.get('review_window_char_offsets')
            lo, hi = interval if interval is not None else (0, len(content))
            require(type(lo) is int and type(hi) is int and 0 <= lo < hi <= len(content),
                    'Invalid review window')
            require(r.get('chunk_chars') == hi - lo, 'Window character count mismatch')
            check_edit_artifacts(ref, r, content[lo:hi], pins)
            windows.append((lo, hi))
        cursor = 0
        for lo, hi in sorted(windows):
            require(lo == cursor, 'Review window gap or overlap')
            cursor = hi
        require(cursor == len(content), 'Incomplete reviewed chunk')
    # Historical whole-document records do not imply machine-verified semantic coverage.


def check_source_row(row, sources, store, pins):
    source = sources[row['path']]
    require(source['sha256'] == row['sha256'], 'Queue/inventory source mismatch')
    require(digest(pinned(store / source['snapshot'], pins)) == row['sha256'], 'Source snapshot mismatch')
    from geek_work_ranges import prepared_views, range_coverage
    preparations = {}
    for view in prepared_views(row):
        preparations[view['prepared']] = check_prepared_view(view, source, store, pins)
    range_coverage(row, preparations)


def check_prepared_view(row, source, store, pins):
    pp = Path(row['prepared']); prep = json.loads(pinned(pp / 'preparation.json', pins))
    require(prep['source']['snapshot'] == source['snapshot'], 'Preparation snapshot mismatch')
    for name in ['extracted.txt', 'cleaned.md'] + [c['file'] for c in prep['chunks']]:
        p = Path(name)
        require(not p.is_absolute() and '..' not in p.parts, 'Invalid prepared path')
        pinned(pp / p, pins)
    verify(store, pp)
    check_reviews(row, pp, prep, pins)
    return prep


def audit_queue(queue, store, stream_id='chat-intake-20261027'):
    """Read-only readiness check, using the same archive checks as finalize.

    Collects the first error per source, not an exhaustive diagnosis of that source.
    A valid result is not a commit, CAS reservation, or semantic acceptance.
    """
    from geek_work import queue_summary
    pins = {}; queue = Path(queue).resolve(); store = Path(store).resolve()
    q = json.loads(pinned(queue, pins))
    inv = json.loads(pinned(store / 'inventory.json', pins))
    sources = {r['path']: r for r in inv['files']}
    require(len(sources) == len(inv['files']), 'Duplicate source inventory rows')
    issues = []; checked = 0
    expected_errors = (ValueError, OSError, KeyError, TypeError)
    for row in q['items']:
        try:
            check_source_row(row, sources, store, pins)
            checked += 1
        except expected_errors as err:
            issues.append(dict(source=row.get('path'), error_type=type(err).__name__, detail=str(err)))
    summary = None
    try: summary = queue_summary(queue, stream_id)
    except expected_errors as err:
        issues.append(dict(source=None, error_type=type(err).__name__, detail=str(err)))
    for path, h in list(pins.items()):
        try: require(digest(read_source(Path(path))) == h, 'Input changed during readiness check')
        except expected_errors as err:
            issues.append(dict(source=None, path=path, error_type=type(err).__name__, detail=str(err)))
    return dict(schema='geek-work-queue-readiness-1', status='invalid' if issues else 'valid',
                queue=str(queue), queue_sha256=pins[str(queue)], batch=q.get('batch'),
                rows_checked=checked, rows_total=len(q['items']), issues=issues,
                diagnostic_scope='First failure per source; fix and rerun',
                summary=summary, input_hashes=pins, semantic_review=False, committed=False)


def validate_inputs(request, pins):
    from geek_work import queue_summary
    qpath = Path(request['queue']); ledger_path = Path(request['ledger'])
    q = json.loads(pinned(qpath, pins)); ledger = json.loads(pinned(ledger_path, pins))
    members = check_manifest(Path(request['manifest']), pins)
    require(str(qpath.resolve()) in members and str(ledger_path.resolve()) in members and
            str((Path(request['manifest']).parent / 'README.md').resolve()) in members,
            'Manifest must cover candidate queue, ledger and README.md')
    store = Path(request['store'])
    inv = json.loads(pinned(store / 'inventory.json', pins))
    sources = {r['path']: r for r in inv['files']}
    require(len(sources) == len(inv['files']), 'Duplicate source inventory rows')
    for row in q['items']: check_source_row(row, sources, store, pins)
    validate_ledger(ledger)
    for task in ledger['tasks']:
        if task['acceptance']:
            for evidence in task['acceptance']['evidence']:
                require(digest(pinned(Path(evidence['path']), pins)) == evidence['sha256'],
                        'Acceptance evidence mismatch')
    summary = queue_summary(qpath, request['stream'])
    return q, ledger, summary


def read_transaction(entry):
    receipt = Path(entry['receipt'])
    require(digest(read_source(receipt)) == entry['receipt_sha256'], 'Receipt hash mismatch')
    require(digest(read_source(receipt.parent / 'seal.json')) == entry['seal_sha256'], 'Seal hash mismatch')
    seal = load(receipt.parent / 'seal.json')
    require(set(seal) == {'queue.json', 'summary.json', 'receipt.json', 'ledger.json',
                          'inputs.json', 'request.json'}, 'Invalid transaction seal')
    for name, h in seal.items():
        require(digest(read_source(receipt.parent / name)) == h, 'Transaction seal mismatch')
    r = load(receipt); q = load(receipt.parent / 'queue.json'); s = load(receipt.parent / 'summary.json')
    require(r['queue_sha256'] == s['queue_sha256'] == seal['queue.json'], 'Queue binding mismatch')
    require(r['batch'] == s['batch'] == q['batch'], 'Batch binding mismatch')
    require(r['summary_sha256'] == seal['summary.json'] and r['ledger_sha256'] == seal['ledger.json'],
            'Summary/ledger binding mismatch')
    require(r['operation_id'] == entry['operation_id'] and r['fingerprint'] == entry['fingerprint'],
            'Transaction identity mismatch')
    return r, load(receipt.parent / 'ledger.json')


def ledger_report(registry, stream_id):
    doc = load(registry); stream = next(s for s in doc['streams'] if s['id'] == stream_id)
    history = stream.get('finalize_history', [])
    require(len({h['operation_id'] for h in history}) == len(history), 'Duplicate operation in history')
    result = summarize([read_transaction(h)[1] for h in history])
    result['committed_operations'] = len(history)
    result['registry_sha256'] = digest(read_source(registry))
    return result


def finalize(registry, request):
    registry = Path(registry).resolve()
    require(request['schema'] == 'geek-work-finalize-1', 'Invalid finalize schema')
    for key in ['operation_id', 'stream']:
        require(isinstance(request[key], str) and re.fullmatch('[A-Za-z0-9_-]{1,100}', request[key]), 'Invalid ID')
    for key in ['expected_state', 'expected_queue_sha256']:
        require(isinstance(request[key], str) and re.fullmatch('[0-9a-f]{64}', request[key]), 'Invalid CAS token')
    pins = {}
    # Hash mutable request payloads before looking up idempotency, without accepting them yet.
    hashes = {k: digest(pinned(Path(request[k]), pins)) for k in ['queue', 'ledger', 'manifest']}
    fingerprint = digest(encoded(dict(request=request, hashes=hashes)))
    lockpath = registry.parent / '.coordination.lock'
    with lockpath.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        registry_bytes = read_source(registry)
        doc = json.loads(registry_bytes)
        stream = next(s for s in doc['streams'] if s['id'] == request['stream'])
        history = stream.get('finalize_history', [])
        previous_ledgers = []
        for entry in history:
            receipt, old_ledger = read_transaction(entry)
            previous_ledgers.append(old_ledger)
            if entry['operation_id'] == request['operation_id']:
                if entry['fingerprint'] != fingerprint:
                    raise FinalizeError('OPERATION_ID_CONFLICT', 'Operation ID was used with different inputs')
                return dict(status='ALREADY_COMMITTED', receipt=entry['receipt'], data=receipt)
        current = Path(stream['current_queue'])
        if (state_identity(stream) != request['expected_state'] or
                digest(read_source(current)) != request['expected_queue_sha256']):
            raise FinalizeError('STALE_STATE_REJECTED', 'Queue state changed; no registry write performed')
        start = time.monotonic_ns()
        q, ledger, summary = validate_inputs(request, pins)
        oldq = load(current)
        require(digest(pinned(Path(q['previous_queue']), pins)) == digest(read_source(current)),
                'Candidate does not descend from current queue bytes')
        oldrows = {r['path']: r for r in oldq['items']}; newrows = {r['path']: r for r in q['items']}
        require(oldrows.keys() <= newrows.keys(), 'Candidate drops source records')
        for name, old in oldrows.items():
            require(old['sha256'] == newrows[name]['sha256'], 'Source replacement requires separate version migration')
            if old.get('prepared') == newrows[name].get('prepared'):
                require(set(old.get('reviewed_chunks', [])) <= set(newrows[name].get('reviewed_chunks', [])),
                        'Candidate loses reviewed chunks')
            if old.get('range_schema'):
                from geek_work_ranges import prepared_views
                before = {v['prepared']: v for v in prepared_views(old)}
                after = {v['prepared']: v for v in prepared_views(newrows[name])}
                require(before.keys() <= after.keys(), 'Candidate loses prepared ranges')
                for pp, view in before.items():
                    require(set(view.get('reviewed_chunks', [])) <=
                            set(after[pp].get('reviewed_chunks', [])),
                            'Candidate loses reviewed chunks in prior range')
            if old['stage'] == 'editorial_pilot_reviewed' and newrows[name]['stage'] != old['stage']:
                correction = newrows[name].get('status_correction', {})
                require(newrows[name]['stage'] == 'extraction_review_required' and
                        correction.get('previous_stage') == old['stage'] and
                        correction.get('new_stage') == newrows[name]['stage'] and
                        isinstance(correction.get('reason'), str) and correction['reason'].strip() and
                        isinstance(correction.get('evidence'), list) and correction['evidence'],
                        'Completed status correction requires explicit reason and pinned evidence')
                for evidence in correction['evidence']:
                    require(digest(pinned(Path(evidence['path']), pins)) == evidence['sha256'],
                            'Status correction evidence mismatch')
        totals = summarize(previous_ledgers + [ledger])  # Also rejects double accounting of task IDs.
        generation = stream.get('finalize_generation', 0) + 1
        txroot = registry.parent / 'geek-work-transactions' / request['stream']
        txroot.mkdir(parents=True, exist_ok=True)
        tx = txroot / (request['operation_id'] + '-' + uuid.uuid4().hex)
        tx.mkdir()
        queue_bytes = read_source(Path(request['queue']))
        summary['queue'] = str(tx / 'queue.json')
        summary_bytes = encoded(summary); ledger_bytes = encoded(ledger)
        receipt = dict(schema='geek-work-finalize-receipt-1', operation_id=request['operation_id'],
            fingerprint=fingerprint, stream=request['stream'], generation=generation,
            batch=q['batch'], queue_sha256=digest(queue_bytes), summary_sha256=digest(summary_bytes),
            ledger_sha256=digest(ledger_bytes), queue=str(tx / 'queue.json'),
            predecessor_state=request['expected_state'], cost_summary=totals,
            finalizer_check_wall_time_ms=(time.monotonic_ns() - start) // 1000000,
            commitment='Committed only when referenced by registry finalize_history', semantic_verification=False)
        payload = {'queue.json': queue_bytes, 'summary.json': summary_bytes,
                   'ledger.json': ledger_bytes, 'receipt.json': encoded(receipt),
                   'request.json': encoded(request), 'inputs.json': encoded(pins)}
        for name, raw in payload.items(): write_new(tx / name, raw)
        write_new(tx / 'seal.json', encoded({n: digest(b) for n, b in payload.items()}))
        sync_dir(tx); sync_dir(txroot); sync_dir(txroot.parent); sync_dir(registry.parent)
        checkpoint('prepared')
        for name, h in pins.items():
            require(digest(read_source(Path(name))) == h, 'Input changed before commit')
        require(read_source(registry) == registry_bytes, 'Noncooperating registry writer detected')
        entry = dict(operation_id=request['operation_id'], fingerprint=fingerprint,
                     receipt=str(tx / 'receipt.json'), receipt_sha256=digest(payload['receipt.json']),
                     seal_sha256=digest(read_source(tx / 'seal.json')))
        read_transaction(entry)
        stream.update(current_transaction=str(tx), current_queue=str(tx / 'queue.json'),
            current_summary=summary, finalize_generation=generation,
            finalize_history=history + [entry], current_receipt=entry,
            next_batch=q['next_batch'], latest_report=str(Path(request['manifest']).parent / 'README.md'))
        from geek_work import utc
        doc['updated_utc'] = utc()
        fd, temp = tempfile.mkstemp(prefix='.finalize-', suffix='.tmp', dir=registry.parent)
        with os.fdopen(fd, 'wb') as f:
            f.write(encoded(doc)); f.flush(); os.fsync(f.fileno())
        checkpoint('before_replace')
        os.replace(temp, registry)
        checkpoint('after_replace')
        sync_dir(registry.parent)
        return dict(status='COMMITTED', receipt=entry['receipt'], data=receipt)


def inspect_transactions(registry, stream_id):
    doc = load(registry); stream = next(s for s in doc['streams'] if s['id'] == stream_id)
    referenced = {str(Path(e['receipt']).parent) for e in stream.get('finalize_history', [])}
    for e in stream.get('finalize_history', []): read_transaction(e)
    root = Path(registry).resolve().parent / 'geek-work-transactions' / stream_id
    return dict(committed=sorted(referenced), unreferenced=[str(p) for p in sorted(root.glob('*'))
                if p.is_dir() and str(p) not in referenced], action='Read-only; never activate an orphan automatically')
