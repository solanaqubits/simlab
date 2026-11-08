#!/usr/bin/env python3
"""Bounded editorial record checks against external pins, not semantic extraction."""
import argparse
from pathlib import Path

import geek_work_manuscript as m
import geek_work_manuscript_claims as c
from geek_work_claim_transport import FLAGS, ROLES
from knowledge import strict_json

MAX_BYTES = 2 * 1024 * 1024
MAX_SOURCE = 1024 * 1024
CHECKS = ('source_pinned', 'inspection_scope', 'claim_separation', 'quote_atom_bindings',
          'selected_conditions', 'literal_quantities_units', 'evidence_inheritance',
          'nonclaims_obligations', 'decision_record', 'readiness_review')
COMMON = ('extraction_id source_snapshot selected_span claim_type reported_evidence_state '
          'contract coverage_checks unresolved_questions')


def report(status, **fields):
    return dict(schema='geek-work-claim-extraction-report-1', status=status,
                **{flag: False for flag in FLAGS}, **fields)


def enum(value, options, reason):
    m.require(type(value) is str and value in options, reason)


def optional_text(value):
    if value is not None:
        c.text(value)


def indexed(rows, key, maximum=32):
    c.rows(rows, maximum)
    out = {}
    for row in rows:
        m.require(type(row) is dict and key in row, 'row identity')
        c.text(row[key])
        m.require(row[key] not in out, 'duplicate ' + key)
        out[row[key]] = row
    return out


def inside(small, large):
    return large['start_char'] <= small['start_char'] < small['end_char'] <= large['end_char']


def span(value, source, container=None):
    c.obj(value, 'start_char end_char quote')
    a, b = value['start_char'], value['end_char']
    m.require(type(a) is int and type(b) is int and 0 <= a < b <= len(source), 'span_offsets')
    c.text(value['quote'])
    m.require(source[a:b] == value['quote'], 'quote_mismatch')
    if container is not None:
        m.require(inside(value, container), 'span_outside_selected_source')


def atom(value, source, selected, registry):
    c.obj(value, 'atom_id text_raw text_sha256 quote_span')
    c.ident(value['atom_id']); c.text(value['text_raw']); c.digest(value['text_sha256'])
    span(value['quote_span'], source, selected)
    m.require(value['text_raw'] == value['quote_span']['quote'], 'atom_quote_mismatch')
    m.require(m.sha(value['text_raw'].encode()) == value['text_sha256'], 'atom_hash_mismatch')
    # Identity includes the quotation location, not only matching text elsewhere.
    signature = m.encoded(value)
    previous = registry.setdefault(value['atom_id'], signature)
    m.require(previous == signature, 'atom_id_rebinding')


def quantity(value, source, selected):
    c.obj(value, 'quantity_id symbol exact_literal literal_span unit_raw unit_span '
          'unit_interpretation unit_canonical unit_mapping_basis')
    c.ident(value['quantity_id']); c.text(value['symbol']); c.text(value['exact_literal'])
    span(value['literal_span'], source, selected)
    m.require(value['literal_span']['quote'] == value['exact_literal'], 'numeric_literal_mismatch')
    enum(value['unit_interpretation'], {'unknown', 'dimensionless', 'literal', 'mapped'}, 'unit_interpretation')
    for key in ('unit_raw', 'unit_canonical', 'unit_mapping_basis'):
        optional_text(value[key])
    if value['unit_raw'] is None:
        m.require(value['unit_span'] is None, 'unit_span_without_raw_unit')
    else:
        span(value['unit_span'], source, selected)
        m.require(value['unit_span']['quote'] == value['unit_raw'], 'unit_quote_mismatch')
    if value['unit_interpretation'] == 'unknown':
        m.require(value['unit_canonical'] is None, 'unknown_unit_normalized')
    if value['unit_interpretation'] in {'mapped', 'dimensionless'}:
        c.text(value['unit_mapping_basis'])
    # Mapping basis is a pinned editorial assertion, never evaluated as proof.


def common(value, source, source_sha, registry):
    c.ident(value['extraction_id'])
    snap = value['source_snapshot']
    c.obj(snap, 'repository commit file_path sha256 encoding')
    c.text(snap['repository']); c.digest(snap['commit'], 40); c.path_name(snap['file_path'])
    c.digest(snap['sha256'])
    m.require(snap['sha256'] == source_sha and snap['encoding'] == 'UTF-8', 'source_snapshot_binding')
    selected = value['selected_span']; span(selected, source)
    enum(value['claim_type'], {'definition', 'hypothesis', 'computation_result', 'theorem'}, 'claim_type')
    enum(value['reported_evidence_state'], c.STATES, 'reported_evidence_state')
    contract = value['contract']
    c.obj(contract, ' '.join((*ROLES, 'scope', 'quantities', 'evidence_ids', 'non_claims', 'open_obligations')))
    roles = {}
    for role in ROLES:
        roles[role] = indexed(contract[role], 'atom_id')
        for row in roles[role].values():
            atom(row, source, selected, registry)
    c.text(contract['scope'])
    for row in indexed(contract['quantities'], 'quantity_id').values():
        quantity(row, source, selected)
    for key in ('evidence_ids', 'non_claims', 'open_obligations'):
        c.strings(contract[key]); m.require(len(set(contract[key])) == len(contract[key]), 'duplicate text')
    for digest in contract['evidence_ids']:
        c.digest(digest)
    checks = indexed(value['coverage_checks'], 'check_id', 64)
    for row in checks.values():
        c.obj(row, 'check_id expected_condition_editorial_text expected_role source_observation '
              'inspected_spans evidence_spans extracted_atom_ids finding review_notes')
        c.ident(row['check_id']); c.text(row['expected_condition_editorial_text'])
        enum(row['expected_role'], (*ROLES, 'quantities'), 'coverage_role')
        enum(row['source_observation'], {'condition_present', 'condition_absent', 'condition_not_inspected'}, 'coverage_observation')
        optional_text(row['finding']); optional_text(row['review_notes'])
        for group in ('inspected_spans', 'evidence_spans'):
            for quote in c.rows(row[group], 32):
                span(quote, source, selected)
        ids = row['extracted_atom_ids']; c.strings(ids)
        m.require(len(set(ids)) == len(ids), 'duplicate coverage id')
        if row['source_observation'] == 'condition_present':
            m.require(bool(row['inspected_spans']) and bool(row['evidence_spans']), 'present_without_evidence')
            for quote in row['evidence_spans']:
                m.require(any(inside(quote, s) for s in row['inspected_spans']), 'evidence_not_inspected')
            for identifier in ids:
                m.require(row['expected_role'] in roles and identifier in roles[row['expected_role']], 'dangling_coverage_atom')
                quoted = roles[row['expected_role']][identifier]['quote_span']
                m.require(quoted in row['evidence_spans'], 'coverage_atom_quote_mismatch')
        else:
            m.require(not ids and not row['evidence_spans'], 'absent_or_uninspected_has_atom')
            if row['source_observation'] == 'condition_absent':
                m.require(bool(row['inspected_spans']), 'absence_without_inspection')
    questions = indexed(value['unresolved_questions'], 'item_id')
    for row in questions.values():
        c.obj(row, 'item_id description required_before_transport resolution')
        c.ident(row['item_id']); c.text(row['description'])
        m.require(type(row['required_before_transport']) is bool, 'required_flag_type')
        optional_text(row['resolution'])
    return roles


def compare(expected, record):
    differences = []
    for key in ('extraction_id', 'source_snapshot', 'selected_span', 'claim_type', 'reported_evidence_state'):
        if m.encoded(expected[key]) != m.encoded(record[key]):
            differences.append(key + '_changed')
    for role in ROLES:
        old = indexed(expected['contract'][role], 'atom_id')
        new = indexed(record['contract'][role], 'atom_id')
        if old.keys() - new.keys():
            differences.append('missing_extracted_atom:' + role)
        if new.keys() - old.keys():
            differences.append('unexpected_extracted_atom:' + role)
    for key in ('scope', 'quantities', 'evidence_ids', 'non_claims', 'open_obligations'):
        old, new = expected['contract'][key], record['contract'][key]
        if key == 'quantities':
            old, new = indexed(old, 'quantity_id'), indexed(new, 'quantity_id')
        elif key != 'scope':
            old, new = sorted(old), sorted(new)
        if m.encoded(old) != m.encoded(new):
            differences.append(key + '_changed')
    for key, identity, maximum in [('coverage_checks', 'check_id', 64), ('unresolved_questions', 'item_id', 32)]:
        if m.encoded(indexed(expected[key], identity, maximum)) != m.encoded(indexed(record[key], identity, maximum)):
            differences.append(key + '_changed')
    return differences


def check(source_raw, source_sha, expectations_raw, expectations_sha, record_raw):
    """One source snapshot and one record. Pins are provided outside the record."""
    try:
        c.digest(source_sha); c.digest(expectations_sha)
        m.require(len(source_raw) <= MAX_SOURCE, 'source_byte_limit')
        m.require(len(expectations_raw) + len(record_raw) <= MAX_BYTES, 'combined_byte_limit')
        m.require(m.sha(source_raw) == source_sha, 'external_source_hash_mismatch')
        m.require(m.sha(expectations_raw) == expectations_sha, 'external_expectations_hash_mismatch')
        source = source_raw.decode('utf-8'); m.require('\x00' not in source, 'source_nul')
        expected, record = strict_json(expectations_raw), strict_json(record_raw)
        c.obj(expected, 'schema ' + COMMON)
        c.obj(record, 'schema revision editorial_state checklist review assurances ' + COMMON)
        m.require(expected['schema'] == 'geek-work-claim-extraction-expectations-1', 'expectations_schema')
        m.require(record['schema'] == 'geek-work-claim-extraction-record-1', 'record_schema')
        m.require(type(record['revision']) is int and 1 <= record['revision'] <= 2**31-1, 'record_revision')
        enum(record['editorial_state'], {'draft', 'needs_context', 'ready_for_transport'}, 'editorial_state')
        c.obj(record['assurances'], ' '.join(FLAGS))
        m.require(all(record['assurances'][flag] is False for flag in FLAGS), 'assurance_promotion')
        registry = {}
        common(expected, source, source_sha, registry)
        common(record, source, source_sha, registry)
        checklist = indexed(record['checklist'], 'id', 10)
        m.require(set(checklist) == set(CHECKS), 'ten_checklist_items_required')
        for row in checklist.values():
            c.obj(row, 'id state notes')
            enum(row['state'], {'checked', 'needs_context', 'not_inspected'}, 'checklist_state')
            optional_text(row['notes'])
        c.obj(record['review'], 'reviewer_record reviewed_at decision_notes')
        for text in record['review'].values():
            c.text(text)
        # Baseline obligations survive candidate deletion, demotion or invented resolution.
        mandatory = any(q['required_before_transport'] and q['resolution'] is None
                        for obj in (expected, record) for q in obj['unresolved_questions'])
        pending = mandatory or any(row['state'] != 'checked' for row in checklist.values()) or any(
            row['source_observation'] == 'condition_not_inspected' or row['finding'] is not None or
            (row['source_observation'] == 'condition_present' and not row['extracted_atom_ids'])
            for row in record['coverage_checks'])
        if record['editorial_state'] == 'ready_for_transport':
            m.require(not mandatory, 'mandatory_unresolved_question_incompatible_with_ready_for_transport')
            m.require(not pending, 'incomplete_editorial_checks_incompatible_with_ready_for_transport')
        m.require(not mandatory or record['editorial_state'] == 'needs_context', 'mandatory_unresolved_question_requires_needs_context')
        differences = compare(expected, record)
        status = 'review_required' if differences else 'needs_context' if pending or record['editorial_state'] == 'needs_context' else 'record_consistent'
        return report(status, editorial_state=record['editorial_state'], differences=differences,
                      atom_binding_count=sum(len(record['contract'][role]) for role in ROLES),
                      source_sha256=source_sha, expectations_sha256=expectations_sha,
                      record_sha256=m.sha(record_raw))
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError) as error:
        return report('invalid_input', reason=str(error))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-snapshot', 'source-sha256', 'expectations', 'expectations-sha256', 'record', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    try:
        result = check(m.read(args.source_snapshot, MAX_SOURCE), args.source_sha256,
                       m.read(args.expectations, MAX_BYTES), args.expectations_sha256,
                       m.read(args.record, MAX_BYTES))
    except (ValueError, OSError) as error:
        result = report('invalid_input', reason=str(error))
    # Exclusive output: old evidence and source files cannot be overwritten.
    with Path(args.output).open('xb') as stream:
        stream.write(m.encoded(result))
    return {'record_consistent': 0, 'needs_context': 1, 'review_required': 1, 'invalid_input': 2}[result['status']]


if __name__ == '__main__':
    raise SystemExit(main())
