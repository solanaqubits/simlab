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
import geek_work_retrieval_review as r


class RetrievalReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.text='# Material\r\nУсловие 😀.\r\n## Result\r\nOnly a finite test.\r\n'
        self.source=self.root/'source.md';self.source.write_bytes(self.text.encode());self.idx=self.root/'index'
        self.index_sha=r.index.build(self.source,r.m.sha(self.source.read_bytes()),self.idx)['manifest_sha256']
        self.packet=self.root/'packet';self.anchor=r.prepare(self.idx,self.index_sha,self.packet)['manifest_sha256']
        self.response=self.root/'response.json';self.out=self.root/'review'
        quote='Условие 😀.';start=self.text.index(quote)
        self.spec=dict(schema=r.RESPONSE,packet_sha256=self.anchor,reviewer=dict(id='fixture author',model_profile=None,prior_exposure='Synthetic test; written with access to all material.'),independence_verified=False,accepted_as_gold=False,cases=[dict(id='q1',question='What premise applies?',answerability='answerable',required=[dict(id='p1',role='premise',start=start,end=start+len(quote),quote=quote)],rationale='Synthetic citation for protocol testing, not independent annotation.'),dict(id='q2',question='Is the universal theorem proved?',answerability='not_answerable',required=[],rationale='Reviewer reports that this material establishes only finite checks.'),dict(id='q3',question='What timing can be inferred?',answerability='uncertain',required=[],rationale='Reviewer cannot determine the scope of this question.')])
    def receive(self):
        self.response.write_bytes(r.m.encoded(self.spec));return r.receive(self.packet,self.anchor,self.response,r.m.sha(self.response.read_bytes()),self.out)
    def report(self):return json.loads((self.out/'report.json').read_bytes())
    def reseal(self,folder,schema):
        files={str(p.relative_to(folder)):p.read_bytes() for p in folder.rglob('*') if p.is_file() and p!=folder/'manifest.json'}
        meta=r.manifest(schema,files);(folder/'manifest.json').write_bytes(meta);return r.m.sha(meta)
    def test_packet_has_source_and_empty_template_not_prior_labels(self):
        _,files=r.packet_read(self.packet,self.anchor)
        self.assertEqual(set(files),{'index/source.md','index/outline.json','index/manifest.json','packet.json','response.template.json','INSTRUCTIONS.md','manifest.json'})
        template=json.loads(files['response.template.json']);self.assertEqual(template['cases'],[]);self.assertIsNone(template['packet_sha256'])
        self.assertEqual(files['index/source.md'],self.text.encode())
        self.assertFalse(json.loads(files['packet.json'])['retrieval_output_files_included'])
    def test_receive_preserves_all_answerability_states(self):
        result=self.receive();report=self.report();r.verify_review(self.out,result['manifest_sha256'])
        self.assertEqual(report['coverage_eligible_case_ids'],['q1']);self.assertEqual(report['reported_not_answerable_case_ids'],['q2']);self.assertEqual(report['reported_uncertain_case_ids'],['q3'])
        self.assertEqual(report['exact_citations_checked'],1);self.assertEqual(report['case_count'],3)
        self.assertEqual((self.out/'response.json').read_bytes(),self.response.read_bytes())
    def test_all_unresolved_does_not_become_vacuous_coverage_success(self):
        self.spec['cases']=self.spec['cases'][1:];self.receive();report=self.report()
        self.assertEqual(report['coverage_eligible_case_ids'],[]);self.assertEqual(report['case_count'],2);self.assertEqual(report['exact_citations_checked'],0)
        self.assertFalse(report['answerability_verified']);self.assertNotIn('coverage',report)
    def test_nonempty_but_exposed_review_stays_unverified(self):
        self.receive();report=self.report()
        for field in ('reviewer_identity_verified','independence_verified','accepted_as_gold','answerability_verified','annotation_sufficiency_verified','answer_quality_evaluated','model_called_here','scientific_verification','publication_authorized'):self.assertIs(report[field],False)
        self.assertIsNone(report['token_usage']);self.assertIsNone(report['monetary_cost']);self.assertIn('Synthetic',report['reviewer']['prior_exposure'])
    def test_wrong_packet_and_response_anchors(self):
        self.spec['packet_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'response packet mismatch'):self.receive()
        self.response.write_bytes(r.m.encoded(self.spec))
        with self.assertRaisesRegex(ValueError,'response anchor mismatch'):r.receive(self.packet,self.anchor,self.response,'0'*64,self.out)
        self.assertFalse(self.out.exists())
    def test_blank_template_and_empty_cases_refused(self):
        self.spec=json.loads((self.packet/'response.template.json').read_bytes())
        with self.assertRaises(ValueError):self.receive()
        self.spec.update(packet_sha256=self.anchor,reviewer=dict(id='human',model_profile=None,prior_exposure='none declared'))
        with self.assertRaises(ValueError):self.receive()
    def test_quotes_unicode_crlf_and_offsets(self):
        original=copy.deepcopy(self.spec)
        for key,value in [('quote','changed'),('start',True),('start',-1),('end',99999),('end',False)]:
            self.spec=copy.deepcopy(original);self.spec['cases'][0]['required'][0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):self.receive()
        self.spec=original;ref=self.spec['cases'][0]['required'][0];ref.update(start=0,end=len(self.text),quote=self.text)
        self.receive();self.assertEqual(self.report()['exact_citations_checked'],1)
    def test_required_span_cardinality_and_unresolved_spans(self):
        original=copy.deepcopy(self.spec)
        for state,refs in [('answerable',[]),('not_answerable',original['cases'][0]['required']),('uncertain',original['cases'][0]['required'])]:
            self.spec=copy.deepcopy(original);self.spec['cases'][0].update(answerability=state,required=refs)
            with self.assertRaises(ValueError):self.receive()
    def test_duplicate_cases_questions_spans_and_roles(self):
        original=copy.deepcopy(self.spec)
        mutations=[lambda s:s['cases'].append(copy.deepcopy(s['cases'][0])),lambda s:s['cases'][1].update(question=' WHAT PREMISE APPLIES? '),lambda s:s['cases'][0]['required'].append({**s['cases'][0]['required'][0],'id':'p2'}),lambda s:s['cases'][0]['required'][0].update(role='gold')]
        for mutate in mutations:
            self.spec=copy.deepcopy(original);mutate(self.spec)
            with self.assertRaises(ValueError):self.receive()
    def test_unknown_fields_bad_types_limits_and_promotions(self):
        original=copy.deepcopy(self.spec)
        mutations=[lambda s:s.update(accepted_as_gold=True),lambda s:s.update(independence_verified=True),lambda s:s.update(extra='x'),lambda s:s['reviewer'].update(prior_exposure=''),lambda s:s['reviewer'].update(model_profile=3),lambda s:s['cases'][0].update(answerability='unknown'),lambda s:s['cases'][0].update(question='x'*4001),lambda s:s.update(cases=[{**s['cases'][0],'id':f'q{i}','question':f'question {i}'} for i in range(17)])]
        for mutate in mutations:
            self.spec=copy.deepcopy(original);mutate(self.spec)
            with self.assertRaises(ValueError):self.receive()
    def test_packet_resealed_extra_file_and_metadata_promotion(self):
        for name in ['extra','packet.json']:
            folder=self.root/name.replace('.json','-copy');shutil.copytree(self.packet,folder)
            (folder/name).write_bytes(b'{}')
            with self.assertRaises(ValueError):r.packet_read(folder,self.reseal(folder,r.PACKET))
    def test_resealed_response_report_and_nested_packet_tampering(self):
        for name in ['report.json','packet/INSTRUCTIONS.md']:
            self.receive();p=self.out/name;p.write_bytes(p.read_bytes()+b' ')
            with self.assertRaises(ValueError):r.verify_review(self.out,self.reseal(self.out,r.REVIEW))
            shutil.rmtree(self.out)
    def test_symlink_rejected_with_matching_manifest(self):
        self.receive();p=self.out/'response.json';p.unlink();p.symlink_to(self.response)
        with self.assertRaisesRegex(ValueError,'missing or unsafe source: response.json'):r.verify_review(self.out,self.reseal(self.out,r.REVIEW))
    def test_relocation_without_originals_or_network(self):
        result=self.receive();moved=self.root/'moved';shutil.move(self.out,moved)
        shutil.rmtree(self.packet);shutil.rmtree(self.idx);self.source.unlink();self.response.unlink()
        with patch.object(subprocess,'run',side_effect=AssertionError('offline')):r.verify_review(moved,result['manifest_sha256'])
    def test_packet_and_review_bounds_on_build_and_replay(self):
        result=self.receive()
        with patch.object(r,'MAX_PACKET',1):
            with self.assertRaises(ValueError):r.prepare(self.idx,self.index_sha,self.root/'tiny-packet')
            with self.assertRaises(ValueError):r.packet_read(self.packet,self.anchor)
        with patch.object(r,'MAX_REVIEW',1):
            with self.assertRaises(ValueError):r.verify_review(self.out,result['manifest_sha256'])
            shutil.rmtree(self.out)
            with self.assertRaises(ValueError):self.receive()
            self.assertFalse(self.out.exists())
    def test_existing_output_and_source_separation(self):
        self.receive()
        with self.assertRaises(FileExistsError):self.receive()
        with self.assertRaises(ValueError):r.prepare(self.idx,self.index_sha,self.idx/'inside')
    def test_cli_packet_receive_replay_and_invalid(self):
        def cli(*args):return subprocess.run([sys.executable,'-B',r.__file__,*map(str,args)],capture_output=True,text=True)
        second=self.root/'second';result=cli('prepare','--bundle',self.idx,'--sha256',self.index_sha,'--output',second)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertEqual(json.loads(result.stdout)['manifest_sha256'],self.anchor)
        self.assertEqual(cli('verify','--bundle',second,'--sha256',self.anchor).returncode,0)
        self.response.write_bytes(r.m.encoded(self.spec));result=cli('receive','--bundle',second,'--sha256',self.anchor,'--response',self.response,'--response-sha256',r.m.sha(self.response.read_bytes()),'--output',self.out)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr);anchor=json.loads(result.stdout)['manifest_sha256']
        self.assertEqual(cli('verify-review','--bundle',self.out,'--sha256',anchor).returncode,0)
        self.assertEqual(cli('verify-review','--bundle',self.out,'--sha256','0'*64).returncode,2)


if __name__=='__main__':unittest.main()
