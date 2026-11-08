"""Pinned real-source pilot: data replay only, not a fresh Lean audit."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]/'examples/claim-transport-orbit'
ANCHOR = '2460bed9bc5d2c4c98fdee47058d9e737b8dc61c20cb75f848946440ef666951'
spec = importlib.util.spec_from_file_location('orbit_pilot_replay', ROOT/'replay.py')
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


class OrbitPilotTests(unittest.TestCase):
    def test_five_real_source_cases_and_false_assurances(self):
        result = pilot.replay(ROOT, ANCHOR)
        self.assertEqual(result['status'], 'reproduced')
        self.assertEqual({r['case']: r['status'] for r in result['cases']}, pilot.CASES)
        self.assertEqual(result['reported_evidence_state'], 'source_only')
        for flag in pilot.t.FLAGS:
            self.assertIs(result[flag], False)

    def test_coordinator_anchor_is_required(self):
        with self.assertRaisesRegex(ValueError, 'manifest anchor'):
            pilot.replay(ROOT, '0'*64)

    def test_mutated_source_and_report_refused(self):
        for filename in ('source-bundle/material-lean-source.txt', 'reports/preserved.json'):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)/'pilot'; shutil.copytree(ROOT, root)
                path = root/filename; path.write_bytes(path.read_bytes()+b' ')
                with self.assertRaisesRegex(ValueError, 'file hash'):
                    pilot.replay(root, ANCHOR)
