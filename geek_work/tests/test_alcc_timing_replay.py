import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_alcc_timing_replay as a

class TimingReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.pilot=self.root/'pilot';self.out=self.root/'bundle'
        cases,inputs=a.corpus.corpus();fixed=json.loads((a.STUDY/'RESULTS.json').read_bytes())
        build=dict(commands=[['lean','a','b'],['cc','a','b'],['cc','-o','/old/native']],lean_path=['/old/lib'],new_proofs=False,**{k:fixed[k] for k in ('binary_sha256','source_sha256','import_source_sha')})
        frozen=dict(build=build,contract_sha256=a.m.sha((a.STUDY/'CONTRACT.md').read_bytes()),bootstrap=a.driver.BOOTSTRAP,inputs={n:a.m.sha(v) for n,v in inputs.items()},rounds=3)
        self.files={'inputs/'+n:v for n,v in inputs.items()};self.files['frozen.json']=a.m.encoded(frozen);rows=[]
        mapping={'residual_zero':0,'residual_nonzero':2,'PROBLEM_MISMATCH':3,'INVALID_FORMAT':3}
        for r,c in a.order():
            name=c['id'];code=mapping[c['expected']['status']]
            native=dict(schema='alcc-native-timing-1',evidence_kind='compiled_execution',code=code,read_ns=10,verify_ns=20)
            rows.append(dict(case=name,round=r,native=native,command=['/old/python','-I','-B','-c',a.driver.BOOTSTRAP,'/old/native','/old/inputs/'+name+'.passport.json','/old/inputs/'+name+'.certificate.json'],process=dict(outcome='exited',returncode=code,wall_time_ms=1,error=None,stdout_truncated=False,stderr_truncated=False)))
            self.files[f'{r}-{name}-stdout.bin']=a.m.encoded(native);self.files[f'{r}-{name}-stderr.bin']=b''
        self.files['observations.json']=a.m.encoded(rows)
    def pack(self):
        a.archive.write_tree(self.pilot,self.files)
        return a.pack(self.pilot,a.m.sha(self.files['frozen.json']),a.m.sha(self.files['observations.json']),self.out)
    def edit_rows(self,fn):
        rows=json.loads(self.files['observations.json']);fn(rows);self.files['observations.json']=a.m.encoded(rows)
    def test_summary_and_offline_relocation(self):
        r=self.pack();shutil.rmtree(self.pilot);moved=self.root/'moved';self.out.rename(moved)
        with patch.object(subprocess,'Popen',side_effect=AssertionError('no execution')):
            self.assertEqual(a.verify(moved,r['manifest_sha256'])['observations'],36)
        report=json.loads((moved/'report.json').read_bytes());self.assertEqual(report['cases'][0]['medians']['verify_ns'],dict(numerator=40,denominator=2))
    def test_missing_or_reordered_rows(self):
        for edit in (lambda r:r.pop(),lambda r:r.reverse()):
            old=self.files['observations.json'];self.edit_rows(edit)
            with self.assertRaises(ValueError):a.derive(self.files)
            self.files['observations.json']=old
    def test_observation_log_disagreement(self):
        self.edit_rows(lambda r:r[0]['native'].update(verify_ns=21))
        with self.assertRaises(ValueError):a.derive(self.files)
    def test_process_and_command_corruption(self):
        for edit in (lambda r:r[0]['process'].update(returncode=False),lambda r:r[0]['process'].update(stdout_truncated=True),lambda r:r[0]['process'].update(wall_time_ms=-1),lambda r:r[0]['command'].__setitem__(5,'/other/native')):
            old=self.files['observations.json'];self.edit_rows(edit)
            with self.assertRaises(ValueError):a.derive(self.files)
            self.files['observations.json']=old
    def test_input_and_stderr_rejected(self):
        self.files['inputs/empty.passport.json']+=b' '
        with self.assertRaises(ValueError):a.derive(self.files)
    def test_unexpected_stderr(self):
        self.files["0-empty-stderr.bin"]=b"unexpected"
        with self.assertRaises(ValueError):a.derive(self.files)
    def test_wrong_anchor_and_preserve_existing_output(self):
        r=self.pack()
        with self.assertRaises(ValueError):a.verify(self.out,'0'*64)
        with self.assertRaises(FileExistsError):a.pack(self.pilot,a.m.sha(self.files['frozen.json']),a.m.sha(self.files['observations.json']),self.out)
    def test_extra_file_and_symlink(self):
        r=self.pack();extra=self.out/'extra';extra.write_bytes(b'x')
        with self.assertRaises(ValueError):a.verify(self.out,r['manifest_sha256'])
        extra.unlink();f=self.out/'report.json';data=f.read_bytes();f.unlink();other=self.root/'other';other.write_bytes(data);f.symlink_to(other)
        with self.assertRaises(ValueError):a.verify(self.out,r['manifest_sha256'])
    def test_resealed_summary_promotion(self):
        self.pack();f=self.out/'report.json';report=json.loads(f.read_bytes());report['performance_qualified']=True;f.write_bytes(a.m.encoded(report))
        files=a.load(self.out,('selection.json','report.json','manifest.json'));files.pop('manifest.json');meta=a.manifest(files);(self.out/'manifest.json').write_bytes(meta)
        with self.assertRaises(ValueError):a.verify(self.out,a.m.sha(meta))
    def test_total_read_limit(self):
        self.pack()
        with patch.object(a,'MAX_TOTAL',100),self.assertRaises(ValueError):a.load(self.pilot)

if __name__=='__main__':unittest.main()
