import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_exact_runner as r


class ExecutionInspectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.plan=self.root/'plan';self.ph=r.pilot.freeze(self.plan)['manifest_sha256'];self.out=self.root/'execution'
    def partial(self):
        with patch.object(r,'supervise',side_effect=RuntimeError('interrupted coordinator')):
            with self.assertRaises(RuntimeError):r.run(self.plan,self.ph,self.out)
    def complete(self):return r.run(self.plan,self.ph,self.out)['manifest_sha256']
    def test_prelaunch_request_not_claimed_started(self):
        self.partial();before=r.inventory(self.out);result=r.inspect_execution(self.out)
        self.assertEqual(result['state'],'incomplete');self.assertIsNone(result['process_started']);self.assertIsNone(result['process_running']);self.assertIsNone(result['result_status']);self.assertEqual(r.inventory(self.out),before)
    def test_no_manifest_even_with_success_receipt_stays_incomplete(self):
        self.complete();(self.out/'manifest.json').unlink();result=r.inspect_execution(self.out)
        self.assertTrue(result['receipt_present']);self.assertEqual(result['state'],'incomplete');self.assertIsNone(result['result_status'])
        self.assertFalse((self.out/'manifest.json').exists())
    def test_unanchored_complete_not_implicitly_verified(self):
        h=self.complete();result=r.inspect_execution(self.out)
        self.assertEqual(result['state'],'sealed_unverified');self.assertEqual(result['observed_manifest_sha256'],h);self.assertFalse(result['external_manifest_checked']);self.assertIsNone(result['result_status'])
    def test_anchored_complete(self):
        h=self.complete();result=r.inspect_execution(self.out,h)
        self.assertEqual(result['state'],'verified_complete');self.assertEqual(result['result_status'],'controls_observed');self.assertIsNone(result['process_running'])
    def test_anchored_operational_failure_remains_failure(self):
        process=dict(outcome='timed_out',returncode=-9,wall_time_ms=30000,error=None,stdout_truncated=False,stderr_truncated=False)
        with patch.object(r,'supervise',return_value=(process,{'stdout.bin':b'','stderr.bin':b''})):h=self.complete()
        result=r.inspect_execution(self.out,h);self.assertEqual(result['state'],'verified_complete');self.assertEqual(result['result_status'],'timed_out')
    def test_missing_and_wrong_final_anchor_rejected(self):
        self.partial()
        with self.assertRaises(ValueError):r.inspect_execution(self.out,'0'*64)
        (self.out/'manifest.json').write_bytes(b'{}')
        with self.assertRaises(ValueError):r.inspect_execution(self.out,'0'*64)
    def test_partial_logs_and_empty_run_directory_preserved(self):
        self.partial();(self.out/'run').mkdir();(self.out/'stderr.bin').write_bytes(b'partial\xff')
        result=r.inspect_execution(self.out);self.assertEqual(result['logs_present'],dict(stdout=False,stderr=True));self.assertIn('run',result['directories'])
        row=next(x for x in result['files'] if x['path']=='stderr.bin');self.assertEqual(row['bytes'],8)
    def test_unrecognized_empty_directory(self):
        self.out.mkdir();result=r.inspect_execution(self.out);self.assertEqual(result['state'],'unrecognized');self.assertIsNone(result['attempt_id'])
    def test_malformed_request_not_guessed(self):
        self.partial();(self.out/'request.json').write_bytes(b'{')
        with self.assertRaises(ValueError):r.inspect_execution(self.out)
    def test_symlink_extra_and_nonexistent_refused(self):
        with self.assertRaises(ValueError):r.inspect_execution(self.out)
        self.partial();(self.out/'extra').mkdir()
        with self.assertRaises(ValueError):r.inspect_execution(self.out)
        (self.out/'extra').rmdir();(self.out/'stdout.bin').symlink_to(self.plan/'spec.json')
        with self.assertRaises(ValueError):r.inspect_execution(self.out)
    def test_bounded_inventory_and_no_process_actions(self):
        self.partial()
        with patch.object(r,'MAX_TOTAL',1),self.assertRaises(ValueError):r.inspect_execution(self.out)
        with patch.object(subprocess,'Popen',side_effect=AssertionError('no launch')),patch.object(r.os,'killpg',side_effect=AssertionError('no kill')):r.inspect_execution(self.out)
    def test_cli_exit_states(self):
        h=self.complete()
        def cli(*args):return subprocess.run([sys.executable,'-B',r.__file__,'inspect','--bundle',str(self.out),*args],capture_output=True,text=True)
        self.assertEqual(cli().returncode,4);self.assertEqual(cli('--sha256',h).returncode,0)
        self.assertEqual(cli('--sha256','0'*64).returncode,2)
        (self.out/'manifest.json').unlink();result=cli();self.assertEqual(result.returncode,4);self.assertEqual(json.loads(result.stdout)['state'],'incomplete')

if __name__=='__main__':unittest.main()
