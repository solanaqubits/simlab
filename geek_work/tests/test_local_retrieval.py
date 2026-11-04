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
import geek_work_local_retrieval as r


class LocalRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.text='# Parent\r\nPremise only.\r\n## Needle\r\nAnswer 😀.\r\n# Other\r\nneedle needle needle.\r\n'
        self.source=self.root/'source.md';self.source.write_bytes(self.text.encode())
        self.idx=self.root/'index';self.out=self.root/'search';self.query=self.root/'query.json'
        self.anchor=r.index.build(self.source,r.m.sha(self.source.read_bytes()),self.idx)['manifest_sha256']
        self.spec=dict(schema='geek-work-local-retrieval-query-1',policy=r.POLICY,index_sha256=self.anchor,query='needle',top_k=2,max_context_bytes=65536)
    def build(self):
        self.query.write_bytes(r.m.encoded(self.spec));return r.build(self.idx,self.anchor,self.query,r.m.sha(self.query.read_bytes()),self.out)
    def report(self):return json.loads((self.out/'report.json').read_bytes())
    def reseal(self):
        files={str(p.relative_to(self.out)):p.read_bytes() for p in self.out.rglob('*') if p.is_file() and p!=self.out/'manifest.json'}
        meta=r.manifest(files);(self.out/'manifest.json').write_bytes(meta);return r.m.sha(meta)
    def test_terms_case_unicode_underscore_and_repetition(self):
        self.assertEqual(r.terms('И Test_TEST ёж ЁЖ 42'),{'test','ёж','42'})
        self.assertEqual(r.terms('Straße STRASSE'),{'strasse'})
        self.assertNotEqual(r.terms('условие'),r.terms('условия'))
    def test_heading_weight_and_descendants_not_boosting_parent(self):
        self.build();trace=self.report()['trace'];self.assertEqual([x['node_id'] for x in trace],['section-0002','section-0003'])
        self.assertEqual([x['score'] for x in trace],[3,1]);self.assertEqual(self.report()['selected_node_ids'],['section-0002','section-0003'])
    def test_tie_order_and_top_k(self):
        self.spec.update(query='Parent Other',top_k=1);self.build();t=self.report()['trace']
        self.assertEqual([x['decision'] for x in t],['selected','top_k_limit']);self.assertEqual(t[0]['node_id'],'section-0001')
    def test_overlapping_subtrees_skipped(self):
        self.spec['query']='Parent Needle';self.build();t=self.report()['trace']
        self.assertEqual(t[1]['decision'],'overlapping_selected_subtree');self.assertEqual(self.report()['selected_node_ids'],['section-0001','section-0003'])
    def test_native_selection_exact_payload_and_replay(self):
        result=self.build();report=self.report();payload=(self.out/'selection/context.json').read_bytes()
        self.assertEqual(report['context_bytes'],len(payload));self.assertEqual(report['context_sha256'],r.m.sha(payload))
        r.index.verify_selection(self.out/'selection',report['selection_manifest_sha256']);r.verify(self.out,result['manifest_sha256'])
    def test_no_query_terms_no_matches_and_budget_exhausted(self):
        for query,budget,status in [('и the',65536,'no_query_terms'),('unfindable',65536,'no_matches'),('needle',1,'budget_exhausted')]:
            self.spec.update(query=query,max_context_bytes=budget);result=self.build();report=self.report()
            self.assertEqual(report['status'],status);self.assertEqual(r.verify(self.out,result['manifest_sha256'])['status'],status)
            self.assertIsNone(report['context_bytes']);self.assertFalse((self.out/'selection').exists());shutil.rmtree(self.out)
    def test_skip_oversized_best_candidate_and_accept_smaller(self):
        text='# Needle\n'+('large '*1200)+'\n# Small\nneedle\n'
        outline,parent=r.index.index_files(text.encode());parent['manifest.json']=r.index.manifest(r.index.SCHEMA,parent)
        spec={**self.spec,'index_sha256':r.m.sha(parent['manifest.json']),'max_context_bytes':4000}
        files,report=r.derive(r.m.encoded(spec),outline,parent)
        self.assertEqual([x['decision'] for x in report['trace']],['budget_rejected','selected'])
        self.assertEqual(report['selected_node_ids'],['section-0002']);self.assertLessEqual(len(files['selection/context.json']),4000)
    def test_document_without_headings_and_no_synthetic_title_match(self):
        outline,parent=r.index.index_files(b'needle only\n');parent['manifest.json']=r.index.manifest(r.index.SCHEMA,parent)
        spec={**self.spec,'index_sha256':r.m.sha(parent['manifest.json'])}
        self.assertEqual(r.derive(r.m.encoded(spec),outline,parent)[1]['selected_node_ids'],['document'])
        self.assertEqual(r.rank(outline,'needle only\n','Document'),[])
    def test_invalid_schema_policy_anchor_and_limits(self):
        original=copy.deepcopy(self.spec)
        for key,value in [('schema','wrong'),('policy','other'),('index_sha256','0'*64),('query',' '),('query','x'*4001),('query',' '.join('term'+str(i) for i in range(65))),('top_k',True),('top_k',0),('top_k',17),('max_context_bytes',True),('max_context_bytes',0),('max_context_bytes',r.k.MAX_FILE+1)]:
            self.spec={**original,key:value}
            with self.subTest(key=key,value=str(value)[:30]),self.assertRaises(ValueError):self.build()
            self.assertFalse(self.out.exists())
        self.spec={**original,'required':[]}
        with self.assertRaises(ValueError):self.build()
    def test_query_anchor_mismatch(self):
        self.query.write_bytes(r.m.encoded(self.spec))
        with self.assertRaises(ValueError):r.build(self.idx,self.anchor,self.query,'0'*64,self.out)
        self.assertFalse(self.out.exists())
    def test_other_native_errors_not_swallowed(self):
        with patch.object(r.index,'selected_files',side_effect=ValueError('bad native input')),self.assertRaisesRegex(ValueError,'bad native input'):self.build()
    def test_no_truth_or_quality_promotion(self):
        self.build();report=self.report()
        for key in ('semantic_completeness_verified','relevance_verified','answer_quality_evaluated','model_called_here','scientific_verification','publication_authorized'):self.assertIs(report[key],False)
        self.assertIsNone(report['token_usage']);self.assertIsNone(report['monetary_cost'])
    def test_relocation_without_original_inputs(self):
        result=self.build();moved=self.root/'moved';shutil.move(self.out,moved);shutil.rmtree(self.idx);self.source.unlink();self.query.unlink()
        with patch.object(subprocess,'run',side_effect=AssertionError('offline')):r.verify(moved,result['manifest_sha256'])
    def test_resealed_artifact_tampering(self):
        for name in ['report.json','selection/context.json','selection/report.json']:
            self.build();p=self.out/name;p.write_bytes(p.read_bytes()+b' ')
            with self.assertRaises(ValueError):r.verify(self.out,self.reseal())
            shutil.rmtree(self.out)
    def test_extra_files_symlink_and_existing_output(self):
        result=self.build()
        with self.assertRaises(FileExistsError):self.build()
        (self.out/'extra').write_bytes(b'x')
        with self.assertRaises(ValueError):r.verify(self.out,self.reseal())
        (self.out/'extra').unlink();p=self.out/'query.json';p.unlink();p.symlink_to(self.query)
        with self.assertRaisesRegex(ValueError,'missing or unsafe source: query.json'):r.verify(self.out,self.reseal())
    def test_archive_bound_on_build_and_replay(self):
        result=self.build()
        with patch.object(r,'MAX_TOTAL',1),self.assertRaises(ValueError):r.verify(self.out,result['manifest_sha256'])
        shutil.rmtree(self.out)
        with patch.object(r,'MAX_TOTAL',1),self.assertRaises(ValueError):self.build()
        self.assertFalse(self.out.exists())
    def test_cli_success_no_result_and_invalid(self):
        def cli(*args):return subprocess.run([sys.executable,'-B',r.__file__,*map(str,args)],capture_output=True,text=True)
        for query,status in [('needle',0),('unfindable',3)]:
            self.spec['query']=query;self.query.write_bytes(r.m.encoded(self.spec))
            result=cli('search','--bundle',self.idx,'--sha256',self.anchor,'--query',self.query,'--query-sha256',r.m.sha(self.query.read_bytes()),'--output',self.out)
            self.assertEqual(result.returncode,status,result.stdout+result.stderr);anchor=json.loads(result.stdout)['manifest_sha256']
            self.assertEqual(cli('verify','--bundle',self.out,'--sha256',anchor).returncode,status)
            self.assertEqual(cli('verify','--bundle',self.out,'--sha256','0'*64).returncode,2);shutil.rmtree(self.out)


if __name__=='__main__':unittest.main()
