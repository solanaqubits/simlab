#!/usr/bin/env python3
"""Local coordination and byte-preserving intake archive utilities; no source execution."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

from chat_intake import check_queue, read_source, write_json
from geek_work_finalize import state_identity

MAX_ARCHIVE = 1024 ** 3
MAX_FILES = 20000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def status(registry, stream_id):
    stream = next(s for s in load(registry)['streams'] if s['id'] == stream_id)
    path = Path(stream['current_queue'])
    result = queue_summary(path, stream_id)
    result['expected_state'] = state_identity(stream)
    return result


def queue_summary(path, stream_id):
    queue = load(path)
    checks = check_queue(path)
    if checks['status'] != 'valid':
        raise ValueError('Queue is invalid: ' + '; '.join(checks['issues']))
    counts = Counter(row['stage'] for row in queue['items'])
    allowed = {'inventoried', 'prepared', 'editorial_pilot_reviewed',
               'editorial_partial_reviewed', 'extraction_review_required'}
    if counts.keys() - allowed:
        raise ValueError('Unknown stage: ' + repr(counts.keys() - allowed))
    from geek_work_ranges import prepared_views, range_coverage
    prepared, chunks, chunk_reviews, legacy, range_count = 0, 0, 0, 0, 0
    pdf_coverage = {}
    for row in queue['items']:
        views = prepared_views(row)
        prepared += bool(views)
        preparations = {}
        for view in views:
            prep = load(Path(view['prepared']) / 'preparation.json')
            preparations[view['prepared']] = prep
            range_count += 1
            chunks += len(prep['chunks'])
            if 'reviewed_chunks' in view:
                chunk_reviews += len(view['reviewed_chunks'])
            elif row['stage'] == 'editorial_pilot_reviewed':
                legacy += 1
        coverage = range_coverage(row, preparations)
        if coverage:
            pdf_coverage[row['path']] = coverage
    return dict(schema='geek-work-status-1', as_of=utc(), stream=stream_id,
                queue=str(path), queue_sha256=sha(path.read_bytes()), batch=queue['batch'],
                tool_sha256=sha(Path(__file__).read_bytes()),
                documents=len(queue['items']), stages=dict(sorted(counts.items())),
                prepared_documents=prepared, prepared_ranges=range_count, prepared_chunks=chunks,
                pdf_range_coverage=pdf_coverage,
                explicitly_accounted_reviewed_chunks=chunk_reviews,
                legacy_whole_document_reviews=legacy,
                next_batch=queue['next_batch'], queue_check=checks,
                counts_meaning='Recorded progress, not independent semantic review; '
                               'whole-document reviews are not converted into chunk counts.',
                facts_checked=False)


def compare(old_path, new_path):
    old, new = load(old_path), load(new_path)
    def index(doc):
        rows = {r['path']: r for r in doc['files']}
        if len(rows) != len(doc['files']):
            raise ValueError('Duplicate inventory paths')
        return rows
    a, b = index(old), index(new)
    result = dict(schema='geek-work-inventory-delta-1',
                  old_inventory=str(old_path.resolve()), old_sha256=sha(old_path.read_bytes()),
                  new_inventory=str(new_path.resolve()), new_sha256=sha(new_path.read_bytes()),
                  added=[], changed=[], unchanged=[], absent_in_new=[],
                  identical_content_candidates=[], automatic_queue_updates=False)
    for name in sorted(a.keys() | b.keys()):
        kind = ('added' if name not in a else 'absent_in_new' if name not in b else
                'unchanged' if a[name]['sha256'] == b[name]['sha256'] else 'changed')
        result[kind].append(name)
    by_hash = {}
    for name, row in a.items():
        by_hash.setdefault(row['sha256'], []).append(name)
    for name in result['added']:
        if b[name]['sha256'] in by_hash:
            result['identical_content_candidates'].append(
                dict(new_path=name, old_paths=by_hash[b[name]['sha256']]))
    return result


def owner_note(inventory, source, note_file, author, locator):
    doc = load(inventory)
    row = next(r for r in doc['files'] if r['path'] == source)
    # Resolve against the immutable snapshot, not a possibly updated live export.
    blob = inventory.parent / row['snapshot']
    if sha(read_source(blob)) != row['sha256']:
        raise ValueError('Source snapshot mismatch')
    text = read_source(note_file).decode('utf-8')
    if not text.strip() or not author.strip():
        raise ValueError('Nonempty note and author required')
    return dict(schema='geek-work-owner-note-1', recorded_at=utc(), author_label=author,
                author_authenticated=False, source_path=source, source_sha256=row['sha256'],
                inventory=str(inventory.resolve()), inventory_sha256=sha(inventory.read_bytes()),
                locator=locator, note=text, note_sha256=sha(text.encode('utf-8')),
                status='owner_context_not_scientific_evidence', instructions_executed=False)


def safe_name(name):
    p = PurePosixPath(name)
    if (not name or '\\' in name or p.is_absolute() or '..' in p.parts or
            str(p) != name or name == '.'):
        raise ValueError('Unsafe archive path: ' + name)
    return name


def snapshot(root, archive):
    root = root.resolve()
    if not root.is_dir() or archive.resolve() == root or root in archive.resolve().parents:
        raise ValueError('Archive must be outside a directory source')
    paths = sorted(root.rglob('*'))
    if any(p.is_symlink() for p in paths):
        raise ValueError('Symlinks are not archived')
    files = [p for p in paths if p.is_file()]
    if not files or len(files) > MAX_FILES or sum(p.stat().st_size for p in files) > MAX_ARCHIVE:
        raise ValueError('Archive budget exceeded or empty source')
    rows = []
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for p in files:
            data = read_source(p)
            name = safe_name(p.relative_to(root).as_posix())
            z.writestr('files/' + name, data)
            rows.append(dict(path=name, bytes=len(data), sha256=sha(data)))
        # Detect writes or new/deleted files during capture; failed archives are retained.
        now = sorted(p for p in root.rglob('*') if p.is_file())
        if now != files or any(sha(read_source(root / r['path'])) != r['sha256'] for r in rows):
            raise ValueError('Source changed during snapshot; archive is incomplete')
        manifest = dict(schema='geek-work-backup-1', created_at=utc(), source_root=str(root),
                        files=rows, total_bytes=sum(r['bytes'] for r in rows),
                        absolute_references='Preserved as source data; use source_root mapping '
                                            'after restore. No automatic registry activation.')
        z.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    return verify_archive(archive)


def verify_archive(archive, destination=None):
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or len(names) > MAX_FILES + 1:
            raise ValueError('Duplicate or excessive archive entries')
        for n in names:
            safe_name(n)
        if sum(i.file_size for i in z.infolist()) > MAX_ARCHIVE + 16 * 1024 ** 2:
            raise ValueError('Archive budget exceeded')
        manifest = json.loads(z.read('manifest.json'))
        if manifest['schema'] != 'geek-work-backup-1':
            raise ValueError('Unexpected archive schema')
        rows = manifest['files']
        expected = {'manifest.json'} | {'files/' + safe_name(r['path']) for r in rows}
        if len(expected) != len(rows) + 1 or set(names) != expected:
            raise ValueError('Archive manifest coverage mismatch')
        if manifest['total_bytes'] != sum(r['bytes'] for r in rows):
            raise ValueError('Manifest byte count mismatch')
        # Verify everything before creating restoration output.
        for r in rows:
            data = z.read('files/' + r['path'])
            if len(data) != r['bytes'] or sha(data) != r['sha256']:
                raise ValueError('Archive hash mismatch: ' + r['path'])
        if destination is not None:
            destination.mkdir(parents=True, exist_ok=False)
            for r in rows:
                p = destination / r['path']
                p.parent.mkdir(parents=True, exist_ok=True)
                with p.open('xb') as f:
                    f.write(z.read('files/' + r['path']))
                if sha(p.read_bytes()) != r['sha256']:
                    raise ValueError('Restored file mismatch')
    return dict(status='verified', archive=str(archive.resolve()), archive_sha256=sha(archive.read_bytes()),
                files=len(rows), bytes=manifest['total_bytes'],
                original_root=manifest['source_root'],
                restored_root=str(destination.resolve()) if destination else None,
                operational_relocation_tested=False, authenticity_claim=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    subs = p.add_subparsers(dest='command', required=True)
    s = subs.add_parser('status'); s.add_argument('registry', type=Path)
    s.add_argument('--stream', default='chat-intake-20261027')
    s = subs.add_parser('compare'); s.add_argument('old', type=Path); s.add_argument('new', type=Path)
    s = subs.add_parser('owner-note'); s.add_argument('inventory', type=Path)
    s.add_argument('source'); s.add_argument('note', type=Path); s.add_argument('--author', required=True)
    s.add_argument('--locator', default='whole document')
    s = subs.add_parser('backup'); s.add_argument('root', type=Path); s.add_argument('archive', type=Path)
    s = subs.add_parser('verify-backup'); s.add_argument('archive', type=Path)
    s = subs.add_parser('restore'); s.add_argument('archive', type=Path); s.add_argument('destination', type=Path)
    s = subs.add_parser('audit-queue'); s.add_argument('queue', type=Path); s.add_argument('store', type=Path)
    s.add_argument('--stream', default='chat-intake-20261027')
    s = subs.add_parser('finalize'); s.add_argument('registry', type=Path); s.add_argument('request', type=Path)
    for name in ['ledger-report', 'inspect-transactions']:
        s = subs.add_parser(name); s.add_argument('registry', type=Path)
        s.add_argument('--stream', default='chat-intake-20261027')
    for s in subs.choices.values():
        s.add_argument('--output', type=Path, help='Exclusive-create JSON report; otherwise stdout')
    a = p.parse_args()
    if a.output and a.output.exists():
        p.error("Output already exists; no action taken")
    if a.command == 'finalize':
        from geek_work_finalize import finalize, FinalizeError
        try: result = finalize(a.registry, load(a.request))
        except (ValueError, OSError, KeyError, StopIteration, TypeError) as err:
            print(json.dumps({'status': getattr(err, 'code', 'VALIDATION_OR_IO_ERROR'), 'detail': str(err)}))
            raise SystemExit(2)
    elif a.command == 'audit-queue':
        from geek_work_finalize import audit_queue
        result = audit_queue(a.queue, a.store, a.stream)
    elif a.command in ['ledger-report', 'inspect-transactions']:
        from geek_work_finalize import ledger_report, inspect_transactions
        result = (ledger_report if a.command == 'ledger-report' else inspect_transactions)(a.registry, a.stream)
    elif a.command == 'status': result = status(a.registry, a.stream)
    elif a.command == 'compare': result = compare(a.old, a.new)
    elif a.command == 'owner-note': result = owner_note(a.inventory, a.source, a.note, a.author, a.locator)
    elif a.command == 'backup': result = snapshot(a.root, a.archive)
    else: result = verify_archive(a.archive, getattr(a, 'destination', None))
    if a.output: write_json(a.output, result)
    else: print(json.dumps(result, ensure_ascii=False, indent=2))
    if a.command == 'audit-queue' and result['status'] != 'valid':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
