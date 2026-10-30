import base64
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import test_draft_review as fixture
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
import geek_work_council as c
sys.path.pop(0)

class CouncilTests(unittest.TestCase):
    def setUp(self):
        f=fixture.DraftReviewTests();f.setUp();self.packet=c.k.canonical(f.packet);self.anchor=c.k.digest(self.packet)
        self.a=f.review;self.a['packet_file_sha256']=self.anchor
        self.b=copy.deepcopy(self.a);self.b['reviewer']['id']='second-fixture'
    def build(self,raw=None):return c.compare(self.packet,raw or [c.k.canonical(self.a),c.k.canonical(self.b)],self.anchor)
    def test_agreement_never_gold(self):
        r=self.build();self.assertEqual(r['cases'][0]['state'],'agreement');self.assertFalse(r['accepted_as_gold']);self.assertIsNone(r['participants'][0]['monetary_cost'])
    def test_disagreement_preserved(self):
        self.b['decisions'][0].update(supported=False,failure_classes=['scope'])
        r=self.build();self.assertEqual(r['disagreement_cases'],['c']);self.assertEqual(len(r['cases'][0]['observations']),2)
    def test_abstention_not_false_vote(self):
        self.b['decisions'][0].update(supported=None,failure_classes=None)
        r=self.build();self.assertEqual(r['cases'][0]['observations'][1]['state'],'incomplete_decision')
        self.b['decisions'][0]['failure_classes']=[]
        r=self.build();self.assertEqual(r['cases'][0]['observations'][1]['state'],'abstained');self.assertEqual(r['cases'][0]['valid_decisions'],1)
    def test_missing(self):
        self.b['decisions']=[];self.assertEqual(self.build()['cases'][0]['observations'][1]['state'],'missing')
    def test_invalid_json_preserved(self):
        raw=b'not JSON';r=self.build([c.k.canonical(self.a),raw])
        self.assertEqual(base64.b64decode(r['participants'][1]['raw_base64']),raw)
        self.assertEqual(r['status'],'needs_review')
    def test_invalid_quote_not_counted(self):
        self.b['decisions'][0]['citations'][0]['quote']='wrong'
        self.assertEqual(self.build()['cases'][0]['valid_decisions'],1)
    def test_duplicate_raw(self):
        raw=c.k.canonical(self.a)
        with self.assertRaisesRegex(c.k.Refusal,'duplicate_response_bytes'):self.build([raw,raw])
    def test_duplicate_declared_identity(self):
        self.b['reviewer']['id']=self.a['reviewer']['id']
        self.b['reviewer']['prior_exposure']='different'
        with self.assertRaisesRegex(c.k.Refusal,'duplicate_declared_reviewer'):self.build()
    def test_participant_limit(self):
        with self.assertRaisesRegex(c.k.Refusal,'participant_limit'):c.compare(self.packet,[],self.anchor)
    def test_byte_limit(self):
        with patch.object(c,'MAX_TOTAL_BYTES',1),self.assertRaisesRegex(c.k.Refusal,'council_byte_limit'):self.build()
    def test_replay_tamper(self):
        raw=[c.k.canonical(self.a),c.k.canonical(self.b)];r=self.build(raw)
        self.assertEqual(c.verify(r,c.k.digest(c.k.canonical(r)),self.packet,raw,self.anchor)['status'],'verified_council_comparison')
        r['cases'][0]['state']='disagreement'
        with self.assertRaisesRegex(c.k.Refusal,'council_report_changed'):c.verify(r,c.k.digest(c.k.canonical(r)),self.packet,raw,self.anchor)
    def test_wrong_packet_anchor(self):
        with self.assertRaisesRegex(c.k.Refusal,'packet_anchor'):c.compare(self.packet,[b'a',b'b'],'0'*64)
    def test_v2_relations_preserved(self):
        packet=c.k.strict_json(self.packet);packet.update(response_schema='geek-work-review-draft-response-2',failure_taxonomy={'scope':'Fixture'})
        self.packet=c.k.canonical(packet);self.anchor=c.k.digest(self.packet)
        for value in (self.a,self.b):
            value.update(schema='geek-work-review-draft-response-2',packet_file_sha256=self.anchor)
            value['decisions'][0]['relation_to_source']='entails'
        self.b['decisions'][0].update(supported=False,failure_classes=['scope'],relation_to_source='not_established')
        result=self.build();self.assertEqual(result['status'],'comparison_ready')
        self.assertEqual(result['cases'][0]['state'],'disagreement')
        self.assertEqual(result['cases'][0]['observations'][1]['decision']['relation_to_source'],'not_established')
    def test_v1_against_v2_packet_not_counted(self):
        packet=c.k.strict_json(self.packet);packet.update(response_schema='geek-work-review-draft-response-2',failure_taxonomy={'scope':'Fixture'})
        self.packet=c.k.canonical(packet);self.anchor=c.k.digest(self.packet)
        for value in (self.a,self.b):value['packet_file_sha256']=self.anchor
        result=self.build();self.assertTrue(all(p['status']=='invalid_response' for p in result['participants']))
        self.assertEqual(result['cases'][0]['valid_decisions'],0)

    def test_same_label_different_mechanism_visible(self):
        self.a['decisions'][0].update(supported=False,failure_classes=['scope'])
        self.b['decisions'][0].update(supported=False,failure_classes=['evidence'])
        result=self.build()
        self.assertEqual(result['cases'][0]['state'],'agreement')
        self.assertEqual(result['mechanism_disagreement_cases'],['c'])
        self.assertEqual(result['cases'][0]['relation_state'],'not_available')
    def test_v2_same_label_different_relation_visible(self):
        packet=c.k.strict_json(self.packet);packet.update(response_schema='geek-work-review-draft-response-2',failure_taxonomy={'scope':'Fixture'})
        self.packet=c.k.canonical(packet);self.anchor=c.k.digest(self.packet)
        for value in (self.a,self.b):
            value.update(schema='geek-work-review-draft-response-2',packet_file_sha256=self.anchor)
            value['decisions'][0].update(supported=False,failure_classes=['scope'],relation_to_source='contradicts')
        self.b['decisions'][0]['relation_to_source']='not_established'
        result=self.build()
        self.assertEqual(result['cases'][0]['state'],'agreement')
        self.assertEqual(result['relation_disagreement_cases'],['c'])
        self.assertEqual(result['cases'][0]['mechanism_state'],'agreement')

    def test_partial_v2_axes_do_not_count_as_complete_votes(self):
        packet=c.k.strict_json(self.packet)
        packet.update(response_schema='geek-work-review-draft-response-2',
                      failure_taxonomy={'scope':'Fixture'})
        self.packet=c.k.canonical(packet); self.anchor=c.k.digest(self.packet)
        for value in (self.a,self.b):
            value.update(schema='geek-work-review-draft-response-2',packet_file_sha256=self.anchor)
            value['decisions'][0].update(supported=False,failure_classes=['scope'],relation_to_source='contradicts')
        for field in ('relation_to_source','failure_classes'):
            with self.subTest(field=field):
                saved=self.b['decisions'][0][field]
                self.b['decisions'][0][field]=None
                result=self.build()
                self.assertEqual(result['status'],'needs_review')
                self.assertEqual(result['cases'][0]['valid_decisions'],1)
                self.assertEqual(result['cases'][0]['observations'][1]['state'],'incomplete_decision')
                self.assertIsNone(result['cases'][0]['observations'][1]['decision'][field])
                self.b['decisions'][0][field]=saved
