#!/usr/bin/env python3
"""Offline, pinned comparison of selected claim contracts; never semantic proof."""
import argparse
from collections import Counter
import copy
import os
from pathlib import Path
import re
import stat

import geek_work_manuscript_claims as claims
import geek_work_manuscript as m
from knowledge import strict_json

MAX_BYTES = 2 * 1024 * 1024
ROLES = ('premise_atoms', 'conclusion_atoms', 'domain_atoms', 'quantifier_atoms', 'negation_atoms')
FLAGS = ('semantic_equivalence_verified', 'source_extraction_complete',
         'kernel_replayed', 'publication_authorized')
CONTRACT_FIELDS = (*ROLES, 'scope', 'quantities', 'reported_evidence_state',
                   'evidence_ids', 'non_claims', 'open_obligations')


def report(status, **fields):
    return dict(schema='geek-work-claim-transport-report-1', mode='exact_contract',
                status=status, **{key: False for key in FLAGS}, **fields)


def unique(rows, key):
    values = [row[key] for row in rows]
    m.require(len(set(values)) == len(values), 'duplicate ' + key)


def revision(value):
    m.require(type(value) is int and 1 <= value <= 2**31 - 1, 'revision range')


def strings(value):
    claims.strings(value)
    m.require(len(set(value)) == len(value), 'duplicate text')


def atoms(value, table):
    for atom in claims.rows(value, 32):
        claims.obj(atom, 'id text sha256')
        claims.ident(atom['id']); claims.text(atom['text']); claims.digest(atom['sha256'])
        m.require(m.sha(atom['text'].encode('utf-8')) == atom['sha256'], 'atom text hash')
        previous = table.setdefault(atom['id'], (atom['text'], atom['sha256']))
        m.require(previous == (atom['text'], atom['sha256']), 'atom id rebinding')
    unique(value, 'id')


def quantities(value):
    for row in claims.rows(value, 32):
        claims.obj(row, 'id symbol exact_literal unit')
        claims.ident(row['id'])
        for key in ('symbol', 'exact_literal', 'unit'):
            claims.text(row[key])
    unique(value, 'id')


def contract(value, table):
    claims.obj(value, ' '.join(CONTRACT_FIELDS))
    for role in ROLES:
        atoms(value[role], table)
    claims.text(value['scope']); quantities(value['quantities'])
    m.require(type(value['reported_evidence_state']) is str and
              value['reported_evidence_state'] in claims.STATES, 'reported state')
    for key in ('evidence_ids', 'non_claims', 'open_obligations'):
        strings(value[key])
    for value in value['evidence_ids']:
        claims.digest(value)


def snapshot(bundle, expected):
    """Read a single bounded snapshot through a directory FD, then replay claim-map-1.

    Inherited bundles retain their own 16 MiB bound. No verify-then-reread window.
    The supplied hash authenticates bytes only relative to the coordinator input.
    """
    claims.digest(expected)
    fd = os.open(bundle, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        def read(name, limit):
            leaf = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            with os.fdopen(leaf, 'rb') as stream:
                m.require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'regular bundle file')
                raw = stream.read(limit + 1)
                m.require(len(raw) <= limit, 'bundle file byte limit')
                return raw
        raw = read('manifest.json', MAX_BYTES)
        m.require(m.sha(raw) == expected, 'source bundle anchor mismatch')
        manifest = strict_json(raw); claims.obj(manifest, 'schema files')
        m.require(manifest['schema'] == 'geek-work-manuscript-claim-bundle-1' and
                  type(manifest['files']) is dict and 3 <= len(manifest['files']) <= 51,
                  'bundle manifest schema')
        for name, digest in manifest['files'].items():
            m.require(name in {'map.json', 'report.json', 'review.html'} or
                      re.fullmatch(r'(document|material)-[a-z0-9][a-z0-9-]{0,63}\.txt', name),
                      'bundle filename')
            claims.digest(digest)
        names = set()
        with os.scandir(fd) as entries:
            for entry in entries:
                names.add(entry.name)
                m.require(len(names) <= 52, 'bundle directory entry limit')
        m.require(names == set(manifest['files']) | {'manifest.json'}, 'bundle file set')
        blobs, total = {}, 0
        for name, digest in manifest['files'].items():
            limit = claims.MAX_TOTAL if name in {'report.json', 'review.html'} else claims.MAX_FILE if name.endswith('.txt') else MAX_BYTES
            blob = read(name, limit); total += len(blob)
            m.require(total <= claims.MAX_TOTAL, 'bundle total byte limit')
            m.require(m.sha(blob) == digest, 'bundle artifact hash mismatch')
            blobs[name] = blob
        m.require({'map.json', 'report.json', 'review.html'} <= set(blobs), 'required bundle files')
        mapping = strict_json(blobs['map.json']); files = claims.catalog(mapping)
        m.require(set(blobs) == set(files) | {'map.json', 'report.json', 'review.html'}, 'mapped file set')
        generated = claims.derive(mapping, {name: blobs[name] for name in files})
        m.require(all(blobs[name] == value for name, value in generated.items()), 'bundle replay mismatch')
        return mapping
    finally:
        os.close(fd)


def adapt(mapping, plan, expected_bundle):
    """Coordinator annotations bind roles; their semantic completeness is not checked."""
    claims.obj(plan, 'schema mode source_bundle_sha256 pairs')
    m.require(plan['schema'] == 'geek-work-claim-transport-plan-1' and
              plan['mode'] == 'exact_contract', 'plan schema/mode')
    m.require(plan['source_bundle_sha256'] == expected_bundle, 'plan source anchor mismatch')
    pairs = claims.rows(plan['pairs'], 16, 1)
    table, cards = {}, []
    source_claims = {row['id']: row for row in mapping['claims']}
    docs = {row['id']: row for row in mapping['documents']}
    materials = {row['id']: row for row in mapping['materials']}
    for pair in pairs:
        claims.obj(pair, 'id source_claim_id candidate_claim_id source_revision candidate_revision annotations')
        for key in ('id', 'source_claim_id', 'candidate_claim_id'):
            claims.ident(pair[key])
        revision(pair['source_revision']); revision(pair['candidate_revision'])
        m.require(pair['source_claim_id'] in source_claims, 'unknown source claim')
        source = source_claims[pair['source_claim_id']]
        annotation = pair['annotations']
        claims.obj(annotation, ' '.join((*ROLES, 'quantities')))
        for role in ROLES:
            atoms(annotation[role], table)
        quantities(annotation['quantities'])
        m.require(Counter(a['text'] for a in annotation['premise_atoms']) == Counter(source['assumptions']),
                  'premise annotations must cover declared assumptions exactly')
        m.require(bool(annotation['conclusion_atoms']), 'conclusion annotation required')
        quote = source['statement']['quote']
        for a in annotation['conclusion_atoms']:
            m.require(a['text'] in quote, 'conclusion annotation quote mismatch')
        available = [quote, source['scope'], *source['assumptions']]
        for role in ('domain_atoms', 'quantifier_atoms', 'negation_atoms'):
            for a in annotation[role]:
                m.require(any(a['text'] in text for text in available), 'annotation quote mismatch')
        for q in annotation['quantities']:
            m.require(any(q['exact_literal'] in text for text in available), 'quantity literal not quoted')
        evidence = [dict(binding=row, material=materials[row['citation']['material']]) for row in source['evidence']]
        binding = dict(document=docs[source['statement']['document']], statement=source['statement'], evidence=evidence)
        result = dict(**copy.deepcopy(annotation), scope=source['scope'],
                      reported_evidence_state=source['reported_evidence_state'],
                      evidence_ids=[m.sha(m.encoded(row)) for row in evidence],
                      non_claims=source['non_claims'], open_obligations=source['open_obligations'])
        contract(result, table)
        cards.append(dict(pair_id=pair['id'], source_claim_id=source['id'],
                          source_revision=pair['source_revision'], source=binding,
                          contract=result))
    for key in ('id', 'source_claim_id', 'candidate_claim_id'):
        unique(pairs, key)
    return cards, table


def prepared(bundle, bundle_sha, plan_raw, plan_sha):
    claims.digest(plan_sha); claims.digest(bundle_sha)
    m.require(len(plan_raw) <= MAX_BYTES, 'transport byte limit')
    m.require(m.sha(plan_raw) == plan_sha, 'plan anchor mismatch')
    plan = strict_json(plan_raw)
    cards, table = adapt(snapshot(bundle, bundle_sha), plan, bundle_sha)
    return plan, cards, table


def template(bundle, bundle_sha, plan_raw, plan_sha):
    """Create a bounded candidate template. This does not authorize its use as baseline."""
    plan, cards, _ = prepared(bundle, bundle_sha, plan_raw, plan_sha)
    result = dict(schema='geek-work-claim-transport-candidate-1', source_bundle_sha256=bundle_sha,
                  plan_sha256=plan_sha, cards=[])
    for pair, source in zip(plan['pairs'], cards):
        text = source['source']['statement']['quote']
        result['cards'].append(dict(id=pair['candidate_claim_id'], revision=pair['candidate_revision'],
            source=source['source'], contract=source['contract'], proof_reference=None,
            statement=dict(text=text, sha256=m.sha(text.encode()), start=0, end=len(text), quote=text)))
    m.require(len(plan_raw) + len(m.encoded(result)) <= MAX_BYTES, 'transport byte limit')
    return result


def normalized(value):
    """Only conjunct/evidence/obligation ordering is ignored; strings stay byte exact."""
    return {key: sorted(rows, key=lambda row: row['id']) if key in (*ROLES, 'quantities')
            else sorted(rows) if key in ('evidence_ids', 'non_claims', 'open_obligations')
            else rows for key, rows in value.items()}


def compare(source, candidate):
    a, b = normalized(source), normalized(candidate)
    changes = []
    for role in ROLES:
        if a[role] != b[role]:
            old = {row['id'] for row in a[role]}; new = {row['id'] for row in b[role]}
            category = {'premise_atoms': 'premise_changed', 'conclusion_atoms': 'conclusion_changed',
                        'domain_atoms': 'scope_or_domain_changed', 'quantifier_atoms': 'quantifier_or_negation_changed',
                        'negation_atoms': 'quantifier_or_negation_changed'}[role]
            changes.append(category)
            if role == 'premise_atoms' and old - new: changes.append('premise_removed')
            if new - old: changes.append('unreviewed_atom')
    for key, category in [('scope', 'scope_or_domain_changed'), ('quantities', 'quantity_or_unit_changed'),
                          ('reported_evidence_state', 'evidence_state_changed'), ('evidence_ids', 'evidence_binding_changed'),
                          ('non_claims', 'non_claim_changed'), ('open_obligations', 'open_obligation_changed')]:
        if a[key] != b[key]: changes.append(category)
    for key, category in [('non_claims', 'non_claim_removed'), ('open_obligations', 'open_obligation_removed')]:
        if set(a[key]) - set(b[key]): changes.append(category)
    return changes


def check(bundle, bundle_sha, plan_raw, plan_sha, candidate_raw):
    """Three outcomes, all four assurance flags false, including malformed input."""
    try:
        m.require(len(plan_raw) + len(candidate_raw) <= MAX_BYTES, 'transport byte limit')
        plan, source_cards, table = prepared(bundle, bundle_sha, plan_raw, plan_sha)
        candidate = strict_json(candidate_raw)
        claims.obj(candidate, 'schema source_bundle_sha256 plan_sha256 cards')
        m.require(candidate['schema'] == 'geek-work-claim-transport-candidate-1', 'candidate schema')
        m.require(candidate['source_bundle_sha256'] == bundle_sha and candidate['plan_sha256'] == plan_sha,
                  'candidate baseline substitution')
        rows = claims.rows(candidate['cards'], 16, 1)
        for row in rows:
            claims.obj(row, 'id revision source statement contract proof_reference')
            claims.ident(row['id']); revision(row['revision'])
        unique(rows, 'id')
        by_id = {row['id']: row for row in rows}
        m.require(set(by_id) == {p['candidate_claim_id'] for p in plan['pairs']}, 'candidate pair coverage')
        results = []
        for pair, original in zip(plan['pairs'], source_cards):
            card = by_id[pair['candidate_claim_id']]
            m.require(card['revision'] == pair['candidate_revision'], 'candidate revision mismatch')
            m.require(m.encoded(card['source']) == m.encoded(original['source']),
                      'candidate source binding substitution')
            contract(card['contract'], table)
            s = card['statement']; claims.obj(s, 'text sha256 start end quote')
            claims.text(s['text']); claims.text(s['quote']); claims.digest(s['sha256'])
            m.require(m.sha(s['text'].encode()) == s['sha256'], 'candidate statement hash')
            m.require(type(s['start']) is int and type(s['end']) is int and
                      0 <= s['start'] < s['end'] <= len(s['text']), 'candidate statement offsets')
            m.require(s['text'][s['start']:s['end']] == s['quote'], 'candidate quote mismatch')
            changes = compare(original['contract'], card['contract'])
            if s['quote'] != original['source']['statement']['quote']:
                changes.append('selected_statement_changed')
            if card['proof_reference'] is not None:
                claims.text(card['proof_reference']); changes.append('unverified_proof_reference')
            results.append(dict(pair_id=pair['id'], source_claim_id=pair['source_claim_id'],
                                candidate_claim_id=card['id'], source_revision=pair['source_revision'],
                                candidate_revision=card['revision'], changes=sorted(set(changes)),
                                source=original['source'], candidate_statement=s))
        return report('review_required' if any(r['changes'] for r in results) else 'contract_preserved',
                      source_bundle_sha256=bundle_sha, plan_sha256=plan_sha,
                      candidate_sha256=m.sha(candidate_raw), selected_pairs=len(results), pairs=results)
    except (ValueError, TypeError, KeyError, UnicodeError, OSError) as error:
        return report('invalid_input', reason=str(error), selected_pairs=0, pairs=[])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('template', 'check'))
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        plan = m.read(args.plan, MAX_BYTES)
        if args.action == 'template':
            result = template(args.bundle, args.source_sha256, plan, args.plan_sha256)
        else:
            m.require(args.candidate is not None, 'candidate required')
            result = check(args.bundle, args.source_sha256, plan, args.plan_sha256,
                           m.read(args.candidate, MAX_BYTES))
    except (ValueError, TypeError, KeyError, UnicodeError, OSError) as error:
        result = report('invalid_input', reason=str(error), selected_pairs=0, pairs=[])
    with args.output.open('xb') as stream:
        stream.write(m.encoded(result))
    return {'contract_preserved': 0, 'review_required': 1, 'invalid_input': 2}.get(result.get('status'), 0)


if __name__ == '__main__':
    raise SystemExit(main())
