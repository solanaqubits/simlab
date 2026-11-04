import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_exact_runner as r


class ExactRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.plan=self.root/'plan';self.out=self.root/'execution'
        self.sha=r.pilot.freeze(self.plan)['manifest_sha256']
    def execute(self):return r.run(self.plan,self.sha,self.out)
    def command(self,code,**kw):return r.supervise([sys.executable,'-I','-B','-c',code],self.root,**kw)
    def reseal(self):
        files=r.inventory(self.out);meta=r.m.encoded(dict(schema=r.SCHEMA,files={n:r.m.sha(b) for n,b in files.items()},directories=r.directories(self.out)))
        (self.out/'manifest.json').write_bytes(meta);return r.m.sha(meta)
    def failed(self,outcome='timed_out',rc=-9):
        process=dict(outcome=outcome,returncode=rc,wall_time_ms=30,error=None,stdout_truncated=False,stderr_truncated=False)
        with patch.object(r,'supervise',return_value=(process,{'stdout.bin':b'partial','stderr.bin':b'failure'})):
            return self.execute()
    def test_real_fixed_worker_and_limits(self):
        result=self.execute();self.assertEqual(result['status'],'controls_observed')
        receipt=json.loads((self.out/'receipt.json').read_bytes())
        self.assertEqual(receipt['process']['returncode'],0)
        self.assertGreaterEqual(receipt['process']['wall_time_ms'],0)
        self.assertEqual(json.loads((self.out/'worker-limits.json').read_bytes()),dict(address_space=[r.MEMORY_BYTES]*2,core_dump=[0,0]))
        self.assertIsNone(receipt['peak_memory_bytes']);self.assertIsNone(receipt['monetary_cost'])
        self.assertFalse(receipt['execution_independently_verified'])
        self.assertEqual(r.verify(self.out,result['manifest_sha256'])['status'],'controls_observed')
    def test_timeout_retains_prefix_and_kills_worker(self):
        p,logs=self.command("import time;print('started',flush=True);time.sleep(10)",wall_seconds=0.2)
        self.assertEqual(p['outcome'],'timed_out');self.assertLess(p['wall_time_ms'],3000)
        self.assertIn(b'started',logs['stdout.bin']);self.assertLess(p['returncode'],0)
    def test_output_limit_both_streams(self):
        for fd,name in [(1,'stdout'),(2,'stderr')]:
            p,logs=self.command(f"import os;os.write({fd},b'x'*100000)",log_bytes=1024)
            self.assertEqual(p['outcome'],'output_limit');self.assertEqual(len(logs[name+'.bin']),1024)
            self.assertTrue(p[name+'_truncated'])
    def test_signal_not_mathematical_mismatch(self):
        p,logs=self.command('import os,signal;os.kill(os.getpid(),signal.SIGTERM)')
        self.assertEqual(p['outcome'],'signalled');self.assertEqual(p['returncode'],-signal.SIGTERM)
    def test_launch_error(self):
        p,logs=r.supervise(['/nonexistent-geek-work-executable'],self.root)
        self.assertEqual(p['outcome'],'launch_failed');self.assertIsNone(p['returncode'])
        self.assertTrue(p['error']);self.assertEqual(logs,{'stdout.bin':b'','stderr.bin':b''})
    def test_memory_ceiling_is_real_per_process(self):
        p,logs=self.command(r.BOOTSTRAP.split('sys.path.insert')[0]+'\ntry: x=bytearray(536870912)\nexcept MemoryError: print("allocation refused")\nelse: raise RuntimeError("limit failed")')
        self.assertEqual(p['returncode'],0);self.assertIn(b'allocation refused',logs['stdout.bin'])
    def test_parent_environment_not_forwarded(self):
        with patch.dict(os.environ,{'GEEK_SECRET_FIXTURE':'not-for-worker'}):
            p,logs=self.command("import os;print(os.getenv('GEEK_SECRET_FIXTURE'))")
        self.assertEqual(logs['stdout.bin'],b'None\n')
    def test_failed_receipt_retained_and_replayable(self):
        result=self.failed();self.assertEqual(result['status'],'timed_out')
        rec=json.loads((self.out/'receipt.json').read_bytes());self.assertIsNone(rec['result']['control_suite_passed'])
        self.assertEqual((self.out/'stderr.bin').read_bytes(),b'failure')
        self.assertEqual(r.verify(self.out,result['manifest_sha256'])['status'],'timed_out')
    def test_exit_zero_without_artifact_is_invalid(self):
        result=self.failed('exited',0);self.assertEqual(result['status'],'artifact_invalid')
        self.assertEqual(r.verify(self.out,result['manifest_sha256'])['status'],'artifact_invalid')
    def test_exit_two_not_identity_mismatch(self):
        result=self.failed('exited',2);self.assertEqual(result['status'],'execution_failed')
    def test_partial_empty_output_retained(self):
        def failure(*args):
            (self.out/'run').mkdir()
            return dict(outcome='signalled',returncode=-9,wall_time_ms=1,error=None,stdout_truncated=False,stderr_truncated=False),{'stdout.bin':b'','stderr.bin':b''}
        with patch.object(r,'supervise',side_effect=failure):result=self.execute()
        self.assertTrue((self.out/'run').is_dir());self.assertEqual(r.verify(self.out,result['manifest_sha256'])['status'],'signalled')
    def test_completed_control_mismatch_remains_distinct(self):
        def candidate_failure(*args):
            parent=r.pilot.plan_bytes(self.plan,self.sha);rows=r.pilot.generator.candidates(r.pilot.TRAINING['samples']);rows[-1]['coefficients'][0]='1'
            files,_=r.pilot.artifacts(parent,rows);meta=r.pilot.manifest(files)
            r.archive.write_tree(self.out/'run',{**files,'manifest.json':meta})
            (self.out/'worker-limits.json').write_bytes(r.m.encoded(dict(address_space=[r.MEMORY_BYTES]*2,core_dump=[0,0])))
            return dict(outcome='exited',returncode=3,wall_time_ms=1,error=None,stdout_truncated=False,stderr_truncated=False),{'stdout.bin':b'','stderr.bin':b''}
        with patch.object(r,'supervise',side_effect=candidate_failure):result=self.execute()
        self.assertEqual(result['status'],'control_pattern_mismatch');self.assertEqual(r.verify(self.out,result['manifest_sha256'])['status'],'control_pattern_mismatch')
    def test_relocation_without_launch_or_generation(self):
        result=self.execute();moved=self.root/'moved';shutil.move(self.out,moved);shutil.rmtree(self.plan)
        with patch.object(subprocess,'Popen',side_effect=AssertionError('no subprocess')),patch.object(r.pilot.generator,'candidates',side_effect=AssertionError('no generation')):
            check=r.verify(moved,result['manifest_sha256'])
        self.assertFalse(check['subprocess_rerun']);self.assertFalse(check['os_limits_reenforced_here'])
    def test_wrong_anchor_log_tamper_and_symlinks(self):
        result=self.failed()
        with self.assertRaises(ValueError):r.verify(self.out,'0'*64)
        p=self.out/'stdout.bin';p.write_bytes(b'tamper')
        with self.assertRaises(ValueError):r.verify(self.out,result['manifest_sha256'])
        external=self.root/'external';p.rename(external);p.symlink_to(external)
        with self.assertRaises(ValueError):r.verify(self.out,result['manifest_sha256'])
    def test_receipt_promotions_rejected_even_when_resealed(self):
        result=self.failed();p=self.out/'receipt.json';rec=json.loads(p.read_bytes());rec['scientific_verification']=True;p.write_bytes(r.m.encoded(rec))
        with self.assertRaises(ValueError):r.verify(self.out,self.reseal())
    def test_log_bound_and_invalid_process_fields(self):
        for key,value in [('returncode',True),('wall_time_ms',-1),('outcome','memory_proved')]:
            self.failed();p=self.out/'receipt.json';rec=json.loads(p.read_bytes());rec['process'][key]=value;p.write_bytes(r.m.encoded(rec))
            with self.assertRaises(ValueError):r.verify(self.out,self.reseal())
            shutil.rmtree(self.out)
        self.failed();(self.out/'stdout.bin').write_bytes(b'x'*(r.LOG_BYTES+1))
        with self.assertRaises(ValueError):r.verify(self.out,self.reseal())
    def test_existing_output_and_invalid_plan_do_not_launch(self):
        self.failed()
        with patch.object(r,'supervise',side_effect=AssertionError('must not launch')):
            with self.assertRaises(FileExistsError):self.execute()
            with self.assertRaises(ValueError):r.run(self.plan,'0'*64,self.root/'other')
        self.assertFalse((self.root/'other').exists())
    def test_unfinished_attempt_not_success_and_no_retry_overwrite(self):
        with patch.object(r,'supervise',side_effect=RuntimeError('coordinator crash')):
            with self.assertRaises(RuntimeError):self.execute()
        self.assertTrue((self.out/'request.json').exists());self.assertFalse((self.out/'manifest.json').exists())
        with self.assertRaises(ValueError):r.verify(self.out,'0'*64)
    def test_extra_files_and_directories_rejected(self):
        self.failed();(self.out/'extra').write_bytes(b'x')
        with self.assertRaises(ValueError):r.verify(self.out,self.reseal())
    def test_extra_empty_directory_rejected(self):
        self.failed();(self.out/'extra').mkdir()
        with self.assertRaises(ValueError):r.verify(self.out,self.reseal())
    def test_fixed_worker_refuses_changed_runtime_binding(self):
        actual=r.runtime()
        with patch.object(r,'runtime',return_value={**actual,'python_version':'0.0.0'}):result=self.execute()
        self.assertEqual(result['status'],'execution_failed')
        self.assertFalse((self.out/'run').exists())
        self.assertIn(b'worker runtime changed',(self.out/'stderr.bin').read_bytes())
    def test_boolean_limit_rejected(self):
        self.failed();p=self.out/'request.json';request=json.loads(p.read_bytes())
        request['limits']['core_dump_bytes']=False;p.write_bytes(r.m.encoded(request))
        with self.assertRaises(ValueError):r.verify(self.out,self.reseal())
    def test_sigterm_supervisor_cleans_child_and_returns_interrupted(self):
        ready=self.root/'child-ready'
        child="import os,time;from pathlib import Path;Path("+repr(str(ready))+").write_text(str(os.getpid()));time.sleep(10)"
        code="import sys,json;sys.path.insert(0,"+repr(str(Path(r.__file__).parent))+");import geek_work_exact_runner as r;p,_=r.supervise("+repr([sys.executable,'-I','-B','-c',child])+","+repr(str(self.root))+",wall_seconds=5);print(json.dumps(p))"
        proc=subprocess.Popen([sys.executable,'-I','-B','-c',code],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            end=time.monotonic()+3
            while not ready.exists() and time.monotonic()<end:time.sleep(0.01)
            self.assertTrue(ready.exists(),'child did not start')
            child_pid=int(ready.read_text());proc.send_signal(signal.SIGTERM)
            stdout,stderr=proc.communicate(timeout=3);self.assertEqual(proc.returncode,0,stderr)
            self.assertEqual(json.loads(stdout)['outcome'],'interrupted')
            self.assertFalse(Path('/proc/'+str(child_pid)).exists(),'child not reaped')
        finally:
            if proc.poll() is None:proc.kill()
            proc.communicate()
    def test_cli_end_to_end_and_arbitrary_command_rejected(self):
        def cli(*args):return subprocess.run([sys.executable,'-B',r.__file__,*map(str,args)],capture_output=True,text=True)
        result=cli('run','--bundle',self.plan,'--sha256',self.sha,'--output',self.out)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        anchor=json.loads(result.stdout)['manifest_sha256']
        self.assertEqual(cli('verify','--bundle',self.out,'--sha256',anchor).returncode,0)
        self.assertEqual(cli('run','--command','echo hello').returncode,2)


if __name__=='__main__':unittest.main()
