"""Mutation tests of the public metadata boundary; no physical model is run."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import check


class PublicProjectionTests(unittest.TestCase):
    def setUp(self):
        self.data = check.load((check.ROOT / 'registry.json').read_bytes())

    def rejected(self, mutate):
        mutate(self.data)
        with self.assertRaises(ValueError):
            check.evaluate(self.data)

    def test_baseline(self):
        result = check.verify_bundle()
        self.assertEqual((result['claims'], result['scenarios'], result['rules']), (14, 38, 77))
        self.assertEqual(Counter(g['status'] for g in result['groups'].values()),
                         dict(blocked_requirements=11, unsupported_requirements=2, mismatch=13, metadata_match_only=2))
        self.assertFalse(result['physical_validation_established'])
        self.assertFalse(result['composable_security_established'])
        self.assertEqual(result['third_obligation'], 'OPEN')

    def test_six_mandatory_exclusions(self):
        result = check.evaluate(self.data)
        for group in ['geometry-long-short', 'repetition100-to-rs256', 'sparse-to-wire-throughput',
                      'nqkd-candidate-to-certified-skr', 'cd2-energy-to-timing-and-thermal',
                      'takl-conditional-to-qft-and-discovery']:
            with self.subTest(group=group):
                self.assertEqual(result['groups'][group]['status'], 'blocked_requirements')

    def test_unknown_is_not_false(self):
        result = check.evaluate(self.data)['groups']['cd2-to-calibrated-t0']
        self.assertEqual(result['requirement_status'], 'unknown')
        self.assertEqual(result['status'], 'unsupported_requirements')

    def test_duplicate_key(self):
        with self.assertRaises(ValueError): check.load(b'{"a": 1, "a": 2}')

    def test_nonfinite(self):
        for raw in [b'{"a": NaN}', b'{"a": Infinity}']:
            with self.assertRaises(ValueError): check.load(raw)

    def test_boolean_is_not_integer(self):
        with self.assertRaises(ValueError): check.typed('integer', True)
        self.assertFalse(check.same(True, 1))

    def test_exact_decimal(self):
        from decimal import Decimal
        self.assertEqual(check.typed('number', '0.010192'), Decimal(10192) / 1000000)
        for value in ['NaN', 'Infinity', '1e9999', 0.010192]:
            with self.assertRaises(ValueError): check.typed('number', value)

    def test_unit_mismatch(self):
        self.rejected(lambda d: next(iter(d['scenarios'][0]['fields'].values())).update(unit='wrong'))

    def test_scope_mismatch(self):
        self.rejected(lambda d: next(iter(d['scenarios'][0]['fields'].values())).update(scope='all devices'))

    def test_duplicate_scenario(self):
        self.rejected(lambda d: d['scenarios'].append(deepcopy(d['scenarios'][0])))

    def test_dangling_group(self):
        self.rejected(lambda d: d['claims'][0]['groups'].append('nonexistent'))

    def test_false_status_promotion(self):
        self.rejected(lambda d: d['expected_statuses']['geometry-long-short'].update(status='metadata_match_only'))

    def test_physical_promotion(self):
        self.rejected(lambda d: d['claims'][0].update(state='physically_verified'))

    def test_missing_claim(self):
        self.rejected(lambda d: d['claims'].pop())

    def test_editorial_boundary_preserved(self):
        self.rejected(lambda d: next(c for c in d['claims'] if c['id'] == 'NC05').update(coverage='existing_rule'))

    def test_source_path_escape(self):
        self.rejected(lambda d: d['formal_sources'][0].update(path='../secret'))

    def test_source_link_wrong_commit(self):
        self.rejected(lambda d: d['formal_sources'][0].update(url='https://github.com/solanaqubits/leanbook/blob/main/Verification/X.lean'))

    def test_duplicate_formal_source(self):
        self.rejected(lambda d: d['formal_sources'].__setitem__(1, deepcopy(d['formal_sources'][0])))

    def test_scope_promotion(self):
        self.rejected(lambda d: d['provenance'].update(export_kind='full_source_audit'))

    def test_bundle_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ['registry.json', 'check.py', 'test_check.py', 'README.md', 'LIMITS.md', 'MANIFEST.json']:
                shutil.copyfile(check.ROOT / name, root / name)
            (root / 'LIMITS.md').write_text('unrestricted claims')
            with self.assertRaises(ValueError): check.verify_bundle(root)

    def test_allowlist_injection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = check.load((check.ROOT / 'MANIFEST.json').read_bytes())
            manifest['files']['private-log.txt'] = '0' * 64
            (root / 'MANIFEST.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError): check.verify_bundle(root)


if __name__ == '__main__':
    unittest.main()
