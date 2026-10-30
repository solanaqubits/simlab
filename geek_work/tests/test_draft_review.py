import copy
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
import geek_work_draft_review as d
sys.path.pop(0)

class DraftReviewTests(unittest.TestCase):
    def setUp(self):
        text='Условие α не удалять.'
        self.packet=dict(schema='geek-work-review-draft-1',state='awaiting_independent_annotation',sources=[dict(id='s',text=text,sha256=d.k.digest(text.encode()))],cases=[dict(id='c',source_id='s',candidate='Сохранять условие.')])
        self.review=dict(schema='geek-work-review-draft-response-1',packet_file_sha256='',reviewer=dict(id='fixture',kind='human',prior_exposure='synthetic',relationship_to_author='fixture'),decisions=[dict(case_id='c',supported=True,failure_classes=[],rationale='Fixture only',citations=[dict(source_id='s',start=0,end=len(text),quote=text)])],accepted_as_gold=False)
    def run_check(self):
        raw=d.k.canonical(self.packet);anchor=d.k.digest(raw);self.review['packet_file_sha256']=anchor
        return d.assess(raw,self.review,anchor)
    def test_complete_never_gold(self):
        r=self.run_check();self.assertEqual(r['status'],'structurally_complete');self.assertFalse(r['accepted_as_gold']);self.assertFalse(r['independence_verified'])
    def test_abstention_retained(self):
        self.review['decisions'][0]['supported']=None
        self.assertIn('abstained',self.run_check()['cases'][0]['issues'])
    def test_missing_case(self):
        self.review['decisions']=[];self.assertEqual(self.run_check()['missing_case_ids'],['c'])
    def test_missing_identity(self):
        self.review['reviewer']['id']=None;self.assertEqual(self.run_check()['status'],'needs_review')
    def test_wrong_anchor(self):
        with self.assertRaisesRegex(d.k.Refusal,'packet_anchor'):d.assess(d.k.canonical(self.packet),self.review,'0'*64)
    def test_changed_source(self):
        self.packet['sources'][0]['text']='changed'
        with self.assertRaisesRegex(d.k.Refusal,'source_hash'):self.run_check()
    def test_false_citation(self):
        self.review['decisions'][0]['citations'][0]['quote']='invented'
        with self.assertRaisesRegex(d.k.Refusal,'citation_text'):self.run_check()
    def test_boolean_offset_refused(self):
        self.review['decisions'][0]['citations'][0]['start']=False
        with self.assertRaisesRegex(d.k.Refusal,'citation_span'):self.run_check()
    def test_duplicate_case(self):
        self.packet['cases'].append(copy.deepcopy(self.packet['cases'][0]))
        with self.assertRaisesRegex(d.k.Refusal,'packet_case'):self.run_check()
    def test_unknown_decision(self):
        self.review['decisions'][0]['case_id']='unknown'
        with self.assertRaisesRegex(d.k.Refusal,'decision_id'):self.run_check()
    def test_wrong_source(self):
        self.review['decisions'][0]['citations'][0]['source_id']='other'
        with self.assertRaisesRegex(d.k.Refusal,'citation_source'):self.run_check()
    def test_inconsistent_label(self):
        self.review['decisions'][0]['failure_classes']=['missing_premise']
        self.assertIn('supported_with_failures',self.run_check()['cases'][0]['issues'])
    def test_gold_claim_refused(self):
        self.review['accepted_as_gold']=True
        with self.assertRaisesRegex(d.k.Refusal,'gold_claim'):self.run_check()

class DraftReviewV2Tests(DraftReviewTests):
    def setUp(self):
        super().setUp()
        self.packet.update(response_schema='geek-work-review-draft-response-2',failure_taxonomy={'scope':'Fixture scope error'})
        self.review['schema']='geek-work-review-draft-response-2'
        self.review['decisions'][0]['relation_to_source']='entails'
    def test_relation_required(self):
        self.review['decisions'][0]['relation_to_source']=None
        self.assertIn('relation_missing',self.run_check()['cases'][0]['issues'])
    def test_conflicting_relation(self):
        self.review['decisions'][0]['relation_to_source']='contradicts'
        self.assertIn('label_relation_conflict',self.run_check()['cases'][0]['issues'])
    def test_unknown_mechanism(self):
        self.review['decisions'][0]['failure_classes']=['direct_contradiction']
        with self.assertRaisesRegex(d.k.Refusal,'unknown_failure_class'):self.run_check()
    def test_old_review_not_reused(self):
        self.review['schema']='geek-work-review-draft-response-1'
        with self.assertRaisesRegex(d.k.Refusal,'review_packet'):self.run_check()
    def test_v2_missing_taxonomy(self):
        del self.packet['failure_taxonomy']
        with self.assertRaisesRegex(d.k.Refusal,'failure_taxonomy'):self.run_check()
    def test_inconsistent_label(self):
        self.review['decisions'][0]['failure_classes']=['scope']
        self.assertIn('supported_with_failures',self.run_check()['cases'][0]['issues'])

class PartialAxesTests(unittest.TestCase):
    def setUp(self):
        self.fixture = DraftReviewV2Tests()
        self.fixture.setUp()

    def test_known_false_unknown_relation_is_not_complete(self):
        self.fixture.review['decisions'][0].update(
            supported=False, relation_to_source=None, failure_classes=['scope'])
        result = self.fixture.run_check()
        self.assertEqual(result['status'], 'needs_review')
        self.assertEqual(result['cases'][0]['issues'], ['relation_missing'])

    def test_known_relation_unknown_mechanism_is_not_complete(self):
        self.fixture.review['decisions'][0].update(
            supported=False, relation_to_source='contradicts', failure_classes=None)
        result = self.fixture.run_check()
        self.assertEqual(result['status'], 'needs_review')
        self.assertEqual(result['cases'][0]['issues'], ['failure_classes_missing'])

    def test_abstention_relations_are_retained_as_unresolved(self):
        for relation in ('ambiguous', 'insufficient_information'):
            with self.subTest(relation=relation):
                self.fixture.review['decisions'][0].update(
                    supported=None, relation_to_source=relation, failure_classes=[])
                result = self.fixture.run_check()
                self.assertEqual(result['status'], 'needs_review')
                self.assertEqual(result['cases'][0]['issues'], ['abstained'])
