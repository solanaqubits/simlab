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
import geek_work_manuscript_hunks as h


class HunkReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.base=self.root/'base.tex';self.candidate=self.root/'candidate.tex'
        self.before=b'Title old\r\nunchanged\r\nClaim bounded\r\n';self.after=b'Title new\r\nunchanged\r\nClaim universal\r\n'
        self.base.write_bytes(self.before);self.candidate.write_bytes(self.after);self.bundle=self.root/'proposal';self.out=self.root/'decision'
        r=h.propose(self.base,self.candidate,'paper/main.tex','test author','synthetic changes',self.bundle);self.anchor=r['manifest_sha256']
        self.spec,self.data,self.rows,_=h.verified(self.bundle,self.anchor)
        self.choices=dict(schema='geek-work-hunk-selection-1',proposal_sha256=self.anchor,reviewer='test reviewer',decisions=[dict(hunk_id=r['id'],decision='accept' if i==0 else 'reject',reason='synthetic rationale') for i,r in enumerate(self.rows)])
        self.selection=self.root/'selection.json'

    def decide(self):
        raw=h.m.encoded(self.choices);self.selection.write_bytes(raw)
        return h.decide(self.bundle,self.anchor,self.base,self.selection,h.m.sha(raw),self.out)

    def reseal_proposal(self):
        x=h.m.load((self.bundle/'manifest.json').read_bytes())
        x['files']={n:h.m.sha((self.bundle/n).read_bytes()) for n in h.FILES};raw=h.m.encoded(x)
        (self.bundle/'manifest.json').write_bytes(raw);self.anchor=h.m.sha(raw)

    def reseal_decision(self):
        p=self.out/'manifest.json';x=json.loads(p.read_bytes());x['files']={n:h.m.sha((self.out/n).read_bytes()) for n in x['files']};raw=h.m.encoded(x);p.write_bytes(raw);return h.m.sha(raw)

    def test_mixed_selection_preserves_bytes_and_originals(self):
        r=self.decide();self.assertEqual((r['accepted'],r['rejected']),(1,1))
        self.assertEqual((self.out/'result.tex').read_bytes(),b'Title new\r\nunchanged\r\nClaim bounded\r\n')
        self.assertEqual(self.base.read_bytes(),self.before);self.assertEqual(self.candidate.read_bytes(),self.after)
        self.assertFalse(r['scientific_verification']);self.assertFalse(r['compilation_checked'])
        self.assertEqual(h.verify_decision(self.out,r['manifest_sha256'])['status'],'hunk_decision_consistent')

    def test_all_accept_and_all_reject(self):
        for decision,expected in [('accept',self.after),('reject',self.before)]:
            for row in self.choices['decisions']:row['decision']=decision
            r=self.decide();self.assertEqual((self.out/'result.tex').read_bytes(),expected)
            self.assertEqual(h.verify_decision(self.out,r['manifest_sha256'])['result_sha256'],h.m.sha(expected));shutil.rmtree(self.out)

    def test_insert_delete_unicode_and_final_newline(self):
        cases=[(b'',b'new'),(b'old',b''),(b'a\nb\nc\n',b'new\na\nc\nend'),('α\r\nβ'.encode(),'α\nβ\n'.encode()),(b'a\rb\n',b'a\rB\n')]
        for left,right in cases:
            rows=h.hunks(left,right)
            with self.subTest(left=left,right=right):
                self.assertEqual(h.assemble(left,rows,[{'decision':'accept'}]*len(rows)),right)
                self.assertEqual(h.assemble(left,rows,[{'decision':'reject'}]*len(rows)),left)
                for row in rows:self.assertEqual(left[row['before_start']:row['before_end']],row['before_text'].encode())

    def test_repeated_lines_deterministic(self):
        left=b'A\nx\nA\nx\n';right=b'A\ny\nA\nx\n'
        self.assertEqual(h.hunks(left,right),h.hunks(left,right))
        rows=h.hunks(left,right);self.assertEqual(h.assemble(left,rows,[{'decision':'accept'}]*len(rows)),right)

    def test_stale_base_before_output(self):
        self.base.write_bytes(self.before+b'drift')
        with self.assertRaisesRegex(ValueError,'STALE_BASE_REJECTED'):self.decide()
        self.assertFalse(self.out.exists())

    def test_missing_duplicate_unknown_null_decisions(self):
        original=copy.deepcopy(self.choices)
        edits=[lambda x:x['decisions'].pop(),lambda x:x['decisions'].append(x['decisions'][0]),lambda x:x['decisions'][0].update(hunk_id='unknown'),lambda x:x['decisions'][0].update(decision=None),lambda x:x['decisions'][0].update(decision='defer'),lambda x:x['decisions'][0].update(reason=''),lambda x:x.update(reviewer=None)]
        for edit in edits:
            self.choices=copy.deepcopy(original);edit(self.choices)
            with self.subTest(edit=edit),self.assertRaises(ValueError):self.decide()
            self.assertFalse(self.out.exists())

    def test_decision_order_normalized(self):
        self.choices['decisions'].reverse();r=self.decide()
        self.assertEqual([x['hunk_id'] for x in r['decisions']],[x['id'] for x in self.rows])

    def test_selection_and_proposal_anchors(self):
        raw=h.m.encoded(self.choices);self.selection.write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'selection SHA'):h.decide(self.bundle,self.anchor,self.base,self.selection,'0'*64,self.out)
        self.choices['proposal_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'selection/proposal'):self.decide()
        with self.assertRaisesRegex(ValueError,'anchor'):h.verified(self.bundle,'0'*64)
        self.assertFalse(self.out.exists())

    def test_resealed_hunk_and_preview_tampering(self):
        for file in ('hunks.json','hunk-review.html','decisions.template.json'):
            original=(self.bundle/file).read_bytes();(self.bundle/file).write_bytes(original+b' ');self.reseal_proposal()
            with self.assertRaisesRegex(ValueError,'reproduction'):h.verified(self.bundle,self.anchor)
            (self.bundle/file).write_bytes(original);self.reseal_proposal()

    def test_unsealed_source_and_extra_file(self):
        (self.bundle/'before.txt').write_bytes(b'drift')
        with self.assertRaisesRegex(ValueError,'hash'):h.verified(self.bundle,self.anchor)
        (self.bundle/'before.txt').write_bytes(self.before);(self.bundle/'extra').mkdir()
        with self.assertRaisesRegex(ValueError,'file set'):h.verified(self.bundle,self.anchor)

    def test_decision_reproduction_rejects_resealed_result_and_receipt(self):
        r=self.decide();original=(self.out/'result.tex').read_bytes();(self.out/'result.tex').write_bytes(self.after)
        anchor=self.reseal_decision()
        with self.assertRaisesRegex(ValueError,'reproduction'):h.verify_decision(self.out,anchor)
        (self.out/'result.tex').write_bytes(original);p=self.out/'receipt.json';x=json.loads(p.read_bytes());x['scientific_verification']=True;p.write_bytes(h.m.encoded(x));anchor=self.reseal_decision()
        with self.assertRaisesRegex(ValueError,'reproduction'):h.verify_decision(self.out,anchor)

    def test_decision_relocation_no_current_document_or_process(self):
        r=self.decide();moved=self.root/'moved';shutil.move(self.out,moved);self.base.unlink();self.candidate.unlink();shutil.rmtree(self.bundle)
        with patch('subprocess.run',side_effect=AssertionError('no execution')):
            checked=h.verify_decision(moved,r['manifest_sha256'])
        self.assertFalse(checked['historical_baseline_check_verified']);self.assertFalse(checked['live_document_checked'])
        result=json.loads(subprocess.check_output([sys.executable,h.__file__,'verify-decision','--bundle',str(moved),'--sha256',r['manifest_sha256']],env={**os.environ,'PATH':''}))
        self.assertEqual(result,checked)

    def test_limits_noop_and_oversized_mixed_result(self):
        with self.assertRaisesRegex(ValueError,'no change'):h.hunks(b'a',b'a')
        with patch.object(h,'MAX_HUNKS',1),self.assertRaisesRegex(ValueError,'hunk count'):h.hunks(self.before,self.after)
        with patch.object(h,'MAX_BUNDLE',1),self.assertRaisesRegex(ValueError,'proposal byte'):h.verified(self.bundle,self.anchor)
        rows=h.hunks(b'abcdef\nanchor\n',b'anchor\nuvwxyz\n')
        with patch.object(h.m,'MAX_SOURCE',15),self.assertRaisesRegex(ValueError,'source byte'):
            h.assemble(b'abcdef\nanchor\n',rows,[{'decision':'reject'},{'decision':'accept'}])

    def test_symlink_fifo_and_exclusive_outputs(self):
        self.decide()
        with self.assertRaises(FileExistsError):self.decide()
        p=self.bundle/'hunks.json';p.unlink();p.symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):h.verified(self.bundle,self.anchor)
        p.unlink();os.mkfifo(p)
        with self.assertRaises(ValueError):h.verified(self.bundle,self.anchor)

    def test_html_escapes_source_and_document(self):
        data,_=h.artifacts(b'old\n',b'<script>alert(1)</script>\n','paper.tex','<b>author</b>','<img>')
        for n in ('review.html','hunk-review.html'):
            self.assertNotIn(b'<script>',data[n]);self.assertIn(b'&lt;script&gt;',data[n])
        self.assertIn(b"default-src 'none'",data['hunk-review.html'])

    def test_template_is_incomplete_and_bad_json_rejected(self):
        template=(self.bundle/'decisions.template.json').read_bytes()
        with self.assertRaises(ValueError):h.selection(template,self.anchor,self.rows)
        with self.assertRaisesRegex(ValueError,'duplicate JSON'):h.selection(b'{"schema":1,"schema":2}',self.anchor,self.rows)


if __name__=='__main__':unittest.main()
