import base64
import copy
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'tools'))
import geek_work_claim_api_harness as h
import geek_work_claim_adapter as adapter

U=lambda n:f'00000000-0000-4000-8000-{n:012d}'
TOKEN=base64.urlsafe_b64encode(b'x'*32).decode().rstrip('=')
HEADERS=[('Content-Type','application/json'),('Cache-Control','no-store')]


def envelope(request,data=None,error=None):
    r=dict(schema='claim-review-api-response-1',operation=request['operation'],request_id=request['request_id'],context_id=request['context_id'],ok=error is None,assurances={f:False for f in h.FLAGS})
    if error:r['error']=dict(code=error,message='Controlled test error.',retry_after_seconds=None)
    else:r['data']=data
    return r


class HarnessTests(unittest.TestCase):
    def setUp(self):self.client=h.Harness(12345,TOKEN,U(2))

    def sample(self,name):return json.loads((h.CONTRACT/'examples'/name).read_bytes())

    def context_reply(self,request):return envelope(request,self.sample('context.response.json')['data'])

    def test_only_loopback_port_and_uuid_are_configurable(self):
        for port in (0,65536,True,'https://example.com'):
            with self.subTest(port=port),self.assertRaises(ValueError):h.Harness(port,TOKEN,U(2))
        with self.assertRaises(ValueError):h.Harness(12345,TOKEN,'../context')
        self.assertEqual(self.client.origin,'http://127.0.0.1:12345')

    def test_token_file_canonical_and_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'token';p.write_text(TOKEN+'\n');self.assertEqual(h.read_token(p),TOKEN)
            (Path(d)/'link').symlink_to(p)
            with self.assertRaises(ValueError):h.read_token(Path(d)/'link')
            for value in ('abc',TOKEN+' ',TOKEN+'='):
                p.write_text(value)
                with self.assertRaises(ValueError):h.read_token(p)

    def test_base64_canonical(self):
        self.assertEqual(h.decode('Zg=='),b'f')
        for value in ('Zh==','Zg==\n','!','Zg'):
            with self.subTest(value=value),self.assertRaises(ValueError):h.decode(value)

    def test_valid_context_envelope(self):
        request=self.client.request('context');body=self.context_reply(request)
        self.assertEqual(self.client.validate(200,HEADERS,h.m.encoded(body),request,200,None),body)

    def test_response_schema_and_all_false_flags(self):
        request=self.client.request('context');body=self.context_reply(request)
        for flag in h.FLAGS:
            changed=copy.deepcopy(body);changed['assurances'][flag]=True
            with self.subTest(flag=flag),self.assertRaises(ValueError):self.client.validate(200,HEADERS,h.m.encoded(changed),request,200,None)
        body['extra']='unrecognized'
        with self.assertRaises(ValueError):self.client.validate(200,HEADERS,h.m.encoded(body),request,200,None)

    def test_http_and_error_code_pair(self):
        request=self.client.request('context');body=envelope(request,error='unauthorized')
        self.client.validate(401,HEADERS,h.m.encoded(body),request,401,'unauthorized')
        with self.assertRaises(ValueError):self.client.validate(403,HEADERS,h.m.encoded(body),request,403,'unauthorized')

    def test_missing_or_duplicate_cache_control(self):
        req=self.client.request('context');raw=h.m.encoded(self.context_reply(req))
        for headers in (HEADERS[:1],HEADERS+[('Cache-Control','no-store')]):
            with self.assertRaises(ValueError):self.client.validate(200,headers,raw,req,200,None)

    def test_response_request_binding(self):
        req=self.client.request('context');body=self.context_reply(req);body['request_id']=U(99)
        with self.assertRaisesRegex(ValueError,'response_binding_mismatch'):self.client.validate(200,HEADERS,h.m.encoded(body),req,200,None)

    def test_error_can_omit_untrusted_request_identity(self):
        req=self.client.request('context');body=envelope(req,error='malformed_request')
        for k in ('operation','request_id','context_id'):body[k]=None
        self.client.validate(400,HEADERS,h.m.encoded(body),req,400,'malformed_request')

    def test_no_redirect_is_accepted(self):
        req=self.client.request('context')
        with self.assertRaisesRegex(ValueError,'unexpected_http_status'):self.client.validate(302,HEADERS,b'{}',req,200,None)

    def test_receipt_does_not_include_raw_response_or_token(self):
        req=self.client.request('context');raw=h.m.encoded(self.context_reply(req))
        with patch.object(self.client,'wire',return_value=(200,HEADERS,raw)):self.client.send('context',req)
        receipt=self.client.receipt('probe',True)
        text=json.dumps(receipt);self.assertNotIn(TOKEN,text);self.assertNotIn(raw.decode(),text)
        self.assertIn('CLI_timeout_and_process_cleanup',receipt['untested'])
        self.assertTrue(all(receipt[f] is False for f in h.FLAGS))

    def test_context_anchor_equality_not_only_schema(self):
        data=self.sample('context.response.json')['data'];data['anchors']['source']['observed_sha256']='1'*64
        with patch.object(self.client,'send',return_value={'data':data}),self.assertRaisesRegex(ValueError,'anchors_not_matched'):self.client.context()

    def test_limits_mismatch(self):
        data=self.sample('context.response.json')['data'];data['limits']['build_timeout_seconds']=1
        with patch.object(self.client,'send',return_value={'data':data}),self.assertRaisesRegex(ValueError,'limits_mismatch'):self.client.context()

    def chunks(self,raw):
        ref=dict(artifact_id=U(20),sha256=h.m.sha(raw),size_bytes=len(raw),media_type='text/plain')
        def send(name,req,*args,**kwargs):
            offset=req['offset'];chunk=raw[offset:offset+req['max_bytes']]
            return {'data':dict(artifact_id=ref['artifact_id'],artifact_sha256=ref['sha256'],total_size_bytes=len(raw),offset=offset,returned_bytes=len(chunk),eof=offset+len(chunk)==len(raw),chunk_base64=base64.b64encode(chunk).decode())}
        return ref,send

    def test_chunks_preserve_split_emoji_and_crlf(self):
        raw=b'a'*65535+'😀\r\nא\u05b0'.encode()
        ref,send=self.chunks(raw)
        with patch.object(self.client,'send',side_effect=send):self.assertEqual(self.client.read_artifact(ref),raw)

    def test_empty_artifact(self):
        ref,send=self.chunks(b'')
        with patch.object(self.client,'send',side_effect=send):self.assertEqual(self.client.read_artifact(ref),b'')

    def test_chunk_hash_failure(self):
        ref,send=self.chunks(b'abc');ref['sha256']='0'*64
        with patch.object(self.client,'send',side_effect=send),self.assertRaisesRegex(ValueError,'artifact_hash_mismatch'):self.client.read_artifact(ref)

    def test_chunk_offset_failure(self):
        ref,send=self.chunks(b'abc')
        def bad(*args,**kw):
            r=send(*args,**kw);r['data']['offset']=1;return r
        with patch.object(self.client,'send',side_effect=bad),self.assertRaisesRegex(ValueError,'artifact_range_mismatch'):self.client.read_artifact(ref)

    def test_false_eof_or_empty_nonfinal_chunk(self):
        ref,send=self.chunks(b'abc')
        def bad(*args,**kw):
            r=send(*args,**kw);r['data'].update(returned_bytes=0,eof=False,chunk_base64='');return r
        with patch.object(self.client,'send',side_effect=bad),self.assertRaisesRegex(ValueError,'empty_nonfinal_chunk'):self.client.read_artifact(ref)

    def test_poll_does_not_accept_other_draft(self):
        accepted=dict(job_id=U(4),draft_id=U(3),draft_sha256='0'*64,context_fingerprint='0'*64)
        job=self.sample('job-built.response.json')['data'];job['draft_id']=U(99)
        with patch.object(self.client,'send',return_value={'data':job}),self.assertRaisesRegex(ValueError,'job_binding_mismatch'):self.client.poll(accepted,'build')

    def test_poll_running_to_queued_rejected(self):
        accepted=dict(job_id=U(4),draft_id=U(3),draft_sha256='0'*64,context_fingerprint='0'*64)
        values=[{'data':self.sample('job-running.response.json')['data']},{'data':self.sample('job-queued.response.json')['data']}]
        with patch.object(self.client,'send',side_effect=values),patch.object(h.time,'sleep'),self.assertRaisesRegex(ValueError,'job_state_regression'):self.client.poll(accepted,'build')

    def test_failed_job_is_not_successful_validation(self):
        accepted=dict(job_id=U(4),draft_id=U(3),draft_sha256='0'*64,context_fingerprint='0'*64)
        with patch.object(self.client,'send',return_value={'data':self.sample('job-failed.response.json')['data']}):
            self.assertEqual(self.client.poll(accepted,'build')['state'],'failed')

    def test_wire_limit_before_connect(self):
        with patch.object(h.http.client,'HTTPConnection') as connection,self.assertRaisesRegex(ValueError,'request_too_large'):
            self.client.wire('context',b'x'*(2097152+1))
        connection.assert_not_called()

    def test_exclusive_output_before_network(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'existing.json';out.write_bytes(b'preserve')
            result=subprocess.run([sys.executable,str(Path(h.__file__)),'--port','1','--token-file',str(Path(d)/'missing'),
                '--context-id',U(2),'--output',str(out)],capture_output=True,timeout=10)
            self.assertNotEqual(result.returncode,0);self.assertEqual(out.read_bytes(),b'preserve')

    def test_report_other_draft_rejected(self):
        body=dict(schema='geek-work-claim-extraction-report-1',status='record_consistent',record_sha256='1'*64,**{f:False for f in h.FLAGS})
        with self.assertRaisesRegex(ValueError,'report_draft_binding_mismatch'):
            self.client.validate_report('extraction',body,{'status':'record_consistent'},{},'0'*64)

    def test_report_identifier_rejected(self):
        with self.assertRaisesRegex(ValueError,'report_schema_identifier_mismatch'):
            self.client.validate_report('adapter',{'status':'built'},{'status':'built'},{},'0'*64)

    def workflow_model(self,mode):
        # In-memory model solely for testing the client's workflow logic, not server acceptance.
        brain=Path(h.__file__).resolve().parents[1]
        ready=brain/'examples/claim-adapter-ready'
        if mode=='ready':
            record=(ready/'record.json').read_bytes();pins=json.loads((ready/'pins.json').read_bytes())
            raw_reports={kind:(ready/'expected-package'/(kind+'-report.json')).read_bytes() for kind in ('extraction','adapter','transport')}
        else:
            orbit=brain/'examples/claim-extraction-orbit';record=(orbit/'orbit-needs-context.json').read_bytes()
            pins=json.loads((orbit/'pins.json').read_bytes());pins['claim_map_bundle_sha256']='022bbbc4659daa6cb249aed9bdb8dc8a90c85f7fb9bd828ab53964458398281b'
            bundle=brain/'examples/claim-transport-orbit/source-bundle'
            generated=adapter.build((bundle/'material-lean-source.txt').read_bytes(),pins['source_sha256'],
                (orbit/'expectations.json').read_bytes(),pins['expectations_sha256'],record,
                bundle,pins['claim_map_bundle_sha256'],'subcritical-orbit-limit',1)
            raw_reports={'extraction':(orbit/'orbit-needs-context.report.json').read_bytes(),
                         'adapter':generated['adapter-report.json']}
        context=self.sample('context.response.json')['data']
        for key,pin in [('source','source_sha256'),('expectations','expectations_sha256'),('claim_map_manifest','claim_map_bundle_sha256')]:
            context['anchors'][key]=dict(state='matched',expected_sha256=pins[pin],observed_sha256=pins[pin])
        blobs={};summaries={}
        for n,(kind,raw) in enumerate(raw_reports.items(),30):
            ref=dict(artifact_id=U(n),sha256=h.m.sha(raw),size_bytes=len(raw),media_type='application/json')
            blobs[U(n)]=raw;summaries[kind]=dict(validator=kind,status=json.loads(raw)['status'],reason=json.loads(raw).get('reason'),artifact=ref)
        cache={};jobs={}
        def wire(op,raw,*args):
            req=json.loads(raw);key=(op,req['request_id']);status=200
            if op in ('drafts','checks','builds') and key in cache:
                old,code,body=cache[key]
                if old==raw:return code,HEADERS,h.m.encoded(body)
                return 409,HEADERS,h.m.encoded(envelope(req,error='idempotency_conflict'))
            if op=='drafts':
                status=201;body=envelope(req,dict(draft_id=U(3),parent_draft_id=None,draft_sha256=h.m.sha(record),size_bytes=len(record),validation_state='not_run'))
            elif op in ('checks','builds'):
                if req['draft_sha256']!=h.m.sha(record):return 409,HEADERS,h.m.encoded(envelope(req,error='draft_hash_mismatch'))
                kind='check' if op=='checks' else 'build';job_id=U(4 if kind=='check' else 5)
                data=dict(job_id=job_id,kind=kind,draft_id=U(3),draft_sha256=h.m.sha(record),context_fingerprint=context['context_fingerprint'])
                status=202;body=envelope(req,data)
                reports=[summaries['extraction']] if kind=='check' else list(summaries.values())
                jobs[job_id]=dict(**data,state='completed',exit_code=0 if mode=='ready' else 1,reports=reports,failure=None,artifacts=[r['artifact'] for r in reports],package_available=kind=='build' and mode=='ready')
            elif op=='jobs/status':body=envelope(req,jobs[req['job_id']])
            elif op=='artifacts/read':
                blob=blobs[req['artifact_id']];chunk=blob[req['offset']:req['offset']+req['max_bytes']]
                body=envelope(req,dict(artifact_id=req['artifact_id'],artifact_sha256=h.m.sha(blob),total_size_bytes=len(blob),offset=req['offset'],returned_bytes=len(chunk),eof=req['offset']+len(chunk)==len(blob),chunk_base64=base64.b64encode(chunk).decode()))
            else:raise AssertionError(op)
            if op in ('drafts','checks','builds'):cache[key]=(raw,status,body)
            return status,HEADERS,h.m.encoded(body)
        with patch.object(self.client,'wire',side_effect=wire):self.client.workflow(context,record,mode)
        self.assertIn(mode+'_build_live_result_and_reports',self.client.completed_scenarios)
        self.assertEqual(len(jobs),2)

    def test_ready_workflow_client_with_in_memory_model(self):self.workflow_model('ready')

    def test_orbit_workflow_client_with_in_memory_model(self):self.workflow_model('orbit')

    def test_real_http_client_against_controlled_stub_only(self):
        # Transport smoke self-test. This stub is NOT a Claim Review server.
        observed=[]
        outer=self
        class Stub(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                raw=self.rfile.read(int(self.headers['Content-Length']));req=json.loads(raw)
                observed.append((self.path,self.headers.get_all('Host'),self.headers['Authorization'],raw))
                body=h.m.encoded(outer.context_reply(req))
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',0),Stub)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            client=h.Harness(server.server_port,TOKEN,U(2));req=client.request('context')
            client.send('transport_smoke',req)
            self.assertEqual(observed[0][0],'/v1/context');self.assertEqual(observed[0][1],[client.host])
            self.assertEqual(observed[0][2],'Bearer '+TOKEN);self.assertEqual(observed[0][3],h.m.encoded(req))
        finally:server.shutdown();server.server_close();thread.join(timeout=2)


if __name__=='__main__':unittest.main()
