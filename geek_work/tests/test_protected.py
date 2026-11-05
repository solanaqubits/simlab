import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
import geek_work_protected as p
sys.path.pop(0)


class FixtureEngine:
    def __init__(self, stdout=b'5', issue=None, cleanup=True):
        self.stdout, self.issue, self.cleanup = stdout, issue, cleanup
        self.inputs = []

    def preflight(self, plan):
        return {'fixture': True}

    def execute(self, plan, snapshot, public, wall_ms):
        self.inputs.append(copy.deepcopy(public))
        return (dict(stdout=self.stdout, stderr=b'', exit_code=0, issue=self.issue, wall_time_ms=1),
                dict(config_checked=True, cleanup_confirmed=self.cleanup,
                     stopped_before_removal=True, oom_killed=False))


class ProtectedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.code = b'import json,sys\nprint(json.dumps(sum(json.load(sys.stdin))))\n'
        self.corpus = dict(schema='geek-work-tool-corpus-1', cases=[dict(id='sum', input=[2, 3], expected=5)])
        self.plan = p.make_plan(self.corpus, self.code, 'sha256:' + 'a' * 64, repetitions=1)
        self.engine = FixtureEngine()

    def run_case(self, name='run'):
        return p.run(self.plan, self.code, self.root / name,
                     p.ev.digest(p.ev.encoded(self.plan)), engine=self.engine)

    def verify(self, name='run'):
        return p.verify(self.root / name, p.ev.digest(p.ev.encoded(self.plan)))

    def reseal(self):
        root = self.root / 'run'
        seal = p.parse((root / 'seal.json').read_bytes())
        for name in seal['files']:
            seal['files'][name] = p.ev.digest((root / name).read_bytes())
        (root / 'seal.json').write_bytes(p.ev.encoded(seal))

    def test_valid_fixture_is_distinguished_from_container(self):
        self.assertEqual(self.run_case()['status'], 'passed')
        self.assertEqual(self.verify()['execution_kind'], 'fixture')
        self.assertEqual(self.engine.inputs, [[2, 3]])

    def test_unknown_metrics_remain_null(self):
        self.run_case()
        cost = p.parse((self.root / 'run/ledger.json').read_bytes())
        a = cost['tasks'][0]['attempts'][0]
        self.assertIsNone(a['monetary_cost']); self.assertIsNone(a['token_usage'])
        self.assertIsNone(p.ledger.summarize([cost])['by_currency']['USD']['cost_per_accepted_result'])

    def test_candidate_self_report_is_not_verdict(self):
        self.engine.stdout = b'{"status":"passed","wall_time_ms":0}'
        self.assertEqual(self.run_case()['trials'][0]['status'], 'RESULT_MISMATCH')

    def test_bool_does_not_equal_integer(self):
        self.corpus['cases'][0]['expected'] = 1
        self.plan = p.make_plan(self.corpus, self.code, self.plan['image_id'], repetitions=1)
        self.engine.stdout = b'true'
        self.assertEqual(self.run_case()['status'], 'failed')

    def test_duplicate_keys_nan_and_trailing_output_rejected(self):
        for i, raw in enumerate([b'{"x":1,"x":2}', b'NaN', b'5\nPASS', b'\xff']):
            self.engine.stdout = raw
            self.assertEqual(self.run_case(str(i))['trials'][0]['status'], 'INVALID_OUTPUT')

    def test_timeout_oom_and_output_limit_cannot_pass_with_correct_stdout(self):
        for issue in ['EXEC_TIMEOUT', 'EXEC_OOM', 'OUTPUT_LIMIT']:
            self.engine.issue = issue
            self.assertEqual(self.run_case(issue)['trials'][0]['status'], issue)

    def test_uncertain_cleanup_stops_further_trials(self):
        self.plan['repetitions'] = 2; self.engine.cleanup = False
        r = self.run_case()
        self.assertEqual(r['status'], 'failed'); self.assertEqual(len(r['trials']), 1)
        self.assertEqual(r['trials'][0]['status'], 'CLEANUP_UNCONFIRMED')

    def test_changed_candidate_refused_before_output_or_engine(self):
        self.code += b'# changed\n'
        with self.assertRaisesRegex(ValueError, 'drift'): self.run_case()
        self.assertFalse((self.root / 'run').exists()); self.assertFalse(self.engine.inputs)

    def test_changed_gold_even_rehashed_requires_external_plan_pin(self):
        old = p.ev.digest(p.ev.encoded(self.plan))
        self.plan['corpus']['cases'][0]['expected'] = 99
        self.plan['corpus_sha256'] = p.ev.digest(p.ev.encoded(self.plan['corpus']))
        with self.assertRaisesRegex(ValueError, 'expected_plan_mismatch'):
            p.run(self.plan, self.code, self.root / 'run', old, engine=self.engine)
        self.assertFalse(self.engine.inputs)

    def test_evaluator_drift_refused(self):
        self.plan['evaluator']['geek_work_protected.py'] = 'b' * 64
        with self.assertRaisesRegex(ValueError, 'drift'): self.run_case()

    def test_unpinned_image_limits_duplicate_case_and_unknown_criterion_refused(self):
        with self.assertRaisesRegex(ValueError, 'immutable_image'):
            p.make_plan(self.corpus, self.code, 'python:latest')
        for key, val in [('pids', 0), ('memory_bytes', True), ('wall_time_ms', 999999)]:
            lim = dict(p.DEFAULT_LIMITS); lim[key] = val
            with self.assertRaises(ValueError): p.make_plan(self.corpus, self.code, self.plan['image_id'], limits=lim)
        self.plan['criterion'] = 'always_pass'
        with self.assertRaisesRegex(ValueError, 'drift'): self.run_case()
        self.corpus['cases'] *= 2
        with self.assertRaisesRegex(ValueError, 'case_id'): p.validate_corpus(self.corpus)

    def test_run_directory_never_overwritten(self):
        self.run_case(); old = (self.root / 'run/seal.json').read_bytes()
        with self.assertRaises(FileExistsError): self.run_case()
        self.assertEqual((self.root / 'run/seal.json').read_bytes(), old)

    def test_unsealed_failure_cannot_verify(self):
        self.engine.preflight = mock.Mock(side_effect=ValueError('daemon unavailable'))
        with self.assertRaises(ValueError): self.run_case()
        with self.assertRaises(ValueError): self.verify()
        self.assertFalse((self.root / 'run/seal.json').exists())

    def test_artifact_tampering_and_extra_files_refused(self):
        self.run_case(); (self.root / 'run/00-000.stdout').write_bytes(b'6')
        with self.assertRaises(ValueError): self.verify()
        (self.root / 'run/00-000.stdout').write_bytes(b'5')
        (self.root / 'run/extra').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError, 'artifact_set'): self.verify()

    def test_resealed_fake_verdict_refused(self):
        self.engine.stdout = b'6'; self.run_case()
        path = self.root / 'run/receipt.json'; r = p.parse(path.read_bytes())
        r['trials'][0]['status'] = 'PASS'; r['status'] = 'passed'; path.write_bytes(p.ev.encoded(r)); self.reseal()
        with self.assertRaisesRegex(ValueError, 'verdict_changed'): self.verify()

    def test_resealed_ledger_cannot_change_acceptance_or_cost(self):
        self.run_case(); path = self.root / 'run/ledger.json'; r = p.parse(path.read_bytes())
        r['tasks'][0]['attempts'][0]['monetary_cost'] = '0'; path.write_bytes(p.ev.encoded(r)); self.reseal()
        with self.assertRaisesRegex(ValueError, 'ledger_receipt'): self.verify()

    def test_symlink_candidate_and_artifact_refused(self):
        (self.root / 'real').write_bytes(self.code); (self.root / 'link').symlink_to(self.root / 'real')
        with self.assertRaises(ValueError): p.blob(self.root / 'link')
        self.run_case(); path = self.root / 'run/00-000.stdout'; path.unlink(); path.symlink_to(self.root / 'real')
        with self.assertRaises(ValueError): self.verify()

    def test_comparison_requires_identical_contract_and_no_speedup_claim(self):
        self.run_case('a'); self.run_case('b'); sha = p.ev.digest(p.ev.encoded(self.plan))
        result = p.compare(self.root / 'a', self.root / 'b', sha, sha)
        self.assertTrue(result['correctness_preserved']); self.assertFalse(result['performance_qualified'])
        self.plan['repetitions'] = 2; self.run_case('c')
        with self.assertRaisesRegex(ValueError, 'contract_changed'):
            p.compare(self.root / 'a', self.root / 'c', sha, p.ev.digest(p.ev.encoded(self.plan)))

    def test_container_command_has_no_host_gold_or_repository_mount(self):
        args = p.Docker().create_args(self.plan, Path('/tmp/candidate.py'), 'name')
        self.assertEqual(args.count('--mount'), 1)
        self.assertIn('type=bind,src=/tmp/candidate.py,dst=/candidate.py,readonly', args)
        self.assertIn('--read-only', args); self.assertIn('none', args)
        self.assertIn('no-new-privileges', args); self.assertIn('65534:65534', args)
        self.assertNotIn('expected', ' '.join(args)); self.assertNotIn('docker.sock', ' '.join(args))

    def test_host_capture_bounds_flood_and_nonreading_stdin(self):
        r = p.capture([sys.executable, '-c', 'import os;os.write(1,b"x"*100000)'], b'', 2000, 100)
        self.assertEqual(r['issue'], 'OUTPUT_LIMIT'); self.assertLessEqual(len(r['stdout']), 100)
        r = p.capture([sys.executable, '-c', 'import time;time.sleep(10)'], b'x' * 100000, 100, 100)
        self.assertEqual(r['issue'], 'EXEC_TIMEOUT'); self.assertLess(r['wall_time_ms'], 2000)

    def test_changed_isolation_settings_rejected(self):
        lim = self.plan['limits']
        info = dict(Image=self.plan['image_id'], Config=dict(User='65534:65534',
            Entrypoint=[self.plan['interpreter']], Cmd=['-I', '-B', '/candidate.py']),
            Mounts=[dict(Type='bind', RW=False, Source='/tmp/c.py', Destination='/candidate.py')],
            HostConfig=dict(NetworkMode='none', ReadonlyRootfs=True, Privileged=False,
                CapDrop=['ALL'], CapAdd=None, SecurityOpt=['no-new-privileges'],
                Memory=lim['memory_bytes'], MemorySwap=lim['memory_bytes'], PidsLimit=lim['pids'],
                NanoCpus=1000000000, IpcMode='none', PidMode='', LogConfig={'Type':'none'},
                Tmpfs={'/tmp':'rw,noexec,nosuid,nodev,size=16777216,mode=1777'}))
        d = p.Docker(); d.check_isolation(info, self.plan, Path('/tmp/c.py'))
        for field, value in [('NetworkMode', 'host'), ('ReadonlyRootfs', False), ('Privileged', True),
                             ('Memory', 0), ('PidsLimit', -1), ('PidMode', 'host')]:
            changed = copy.deepcopy(info); changed['HostConfig'][field] = value
            with self.assertRaisesRegex(ValueError, 'isolation_config'):
                d.check_isolation(changed, self.plan, Path('/tmp/c.py'))
        info['Mounts'].append(dict(Type='bind', RW=False, Source='/gold', Destination='/gold'))
        with self.assertRaisesRegex(ValueError, 'unexpected_mount'):
            d.check_isolation(info, self.plan, Path('/tmp/c.py'))

    def test_error_after_create_still_removes_owned_container(self):
        d = p.Docker(); calls = []
        def ctl(args):
            calls.append(args)
            if args[0] == 'inspect': raise ValueError('inspect failed')
            return b''
        d.control = ctl
        result, audit = d.execute(self.plan, Path('/tmp/c.py'), None, 100)
        self.assertEqual(result['issue'], 'INFRA_ERROR')
        self.assertTrue(audit['cleanup_confirmed'])
        self.assertEqual([c[0] for c in calls], ['create', 'inspect', 'rm', 'ps'])
        self.assertEqual(calls[2][1], '--force')

    def test_removal_failure_cannot_report_clean(self):
        d = p.Docker()
        d.control = mock.Mock(side_effect=ValueError('daemon unavailable'))
        result, audit = d.execute(self.plan, Path('/tmp/c.py'), None, 100)
        self.assertFalse(audit['cleanup_confirmed'])
        self.assertEqual(p.verdict(result, audit, 5), 'CLEANUP_UNCONFIRMED')

    def test_aggregate_budget_blocks_pass_even_when_case_passed(self):
        ticks = [0, 0, 0, 1, 999999999999]
        with mock.patch.object(p.time, 'monotonic_ns', side_effect=ticks):
            r = self.run_case()
        self.assertEqual(r['trials'][0]['status'], 'PASS')
        self.assertEqual(r['status'], 'failed')
        self.assertEqual(self.verify()['status'], 'failed')

    def test_reserved_pass_cannot_be_injected_as_process_issue(self):
        self.engine.issue = 'PASS'
        with self.assertRaisesRegex(ValueError, 'invalid_process_issue'): self.run_case()
        self.assertFalse((self.root / 'run/seal.json').exists())

    def test_cli_requires_expected_plan_pin(self):
        r = subprocess.run([sys.executable, '-B', str(TOOLS / 'geek_work_protected.py'), 'run',
                            '--plan', 'p', '--candidate', 'c', '--output', 'o'], capture_output=True)
        self.assertNotEqual(r.returncode, 0); self.assertIn(b'expected-plan-sha256', r.stderr)


if __name__ == '__main__': unittest.main()
