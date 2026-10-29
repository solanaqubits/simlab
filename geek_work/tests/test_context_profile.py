import copy
import sys
import unittest
from pathlib import Path
import test_memory as fixture
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
import geek_work_context_profile as p
import knowledge as k
sys.path.pop(0)

class ContextProfileTests(unittest.TestCase):
    def setUp(self): fixture.MemoryTests.setUp(self)
    def run_profile(self): return p.profile(self.g,self.root,self.req)
    def test_closure_and_omissions(self):
        r=self.run_profile()
        self.assertEqual(r['selected']['closure_ids'],['claim:premise'])
        self.assertEqual(r['omitted_ids'],['claim:objection'])
        self.assertEqual(r['full']['cards'],3)
        self.assertEqual(r['selected']['cards'],2)
    def test_unknown_metrics(self):
        r=self.run_profile()
        for key in ('token_usage','monetary_cost','answer_quality'): self.assertIsNone(r[key])
        self.assertEqual(r['model_calls'],0)
    def test_sizes_and_no_mutation(self):
        before=copy.deepcopy(self.g);r=self.run_profile()
        self.assertEqual(self.g,before)
        self.assertEqual(r['full']['utf8_bytes'],len(k.canonical(dict(cards=self.g['cards'],links=self.g['links']))))
        self.assertGreater(r['full']['utf8_bytes'],r['selected']['utf8_bytes'])
    def test_unicode_is_not_bytes(self):
        r=p.measure({'x':'формула'})
        self.assertGreater(r['utf8_bytes'],r['unicode_codepoints'])
    def test_stale_graph(self):
        self.req['expected_graph_sha256']='0'*64
        with self.assertRaisesRegex(k.Refusal,'graph_changed'):self.run_profile()
    def test_stale_revision(self):
        self.req['cards'][0]['revision']=2
        with self.assertRaisesRegex(k.Refusal,'revision_changed'):self.run_profile()
    def test_missing_source_visible(self):
        (self.root/'source.txt').unlink()
        self.assertIn('source_missing',self.run_profile()['selected']['issues'])
    def test_boundary_retained(self):
        self.g['links'].append(dict(**{'from':'claim:result','to':'claim:objection'},relation='related_to',scope='Not dependency'))
        self.req['expected_graph_sha256']=k.digest(k.canonical(self.g))
        r=self.run_profile();self.assertEqual(len(r['boundary_links']),1)
        self.assertEqual(r['selected']['cards'],2)
    def test_objection_included(self):
        self.g['links'].append(dict(**{'from':'claim:objection','to':'claim:result'},relation='contradicts',scope='Objection'))
        self.req['expected_graph_sha256']=k.digest(k.canonical(self.g))
        r=self.run_profile();self.assertEqual(r['selected']['cards'],3)
        self.assertEqual(r['selected']['sha256'],r['full']['sha256'])

    def replay(self, report):
        return p.verify(report,k.digest(k.canonical(report)),self.g,self.root,self.req)
    def test_replay(self):
        self.assertEqual(self.replay(self.run_profile())['status'],'verified_profile')
    def test_tampered_measurement_reanchored(self):
        r=self.run_profile();r['selected']['utf8_bytes']+=1
        with self.assertRaisesRegex(k.Refusal,'report_not_reproducible'):self.replay(r)
    def test_wrong_anchor(self):
        with self.assertRaisesRegex(k.Refusal,'report_anchor'):
            p.verify(self.run_profile(),'0'*64,self.g,self.root,self.req)
    def test_source_drift_replay(self):
        r=self.run_profile();(self.root/'source.txt').write_text('changed')
        with self.assertRaisesRegex(k.Refusal,'report_not_reproducible'):self.replay(r)
    def test_tool_pin_tamper(self):
        r=self.run_profile();r['tool_pins']={}
        with self.assertRaisesRegex(k.Refusal,'report_not_reproducible'):self.replay(r)
    def test_fabricated_cost(self):
        r=self.run_profile();r['monetary_cost']=0
        with self.assertRaisesRegex(k.Refusal,'report_not_reproducible'):self.replay(r)

    def budget(self, n, report=None):
        r=self.run_profile() if report is None else report
        return p.preflight(r,k.digest(k.canonical(r)),self.g,self.root,self.req,n)
    def test_exact_budget(self):
        r=self.run_profile();n=r['retrieval_envelope']['utf8_bytes']
        v=self.budget(n,r);self.assertEqual(v['status'],'within_context_budget')
        self.assertEqual(v['remaining_context_bytes'],0)
        self.assertFalse(v['execution_authorized'])
    def test_one_byte_short_no_truncation(self):
        before=copy.deepcopy(self.g);r=self.run_profile()
        v=self.budget(r['retrieval_envelope']['utf8_bytes']-1,r)
        self.assertIn('context_byte_budget_exceeded',v['reasons'])
        self.assertFalse(v['truncated']);self.assertEqual(self.g,before)
    def test_budget_checks_envelope_not_payload(self):
        r=self.run_profile()
        self.assertEqual(self.budget(r['selected']['utf8_bytes'],r)['status'],'refused')
    def test_budget_invalid(self):
        for n in (None,True,0,-1,1.5,16777217):
            with self.subTest(n=n),self.assertRaisesRegex(k.Refusal,'byte_budget_range'):self.budget(n)
    def test_budget_source_review(self):
        (self.root/'source.txt').unlink()
        self.assertIn('context_requires_review',self.budget(100000)['reasons'])
    def test_budget_cannot_admit_tampered_report(self):
        r=self.run_profile();r['retrieval_envelope']['utf8_bytes']=1
        with self.assertRaisesRegex(k.Refusal,'report_not_reproducible'):self.budget(100000,r)

if __name__=='__main__':unittest.main()
