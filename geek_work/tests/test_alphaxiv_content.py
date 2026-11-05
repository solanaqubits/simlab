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
import geek_work_alphaxiv_content as a


class AlphaXivContentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.output=self.root/'archive';self.body='Страница 😀\r\nНе доказано: $x ≠ 0$.\r\n';q='Не доказано: $x ≠ 0$.';start=self.body.index(q)
        self.raw=a.m.encoded({'content':[{'type':'text','text':self.body}]})
        self.spec=dict(schema='geek-work-alphaxiv-content-import-1',request=dict(tool='get_paper_content',url='https://arxiv.org/abs/2601.00001v2',fullText=True),
            response=dict(format='json',state='complete'),annotation=dict(representation='extracted_text',paper_id='2601.00001v2',observed_at='2026-11-04T00:00:00Z',note='Synthetic fixture; no provider request'),
            excerpts=[dict(id='claim',text_pointer='/content/0/text',start=start,end=start+len(q),quote=q,reported_page=3)])
    def capture(self):
        sp=self.root/'spec.json';rp=self.root/'response.raw';sp.write_bytes(a.m.encoded(self.spec));rp.write_bytes(self.raw)
        return a.capture(sp,a.m.sha(sp.read_bytes()),rp,a.m.sha(self.raw),self.output)
    def report(self):return json.loads((self.output/'content.json').read_bytes())
    def reseal(self):
        files={n:(self.output/n).read_bytes() for n in a.FILES};meta=a.manifest(files);(self.output/'manifest.json').write_bytes(meta);return a.m.sha(meta)
    def test_exact_unicode_crlf_quote_and_labels(self):
        r=self.capture();doc=self.report();self.assertEqual(doc['status'],'content_bound_review_required')
        e=doc['excerpts'][0];self.assertEqual(e['quote'],self.body[e['start']:e['end']]);self.assertEqual(e['reported_page'],3)
        self.assertTrue(e['exact_response_quote_verified']);self.assertFalse(e['pdf_page_verified']);self.assertFalse(e['original_paper_quote_verified'])
        for key in ('representation_verified','paper_identity_verified','origin_authenticated','scientific_verification','network_called_here'):self.assertIs(doc[key],False)
        self.assertTrue(a.verify(self.output,r['manifest_sha256'])['integrity_reproduced'])
    def test_ai_report_is_never_promoted_by_fulltext_request(self):
        self.spec['annotation']['representation']='ai_report';r=self.capture()
        self.assertEqual(r['status'],'content_requires_resolution');self.assertIn('requested_full_text_but_reported_ai_report',r['issues'])
        self.assertEqual(self.report()['excerpts'][0]['reported_representation'],'ai_report')
    def test_default_request_may_return_report_or_text(self):
        self.spec['request']['fullText']=False
        for representation in ('ai_report','extracted_text'):
            self.spec['annotation']['representation']=representation;r=self.capture();self.assertEqual(r['issues'],[])
            self.assertEqual(self.report()['requested_representation'],'prefer_ai_report_with_text_fallback');shutil.rmtree(self.output)
    def test_unknown_representation_and_version_preserved(self):
        self.spec['annotation'].update(representation='unknown',paper_id=None);r=self.capture()
        self.assertEqual(set(r['issues']),{'representation_unknown','returned_version_unconfirmed'})
        self.assertIsNone(self.report()['reported_identity'])
    def test_wrong_work_or_version_cannot_inherit_request_identity(self):
        for ident in ['2601.00001v1','2601.00002v2','2601.00001']:
            self.spec['annotation']['paper_id']=ident;r=self.capture();self.assertNotEqual(r['issues'],[])
            self.assertEqual(self.report()['excerpts'][0]['reported_paper_id'],ident);shutil.rmtree(self.output)
    def test_plain_text_not_guessed_as_json(self):
        self.raw=self.body.encode();self.spec['response']['format']='text';self.spec['excerpts'][0]['text_pointer']='';self.capture()
        self.assertEqual(self.report()['excerpts'][0]['quote'],self.spec['excerpts'][0]['quote'])
    def test_escaped_json_pointer_and_root_scalar(self):
        self.raw=a.m.encoded({'a/b':{'~text':self.body}});self.spec['excerpts'][0]['text_pointer']='/a~1b/~0text';self.capture();shutil.rmtree(self.output)
        self.raw=a.m.encoded(self.body);self.spec['excerpts'][0]['text_pointer']='';self.capture()
        self.assertEqual(len(self.report()['excerpts']),1)
    def test_missing_nontext_pointer_and_array_index_refuse_citations(self):
        for ptr in ['/missing','/content','/content/01/text','/content/9999999/text']:
            self.spec['excerpts'][0]['text_pointer']=ptr;r=self.capture();self.assertIn('response_or_citation_invalid',r['issues']);self.assertEqual(self.report()['excerpts'],[]);shutil.rmtree(self.output)
    def test_partial_error_unknown_states_remain_non_success(self):
        for state in ('partial','error','unknown'):
            self.spec['response']['state']=state;r=self.capture();self.assertIn('response_'+state,r['issues']);shutil.rmtree(self.output)
    def test_invalid_payload_retained_and_replayable(self):
        for raw in [b'\xff',b'{"text":1,"text":2}',b'{broken']:
            self.raw=raw;r=self.capture();self.assertEqual((self.output/'response.raw').read_bytes(),raw)
            self.assertEqual(a.verify(self.output,r['manifest_sha256'])['status'],'content_requires_resolution');shutil.rmtree(self.output)
    def test_one_bad_quote_prevents_partial_citation_success(self):
        second=copy.deepcopy(self.spec['excerpts'][0]);second.update(id='bad',quote='Changed meaning')
        self.spec['excerpts'].append(second);self.capture();self.assertEqual(self.report()['excerpts'],[])
    def test_spec_rejects_bool_offsets_pages_and_unknown_fields(self):
        original=copy.deepcopy(self.spec)
        for field,value in [('start',True),('reported_page',True),('reported_page',0),('end',-1)]:
            self.spec=copy.deepcopy(original);self.spec['excerpts'][0][field]=value
            with self.assertRaises(ValueError):self.capture()
        self.spec=original;self.spec['accepted_into_knowledge_graph']=True
        with self.assertRaises(ValueError):self.capture()
    def test_explicit_versioned_allowlisted_url(self):
        for url in ['https://arxiv.org/abs/2601.00001','https://evil.example/abs/2601.00001v2','https://arxiv.org:443/abs/2601.00001v2','http://arxiv.org/abs/2601.00001v2','https://arxiv.org/abs/2601.00001v2?token=x']:
            with self.assertRaises(ValueError):a.requested_identity(url)
        self.assertEqual(a.requested_identity('https://arxiv.org/pdf/math/0309136v1.pdf')['version'],1)
        self.assertEqual(a.requested_identity('https://www.alphaxiv.org/abs/2601.00001v2')['work_id'],'2601.00001')
    def test_empty_excerpt_selection_explicit(self):
        self.spec['excerpts']=[];r=self.capture();self.assertIn('no_excerpts_selected',r['issues'])
    def test_relocation_without_network_or_original_files(self):
        r=self.capture();moved=self.root/'moved';shutil.move(self.output,moved)
        (self.root/'spec.json').unlink();(self.root/'response.raw').unlink()
        with patch.object(a.discovery,'fetch',side_effect=AssertionError('no network')):a.verify(moved,r['manifest_sha256'])
    def test_tamper_promotion_and_extra_files_rejected(self):
        self.capture();doc=self.report();doc['representation_verified']=True;(self.output/'content.json').write_bytes(a.m.encoded(doc))
        with self.assertRaises(ValueError):a.verify(self.output,self.reseal())
        shutil.rmtree(self.output);r=self.capture();(self.output/'extra').write_bytes(b'x')
        with self.assertRaises(ValueError):a.verify(self.output,r['manifest_sha256'])
    def test_input_anchor_size_and_output_preservation(self):
        self.capture()
        with self.assertRaises(FileExistsError):self.capture()
        with self.assertRaises(ValueError):a.verify(self.output,'0'*64)
        shutil.rmtree(self.output);self.raw=b'x'*(a.k.MAX_FILE+1)
        with self.assertRaises(ValueError):self.capture()
        self.assertFalse(self.output.exists())
    def test_symlink_rejected(self):
        r=self.capture();rp=self.root/'response.raw';(self.output/'response.raw').unlink();(self.output/'response.raw').symlink_to(rp)
        with self.assertRaises(ValueError):a.verify(self.output,r['manifest_sha256'])
    def test_cli_capture_replay_and_issue_exit(self):
        sp=self.root/'spec.json';rp=self.root/'raw';sp.write_bytes(a.m.encoded(self.spec));rp.write_bytes(self.raw)
        def cli(*args):return subprocess.run([sys.executable,'-B',a.__file__,*map(str,args)],capture_output=True,text=True)
        r=cli('import','--spec',sp,'--sha256',a.m.sha(sp.read_bytes()),'--response',rp,'--response-sha256',a.m.sha(self.raw),'--output',self.output)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);anchor=json.loads(r.stdout)['manifest_sha256']
        self.assertEqual(cli('verify','--bundle',self.output,'--sha256',anchor).returncode,0)
        shutil.rmtree(self.output);self.spec['annotation']['representation']='ai_report';r=self.capture()
        v=cli('verify','--bundle',self.output,'--sha256',r['manifest_sha256']);self.assertEqual(v.returncode,2);self.assertTrue(json.loads(v.stdout)['integrity_reproduced'])


if __name__=='__main__':unittest.main()
