import copy
import json
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch
from tools.alcc_normalization_bench import (
    PROTOCOL, ISOLATED_PROFILE, LEGACY_PROFILE, PROFILES, corpus, reference,
    validate_run, require_isolation, remaining_timeout, limits, run,
)


class NormalizationBenchTests(unittest.TestCase):
    def rows(self):
        expected = reference(corpus()['rational'])
        rows = []
        for r in range(11):
            for v in (['baseline', 'cached'] if r % 2 == 0 else ['cached', 'baseline']):
                rows.append({'protocol': PROTOCOL, 'variant': v, 'elapsed_ns': r + 1,
                             'force_digest': 9, 'output': copy.deepcopy(expected)})
        return rows, expected

    def check(self, rows, expected):
        return validate_run('\n'.join(json.dumps(x) for x in rows), expected)

    def test_independent_rational_result(self):
        self.assertEqual(reference(corpus()['rational']),
                         [[[1, 0, 0], '1', '2'], [[0, 1, 0], '-7', '5']])

    def test_cancellation(self):
        for name in ('empty', 'zero', 'cancel', 'cancel128'):
            self.assertEqual(reference(corpus()[name]), [])

    def test_order_and_sample_exclusion(self):
        rows, expected = self.rows()
        summary = self.check(rows, expected)
        self.assertEqual(summary['baseline']['samples_ns'], list(range(4, 12)))
        self.assertEqual(summary['cached']['median_ns'], 7.5)

    def test_last_result_mutation_rejected(self):
        rows, expected = self.rows()
        rows[-1]['output'][0][1] = '2'
        with self.assertRaisesRegex(ValueError, 'complete result'):
            self.check(rows, expected)

    def test_validation_result_mutation_rejected(self):
        rows, expected = self.rows()
        rows[0]['output'] = []
        with self.assertRaises(ValueError):
            self.check(rows, expected)

    def test_protocol_order_and_times_rejected(self):
        for key, value in [('protocol', 'other'), ('variant', 'cached'),
                           ('elapsed_ns', True), ('elapsed_ns', -1), ('force_digest', 0)]:
            with self.subTest(key=key, value=value):
                rows, expected = self.rows()
                rows[0][key] = value
                with self.assertRaises(ValueError):
                    self.check(rows, expected)

    def test_missing_run_rejected(self):
        rows, expected = self.rows()
        with self.assertRaises(ValueError):
            self.check(rows[:-1], expected)

    def test_boolean_exponent_is_not_an_integer(self):
        rows, expected = self.rows()
        rows[0]['output'][0][0][0] = True
        with self.assertRaisesRegex(ValueError, 'result schema'):
            self.check(rows, expected)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate JSON'):
            validate_run('{"protocol": "x", "protocol": "y"}', [])


class ResourceContractTests(unittest.TestCase):
    def snapshot(self):
        return {'memory.max': str(1024**3), 'memory.swap.max': '0',
                'cpu.max': '100000 100000'}

    def test_bounded_cgroup_accepted(self):
        require_isolation(self.snapshot())

    def test_unbounded_memory_or_swap_rejected(self):
        for key, value in [('memory.max', 'max'), ('memory.max', str(2*1024**3)),
                           ('memory.swap.max', 'max'), ('memory.swap.max', '1')]:
            with self.subTest(key=key, value=value):
                snap = self.snapshot()
                snap[key] = value
                with self.assertRaises(ValueError):
                    require_isolation(snap)

    def test_invalid_cpu_quota_rejected(self):
        for value in ['max 100000', '200000 100000', '0 100000', '100000 0']:
            with self.subTest(value=value):
                snap = self.snapshot()
                snap['cpu.max'] = value
                with self.assertRaises(ValueError):
                    require_isolation(snap)

    def test_deadline_caps_last_subprocess(self):
        self.assertEqual(remaining_timeout(10, 10), 15)
        self.assertEqual(remaining_timeout(10, 189), 1)
        with self.assertRaises(TimeoutError):
            remaining_timeout(10, 190)

    def test_legacy_profile_still_one_gib(self):
        self.assertEqual(PROFILES[LEGACY_PROFILE], 1024**3)

    def test_child_limits_are_applied(self):
        import resource
        with patch('tools.alcc_normalization_bench.resource.setrlimit') as setter:
            limits(PROFILES[ISOLATED_PROFILE])
        self.assertEqual(setter.call_args_list[0].args,
                         (resource.RLIMIT_AS, (4*1024**3, 4*1024**3)))
        self.assertEqual(setter.call_args_list[1].args, (resource.RLIMIT_CPU, (10, 10)))

    def test_missing_cgroup_fails_before_spawn_and_preserves_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / 'binary'
            binary.write_bytes(b'not executed')
            log = root / 'build.log'
            log.write_text('fixture')
            with patch('tools.alcc_normalization_bench.cgroup_snapshot',
                       side_effect=FileNotFoundError('no cgroup')), \
                 patch('tools.alcc_normalization_bench.platform.platform', return_value='fixture'), \
                 patch('tools.alcc_normalization_bench.platform.processor', return_value='fixture'), \
                 patch('tools.alcc_normalization_bench.subprocess.run') as spawn:
                with self.assertRaises(FileNotFoundError):
                    run(binary, root / 'output', 'fixture', log, ISOLATED_PROFILE)
                spawn.assert_not_called()
            report = json.loads((root / 'output/report.json').read_text())
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(report['cases'], {})
