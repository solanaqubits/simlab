import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_context_coverage as c


class ContextCoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.source=self.root/'doc.md';self.text='# Parent\r\nУсловие 😀.\r\n## Child\r\nОтвет.\r\n# Other\r\nУсловие 😀.\r\n';self.source.write_bytes(self.text.encode())
        self.index=self.root/'index';self.out=self.root/'eval';self.anchor=c.index.build(self.source,c.m.sha(self.source.read_bytes()),self.index)['manifest_sha256']
        def ref(i,role,q):
            a=self.text.index(q);return dict(id=i,role=role,start=a,end=a+len(q),quote=q)
        self.spec=dict(schema='geek-work-context-coverage-corpus-1',index_sha256=self.anchor,annotation=dict(author='fixture',note='Synthetic author annotations',independence_verified=False,accepted_as_gold=False),variants=[dict(id='full',description='Full document'),dict(id='child',description='Child only'),dict(id='tiny',description='Refusal control')],cases=[dict(id='q1',question='What answer under what premise?',required=[ref('answer','answer','Ответ.'),ref('premise','premise','Условие 😀.'),ref('heading','limit','# Parent\r\n')],selections={key:dict(node_ids=nodes,max_context_bytes=budget) for key,nodes,budget in [('full',['document'],100000),('child',['section-0002'],100000),('tiny',['document'],1)]})])
    def build(self):
        p=self.root/'corpus.json';p.write_bytes(c.m.encoded(self.spec));return c.build(self.index,self.anchor,p,c.m.sha(p.read_bytes()),self.out)
    def report(self):return json.loads((self.out/'report.json').read_bytes())
    def reseal(self):
        files={str(p.relative_to(self.out)):p.read_bytes() for p in self.out.rglob('*') if p.is_file() and p!=self.out/'manifest.json'}
        raw=c.manifest(files);(self.out/'manifest.json').write_bytes(raw);return c.m.sha(raw)
    def test_parent_premise_omission_and_visible_ancestor_heading(self):
        self.build();rows=self.report()['rows'];self.assertTrue(rows[0]['all_required_covered'])
        self.assertEqual([r['status'] for r in rows[1]['requirements']],['covered','missing','covered'])
        self.assertFalse(rows[1]['all_required_covered']);self.assertEqual(rows[1]['covered_count'],2)
    def test_budget_refusal_has_null_measurements_and_separate_denominator(self):
        self.build();row=self.report()['rows'][2]
        self.assertEqual(row['status'],'budget_rejected');self.assertIsNone(row['context_bytes']);self.assertIsNone(row['covered_count']);self.assertIsNone(row['all_required_covered'])
        summary=self.report()['summary'][2];self.assertEqual(summary['completed'],0);self.assertEqual(summary['budget_rejected'],1);self.assertIsNone(summary['serialized_context_bytes_on_completed'])
        self.assertFalse((self.out/'selections/q1/tiny').exists())
    def test_exact_serialized_native_payload_size(self):
        self.build();r=self.report()['rows'][1];raw=(self.out/'selections/q1/child/context.json').read_bytes()
        self.assertEqual(len(raw),r['context_bytes']);self.assertEqual(c.m.sha(raw),r['context_sha256'])
    def test_same_quote_elsewhere_does_not_cover_anchor(self):
        self.spec['cases'][0]['selections']['child']['node_ids']=['section-0003'];self.build()
        self.assertEqual(self.report()['rows'][1]['requirements'][1]['status'],'missing')
    def test_union_handles_overlap_adjacency_and_gap(self):
        r=dict(id='r',role='premise',start=2,end=12)
        self.assertEqual(c.coverage(r,[(0,5),(3,7),(7,10)])['covered_codepoints'],8)
        self.assertEqual(c.coverage(r,[(0,7),(8,20)])['status'],'partial')
        self.assertEqual(c.coverage(r,[(0,7),(7,20)])['status'],'covered')
    def test_partial_requirement_crossing_parent_child_boundary(self):
        start=self.text.index('Условие');end=self.text.index('Ответ.')+len('Ответ.')
        self.spec['cases'][0]['required']=[dict(id='cross',role='premise',start=start,end=end,quote=self.text[start:end])]
        self.build();self.assertEqual(self.report()['rows'][1]['requirements'][0]['status'],'partial')
    def test_annotations_and_success_do_not_promote_semantics(self):
        self.build();r=self.report()
        for key in ('semantic_completeness_verified','answer_quality_evaluated','automatic_retrieval_evaluated','annotation_completeness_verified','independence_verified','accepted_as_gold'):self.assertIs(r[key],False)
        self.assertIsNone(r['token_usage']);self.assertIsNone(r['monetary_cost'])
    def test_no_requirements_or_duplicate_intervals_rejected(self):
        saved=copy.deepcopy(self.spec['cases'][0]['required'])
        for refs in [[],saved+[dict(**{**saved[0],'id':'other'})]]:
            self.spec['cases'][0]['required']=refs
            with self.assertRaises(ValueError):self.build()
            self.assertFalse(self.out.exists())
    def test_invalid_or_missing_selection_is_not_budget_refusal(self):
        original=copy.deepcopy(self.spec)
        for selection in [dict(node_ids=['unknown'],max_context_bytes=100),dict(node_ids=['document'],max_context_bytes=True)]:
            self.spec=copy.deepcopy(original);self.spec['cases'][0]['selections']['child']=selection
            with self.assertRaises(ValueError):self.build()
        self.spec=original;del self.spec['cases'][0]['selections']['child']
        with self.assertRaises(ValueError):self.build()
    def test_wrong_quote_bool_offsets_and_gold_promotion_rejected(self):
        original=copy.deepcopy(self.spec)
        for key,value in [('quote','fake'),('start',True)]:
            self.spec=copy.deepcopy(original);self.spec['cases'][0]['required'][0][key]=value
            with self.assertRaises(ValueError):self.build()
        self.spec=original;self.spec['annotation']['accepted_as_gold']=True
        with self.assertRaises(ValueError):self.build()
    def test_corpus_index_binding_required(self):
        self.spec['index_sha256']='0'*64
        with self.assertRaises(ValueError):self.build()
    def test_relocation_without_original_or_network(self):
        result=self.build();moved=self.root/'moved';shutil.move(self.out,moved);shutil.rmtree(self.index);self.source.unlink()
        with patch.object(subprocess,'run',side_effect=AssertionError('offline')):c.verify(moved,result['manifest_sha256'])
    def test_resealed_report_and_context_tampering_rejected(self):
        for name in ['report.json','selections/q1/child/context.json']:
            self.build();p=self.out/name;p.write_bytes(p.read_bytes()+b' ')
            with self.assertRaises(ValueError):c.verify(self.out,self.reseal())
            shutil.rmtree(self.out)
    def test_extra_file_symlink_and_existing_output(self):
        r=self.build()
        with self.assertRaises(FileExistsError):self.build()
        (self.out/'extra').write_bytes(b'x')
        with self.assertRaises(ValueError):c.verify(self.out,self.reseal())
        (self.out/'extra').unlink();p=self.out/'corpus.json';p.unlink();p.symlink_to(self.root/'corpus.json')
        with self.assertRaises(ValueError):c.verify(self.out,r['manifest_sha256'])
    def test_archive_limit_applies_to_build_and_verify(self):
        r=self.build()
        with patch.object(c,'MAX_TOTAL',1),self.assertRaises(ValueError):c.verify(self.out,r['manifest_sha256'])
        shutil.rmtree(self.out)
        with patch.object(c,'MAX_TOTAL',1),self.assertRaises(ValueError):self.build()
        self.assertFalse(self.out.exists())
    def test_cli_build_and_replay(self):
        path=self.root/'corpus.json';path.write_bytes(c.m.encoded(self.spec))
        def cli(*args):return subprocess.run([sys.executable,'-B',c.__file__,*map(str,args)],capture_output=True,text=True)
        r=cli('build','--bundle',self.index,'--sha256',self.anchor,'--corpus',path,'--corpus-sha256',c.m.sha(path.read_bytes()),'--output',self.out)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);anchor=json.loads(r.stdout)['manifest_sha256']
        self.assertEqual(cli('verify','--bundle',self.out,'--sha256',anchor).returncode,0)
        self.assertEqual(cli('verify','--bundle',self.out,'--sha256','0'*64).returncode,2)


if __name__=='__main__':unittest.main()
