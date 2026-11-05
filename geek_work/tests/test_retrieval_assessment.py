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
import geek_work_retrieval_assessment as a


class RetrievalAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.text='# Parent\r\nPremise hidden.\r\n## Needle\r\nNeedle answer 😀.\r\n# Other\r\nOther detail.\r\n'
        self.source=self.root/'source.md';self.source.write_bytes(self.text.encode());self.idx=self.root/'index';self.packet=self.root/'packet';self.review=self.root/'review';self.out=self.root/'assessment';self.plan_path=self.root/'plan.json'
        index_sha=a.index.build(self.source,a.m.sha(self.source.read_bytes()),self.idx)['manifest_sha256']
        self.packet_sha=a.review.prepare(self.idx,index_sha,self.packet)['manifest_sha256']
        def ref(i,role,quote):
            start=self.text.index(quote);return dict(id=i,role=role,start=start,end=start+len(quote),quote=quote)
        self.response=dict(schema=a.review.RESPONSE,packet_sha256=self.packet_sha,reviewer=dict(id='test author',model_profile=None,prior_exposure='Full synthetic fixture known.'),independence_verified=False,accepted_as_gold=False,cases=[
            dict(id='match',question='needle',answerability='answerable',required=[ref('a','answer','Needle answer 😀.'),ref('p','premise','Premise hidden.'),ref('h','limit','# Parent\r\n')],rationale='Requires answer, parent premise and heading.'),
            dict(id='miss',question='непереводимое',answerability='answerable',required=[ref('a','answer','Other detail.')],rationale='Nonmatching query still needs this span.'),
            dict(id='stop',question='the and',answerability='answerable',required=[ref('a','answer','Other detail.')],rationale='Stopword-only query still belongs in denominator.'),
            dict(id='absent',question='Other',answerability='not_answerable',required=[],rationale='Reported absence, despite lexical matches.'),
            dict(id='uncertain',question='unfindable',answerability='uncertain',required=[],rationale='Unresolved question, no coverage truth.')])
        self.make_review()
    def make_review(self):
        p=self.root/'response.json';p.write_bytes(a.m.encoded(self.response))
        if self.review.exists():shutil.rmtree(self.review)
        self.review_sha=a.review.receive(self.packet,self.packet_sha,p,a.m.sha(p.read_bytes()),self.review)['manifest_sha256']
        self.plan=dict(schema='geek-work-retrieval-assessment-plan-1',review_sha256=self.review_sha,retriever_source_sha256=a.m.sha(Path(a.search.__file__).read_bytes()),policy=a.search.POLICY,top_k=1,max_context_bytes=65536)
    def build(self):
        self.plan_path.write_bytes(a.m.encoded(self.plan));return a.build(self.review,self.review_sha,self.plan_path,a.m.sha(self.plan_path.read_bytes()),self.out)
    def report(self):return json.loads((self.out/'report.json').read_bytes())
    def reseal(self):
        files={str(p.relative_to(self.out)):p.read_bytes() for p in self.out.rglob('*') if p.is_file() and p!=self.out/'manifest.json'}
        meta=a.manifest(files);(self.out/'manifest.json').write_bytes(meta);return a.m.sha(meta)
    def test_all_answerable_cases_remain_in_denominator(self):
        self.build();lex,full=self.report()['summary']
        self.assertEqual((lex['total_cases'],lex['eligible_cases'],lex['required_span_count'],lex['covered_span_count']),(5,3,5,2))
        self.assertEqual((lex['eligible_cases_with_context'],lex['eligible_cases_without_context'],lex['cases_with_all_required_spans']),(1,2,0))
        self.assertEqual((full['covered_span_count'],full['cases_with_all_required_spans']),(5,3))
    def test_no_matches_and_no_terms_are_zero_coverage_null_bytes(self):
        self.build();rows=self.report()['rows']
        for cid,status in [('miss','no_matches'),('stop','no_query_terms')]:
            row=next(r for r in rows if r['case_id']==cid and r['variant_id']=='lexical')
            self.assertEqual(row['retrieval_status'],status);self.assertEqual(row['covered_count'],0);self.assertFalse(row['all_required_covered']);self.assertIsNone(row['context_bytes'])
            self.assertEqual(row['requirements'][0]['status'],'missing')
    def test_visible_ancestor_heading_does_not_restore_parent_premise(self):
        self.build();row=self.report()['rows'][0]
        self.assertEqual([c['status'] for c in row['requirements']],['covered','missing','covered'])
    def test_unresolved_cases_keep_null_coverage_even_with_context(self):
        self.build();report=self.report()
        for row in report['rows']:
            if row['case_id'] in ('absent','uncertain'):
                for name in ('covered_count','all_required_covered','required_count','requirements'):self.assertIsNone(row[name])
        self.assertEqual(report['summary'][0]['reported_not_answerable'],dict(cases=1,with_context=1,without_context=0))
        self.assertFalse(report['semantic_abstention_evaluated'])
    def test_only_unresolved_cases_are_not_vacuous_successes(self):
        self.response['cases']=self.response['cases'][3:];self.make_review();self.build()
        for summary in self.report()['summary']:
            self.assertEqual(summary['eligible_cases'],0);self.assertEqual(summary['cases_with_all_required_spans'],0);self.assertIsNone(summary['eligible_context_bytes_on_produced'])
        self.assertTrue(all(r['all_required_covered'] is None for r in self.report()['rows']))
    def test_budget_refusals_keep_all_requirements_and_no_fallback(self):
        self.plan['max_context_bytes']=1;self.build();lex,full=self.report()['summary']
        for summary in (lex,full):
            self.assertEqual(summary['eligible_cases'],3);self.assertEqual(summary['required_span_count'],5);self.assertEqual(summary['covered_span_count'],0);self.assertIsNone(summary['context_bytes_on_produced'])
        self.assertEqual(full['retrieval_status_counts'],{'budget_rejected':5})
        self.assertEqual(lex['retrieval_status_counts']['budget_exhausted'],2)
        self.assertFalse((self.out/'baseline/context.json').exists());self.assertFalse((self.out/'searches/match/selection/context.json').exists())
    def test_only_question_and_fixed_settings_enter_retrieval(self):
        with patch.object(a.search,'derive',wraps=a.search.derive) as derive:self.build()
        self.assertEqual(derive.call_count,5)
        for call,case in zip(derive.call_args_list,self.response['cases']):
            query=json.loads(call.args[0]);self.assertEqual(set(query),{'schema','index_sha256','query','policy','top_k','max_context_bytes'})
            self.assertEqual(query['query'],case['question']);self.assertEqual(query['top_k'],1)
    def test_serialized_native_context_size_and_shared_full_baseline(self):
        self.build();report=self.report()
        for row in report['rows']:
            if row['context_obtained']:
                p=self.out/('baseline/context.json' if row['variant_id']=='full' else 'searches/'+row['case_id']+'/selection/context.json')
                self.assertEqual(row['context_bytes'],len(p.read_bytes()));self.assertEqual(row['context_sha256'],a.m.sha(p.read_bytes()))
        self.assertEqual(report['summary'][1]['context_bytes_on_produced'],len((self.out/'baseline/context.json').read_bytes())*5)
    def test_frozen_source_and_plan_validation(self):
        original=copy.deepcopy(self.plan)
        for key,value in [('retriever_source_sha256','0'*64),('review_sha256','0'*64),('policy','different'),('top_k',True),('top_k',17),('max_context_bytes',0),('max_context_bytes',True),('schema','different')]:
            self.plan={**original,key:value}
            with self.subTest(key=key),self.assertRaises(ValueError):self.build()
        self.plan={**original,'labels':[]}
        with self.assertRaises(ValueError):self.build()
    def test_invalid_native_errors_do_not_become_budget_results(self):
        with patch.object(a.index,'selected_files',side_effect=ValueError('invalid selection')),self.assertRaisesRegex(ValueError,'invalid selection'):self.build()
    def test_plan_anchor_mismatch(self):
        self.plan_path.write_bytes(a.m.encoded(self.plan))
        with self.assertRaisesRegex(ValueError,'plan anchor mismatch'):a.build(self.review,self.review_sha,self.plan_path,'0'*64,self.out)
    def test_resealed_reports_and_contexts_rejected(self):
        for name in ['report.json','searches/match/report.json','searches/match/selection/context.json','baseline/context.json']:
            self.build();p=self.out/name;p.write_bytes(p.read_bytes()+b' ')
            with self.assertRaises(ValueError):a.verify(self.out,self.reseal())
            shutil.rmtree(self.out)
    def test_extra_files_symlinks_and_existing_output(self):
        self.build()
        with self.assertRaises(FileExistsError):self.build()
        (self.out/'extra').write_bytes(b'x')
        with self.assertRaises(ValueError):a.verify(self.out,self.reseal())
        (self.out/'extra').unlink();p=self.out/'plan.json';p.unlink();p.symlink_to(self.plan_path)
        with self.assertRaisesRegex(ValueError,'missing or unsafe source: plan.json'):a.verify(self.out,self.reseal())
    def test_relocation_without_originals_or_network(self):
        result=self.build();moved=self.root/'moved';shutil.move(self.out,moved)
        for p in (self.packet,self.review,self.idx):shutil.rmtree(p)
        self.source.unlink();self.plan_path.unlink()
        with patch.object(subprocess,'run',side_effect=AssertionError('offline')):a.verify(moved,result['manifest_sha256'])
    def test_archive_bound_on_build_and_replay(self):
        result=self.build()
        with patch.object(a,'MAX_TOTAL',1),self.assertRaises(ValueError):a.verify(self.out,result['manifest_sha256'])
        shutil.rmtree(self.out)
        with patch.object(a,'MAX_TOTAL',1),self.assertRaises(ValueError):self.build()
        self.assertFalse(self.out.exists())
    def test_integrity_does_not_promote_quality_or_independence(self):
        self.build();report=self.report()
        for name in ('independence_verified','held_out_verified','accepted_as_gold','annotation_sufficiency_verified','answerability_verified','answer_quality_evaluated','semantic_abstention_evaluated','model_called_here','scientific_verification','publication_authorized'):self.assertIs(report[name],False)
        self.assertIsNone(report['token_usage']);self.assertIsNone(report['monetary_cost'])
    def test_cli_build_and_replay(self):
        self.plan_path.write_bytes(a.m.encoded(self.plan))
        def cli(*args):return subprocess.run([sys.executable,'-B',a.__file__,*map(str,args)],capture_output=True,text=True)
        r=cli('build','--bundle',self.review,'--sha256',self.review_sha,'--plan',self.plan_path,'--plan-sha256',a.m.sha(self.plan_path.read_bytes()),'--output',self.out)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);anchor=json.loads(r.stdout)['manifest_sha256']
        self.assertEqual(cli('verify','--bundle',self.out,'--sha256',anchor).returncode,0)
        self.assertEqual(cli('verify','--bundle',self.out,'--sha256','0'*64).returncode,2)


if __name__=='__main__':unittest.main()
