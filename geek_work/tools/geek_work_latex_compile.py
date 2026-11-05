#!/usr/bin/env python3
"""Opt-in two-pass pdfLaTeX adapter, isolated from the Typst archive format."""
import argparse
import base64
import json
from pathlib import Path
import re
import resource
import subprocess
import time
import uuid
import geek_work_manuscript as m
import geek_work_manuscript_claims as k
import geek_work_manuscript_compile as common

RUNTIME = Path(__file__).resolve().parents[1]/'research/manuscript-workbench/latex-runtime'
CAPTURE = 32 * 1024 * 1024
MAX_OUTPUT = 8 * 1024 * 1024
TIMEOUT = 30
OUTPUTS = {'document.pdf','document.log','document.aux','document.fls'}


def profile():
    value=m.load(m.read(RUNTIME/'profile.json'))
    k.obj(value,'schema platform image_id base_image snapshot files packages_sha256 compiler_version')
    m.require(value['schema']=='geek-work-latex-runtime-1' and value['platform']=='linux/amd64','runtime profile')
    m.require(type(value['image_id']) is str and re.fullmatch('sha256:[0-9a-f]{64}',value['image_id']),'image ID')
    m.require(set(value['files'])=={'Dockerfile','worker.py'},'runtime files')
    for name,h in value['files'].items():m.require(m.sha(m.read(RUNTIME/name))==h,'runtime source drift')
    m.require(m.sha(m.read(RUNTIME/'packages.tsv'))==value['packages_sha256'],'runtime package inventory drift')
    return value


def request(value):
    common.validate_request(value,'geek-work-latex-compile-request-1','.tex')
    m.require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_/-]*\.tex',value['entry']), 'literal LaTeX entry name required')
    return value


def command(name,snapshot,entry,image):
    return command_for_path(name,str(snapshot.resolve()),entry,image)


def command_for_path(name,path,entry,image):
    m.require(',' not in path and '\n' not in path,'Docker bind path')
    return ['docker','create','--pull=never','--platform=linux/amd64','--name',name,
            '--network=none','--read-only','--user=1000:1000','--cap-drop=ALL',
            '--security-opt=no-new-privileges','--cpus=2','--memory=512m','--memory-swap=512m',
            '--pids-limit=64','--ulimit=fsize=8388608:8388608','--ulimit=core=0:0','--log-driver=none',
            '--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=96m,mode=1777',
            '--mount','type=bind,src='+path+',dst=/src,readonly','--workdir=/src',
            '--env=PYTHONDONTWRITEBYTECODE=1','--entrypoint=/usr/local/bin/python',image,'-B','/opt/worker.py',entry]


def decode_envelope(raw):
    m.require(len(raw)<CAPTURE,'capture byte limit')
    value=m.load(raw);k.obj(value,'schema passes files')
    m.require(value['schema']=='geek-work-latex-worker-1','worker schema')
    passes=k.rows(value['passes'],2,1);artifacts={};codes=[]
    def decode(encoded):
        m.require(type(encoded) is str and len(encoded)<=((MAX_OUTPUT+2)//3)*4,'encoded byte limit')
        blob=base64.b64decode(encoded,validate=True);m.require(len(blob)<=MAX_OUTPUT,'decoded byte limit')
        return blob
    for i,row in enumerate(passes):
        k.obj(row,'exit_code log_b64');m.require(type(row['exit_code']) is int,'engine exit code')
        codes.append(row['exit_code']);artifacts['pass-'+str(i+1)+'.log']=decode(row['log_b64'])
    m.require(all(code==0 for code in codes[:-1]),'pass after failed engine')
    m.require(type(value['files']) is dict and set(value['files'])<=OUTPUTS,'worker output set')
    artifacts.update({name:decode(blob) for name,blob in value['files'].items()})
    m.require(sum(map(len,artifacts.values()))<=24*1024*1024,'decoded output total')
    if codes[-1]!=0:
        return dict(status='compiler_failed',engine_exit_codes=codes),artifacts
    m.require(codes==[0,0] and set(value['files'])==OUTPUTS,'incomplete successful compilation')
    m.require(artifacts['document.pdf'].startswith(b'%PDF-'),'PDF header')
    last=artifacts['pass-2.log']+artifacts['document.log']
    warning=bool(re.search(rb'Warning:|Overfull|Underfull|undefined references|Rerun',last,re.I))
    return dict(status='compiled_with_warnings' if warning else 'compiled',engine_exit_codes=codes,
                diagnostics_review_required=warning,pdf_sha256=m.sha(artifacts['document.pdf'])),artifacts


def attach(name,out):
    def limit():resource.setrlimit(resource.RLIMIT_FSIZE,(CAPTURE,CAPTURE))
    with (out/'worker.stdout').open('xb') as stdout,(out/'worker.stderr').open('xb') as stderr:
        return subprocess.run(['docker','start','-a',name],stdout=stdout,stderr=stderr,timeout=TIMEOUT,preexec_fn=limit)


def execute(snapshot,entry,out,runtime):
    image=runtime['image_id'];name='geek-work-latex-'+uuid.uuid4().hex
    result=dict(status='infrastructure_error',image_id=image,container_name=name,container_removed=False,
                timed_out=False,oom_killed=None,worker_exit_code=None)
    artifacts={};started=time.monotonic()
    try:
        observed=json.loads(common.success(common.docker(['docker','image','inspect',image])))
        m.require(len(observed)==1 and observed[0]['Id']==image and observed[0]['Os']=='linux' and observed[0]['Architecture']=='amd64','installed image identity')
        (out/'image.json').write_bytes(m.encoded(observed))
        cmd=command(name,snapshot,entry,image);(out/'command.json').write_bytes(m.encoded(cmd))
        common.success(common.docker(cmd));client=None
        try:client=attach(name,out).returncode
        except subprocess.TimeoutExpired:
            result['timed_out']=True;common.docker(['docker','kill',name])
        state=json.loads(common.success(common.docker(['docker','inspect',name])))[0]
        (out/'container.json').write_bytes(m.encoded(state))
        m.require(state['Image']==image,'container image identity')
        result.update(worker_exit_code=state['State']['ExitCode'],oom_killed=state['State']['OOMKilled'],client_exit_code=client)
        if result['timed_out']:result['status']='timeout'
        elif result['oom_killed']:result['status']='oom'
        elif any((out/n).stat().st_size>=CAPTURE for n in ('worker.stdout','worker.stderr')):result['status']='capture_limit'
        elif state['State']['Running']:result['status']='infrastructure_error'
        elif result['worker_exit_code']!=0 or client!=0:result['status']='worker_failed'
        else:
            try:
                decoded,artifacts=decode_envelope(m.read(out/'worker.stdout',CAPTURE));result.update(decoded)
            except (ValueError,KeyError,TypeError) as error:
                result.update(status='artifact_rejected',error=str(error)[:4000])
    except (ValueError,OSError,RuntimeError,subprocess.TimeoutExpired) as error:
        result.update(status='infrastructure_error',error=str(error)[:4000])
    finally:
        try:
            common.docker(['docker','rm','-f',name])
            left=common.success(common.docker(['docker','container','ls','-aq','--filter','name=^/'+name+'$']))
            result['container_removed']=not left.strip()
        except (ValueError,OSError,RuntimeError,subprocess.TimeoutExpired) as error:result['cleanup_error']=str(error)[:4000]
        if not result['container_removed']:result['prior_status']=result['status'];result['status']='cleanup_failed'
        result['wall_time_ms']=round((time.monotonic()-started)*1000)
    if artifacts:
        (out/'artifacts').mkdir()
        for filename,raw in artifacts.items():
            with (out/'artifacts'/filename).open('xb') as f:f.write(raw)
    return result


def build(root,request_path,anchor,output):
    k.digest(anchor);raw=m.read(request_path);m.require(m.sha(raw)==anchor,'request SHA mismatch')
    spec=request(m.load(raw));runtime=profile();blobs={};total=0
    for row in spec['files']:
        blob=common.source(root,row['path']);total+=len(blob);m.require(total<=common.MAX_TOTAL,'input byte limit')
        if Path(row['path']).suffix in {'.tex','.bib','.sty','.cls'}:m.source(blob)
        m.require(m.sha(blob)==row['sha256'],'source SHA mismatch');blobs[row['path']]=blob
    output.mkdir(parents=True,exist_ok=False);snapshot=output/'sources';snapshot.mkdir()
    for name,blob in blobs.items():
        p=snapshot/name;p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('xb') as f:f.write(blob)
        p.chmod(0o644)
    for p in [snapshot,*[p for p in snapshot.rglob('*') if p.is_dir()]]:p.chmod(0o755)
    (output/'request.json').write_bytes(raw);(output/'runtime.json').write_bytes(m.encoded(runtime))
    result=execute(snapshot,spec['entry'],output,runtime)
    unchanged=all(common.source(snapshot,n)==b for n,b in blobs.items())
    if not unchanged:result['prior_status']=result['status'];result['status']='snapshot_changed'
    receipt=dict(schema='geek-work-latex-compile-receipt-1',request_sha256=anchor,**result,
                 snapshot_unchanged_at_final_check=unchanged,compile_timeout_seconds=TIMEOUT,
                 shell_escape_enabled=False,scientific_verification=False,pdf_visual_review=False,
                 limits='Local trusted Docker/kernel/pdfLaTeX worker. Two fixed passes, no BibTeX/Biber. Header/warning checks are not PDF conformance, complete reference validation or proof. No live writeback or publication.')
    (output/'receipt.json').write_bytes(m.encoded(receipt))
    files={str(p.relative_to(output)):m.sha(m.read(p,40*1024*1024)) for p in sorted(output.rglob('*')) if p.is_file()}
    manifest=m.encoded(dict(schema='geek-work-latex-compile-manifest-1',files=files));(output/'manifest.json').write_bytes(manifest)
    return dict(status=result['status'],manifest_sha256=m.sha(manifest),container_removed=result['container_removed'],pdf_sha256=result.get('pdf_sha256'))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--request',type=Path,required=True);p.add_argument('--request-sha256',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=build(a.root,a.request,a.request_sha256,a.output);print(m.encoded(r).decode(),end='')
    if r['status']!='compiled':raise SystemExit(2)


if __name__=='__main__':main()
