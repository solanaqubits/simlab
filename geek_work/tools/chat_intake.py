#!/usr/bin/env python3
"""Offline, reversible staging before Digital Brain knowledge-card curation."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

MAX_SOURCE = 64 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, obj):
    with path.open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write('\n')


def read_source(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('Only regular, non-symlink input files are accepted')
    with path.open('rb') as f:
        data = f.read(MAX_SOURCE + 1)
    if len(data) > MAX_SOURCE:
        raise ValueError('Source exceeds 64 MiB; select a separate bounded workflow')
    return data


def inventory(root, output):
    root = root.resolve()
    output = output.resolve()
    if output == root or root in output.parents:
        raise ValueError('Output must be outside the input tree')
    files = sorted(p for p in root.rglob('*') if p.suffix.lower() in ('.md', '.pdf'))
    if not files or len(files) > 1000:
        raise ValueError('Expected 1..1000 input files')
    # Reject symlinked directories as well as files; never traverse outside root.
    for p in files:
        if any(q.is_symlink() for q in (p, *p.parents)):
            raise ValueError('Symlinked source paths are not accepted')
    if sum(p.stat().st_size for p in files) > MAX_TOTAL:
        raise ValueError('Inventory exceeds 512 MiB')
    output.mkdir(parents=True, exist_ok=False)
    (output / 'raw').mkdir()
    rows = []
    for p in files:
        raw = read_source(p)
        sha = digest(raw)
        blob = output / 'raw' / sha
        if not blob.exists():
            with blob.open('xb') as f:
                f.write(raw)
        elif blob.read_bytes() != raw:
            raise ValueError('Snapshot mismatch')
        row = dict(path=p.relative_to(root).as_posix(), sha256=sha,
                   bytes=len(raw), format=p.suffix.lower()[1:], status='inventoried',
                   snapshot='raw/' + sha, content_review='not_started')
        if p.suffix.lower() == '.md':
            try:
                text = raw.decode('utf-8')
                row.update(chars=len(text), lines=len(text.splitlines()),
                           user_prompt_markers=text.count('User prompt:'))
            except UnicodeDecodeError:
                row['encoding_issue'] = 'not UTF-8; no replacement decoding'
        else:
            try:
                proc = subprocess.run(['pdfinfo', str(blob)], capture_output=True,
                                      timeout=30, check=True)
                m = re.search(rb'^Pages:\s+(\d+)', proc.stdout, re.M)
                row['pages'] = int(m[1]) if m else None
            except (OSError, subprocess.SubprocessError) as err:
                row['pdfinfo_issue'] = type(err).__name__
        rows.append(row)
    doc = dict(schema='digital-brain-intake-1', source_root=str(root), files=rows,
               source_identity='byte content, not authorship or truth',
               total_bytes=sum(r['bytes'] for r in rows))
    write_json(output / 'inventory.json', doc)
    return doc


def protected_lines(lines):
    """Conservative fence/display-math guard, not a complete Markdown parser."""
    fence = None
    math = None
    flags = []
    for line in lines:
        s = line.strip()
        # Chat exports commonly wrap fenced blocks in Markdown blockquotes.
        s = re.sub(r'^(?:>\s*)+', '', s)
        active = fence is not None or math is not None
        marker = re.match(r'^(`{3,}|~{3,})', s)
        if fence:
            if re.fullmatch(re.escape(fence[0]) + '{' + str(len(fence)) + ',}', s):
                fence = None
        elif math:
            if (math == '$$' and s.count('$$') % 2) or (math == '\\[' and '\\]' in s):
                math = None
        elif marker:
            fence = marker[1]
            active = True
        elif '$$' in s:
            active = True
            if s.count('$$') % 2:
                math = '$$'
        elif '\\[' in s:
            active = True
            if '\\]' not in s:
                math = '\\['
        flags.append(active)
    return flags


def clean_text(text, markdown=True):
    lines = text.splitlines(keepends=True)
    flags = protected_lines(lines) if markdown else [True] * len(lines)
    kept, removed, mapping = [], [], []
    blank_run = 0
    for n, (line, protected) in enumerate(zip(lines, flags), 1):
        # Even apparent UI text can contain evidence. Only redundant blank lines
        # outside protected regions are removed automatically. PDF layout is kept.
        blank = not line.strip()
        blank_run = blank_run + 1 if blank and not protected else 0
        if blank_run > 1:
            removed.append(dict(source_line=n, text=line, reason='extra_blank_line'))
        else:
            kept.append(line)
            mapping.append(n)
    rebuilt = dict(zip(mapping, kept))
    rebuilt.update((r['source_line'], r['text']) for r in removed)
    assert ''.join(rebuilt[n] for n in range(1, len(lines) + 1)) == text
    return ''.join(kept), mapping, removed


def chunk_spans(text, target_chars, split_oversized_lines=False):
    if target_chars < 256:
        raise ValueError('Chunk target must be at least 256 characters')
    lines = text.splitlines(keepends=True)
    flags = protected_lines(lines)
    # Paragraph blocks stay intact. Large blocks are flagged, never truncated.
    blocks, start = [], 0
    for i, line in enumerate(lines):
        if not flags[i] and not line.strip():
            blocks.append((start, i + 1))
            start = i + 1
    if start < len(lines):
        blocks.append((start, len(lines)))
    units = []
    for a, b in blocks:
        count = sum(len(line) for line in lines[a:b])
        if not split_oversized_lines or count <= target_chars:
            units.append((a, b))
            continue

        # Explicit fallback for an oversized, unseparated block. Never split
        # protected code/math runs or contiguous Markdown table rows; other
        # text is divided only between complete source lines.
        i = a
        while i < b:
            j = i + 1
            if flags[i]:
                while j < b and flags[j]:
                    j += 1
            elif '|' in lines[i]:
                while (j < b and not flags[j]
                       and '|' in lines[j]):
                    j += 1
            units.append((i, j))
            i = j

    chunks, start, end, size = [], 0, 0, 0
    for a, b in units:
        count = sum(len(line) for line in lines[a:b])
        if size and size + count > target_chars:
            chunks.append((start, end))
            start, size = a, 0
        end, size = b, size + count
    if end > start:
        chunks.append((start, end))
    assert ''.join(''.join(lines[a:b]) for a, b in chunks) == text
    return chunks


def prepare(store, name, output, target_chars=12000, pages=None,
            split_oversized_lines=False):
    inv = json.loads((store / 'inventory.json').read_text())
    for protected in [store.resolve() / 'raw'] + ([Path(inv['source_root'])] if 'source_root' in inv else []):
        if output.resolve() == protected or protected in output.resolve().parents:
            raise ValueError('Prepared outputs must not be placed inside source or raw snapshots')
    row = next(r for r in inv['files'] if r['path'] == name)
    raw = read_source(store / row['snapshot'])
    if digest(raw) != row['sha256']:
        raise ValueError('Snapshot hash mismatch')
    page_map = []
    extractor = None
    if row['format'] == 'md':
        if pages:
            raise ValueError('Page selection only applies to PDF')
        text = raw.decode('utf-8')
    else:
        if not pages or not 1 <= pages[0] <= pages[1] or pages[1] - pages[0] >= 20:
            raise ValueError('PDF requires explicit range of at most 20 pages')
        if row.get('pages') is None or pages[1] > row['pages']:
            raise ValueError('PDF page count unavailable or page range out of bounds')
        extractor = subprocess.run(['pdftotext', '-v'], capture_output=True,
                                   timeout=10, check=True).stderr.decode().splitlines()[0]
        text = ''
        for page in range(pages[0], pages[1] + 1):
            proc = subprocess.run(['pdftotext', '-f', str(page), '-l', str(page),
                                   '-layout', '-enc', 'UTF-8', str(store / row['snapshot']), '-'],
                                  capture_output=True, timeout=60, check=True)
            if len(proc.stdout) > MAX_SOURCE:
                raise ValueError('Extracted page exceeds output limit')
            part = proc.stdout.decode('utf-8')
            start = len(text.splitlines()) + 1
            text += part
            page_map.append(dict(page=page, line_start=start, line_end=len(text.splitlines()),
                                 text_chars=len(part.strip()), sha256=digest(proc.stdout)))
    output.mkdir(parents=True, exist_ok=False)
    extracted = text.encode('utf-8')
    with (output / 'extracted.txt').open('xb') as f:
        f.write(extracted)
    cleaned, mapping, removed = clean_text(text, markdown=row['format'] == 'md')
    with (output / 'cleaned.md').open('xb') as f:
        f.write(cleaned.encode('utf-8'))
    lines = cleaned.splitlines(keepends=True)
    (output / 'chunks').mkdir()
    chunks = []
    for n, (a, b) in enumerate(
            chunk_spans(cleaned, target_chars, split_oversized_lines), 1):
        part = ''.join(lines[a:b])
        filename = f'chunks/{n:04}.md'
        (output / filename).write_bytes(part.encode('utf-8'))
        source_start, source_end = mapping[a], mapping[b - 1]
        chunks.append(dict(file=filename, sha256=digest(part.encode('utf-8')),
                           chars=len(part), clean_line_start=a + 1, clean_line_end=b,
                           extracted_line_start=source_start, extracted_line_end=source_end,
                           pdf_pages=[p['page'] for p in page_map if p['line_start'] <= source_end
                                      and p['line_end'] >= source_start],
                           oversized=len(part) > target_chars, review='not_started'))
    record = dict(schema='digital-brain-intake-prepared-1', source=row,
                  extracted_sha256=digest(extracted), cleaned_sha256=digest(cleaned.encode('utf-8')),
                  retained_source_lines=mapping, removed=removed, chunks=chunks,
                  pdf_pages=page_map, extractor=extractor, target_chars=target_chars,
                  split_oversized_lines=split_oversized_lines,
                  chunking_method=('line_boundary_fallback' if split_oversized_lines
                                   else 'blank_line_blocks'),
                  extraction_review='required' if page_map else 'direct_utf8',
                  content_review='not_started', fact_check='not_performed',
                  partial_pdf=bool(page_map) and len(page_map) != row['pages'])
    write_json(output / 'preparation.json', record)
    return record


def verify(store, prepared):
    def require(condition):
        if not condition:
            raise ValueError('Intake integrity verification failed')

    rec = json.loads((prepared / 'preparation.json').read_text())
    raw = read_source(store / rec['source']['snapshot'])
    require(digest(raw) == rec['source']['sha256'])
    extracted = (prepared / 'extracted.txt').read_bytes()
    cleaned = (prepared / 'cleaned.md').read_bytes()
    require(digest(extracted) == rec['extracted_sha256'])
    require(digest(cleaned) == rec['cleaned_sha256'])
    lines = cleaned.decode('utf-8').splitlines(keepends=True)
    mapping = rec['retained_source_lines']
    require(len(mapping) == len(lines) and len(set(mapping)) == len(mapping))
    original = dict(zip(mapping, lines))
    for removed in rec['removed']:
        require(removed['source_line'] not in original)
        original[removed['source_line']] = removed['text']
    require(set(original) == set(range(1, len(extracted.decode('utf-8').splitlines()) + 1)))
    require(''.join(original[i] for i in sorted(original)).encode('utf-8') == extracted)
    if rec['source']['format'] == 'md':
        require(extracted == raw)
    parts = []
    for ch in rec['chunks']:
        part = (prepared / ch['file']).read_bytes()
        require(digest(part) == ch['sha256'])
        require(part == ''.join(lines[ch['clean_line_start'] - 1:ch['clean_line_end']]).encode('utf-8'))
        parts.append(part)
    require(b''.join(parts) == cleaned)
    return {'status': 'byte_roundtrip_and_chunks_verified', 'semantic_review': False}


def edit(source, specification, output):
    """Apply explicit, reviewed character edits; preserve exact inverse patches."""
    raw = read_source(source)
    text = raw.decode('utf-8')
    spec = json.loads(specification.read_text())
    if digest(raw) != spec['input_sha256']:
        raise ValueError('Editorial input changed')
    edits = sorted(spec['edits'], key=lambda e: e['start_char'])
    cursor, parts, applied, size = 0, [], [], 0
    for e in edits:
        start, end = e['start_char'], e['end_char']
        if not cursor <= start < end <= len(text) or not e['reason'].strip():
            raise ValueError('Invalid or overlapping editorial edits')
        if text[start:end] != e['before']:
            raise ValueError('Editorial context mismatch')
        whole_word = e.get('whole_word', False)
        if type(whole_word) is not bool:
            raise ValueError('whole_word must be a Boolean')
        if whole_word and ((start and re.match(r'\w', text[start - 1])) or
                           (end < len(text) and re.match(r'\w', text[end]))):
            raise ValueError('Editorial whole-word boundary mismatch')
        unchanged = text[cursor:start]
        parts.extend([unchanged, e['after']])
        size += len(unchanged)
        applied.append(dict(e, output_start_char=size, output_end_char=size + len(e['after'])))
        size += len(e['after'])
        cursor = end
    result = ''.join(parts) + text[cursor:]
    restored = result
    for e in reversed(applied):
        restored = restored[:e['output_start_char']] + e['before'] + restored[e['output_end_char']:]
    if restored != text:
        raise ValueError('Editorial inverse verification failed')
    output.mkdir(parents=True, exist_ok=False)
    (output / 'edited.md').write_bytes(result.encode('utf-8'))
    record = dict(schema='digital-brain-editorial-patch-1', input_sha256=digest(raw),
                  output_sha256=digest(result.encode('utf-8')), edits=applied,
                  offsets='Unicode code points, half-open', inverse_verified=True,
                  factual_verification='not_performed', review=spec['review'])
    write_json(output / 'edits.json', record)
    return record


def check_queue(path):
    """Check local queue references and chunk accounting, not editorial quality."""
    queue = json.loads(path.read_text())
    issues = []
    batch = re.search(r'-batch(\d+)$', path.parent.name)
    if batch and str(queue.get('batch')) != batch[1]:
        issues.append('Batch ID differs from queue directory')
    previous = queue.get('previous_queue')
    lineage = queue.get('lineage', {}).get('previous_queue')
    if previous and lineage and Path(previous).resolve() != Path(lineage).resolve():
        issues.append('Conflicting previous_queue references')
    for reference in [previous, lineage, queue.get('lineage', {}).get('previous_manifest')]:
        if reference and not Path(reference).is_file():
            issues.append('Missing history reference: ' + reference)
    history = queue.get('lineage', {})
    if 'batch' in history and str(history['batch']) != str(queue.get('batch')):
        issues.append('Lineage batch differs from queue batch')
    if previous and Path(previous).is_file():
        raw = Path(previous).read_bytes()
        if history.get('previous_queue_sha256') and history['previous_queue_sha256'] != hashlib.sha256(raw).hexdigest():
            issues.append('Previous queue hash mismatch')
        if 'previous_batch' in history and str(history['previous_batch']) != str(json.loads(raw).get('batch')):
            issues.append('Previous batch mismatch')
    rows = queue['items']
    if len({row['path'] for row in rows}) != len(rows):
        issues.append('Duplicate source paths')
    from geek_work_ranges import prepared_views, range_coverage
    views = []
    for row in rows:
        try:
            ranges = prepared_views(row)
            if row.get('range_schema'):
                preparations = {v['prepared']: json.loads((Path(v['prepared']) / 'preparation.json').read_text()) for v in ranges}
                range_coverage(row, preparations)
            views.extend(ranges or [row])
        except (ValueError, KeyError, OSError, TypeError) as error:
            issues.append(f"{row['path']}: invalid prepared ranges: {error}")
    for row in views:
        name = row['path']
        refs = set(row.get('reviews', []))
        if row.get('review'):
            refs.add(row['review'])
        reviewed_by_record = set()
        review_records = []
        for ref in sorted(refs):
            if not Path(ref).is_file():
                issues.append(f'{name}: missing review {ref}')
                continue
            review = json.loads(Path(ref).read_text())
            review_records.append((ref, review))
            for field, expected in [('source_path', name), ('source_sha256', row['sha256'])]:
                if field in review and review[field] != expected:
                    issues.append(f'{name}: review {field} mismatch in {ref}')
            if review.get('chunk_path'):
                reviewed_by_record.add(review['chunk_path'])
        prepared = row.get('prepared')
        if not prepared:
            continue
        prep_path = Path(prepared) / 'preparation.json'
        if not prep_path.is_file():
            issues.append(f'{name}: missing preparation')
            continue
        prep = json.loads(prep_path.read_text())
        if prep['source']['sha256'] != row['sha256']:
            issues.append(f'{name}: preparation source hash mismatch')
        if 'reviewed_chunks' not in row:
            continue  # Whole-document reviews use the older representation.
        done, pending = row['reviewed_chunks'], row.get('unreviewed_chunks', [])
        expected = {ch['file']: ch for ch in prep['chunks']}
        for ref, review in review_records:
            chunk = expected.get(review.get('chunk_path'))
            if chunk is not None and review.get('chunk_sha256') != chunk['sha256']:
                issues.append(f'{name}: review chunk hash mismatch in {ref}')
        if (len(set(done)) != len(done) or len(set(pending)) != len(pending) or
                set(done) & set(pending) or set(done) | set(pending) != set(expected)):
            issues.append(f'{name}: chunk partition mismatch')
        if set(done) != reviewed_by_record:
            issues.append(f'{name}: reviewed chunks differ from review records')
        if row.get('reviewed_chars') != sum(expected[c]['chars'] for c in set(done) if c in expected):
            issues.append(f'{name}: reviewed character count mismatch')
        if pending and row.get('stage') == 'editorial_pilot_reviewed':
            issues.append(f'{name}: complete status with pending chunks')
    return dict(status='valid' if not issues else 'invalid', issues=issues,
                completed_documents=sum(r.get('stage') == 'editorial_pilot_reviewed' for r in rows),
                partial_documents=sum(r.get('stage') == 'editorial_partial_reviewed' for r in rows),
                semantic_review=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('inventory'); p.add_argument('root', type=Path); p.add_argument('output', type=Path)
    p = sub.add_parser('prepare'); p.add_argument('store', type=Path); p.add_argument('name'); p.add_argument('output', type=Path)
    p.add_argument('--chars', type=int, default=12000); p.add_argument('--pages', type=int, nargs=2)
    p.add_argument('--split-oversized-lines', action='store_true',
                   help='For oversized blocks only, split between lines while keeping code/math and table runs intact')
    p = sub.add_parser('verify'); p.add_argument('store', type=Path); p.add_argument('prepared', type=Path)
    p = sub.add_parser('check-queue'); p.add_argument('queue', type=Path)
    p = sub.add_parser('edit'); p.add_argument('source', type=Path); p.add_argument('specification', type=Path); p.add_argument('output', type=Path)
    a = parser.parse_args()
    if a.command == 'inventory':
        doc = inventory(a.root, a.output)
        print(json.dumps({'files': len(doc['files']), 'bytes': doc['total_bytes']}))
    elif a.command == 'prepare':
        rec = prepare(a.store, a.name, a.output, a.chars, a.pages,
                      a.split_oversized_lines)
        print(json.dumps({'chunks': len(rec['chunks']), 'removed_blank_lines': len(rec['removed']),
                          'partial_pdf': rec['partial_pdf']}))
    elif a.command == 'verify':
        print(json.dumps(verify(a.store, a.prepared)))
    elif a.command == 'check-queue':
        result = check_queue(a.queue)
        print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(0 if result['status'] == 'valid' else 1)
    else:
        rec = edit(a.source, a.specification, a.output)
        print(json.dumps({'edits': len(rec['edits']), 'inverse_verified': rec['inverse_verified']}))


if __name__ == '__main__':
    main()
