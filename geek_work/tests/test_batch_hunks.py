import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_batch_hunks as c


class BatchHunksTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.base=self.root/'base';self.candidate=self.root/'candidate';self.batch=self.root/'batch';self.plan=self.root/'plan';self.out=self.root/'decision'
        self.left={'paper/main.tex':b'Title old\r\ncontext\r\nAssumption P\r\n','paper/refs.bib':b'old reference\n','notes/scope.md':b'Unchanged guard\n'}
        self.right={**self.left,'paper/main.tex':b'Title new\r\ncontext\r\nNo assumption\r\n','paper/refs.bib':b'new reference\n'}
        for root,files in [(self.base,self.left),(self.candidate,self.right)]:
            for name,raw in files.items():p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        r=c.b.propose(self.base,self.candidate,list(self.left),'synthetic author','test',self.batch);self.batch_anchor=r['manifest_sha256']
        p=c.prepare(self.batch,self.batch_anchor,self.plan);self.anchor=p['manifest_sha256']
        self.selection=json.loads((self.plan/'decisions.template.json').read_bytes());self.selection.update(plan_sha256=self.anchor,reviewer='synthetic reviewer')
        for row in self.selection['files']:
            for i,d in enumerate(row['decisions']):d.update(decision='accept' if i==0 else 'reject',reason='test choice')
        self.decisions=self.root/'selection.json'

    def decide(self):
        raw=c.m.encoded(self.selection);self.decisions.write_bytes(raw)
        return c.decide(self.plan,self.anchor,self.base,self.decisions,c.m.sha(raw),self.out)

    def reseal(self,root):
        p=root/'manifest.json';x=json.loads(p.read_bytes());x['files']={n:c.m.sha((root/n).read_bytes()) for n in x['files']};raw=c.m.encoded(x);p.write_bytes(raw);return c.m.sha(raw)

    def test_mixed_three_file_decision_and_guard(self):
        r=self.decide();checked=c.verify_decision(self.out,r['manifest_sha256'])
        self.assertEqual((checked['accepted'],checked['rejected'],checked['unchanged_guards']),(2,1,1))
        self.assertEqual((self.out/'result/paper/main.tex').read_bytes(),b'Title new\r\ncontext\r\nAssumption P\r\n')
        self.assertEqual((self.out/'result/paper/refs.bib').read_bytes(),self.right['paper/refs.bib'])
        self.assertEqual((self.out/'result/notes/scope.md').read_bytes(),self.left['notes/scope.md'])
        for name,raw in self.left.items():self.assertEqual((self.base/name).read_bytes(),raw)
        self.assertFalse(r['reference_consistency_checked']);self.assertFalse(r['compilation_checked'])

    def test_all_accept_and_reject_selected_subset(self):
        (self.base/'private.md').write_text('unselected')
        for choice,expected in [('accept',self.right),('reject',self.left)]:
            for row in self.selection['files']:
                for d in row['decisions']:d['decision']=choice
            r=self.decide()
            for name,raw in expected.items():self.assertEqual((self.out/'result'/name).read_bytes(),raw)
            self.assertFalse((self.out/'result/private.md').exists());c.verify_decision(self.out,r['manifest_sha256']);shutil.rmtree(self.out)

    def test_stale_changed_file_and_unchanged_guard(self):
        for name in ('paper/main.tex','notes/scope.md'):
            p=self.base/name;p.write_bytes(self.left[name]+b'drift')
            with self.assertRaisesRegex(ValueError,'STALE_BASE_REJECTED'):self.decide()
            self.assertFalse(self.out.exists());p.write_bytes(self.left[name])

    def test_missing_duplicate_unknown_file_rows(self):
        original=copy.deepcopy(self.selection)
        edits=[lambda x:x['files'].pop(),lambda x:x['files'].append(x['files'][0]),lambda x:x['files'][0].update(document='unknown.md')]
        for edit in edits:
            self.selection=copy.deepcopy(original);edit(self.selection)
            with self.assertRaises(ValueError):self.decide()
            self.assertFalse(self.out.exists())

    def test_hunk_ids_are_scoped_and_guards_cannot_change(self):
        original=copy.deepcopy(self.selection)
        edits=[lambda x:x['files'][0]['decisions'].append(dict(hunk_id='h001',decision='accept',reason='x')),lambda x:x['files'][1]['decisions'].pop(),lambda x:x['files'][1]['decisions'].append(x['files'][1]['decisions'][0]),lambda x:x['files'][1]['decisions'][0].update(decision=None)]
        for edit in edits:
            self.selection=copy.deepcopy(original);edit(self.selection)
            with self.assertRaises(ValueError):self.decide()
        self.selection=original;r=self.decide();self.assertEqual(sum(x['accepted'] for x in r['files']),2)

    def test_order_normalization(self):
        self.selection['files'].reverse()
        for row in self.selection['files']:row['decisions'].reverse()
        r=self.decide();self.assertEqual([x['document'] for x in r['files']],sorted(self.left));c.verify_decision(self.out,r['manifest_sha256'])

    def test_anchors_and_incomplete_template(self):
        raw=c.m.encoded(self.selection);self.decisions.write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'selection SHA'):c.decide(self.plan,self.anchor,self.base,self.decisions,'0'*64,self.out)
        with self.assertRaisesRegex(ValueError,'plan anchor'):c.verified_plan(self.plan,'0'*64)
        self.selection['plan_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'selection/plan'):self.decide()
        self.selection=json.loads((self.plan/'decisions.template.json').read_bytes())
        with self.assertRaises(ValueError):self.decide()

    def test_resealed_plan_artifact_and_nested_batch_tampering(self):
        p=self.plan/'hunks.json';old=p.read_bytes();p.write_bytes(old+b' ');anchor=self.reseal(self.plan)
        with self.assertRaisesRegex(ValueError,'reproduction'):c.verified_plan(self.plan,anchor)
        p.write_bytes(old);anchor=self.reseal(self.plan);(self.plan/'batch/files/0000/before.txt').write_bytes(b'drift')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):c.verified_plan(self.plan,anchor)

    def test_resealed_result_and_receipt(self):
        r=self.decide();p=self.out/'result/notes/scope.md';old=p.read_bytes();p.write_bytes(b'changed guard');anchor=self.reseal(self.out)
        with self.assertRaisesRegex(ValueError,'reproduction'):c.verify_decision(self.out,anchor)
        p.write_bytes(old);p=self.out/'receipt.json';x=json.loads(p.read_bytes());x['reference_consistency_checked']=True;p.write_bytes(c.m.encoded(x));anchor=self.reseal(self.out)
        with self.assertRaisesRegex(ValueError,'reproduction'):c.verify_decision(self.out,anchor)

    def test_relocation_without_live_inputs_or_process(self):
        r=self.decide();moved=self.root/'moved';shutil.move(self.out,moved)
        for p in (self.base,self.candidate,self.plan,self.batch):shutil.rmtree(p)
        with patch('subprocess.run',side_effect=AssertionError('no execution')):checked=c.verify_decision(moved,r['manifest_sha256'])
        self.assertFalse(checked['live_document_checked']);self.assertFalse(checked['historical_baseline_check_verified'])
        observed=json.loads(subprocess.check_output([sys.executable,c.__file__,'verify-decision','--bundle',str(moved),'--sha256',r['manifest_sha256']],env={**os.environ,'PATH':''}));self.assertEqual(observed,checked)

    def test_result_extra_empty_directory_symlink_and_fifo(self):
        r=self.decide();(self.out/'result/extra').mkdir()
        with self.assertRaises(ValueError):c.verify_decision(self.out,r['manifest_sha256'])
        (self.out/'result/extra').rmdir();p=self.out/'result/notes/scope.md';p.unlink();p.symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):c.verify_decision(self.out,r['manifest_sha256'])
        p.unlink();os.mkfifo(p)
        with self.assertRaises(ValueError):c.verify_decision(self.out,r['manifest_sha256'])

    def test_current_parent_symlink_rejected_before_output(self):
        original=self.base/'paper';moved=self.root/'external';shutil.move(original,moved);original.symlink_to(moved,target_is_directory=True)
        with self.assertRaises(ValueError):self.decide()
        self.assertFalse(self.out.exists())

    def test_limits_and_existing_output(self):
        with patch.object(c,'MAX_HUNKS',1),self.assertRaisesRegex(ValueError,'hunk count'):c.prepare(self.batch,self.batch_anchor,self.root/'too-many')
        with patch.object(c.m,'MAX_ARTIFACT',1),self.assertRaises(ValueError):c.verified_plan(self.plan,self.anchor)
        self.decide()
        with self.assertRaises(FileExistsError):self.decide()

    def test_batch_directory_symlink_and_html_escaping(self):
        linked=self.root/'linked';linked.symlink_to(self.batch,target_is_directory=True)
        with self.assertRaises(ValueError):c.prepare(linked,self.batch_anchor,self.root/'bad')
        spec,data,_=c.batch_bytes(self.batch,self.batch_anchor)
        data[1]['after.txt']=b'<script>alert(1)</script>\n';files,_=c.plan_artifacts(spec,data)
        self.assertNotIn(b'<script>',files['review.html']);self.assertIn(b'&lt;script&gt;',files['review.html'])


if __name__=='__main__':unittest.main()
