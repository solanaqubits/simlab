import copy
import json
import unittest
from tools.alcc_normalization_bench import PROTOCOL, corpus, reference, validate_run


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
