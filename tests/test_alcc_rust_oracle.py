import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.alcc_rust_oracle import (
    RustOracle, OracleNotChecked, OracleMismatch, build, PROTOCOL,
)
from tools.alcc_normalization_bench import corpus, reference, run


class RustOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(os.environ.get('ALCC_RUST_BUILD', Path(cls.temp.name) / 'build'))
        cls.pin = (os.environ['ALCC_RUST_MANIFEST_SHA256'] if 'ALCC_RUST_BUILD' in os.environ
                   else build(cls.directory))
        cls.oracle = RustOracle(cls.directory, cls.pin)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.input = self.root / 'input with "quotes".txt'

    def check_terms(self, terms, expected=None):
        self.input.write_text(''.join(' '.join(map(str, t)) + '\n' for t in terms))
        return self.oracle.check(self.input, reference(terms) if expected is None else expected)

    def refusal(self, text, status):
        self.input.write_text(text)
        with self.assertRaises(OracleNotChecked) as caught:
            self.oracle.check(self.input, [])
        r = caught.exception.receipt
        self.assertFalse(r['checked'])
        self.assertEqual(r['status'], status)
        return r

    def test_all_nine_fixed_cases(self):
        for name, terms in corpus().items():
            with self.subTest(name=name):
                r = self.check_terms(terms)
                self.assertTrue(r['checked']); self.assertEqual(r['status'], 'MATCH')

    def test_deterministic_differential_cases(self):
        rng = random.Random(7919)
        for _ in range(40):
            terms = [[rng.randrange(4), rng.randrange(3), rng.randrange(2),
                      rng.randrange(-100, 101), rng.randrange(1, 20)]
                     for _ in range(rng.randrange(1, 45))]
            self.assertTrue(self.check_terms(terms)['checked'])

    def test_algebraic_metamorphisms(self):
        terms = corpus()['rational']
        expected = reference(terms)
        for modified in [list(reversed(terms)), terms + [[9, 9, 9, 0, 3]],
                         terms + [[8, 8, 8, 5, 7], [8, 8, 8, -5, 7]]]:
            self.assertTrue(self.check_terms(modified, expected)['checked'])

    def test_minimum_integer_refuses_without_panic(self):
        r = self.refusal(f'0 0 0 {-2**127} 1\n', 'RANGE_EXCEEDED')
        self.assertEqual(r['exit_code'], 3)

    def test_maximum_integer_accepted(self):
        self.assertTrue(self.check_terms([[0, 0, 0, 2**127-1, 1]])['checked'])

    def test_addition_and_denominator_overflow(self):
        for text in [f'0 0 0 {2**127-1} 1\n0 0 0 1 1\n',
                     f'0 0 0 1 {2**127-1}\n0 0 0 1 2\n']:
            self.refusal(text, 'RANGE_EXCEEDED')

    def test_integer_and_exponent_range(self):
        for text in [f'0 0 0 {2**127} 1\n', f'{2**64} 0 0 1 1\n']:
            self.refusal(text, 'RANGE_EXCEEDED')

    def test_invalid_input_is_not_mismatch(self):
        for text in ['0 0 0 1 0', '0 0 0 1 -1', '-1 0 0 1 2',
                     '0 0 0 nan 1', '1 2 3', '0 0 0 +1 1']:
            self.refusal(text, 'INVALID_INPUT')

    def test_input_and_term_limits(self):
        self.refusal(' ' * (1024**2 + 1), 'INPUT_LIMIT')
        self.refusal('0 0 0 0 1\n' * 4097, 'INPUT_LIMIT')

    def test_reference_mutation_detected(self):
        expected = reference(corpus()['rational'])
        expected[0][1] = '99'
        with self.assertRaises(OracleMismatch) as caught:
            self.check_terms(corpus()['rational'], expected)
        self.assertEqual(caught.exception.receipt['status'], 'REFERENCE_MISMATCH')

    def test_wrong_manifest_pin(self):
        with self.assertRaisesRegex(ValueError, 'pin'):
            RustOracle(self.directory, '0' * 64)

    def test_binary_tampering_detected(self):
        clone = self.root / 'copy'; clone.mkdir()
        for name in ('manifest.json', 'build.log', 'alcc-fraction-oracle'):
            shutil.copyfile(self.directory / name, clone / name)
        (clone / 'alcc-fraction-oracle').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'binding'):
            RustOracle(clone, self.pin)

    def fake_run(self, text, code):
        def result(command, **kw):
            kw['stdout'].write(text.encode())
            return SimpleNamespace(returncode=code)
        return result

    def test_protocol_corruption_is_not_checked(self):
        self.input.write_text('')
        cases = [('not json', 0),
                 (json.dumps(dict(protocol=PROTOCOL, status='RANGE_EXCEEDED')), 0),
                 (json.dumps(dict(protocol=PROTOCOL, status='OK', reference=[])), 3),
                 ('{"protocol":"x","protocol":"y"}', 0),
                 (json.dumps(dict(protocol=PROTOCOL, status='OK',
                                  reference=[[[True, 0, 0], '1', '1']])), 0)]
        for text, code in cases:
            with patch('tools.alcc_rust_oracle.subprocess.run', self.fake_run(text, code)):
                with self.assertRaises(OracleNotChecked):
                    self.oracle.check(self.input, [])

    def test_timeout_is_not_checked(self):
        self.input.write_text('')
        with patch('tools.alcc_rust_oracle.subprocess.run',
                   side_effect=subprocess.TimeoutExpired('oracle', 5)):
            with self.assertRaises(OracleNotChecked) as caught:
                self.oracle.check(self.input, [])
        self.assertEqual(caught.exception.receipt['status'], 'TIMEOUT')

    def test_signal_is_not_mismatch(self):
        self.input.write_text('')
        with patch('tools.alcc_rust_oracle.subprocess.run', self.fake_run('', -9)):
            with self.assertRaises(OracleNotChecked) as caught:
                self.oracle.check(self.input, [])
        self.assertEqual(caught.exception.receipt['status'], 'EXEC_CRASH')

    def test_refusal_stops_bench_before_lean(self):
        binary = self.root / 'lean'; binary.write_bytes(b'not executed')
        log = self.root / 'log'; log.write_text('fixture')
        refused = OracleNotChecked(dict(status='RANGE_EXCEEDED', checked=False))
        with patch.object(self.oracle, 'check', side_effect=refused), \
             patch('tools.alcc_normalization_bench.platform.platform', return_value='fixture'), \
             patch('tools.alcc_normalization_bench.platform.processor', return_value='fixture'), \
             patch('tools.alcc_normalization_bench.subprocess.run') as spawn:
            with self.assertRaises(OracleNotChecked):
                run(binary, self.root / 'run', 'fixture', log, oracle=self.oracle)
            spawn.assert_not_called()
        report = json.loads((self.root / 'run/report.json').read_text())
        self.assertEqual(report['status'], 'not_checked')
        self.assertEqual(report['oracle_failure']['status'], 'RANGE_EXCEEDED')

    def test_native_oracle_attached_to_bench_fixture_receipt(self):
        binary = self.root / 'lean-fixture'; binary.write_bytes(b'fixture, not Lean')
        log = self.root / 'log'; log.write_text('fixture')
        terms = corpus()['rational']; expected = reference(terms)
        rows = []
        for r in range(11):
            for v in (['baseline', 'cached'] if r % 2 == 0 else ['cached', 'baseline']):
                rows.append(dict(protocol='ALCC-NORMALIZE-PILOT-1', variant=v,
                                 elapsed_ns=1, force_digest=9, output=expected))
        actual_run = subprocess.run
        def dispatch(command, **kw):
            if command[0] == str(binary):
                return SimpleNamespace(returncode=0, stderr=b'',
                                       stdout='\n'.join(map(json.dumps, rows)).encode())
            return actual_run(command, **kw)
        with patch('tools.alcc_normalization_bench.corpus', return_value={'rational': terms}), \
             patch('tools.alcc_normalization_bench.platform.platform', return_value='fixture'), \
             patch('tools.alcc_normalization_bench.platform.processor', return_value='fixture'), \
             patch('tools.alcc_normalization_bench.subprocess.run', side_effect=dispatch):
            result = run(binary, self.root / 'run', 'fixture', log, oracle=self.oracle)
        self.assertEqual(result['status'], 'passed')
        self.assertTrue(result['cases']['rational']['second_oracle']['checked'])


if __name__ == '__main__':
    unittest.main()
