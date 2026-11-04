import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / 'tools'))
import geek_work_gnark_statement as g
sys.path.pop(0)


class GnarkStatementTests(unittest.TestCase):
    def setUp(self):
        self.a = dict(specification=g.SPEC, parameters=g.PARAMETERS, program=b'circuit',
                      verifier=b'vk', input=b'{"h":[1,2,3]}', public_output=b'{"t":[4,13,28,27,18]}')
        self.r = dict(schema=g.contract.SCHEMA, claim='bounded-convolution-v1',
                      artifacts={n:g.k.digest(b) for n,b in self.a.items()},
                      backend=dict(id='gnark', version='v0.16.4', proof_system='groth16-bn254'),
                      target=dict(ecosystem='offline', network='local', application_id='pilot', verifier_id='test'),
                      nonce='01'*32, requirements=dict(zero_knowledge=True, post_quantum=False))

    def prepare(self):
        raw = g.k.canonical(self.r)
        return g.expected_statement(raw, g.k.digest(raw), self.a)

    def test_expected_public_values_and_lossless_context(self):
        e = self.prepare()
        self.assertEqual(e['h'], [1,2,3]); self.assertEqual(e['t'], [4,13,28,27,18])
        raw = g.k.canonical(self.r)
        self.assertEqual(''.join(e['context']), g.k.digest(g.contract.DOMAIN + raw))
        self.assertEqual(set(e), {'h','t','context','program_sha256','verifier_sha256'})

    def test_reanchored_context_changes_expected_proof_inputs(self):
        before = self.prepare()['context']
        for field in ('network','application_id','verifier_id'):
            old = self.r['target'][field]; self.r['target'][field] = 'changed'
            self.assertNotEqual(self.prepare()['context'], before)
            self.r['target'][field] = old
        self.r['nonce'] = '02'*32
        self.assertNotEqual(self.prepare()['context'], before)

    def test_external_request_anchor_is_required(self):
        raw = g.k.canonical(self.r); self.r['nonce'] = '02'*32
        with self.assertRaisesRegex(g.k.Refusal, 'request_anchor'):
            g.expected_statement(g.k.canonical(self.r), g.k.digest(raw), self.a)

    def test_unsupported_profiles_rejected_even_when_reanchored(self):
        for key, value in [('claim','other'), ('backend',dict(id='gnark',version='old',proof_system='groth16-bn254'))]:
            old = self.r[key]; self.r[key] = value
            with self.assertRaises(g.k.Refusal): self.prepare()
            self.r[key] = old
        self.r['target']['ecosystem'] = 'ethereum'
        with self.assertRaisesRegex(g.k.Refusal, 'offline_only'): self.prepare()

    def test_coefficient_types_lengths_and_ranges(self):
        for value in [[1,2], [1,2,3,4], [True,2,3], [1.0,2,3], [-1,2,3], [256,2,3]]:
            self.a['input'] = g.k.canonical(dict(h=value)); self.r['artifacts']['input'] = g.k.digest(self.a['input'])
            with self.assertRaises(g.k.Refusal): self.prepare()
        self.a['input'] = b'{"h":[1,2,3]}'; self.r['artifacts']['input'] = g.k.digest(self.a['input'])
        self.a['public_output'] = b'{"t":[262144,0,0,0,0]}'
        self.r['artifacts']['public_output'] = g.k.digest(self.a['public_output'])
        with self.assertRaisesRegex(g.k.Refusal,'coefficient_range'): self.prepare()

    def test_spec_parameters_and_duplicate_input_keys(self):
        for name in ('specification','parameters','input'):
            a = dict(self.a); r = copy.deepcopy(self.r)
            a[name] = b'{"h":[1,2,3],"h":[4,5,6]}' if name == 'input' else b'changed'
            r['artifacts'][name] = g.k.digest(a[name]); raw = g.k.canonical(r)
            with self.assertRaises(g.k.Refusal):g.expected_statement(raw,g.k.digest(raw),a)

    def test_cli_anchor_and_exclusive_output(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            raw = g.k.canonical(self.r)
            (root/'request.json').write_bytes(raw)
            for n,f in g.FILES.items(): (root/f).write_bytes(self.a[n])
            output = root/'expected.json'
            args = [sys.executable, g.__file__, '--bundle', str(root),
                    '--expected-request-sha256', g.k.digest(raw), '--output', str(output)]
            good = subprocess.run(args, capture_output=True)
            self.assertEqual(good.returncode, 0, good.stdout)
            self.assertEqual(g.k.strict_json(output.read_bytes()), self.prepare())
            before = output.read_bytes()
            self.assertNotEqual(subprocess.run(args, capture_output=True).returncode, 0)
            self.assertEqual(output.read_bytes(), before)
            args[-1] = str(root/'stale.json'); args[-3] = '00'*32
            self.assertNotEqual(subprocess.run(args, capture_output=True).returncode, 0)
            self.assertFalse((root/'stale.json').exists())
