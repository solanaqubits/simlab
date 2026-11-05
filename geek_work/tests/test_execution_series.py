import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_execution_series as s


class ExecutionSeriesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.plan=self.root/'plan';self.sha=s.runner.pilot.freeze(self.plan)['manifest_sha256'];self.out=self.root/'series'
    def attempt(self,name,fail=False):
        path=self.root/name
        if fail:
            process=dict(outcome='timed_out',returncode=-9,wall_time_ms=30000,error=None,stdout_truncated=False,stderr_truncated=False)
            with patch.object(s.runner,'supervise',return_value=(process,{'stdout.bin':b'','stderr.bin':b''})):r=s.runner.run(self.plan,self.sha,path)
        else:r=s.runner.run(self.plan,self.sha,path)
        return path,r['manifest_sha256']
    def build(self,items):return s.build([p for p,_ in items],[h for _,h in items],self.out)
    def report(self):return json.loads((self.out/'report.json').read_bytes())
    def test_all_selected_attempts_including_failure_counted(self):
        items=[self.attempt('failed',True),self.attempt('good')];r=self.build(items);g=self.report()['groups'][0]
        self.assertEqual(g['attempts_count'],2);self.assertEqual(g['control_suite_successes'],1)
        self.assertEqual(g['outcome_counts'],{'controls_observed':1,'timed_out':1})
        self.assertGreaterEqual(g['total_process_wall_time_ms'],30000)
        self.assertEqual(g['process_wall_ms_per_control_suite_success']['numerator'],g['total_process_wall_time_ms'])
        self.assertIsNone(g['monetary_cost_per_control_suite_success']);self.assertTrue(s.verify(self.out,r['manifest_sha256'])['exact_bindings_match'])
    def test_no_success_zero_denominator_is_null(self):
        self.build([self.attempt('failed',True)]);self.assertIsNone(self.report()['groups'][0]['process_wall_ms_per_control_suite_success'])
    def test_distinct_runtime_group_not_pooled(self):
        a=self.attempt('a',True);b=self.attempt('b',True)
        p=b[0]/'request.json';req=json.loads(p.read_bytes());req['runtime']['platform']='different';p.write_bytes(s.m.encoded(req))
        rp=b[0]/'receipt.json';rec=json.loads(rp.read_bytes());rec['request_sha256']=s.m.sha(p.read_bytes());rp.write_bytes(s.m.encoded(rec))
        files=s.runner.inventory(b[0]);meta=s.m.encoded(dict(schema=s.runner.SCHEMA,files={n:s.m.sha(v) for n,v in files.items()},directories=s.runner.directories(b[0])));(b[0]/'manifest.json').write_bytes(meta)
        result=self.build([a,(b[0],s.m.sha(meta))]);self.assertFalse(result['exact_bindings_match']);self.assertEqual(len(self.report()['groups']),2)
    def test_duplicate_id_rejected_even_relocated(self):
        a=self.attempt('a',True);shutil.copytree(a[0],self.root/'copy')
        with self.assertRaises(ValueError):self.build([a,(self.root/'copy',a[1])])
        self.assertFalse(self.out.exists())
    def test_relocation_offline_without_originals(self):
        a=self.attempt('a');r=self.build([a]);shutil.rmtree(a[0]);shutil.rmtree(self.plan)
        with patch.object(subprocess,'Popen',side_effect=AssertionError('no execution')):s.verify(self.out,r['manifest_sha256'])
    def test_tamper_promotions_and_wrong_anchor(self):
        r=self.build([self.attempt('a',True)])
        with self.assertRaises(ValueError):s.verify(self.out,'0'*64)
        p=self.out/'report.json';doc=json.loads(p.read_bytes());doc['global_attempt_completeness_verified']=True;p.write_bytes(s.m.encoded(doc))
        with self.assertRaises(ValueError):s.verify(self.out,r['manifest_sha256'])
    def test_missing_and_incomplete_attempt_rejected(self):
        path=self.root/'incomplete';path.mkdir();(path/'request.json').write_bytes(b'{}')
        with self.assertRaises(ValueError):self.build([(path,'0'*64)])
    def test_selection_bounds_and_existing_output(self):
        a=self.attempt('a',True);self.build([a])
        with self.assertRaises(FileExistsError):self.build([a])
        for items in ([],[a]*17):
            with self.assertRaises(ValueError):self.build(items)
        with self.assertRaises(ValueError):s.build([a[0]],[],self.root/'bad')
    def test_byte_limit(self):
        a=self.attempt('a',True)
        with patch.object(s,'MAX_TOTAL',1),self.assertRaises(ValueError):self.build([a])
    def test_empty_partial_directory_preserved(self):
        a=self.attempt('a',True);(a[0]/'run').mkdir();files=s.runner.inventory(a[0]);meta=s.m.encoded(dict(schema=s.runner.SCHEMA,files={n:s.m.sha(v) for n,v in files.items()},directories=s.runner.directories(a[0])));(a[0]/'manifest.json').write_bytes(meta)
        r=self.build([(a[0],s.m.sha(meta))]);self.assertTrue((self.out/'attempts/0000/run').is_dir());s.verify(self.out,r['manifest_sha256'])
    def test_extra_directory_and_symlink_rejected(self):
        r=self.build([self.attempt('a',True)]);(self.out/'extra').mkdir()
        with self.assertRaises(ValueError):s.verify(self.out,r['manifest_sha256'])
        (self.out/'extra').rmdir();p=self.out/'report.json';raw=p.read_bytes();p.unlink();external=self.root/'report';external.write_bytes(raw);p.symlink_to(external)
        with self.assertRaises(ValueError):s.verify(self.out,r['manifest_sha256'])
    def test_cli(self):
        a=self.attempt('a',True)
        def cli(*args):return subprocess.run([sys.executable,'-B',s.__file__,*map(str,args)],capture_output=True,text=True)
        result=cli('build','--attempt',a[0],'--sha256',a[1],'--output',self.out);self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        h=json.loads(result.stdout)['manifest_sha256'];self.assertEqual(cli('verify','--bundle',self.out,'--sha256',h).returncode,0)

if __name__=='__main__':unittest.main()
