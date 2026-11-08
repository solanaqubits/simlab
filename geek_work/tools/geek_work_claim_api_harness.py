#!/usr/bin/env python3
"""Contract probes for an explicitly supplied loopback Claim Review API.

This is a test client, not the API server. Uses jsonschema as a developer dependency.
No source/ledger mutation, process injection, public network access or CLI execution.
"""
import argparse
import base64
import hashlib
import http.client
import json
from pathlib import Path
import re
import time
import uuid

from jsonschema import Draft202012Validator
import geek_work_manuscript as m
from geek_work_claim_extraction import FLAGS
from knowledge import strict_json

CONTRACT=Path(__file__).resolve().parents[1]/'contracts/claim-review-api'
MAX_RESPONSE=2*1024*1024
UUID=re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z')
ERROR_HTTP={400:{'malformed_request','invalid_schema','noncanonical_base64','invalid_record_json'},
    401:{'unauthorized'},403:{'origin_host_rejected'},404:{'unknown_route','unknown_context','unknown_draft','unknown_job','unknown_artifact'},
    405:{'method_not_allowed'},408:{'request_timeout'},409:{'draft_hash_mismatch','context_fingerprint_mismatch','anchor_mismatch','anchor_unavailable','context_busy','idempotency_conflict','artifact_unavailable','artifact_integrity_failure'},
    413:{'payload_too_large'},415:{'unsupported_media_type'},416:{'range_not_satisfiable'},429:{'rate_limited'},507:{'quota_exceeded'},500:{'internal_error'}}


def require(ok,code):
    if not ok:raise ValueError(code)


def decode(value):
    try:
        raw=base64.b64decode(value,validate=True)
    except (ValueError,TypeError) as error:raise ValueError('invalid_base64') from error
    require(base64.b64encode(raw).decode()==value,'noncanonical_base64')
    return raw


def read_token(path):
    value=m.read(path,64).decode('ascii').strip('\r\n')
    require(bool(re.fullmatch(r'[A-Za-z0-9_-]{43}',value)),'invalid_token_file')
    raw=base64.urlsafe_b64decode(value+'=')
    require(len(raw)==32 and base64.urlsafe_b64encode(raw).decode().rstrip('=')==value,'invalid_token_file')
    return value


class Harness:
    def __init__(self,port,token,context_id):
        require(type(port) is int and 1<=port<=65535,'invalid_port')
        require(type(context_id) is str and UUID.fullmatch(context_id),'invalid_context_id')
        require(bool(re.fullmatch(r'[A-Za-z0-9_-]{43}',token)),'invalid_token')
        self.port=port;self.token=token;self.context_id=context_id
        self.host=f'127.0.0.1:{port}';self.origin='http://'+self.host
        self.validator=Draft202012Validator(json.loads((CONTRACT/'response.schema.json').read_bytes()))
        self.limits=json.loads((CONTRACT/'limits.json').read_bytes())
        self.next_request=0.;self.cases=[];self.completed_scenarios=[]

    def request(self,operation,**fields):
        return dict(schema='claim-review-api-request-1',operation=operation,
                    request_id=str(uuid.uuid4()),context_id=self.context_id,**fields)

    def wire(self,operation,raw,headers=None,extra_headers=()):
        # Literal address: no remote URL, DNS, proxy, redirects or credentials in query.
        require(operation in {'context','drafts','checks','builds','jobs/status','artifacts/read'},'unsupported_operation')
        require(len(raw)<=self.limits['post_body_bytes'],'request_too_large')
        time.sleep(max(0,self.next_request-time.monotonic()))
        self.next_request=time.monotonic()+0.15  # below the specified 8 RPS
        default={'Host':self.host,'Origin':self.origin,'Authorization':'Bearer '+self.token,
                 'Content-Type':'application/json','Content-Length':str(len(raw))}
        for key,value in (headers or {}).items():
            if value is None:default.pop(key,None)
            else:default[key]=value
        connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=10)
        try:
            connection.putrequest('POST','/v1/'+operation,skip_host=True,skip_accept_encoding=True)
            for key,value in [*default.items(),*extra_headers]:connection.putheader(key,value)
            connection.endheaders(raw)
            response=connection.getresponse()
            body=response.read(MAX_RESPONSE+1)
            require(len(body)<=MAX_RESPONSE,'response_too_large')
            return response.status,response.getheaders(),body
        finally:connection.close()

    def validate(self,status,headers,raw,request,expected_http,expected_error):
        require(status==expected_http,'unexpected_http_status')
        values={}
        for key,value in headers:values.setdefault(key.lower(),[]).append(value)
        require(values.get('cache-control')==['no-store'],'missing_no_store')
        content=values.get('content-type',[])
        require(len(content)==1 and content[0].lower() in ('application/json','application/json; charset=utf-8'),'invalid_response_content_type')
        body=strict_json(raw)
        require(self.validator.is_valid(body),'response_schema_mismatch')
        require(all(body['assurances'][f] is False for f in FLAGS),'assurance_promotion')
        for key in ('operation','request_id','context_id'):
            require(body[key]==request[key] or (not body['ok'] and body[key] is None),'response_binding_mismatch')
        if expected_error:
            require(not body['ok'] and body['error']['code']==expected_error,'wrong_error_code')
            require(expected_error in ERROR_HTTP.get(status,set()),'error_http_mismatch')
        else:require(body['ok'],'unexpected_error_response')
        return body

    def send(self,name,request,expected_http=200,expected_error=None,raw=None,headers=None,extra_headers=()):
        encoded=m.encoded(request) if raw is None else raw
        status,hs,body=self.wire(request['operation'],encoded,headers,extra_headers)
        # No bodies, Authorization values, source text or server error messages in receipts.
        entry=dict(name=name,http_status=status,response_sha256=hashlib.sha256(body).hexdigest(),passed=False)
        self.cases.append(entry)
        result=self.validate(status,hs,body,request,expected_http,expected_error)
        entry['passed']=True
        return result

    def context(self):
        data=self.send('context',self.request('context'))['data']
        require(data['limits']==self.limits,'limits_mismatch')
        for row in data['anchors'].values():
            require(row['state']=='matched' and row['expected_sha256']==row['observed_sha256'],'anchors_not_matched')
        self.completed_scenarios.append('context_anchors_and_limits')
        return data

    def probe(self):
        context=self.context()
        wrong=('A' if self.token[0]!='A' else 'B')+self.token[1:]
        for name,headers,code,error in [
            ('missing_token',{'Authorization':None},401,'unauthorized'),
            ('wrong_token',{'Authorization':'Bearer '+wrong},401,'unauthorized'),
            ('wrong_origin',{'Origin':'http://example.invalid'},403,'origin_host_rejected'),
            ('null_origin',{'Origin':'null'},403,'origin_host_rejected'),
            ('missing_origin',{'Origin':None},403,'origin_host_rejected'),
            ('wrong_host',{'Host':'localhost:'+str(self.port)},403,'origin_host_rejected'),
        ]:self.send(name,self.request('context'),code,error,headers=headers)
        for key,value in [('Host',self.host),('Origin',self.origin),('Authorization','Bearer '+wrong),('Content-Length','0')]:
            self.send('duplicate_'+key.lower(),self.request('context'),400,'malformed_request',extra_headers=[(key,value)])
        self.send('transfer_encoding',self.request('context'),400,'malformed_request',extra_headers=[('Transfer-Encoding','chunked')])
        self.send('compressed_body',self.request('context'),415,'unsupported_media_type',extra_headers=[('Content-Encoding','gzip')])
        request=self.request('context');request['path']='../outside'
        self.send('path_field',request,400,'invalid_schema')
        self.send('malformed_json',self.request('context'),400,'malformed_request',raw=b'{')
        self.completed_scenarios.append('auth_headers_and_request_rejections')
        raw=self.read_artifact(context['source_snapshot'])
        require(len(raw)==context['source_snapshot']['size_bytes'],'source_size_mismatch')
        self.completed_scenarios.append('source_chunk_read_and_hash')
        return context

    def read_artifact(self,ref):
        result=bytearray();offset=0
        require(0<=ref['size_bytes']<=self.limits['output_file_bytes'],'artifact_size_out_of_bounds')
        for _ in range(self.limits['output_file_bytes']//self.limits['artifact_chunk_bytes']+1):
            request=self.request('artifacts/read',artifact_id=ref['artifact_id'],artifact_sha256=ref['sha256'],offset=offset,max_bytes=65536)
            data=self.send('artifact_chunk',request)['data']
            require(data['artifact_id']==ref['artifact_id'] and data['artifact_sha256']==ref['sha256'],'artifact_binding_mismatch')
            require(data['total_size_bytes']==ref['size_bytes'] and data['offset']==offset,'artifact_range_mismatch')
            chunk=decode(data['chunk_base64'])
            require(len(chunk)==data['returned_bytes'] and len(chunk)<=65536,'chunk_size_mismatch')
            result.extend(chunk);offset+=len(chunk)
            require(offset<=ref['size_bytes'] and data['eof']==(offset==ref['size_bytes']),'invalid_eof')
            if data['eof']:
                require(hashlib.sha256(result).hexdigest()==ref['sha256'],'artifact_hash_mismatch')
                return bytes(result)
            require(bool(chunk),'empty_nonfinal_chunk')
        raise ValueError('artifact_chunk_limit')

    def poll(self,accepted,kind):
        deadline=time.monotonic()+self.limits['job_start_seconds']+self.limits['build_timeout_seconds' if kind=='build' else 'check_timeout_seconds']+10
        previous=None
        while time.monotonic()<deadline:
            job=self.send('poll_'+kind,self.request('jobs/status',job_id=accepted['job_id']))['data']
            for key in ('job_id','draft_id','draft_sha256','context_fingerprint'):
                require(job[key]==accepted[key],'job_binding_mismatch')
            require(job['kind']==kind,'job_kind_mismatch')
            require(not (previous=='running' and job['state']=='queued'),'job_state_regression')
            previous=job['state']
            if job['state'] in ('completed','failed'):return job
            time.sleep(0.5)
        raise ValueError('poll_deadline_exceeded')

    def validate_report(self,name,body,summary,context,draft_sha):
        schemas={'extraction':'geek-work-claim-extraction-report-1',
                 'adapter':'geek-work-claim-adapter-report-1',
                 'transport':'geek-work-claim-transport-report-1'}
        require(type(body) is dict and body.get('schema')==schemas[name],'report_schema_identifier_mismatch')
        require(all(body.get(f) is False for f in FLAGS),'report_assurance_promotion')
        require(body.get('status')==summary['status'],'summary_report_mismatch')
        if name=='extraction' or (name=='adapter' and body['status']=='built'):
            require(body.get('record_sha256')==draft_sha,'report_draft_binding_mismatch')
            for key,anchor in [('source_sha256','source'),('expectations_sha256','expectations')]:
                require(body.get(key)==context['anchors'][anchor]['expected_sha256'],'report_anchor_binding_mismatch')
        if name=='transport' or (name=='adapter' and body['status']=='built'):
            key='source_bundle_sha256' if name=='transport' else 'claim_map_bundle_sha256'
            require(body.get(key)==context['anchors']['claim_map_manifest']['expected_sha256'],'report_bundle_binding_mismatch')

    def workflow(self,context,record_raw,mode):
        require(mode in ('ready','orbit'),'unknown_workflow')
        require(len(record_raw)<=self.limits['record_bytes'],'record_too_large')
        draft_request=self.request('drafts',parent_draft_id=None,record_sha256=m.sha(record_raw),record_base64=base64.b64encode(record_raw).decode())
        saved=self.send('save_draft',draft_request,201)['data']
        require(saved['draft_sha256']==m.sha(record_raw) and saved['size_bytes']==len(record_raw),'saved_draft_mismatch')
        repeat=self.send('repeat_draft',draft_request,201)['data']
        require(repeat==saved,'idempotent_draft_mismatch')
        conflict=dict(draft_request,record_base64=base64.b64encode(record_raw+b' ').decode(),record_sha256=m.sha(record_raw+b' '))
        self.send('draft_idempotency_conflict',conflict,409,'idempotency_conflict')
        fields=dict(draft_id=saved['draft_id'],draft_sha256=saved['draft_sha256'],context_fingerprint=context['context_fingerprint'])
        self.send('stale_draft_hash',self.request('checks',**dict(fields,draft_sha256='0'*64)),409,'draft_hash_mismatch')
        for operation,kind in [('checks','check'),('builds','build')]:
            request=self.request(operation,**fields)
            accepted=self.send('start_'+kind,request,202)['data']
            for key,value in fields.items():require(accepted[key]==value,'accepted_binding_mismatch')
            require(accepted['kind']==kind,'accepted_kind_mismatch')
            repeated=self.send('repeat_'+kind,request,202)['data']
            require(repeated==accepted,'idempotent_job_mismatch')
            job=self.poll(accepted,kind)
            require(job['state']=='completed','unexpected_job_failure')
            reports={r['validator']:r for r in job['reports']}
            expected=('record_consistent' if mode=='ready' else 'needs_context') if kind=='check' else ('built' if mode=='ready' else 'build_blocked')
            target='extraction' if kind=='check' else 'adapter'
            require(reports[target]['status']==expected,'unexpected_validation_outcome')
            for name,summary in reports.items():
                raw=self.read_artifact(summary['artifact']);body=strict_json(raw)
                self.validate_report(name,body,summary,context,saved['draft_sha256'])
            require(job['package_available']==(kind=='build' and mode=='ready'),'package_availability_mismatch')
            if kind=='build' and mode=='ready':require(reports.get('transport',{}).get('status')=='contract_preserved','transport_not_preserved')
            self.completed_scenarios.append(mode+'_'+kind+'_live_result_and_reports')
        self.completed_scenarios.append('draft_and_job_idempotency')

    def receipt(self,mode,success,reason=None):
        return dict(schema='claim-review-api-harness-report-1',target='127.0.0.1:'+str(self.port),
            mode=mode,status='passed' if success else 'failed',failure_code=reason,
            scope='Selected HTTP contract probes; not full API server acceptance.',
            completed_scenarios=self.completed_scenarios,cases=self.cases,
            untested=['coordinator_source_mutation','deterministic_concurrent_slot','CLI_timeout_and_process_cleanup',
                      'stdout_stderr_and_storage_quotas','rate_limiting','browser_UI_and_late_response'],
            **{f:False for f in FLAGS})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',type=int,required=True);p.add_argument('--token-file',type=Path,required=True)
    p.add_argument('--context-id',required=True);p.add_argument('--mode',choices=('probe','ready','orbit'),default='probe')
    p.add_argument('--record',type=Path);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    # Reserve receipt before issuing any mutating HTTP request; existing output aborts.
    with args.output.open('xb') as output:
        harness=None
        try:
            token=read_token(args.token_file);harness=Harness(args.port,token,args.context_id)
            require(args.mode=='probe' or args.record is not None,'record_required')
            record=None if args.mode=='probe' else m.read(args.record,1048576)
            context=harness.probe()
            if record is not None:harness.workflow(context,record,args.mode)
            receipt=harness.receipt(args.mode,True)
        except Exception as error:
            # Never persist untrusted error text (it could contain token/source bytes).
            reason=str(error) if type(error) is ValueError and re.fullmatch(r'[a-z_]{1,80}',str(error)) else type(error).__name__
            receipt=harness.receipt(args.mode,False,reason) if harness else dict(schema='claim-review-api-harness-report-1',status='failed',failure_code=reason,**{f:False for f in FLAGS})
        output.write(m.encoded(receipt))
    return 0 if receipt['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
