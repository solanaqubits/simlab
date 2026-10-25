"""Protocol/process tests use pinned synthetic executors, not Lean proofs."""
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest

from tools import alcc_compiled_runner as r


def response(verdict="VERIFIED_SUCCESS", **updates):
    obj = dict(protocol_version=r.PROTOCOL, evidence_kind="compiled_execution", verdict=verdict)
    obj.update(updates)
    return json.dumps(obj).encode()


class ProtocolTests(unittest.TestCase):
    def test_three_verdict_pairs(self):
        for code, verdict in r.PAIRS.items():
            with self.subTest(code=code):
                self.assertEqual(r.classify(code, response(verdict), b"")[0], verdict)

    def test_protocol_rejections(self):
        cases = [b"garbage", b"[]", b"null", b'{}', b'\xff', response() + response(),
                 response(protocol_version="1.0.0"), response(evidence_kind="kernel_proof"),
                 response(extra=1), response(verdict=True), b"["*1500+b"0"+b"]"*1500,
                 b'{"verdict":0,"verdict":1}', b'{"verdict":NaN}']
        for data in cases:
            with self.subTest(data=data):
                self.assertEqual(r.classify(0, data, b"")[0], "EXEC_PROTOCOL_ERROR")
        for code in (1, 2, 3, 64, 74):
            self.assertEqual(r.classify(code, response(), b"")[0], "EXEC_PROTOCOL_ERROR")

    def test_io_is_not_decode(self):
        self.assertEqual(r.classify(74, response("EXEC_IO_ERROR"), b"")[0], "EXEC_IO_ERROR")
        self.assertEqual(r.classify(3, response("EXEC_IO_ERROR"), b"")[0], "EXEC_PROTOCOL_ERROR")

    def test_crash_oom_evidence(self):
        for code in (-signal.SIGKILL, 137, -signal.SIGSEGV):
            self.assertEqual(r.classify(code, response(), b"")[0], "EXEC_CRASH")
        self.assertEqual(r.classify(-9, b"", b"INTERNAL PANIC: out of memory\n")[0], "EXEC_OOM")
        self.assertEqual(r.classify(-9, b"", b"a file called out of memory\n")[0], "EXEC_CRASH")
        self.assertEqual(r.classify(0, response(), b"INTERNAL PANIC: out of memory\n")[0], "EXEC_PROTOCOL_ERROR")


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bp = self.root / "passport"
        self.bc = self.root / "certificate"
        self.bp.write_bytes(b'raw passport\x00\xff')
        self.bc.write_bytes(b'raw certificate\r\n')
        self.output = self.root / "runs"

    def tearDown(self):
        self.temp.cleanup()

    def pin(self, code):
        binary = self.root / "executor"
        binary.write_text(f"#!{sys.executable}\n" + code + "\n")
        binary.chmod(0o700)
        build = self.root / "build.log"
        build.write_bytes(b"TEST FIXTURE: no Lean build\n")
        environment = self.root / "environment.json"
        env = dict(kernel_base_commit=r.KERNEL_BASE, cli_source_commit="1" * 40,
                   lean_toolchain="fixture-only", binary_sha256=r.file_hash(binary),
                   build_log_hash=r.file_hash(build))
        environment.write_text(json.dumps(env))
        pin = dict(protocol_version=r.PROTOCOL, evidence_kind="compiled_execution", kernel_base_commit=r.KERNEL_BASE,
                   cli_source_commit="1" * 40, bridge_runner_commit="2" * 40, lean_toolchain="fixture-only",
                   artifacts={name: dict(path=str(path), sha256=r.file_hash(path)) for name, path in
                              {"binary": binary, "build_log": build, "environment": environment,
                               "runner": Path(r.__file__).resolve()}.items()})
        path = self.root / "pin.json"
        path.write_text(json.dumps(pin))
        return path

    def run_case(self, code, **kwargs):
        return r.verify(self.bp, self.bc, self.output, self.pin(code), **kwargs)

    def test_real_process_pairs_and_snapshots(self):
        for code, verdict in r.PAIRS.items():
            result = self.run_case(f"import sys\nprint({response(verdict).decode()!r})\nsys.exit({code})")
            self.assertEqual(result["status"], verdict)
            self.assertTrue(result["snapshot_integrity_verified"])
            self.assertTrue(result["artifact_integrity_verified"])
            self.assertEqual(Path(result['snapshots']['passport']['path']).read_bytes(), self.bp.read_bytes())
            self.assertTrue((Path(result['run_directory']) / 'receipt.json').exists())
        self.assertEqual(len(list(self.output.iterdir())), 3)

    def test_timeout_keeps_partial_logs(self):
        result = self.run_case("import time\nprint('partial', flush=True)\ntime.sleep(5)", timeout=0.15)
        self.assertEqual(result['status'], 'EXEC_TIMEOUT')
        self.assertIn(b'partial', (Path(result['run_directory']) / 'stdout.bin').read_bytes())
        self.assertTrue(result['snapshot_integrity_verified'])
        self.assertLess(result['elapsed_seconds'], 3)

    def test_sigkill_without_oom(self):
        result = self.run_case('import os, signal\nos.kill(os.getpid(), signal.SIGKILL)')
        self.assertEqual(result['status'], 'EXEC_CRASH')
        self.assertEqual(result['exit_code'], -9)

    def test_runtime_diagnostic_classification(self):
        result = self.run_case("import sys\nprint('INTERNAL PANIC: out of memory', file=sys.stderr)\nsys.exit(1)")
        self.assertEqual(result['status'], 'EXEC_OOM')  # simulated diagnostic, NOT a physical OOM experiment

    def test_memory_limit_is_applied(self):
        cap = 128 * 1024**2
        result = self.run_case(f"import resource, os\nassert os.environ['LEAN_NUM_THREADS'] == '1'\nassert os.environ['LEAN_ABORT_ON_PANIC'] == '1'\nassert os.environ['MIMALLOC_ARENA_RESERVE'] == '67108864'\nassert os.environ['LEAN_STACK_SIZE_KB'] == '65536'\nassert resource.getrlimit(resource.RLIMIT_AS) == ({cap},{cap})\nprint({response().decode()!r})", memory=cap)
        self.assertEqual(result['status'], 'VERIFIED_SUCCESS')
        self.assertEqual(result['limits']['address_space_bytes'], cap)

    def test_output_limit(self):
        result = self.run_case("import os\nwhile True: os.write(1, b'x'*4096)", log_limit=8192)
        self.assertEqual(result['status'], 'EXEC_PROTOCOL_ERROR')
        self.assertLessEqual((Path(result['run_directory']) / 'stdout.bin').stat().st_size, 8192)

    def test_malformed_native_output(self):
        result = self.run_case("import os\nos.write(1, b'\\xff')")
        self.assertEqual(result['status'], 'EXEC_PROTOCOL_ERROR')

    def test_snapshot_mutation(self):
        result = self.run_case("import pathlib, sys\np=pathlib.Path(sys.argv[2]); p.chmod(0o600); p.write_bytes(b'changed')\n" + f"print({response().decode()!r})")
        self.assertEqual(result['status'], 'EXEC_IO_ERROR')
        self.assertFalse(result['snapshot_integrity_verified'])

    def test_binary_changed_during_execution(self):
        result = self.run_case("import pathlib\np=pathlib.Path(__file__); p.write_bytes(p.read_bytes()+b'# change')\n" + f"print({response().decode()!r})")
        self.assertEqual(result['status'], 'EXEC_IO_ERROR')
        self.assertFalse(result['artifact_integrity_verified'])

    def test_binary_tampered_before_execution(self):
        pin = self.pin(f"print({response().decode()!r})")
        with (self.root / 'executor').open('a') as stream:
            stream.write('# tamper')
        result = r.verify(self.bp, self.bc, self.output, pin)
        self.assertEqual(result['status'], 'EXEC_PROTOCOL_ERROR')
        self.assertIsNone(result['exit_code'])

    def test_missing_input(self):
        self.bp.unlink()
        result = self.run_case(f"print({response().decode()!r})")
        self.assertEqual(result['status'], 'EXEC_IO_ERROR')
        self.assertIsNone(result['exit_code'])

    def test_fifo_input_refused_without_blocking(self):
        self.bp.unlink()
        os.mkfifo(self.bp)
        result = self.run_case(f"print({response().decode()!r})")
        self.assertEqual(result['status'], 'EXEC_IO_ERROR')
        self.assertIsNone(result['exit_code'])
        self.assertLess(result['elapsed_seconds'], 2)

    def test_unexpected_stderr_quarantined(self):
        result = self.run_case("import sys\nprint('panic', file=sys.stderr)\n" + f"print({response().decode()!r})")
        self.assertEqual(result['status'], 'EXEC_PROTOCOL_ERROR')

    def test_input_budget(self):
        result = self.run_case(f"print({response().decode()!r})", input_limit=2)
        self.assertEqual(result['status'], 'EXEC_IO_ERROR')
        self.assertIsNone(result['exit_code'])

    def test_invalid_limits(self):
        for changes in ({'memory': 0}, {'timeout': float('inf')}, {'timeout': -1}):
            with self.assertRaises(ValueError):
                self.run_case('', **changes)


if __name__ == '__main__':
    unittest.main()
