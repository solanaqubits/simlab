import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_observations as o
import geek_work_exact_runner as r


class ExecutionLogHandleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.plan=self.root/'plan';self.ph=r.pilot.freeze(self.plan)['manifest_sha256'];self.execution=self.root/'execution';self.out=self.root/'handles'
    def make(self,raw=b'line 1\r\nline 2\xff',outcome='timed_out',truncated=False):
        p=dict(outcome=outcome,returncode=-9,wall_time_ms=30000,error=None,stdout_truncated=truncated,stderr_truncated=False)
        with patch.object(r,'supervise',return_value=(p,{'stdout.bin':raw,'stderr.bin':b''})):self.h=r.run(self.plan,self.ph,self.execution)['manifest_sha256']
    def capture(self):return o.capture_execution(self.execution,self.h,self.out)
    def test_native_binary_handles_and_exact_readback(self):
        self.make();result=self.capture();stream=result['streams'][0]
        raw,spec=o.verified(self.out/'stdout',stream['handle']);self.assertEqual(raw,b'line 1\r\nline 2\xff');self.assertEqual(spec['source']['encoding'],'binary')
        excerpt=o.excerpt(self.out/'stdout',stream['handle'],'lines',0,1);self.assertEqual(excerpt['utf8'],'line 1\r\n')
        o.verify_execution(self.out,result['index_sha256'],self.execution,self.h)
    def test_failed_and_empty_logs_not_promoted(self):
        self.make();self.capture();idx=json.loads((self.out/'index.json').read_bytes())
        self.assertEqual(idx['result_status'],'timed_out');self.assertEqual(idx['streams'][1]['bytes'],0)
        self.assertFalse(idx['complete_process_output_verified']);self.assertFalse(idx['execution_independently_verified'])
    def test_truncated_prefix_kept_and_flagged(self):
        self.make(b'x'*r.LOG_BYTES,'output_limit',True);self.capture();idx=json.loads((self.out/'index.json').read_bytes())
        self.assertTrue(idx['streams'][0]['reported_truncated']);self.assertEqual((self.out/'stdout/observation.bin').stat().st_size,r.LOG_BYTES)
    def test_native_handle_validity_does_not_establish_parent(self):
        self.make();result=self.capture();o.verify(self.out/'stdout',result['streams'][0]['handle'])
        with self.assertRaises(ValueError):o.verify_execution(self.out,result['index_sha256'],self.execution,'0'*64)
    def test_swap_streams_and_index_tamper(self):
        self.make();result=self.capture();a=self.out/'stdout/observation.bin';b=self.out/'stderr/observation.bin';x=a.read_bytes();a.write_bytes(b.read_bytes());b.write_bytes(x)
        with self.assertRaises(ValueError):o.verify_execution(self.out,result['index_sha256'],self.execution,self.h)
    def test_existing_output_and_failed_capture_preserve_parent(self):
        self.make();before=r.inventory(self.execution);self.capture()
        with self.assertRaises(FileExistsError):self.capture()
        with self.assertRaises(ValueError):o.capture_execution(self.execution,'0'*64,self.root/'bad')
        self.assertEqual(r.inventory(self.execution),before);self.assertFalse((self.root/'bad').exists())
    def test_extra_symlink_and_changed_index_rejected(self):
        self.make();result=self.capture();(self.out/'extra').mkdir()
        with self.assertRaises(ValueError):o.verify_execution(self.out,result['index_sha256'],self.execution,self.h)
        (self.out/'extra').rmdir();p=self.out/'index.json';idx=json.loads(p.read_bytes());idx['complete_process_output_verified']=True;p.write_bytes(o.m.encoded(idx))
        with self.assertRaises(ValueError):o.verify_execution(self.out,o.m.sha(p.read_bytes()),self.execution,self.h)
        p.unlink();p.symlink_to(self.execution/'receipt.json')
        with self.assertRaises(ValueError):o.verify_execution(self.out,result['index_sha256'],self.execution,self.h)
    def test_relocation_offline(self):
        self.make();result=self.capture();moved=self.root/'moved';shutil.move(self.execution,moved);shutil.rmtree(self.plan)
        with patch.object(subprocess,'Popen',side_effect=AssertionError('no process')):o.verify_execution(self.out,result['index_sha256'],moved,self.h)
    def test_cli_real_success(self):
        self.h=r.run(self.plan,self.ph,self.execution)['manifest_sha256']
        def cli(*args):return subprocess.run([sys.executable,'-B',o.__file__,*map(str,args)],capture_output=True,text=True)
        result=cli('capture-execution','--bundle',self.execution,'--sha256',self.h,'--output',self.out);self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        h=json.loads(result.stdout)['index_sha256'];self.assertEqual(cli('verify-execution','--bundle',self.out,'--sha256',h,'--execution',self.execution,'--execution-sha256',self.h).returncode,0)

if __name__=='__main__':unittest.main()
