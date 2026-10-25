"""Synthetic archive controls: not Lean proofs or authenticated executions."""
import base64
import copy
import json
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from tools import alcc_receipt_audit as a


class ReceiptAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run = self.root / 'run'
        self.run.mkdir()
        self.bp, self.bc = b'passport raw\x00\xff', b'certificate raw\r\n'
        provenance = dict(kernel_base_commit=a.BASE, cli_source_commit='1'*40,
                          bridge_runner_commit='2'*40, lean_toolchain='synthetic fixture')
        self.pin = dict(**provenance, protocol_version=a.PROTOCOL, evidence_kind='compiled_execution', artifacts={})
        for name in ('binary', 'build_log', 'runner'):
            p = self.root / name
            p.write_bytes(b'SYNTHETIC NOT EXECUTABLE ' + name.encode())
            self.pin['artifacts'][name] = dict(path=str(p), sha256=a.hash_file(p))
        self.env = dict(**provenance, binary_sha256=self.pin['artifacts']['binary']['sha256'],
                        build_log_hash=self.pin['artifacts']['build_log']['sha256'])
        self.env_path = self.root / 'environment.json'
        self.write(self.env_path, self.env)
        self.pin['artifacts']['environment'] = dict(path=str(self.env_path), sha256=a.hash_file(self.env_path))
        self.pin_path = self.root / 'pin.json'
        self.write(self.pin_path, self.pin)
        self.receipt_path = self.run / 'receipt.json'
        self.r = dict(**provenance, protocol_version=a.PROTOCOL, evidence_kind='compiled_execution',
                      started_at='2026-10-25T00:00:00+00:00', finished_at='2026-10-25T00:00:01+00:00', elapsed_seconds=1,
                      status='VERIFIED_SUCCESS', exit_code=0, run_directory=str(self.run), runtime_environment=dict(a.RUNTIME_ENV),
                      limits=dict(wall_seconds=30, address_space_bytes=2147483648, cpu_seconds=31,
                                  input_bytes=1048576, log_bytes_per_stream=1048576, lean_worker_threads=1),
                      snapshots={}, errors=[], pin_sha256=a.hash_file(self.pin_path),
                      binary_sha256=self.pin['artifacts']['binary']['sha256'],
                      build_log_hash=self.pin['artifacts']['build_log']['sha256'],
                      environment_manifest_hash=self.pin['artifacts']['environment']['sha256'],
                      snapshot_integrity_verified=True, artifact_integrity_verified=True)
        for name, data in (('passport', self.bp), ('certificate', self.bc)):
            p = self.run / f'snapshot_{name}.bin'; p.write_bytes(data)
            self.r['snapshots'][name] = dict(path=str(p), bytes=len(data), sha256_before=a.sha(data), sha256_after=a.sha(data))
        self.r['command'] = [self.pin['artifacts']['binary']['path'], '--passport', self.r['snapshots']['passport']['path'],
                             '--certificate', self.r['snapshots']['certificate']['path']]
        self.logs()

    @staticmethod
    def write(path, obj):
        path.write_text(json.dumps(obj))

    def logs(self, stdout=None, stderr=b''):
        if stdout is None:
            stdout = json.dumps(dict(protocol_version=a.PROTOCOL, evidence_kind='compiled_execution', verdict=self.r['status'])).encode()
        for name, data in (('stdout', stdout), ('stderr', stderr)):
            (self.run / (name + '.bin')).write_bytes(data)
            self.r[name + '_sha256'] = a.sha(data)
            self.r['raw_' + name + '_base64'] = base64.b64encode(data).decode()
        self.write(self.receipt_path, self.r)

    def check(self):
        return a.audit(self.receipt_path, self.pin_path, a.sha(self.bp), a.sha(self.bc))

    def test_three_normal_outcomes_without_execution(self):
        with patch('subprocess.Popen', side_effect=AssertionError('must not execute')):
            for code, verdict in a.PAIRS.items():
                self.r.update(exit_code=code, status=verdict); self.logs()
                result = self.check()
                self.assertTrue(result['ok'], result)
                self.assertEqual(result['recorded_verdict'], verdict)
                self.assertFalse(result['kernel_proof'])
                self.assertFalse(result['authenticated_execution'])

    def test_metadata_mutations(self):
        original = copy.deepcopy(self.r)
        mutations = dict(exit_code=True, status='IDENTITY_MISMATCH', evidence_kind='kernel_proof',
                         pin_sha256='0'*64, binary_sha256='0'*64, cli_source_commit='3'*40,
                         artifact_integrity_verified=1, snapshot_integrity_verified=False,
                         errors=['error'], command=[], elapsed_seconds=-1,
                         started_at='2026-10-26T00:00:00+00:00', finished_at='invalid',
                         protocol_version='new', limits={}, snapshots={}, runtime_environment={})
        for key, value in mutations.items():
            with self.subTest(key=key):
                self.r = copy.deepcopy(original); self.r[key] = value
                self.write(self.receipt_path, self.r)
                self.assertFalse(self.check()['ok'])

    def test_snapshot_changes_and_missing(self):
        p = self.run / 'snapshot_passport.bin'
        p.write_bytes(b'changed')
        self.assertFalse(self.check()['ok'])
        p.unlink()
        self.assertFalse(self.check()['ok'])

    def test_independently_expected_inputs(self):
        self.assertFalse(a.audit(self.receipt_path, self.pin_path, '0'*64, a.sha(self.bc))['ok'])
        self.assertFalse(a.audit(self.receipt_path, self.pin_path, a.sha(self.bp), '0'*64)['ok'])
        self.assertFalse(a.audit(self.receipt_path, self.pin_path, '', '')['ok'])

    def test_snapshot_metadata_types_and_paths(self):
        original = copy.deepcopy(self.r)
        for key, value in [('bytes', True), ('bytes', 999), ('sha256_after', '0'*64), ('path', '/etc/passwd')]:
            self.r = copy.deepcopy(original); self.r['snapshots']['passport'][key] = value
            self.write(self.receipt_path, self.r)
            self.assertFalse(self.check()['ok'])

    def test_logs_and_base64(self):
        (self.run / 'stdout.bin').write_bytes(b'changed')
        self.assertFalse(self.check()['ok'])
        self.logs()
        self.r['raw_stdout_base64'] += '\n'; self.write(self.receipt_path, self.r)
        self.assertFalse(self.check()['ok'])
        self.logs(stderr=b'unexpected diagnostic')
        self.assertFalse(self.check()['ok'])

    def test_rehashed_malformed_protocol(self):
        for raw in (b'null', b'[]', b'{}', b'\xff', b'{"verdict":0,"verdict":1}',
                    b'{"verdict":NaN}', b'{}{}', b'[' * 1500):
            self.logs(stdout=raw)
            self.assertFalse(self.check()['ok'])
        self.r['status'] = 'IDENTITY_MISMATCH'; self.logs()
        self.assertFalse(self.check()['ok'])

    def test_duplicate_and_nonfinite_receipt(self):
        self.receipt_path.write_bytes(b'{"status":0,"status":1}')
        self.assertFalse(self.check()['ok'])
        self.r['elapsed_seconds'] = float('nan'); self.logs()
        self.assertFalse(self.check()['ok'])

    def test_artifacts_corruption(self):
        for name in self.pin['artifacts']:
            p = Path(self.pin['artifacts'][name]['path']); old = p.read_bytes()
            p.write_bytes(old + b'changed')
            self.assertFalse(self.check()['ok'])
            p.write_bytes(old)

    def test_rehashed_inconsistent_environment(self):
        self.env['cli_source_commit'] = '3'*40
        self.write(self.env_path, self.env)
        self.pin['artifacts']['environment']['sha256'] = a.hash_file(self.env_path)
        self.write(self.pin_path, self.pin)
        self.r['pin_sha256'] = a.hash_file(self.pin_path)
        self.r['environment_manifest_hash'] = a.hash_file(self.env_path)
        self.write(self.receipt_path, self.r)
        self.assertFalse(self.check()['ok'])

    def test_symlink_and_fifo_refused(self):
        p = self.run / 'snapshot_passport.bin'; p.unlink()
        target = self.root / 'original'; target.write_bytes(self.bp)
        p.symlink_to(target)
        self.assertFalse(self.check()['ok'])
        p.unlink(); os.mkfifo(p)
        self.assertFalse(self.check()['ok'])

    def test_oversized_receipt(self):
        self.receipt_path.write_bytes(b' ' * (4 * 1024**2 + 1))
        self.assertFalse(self.check()['ok'])

    def test_relocated_archive_uses_fixed_local_files(self):
        new = self.root / 'moved'; self.run.rename(new)
        self.receipt_path = new / 'receipt.json'
        self.assertTrue(self.check()['ok'])

    def test_execution_failure_not_promoted(self):
        self.r.update(status='EXEC_TIMEOUT', exit_code=-9); self.logs()
        self.assertFalse(self.check()['ok'])
