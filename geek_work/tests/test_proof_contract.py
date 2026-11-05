import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'tools'))
import geek_work_proof_contract as p
sys.path.pop(0)


class ProofContractTests(unittest.TestCase):
    def setUp(self):
        self.artifacts = {name: ('synthetic-' + name).encode() for name in p.ARTIFACTS}
        self.req = dict(schema=p.SCHEMA, claim='alcc-test-only',
                        artifacts={name: p.k.digest(b) for name, b in self.artifacts.items()},
                        backend=dict(id='gnark', version='synthetic-v0', proof_system='groth16-bn254'),
                        target=dict(ecosystem='offline', network='local', verifier_id='fixture',
                                    application_id='test'), nonce='01' * 32,
                        requirements=dict(zero_knowledge=True, post_quantum=False))

    def bind(self):
        raw = p.k.canonical(self.req)
        return p.bind(raw, p.k.digest(raw), self.artifacts)

    def test_no_proof_claim_from_matching_bytes(self):
        result = self.bind()
        self.assertEqual(result['status'], 'request_bound')
        for key in ('proof_generated', 'cryptographic_verification', 'zero_knowledge_verified',
                    'post_quantum_verified', 'chain_compatibility_verified', 'deployment_performed'):
            self.assertIs(result[key], False)

    def test_every_artifact_is_bound(self):
        for name in p.ARTIFACTS:
            with self.subTest(name=name):
                changed = dict(self.artifacts, **{name: b'substituted'})
                raw = p.k.canonical(self.req)
                with self.assertRaisesRegex(p.k.Refusal, 'artifact_hash:' + name):
                    p.bind(raw, p.k.digest(raw), changed)

    def test_untrusted_target_cannot_change_expected_request(self):
        anchor = p.k.digest(p.k.canonical(self.req))
        for key, value in [('ecosystem', 'solana'), ('network', 'mainnet'),
                           ('verifier_id', 'other'), ('application_id', 'other')]:
            changed = copy.deepcopy(self.req); changed['target'][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(p.k.Refusal, 'request_anchor'):
                p.bind(p.k.canonical(changed), anchor, self.artifacts)

    def test_commitment_changes_with_every_domain_component(self):
        first = self.bind()['statement_sha256']
        for key in self.req['target']:
            old = self.req['target'][key]
            self.req['target'][key] = 'ethereum' if key == 'ecosystem' else 'changed'
            self.assertNotEqual(first, self.bind()['statement_sha256'])
            self.req['target'][key] = old
        self.req['nonce'] = '02' * 32
        self.assertNotEqual(first, self.bind()['statement_sha256'])

    def test_digest_encoding_preserves_all_bits(self):
        for text in ('00' * 32, 'ff' * 32, '00' * 16 + 'ff' * 16, 'ab' * 32):
            with self.subTest(text=text):
                limbs = p.digest_limbs(text)
                self.assertTrue(all(x < 2**128 for x in limbs))
                self.assertEqual(p.limbs_digest(limbs), text)
        self.assertEqual(p.digest_limbs('00' * 16 + '01' * 16)[0], 0)

    def test_oversized_or_boolean_limbs_refused(self):
        for limbs in ([True, 0], [2**128, 0], [-1, 0], [0], ['0', 0]):
            with self.subTest(limbs=limbs), self.assertRaises(p.k.Refusal):
                p.limbs_digest(limbs)

    def test_pairing_cannot_request_post_quantum(self):
        self.req['requirements']['post_quantum'] = True
        with self.assertRaisesRegex(p.k.Refusal, 'pairing_not_post_quantum'): self.bind()

    def test_stark_does_not_automatically_establish_pq_or_zk(self):
        self.req['backend']['proof_system'] = 'native-stark'
        self.req['requirements']['post_quantum'] = True
        result = self.bind()
        self.assertFalse(result['post_quantum_verified'])
        self.assertFalse(result['zero_knowledge_verified'])

    def test_duplicate_json_and_extra_fields_refused(self):
        raw = b'{"schema":"a","schema":"b"}'
        with self.assertRaisesRegex(p.k.Refusal, 'duplicate_key'):
            p.validate(raw, p.k.digest(raw))
        self.req['verified'] = True
        with self.assertRaises(p.k.Refusal): self.bind()

    def test_resource_bounds(self):
        with patch.object(p, 'MAX_TOTAL_BYTES', 1), self.assertRaisesRegex(p.k.Refusal, 'total_bytes'):
            self.bind()
        with patch.object(p, 'MAX_REQUEST_BYTES', 1), self.assertRaisesRegex(p.k.Refusal, 'request_size'):
            self.bind()
        self.artifacts['input'] = b''
        with self.assertRaisesRegex(p.k.Refusal, 'artifact_size'): self.bind()

    def test_replay_detects_reanchored_tampering(self):
        result = self.bind(); raw = p.k.canonical(self.req)
        self.assertEqual(p.verify(result, p.k.digest(p.k.canonical(result)), raw,
                                  p.k.digest(raw), self.artifacts)['status'], 'binding_reproduced')
        result['cryptographic_verification'] = True
        with self.assertRaisesRegex(p.k.Refusal, 'binding_changed'):
            p.verify(result, p.k.digest(p.k.canonical(result)), raw, p.k.digest(raw), self.artifacts)

    def test_cli_exclusive_output_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); request = root / 'request.json'; request.write_bytes(p.k.canonical(self.req))
            args = [sys.executable, '-B', p.__file__, '--request', str(request),
                    '--expected-request-sha256', p.k.digest(request.read_bytes())]
            for name, content in self.artifacts.items():
                path = root / name; path.write_bytes(content)
                args += ['--' + name.replace('_', '-'), str(path)]
            output = root / 'binding.json'
            first = subprocess.run(args + ['bind', '--output', str(output)], capture_output=True)
            self.assertEqual(first.returncode, 0, first.stdout)
            original = output.read_bytes()
            self.assertEqual(subprocess.run(args + ['bind', '--output', str(output)], capture_output=True).returncode, 1)
            self.assertEqual(original, output.read_bytes())
            report = p.k.strict_json(original)
            replay = subprocess.run(args + ['verify', '--report', str(output), '--report-anchor',
                                           p.k.digest(p.k.canonical(report)), '--output', str(root / 'replay.json')],
                                    capture_output=True)
            self.assertEqual(replay.returncode, 0, replay.stdout)
            (root / 'input').unlink(); (root / 'input').symlink_to(root / 'program')
            self.assertEqual(subprocess.run(args + ['bind', '--output', str(root / 'bad.json')], capture_output=True).returncode, 1)
