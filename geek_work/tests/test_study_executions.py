import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_study_executions as a


class StudyExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.inputs=self.root/'inputs';self.plan=self.inputs/'plan';self.psha=a.series.runner.pilot.freeze(self.plan)['manifest_sha256']
        run=self.root/'run';rh=a.series.runner.run(self.plan,self.psha,run)['manifest_sha256']
        self.series=self.root/'series';self.sha=a.series.build([run],[rh],self.series)['manifest_sha256']
        self.tree=self.root/'tree';self.out=self.root/'attached'
        self.spec=dict(schema='geek-work-experiment-tree-1',id='study',title='Study <test>',nodes=[dict(id='base',parent=None,builds_on=None,plan=dict(path='plan',sha256=self.psha),ledger=None,claim_maps=[])])
        self.tree_build()
    def tree_build(self):
        path=self.root/'spec.json';path.write_bytes(a.m.encoded(self.spec))
        if self.tree.exists():shutil.rmtree(self.tree)
        self.th=a.study.build(path,a.m.sha(path.read_bytes()),self.inputs,self.tree)['manifest_sha256']
    def build(self,bindings=None):return a.build(self.tree,self.th,bindings or [('base',self.series,self.sha)],self.out)
    def test_plan_binding_preserves_native_tree_and_separates_costs(self):
        before=(self.tree/'manifest.json').read_bytes();r=self.build();doc=json.loads((self.out/'report.json').read_bytes())
        self.assertEqual((self.out/'tree/manifest.json').read_bytes(),before);self.assertTrue(doc['nodes'][0]['plan_byte_binding_checked']);self.assertFalse(doc['ledger_costs_combined']);self.assertFalse(doc['scientific_verification']);a.verify(self.out,r['manifest_sha256'])
    def test_wrong_plan_rejected(self):
        # A distinct valid frozen plan: explanation change, same profile inputs.
        raw=json.loads((self.plan/'spec.json').read_bytes());raw['title']='Different plan'
        spec=self.inputs/'other-spec.json';spec.write_bytes(a.m.encoded(raw));other=self.inputs/'other'
        h=a.study.experiment.capture('plan',spec,a.m.sha(spec.read_bytes()),self.plan/'sources',other)['manifest_sha256']
        self.spec['nodes'][0]['plan']=dict(path='other',sha256=h);self.tree_build()
        with self.assertRaisesRegex(ValueError,'does not match'):self.build()
    def test_unknown_and_duplicate_nodes(self):
        for bindings in [[('missing',self.series,self.sha)],[('base',self.series,self.sha)]*2]:
            with self.assertRaises(ValueError):self.build(bindings)
    def test_same_execution_at_two_nodes_rejected(self):
        self.spec['nodes'].append(dict(id='child',parent='base',builds_on='Same plan',plan=dict(path='plan',sha256=self.psha),ledger=None,claim_maps=[]));self.tree_build()
        with self.assertRaisesRegex(ValueError,'multiple nodes'):self.build([('base',self.series,self.sha),('child',self.series,self.sha)])
    def test_unbound_nodes_visible(self):
        self.spec['nodes'].append(dict(id='child',parent='base',builds_on='Pending',plan=dict(path='plan',sha256=self.psha),ledger=None,claim_maps=[]));self.tree_build();self.build()
        self.assertEqual(json.loads((self.out/'report.json').read_bytes())['nodes_without_execution_binding'],['child'])
    def test_offline_relocation(self):
        r=self.build();shutil.rmtree(self.tree);shutil.rmtree(self.series);shutil.rmtree(self.inputs)
        with patch.object(subprocess,'Popen',side_effect=AssertionError('no process')):a.verify(self.out,r['manifest_sha256'])
    def test_tamper_wrong_anchor_extra_and_symlink(self):
        r=self.build()
        with self.assertRaises(ValueError):a.verify(self.out,'0'*64)
        (self.out/'extra').mkdir()
        with self.assertRaises(ValueError):a.verify(self.out,r['manifest_sha256'])
        (self.out/'extra').rmdir();p=self.out/'report.json';p.write_bytes(p.read_bytes()+b' ')
        with self.assertRaises(ValueError):a.verify(self.out,r['manifest_sha256'])
        p.unlink();p.symlink_to(self.tree/'report.json')
        with self.assertRaises(ValueError):a.verify(self.out,r['manifest_sha256'])
    def test_bounds_and_no_overwrite(self):
        with patch.object(a,'MAX_TOTAL',1),self.assertRaises(ValueError):self.build()
        self.build()
        with self.assertRaises(FileExistsError):self.build()
    def test_ledger_kept_separate(self):
        raw=(self.root/'run/run/ledger.json').read_bytes();(self.inputs/'ledger.json').write_bytes(raw)
        self.spec['nodes'][0]['ledger']=dict(path='ledger.json',sha256=a.m.sha(raw),task_id=a.series.runner.pilot.PROFILE)
        self.tree_build();self.build();report=json.loads((self.out/'report.json').read_bytes())
        self.assertTrue(report['nodes'][0]['ledger_present']);self.assertFalse(report['ledger_costs_combined'])
        self.assertEqual(report['nodes'][0]['ledger_execution_overlap'],'not_assessed')
    def test_failed_execution_with_empty_output_preserved(self):
        path=self.root/'failed'
        def fail(*args):
            (path/'run').mkdir()
            return dict(outcome='timed_out',returncode=-9,wall_time_ms=30000,error=None,stdout_truncated=False,stderr_truncated=False),{'stdout.bin':b'', 'stderr.bin':b''}
        with patch.object(a.series.runner,'supervise',side_effect=fail):r=a.series.runner.run(self.plan,self.psha,path)
        failed_series=self.root/'failed-series';h=a.series.build([path],[r['manifest_sha256']],failed_series)['manifest_sha256']
        result=self.build([('base',failed_series,h)]);a.verify(self.out,result['manifest_sha256'])
        doc=json.loads((self.out/'report.json').read_bytes());self.assertEqual(doc['nodes'][0]['attempts'][0]['status'],'timed_out')
        self.assertTrue((self.out/'series/0000/attempts/0000/run').is_dir())
    def test_cli(self):
        def cli(*args):return subprocess.run([sys.executable,'-B',a.__file__,*map(str,args)],capture_output=True,text=True)
        r=cli('build','--tree',self.tree,'--tree-sha256',self.th,'--node','base','--series',self.series,'--series-sha256',self.sha,'--output',self.out);self.assertEqual(r.returncode,0,r.stderr+r.stdout)
        self.assertEqual(cli('verify','--bundle',self.out,'--sha256',json.loads(r.stdout)['manifest_sha256']).returncode,0)

if __name__=='__main__':unittest.main()
