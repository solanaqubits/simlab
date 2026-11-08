#!/usr/bin/env python3
"""Build one transport pair from a pinned, manually reviewed extraction record."""
import argparse
import os
from pathlib import Path

import geek_work_claim_extraction as extraction
import geek_work_claim_transport as transport
import geek_work_manuscript as m
import geek_work_manuscript_claims as c
from knowledge import strict_json

FLAGS = extraction.FLAGS
MAX_BYTES = extraction.MAX_BYTES


class Blocked(ValueError):
    """Valid inputs cannot be assembled under this adapter's mapping policy."""


def require_mapping(ok, reason):
    if not ok:
        raise Blocked(reason)


def report(status, stage, reason=None, **fields):
    result = dict(schema='geek-work-claim-adapter-report-1', status=status, stage=stage,
                  **{flag: False for flag in FLAGS}, **fields)
    if reason is not None:
        result['reason'] = reason
    return result


def unit(quantity):
    """Literal deterministic projection; the pinned editor supplies interpretation."""
    interpretation = quantity['unit_interpretation']
    raw, canonical = quantity['unit_raw'], quantity['unit_canonical']
    if interpretation == 'unknown':
        require_mapping(raw is None and canonical is None, 'unit_mapping_ambiguous')
        return 'unknown'
    if interpretation == 'literal':
        require_mapping(raw is not None and canonical in (None, raw), 'unit_mapping_ambiguous')
        return raw
    if interpretation == 'dimensionless':
        require_mapping(canonical in (None, 'dimensionless'), 'unit_mapping_ambiguous')
        return 'dimensionless'
    if interpretation == 'mapped':
        require_mapping(canonical is not None, 'unit_mapping_ambiguous')
        return canonical
    raise Blocked('unit_mapping_unsupported')


def mapped_contract(record):
    original = record['contract']
    result = {role: sorted([dict(id=a['atom_id'], text=a['text_raw'], sha256=a['text_sha256'])
                           for a in original[role]], key=lambda a: a['id']) for role in transport.ROLES}
    result['quantities'] = sorted([dict(id=q['quantity_id'], symbol=q['symbol'],
        exact_literal=q['exact_literal'], unit=unit(q)) for q in original['quantities']], key=lambda q:q['id'])
    result['scope'] = original['scope']
    result['reported_evidence_state'] = record['reported_evidence_state']
    for key in ('evidence_ids', 'non_claims', 'open_obligations'):
        result[key] = sorted(original[key])
    return result


def bound_source(mapping, claim, record):
    """Require byte/quote provenance, not merely equal words in unrelated files."""
    selected, snap = record['selected_span'], record['source_snapshot']
    statement = claim['statement']
    require_mapping(selected['quote'] == statement['quote'], 'selected_statement_mismatch')
    document = next(d for d in mapping['documents'] if d['id'] == statement['document'])
    if (document['sha256'] == snap['sha256'] and statement['start'] == selected['start_char']
            and statement['end'] == selected['end_char']):
        return dict(kind='document', id=document['id'])
    materials = {row['id']:row for row in mapping['materials']}
    matches = []
    for evidence in claim['evidence']:
        citation = evidence['citation']; material = materials[citation['material']]
        if (material['sha256'] == snap['sha256'] and
            material['origin']['commit'] == snap['commit'] and
            citation['start'] == selected['start_char'] and citation['end'] == selected['end_char']
                and citation['quote'] == selected['quote']):
            matches.append(material['id'])
    require_mapping(bool(matches), 'source_not_bound_to_selected_claim')
    return dict(kind='material', ids=sorted(set(matches)))


def build(source_raw, source_sha, expectations_raw, expectations_sha, record_raw,
          bundle, bundle_sha, source_claim_id, source_revision):
    """No saved-report input. Returns only receipts on failure, a package on success.

    The three expected hashes and source claim selection come from the coordinator.
    The generated plan's hash is derived output, not an independently approved pin.
    """
    artifacts = {}
    stage = 'admission'
    try:
        c.digest(bundle_sha); c.ident(source_claim_id); transport.revision(source_revision)
        checked = extraction.check(source_raw, source_sha, expectations_raw, expectations_sha, record_raw)
        artifacts['extraction-report.json'] = m.encoded(checked)
        if checked['status'] == 'invalid_input':
            result = report('invalid_input', stage, 'extraction_invalid_input', extraction_reason=checked['reason'])
        elif checked['status'] != 'record_consistent':
            result = report('build_blocked', stage, 'extraction_not_record_consistent', extraction_status=checked['status'])
        else:
            record = strict_json(record_raw)
            if record['editorial_state'] != 'ready_for_transport':
                result = report('build_blocked', stage, 'editorial_state_not_ready')
            elif record['unresolved_questions']:
                result = report('build_blocked', stage, 'unresolved_questions_not_empty')
            else:
                stage = 'bundle_validation'
                mapping = transport.snapshot(bundle, bundle_sha)
                matches = [row for row in mapping['claims'] if row['id'] == source_claim_id]
                require_mapping(len(matches) == 1, 'source_claim_not_found')
                stage = 'mapping'
                source_binding = bound_source(mapping, matches[0], record)
                contract = mapped_contract(record)
                annotations = {key:contract[key] for key in (*transport.ROLES, 'quantities')}
                plan = dict(schema='geek-work-claim-transport-plan-1', mode='exact_contract',
                    source_bundle_sha256=bundle_sha, pairs=[dict(id='extraction-pair',
                    source_claim_id=source_claim_id, candidate_claim_id=record['extraction_id'],
                    source_revision=source_revision, candidate_revision=record['revision'], annotations=annotations)])
                # Validate claim-map compatibility before a template could hide a mismatch
                # by replacing editorial scope/evidence/obligations with source defaults.
                try:
                    source_cards, _ = transport.adapt(mapping, plan, bundle_sha)
                except (ValueError, TypeError, KeyError) as error:
                    raise Blocked('claim_map_inconsistent: ' + str(error)) from error
                differences = transport.compare(source_cards[0]['contract'], contract)
                require_mapping(not differences, 'claim_map_inconsistent: ' + ','.join(differences))
                plan_raw = m.encoded(plan); plan_sha = m.sha(plan_raw)
                candidate = transport.template(bundle, bundle_sha, plan_raw, plan_sha)
                candidate['cards'][0]['contract'] = contract
                candidate_raw = m.encoded(candidate)
                stage = 'transport_validation'
                transported = transport.check(bundle, bundle_sha, plan_raw, plan_sha, candidate_raw)
                artifacts['transport-report.json'] = m.encoded(transported)
                require_mapping(transported['status'] == 'contract_preserved', 'transport_did_not_preserve_contract')
                artifacts.update({'source-snapshot.txt':source_raw, 'expectations.json':expectations_raw,
                    'record.json':record_raw, 'plan.json':plan_raw, 'candidate.json':candidate_raw})
                result = report('built', 'complete', source_binding=source_binding,
                    source_sha256=source_sha, expectations_sha256=expectations_sha,
                    record_sha256=m.sha(record_raw), claim_map_bundle_sha256=bundle_sha,
                    source_claim_id=source_claim_id, source_revision=source_revision,
                    plan_sha256=plan_sha, candidate_sha256=m.sha(candidate_raw),
                    extraction_status=checked['status'], transport_status=transported['status'])
        artifacts['adapter-report.json'] = m.encoded(result)
    except Blocked as error:
        artifacts['adapter-report.json'] = m.encoded(report('build_blocked', stage, str(error)))
    except (ValueError, TypeError, KeyError, UnicodeError, OSError) as error:
        artifacts['adapter-report.json'] = m.encoded(report('invalid_input', stage, str(error)))
    return artifacts


def write_package(output, artifacts, inputs):
    """Exclusive directory; manifest is last and marks a completed receipt/package.

    Partial directories are retained on I/O failure, without a completion manifest.
    No old artifact is removed or overwritten. Output is operator-controlled.
    """
    Path(output).mkdir()
    fd = os.open(output, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        def write(name, raw):
            leaf = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            with os.fdopen(leaf, 'wb') as stream:
                stream.write(raw)
        for name, raw in sorted(artifacts.items()):
            write(name, raw)
        manifest = dict(schema='geek-work-claim-adapter-package-1',
            status=strict_json(artifacts['adapter-report.json'])['status'],
            input_hashes=inputs, files={name:m.sha(raw) for name, raw in sorted(artifacts.items())},
            **{flag:False for flag in FLAGS})
        write('manifest.json', m.encoded(manifest))
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-snapshot', 'source-sha256', 'expectations', 'expectations-sha256',
                 'record', 'claim-map-bundle', 'claim-map-bundle-sha256', 'source-claim-id', 'output'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--source-revision', required=True, type=int)
    args = parser.parse_args()
    inputs = {}
    try:
        source = m.read(args.source_snapshot, extraction.MAX_SOURCE)
        expected = m.read(args.expectations, MAX_BYTES)
        record = m.read(args.record, MAX_BYTES)
        inputs = dict(source_sha256=m.sha(source), expectations_sha256=m.sha(expected), record_sha256=m.sha(record))
        artifacts = build(source, args.source_sha256, expected, args.expectations_sha256, record,
                          args.claim_map_bundle, args.claim_map_bundle_sha256, args.source_claim_id, args.source_revision)
    except (ValueError, OSError) as error:
        artifacts = {'adapter-report.json':m.encoded(report('invalid_input', 'input_read', str(error)))}
    # Keep supplied anchors distinct from observed input hashes, including on rejection.
    inputs.update(expected_source_sha256=args.source_sha256,
                  expected_expectations_sha256=args.expectations_sha256,
                  expected_claim_map_bundle_sha256=args.claim_map_bundle_sha256,
                  source_claim_id=args.source_claim_id, declared_source_revision=args.source_revision)
    write_package(args.output, artifacts, inputs)
    return {'built':0, 'build_blocked':1, 'invalid_input':2}[strict_json(artifacts['adapter-report.json'])['status']]


if __name__ == '__main__':
    raise SystemExit(main())
