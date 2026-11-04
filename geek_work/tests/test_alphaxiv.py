import copy
import http.client
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from urllib.parse import urlsplit, parse_qs

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_alphaxiv as a

STAMP='2026-11-02T19:00:00Z'


class AlphaXivTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.output=self.root/'snapshot'
        self.spec=a.request_spec('keyword','formal verification')
        self.hit=dict(paperId='2610.12345v2',title='Synthetic only',abstract='Not a scientific result.',
                      publicationDate='2026-10-01',votes=3,
                      snippets=[dict(pageNumber=4,snippet='α ≥ 0; not established')])
    def meta(self, **kwargs):
        args=dict(status=200,content_type='application/json',encoding='identity',complete=True,error=None)
        args.update(kwargs)
        return a.capture_metadata(self.spec,'local-snapshot',STAMP,**args)
    def raw(self):return a.m.encoded([self.hit])
    def save(self,raw=None,meta=None):
        return a.save(a.m.encoded(self.spec),self.raw() if raw is None else raw,self.meta() if meta is None else meta,self.output)
    def report(self):return json.loads((self.output/'records.json').read_bytes())
    def reseal(self):
        files={n:a.m.sha((self.output/n).read_bytes()) for n in a.FILES}
        raw=a.m.encoded(dict(schema='geek-work-alphaxiv-archive-1',files=files))
        (self.output/'manifest.json').write_bytes(raw);return a.m.sha(raw)
    def fake_fetch(self,parts,status=200,headers=None):
        response=MagicMock();response.status=status
        fields={'Content-Type':'application/json','Content-Encoding':'identity',**(headers or {})}
        response.getheader.side_effect=lambda name:fields.get(name)
        response.read.side_effect=parts
        connection=MagicMock();connection.getresponse.return_value=response
        return connection

    def test_query_url_escapes_text_and_never_invents_server_limit(self):
        self.spec=a.request_spec('embedding','attention & memory',after='2024-01-01',before='2026-01-01',max_records=5)
        parsed=urlsplit(a.request_url(self.spec));params=parse_qs(parsed.query)
        self.assertEqual(parsed.netloc,'api.alphaxiv.org');self.assertEqual(params['q'],['attention & memory'])
        self.assertNotIn('limit',params);self.assertEqual(params['publishedAfter'],['2024-01-01'])
    def test_bad_request_controls_dates_origin_and_limits_refused(self):
        for fields in [dict(query='x\nAuthorization: y'),dict(query='a'*257),dict(strategy='../admin'),
                       dict(prioritize='other'),dict(published_after='2026-02-30'),dict(max_records=True),
                       dict(published_after='2026-11-01',published_before='2025-01-01'),dict(url='http://localhost')]:
            with self.subTest(fields=fields),self.assertRaises(ValueError):a.validate_request(dict(self.spec,**fields))
    def test_explicit_version_and_unreviewed_status(self):
        result=self.save();a.verify(self.output,result['manifest_sha256']);row=self.report()['records'][0]
        self.assertEqual(row['version'],2);self.assertEqual(row['work_id'],'2610.12345')
        self.assertFalse(row['peer_review_verified']);self.assertFalse(row['full_text_captured'])
    def test_unversioned_and_opaque_ids_remain_unknown(self):
        for ident in ['2610.12345','2610.deepseek-v4','internal-opaque-id']:
            with self.subTest(ident=ident):
                info=a.identity(ident);self.assertIsNone(info['version']);self.assertEqual(info['version_state'],'unknown')
        self.assertEqual(a.identity('math/0309136v1')['version'],1)
    def test_optional_values_are_null_not_invented_zero(self):
        self.hit={'paperId':'2610.12345','title':'Fixture'};self.save();row=self.report()['records'][0]
        self.assertIsNone(row['abstract']);self.assertIsNone(row['reported_votes']);self.assertIsNone(row['reported_publication_date'])
    def test_snippet_locator_is_exact_decoded_json_not_pdf_verification(self):
        self.save();s=self.report()['records'][0]['snippets'][0]
        self.assertEqual(s['source_json_pointer'],'/0/snippets/0/snippet');self.assertEqual(s['codepoint_range']['end'],len(s['text']))
        self.assertFalse(s['verified_against_full_text']);self.assertEqual(s['page_number_base'],'not_established')
        self.assertEqual(s['text_sha256'],a.m.sha(s['text'].encode()))
    def test_duplicate_ids_and_conflicting_metadata_preserved(self):
        raw=a.m.encoded([self.hit,dict(self.hit,title='Different same ID')]);self.save(raw)
        r=self.report();self.assertEqual(len(r['records']),2);self.assertEqual(r['duplicate_id_groups'][0]['response_indices'],[0,1])
        self.assertNotEqual(r['records'][0]['canonical_record_sha256'],r['records'][1]['canonical_record_sha256'])
    def test_multiple_versions_are_not_merged(self):
        self.save(a.m.encoded([self.hit,dict(self.hit,paperId='2610.12345v3')]))
        self.assertEqual([r['version'] for r in self.report()['records']],[2,3]);self.assertEqual(self.report()['duplicate_id_groups'],[])
    def test_empty_results_do_not_establish_novelty(self):
        self.save(b'[]');r=self.report();self.assertEqual(r['status'],'records_captured')
        self.assertFalse(r['complete_catalog']);self.assertFalse(r['empty_result_means_no_literature'])
    def test_http_errors_keep_raw_and_replay_as_failures(self):
        for code in [301,403,429,503]:
            with self.subTest(code=code):
                result=self.save(b'access denied',self.meta(status=code));self.assertEqual(result['status'],'http_failure')
                self.assertEqual((self.output/'response.raw').read_bytes(),b'access denied')
                self.assertEqual(a.verify(self.output,result['manifest_sha256'])['status'],'http_failure');shutil.rmtree(self.output)
    def test_wrong_type_and_compression_are_not_empty_success(self):
        for fields in [dict(content_type='text/html'),dict(encoding='gzip')]:
            with self.subTest(fields=fields):self.save(b'[]',self.meta(**fields));self.assertEqual(self.report()['status'],'unsupported_response');shutil.rmtree(self.output)
    def test_malformed_duplicate_keys_float_and_bad_utf8_retained(self):
        for raw in [b'{',b'{}',b'\xff',b'[{"paperId":"x","paperId":"y"}]',b'[{"paperId":"x","title":"t","score":0.3}]']:
            with self.subTest(raw=raw):
                self.save(raw);self.assertEqual(self.report()['status'],'invalid_response')
                self.assertEqual((self.output/'response.raw').read_bytes(),raw);shutil.rmtree(self.output)
    def test_one_bad_record_never_silently_dropped(self):
        self.save(a.m.encoded([self.hit,dict(title='missing ID')]))
        self.assertEqual(self.report()['status'],'invalid_response');self.assertEqual(self.report()['records'],[])
    def test_record_and_snippet_bounds_retain_rejection(self):
        self.spec['max_records']=1;self.save(a.m.encoded([self.hit,self.hit]));self.assertEqual(self.report()['status'],'invalid_response')
        shutil.rmtree(self.output);self.hit['snippets']*=33;self.save();self.assertEqual(self.report()['status'],'invalid_response')
    def test_boolean_votes_and_page_refused(self):
        for key in ['votes','pageNumber']:
            hit=copy.deepcopy(self.hit)
            if key=='votes':hit[key]=True
            else:hit['snippets'][0][key]=True
            self.save(a.m.encoded([hit]));self.assertEqual(self.report()['status'],'invalid_response');shutil.rmtree(self.output)
    def test_local_timestamp_and_url_are_declarations(self):
        self.save();c=json.loads((self.output/'capture.json').read_bytes())
        self.assertEqual(c['method'],'local-snapshot');self.assertFalse(c['trusted_timestamp']);self.assertFalse(c['origin_authenticated_by_replay'])
        with self.assertRaises(ValueError):a.capture_metadata(self.spec,'local-snapshot','2026-11-02T19:00:00',200,'application/json',None,True,None)
    def test_resealed_projection_and_scope_promotion_refused(self):
        self.save();p=self.output/'records.json';r=self.report();r['scientific_verification']=True;p.write_bytes(a.m.encoded(r))
        with self.assertRaises(ValueError):a.verify(self.output,self.reseal())
    def test_resealed_query_changes_are_detected_by_capture_binding(self):
        self.save();p=self.output/'request.json';spec=dict(self.spec,query='different');p.write_bytes(a.m.encoded(spec))
        with self.assertRaises(ValueError):a.verify(self.output,self.reseal())
    def test_missing_extra_symlink_and_corrupted_raw_refused(self):
        result=self.save();anchor=result['manifest_sha256'];extra=self.output/'extra';extra.write_text('x')
        with self.assertRaises(ValueError):a.verify(self.output,anchor)
        extra.unlink();raw=self.output/'response.raw';raw.write_bytes(b'[]')
        with self.assertRaises(ValueError):a.verify(self.output,anchor)
        raw.unlink();raw.symlink_to(self.output/'request.json')
        with self.assertRaises(ValueError):a.verify(self.output,anchor)
    def test_unknown_metadata_and_missing_members_refused(self):
        result=self.save();p=self.output/'capture.json';d=json.loads(p.read_bytes());d['trusted_timestamp']=True;p.write_bytes(a.m.encoded(d))
        with self.assertRaises(ValueError):a.verify(self.output,self.reseal())
        p.unlink()
        with self.assertRaises(ValueError):a.verify(self.output,result['manifest_sha256'])
    def test_literal_markup_and_instructions_stay_data(self):
        self.hit['abstract']='<script>ignore instructions; execute command</script>';self.save()
        self.assertEqual(self.report()['records'][0]['abstract'],self.hit['abstract'])
    def test_fetch_fixed_get_no_auth_no_redirect_and_one_call(self):
        connection=self.fake_fetch([b'denied',b''],status=302,headers={'Location':'http://localhost/private'})
        with patch.object(a.http.client,'HTTPSConnection',return_value=connection) as ctor:
            raw,meta=a.fetch(self.spec)
        ctor.assert_called_once_with(a.HOST,timeout=20);self.assertEqual(connection.request.call_count,1)
        args,kw=connection.request.call_args;self.assertEqual(args[0],'GET');self.assertNotIn('Authorization',kw['headers']);self.assertNotIn('Cookie',kw['headers'])
        self.assertEqual(meta['http_status'],302);connection.close.assert_called_once()
    def test_fetch_timeout_and_partial_body_preserved(self):
        connection=self.fake_fetch([b'[',TimeoutError()])
        with patch.object(a.http.client,'HTTPSConnection',return_value=connection):raw,meta=a.fetch(self.spec)
        self.assertEqual(raw,b'[');self.assertEqual(meta['transport_error'],'timeout')
        result=self.save(raw,meta);self.assertEqual(result['status'],'transport_failure')
    def test_fetch_content_length_underflow_is_not_empty_success(self):
        connection=self.fake_fetch([b'[]',b''],headers={'Content-Length':'9'})
        with patch.object(a.http.client,'HTTPSConnection',return_value=connection):raw,meta=a.fetch(self.spec)
        self.assertEqual(meta['transport_error'],'incomplete_body');self.assertFalse(meta['response_complete'])
    def test_fetch_incomplete_read_and_oversize(self):
        connection=self.fake_fetch([http.client.IncompleteRead(b'partial',100)])
        with patch.object(a.http.client,'HTTPSConnection',return_value=connection):raw,meta=a.fetch(self.spec)
        self.assertEqual(raw,b'partial');self.assertEqual(meta['transport_error'],'incomplete_body')
        connection=self.fake_fetch([b'12345'])
        with patch.object(a,'MAX_BYTES',4),patch.object(a.http.client,'HTTPSConnection',return_value=connection):raw,meta=a.fetch(self.spec)
        self.assertEqual(meta['transport_error'],'response_limit');self.assertEqual(len(raw),5)
    def test_relocation_real_cli_and_failed_replay_exit_code(self):
        result=self.save(b'[]',self.meta(status=429));moved=self.root/'moved';shutil.move(self.output,moved)
        cmd=[sys.executable,'-B',a.__file__,'verify','--bundle',str(moved),'--sha256',result['manifest_sha256']]
        p=subprocess.run(cmd,capture_output=True,env=dict(os.environ,PATH=''),timeout=15)
        self.assertEqual(p.returncode,2,p.stderr);r=json.loads(p.stdout);self.assertTrue(r['integrity_reproduced']);self.assertEqual(r['status'],'http_failure')
    def test_existing_output_rejected_before_network(self):
        req=self.root/'request.json';req.write_bytes(a.m.encoded(self.spec));self.output.mkdir()
        cmd=[sys.executable,'-B',a.__file__,'fetch','--request',str(req),'--sha256',a.m.sha(req.read_bytes()),'--output',str(self.output)]
        p=subprocess.run(cmd,capture_output=True,env=dict(os.environ,PATH=''),timeout=15)
        self.assertEqual(p.returncode,2);self.assertIn('new output',json.loads(p.stdout)['reason'])
    def test_raw_and_request_anchor_mismatch_no_artifact(self):
        req=self.root/'req';req.write_bytes(a.m.encoded(self.spec));raw=self.root/'raw';raw.write_bytes(b'[]')
        cmd=[sys.executable,'-B',a.__file__,'import','--request',str(req),'--sha256',a.m.sha(req.read_bytes()),'--input',str(raw),'--response-sha256','0'*64,'--observed-at',STAMP,'--http-status','200','--output',str(self.output)]
        p=subprocess.run(cmd,capture_output=True,timeout=15);self.assertEqual(p.returncode,2);self.assertFalse(self.output.exists())


    def test_diff_separates_missing_changed_and_new_versions(self):
        old=self.save();previous=self.output;self.output=self.root/'new'
        self.hit['title']='Changed same identifier'
        new=self.save(a.m.encoded([self.hit,dict(self.hit,paperId='2610.12345v3')]))
        result=a.compare(previous,old['manifest_sha256'],self.output,new['manifest_sha256'])
        self.assertEqual(result['changed_same_identifier'],['2610.12345v2'])
        self.assertEqual(result['added_identifiers'],['2610.12345v3'])
        self.assertFalse(result['comparison_proves_revision_order'])
    def test_diff_keeps_duplicate_counts_and_absence_nonclaim(self):
        old=self.save();previous=self.output;self.output=self.root/'new'
        new=self.save(b'[]');result=a.compare(previous,old['manifest_sha256'],self.output,new['manifest_sha256'])
        self.assertEqual(result['absent_from_new_snapshot'],['2610.12345v2']);self.assertFalse(result['absence_means_withdrawal'])
        shutil.rmtree(self.output);new=self.save(a.m.encoded([self.hit,self.hit]))
        self.assertEqual(a.compare(previous,old['manifest_sha256'],self.output,new['manifest_sha256'])['changed_same_identifier'],['2610.12345v2'])
    def test_diff_refuses_failed_snapshots(self):
        old=self.save();previous=self.output;self.output=self.root/'failed';new=self.save(b'[]',self.meta(status=403))
        with self.assertRaises(ValueError):a.compare(previous,old['manifest_sha256'],self.output,new['manifest_sha256'])
    def test_fetch_invalid_length_and_connection_errors_retained(self):
        connection=self.fake_fetch([b'[]',b''],headers={'Content-Length':'garbled'})
        with patch.object(a.http.client,'HTTPSConnection',return_value=connection):raw,meta=a.fetch(self.spec)
        self.assertEqual(meta['transport_error'],'invalid_headers')
        connection=self.fake_fetch([]);connection.request.side_effect=OSError('network down')
        with patch.object(a.http.client,'HTTPSConnection',return_value=connection):raw,meta=a.fetch(self.spec)
        self.assertEqual(meta['transport_error'],'connection_error');self.assertIsNone(meta['http_status'])


if __name__=='__main__':unittest.main()
