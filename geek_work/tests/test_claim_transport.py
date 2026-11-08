import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import geek_work_claim_transport as t


def atom(identifier, text):
    return dict(id=identifier, text=text, sha256=t.m.sha(text.encode()))


class ClaimTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.quote = 'For every n, the orbit converges to 1/4; no rate is claimed.'
        self.text = 'Header\r\n' + self.quote + '\r\nOther prose.'
        doc = self.text.encode()
        (self.root / 'paper.txt').write_bytes(doc)
        start = self.text.index(self.quote)
        self.mapping = dict(schema='geek-work-manuscript-claim-map-1',
            documents=[dict(id='paper', path='paper.txt', sha256=t.m.sha(doc))], materials=[],
            claims=[dict(id='limit', statement=dict(document='paper', start=start,
                end=start+len(self.quote), quote=self.quote), reported_evidence_state='hypothesis',
                scope='0 ≤ F₀ ≤ 1', assumptions=['γ < γc', '0 ≤ F₀ ≤ 1'],
                non_claims=['No rate'], open_obligations=['Kernel proof'], evidence=[])])
        raw = t.m.encoded(self.mapping); (self.root / 'map.json').write_bytes(raw)
        self.bundle = self.root / 'bundle'
        self.anchor = t.claims.prepare(self.root / 'map.json', t.m.sha(raw), self.root,
                                       self.root, self.bundle)['manifest_sha256']
        self.plan = dict(schema='geek-work-claim-transport-plan-1', mode='exact_contract',
            source_bundle_sha256=self.anchor, pairs=[dict(id='pair', source_claim_id='limit',
                candidate_claim_id='transported-limit', source_revision=1, candidate_revision=1,
                annotations=dict(premise_atoms=[atom('noise-bound', 'γ < γc'), atom('input-bound', '0 ≤ F₀ ≤ 1')],
                    conclusion_atoms=[atom('limit-conclusion', 'the orbit converges to 1/4')],
                    domain_atoms=[atom('input-bound', '0 ≤ F₀ ≤ 1')],
                    quantifier_atoms=[atom('all-n', 'For every n')],
                    negation_atoms=[atom('no-rate', 'no rate is claimed')],
                    quantities=[dict(id='limit-value', symbol='F∞', exact_literal='1/4', unit='dimensionless')]))])
        self.raw = t.m.encoded(self.plan); self.plan_sha = t.m.sha(self.raw)
        self.candidate = t.template(self.bundle, self.anchor, self.raw, self.plan_sha)

    def run_check(self, candidate=None, **kwargs):
        result = t.check(kwargs.get('bundle', self.bundle), kwargs.get('anchor', self.anchor),
                         kwargs.get('plan', self.raw), kwargs.get('plan_sha', self.plan_sha),
                         kwargs.get('raw', t.m.encoded(self.candidate if candidate is None else candidate)))
        for flag in t.FLAGS:
            self.assertIs(result[flag], False)
        return result

    def changes(self, candidate):
        result = self.run_check(candidate)
        self.assertEqual(result['status'], 'review_required', result)
        return result['pairs'][0]['changes']

    def test_exact_and_reordered_conjuncts(self):
        self.assertEqual(self.run_check()['status'], 'contract_preserved')
        self.candidate['cards'][0]['contract']['premise_atoms'].reverse()
        self.assertEqual(self.run_check()['status'], 'contract_preserved')

    def test_removed_noise_bound(self):
        self.candidate['cards'][0]['contract']['premise_atoms'].pop(0)
        self.assertIn('premise_removed', self.changes(self.candidate))

    def test_strict_boundary_changed_with_new_id(self):
        self.candidate['cards'][0]['contract']['domain_atoms'] = [atom('strict-domain', '0 ≤ F₀ < 1')]
        self.assertIn('scope_or_domain_changed', self.changes(self.candidate))

    def test_limit_to_equality_and_quantifier_negation_changes(self):
        for role, value, expected in [
            ('conclusion_atoms', [atom('equality', 'the orbit equals 1/4')], 'conclusion_changed'),
            ('quantifier_atoms', [atom('some-n', 'For some n')], 'quantifier_or_negation_changed'),
            ('negation_atoms', [], 'quantifier_or_negation_changed')]:
            with self.subTest(role=role):
                candidate = copy.deepcopy(self.candidate)
                candidate['cards'][0]['contract'][role] = value
                self.assertIn(expected, self.changes(candidate))

    def test_atom_rebinding_and_wrong_hash_invalid(self):
        for rehash in (True, False):
            candidate = copy.deepcopy(self.candidate)
            a = candidate['cards'][0]['contract']['premise_atoms'][0]
            a['text'] = 'γ ≥ γc'
            if rehash: a['sha256'] = t.m.sha(a['text'].encode())
            self.assertEqual(self.run_check(candidate)['status'], 'invalid_input')

    def test_quantity_literal_unit_and_state_changes(self):
        for field, value in [('exact_literal', '0.25'), ('unit', 'seconds')]:
            candidate = copy.deepcopy(self.candidate)
            candidate['cards'][0]['contract']['quantities'][0][field] = value
            self.assertIn('quantity_or_unit_changed', self.changes(candidate))
        self.candidate['cards'][0]['contract']['reported_evidence_state'] = 'formal_reported'
        self.assertIn('evidence_state_changed', self.changes(self.candidate))

    def test_evidence_and_obligations(self):
        for key, value, expected in [('evidence_ids', ['a'*64], 'evidence_binding_changed'),
                                    ('non_claims', [], 'non_claim_removed'),
                                    ('open_obligations', [], 'open_obligation_removed')]:
            candidate = copy.deepcopy(self.candidate)
            candidate['cards'][0]['contract'][key] = value
            self.assertIn(expected, self.changes(candidate))

    def test_lean_name_never_justifies_changed_contract(self):
        self.candidate['cards'][0]['proof_reference'] = 'QuantumNoisyBBPSSWCritical.some_theorem'
        self.candidate['cards'][0]['contract']['premise_atoms'] = []
        changes = self.changes(self.candidate)
        self.assertIn('premise_removed', changes)
        self.assertIn('unverified_proof_reference', changes)

    def test_candidate_cannot_choose_baseline_or_rewrite_source(self):
        for key in ('plan_sha256', 'source_bundle_sha256'):
            candidate = copy.deepcopy(self.candidate); candidate[key] = '0'*64
            self.assertEqual(self.run_check(candidate)['status'], 'invalid_input')
        self.candidate['cards'][0]['source']['document']['sha256'] = '0'*64
        self.assertEqual(self.run_check()['status'], 'invalid_input')
        self.assertEqual(self.run_check(anchor='0'*64)['status'], 'invalid_input')
        self.assertEqual(self.run_check(plan_sha='0'*64)['status'], 'invalid_input')

    def test_missing_extra_duplicate_pairs_and_revision(self):
        for mode in ('missing', 'extra', 'duplicate', 'revision'):
            candidate = copy.deepcopy(self.candidate)
            if mode == 'missing': candidate['cards'] = []
            if mode in ('extra', 'duplicate'):
                candidate['cards'].append(copy.deepcopy(candidate['cards'][0]))
                if mode == 'extra': candidate['cards'][1]['id'] = 'unknown'
            if mode == 'revision': candidate['cards'][0]['revision'] = True
            self.assertEqual(self.run_check(candidate)['status'], 'invalid_input', mode)

    def test_statement_quote_hash_offsets(self):
        for field, value in [('quote', 'bad'), ('sha256', '0'*64), ('start', True), ('end', 0)]:
            candidate = copy.deepcopy(self.candidate); candidate['cards'][0]['statement'][field] = value
            self.assertEqual(self.run_check(candidate)['status'], 'invalid_input')

    def test_selected_quote_change_requires_review(self):
        s = self.candidate['cards'][0]['statement']; s['text'] = 'The orbit equals 1/4.'
        s.update(quote=s['text'], start=0, end=len(s['text']), sha256=t.m.sha(s['text'].encode()))
        self.assertIn('selected_statement_changed', self.changes(self.candidate))

    def test_unselected_prose_is_explicitly_not_certified(self):
        s = self.candidate['cards'][0]['statement']; s['text'] += '\nEverything is proved!'
        s['sha256'] = t.m.sha(s['text'].encode())
        result = self.run_check()
        self.assertEqual(result['status'], 'contract_preserved')
        self.assertFalse(result['source_extraction_complete'])
        self.assertFalse(result['semantic_equivalence_verified'])

    def test_plan_annotations_cannot_drop_assumptions_or_invent_quote(self):
        for role in ('premise_atoms', 'conclusion_atoms'):
            plan = copy.deepcopy(self.plan)
            plan['pairs'][0]['annotations'][role] = [] if role == 'premise_atoms' else [atom('fake', 'invented')]
            raw = t.m.encoded(plan)
            self.assertEqual(self.run_check(plan=raw, plan_sha=t.m.sha(raw))['status'], 'invalid_input')

    def test_budget_atoms_pairs_text_bytes(self):
        candidate = copy.deepcopy(self.candidate)
        candidate['cards'][0]['contract']['premise_atoms'] = [atom('a-'+str(i), str(i)) for i in range(33)]
        self.assertEqual(self.run_check(candidate)['status'], 'invalid_input')
        candidate = copy.deepcopy(self.candidate); candidate['cards'] *= 17
        self.assertEqual(self.run_check(candidate)['status'], 'invalid_input')
        candidate = copy.deepcopy(self.candidate); candidate['cards'][0]['contract']['scope'] = 'x'*4001
        self.assertEqual(self.run_check(candidate)['status'], 'invalid_input')
        self.assertEqual(self.run_check(raw=b' '*t.MAX_BYTES)['status'], 'invalid_input')

    def test_strict_json_duplicate_float_nan_depth_and_bad_utf8(self):
        for raw in (b'{"schema":1,"schema":2}', b'{"x":0.25}', b'{"x":NaN}',
                    b'['*33+b']'*33, b'\xff'):
            self.assertEqual(self.run_check(raw=raw)['status'], 'invalid_input')

    def test_duplicate_atoms_unknown_fields_and_numeric_literal_type(self):
        for mode in ('atom', 'field', 'float'):
            candidate = copy.deepcopy(self.candidate); card = candidate['cards'][0]
            if mode == 'atom': card['contract']['premise_atoms'] *= 2
            if mode == 'field': card['contract']['semantic_equivalence_verified'] = True
            if mode == 'float': card['contract']['quantities'][0]['exact_literal'] = 0.25
            self.assertEqual(self.run_check(candidate)['status'], 'invalid_input')

    def test_changed_source_and_resealed_historical_report(self):
        path = self.bundle / 'report.json'; original = path.read_bytes(); path.write_bytes(original+b' ')
        self.assertEqual(self.run_check()['status'], 'invalid_input')
        manifest = json.loads((self.bundle/'manifest.json').read_bytes())
        manifest['files']['report.json'] = t.m.sha(path.read_bytes())
        raw = t.m.encoded(manifest); (self.bundle/'manifest.json').write_bytes(raw)
        # Even a coordinator-pinned new manifest cannot bypass old claim-map replay.
        with self.assertRaisesRegex(ValueError, 'replay mismatch'): t.snapshot(self.bundle, t.m.sha(raw))

    def test_bundle_symlinks_fifo_and_extra_files(self):
        (self.root/'linked').symlink_to(self.bundle, target_is_directory=True)
        self.assertEqual(self.run_check(bundle=self.root/'linked')['status'], 'invalid_input')
        path = self.bundle/'document-paper.txt'; path.unlink(); os.mkfifo(path)
        self.assertEqual(self.run_check()['status'], 'invalid_input')

    def test_cli_exclusive_output_and_status_codes(self):
        (self.root/'plan.json').write_bytes(self.raw)
        (self.root/'candidate.json').write_bytes(t.m.encoded(self.candidate))
        cmd = [sys.executable, t.__file__, 'check', '--bundle', str(self.bundle),
               '--source-sha256', self.anchor, '--plan', str(self.root/'plan.json'),
               '--plan-sha256', self.plan_sha, '--candidate', str(self.root/'candidate.json'),
               '--output', str(self.root/'report.json')]
        run = subprocess.run(cmd, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        first = (self.root/'report.json').read_bytes()
        self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
        self.assertEqual((self.root/'report.json').read_bytes(), first)
        (self.root/'report.json').unlink()
        self.candidate['cards'][0]['contract']['premise_atoms'] = []
        (self.root/'candidate.json').write_bytes(t.m.encoded(self.candidate))
        self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 1)
        (self.root/'report.json').unlink(); (self.root/'candidate.json').write_bytes(b'bad json')
        self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)

    def test_material_origin_and_evidence_binding_preserved(self):
        material = b'Historical reference, not a proof.'
        (self.root/'reference.txt').write_bytes(material)
        mapping = copy.deepcopy(self.mapping)
        mapping['materials'] = [dict(id='reference', path='reference.txt', sha256=t.m.sha(material),
            kind='reference_material', origin=dict(repository='declared-repository', commit='b'*40))]
        claim = mapping['claims'][0]; claim['reported_evidence_state'] = 'reference_only'
        claim['evidence'] = [dict(citation=dict(material='reference', start=0, end=len(material),
                                               quote=material.decode()), declaration=None)]
        raw = t.m.encoded(mapping); (self.root/'second-map.json').write_bytes(raw)
        bundle = self.root/'second-bundle'
        anchor = t.claims.prepare(self.root/'second-map.json', t.m.sha(raw), self.root, self.root, bundle)['manifest_sha256']
        plan = copy.deepcopy(self.plan); plan['source_bundle_sha256'] = anchor
        raw = t.m.encoded(plan); sha = t.m.sha(raw)
        candidate = t.template(bundle, anchor, raw, sha)
        card = candidate['cards'][0]
        self.assertEqual(card['source']['evidence'][0]['material']['origin']['commit'], 'b'*40)
        self.assertEqual(len(card['contract']['evidence_ids']), 1)
        self.assertEqual(self.run_check(candidate, bundle=bundle, anchor=anchor, plan=raw, plan_sha=sha)['status'], 'contract_preserved')
        card['source']['evidence'][0]['material']['origin']['commit'] = 'c'*40
        self.assertEqual(self.run_check(candidate, bundle=bundle, anchor=anchor, plan=raw, plan_sha=sha)['status'], 'invalid_input')

    def test_wire_schema_statuses_and_conservative_flags(self):
        schema = json.loads((Path(t.__file__).parents[1]/'contracts/claim-transport/wire.schema.json').read_bytes())
        definitions = schema['$defs']
        self.assertEqual(set(definitions['contract']['required']), set(t.CONTRACT_FIELDS))
        for branch in definitions['report']['oneOf']:
            for flag in t.FLAGS:
                self.assertEqual(branch['properties'][flag], {'const': False})
        self.assertEqual(definitions['plan']['properties']['pairs']['maxItems'], 16)
        for role in t.ROLES:
            self.assertEqual(definitions['contract']['properties'][role]['maxItems'], 32)

    def test_boolean_source_offset_is_not_equal_to_integer(self):
        # Python treats True == 1; the wire binding must not.
        doc = 'x' + self.quote
        (self.root/'bool-paper.txt').write_text(doc)
        mapping = copy.deepcopy(self.mapping)
        mapping['documents'][0].update(path='bool-paper.txt', sha256=t.m.sha(doc.encode()))
        mapping['claims'][0]['statement'].update(start=1, end=1+len(self.quote))
        raw = t.m.encoded(mapping); (self.root/'bool-map.json').write_bytes(raw)
        bundle = self.root/'bool-bundle'
        anchor = t.claims.prepare(self.root/'bool-map.json', t.m.sha(raw), self.root, self.root, bundle)['manifest_sha256']
        plan = copy.deepcopy(self.plan); plan['source_bundle_sha256'] = anchor
        raw = t.m.encoded(plan); sha = t.m.sha(raw)
        candidate = t.template(bundle, anchor, raw, sha)
        candidate['cards'][0]['source']['statement']['start'] = True
        self.assertEqual(self.run_check(candidate, bundle=bundle, anchor=anchor, plan=raw, plan_sha=sha)['status'], 'invalid_input')

    def test_extra_directory_entries_refused(self):
        for i in range(53):
            (self.bundle/('extra-'+str(i))).write_bytes(b'')
        result = self.run_check()
        self.assertEqual(result['status'], 'invalid_input')
        self.assertIn('entry limit', result['reason'])
