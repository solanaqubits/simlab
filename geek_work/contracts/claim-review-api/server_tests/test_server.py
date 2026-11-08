"""Real loopback server tests; fault injection is private to this test process."""
import base64
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid

BRAIN = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BRAIN / 'tools'))
import geek_work_claim_api_server as s
from geek_work_claim_api_harness import Harness


class ScriptRunner(s.Runner):
    def __init__(self, code, **limits):
        super().__init__({**s.LIMITS, **limits})
        self.code = code

    def command(self, config):
        return [sys.executable, '-B', '-c', self.code, str(config)]


class BlockingRunner(s.Runner):
    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def run(self, config, kind):
        self.entered.set()
        if not self.release.wait(5):
            raise s.JobError('timeout')
        return super().run(config, kind)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = self.root / 'fixture'
        shutil.copytree(BRAIN / 'examples/claim-adapter-ready', self.fixture)
        pins = json.loads((self.fixture / 'pins.json').read_bytes())
        self.c = s.Context(self.fixture/'source.txt', pins['source_sha256'],
            self.fixture/'expectations.json', pins['expectations_sha256'],
            self.fixture/'source-bundle', pins['claim_map_bundle_sha256'],
            pins['source_claim_id'], pins['source_revision'], self.root/'session')
        self.server = s.Server(self.c)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.h = Harness(self.server.server_address[1], self.c.token, self.c.id)

    def stop(self):
        if isinstance(self.c.runner, BlockingRunner):
            self.c.runner.release.set()
        if self.c.worker:
            self.c.worker.join(8)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def send(self, operation, expected=200, error=None, **fields):
        return self.h.send(operation, self.h.request(operation, **fields), expected, error)['data'] if error is None else self.h.send(operation, self.h.request(operation, **fields), expected, error)

    def draft(self, raw=None):
        raw = raw if raw is not None else (self.fixture/'record.json').read_bytes()
        return self.send('drafts', 201, parent_draft_id=None, record_sha256=s.m.sha(raw), record_base64=base64.b64encode(raw).decode())

    def job_request(self, draft, operation='checks'):
        return self.h.request(operation, draft_id=draft['draft_id'], draft_sha256=draft['draft_sha256'], context_fingerprint=self.c.fingerprint)

    def finish(self, request):
        accepted = self.h.send('start', request, 202)['data']
        self.c.worker.join(8)
        self.assertFalse(self.c.worker.is_alive())
        return self.send('jobs/status', job_id=accepted['job_id'])

    def assert_failed(self, job, code):
        self.assertEqual(job['state'], 'failed')
        self.assertEqual(job['failure']['code'], code)
        self.assertEqual(job['artifacts'], [])
        self.assertEqual(job['reports'], [])
        self.assertFalse(job['package_available'])
        self.assertIsNone(self.c.active)
        self.assertEqual(len(self.c.artifacts), 3)

    def test_real_ready_harness(self):
        context = self.h.probe()
        self.h.workflow(context, (self.fixture/'record.json').read_bytes(), 'ready')
        self.assertEqual(len(self.c.jobs), 2)
        for job in self.c.jobs.values():
            self.assertEqual(job['state'], 'completed')

    def test_busy_slot_and_idempotent_retry(self):
        self.c.runner = BlockingRunner()
        req = self.job_request(self.draft())
        first = self.h.send('start', req, 202)
        self.assertTrue(self.c.runner.entered.wait(2))
        self.assertEqual(self.h.send('repeat', req, 202), first)
        other = dict(req, request_id=str(uuid.uuid4()))
        self.h.send('busy', other, 409, 'context_busy')
        self.c.runner.release.set()
        self.c.worker.join(5)
        self.assertEqual(self.c.jobs[first['data']['job_id']]['state'], 'completed')

    def test_timeout_fails_job_and_releases_slot(self):
        self.c.runner = ScriptRunner('import time; time.sleep(20)', check_timeout_seconds=.15, terminate_grace_seconds=.1, kill_wait_seconds=.1)
        self.assert_failed(self.finish(self.job_request(self.draft())), 'timeout')

    def test_stdout_limit(self):
        self.c.runner = ScriptRunner('import os; os.write(1,b"x"*300000)')
        self.assert_failed(self.finish(self.job_request(self.draft())), 'output_limit')

    def test_stderr_limit(self):
        self.c.runner = ScriptRunner('import os; os.write(2,b"x"*300000)')
        self.assert_failed(self.finish(self.job_request(self.draft())), 'output_limit')

    def test_process_crash(self):
        self.c.runner = ScriptRunner('raise SystemExit(17)')
        job = self.finish(self.job_request(self.draft()))
        self.assert_failed(job, 'process_crash')
        self.assertEqual(job['exit_code'], 17)

    def test_assurance_promotion_rejected(self):
        self.c.runner = ScriptRunner('import json,sys,pathlib; c=json.load(open(sys.argv[1])); pathlib.Path(c["root"],"extraction-report.json").write_text(json.dumps({"status":"record_consistent","kernel_replayed":True}))')
        self.assert_failed(self.finish(self.job_request(self.draft())), 'invalid_cli_report')

    def test_wrong_exit_code_rejected(self):
        self.c.runner = ScriptRunner('import json,sys,runpy; c=json.load(open(sys.argv[1])); sys.argv=[c["script"],*c["args"]]; sys.path.insert(0,str(__import__("pathlib").Path(c["script"]).parent))\ntry: runpy.run_path(c["script"],run_name="__main__")\nexcept SystemExit: raise SystemExit(1)')
        self.assert_failed(self.finish(self.job_request(self.draft())), 'invalid_cli_report')

    def test_source_tamper_blocks_start_preserves_drafts(self):
        draft = self.draft()
        (self.fixture/'source.txt').write_bytes(b'changed')
        self.h.send('tamper', self.job_request(draft), 409, 'anchor_mismatch')
        self.assertEqual(self.c.jobs, {})
        self.draft(b'{}')

    def test_ledger_tamper_blocks_start(self):
        draft = self.draft()
        (self.fixture/'expectations.json').write_bytes(b'{}')
        self.h.send('tamper', self.job_request(draft), 409, 'anchor_mismatch')

    def test_bundle_payload_tamper_blocks_start(self):
        draft = self.draft()
        (self.fixture/'source-bundle/report.json').write_bytes(b'{}')
        self.h.send('tamper', self.job_request(draft), 409, 'anchor_unavailable')

    def test_snapshot_race_fails_without_cli(self):
        draft = self.draft()
        original = self.c.snapshot
        calls = []
        def race():
            calls.append(1)
            if len(calls) == 2:
                raise s.APIError(409, 'anchor_mismatch')
            return original()
        with patch.object(self.c, 'snapshot', side_effect=race):
            self.assert_failed(self.finish(self.job_request(draft)), 'anchor_mismatch')

    def test_late_result_bound_to_original_draft(self):
        self.c.runner = BlockingRunner()
        first = self.draft()
        accepted = self.h.send('start', self.job_request(first), 202)['data']
        self.assertTrue(self.c.runner.entered.wait(2))
        second = self.draft((self.fixture/'record.json').read_bytes()+b'\n')
        self.c.runner.release.set()
        self.c.worker.join(5)
        result = self.send('jobs/status', job_id=accepted['job_id'])
        self.assertEqual(result['draft_id'], first['draft_id'])
        self.assertNotEqual(result['draft_sha256'], second['draft_sha256'])
        self.assertEqual(second['validation_state'], 'not_run')

    def test_disk_reservation_blocks_start(self):
        draft = self.draft()
        with patch.object(self.c, 'usage', return_value=s.LIMITS['context_storage_bytes']-s.LIMITS['job_reserved_bytes']+1):
            self.h.send('quota', self.job_request(draft), 507, 'quota_exceeded')
        self.assertIsNone(self.c.active)

    def test_rate_limit(self):
        with self.c.lock:
            self.c.tokens = 0
            self.c.rate_time = time.monotonic()+5
        self.send('context', 429, 'rate_limited')

    def test_artifact_tamper(self):
        ref = self.c.initial['source_snapshot']
        (self.c.root/'inputs/source.txt').write_bytes(b'changed')
        self.send('artifacts/read', 409, 'artifact_integrity_failure', artifact_id=ref['artifact_id'], artifact_sha256=ref['sha256'], offset=0, max_bytes=8)

    def test_unregistered_artifact(self):
        self.send('artifacts/read', 404, 'unknown_artifact', artifact_id=str(uuid.uuid4()), artifact_sha256='0'*64, offset=0, max_bytes=8)

    def test_invalid_record_schema_can_be_saved_and_checked(self):
        job = self.finish(self.job_request(self.draft(b'{}')))
        self.assertEqual(job['state'], 'completed')
        self.assertEqual(job['exit_code'], 2)
        self.assertEqual(job['reports'][0]['status'], 'invalid_input')

    def test_invalid_record_json_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":1.0}', b'{"a":NaN}', b'{"a":"\\ud800"}', b'\xef\xbb\xbf{}', b'{"a":'+b'1'*129+b'}', b'{"a":'+b'['*34+b'0'+b']'*34+b'}'):
            with self.subTest(raw=raw[:30]):
                self.send('drafts', 400, 'invalid_record_json', parent_draft_id=None, record_sha256=s.m.sha(raw), record_base64=base64.b64encode(raw).decode())

    def test_unknown_fields_and_paths_rejected(self):
        self.send('context', 400, 'invalid_schema', source_path='/tmp/../secret')

    def test_registration_failure_does_not_expose_partial_package(self):
        original = self.c.register
        calls = []
        def failing(path, registry=None):
            calls.append(1)
            if len(calls) == 2:
                raise OSError('injected registration failure')
            return original(path, registry)
        draft = self.draft()
        with patch.object(self.c, 'register', side_effect=failing):
            self.assert_failed(self.finish(self.job_request(draft, 'builds')), 'invalid_cli_report')

    def test_receipt_write_failure_does_not_publish(self):
        original = s.write_new
        def failing(path, raw):
            if path.name == 'job-receipt.json':
                raise OSError('injected storage failure')
            return original(path, raw)
        draft = self.draft()
        with patch.object(s, 'write_new', side_effect=failing):
            self.assert_failed(self.finish(self.job_request(draft)), 'invalid_cli_report')

    def test_post_limit_rejected_before_body(self):
        request = self.h.request('context')
        self.h.send('oversize', request, 413, 'payload_too_large', headers={'Content-Length': str(s.LIMITS['post_body_bytes']+1)})

    def test_duplicate_content_type_rejected(self):
        self.h.send('duplicate', self.h.request('context'), 400, 'malformed_request', extra_headers=[('Content-Type','application/json')])

    def test_header_count_rejected(self):
        extras=[('X-Test-'+str(i),'x') for i in range(33)]
        self.h.send('count',self.h.request('context'),400,'malformed_request',extra_headers=extras)

    def test_header_size_rejected(self):
        self.h.send('size',self.h.request('context'),413,'payload_too_large',extra_headers=[('X-Test','x'*17000)])

    def test_body_read_timeout(self):
        with patch.dict(s.LIMITS, body_read_seconds=.05):
            self.h.send('timeout',self.h.request('context'),408,'request_timeout',headers={'Content-Length':'10000'})

    def test_noncanonical_base64(self):
        raw=b'{}'
        self.send('drafts',400,'noncanonical_base64',parent_draft_id=None,record_sha256=s.m.sha(raw),record_base64='e31=')

    def test_draft_limit(self):
        with patch.dict(s.LIMITS,max_drafts=0):
            raw=b'{}'
            self.send('drafts',507,'quota_exceeded',parent_draft_id=None,record_sha256=s.m.sha(raw),record_base64=base64.b64encode(raw).decode())

    def test_job_limit(self):
        draft=self.draft()
        with patch.dict(s.LIMITS,max_jobs=0):
            self.h.send('quota',self.job_request(draft),507,'quota_exceeded')

    def test_stale_context_fingerprint(self):
        req=self.job_request(self.draft())
        req['context_fingerprint']='0'*64
        self.h.send('stale_context',req,409,'context_fingerprint_mismatch')

    def test_private_token_and_directory_modes(self):
        self.assertEqual(self.c.root.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.c.root/'session-token').stat().st_mode & 0o777, 0o600)
        receipt = self.h.receipt('probe', True)
        self.assertNotIn(self.c.token, json.dumps(receipt))


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_worker(self, code, file_limit=1024, budget=2048, **limits):
        script=self.root/'fixture.py'; script.write_text(code)
        config=self.root/'config.json'
        config.write_bytes(s.m.encoded(dict(root=str(self.root), script=str(script), args=[str(self.root)], file_limit=file_limit, write_budget=budget)))
        return s.Runner({**s.LIMITS, **limits}).run(config,'check')

    def test_file_write_rejected_before_growth(self):
        with self.assertRaises(s.JobError) as caught:
            self.run_worker('import pathlib,sys; pathlib.Path(sys.argv[1],"large").write_bytes(b"x"*1025)')
        self.assertEqual(caught.exception.code,'output_limit')
        self.assertEqual((self.root/'large').stat().st_size,0)

    def test_total_write_budget(self):
        with self.assertRaises(s.JobError) as caught:
            self.run_worker('import pathlib,sys; p=pathlib.Path(sys.argv[1]); (p/"a").write_bytes(b"x"*800); (p/"b").write_bytes(b"x"*800)',budget=1000)
        self.assertEqual(caught.exception.code,'output_limit')
        self.assertEqual((self.root/'a').stat().st_size,800)
        self.assertEqual((self.root/'b').stat().st_size,0)

    def test_fdopen_writes_charged_once(self):
        code='import os,sys; fd=os.open(os.path.join(sys.argv[1],"fd"),os.O_WRONLY|os.O_CREAT,0o600)\nwith os.fdopen(fd,"wb") as f: f.write(b"x"*800)'
        result=self.run_worker(code,budget=1000)
        self.assertEqual(result[0],0)
        self.assertEqual((self.root/'fd').stat().st_size,800)

    def test_sigkill_after_sigterm_ignored(self):
        code='import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(20)'
        runner=ScriptRunner(code,check_timeout_seconds=.2,terminate_grace_seconds=.1,kill_wait_seconds=.2)
        started=time.monotonic()
        with self.assertRaises(s.JobError) as caught: runner.run(self.root/'unused','check')
        self.assertEqual(caught.exception.code,'timeout')
        self.assertFalse(caught.exception.stuck)
        self.assertLess(time.monotonic()-started,2)

    def test_process_group_descendant_stopped(self):
        marker=self.root/'escaped'
        code='import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",'+repr('import time,pathlib; time.sleep(.8); pathlib.Path('+repr(str(marker))+').touch()')+']); time.sleep(20)'
        runner=ScriptRunner(code,check_timeout_seconds=.2,terminate_grace_seconds=.1,kill_wait_seconds=.2)
        with self.assertRaises(s.JobError):runner.run(self.root/'unused','check')
        time.sleep(.9)
        self.assertFalse(marker.exists())


if __name__ == '__main__':
    unittest.main()
