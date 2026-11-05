"""Canonical prepared-range views. Counts are provenance records, not semantic review."""
from pathlib import Path

RANGE_SCHEMA = 'geek-work-prepared-ranges-1'
FIELDS = ('prepared', 'reviews', 'review', 'reviewed_chunks', 'unreviewed_chunks', 'reviewed_chars')


def prepared_views(row):
    if row.get('range_schema') is None:
        return [row] if row.get('prepared') else []
    if row['range_schema'] != RANGE_SCHEMA:
        raise ValueError('Unknown range schema')
    records = row.get('prepared_ranges')
    if not isinstance(records, list) or not records:
        raise ValueError('Canonical ranges must be nonempty')
    views, seen = [], set()
    for rec in records:
        pp = str(Path(rec['prepared']).resolve())
        if pp in seen:
            raise ValueError('Duplicate preparation in canonical ranges')
        seen.add(pp)
        view = {k: v for k, v in row.items() if k not in ('prepared_ranges', 'range_schema')}
        for key in FIELDS:
            view.pop(key, None)
        view.update(rec)
        view['path'], view['sha256'] = row['path'], row['sha256']
        # Whole-document completion is checked against the union, not a single range.
        view['stage'] = 'editorial_partial_reviewed'
        views.append(view)
    primary = next((v for v in views if v['prepared'] == row.get('prepared')), None)
    if primary is None:
        raise ValueError('Primary preparation absent from canonical ranges')
    for key in FIELDS:
        if row.get(key) != primary.get(key):
            raise ValueError('Primary/canonical range mismatch: ' + key)
    if row.get('additional_prepared_ranges'):
        raise ValueError('Ambiguous legacy and canonical range authorities')
    return views


def range_coverage(row, preparations):
    """Use preparation page maps; legacy [first,last] fields are deliberately ignored."""
    if row.get('range_schema') != RANGE_SCHEMA:
        return None
    views = prepared_views(row)
    covered = set(); reviewed = set(); chunks = done = 0
    page_total = None
    for view in views:
        prep = preparations[view['prepared']]
        pages = [p['page'] for p in prep.get('pdf_pages', [])]
        if not pages or len(pages) != len(set(pages)):
            raise ValueError('Canonical PDF range needs a unique page map')
        total = prep['source']['pages']
        if type(total) is not int or total <= 0 or page_total not in (None, total):
            raise ValueError('Conflicting PDF page totals')
        page_total = total
        if any(type(p) is not int or not 1 <= p <= total for p in pages):
            raise ValueError('Invalid PDF page number')
        if covered.intersection(pages):
            raise ValueError('Overlapping authoritative PDF preparations')
        covered.update(pages)
        expected = {c['file'] for c in prep['chunks']}
        current = set(view.get('reviewed_chunks', []))
        chunks += len(expected); done += len(current)
        if current == expected:
            reviewed.update(pages)
    complete = reviewed == set(range(1, page_total + 1))
    if (row.get('document_review_complete') or row['stage'] == 'editorial_pilot_reviewed') and not complete:
        raise ValueError('Completed PDF has unreviewed or missing ranges')
    return dict(preparations=len(views), prepared_chunks=chunks, reviewed_chunks=done,
                total_pages=page_total, prepared_pages=len(covered),
                pages_with_all_chunks_reviewed=len(reviewed), complete_recorded_coverage=complete,
                semantic_review=False, visual_review_verified=False)
