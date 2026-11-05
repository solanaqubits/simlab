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
import geek_work_file_operations as c


class FileOperationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.base=self.root/'base';self.candidate=self.root/'candidate';self.bundle=self.root/'proposal';self.out=self.root/'decision'
        self.left={'old.md':b'Old text\r\n','refs.bib':b'References\n','figure.bin':b'\x00old','scope.md':b'Guard'}
        self.right={'new.tex':b'New text\r\n','sources/refs.bib':b'References\n','figure.bin':b'\xffnew','scope.md':b'Guard'}
        for root,files in [(self.base,self.left),(self.candidate,self.right)]:
            root.mkdir()
            for name,raw in files.items():p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        self.rows=[dict(id='new',op='create',kind='text',source=None,target='new.tex'),dict(id='old',op='delete',kind='text',source='old.md',target=None),dict(id='move',op='rename',kind='text',source='refs.bib',target='sources/refs.bib'),dict(id='image',op='replace',kind='binary',source='figure.bin',target='figure.bin'),dict(id='scope',op='guard',kind='text',source='scope.md',target='scope.md')]
        self.ops=self.root/'operations.json';self.prepare()
        self.selection=dict(schema='geek-work-file-operation-selection-1',proposal_sha256=self.anchor,reviewer='synthetic reviewer',decisions=[dict(operation_id=r['id'],decision='confirm' if r['op']=='guard' else 'accept',reason='fixture choice') for r in self.rows])
        self.decisions=self.root/'selection.json'

    def prepare(self,path=None):
        raw=c.m.encoded(dict(schema='geek-work-file-operations-1',operations=self.rows));self.ops.write_bytes(raw)
        r=c.propose(self.base,self.candidate,self.ops,c.m.sha(raw),'test author','test reason',path or self.bundle)
        self.anchor=r['manifest_sha256'];return r

    def decide(self):
        raw=c.m.encoded(self.selection);self.decisions.write_bytes(raw)
        return c.decide(self.bundle,self.anchor,self.base,self.decisions,c.m.sha(raw),self.out)

    def reseal(self,root):
        p=root/'manifest.json';spec=json.loads(p.read_bytes());spec['files']={n:c.m.sha((root/n).read_bytes()) for n in spec['files']};raw=c.m.encoded(spec);p.write_bytes(raw);return c.m.sha(raw)

    def test_all_accept_projects_bytes_and_removal_intents(self):
        r=self.decide();checked=c.verify_decision(self.out,r['manifest_sha256'])
        self.assertEqual((checked['staged_files'],checked['removal_intents']),(4,2))
        for name,raw in self.right.items():self.assertEqual((self.out/'result'/name).read_bytes(),raw)
        self.assertEqual({x['path'] for x in r['removals']},{'old.md','refs.bib'})
        for name,raw in self.left.items():self.assertEqual((self.base/name).read_bytes(),raw)
        self.assertFalse(r['binary_content_validated']);self.assertFalse(r['live_project_modified'])

    def test_all_reject_retains_selected_baseline(self):
        for d in self.selection['decisions']:
            if d['decision']=='accept':d['decision']='reject'
        r=self.decide();self.assertEqual(r['removals'],[])
        for name,raw in self.left.items():self.assertEqual((self.out/'result'/name).read_bytes(),raw)
        self.assertFalse((self.out/'result/new.tex').exists());c.verify_decision(self.out,r['manifest_sha256'])

    def test_mixed_choices_and_normalized_order(self):
        self.selection['decisions'][1]['decision']='reject';self.selection['decisions'].reverse();r=self.decide()
        self.assertEqual([x['operation']['id'] for x in r['operations']],[x['id'] for x in self.rows])
        self.assertEqual([x['path'] for x in r['removals']],['refs.bib']);self.assertEqual((self.out/'result/old.md').read_bytes(),self.left['old.md'])

    def test_stale_existing_and_required_absent_paths(self):
        for name,raw in [('scope.md',b'drift'),('new.tex',b''),('sources/refs.bib',b'occupied')]:
            p=self.base/name;old=p.read_bytes() if p.exists() else None;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'STALE_BASE_REJECTED'):self.decide()
            self.assertFalse(self.out.exists())
            if old is None:p.unlink()
            else:p.write_bytes(old)

    def test_candidate_and_baseline_operation_constraints(self):
        edits=[(self.candidate/'refs.bib',b'not removed'),(self.candidate/'sources/refs.bib',b'changed rename'),(self.candidate/'old.md',b'not deleted'),(self.base/'new.tex',b'occupied')]
        for p,raw in edits:
            old=p.read_bytes() if p.exists() else None;p.write_bytes(raw)
            with self.assertRaises(ValueError):self.prepare(self.root/'invalid')
            self.assertFalse((self.root/'invalid').exists())
            if old is None:p.unlink()
            else:p.write_bytes(old)

    def test_path_collisions_chains_swaps_and_prefixes(self):
        original=copy.deepcopy(self.rows)
        variants=[]
        x=copy.deepcopy(original);x[0]['target']='REFS.bib';variants.append(x)
        x=copy.deepcopy(original);x[0]['target']='refs.bib/child.tex';variants.append(x)
        x=copy.deepcopy(original);x[0]['target']='sources/refs.bib';variants.append(x)
        x=copy.deepcopy(original);x[2]['target']='refs.bib';variants.append(x)
        for rows in variants:
            with self.assertRaises(ValueError):c.operations(c.m.encoded(dict(schema='geek-work-file-operations-1',operations=rows)))

    def test_empty_is_present_and_not_absent(self):
        self.assertIsNone(c.observe(self.base,'missing.tex','text'))
        (self.base/'empty.tex').write_bytes(b'');self.assertEqual(c.observe(self.base,'empty.tex','text'),b'')
        row=dict(op='create',source=None,target='empty.tex',kind='text');self.assertEqual(c.states(row,None,b''),({'empty.tex':None},{'empty.tex':b''}))
        with self.assertRaises(ValueError):c.states(row,b'',b'')

    def test_missing_duplicate_unknown_and_guard_decisions(self):
        original=copy.deepcopy(self.selection)
        edits=[lambda x:x['decisions'].pop(),lambda x:x['decisions'].append(x['decisions'][0]),lambda x:x['decisions'][0].update(operation_id='unknown'),lambda x:x['decisions'][0].update(decision=None),lambda x:x['decisions'][-1].update(decision='accept')]
        for edit in edits:
            self.selection=copy.deepcopy(original);edit(self.selection)
            with self.assertRaises(ValueError):self.decide()
            self.assertFalse(self.out.exists())

    def test_anchor_and_incomplete_template(self):
        with self.assertRaisesRegex(ValueError,'anchor'):c.verified(self.bundle,'0'*64)
        raw=c.m.encoded(self.selection);self.decisions.write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'selection SHA'):c.decide(self.bundle,self.anchor,self.base,self.decisions,'0'*64,self.out)
        self.selection=json.loads((self.bundle/'decisions.template.json').read_bytes())
        with self.assertRaises(ValueError):self.decide()

    def test_proposal_tampering_and_resealed_preview(self):
        p=self.bundle/'0000-after.bin';original=p.read_bytes();p.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):c.verified(self.bundle,self.anchor)
        p.write_bytes(original);p=self.bundle/'review.html';p.write_bytes(p.read_bytes()+b' ');anchor=self.reseal(self.bundle)
        with self.assertRaisesRegex(ValueError,'reproduction'):c.verified(self.bundle,anchor)

    def test_resealed_result_removals_and_receipt(self):
        r=self.decide()
        for name,new in [('result/figure.bin',b'bad bytes'),('removals.json',b'[]\n'),('receipt.json',b'{}\n')]:
            p=self.out/name;old=p.read_bytes();p.write_bytes(new);anchor=self.reseal(self.out)
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'reproduction'):c.verify_decision(self.out,anchor)
            p.write_bytes(old)

    def test_relocation_without_old_roots_or_execution(self):
        r=self.decide();moved=self.root/'moved';shutil.move(self.out,moved)
        for p in (self.base,self.candidate,self.bundle):shutil.rmtree(p)
        with patch('subprocess.run',side_effect=AssertionError('no execution')):result=c.verify_decision(moved,r['manifest_sha256'])
        self.assertFalse(result['historical_baseline_check_verified']);self.assertFalse(result['live_project_checked'])
        cli=json.loads(subprocess.check_output([sys.executable,c.__file__,'verify-decision','--bundle',str(moved),'--sha256',r['manifest_sha256']],env={**os.environ,'PATH':''}));self.assertEqual(cli,result)

    def test_absence_never_follows_symlink_or_missing_root(self):
        (self.base/'dangling.tex').symlink_to(self.root/'missing')
        with self.assertRaises(ValueError):c.observe(self.base,'dangling.tex','text')
        (self.base/'linked').symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):c.observe(self.base,'linked/absent.tex','text')
        with self.assertRaises(ValueError):c.observe(self.root/'missing-root','absent.tex','text')
        (self.base/'folder.tex').mkdir()
        with self.assertRaises(ValueError):c.observe(self.base,'folder.tex','text')

    def test_special_and_extra_output_files(self):
        r=self.decide();(self.out/'extra').mkdir()
        with self.assertRaises(ValueError):c.verify_decision(self.out,r['manifest_sha256'])
        (self.out/'extra').rmdir();p=self.out/'result/figure.bin';p.unlink();os.mkfifo(p)
        with self.assertRaises(ValueError):c.verify_decision(self.out,r['manifest_sha256'])

    def test_binary_is_opaque_and_text_is_validated(self):
        with self.assertRaises(ValueError):c.content(b'\xff','text')
        with self.assertRaises(ValueError):c.content(b'\x00','text')
        self.assertEqual(c.content(b'\xff\x00','binary'),b'\xff\x00')
        raw=c.m.encoded(dict(schema='geek-work-file-operations-1',operations=[self.rows[3]]));data=c.artifacts(raw,[self.rows[3]],[(b'<script>OLD</script>',b'<script>NEW</script>')],'<author>','reason')
        self.assertNotIn(b'OLD',data['review.html']);self.assertNotIn(b'<script>',data['review.html']);self.assertIn(b'&lt;author&gt;',data['review.html'])

    def test_limits_and_exclusive_output(self):
        with patch.object(c,'MAX_SNAPSHOTS',1),self.assertRaisesRegex(ValueError,'snapshot byte'):self.prepare(self.root/'limited')
        self.assertFalse((self.root/'limited').exists())
        with patch.object(c,'MAX_FILE',1),self.assertRaises(ValueError):c.observe(self.base,'figure.bin','binary')
        self.decide()
        with self.assertRaises(FileExistsError):self.decide()

    def test_invalid_operations_schema_paths_and_noops(self):
        for rows in [[self.rows[-1]],[{**self.rows[0],'target':'../escape'}],[{**self.rows[0],'target':'.git/config'}],[{**self.rows[0],'source':'wrong'}],[{**self.rows[3],'target':'different.bin'}],[{**self.rows[0],'op':'shell'}]]:
            with self.assertRaises(ValueError):c.operations(c.m.encoded(dict(schema='geek-work-file-operations-1',operations=rows)))
        with self.assertRaises(ValueError):c.states(self.rows[3],b'same',b'same')

    def test_output_cannot_modify_input_roots(self):
        with self.assertRaisesRegex(ValueError,'disjoint'):self.prepare(self.base/'staged')
        with self.assertRaisesRegex(ValueError,'disjoint'):self.prepare(self.candidate/'staged')
        for root in (self.base,self.bundle):
            self.out=root/'staged'
            with self.assertRaisesRegex(ValueError,'disjoint'):self.decide()
            self.assertFalse(self.out.exists())

    def test_delete_only_and_rejected_create_need_no_result_directory(self):
        for row,pairs,decision,removals in [(self.rows[1],[(b'',None)],'accept',1),(self.rows[0],[(None,b'')],'reject',0)]:
            raw=c.m.encoded(dict(schema='geek-work-file-operation-selection-1',proposal_sha256='a'*64,reviewer='x',decisions=[dict(operation_id=row['id'],decision=decision,reason='x')]))
            payload,receipt=c.projection([row],pairs,'a'*64,raw)
            self.assertFalse(any(n.startswith('result/') for n in payload));self.assertEqual(len(receipt['removals']),removals)


if __name__=='__main__':unittest.main()
