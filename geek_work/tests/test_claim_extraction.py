import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import geek_work_claim_extraction as e

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / 'geek_work/examples/claim-extraction-orbit'


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.pins = json.loads((EXAMPLE / 'pins.json').read_bytes())
        self.source = (ROOT / self.pins['source_path'].replace('digital-brain/', 'geek_work/')).read_bytes()
        self.expected_raw = (EXAMPLE / 'expectations.json').read_bytes()
        self.expected = json.loads(self.expected_raw)
        self.record = json.loads((EXAMPLE / 'orbit-needs-context.json').read_bytes())

    def run_check(self, **kw):
        result = e.check(kw.get('source', self.source), kw.get('source_sha', self.pins['source_sha256']),
                         kw.get('expected_raw', self.expected_raw), kw.get('expected_sha', self.pins['expectations_sha256']),
                         kw.get('raw', e.m.encoded(self.record)))
        for flag in e.FLAGS:
            self.assertIs(result[flag], False)
        return result

    def invalid(self, reason=None, **kw):
        result = self.run_check(**kw)
        self.assertEqual(result['status'], 'invalid_input', result)
        if reason:
            self.assertEqual(result['reason'], reason)
        return result

    def test_orbit_eight_bindings_needs_context(self):
        result = self.run_check()
        self.assertEqual(result['status'], 'needs_context')
        self.assertEqual(result['atom_binding_count'], 8)
        self.assertEqual(result['editorial_state'], 'needs_context')
        self.assertEqual(self.record['contract']['quantities'][0]['unit_interpretation'], 'unknown')

    def test_reports_byte_replay(self):
        for name in ('orbit-needs-context', 'orbit-invalid-promotion'):
            result = self.run_check(raw=(EXAMPLE / (name+'.json')).read_bytes())
            self.assertEqual(e.m.encoded(result), (EXAMPLE / (name+'.report.json')).read_bytes())

    def test_ready_promotion(self):
        self.record['editorial_state'] = 'ready_for_transport'
        self.invalid('mandatory_unresolved_question_incompatible_with_ready_for_transport')

    def test_deleting_or_resolving_pinned_question_cannot_enable_ready(self):
        original = copy.deepcopy(self.record)
        for mode in ('delete', 'resolve', 'optional'):
            with self.subTest(mode=mode):
                self.record = copy.deepcopy(original)
                q = self.record['unresolved_questions'][0]
                if mode == 'delete': self.record['unresolved_questions'] = []
                if mode == 'resolve': q['resolution'] = 'I decided this is resolved.'
                if mode == 'optional': q['required_before_transport'] = False
                self.record['editorial_state'] = 'ready_for_transport'
                self.invalid('mandatory_unresolved_question_incompatible_with_ready_for_transport')

    def test_draft_with_mandatory_issue(self):
        self.record['editorial_state'] = 'draft'
        self.invalid('mandatory_unresolved_question_requires_needs_context')

    def test_changed_question_requires_review(self):
        self.record['unresolved_questions'][0]['resolution'] = 'Unapproved assertion'
        self.assertIn('unresolved_questions_changed', self.run_check()['differences'])

    def test_evidence_promotion(self):
        self.record['reported_evidence_state'] = 'formal_reported'
        self.assertEqual(self.run_check()['status'], 'review_required')
        self.record['reported_evidence_state'] = 'checked_here'
        self.invalid('reported_evidence_state')

    def test_all_existing_source_states_can_be_inherited(self):
        for state in sorted(e.c.STATES):
            with self.subTest(state=state):
                self.record['reported_evidence_state'] = state
                expected = copy.deepcopy(self.expected); expected['reported_evidence_state'] = state
                raw = e.m.encoded(expected)
                self.assertEqual(self.run_check(expected_raw=raw, expected_sha=e.m.sha(raw))['status'], 'needs_context')

    def test_external_source_pin(self):
        self.invalid('external_source_hash_mismatch', source=self.source+b' ')
        self.invalid('external_source_hash_mismatch', source_sha='0'*64)

    def test_external_expectations_pin(self):
        self.invalid('external_expectations_hash_mismatch', expected_raw=self.expected_raw+b' ')
        self.invalid('external_expectations_hash_mismatch', expected_sha='0'*64)

    def test_candidate_cannot_change_snapshot_metadata(self):
        self.record['source_snapshot']['sha256'] = '0'*64
        self.invalid('source_snapshot_binding')

    def test_unicode_not_byte_offset(self):
        s = self.record['contract']['premise_atoms'][0]['quote_span']
        s['start_char'] = len(self.source.decode()[:s['start_char']].encode())
        self.invalid()

    def test_quote_shift(self):
        self.record['contract']['premise_atoms'][0]['quote_span']['start_char'] += 1
        self.invalid('quote_mismatch')

    def test_boolean_offset(self):
        self.record['selected_span']['start_char'] = True
        self.invalid('span_offsets')

    def test_atom_hash(self):
        self.record['contract']['premise_atoms'][0]['text_sha256'] = '0'*64
        self.invalid('atom_hash_mismatch')

    def test_rebound_id_even_with_valid_source_and_hash(self):
        first = self.record['contract']['premise_atoms'][0]
        replacement = copy.deepcopy(self.record['contract']['premise_atoms'][1])
        replacement['atom_id'] = first['atom_id']
        self.record['contract']['premise_atoms'] = [replacement]
        self.invalid('atom_id_rebinding')

    def test_duplicate_atom(self):
        self.record['contract']['premise_atoms'].append(copy.deepcopy(self.record['contract']['premise_atoms'][0]))
        self.invalid('duplicate atom_id')

    def test_missing_condition_relative_to_ledger(self):
        self.record['contract']['premise_atoms'].pop(1)
        row = self.record['coverage_checks'][1]
        row['extracted_atom_ids'] = []
        row['finding'] = 'missing_extracted_atom'
        result = self.run_check()
        self.assertEqual(result['status'], 'review_required')
        self.assertIn('missing_extracted_atom:premise_atoms', result['differences'])
        self.assertEqual(row['source_observation'], 'condition_present')

    def test_deleted_coverage(self):
        self.record['coverage_checks'].pop()
        self.assertIn('coverage_checks_changed', self.run_check()['differences'])

    def test_absence_without_inspected_scope(self):
        self.record['coverage_checks'][-2]['inspected_spans'] = []
        self.invalid('absence_without_inspection')

    def test_absent_condition_cannot_have_fictitious_atom(self):
        self.record['coverage_checks'][-2]['extracted_atom_ids'] = ['real-parameters']
        self.invalid('absent_or_uninspected_has_atom')

    def test_numeric_literal_binding(self):
        self.record['contract']['quantities'][0]['exact_literal'] = '0.25'
        self.invalid('numeric_literal_mismatch')

    def test_number_span_must_stay_in_selected_quote(self):
        q = self.record['contract']['quantities'][0]
        text = self.source.decode(); a = text.index('0')
        q['exact_literal'] = '0'; q['literal_span'] = dict(start_char=a,end_char=a+1,quote='0')
        self.invalid('span_outside_selected_source')

    def test_unknown_is_not_dimensionless(self):
        self.record['contract']['quantities'][0]['unit_interpretation'] = 'dimensionless'
        self.assertIn('quantities_changed', self.run_check()['differences'])

    def test_unit_requires_quote(self):
        q = self.record['contract']['quantities'][0]
        q['unit_raw'] = 'seconds'
        self.invalid()

    def test_no_normalization_of_unknown_unit(self):
        self.record['contract']['quantities'][0]['unit_canonical'] = 'dimensionless'
        self.invalid('unknown_unit_normalized')

    def test_nonclaims_cannot_disappear(self):
        self.record['contract']['non_claims'] = []
        self.assertIn('non_claims_changed', self.run_check()['differences'])

    def test_all_ten_checklist_entries_required(self):
        self.record['checklist'].pop()
        self.invalid('ten_checklist_items_required')

    def test_assurance_flags_cannot_be_truthy_or_integer(self):
        for value in (True, 0, 1):
            for flag in e.FLAGS:
                with self.subTest(value=value, flag=flag):
                    self.record['assurances'] = {f:False for f in e.FLAGS}
                    self.record['assurances'][flag] = value
                    self.invalid('assurance_promotion')

    def test_strict_json_and_schema(self):
        for raw in (b'{"x":0,"x":1}', b'{"x":NaN}', b'{"x":1.0}', b'['*40+b']'*40, b'\xff'):
            with self.subTest(raw=raw): self.invalid(raw=raw)
        self.record['extra'] = 'unexpected'
        self.invalid()

    def test_limits(self):
        self.invalid('combined_byte_limit', raw=b' '*(e.MAX_BYTES+1))
        self.invalid('source_byte_limit', source=b'a'*(e.MAX_SOURCE+1))
        self.record['contract']['premise_atoms'] *= 9
        self.invalid()

    def test_source_utf8_and_nul(self):
        for source in (b'\xff', b'a\x00b'):
            self.invalid(source=source, source_sha=e.m.sha(source))

    def test_order_of_roles_is_not_significant(self):
        self.record['contract']['premise_atoms'].reverse()
        self.record['coverage_checks'].reverse()
        self.assertEqual(self.run_check()['status'], 'needs_context')

    def test_clean_synthetic_editorial_case_does_not_promote(self):
        # Separately pinned fixture: editorial questions have been removed by its coordinator.
        # This is not a resolution of the real orbit unit question.
        expected = copy.deepcopy(self.expected)
        for obj in (expected, self.record):
            obj['unresolved_questions'] = []
            obj['coverage_checks'] = obj['coverage_checks'][:-1]
        for row in self.record['checklist']: row['state'] = 'checked'
        raw = e.m.encoded(expected)
        for state in ('draft', 'ready_for_transport'):
            self.record['editorial_state'] = state
            result = self.run_check(expected_raw=raw, expected_sha=e.m.sha(raw))
            self.assertEqual(result['status'], 'record_consistent')
            self.assertEqual(result['editorial_state'], state)

    def test_pinned_example_files(self):
        for name, digest in self.pins['files'].items():
            self.assertEqual(e.m.sha((EXAMPLE/name).read_bytes()), digest)

    def test_required_question_flag_must_be_boolean(self):
        self.record['unresolved_questions'][0]['required_before_transport'] = 0
        self.invalid('required_flag_type')

    def test_coverage_evidence_must_be_in_inspected_span(self):
        row = self.record['coverage_checks'][0]
        row['inspected_spans'] = [self.record['contract']['premise_atoms'][1]['quote_span']]
        self.invalid('evidence_not_inspected')

    def test_mismatched_scope_is_reviewed(self):
        self.record['contract']['scope'] = 'All real inputs without restrictions'
        self.assertIn('scope_changed', self.run_check()['differences'])

    def test_unchecked_checklist_prevents_ready_even_without_questions(self):
        expected = copy.deepcopy(self.expected)
        expected['unresolved_questions'] = []
        self.record['unresolved_questions'] = []
        self.record['editorial_state'] = 'ready_for_transport'
        raw = e.m.encoded(expected)
        self.invalid('incomplete_editorial_checks_incompatible_with_ready_for_transport',
                     expected_raw=raw, expected_sha=e.m.sha(raw))

    def test_cli_exclusive_and_unsafe_input(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder); output = folder/'report.json'
            cmd = [sys.executable, str(ROOT/'geek_work/tools/geek_work_claim_extraction.py'),
                   '--source-snapshot', str(ROOT/self.pins['source_path'].replace('digital-brain/', 'geek_work/')), '--source-sha256',self.pins['source_sha256'],
                   '--expectations',str(EXAMPLE/'expectations.json'),'--expectations-sha256',self.pins['expectations_sha256'],
                   '--record',str(EXAMPLE/'orbit-needs-context.json'),'--output',str(output)]
            first = subprocess.run(cmd,capture_output=True,timeout=10)
            self.assertEqual(first.returncode,1,first.stderr)
            raw = output.read_bytes()
            self.assertEqual(raw,(EXAMPLE/'orbit-needs-context.report.json').read_bytes())
            again = subprocess.run(cmd,capture_output=True,timeout=10)
            self.assertNotEqual(again.returncode,0); self.assertEqual(output.read_bytes(),raw)
            for name in ('link','fifo'):
                path = folder/name
                if name == 'link': path.symlink_to(EXAMPLE/'orbit-needs-context.json')
                else: os.mkfifo(path)
                next_cmd = cmd.copy(); next_cmd[next_cmd.index('--record')+1] = str(path)
                next_cmd[-1] = str(folder/(name+'.report.json'))
                result = subprocess.run(next_cmd,capture_output=True,timeout=10)
                self.assertEqual(result.returncode,2,result.stderr)
                body = json.loads(Path(next_cmd[-1]).read_bytes())
                self.assertEqual(body['status'],'invalid_input')
                self.assertTrue(all(body[f] is False for f in e.FLAGS))


if __name__ == '__main__':
    unittest.main()
