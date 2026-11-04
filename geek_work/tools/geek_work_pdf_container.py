#!/usr/bin/env python3
"""Pinned no-network Docker PDF page packets with recorded cleanup outcomes."""
import argparse
import json
from pathlib import Path
import re
import resource
import signal
import subprocess
import tempfile
import time
import uuid
import geek_work_pdf_pages as p

m=p.m;k=p.k;tree=p.tree
PROFILE_FILE=Path(__file__).resolve().parents[1]/'runtime/pdf-renderer/container-profile.json'
PROFILE_SHA='1324a5f7875b8f143f13093985b3f2d069a32fb6c7e737f7895ee4cd824f79c6'
SELECTION_PROFILE_SHA='1375ca93274e52fd86bf073204c6bf91b07d52142e431b42a990ee2cf7b2df50'
SCHEMA='geek-work-pdf-container-pages-manifest-1'
PHASES=('image','create','before','start','after','remove','absence')
CONTROL_LIMIT=2*1024*1024
TOTAL_TIMEOUT=180


def profile():
    raw=m.read(PROFILE_FILE);m.require(m.sha(raw)==PROFILE_SHA,'reviewed container profile changed');return m.load(raw)


def validate_profile(value):m.require(m.encoded(value)==m.encoded(profile()),'container profile mismatch')


def selection_profile():
    raw=m.read(PROFILE_FILE.with_name('selection-profile.json'))
    m.require(m.sha(raw)==SELECTION_PROFILE_SHA,'reviewed selection profile changed');return m.load(raw)


def validate_selection_profile(value):m.require(m.encoded(value)==m.encoded(selection_profile()),'selection profile mismatch')


def runtime_profile(value):
    if value is None:return profile()
    # Only the separately pinned selection runtime may override legacy defaults.
    validate_selection_profile(value);return value


def argv(name,mode,page=None,*,runtime=None):
    runtime=runtime_profile(runtime)
    image=runtime['image_id'];args=['docker','create','--name',name,'--pull=never','--network','none','--read-only','--user','1000:1000','--memory','512m','--memory-swap','512m','--cpus','1','--pids-limit','64','--cap-drop','ALL','--security-opt','no-new-privileges','--tmpfs','/tmp:rw,noexec,nosuid,size=67108864,mode=1777','--ulimit','cpu=15:15','--ulimit','fsize=8388608:8388608','--ulimit','nofile=64:64','--log-driver','none','-i',image,mode]
    if mode=='page':args.append(str(page))
    return dict(image=['docker','image','inspect',image],create=args,before=['docker','inspect',name],start=['docker','start','-a','-i',name],after=['docker','inspect',name],remove=['docker','rm','-f',name],absence=['docker','ps','-a','--filter','name=^'+name+'$','--format','{{.ID}}'])


def capture(command,data=b'',timeout=15,limit=CONTROL_LIMIT):
    code=None;error=None
    def limits():
        bound=max(limit,65536);resource.setrlimit(resource.RLIMIT_FSIZE,(bound,bound));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err:
        try:code=subprocess.run(command,input=data,stdout=out,stderr=err,timeout=timeout,preexec_fn=limits,env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LC_ALL':'C'}).returncode
        except (OSError,subprocess.SubprocessError) as exc:error=type(exc).__name__
        out.seek(0);stdout=out.read(limit+1);err.seek(0);stderr=err.read(65537)
    return stdout[:limit],stderr[:65536],dict(returncode=code,error_class=error,capture_overflow=len(stdout)>limit or len(stderr)>65536)


def inspect_config(value,name,*,runtime=None):
    runtime=runtime_profile(runtime)
    m.require(value['Name']=='/'+name and value['Image']==runtime['image_id'],'container identity')
    h=value['HostConfig'];config=value['Config']
    expected=dict(NetworkMode='none',ReadonlyRootfs=True,Memory=536870912,MemorySwap=536870912,NanoCpus=1000000000,PidsLimit=64,Privileged=False,PidMode='',IpcMode='private')
    m.require(all(type(h.get(key)) is type(v) and h.get(key)==v for key,v in expected.items()),'container resource/isolation configuration')
    m.require(config['User']=='1000:1000' and config['Entrypoint']==['python3','-I','/opt/geek-work/worker.py'],'container worker/user')
    m.require(not h.get('Binds') and not value.get('Mounts') and not h.get('Devices') and not h.get('DeviceRequests') and not h.get('PortBindings') and not h.get('PublishAllPorts'),'unexpected host exposure')
    m.require(h['CapDrop']==['ALL'] and not h.get('CapAdd') and h['SecurityOpt']==['no-new-privileges'],'container privileges')
    m.require(h['Tmpfs']=={'/tmp':'rw,noexec,nosuid,size=67108864,mode=1777'},'container tmpfs')
    limits={row['Name']:(row['Soft'],row['Hard']) for row in h['Ulimits']}
    m.require(len(h['Ulimits'])==3 and limits==dict(cpu=(15,15),fsize=(8388608,8388608),nofile=(64,64)),'container ulimits')


def assessment(folder,name,mode,page,pdf_sha,*,runtime=None):
    selected=runtime;runtime=runtime_profile(runtime)
    commands=argv(name,mode,page,runtime=selected);present={x.name for x in folder.iterdir() if x.name!='receipt.json'};expected={phase+suffix for phase in PHASES for suffix in ('.json','.stdout','.stderr')}
    m.require(present<=expected|{'interrupted.json'},'unexpected operation files');rows={};error=None;exit_code=None
    interrupted='interrupted.json' in present
    if interrupted:m.require(m.read(folder/'interrupted.json')==m.encoded(dict(schema='geek-work-pdf-container-interruption-1',error_class='InterruptedError')),'interruption marker')
    try:
        for phase in PHASES:
            raw=m.read(folder/(phase+'.json'));row=m.load(raw);k.obj(row,'argv stdin_sha256 returncode error_class capture_overflow stdout_sha256 stderr_sha256')
            out=m.read(folder/(phase+'.stdout'),p.MAX_IMAGE if phase=='start' and mode=='page' else 65536 if phase=='start' else CONTROL_LIMIT);err=m.read(folder/(phase+'.stderr'),65536)
            m.require(row['argv']==commands[phase] and row['stdout_sha256']==m.sha(out) and row['stderr_sha256']==m.sha(err),'operation command/capture binding')
            m.require(row['stdin_sha256']==(pdf_sha if phase=='start' and mode!='profile' else m.sha(b'')),'operation stdin binding')
            rows[phase]=(row,out,err)
        for row,out,err in rows.values():m.require(type(row['returncode']) is int and row['returncode']==0 and row['error_class'] is None and row['capture_overflow'] is False,'operation process failure')
        image=m.load(rows['image'][1]);m.require(len(image)==1 and image[0]['Id']==runtime['image_id'] and image[0]['Os']=='linux' and image[0]['Architecture']=='amd64','runtime image identity')
        m.require(bool(re.fullmatch(b'[0-9a-f]{64}\n',rows['create'][1])),'container create identity')
        before=m.load(rows['before'][1]);after=m.load(rows['after'][1]);m.require(len(before)==len(after)==1,'container inspect coverage');inspect_config(before[0],name,runtime=selected);inspect_config(after[0],name,runtime=selected)
        cid=rows['create'][1].strip().decode();m.require(before[0]['Id']==after[0]['Id']==cid,'container ID changed')
        exit_code=after[0]['State']['ExitCode'];m.require(after[0]['State']['Running'] is False and type(exit_code) is int and exit_code==0 and after[0]['State'].get('OOMKilled') is False,'container exit state')
        m.require(rows['remove'][1].strip().decode()==name and not rows['absence'][1].strip(),'container removal')
        if mode=='profile':m.require(m.encoded(m.load(rows['start'][1]))==m.encoded(runtime['worker_observation']),'worker profile observation')
    except (ValueError,OSError,KeyError,TypeError,UnicodeError) as exc:error=type(exc).__name__
    if interrupted:error='InterruptedError'
    # Cleanup is checked independently even when an earlier phase was absent/rejected.
    removed=False
    try:
        row=m.load(m.read(folder/'absence.json'));out=m.read(folder/'absence.stdout');err=m.read(folder/'absence.stderr',65536)
        removed=row['argv']==commands['absence'] and row['stdin_sha256']==m.sha(b'') and type(row['returncode']) is int and row['returncode']==0 and row['error_class'] is None and row['capture_overflow'] is False and row['stdout_sha256']==m.sha(out) and row['stderr_sha256']==m.sha(err) and not out.strip()
    except (ValueError,OSError,KeyError,TypeError):pass
    return dict(schema='geek-work-pdf-container-operation-1',name=name,mode=mode,page=page,image_id=runtime['image_id'],stdin_sha256=pdf_sha if mode!='profile' else m.sha(b''),status='cleanup_failed' if not removed else 'failed' if error else 'completed',container_removed=removed,exit_code=exit_code,error_class=error)


def execute(folder,mode,pdf=b'',page=None,*,runtime=None):
    selected=runtime;runtime=runtime_profile(runtime)
    m.require(mode in ('profile','info','page') and (type(page) is int and 1<=page<=runtime.get('max_source_page',16) if mode=='page' else page is None),'fixed container mode/page')
    folder.mkdir();name='geek-work-pdf-'+uuid.uuid4().hex[:16];commands=argv(name,mode,page,runtime=selected);deadline=time.monotonic()+45
    def invoke(phase,cleanup=False):
        remaining=15 if cleanup else min(30 if phase=='start' else 15,deadline-time.monotonic());m.require(remaining>0,'operation deadline')
        limit=p.MAX_IMAGE if phase=='start' and mode=='page' else 65536 if phase=='start' else CONTROL_LIMIT
        data=pdf if phase=='start' and mode!='profile' else b'';out,err,row=capture(commands[phase],data,remaining,limit)
        (folder/(phase+'.stdout')).write_bytes(out);(folder/(phase+'.stderr')).write_bytes(err)
        row=dict(argv=commands[phase],stdin_sha256=m.sha(data),**row,stdout_sha256=m.sha(out),stderr_sha256=m.sha(err));(folder/(phase+'.json')).write_bytes(m.encoded(row))
        m.require(type(row['returncode']) is int and row['returncode']==0 and row['error_class'] is None and row['capture_overflow'] is False,'operation process failure');return out
    try:
        image=m.load(invoke('image'));m.require(len(image)==1 and image[0]['Id']==runtime['image_id'] and image[0]['Os']=='linux' and image[0]['Architecture']=='amd64','runtime image identity')
        invoke('create');before=m.load(invoke('before'));m.require(len(before)==1,'container inspect coverage');inspect_config(before[0],name,runtime=selected)
        invoke('start');invoke('after')
    except InterruptedError:
        (folder/'interrupted.json').write_bytes(m.encoded(dict(schema='geek-work-pdf-container-interruption-1',error_class='InterruptedError')))
    except Exception:pass
    finally:
        for phase in ('remove','absence'):
            try:invoke(phase,True)
            except Exception:pass
    result=assessment(folder,name,mode,page,m.sha(pdf),runtime=selected);(folder/'receipt.json').write_bytes(m.encoded(result));return result


def operation_files(root,descriptors,pdf_sha,*,runtime=None,source_pages=None):
    runtime_profile(runtime)
    if source_pages is not None:
        m.require(runtime is not None and type(source_pages) is list and 1<=len(source_pages)<=16 and all(type(n) is int and 1<=n<=100000 for n in source_pages),'selected source page list')
        m.require(source_pages==list(range(source_pages[0],source_pages[-1]+1)),'contiguous source page selection')
    expected_pages=list(range(1,17)) if source_pages is None else source_pages
    files={};receipts=[]
    m.require(type(descriptors) is list and 0<=len(descriptors)<=len(expected_pages)+2,'operation count')
    for i,row in enumerate(descriptors):
        k.obj(row,'folder name mode page');m.require(row['folder']==f'operations/{i:04}' and bool(re.fullmatch(r'geek-work-pdf-[0-9a-f]{16}',row['name'])),'operation path/name')
        mode='profile' if i==0 else 'info' if i==1 else 'page';number=None if i<2 else expected_pages[i-2]
        m.require(row['mode']==mode and type(row['page']) is type(number) and row['page']==number,'operation order')
        folder=root/row['folder'];receipt=assessment(folder,row['name'],mode,number,pdf_sha,runtime=runtime)
        m.require(m.read(folder/'receipt.json')==m.encoded(receipt),'operation receipt reproduction');receipts.append(receipt)
        m.require(i==len(descriptors)-1 or receipt['status']=='completed','execution after failure')
        for path in folder.iterdir():files[row['folder']+'/'+path.name]=m.read(path,p.MAX_IMAGE if path.name=='start.stdout' and mode=='page' else 65536 if path.name in ('start.stdout','start.stderr') or path.name.endswith('.stderr') else CONTROL_LIMIT)
    return receipts,files


def derived(binding,anchor,runtime,descriptors,receipts,files):
    def failure():
        return dict(schema='geek-work-pdf-container-failure-report-1',status='cleanup_failed' if any(not row['container_removed'] for row in receipts) else 'container_render_failed',binding_sha256=anchor,pdf=binding['pdf'],operations=receipts,renderer_execution_independently_verified=False,pdf_visual_review=False,pdf_conformance_verified=False,scientific_verification=False,publication_authorized=False),{}
    if any(row['status']!='completed' for row in receipts):return failure()
    try:
        m.require(len(descriptors)>=2,'missing PDF info operation')
        def streams(index):
            base=descriptors[index]['folder']+'/';err=b''.join(files[base+phase+'.stderr'] for phase in PHASES);m.require(len(err)<=65536,'diagnostic aggregate limit');return files[base+'start.stdout'],err
        info,info_errors=streams(1);count=p.page_count(info);m.require(len(descriptors)==count+2,'container page coverage')
        _,profile_errors=streams(0);info_errors=profile_errors+info_errors;m.require(len(info_errors)<=65536,'diagnostic aggregate limit')
        images={};diagnostics={}
        for i in range(1,count+1):
            out,err=streams(i+1);images[f'{i:04}.png']=out;diagnostics[f'{i:04}.stdout']=b'';diagnostics[f'{i:04}.stderr']=err
        report=p.report(binding,anchor,runtime,info,images,diagnostics,info_errors);report['container_operations']=receipts
        views={'pdfinfo.stdout':info,'pdfinfo.stderr':info_errors,**{'pages/'+n:data for n,data in images.items()},**{'diagnostics/'+n:data for n,data in diagnostics.items()}}
        return report,views
    except ValueError:return failure()


def render(bundle,anchor,renderer_anchor,output):
    p.b.release.g.pre.ops.outside(output,bundle);m.require(not output.exists() and not output.is_symlink(),'new container page output required')
    binding,archive,pdf=p.pdf_input.verified(bundle,anchor);m.require(pdf is not None,'compiled PDF required');m.require(len(pdf)<=profile()['max_pdf_bytes'],'container PDF byte limit')
    runtime=profile();k.digest(renderer_anchor);m.require(m.sha(m.encoded(runtime))==renderer_anchor,'container profile anchor mismatch')
    output.mkdir(parents=True);tree.write_tree(output/'binding',archive);(output/'profile.json').write_bytes(m.encoded(runtime));(output/'operations').mkdir();descriptors=[];started=time.monotonic()
    def step(mode,page=None):
        m.require(time.monotonic()-started<TOTAL_TIMEOUT,'container page loop deadline')
        folder=f'operations/{len(descriptors):04}';receipt=execute(output/folder,mode,pdf if mode!='profile' else b'',page)
        descriptors.append(dict(folder=folder,name=receipt['name'],mode=mode,page=page));return receipt['status']=='completed'
    try:
        if step('profile') and step('info'):
            count=p.page_count(m.read(output/'operations/0001/start.stdout',65536))
            for i in range(1,count+1):
                if not step('page',i):break
    except ValueError:pass
    if not descriptors:(output/'operations').rmdir()
    receipts,operations=operation_files(output,descriptors,m.sha(pdf))
    report,views=derived(binding,anchor,runtime,descriptors,receipts,operations)
    files={'profile.json':m.encoded(runtime),'report.json':m.encoded(report),**{'binding/'+n:data for n,data in archive.items()},**operations,**views}
    for name,data in views.items():
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    m.require(len(files['report.json'])<=m.MAX_ARTIFACT,'container report limit')
    (output/'report.json').write_bytes(files['report.json']);manifest=m.encoded(dict(schema=SCHEMA,binding_sha256=anchor,renderer_profile_sha256=renderer_anchor,operations=descriptors,files={n:m.sha(data) for n,data in files.items()}))
    (output/'manifest.json').write_bytes(manifest);return dict(status=report['status'],manifest_sha256=m.sha(manifest),pdf_visual_review=False)


def verified(bundle,anchor,require_pages=False):
    k.digest(anchor);raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'container page anchor mismatch');manifest=m.load(raw);k.obj(manifest,'schema binding_sha256 renderer_profile_sha256 operations files');m.require(manifest['schema']==SCHEMA,'container page schema')
    binding,archive,pdf=p.pdf_input.verified(bundle/'binding',manifest['binding_sha256']);m.require(pdf is not None and len(pdf)<=profile()['max_pdf_bytes'],'container bound PDF')
    runtime_raw=m.read(bundle/'profile.json');runtime=m.load(runtime_raw);validate_profile(runtime);m.require(runtime_raw==m.encoded(runtime) and m.sha(runtime_raw)==manifest['renderer_profile_sha256'],'container profile binding')
    receipts,operations=operation_files(bundle,manifest['operations'],m.sha(pdf));report,views=derived(binding,manifest['binding_sha256'],runtime,manifest['operations'],receipts,operations)
    files={'profile.json':runtime_raw,'report.json':m.encoded(report),**{'binding/'+n:data for n,data in archive.items()},**operations,**views};m.require(len(files['report.json'])<=m.MAX_ARTIFACT,'container report limit');tree.exact_tree(bundle,set(files)|{'manifest.json'})
    m.require(manifest['files']=={n:m.sha(data) for n,data in files.items()},'container page hashes')
    for name,data in files.items():m.require(m.read(bundle/name,max(len(data),1))==data,'container page reproduction mismatch')
    if require_pages:m.require(report['status']=='pages_ready_for_review','successful container pages required')
    return report,{**files,'manifest.json':raw}


def verify(bundle,anchor):
    report,_=verified(bundle,anchor);return dict(status='page_packet_consistent' if report['status']=='pages_ready_for_review' else 'failure_archive_intact',recorded_status=report['status'],manifest_sha256=anchor,pdf_visual_review=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True);sub.add_parser('profile')
    for action in ('render','verify'):
        q=sub.add_parser(action);q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True)
        if action=='render':q.add_argument('--renderer-sha256',required=True);q.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    def interrupted(signum,frame):raise InterruptedError('operator termination')
    signal.signal(signal.SIGTERM,interrupted)
    if args.action=='profile':result=dict(profile=profile(),profile_sha256=m.sha(m.encoded(profile())),observed_here=False)
    elif args.action=='render':result=render(args.bundle,args.sha256,args.renderer_sha256,args.output)
    else:result=verify(args.bundle,args.sha256)
    print(m.encoded(result).decode(),end='')
    if result.get('status') in {'container_render_failed','cleanup_failed','failure_archive_intact'}:raise SystemExit(2)


if __name__=='__main__':main()
