"""Resource-budget draft pilot; structural comparison does not prove conservation."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]/'examples/claim-transport-budget'
ANCHOR = 'fdb0bf26aa13db9d57973a9614a4c2d4f492257b72d3d1d96d1ea88b7512a181'
spec = importlib.util.spec_from_file_location('budget_pilot_replay', ROOT/'replay.py')
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


class BudgetPilotTests(unittest.TestCase):
    def test_seven_cases_keep_hypothesis_and_false_assurances(self):
        result = pilot.replay(ROOT, ANCHOR)
        self.assertEqual({r['case']:r['status'] for r in result['cases']}, pilot.CASES)
        self.assertEqual(result['reported_evidence_state'], 'hypothesis')
        for flag in pilot.t.FLAGS:self.assertIs(result[flag],False)
        card=json.loads((ROOT/'candidates/preserved.json').read_text())['cards'][0]
        self.assertEqual(card['contract']['reported_evidence_state'],'hypothesis')
        self.assertEqual(len(card['contract']['premise_atoms']),7)
        self.assertEqual({q['unit'] for q in card['contract']['quantities']},{'compute_credit'})

    def test_independent_manifest_anchor(self):
        with self.assertRaisesRegex(ValueError,'manifest anchor'):
            pilot.replay(ROOT,'0'*64)

    def test_source_and_result_mutations_fail(self):
        for filename in ['source-bundle/material-budget-draft.txt','reports/preserved.json']:
            with self.subTest(filename=filename),tempfile.TemporaryDirectory() as temp:
                copy=Path(temp)/'pilot';shutil.copytree(ROOT,copy)
                p=copy/filename;p.write_bytes(p.read_bytes()+b' ')
                with self.assertRaisesRegex(ValueError,'file hash'):
                    pilot.replay(copy,ANCHOR)
