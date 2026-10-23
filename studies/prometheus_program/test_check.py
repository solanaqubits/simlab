import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('program_checker', ROOT / 'check.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / 'snapshot.json').read_text())

    def test_pristine_bundle(self):
        self.assertEqual(checker.check(ROOT)['status'], 'passed')

    def test_open_obligations(self):
        for key in self.data['obligations']:
            with self.subTest(key=key):
                d = copy.deepcopy(self.data)
                d['obligations'][key] = 'CLOSED'
                with self.assertRaises(ValueError):
                    checker.validate(d)

    def test_no_new_audit_or_scientific_claim(self):
        for key, value in [('new_scientific_verification', True), ('independent_audit', 'passed')]:
            d = copy.deepcopy(self.data)
            d[key] = value
            with self.assertRaises(ValueError):
                checker.validate(d)

    def test_historical_counts_not_aggregate(self):
        self.data['historical_epochs'][0]['declarations'] += 1
        with self.assertRaises(ValueError):
            checker.validate(self.data)

    def test_stage_mismatch(self):
        self.data['audits'][0]['stage'] = '281'
        with self.assertRaises(ValueError):
            checker.validate(self.data)

    def test_missing_limitations(self):
        self.data['audits'][0]['limitations'] = ''
        with self.assertRaises(ValueError):
            checker.validate(self.data)

    def test_coverage_not_rewritten(self):
        self.data['coverage_classification'] = '14/0/0'
        with self.assertRaises(ValueError):
            checker.validate(self.data)

    def test_mutated_bytes_fail_cli_even_with_optimization(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / 'bundle'
            shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns('__pycache__'))
            with (dst / 'LIMITS.md').open('a') as out:
                out.write('tampered')
            result = subprocess.run([sys.executable, '-B', '-O', str(dst / 'check.py')], capture_output=True)
            self.assertNotEqual(result.returncode, 0)

    def test_extra_private_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / 'bundle'
            shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns('__pycache__'))
            (dst / 'private.log').write_text('not exportable')
            with self.assertRaises(ValueError):
                checker.check(dst)


if __name__ == '__main__':
    unittest.main()
