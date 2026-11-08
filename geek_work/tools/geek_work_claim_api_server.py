#!/usr/bin/env python3
"""Single-context loopback Claim Review API. No browser UI or publication actions."""
import argparse
import base64
import copy
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import selectors
import signal
import socket
import socketserver
import stat
import subprocess
import sys
import threading
import time
import uuid

import geek_work_claim_adapter as adapter
import geek_work_claim_extraction as extraction
import geek_work_claim_transport as transport
import geek_work_manuscript as m
import geek_work_manuscript_claims as claims
from knowledge import strict_json

TOOLS=Path(__file__).resolve().parent
LIMITS=json.loads((TOOLS.parent/'contracts/claim-review-api/limits.json').read_bytes())
FLAGS=extraction.FLAGS
WEB=TOOLS.parent/'web/claim-review'
STATIC={'/':('index.html','text/html; charset=utf-8'),'/ui/app.js':('app.js','text/javascript; charset=utf-8'),'/ui/core.js':('core.js','text/javascript; charset=utf-8'),'/ui/style.css':('style.css','text/css; charset=utf-8')}
CSP="default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'; object-src 'none'"
UUID=re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z')
HEX=re.compile(r'[0-9a-f]{64}\Z')
OPS={'context':(), 'drafts':('parent_draft_id','record_sha256','record_base64'),
     'checks':('draft_id','draft_sha256','context_fingerprint'),
     'builds':('draft_id','draft_sha256','context_fingerprint'),
     'jobs/status':('job_id',),'artifacts/read':('artifact_id','artifact_sha256','offset','max_bytes')}


class APIError(Exception):
    def __init__(self,status,code):self.status=status;self.code=code


class JobError(Exception):
    def __init__(self,code,exit_code=None,stuck=False):self.code=code;self.exit_code=exit_code;self.stuck=stuck


def need(ok,status,code):
    if not ok:raise APIError(status,code)


def strict(raw):
    if raw.startswith(b'\xef\xbb\xbf'):raise ValueError('BOM')
    value=strict_json(raw)
    # Reject escaped unpaired surrogates as well as malformed UTF-8 input bytes.
    def walk(x):
        if isinstance(x,str):x.encode('utf-8')
        elif isinstance(x,list):
            for v in x:walk(v)
        elif isinstance(x,dict):
            for k,v in x.items():walk(k);walk(v)
    walk(value);return value


def request_value(raw,operation):
    try:value=strict(raw)
    except (ValueError,UnicodeError):raise APIError(400,'malformed_request')
    need(type(value) is dict and set(value)=={'schema','operation','request_id','context_id',*OPS[operation]},400,'invalid_schema')
    need(value['schema']=='claim-review-api-request-1' and value['operation']==operation,400,'invalid_schema')
    for key in ('request_id','context_id','draft_id','job_id','artifact_id'):
        if key in value:need(type(value[key]) is str and UUID.fullmatch(value[key]),400,'invalid_schema')
    for key in ('record_sha256','draft_sha256','artifact_sha256','context_fingerprint'):
        if key in value:need(type(value[key]) is str and HEX.fullmatch(value[key]),400,'invalid_schema')
    if operation=='drafts':
        parent=value['parent_draft_id'];need(parent is None or (type(parent) is str and UUID.fullmatch(parent)),400,'invalid_schema')
        need(type(value['record_base64']) is str and 4<=len(value['record_base64'])<=1398104,400,'invalid_schema')
    if operation=='artifacts/read':
        need(type(value['offset']) is int and 0<=value['offset']<=LIMITS['output_file_bytes'],400,'invalid_schema')
        need(type(value['max_bytes']) is int and 1<=value['max_bytes']<=LIMITS['artifact_chunk_bytes'],400,'invalid_schema')
    return value


def write_new(path,raw):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw)


def bundle_snapshot(path,expected):
    """Read one bounded directory snapshot, then replay the existing claim-map logic."""
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        def read(name,limit):
            leaf=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
            with os.fdopen(leaf,'rb') as f:
                if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):raise ValueError('regular file required')
                raw=f.read(limit+1)
            if len(raw)>limit:raise ValueError('bundle limit')
            return raw
        manifest=read('manifest.json',extraction.MAX_BYTES)
        if m.sha(manifest)!=expected:raise ValueError('manifest hash')
        value=strict(manifest);claims.obj(value,'schema files')
        if value['schema']!='geek-work-manuscript-claim-bundle-1':raise ValueError('bundle schema')
        need(type(value['files']) is dict and len(value['files'])<=51,409,'anchor_unavailable')
        names=set()
        with os.scandir(fd) as entries:
            for entry in entries:
                names.add(entry.name)
                if len(names)>52:raise ValueError('bundle file count')
        if names!=set(value['files'])|{'manifest.json'}:raise ValueError('bundle files')
        blobs={'manifest.json':manifest};total=len(manifest)
        for name,digest in value['files'].items():
            if name not in ('map.json','report.json','review.html') and not re.fullmatch(r'(document|material)-[a-z0-9][a-z0-9-]{0,63}\.txt',name):raise ValueError('bundle filename')
            claims.digest(digest)
            raw=read(name,LIMITS['claim_map_bundle_bytes']-total);total+=len(raw)
            if m.sha(raw)!=digest:raise ValueError('bundle hash')
            blobs[name]=raw
        mapping=strict(blobs['map.json']);files=claims.catalog(mapping)
        if set(blobs)!=set(files)|{'map.json','report.json','review.html','manifest.json'}:raise ValueError('bundle files')
        generated=claims.derive(mapping,{name:blobs[name] for name in files})
        if any(blobs[name]!=raw for name,raw in generated.items()):raise ValueError('bundle replay')
        return blobs
    finally:os.close(fd)


class Runner:
    """Fixed CLI worker with bounded concurrent pipe reads and process-group cleanup."""
    def __init__(self,limits=None):self.limits=dict(LIMITS if limits is None else limits)

    def command(self,config_path):
        return [sys.executable,'-B',str(TOOLS/'geek_work_claim_api_worker.py'),str(config_path)]

    def terminate(self,process):
        for sig,wait in [(signal.SIGTERM,self.limits['terminate_grace_seconds']),(signal.SIGKILL,self.limits['kill_wait_seconds'])]:
            try:os.killpg(process.pid,sig)
            except ProcessLookupError:pass
            try:process.wait(timeout=wait)
            except subprocess.TimeoutExpired:continue
            # Kill any descendants left after their group leader exits.
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            return True
        return False

    def run(self,config_path,kind):
        process=subprocess.Popen(self.command(config_path),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
        selector=selectors.DefaultSelector();buffers={'stdout':bytearray(),'stderr':bytearray()}
        for name,pipe in [('stdout',process.stdout),('stderr',process.stderr)]:
            os.set_blocking(pipe.fileno(),False);selector.register(pipe,selectors.EVENT_READ,name)
        deadline=time.monotonic()+self.limits['check_timeout_seconds' if kind=='check' else 'build_timeout_seconds']
        try:
            while selector.get_map() or process.poll() is None:
                if time.monotonic()>deadline:raise JobError('timeout')
                for key,_ in selector.select(min(.05,max(0,deadline-time.monotonic()))):
                    raw=os.read(key.fileobj.fileno(),65536)
                    if not raw:selector.unregister(key.fileobj);continue
                    buf=buffers[key.data]
                    if len(buf)+len(raw)>self.limits[key.data+'_bytes']:raise JobError('output_limit')
                    buf.extend(raw)
            code=process.wait()
            if code==75 or code==-signal.SIGXFSZ:raise JobError('output_limit',code)
            return code,{k:bytes(v) for k,v in buffers.items()}
        except JobError as error:
            error.exit_code=process.poll();error.stuck=not self.terminate(process);raise
        finally:
            selector.close();process.stdout.close();process.stderr.close()
            if process.poll() is None:self.terminate(process)


class Context:
    def __init__(self,source,source_sha,expectations,expectations_sha,bundle,bundle_sha,source_claim_id,source_revision,session_dir,runner=None):
        for value in (source_sha,expectations_sha,bundle_sha):claims.digest(value)
        claims.ident(source_claim_id);transport.revision(source_revision)
        self.source=Path(source);self.expectations=Path(expectations);self.bundle=Path(bundle)
        self.pins={'source':source_sha,'expectations':expectations_sha,'claim_map_manifest':bundle_sha}
        self.claim_id=source_claim_id;self.revision=source_revision
        self.root=Path(session_dir);self.root.mkdir(mode=0o700)
        self.lock=threading.RLock();self.runner=runner or Runner()
        self.id=str(uuid.uuid4());self.token=secrets.token_urlsafe(32)
        self.fingerprint=m.sha(m.encoded(dict(source_sha256=source_sha,expectations_sha256=expectations_sha,claim_map_bundle_sha256=bundle_sha,source_claim_id=source_claim_id,source_revision=source_revision,limits_profile=LIMITS['profile'])))
        self.drafts={};self.jobs={};self.artifacts={};self.idempotency={};self.active=None;self.worker=None
        self.tokens=float(LIMITS['request_burst']);self.rate_time=time.monotonic()
        source_raw,expected_raw,blobs=self.snapshot()
        expected=strict(expected_raw);claims.obj(expected,'schema '+extraction.COMMON)
        if expected['schema']!='geek-work-claim-extraction-expectations-1':raise ValueError('expectations schema')
        extraction.common(expected,source_raw.decode('utf-8'),source_sha,{})
        mapping=strict(blobs['map.json'])
        if not any(c['id']==source_claim_id for c in mapping['claims']):raise ValueError('source claim missing')
        (self.root/'inputs').mkdir(mode=0o700);(self.root/'drafts').mkdir(mode=0o700);(self.root/'jobs').mkdir(mode=0o700)
        self.initial={}
        for key,name,raw in [('source_snapshot','source.txt',source_raw),('expectations','expectations.json',expected_raw),('claim_map_manifest','bundle-manifest.json',blobs['manifest.json'])]:
            path=self.root/'inputs'/name;write_new(path,raw);self.initial[key]=self.register(path)
        write_new(self.root/'session-token',self.token.encode())

    def snapshot(self):
        try:
            src=m.read(self.source,LIMITS['source_bytes']);exp=m.read(self.expectations,LIMITS['expectations_bytes'])
            need(m.sha(src)==self.pins['source'] and m.sha(exp)==self.pins['expectations'],409,'anchor_mismatch')
            blobs=bundle_snapshot(self.bundle,self.pins['claim_map_manifest'])
            return src,exp,blobs
        except APIError:raise
        except (OSError,ValueError,KeyError,TypeError,UnicodeError):raise APIError(409,'anchor_unavailable')

    def anchors(self):
        rows={}
        for name,path,limit in [('source',self.source,LIMITS['source_bytes']),('expectations',self.expectations,LIMITS['expectations_bytes']),('claim_map_manifest',self.bundle/'manifest.json',extraction.MAX_BYTES)]:
            try:
                digest=m.sha(m.read(path,limit));rows[name]={'state':'matched' if digest==self.pins[name] else 'mismatch','expected_sha256':self.pins[name],'observed_sha256':digest}
                if name=='claim_map_manifest' and digest==self.pins[name]:bundle_snapshot(self.bundle,digest)
            except (OSError,ValueError,APIError,KeyError,TypeError):rows[name]={'state':'unavailable','expected_sha256':self.pins[name],'observed_sha256':None}
        return rows

    def usage(self):
        total=0
        for directory,dirs,files in os.walk(self.root,followlinks=False):
            for name in [*dirs,*files]:
                s=os.stat(Path(directory)/name,follow_symlinks=False)
                need(not stat.S_ISLNK(s.st_mode),507,'quota_exceeded')
                if stat.S_ISREG(s.st_mode):total+=s.st_size
        return total

    def capacity(self,extra):
        reserve=LIMITS['job_reserved_bytes'] if self.active is not None else 0
        need(self.usage()+reserve+extra<=LIMITS['context_storage_bytes'],507,'quota_exceeded')

    def register(self,path,registry=None):
        raw=m.read(path,LIMITS['output_file_bytes']);identifier=str(uuid.uuid4())
        ref=dict(artifact_id=identifier,sha256=m.sha(raw),size_bytes=len(raw),media_type='application/json' if path.suffix=='.json' else 'text/plain')
        target=self.artifacts if registry is None else registry
        target[identifier]=(path,ref);return ref

    def rate(self):
        now=time.monotonic();self.tokens=min(LIMITS['request_burst'],self.tokens+(now-self.rate_time)*LIMITS['requests_per_second']);self.rate_time=now
        need(self.tokens>=1,429,'rate_limited');self.tokens-=1

    def handle(self,request,raw):
        with self.lock:
            need(request['context_id']==self.id,404,'unknown_context')
            op=request['operation'];key=(op,request['request_id']);digest=m.sha(raw)
            if op in ('drafts','checks','builds') and key in self.idempotency:
                old,response=self.idempotency[key];need(old==digest,409,'idempotency_conflict');return copy.deepcopy(response)
            if op=='context':result=(200,dict(context_fingerprint=self.fingerprint,source_claim_id=self.claim_id,source_revision=self.revision,anchors=self.anchors(),**self.initial,limits=LIMITS))
            elif op=='drafts':result=(201,self.save(request))
            elif op in ('checks','builds'):result=(202,self.start(request))
            elif op=='jobs/status':
                need(request['job_id'] in self.jobs,404,'unknown_job');result=(200,copy.deepcopy(self.jobs[request['job_id']]))
            else:result=(200,self.read(request))
            if op in ('drafts','checks','builds'):self.idempotency[key]=(digest,copy.deepcopy(result))
            return result

    def save(self,req):
        try:
            raw=base64.b64decode(req['record_base64'],validate=True)
            need(base64.b64encode(raw).decode()==req['record_base64'],400,'noncanonical_base64')
        except ValueError:raise APIError(400,'noncanonical_base64')
        need(len(raw)<=LIMITS['record_bytes'],413,'payload_too_large')
        try:need(type(strict(raw)) is dict,400,'invalid_record_json')
        except (ValueError,UnicodeError):raise APIError(400,'invalid_record_json')
        need(m.sha(raw)==req['record_sha256'],409,'draft_hash_mismatch')
        parent=req['parent_draft_id'];need(parent is None or parent in self.drafts,404,'unknown_draft')
        need(len(self.drafts)<LIMITS['max_drafts'],507,'quota_exceeded');self.capacity(len(raw)+2048)
        identifier=str(uuid.uuid4());path=self.root/'drafts'/(identifier+'.json');write_new(path,raw)
        data=dict(draft_id=identifier,parent_draft_id=parent,draft_sha256=m.sha(raw),size_bytes=len(raw),validation_state='not_run')
        self.drafts[identifier]=(path,data);write_new(self.root/'drafts'/(identifier+'.meta.json'),m.encoded(data))
        return data

    def start(self,req):
        need(req['draft_id'] in self.drafts,404,'unknown_draft')
        path,draft=self.drafts[req['draft_id']]
        need(req['draft_sha256']==draft['draft_sha256'],409,'draft_hash_mismatch')
        need(req['context_fingerprint']==self.fingerprint,409,'context_fingerprint_mismatch')
        need(self.active is None,409,'context_busy');need(len(self.jobs)<LIMITS['max_jobs'],507,'quota_exceeded')
        self.snapshot();self.capacity(LIMITS['job_reserved_bytes'])
        raw=m.read(path,LIMITS['record_bytes']);need(m.sha(raw)==draft['draft_sha256'],409,'draft_hash_mismatch')
        identifier=str(uuid.uuid4());kind='check' if req['operation']=='checks' else 'build'
        data=dict(job_id=identifier,kind=kind,draft_id=draft['draft_id'],draft_sha256=draft['draft_sha256'],context_fingerprint=self.fingerprint)
        directory=self.root/'jobs'/identifier;directory.mkdir(mode=0o700)
        self.jobs[identifier]=dict(**data,state='queued',exit_code=None,reports=[],failure=None,artifacts=[],package_available=False)
        self.active=identifier
        self.worker=threading.Thread(target=self.work,args=(identifier,directory,raw,time.monotonic()),daemon=True)
        try:self.worker.start()
        except RuntimeError:
            self.active=None
            self.jobs[identifier].update(state='failed',failure=dict(code='worker_failure',message='Worker could not start.'))
            raise APIError(500,'internal_error')
        return data

    def read(self,req):
        need(req['artifact_id'] in self.artifacts,404,'unknown_artifact')
        path,ref=self.artifacts[req['artifact_id']]
        need(req['artifact_sha256']==ref['sha256'],409,'artifact_integrity_failure')
        try:raw=m.read(path,LIMITS['output_file_bytes'])
        except (ValueError,OSError):raise APIError(409,'artifact_integrity_failure')
        need(m.sha(raw)==ref['sha256'] and len(raw)==ref['size_bytes'],409,'artifact_integrity_failure')
        offset=req['offset'];need(offset<=len(raw),416,'range_not_satisfiable');chunk=raw[offset:offset+req['max_bytes']]
        return dict(artifact_id=ref['artifact_id'],artifact_sha256=ref['sha256'],total_size_bytes=len(raw),offset=offset,returned_bytes=len(chunk),eof=offset+len(chunk)==len(raw),chunk_base64=base64.b64encode(chunk).decode())

    def command_config(self,directory,kind):
        common=['--source-snapshot',str(directory/'source.txt'),'--source-sha256',self.pins['source'],'--expectations',str(directory/'expectations.json'),'--expectations-sha256',self.pins['expectations']]
        if kind=='check':script=TOOLS/'geek_work_claim_extraction.py';args=common+['--record',str(directory/'record.json'),'--output',str(directory/'extraction-report.json')]
        else:script=TOOLS/'geek_work_claim_adapter.py';args=common+['--record',str(directory/'record.json'),'--claim-map-bundle',str(directory/'bundle'),'--claim-map-bundle-sha256',self.pins['claim_map_manifest'],'--source-claim-id',self.claim_id,'--source-revision',str(self.revision),'--output',str(directory/'package')]
        initial=sum(p.stat().st_size for p in directory.rglob('*') if p.is_file())
        return dict(root=str(directory),script=str(script),args=args,file_limit=self.runner.limits['output_file_bytes'],write_budget=self.runner.limits['job_output_bytes']-initial-self.runner.limits['stdout_bytes']-self.runner.limits['stderr_bytes']-8192)

    def work(self,identifier,directory,record,queued_at):
        stuck=False;exit_code=None
        try:
            if time.monotonic()-queued_at>LIMITS['job_start_seconds']:raise JobError('worker_failure')
            with self.lock:self.jobs[identifier]['state']='running'
            source,expected,blobs=self.snapshot()
            write_new(directory/'source.txt',source);write_new(directory/'expectations.json',expected);write_new(directory/'record.json',record)
            (directory/'bundle').mkdir(mode=0o700)
            for name,raw in blobs.items():write_new(directory/'bundle'/name,raw)
            kind=self.jobs[identifier]['kind'];config=self.command_config(directory,kind)
            if config['write_budget']<0:raise JobError('output_limit')
            write_new(directory/'worker.json',m.encoded(config))
            exit_code,logs=self.runner.run(directory/'worker.json',kind)
            for name,raw in logs.items():write_new(directory/(name+'.log'),raw)
            if exit_code not in (0,1,2):raise JobError('process_crash',exit_code)
            # Replay the same deterministic code to validate CLI output bytes and bindings.
            # This is not an independent audit, and never executes source text or Lean.
            if kind=='check':
                result=extraction.check(source,self.pins['source'],expected,self.pins['expectations'],record)
                expected_files={'extraction-report.json':m.encoded(result)};folder=directory
                wanted={'record_consistent':0,'needs_context':1,'review_required':1,'invalid_input':2}[result['status']]
                built=False
            else:
                expected_files=adapter.build(source,self.pins['source'],expected,self.pins['expectations'],record,directory/'bundle',self.pins['claim_map_manifest'],self.claim_id,self.revision)
                result=strict(expected_files['adapter-report.json']);folder=directory/'package'
                wanted={'built':0,'build_blocked':1,'invalid_input':2}[result['status']];built=result['status']=='built'
                manifest=strict(m.read(folder/'manifest.json',extraction.MAX_BYTES));claims.obj(manifest,'schema status input_hashes files '+' '.join(FLAGS))
                if (manifest['schema']!='geek-work-claim-adapter-package-1' or manifest['status']!=result['status'] or
                    any(manifest[f] is not False for f in FLAGS) or manifest['files']!={name:m.sha(raw) for name,raw in sorted(expected_files.items())}):raise JobError('invalid_cli_report')
                inputs=dict(source_sha256=m.sha(source),expectations_sha256=m.sha(expected),record_sha256=m.sha(record),expected_source_sha256=self.pins['source'],expected_expectations_sha256=self.pins['expectations'],expected_claim_map_bundle_sha256=self.pins['claim_map_manifest'],source_claim_id=self.claim_id,declared_source_revision=self.revision)
                if manifest['input_hashes']!=inputs or set(p.name for p in folder.iterdir())!=set(expected_files)|{'manifest.json'}:raise JobError('invalid_cli_report')
            if exit_code!=wanted:raise JobError('invalid_cli_report',exit_code)
            for name,raw in expected_files.items():
                if m.read(folder/name,LIMITS['output_file_bytes'])!=raw:raise JobError('invalid_cli_report')
            reports=[];refs=[];staged={}
            with self.lock:
                # Register only after every file and report has passed validation.
                for name in sorted(expected_files):
                    ref=self.register(folder/name,staged);refs.append(ref)
                    if name in ('extraction-report.json','adapter-report.json','transport-report.json'):
                        body=strict(expected_files[name]);reports.append(dict(validator=name.split('-')[0],status=body['status'],reason=body.get('reason'),artifact=ref))
                if kind=='build':refs.append(self.register(folder/'manifest.json',staged))
                completed=dict(self.jobs[identifier],state='completed',exit_code=exit_code,reports=reports,artifacts=refs,package_available=built)
                write_new(directory/'job-receipt.json',m.encoded(completed))
                self.artifacts.update(staged)
                self.jobs[identifier]=completed
        except APIError as error:
            with self.lock:self.jobs[identifier].update(state='failed',exit_code=exit_code,failure=dict(code=error.code if error.code in ('anchor_mismatch','anchor_unavailable') else 'snapshot_failure',message='Pinned input snapshot could not be prepared.'))
        except JobError as error:
            stuck=error.stuck
            with self.lock:self.jobs[identifier].update(state='failed',exit_code=error.exit_code,failure=dict(code=error.code,message='Job failed under the execution contract.'))
        except Exception:
            with self.lock:self.jobs[identifier].update(state='failed',exit_code=exit_code,failure=dict(code='invalid_cli_report',message='CLI output or local storage did not satisfy the contract.'))
        finally:
            with self.lock:
                try:write_new(directory/'job-receipt.json',m.encoded(self.jobs[identifier]))
                except OSError:pass
                if not stuck:self.active=None


class Handler(socketserver.BaseRequestHandler):
    def receive(self):
        deadline=time.monotonic()+LIMITS['body_read_seconds'];buf=bytearray()
        def recv(count):
            remaining=deadline-time.monotonic()
            if remaining<=0:raise APIError(408,'request_timeout')
            self.request.settimeout(remaining)
            try:raw=self.request.recv(count)
            except socket.timeout:raise APIError(408,'request_timeout')
            if not raw:raise APIError(400,'malformed_request')
            return raw
        while b'\r\n\r\n' not in buf:
            buf.extend(recv(4096));need(len(buf)<=LIMITS['header_bytes']+4096,413,'payload_too_large')
        header,body=bytes(buf).split(b'\r\n\r\n',1);need(len(header)+4<=LIMITS['header_bytes'],413,'payload_too_large')
        try:
            lines=header.decode('ascii').split('\r\n');method,path,protocol=lines[0].split(' ')
        except (ValueError,UnicodeError):raise APIError(400,'malformed_request')
        need(protocol=='HTTP/1.1' and len(lines)-1<=LIMITS['header_count'],400,'malformed_request')
        headers={}
        for line in lines[1:]:
            need(':' in line and not line.startswith((' ','\t')),400,'malformed_request')
            key,value=line.split(':',1);need(bool(re.fullmatch(r'[A-Za-z0-9-]+',key)),400,'malformed_request')
            value=value.strip(' \t');need(not any(ord(c)<32 or ord(c)==127 for c in value),400,'malformed_request')
            headers.setdefault(key.lower(),[]).append(value)
        for key in ('host','origin','authorization','content-length','content-type'):
            need(len(headers.get(key,[]))<=1,400,'malformed_request')
        need('transfer-encoding' not in headers,400,'malformed_request')
        need('content-encoding' not in headers or headers['content-encoding']==['identity'],415,'unsupported_media_type')
        if method=='GET':
            need(headers.get('host')==[self.server.host],403,'origin_host_rejected')
            need('origin' not in headers or headers['origin']==[self.server.origin],403,'origin_host_rejected')
            need(headers.get('sec-fetch-site',['none'])[0] in ('none','same-origin'),403,'origin_host_rejected')
            need(path in STATIC,404,'unknown_route')
            need(not body and headers.get('content-length',['0'])==['0'],400,'malformed_request')
            return '__static__',path
        need(headers.get('host')==[self.server.host] and headers.get('origin')==[self.server.origin],403,'origin_host_rejected')
        auth=headers.get('authorization',[''])[0]
        need(hmac.compare_digest(auth,'Bearer '+self.server.context.token),401,'unauthorized')
        with self.server.context.lock:self.server.context.rate()
        need(method=='POST',405,'method_not_allowed')
        need(path.startswith('/v1/') and path[4:] in OPS,404,'unknown_route');op=path[4:]
        need(headers.get('content-type',[''])[0].lower() in ('application/json','application/json; charset=utf-8'),415,'unsupported_media_type')
        length=headers.get('content-length',[''])[0];need(bool(re.fullmatch('[0-9]{1,10}',length)),400,'malformed_request');length=int(length)
        need(length<=LIMITS['post_body_bytes'],413,'payload_too_large')
        while len(body)<length:body+=recv(min(65536,length-len(body)))
        need(len(body)==length,400,'malformed_request')
        return op,body

    def handle(self):
        req=None
        try:
            op,raw=self.receive()
            if op=='__static__':
                name,kind=STATIC[raw];body=m.read(WEB/name,1048576)
                header=(f'HTTP/1.1 200 OK\r\nContent-Type: {kind}\r\nContent-Length: {len(body)}\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\nReferrer-Policy: no-referrer\r\nContent-Security-Policy: {CSP}\r\nConnection: close\r\n\r\n').encode()
                self.request.settimeout(LIMITS['response_write_seconds']);self.request.sendall(header+body);return
            req=request_value(raw,op);status,data=self.server.context.handle(req,raw)
            response=dict(schema='claim-review-api-response-1',operation=op,request_id=req['request_id'],context_id=req['context_id'],ok=True,assurances={f:False for f in FLAGS},data=data)
        except APIError as error:
            status=error.status;response=dict(schema='claim-review-api-response-1',operation=req['operation'] if req else None,request_id=req['request_id'] if req else None,context_id=req['context_id'] if req else None,ok=False,assurances={f:False for f in FLAGS},error=dict(code=error.code,message=error.code,retry_after_seconds=1 if status==429 else None))
        except Exception:
            status=500;response=dict(schema='claim-review-api-response-1',operation=None,request_id=None,context_id=None,ok=False,assurances={f:False for f in FLAGS},error=dict(code='internal_error',message='Local request failed.',retry_after_seconds=None))
        body=m.encoded(response)
        header=f'HTTP/1.1 {status} Response\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n'.encode()
        try:self.request.settimeout(LIMITS['response_write_seconds']);self.request.sendall(header+body)
        except OSError:pass


class Server(socketserver.TCPServer):
    allow_reuse_address=False
    def __init__(self,context,port=0):
        self.context=context
        super().__init__(('127.0.0.1',port),Handler)
        self.host='127.0.0.1:'+str(self.server_address[1]);self.origin='http://'+self.host
    def handle_error(self,request,client_address):pass  # no secret-bearing request logs


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source-snapshot','source-sha256','expectations','expectations-sha256','claim-map-bundle','claim-map-bundle-sha256','source-claim-id','session-dir'):p.add_argument('--'+name,required=True)
    p.add_argument('--source-revision',type=int,required=True);p.add_argument('--port',type=int,default=0)
    args=p.parse_args()
    if not 0<=args.port<=65535:p.error('port out of range')
    context=Context(args.source_snapshot,args.source_sha256,args.expectations,args.expectations_sha256,args.claim_map_bundle,args.claim_map_bundle_sha256,args.source_claim_id,args.source_revision,args.session_dir)
    with Server(context,args.port) as server:
        info=dict(context_id=context.id,port=server.server_address[1],context_fingerprint=context.fingerprint,token_file=str(context.root/'session-token'))
        write_new(context.root/'session.json',m.encoded(info));print(json.dumps(info),flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:
            if context.worker is not None:context.worker.join(timeout=LIMITS['build_timeout_seconds']+10)


if __name__=='__main__':main()
