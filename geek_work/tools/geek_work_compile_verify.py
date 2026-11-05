#!/usr/bin/env python3
"""Verify an anchored compile archive without Docker, compilation or PDF rendering."""
import argparse
import os
from pathlib import Path, PurePosixPath
import re
import stat
import geek_work_manuscript as m
import geek_work_manuscript_claims as k
import geek_work_manuscript_compile as c

MAX_BUNDLE = 48 * 1024 * 1024
MAX_METADATA = 2 * 1024 * 1024
ROOT_FILES = {'request.json','receipt.json','image.json','command.json','container.json',
              'compiler.stdout','compiler.log','document.pdf'}
FAILURES = {'compiler_failed','timeout','oom','capture_limit','artifact_rejected',
            'infrastructure_error','cleanup_failed','snapshot_changed'}
BASE_FIELDS = set('schema request_sha256 status container_name image image_id exit_code oom_killed timed_out container_removed wall_time_ms snapshot_unchanged_at_final_check scientific_verification semantic_claim_check pdf_visual_review limits'.split())
OPTIONAL_FIELDS = {'compile_timeout_seconds','capture_limit_bytes','client_exit_code','error','cleanup_error','prior_status','pdf_sha256'}


def bounded_read(root, name, limit):
    parts = PurePosixPath(name).parts
    fd = None
    try:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(leaf,'rb') as stream:
            m.require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'regular archive file required')
            raw = stream.read(limit+1); m.require(len(raw)<=limit, 'archive file byte limit')
            return raw
    except OSError as error:
        raise ValueError('missing or unsafe archive file: '+name) from error
    finally:
        if fd is not None: os.close(fd)


def file_set(root, expected):
    # Include directory entries too: hidden/empty extra trees and symlinks fail.
    wanted = set(expected) | {'manifest.json'}
    dirs = {str(parent) for name in wanted for parent in PurePosixPath(name).parents} - {'.'}
    found, found_dirs = set(), set()
    def visit(folder, prefix):
        with os.scandir(folder) as entries:
            for entry in entries:
                name = prefix+entry.name
                if entry.is_dir(follow_symlinks=False):
                    m.require(name in dirs, 'unexpected archive directory')
                    found_dirs.add(name); visit(entry.path, name+'/')
                else:
                    m.require(name in wanted and entry.is_file(follow_symlinks=False), 'unexpected/unsafe archive entry')
                    found.add(name)
    m.require(root.is_dir() and not root.is_symlink(), 'regular archive directory required')
    visit(root, '')
    m.require(found==wanted and found_dirs==dirs, 'archive file set mismatch')


def integer(value, expected=None):
    m.require(type(value) is int and (expected is None or value==expected), 'integer metadata mismatch')


def environment(values):
    m.require(type(values) is list, 'environment list')
    result={}
    for value in values:
        m.require(type(value) is str and '=' in value, 'environment entry')
        key,val=value.split('=',1)
        m.require(key not in result, 'duplicate environment key');result[key]=val
    return result


def compiled_profile(data, spec, receipt):
    required = ROOT_FILES
    m.require(required <= set(data), 'missing compiled evidence')
    m.require(set(receipt)==BASE_FIELDS|{'compile_timeout_seconds','capture_limit_bytes','client_exit_code','pdf_sha256'}, 'compiled receipt fields')
    for key in ('exit_code','client_exit_code'):integer(receipt[key],0)
    for key in ('oom_killed','timed_out'):m.require(receipt[key] is False,'compiled failure flag')
    for key in ('container_removed','snapshot_unchanged_at_final_check'):m.require(receipt[key] is True,'compiled completion flag')
    integer(receipt['compile_timeout_seconds'],c.TIMEOUT);integer(receipt['capture_limit_bytes'],c.MAX_PDF)
    k.digest(receipt['pdf_sha256'])
    m.require(receipt['image']==c.IMAGE and receipt['image_id']==c.IMAGE_ID,'receipt image pin')
    pdf=data['document.pdf']
    m.require(pdf.startswith(b'%PDF-') and pdf==data['compiler.stdout'] and m.sha(pdf)==receipt['pdf_sha256'],'PDF/capture binding mismatch')
    m.require(len(pdf)<c.MAX_PDF and len(data['compiler.log'])<c.MAX_PDF,'compiled capture limit')
    image=m.load(data['image.json'])
    m.require(type(image) is list and len(image)==1 and type(image[0]) is dict,'image observation')
    image=image[0]
    m.require(image.get('Id')==c.IMAGE_ID and image.get('Os')=='linux' and image.get('Architecture')=='amd64','observed image identity')
    command=m.load(data['command.json'])
    m.require(type(command) is list and all(type(x) is str for x in command) and command.count('--mount')==1,'command shape')
    idx=command.index('--mount');m.require(idx+1<len(command),'mount argument')
    mount=command[idx+1];prefix='type=bind,src=';suffix=',dst=/src,readonly'
    m.require(mount.startswith(prefix) and mount.endswith(suffix),'read-only snapshot mount')
    old_root=mount[len(prefix):-len(suffix)]
    path=PurePosixPath(old_root)
    m.require(path.is_absolute() and path.as_posix()==old_root and '..' not in path.parts and path.name=='sources','historical snapshot path')
    # Never resolve/stat/access old_root. Compare as inert metadata only.
    expected=c.command_for_path(receipt['container_name'],old_root,spec['entry'])
    m.require(command==expected,'compile command/profile mismatch')
    container=m.load(data['container.json']);m.require(type(container) is dict,'container observation')
    m.require(container.get('Name')=='/'+receipt['container_name'] and container.get('Image')==c.IMAGE_ID,'container identity')
    state=container.get('State');cfg=container.get('Config');host=container.get('HostConfig')
    m.require(all(type(x) is dict for x in (state,cfg,host)),'container sections')
    for key in ('Running','OOMKilled','Paused','Restarting','Dead'):m.require(state.get(key) is False,'container not cleanly exited')
    integer(state.get('ExitCode'),0)
    m.require(state.get('Status')=='exited' and state.get('Error')=='','container exit state')
    m.require(cfg.get('Image')==c.IMAGE and cfg.get('Entrypoint')==['/bin/typst'] and cfg.get('Cmd')==expected[expected.index(c.IMAGE)+1:],'container compiler invocation')
    m.require(cfg.get('User')=='1000:1000' and cfg.get('WorkingDir')=='/src' and cfg.get('Tty') is False and not cfg.get('Volumes'),'container execution config')
    wanted_env={'HOME':'/tmp','TZ':'UTC','SOURCE_DATE_EPOCH':'0','PATH':'/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'}
    m.require(environment(cfg.get('Env'))==wanted_env,'container environment mismatch')
    container_security(host,container.get('Mounts'),old_root,'rw,noexec,nosuid,nodev,size=64m,mode=1777',16777216)
    return old_root


def container_security(host,mounts,old_root,tmpfs,fsize):
    for key,value in {'Memory':536870912,'MemorySwap':536870912,'NanoCpus':2000000000,'PidsLimit':64}.items():integer(host.get(key),value)
    m.require(host.get('NetworkMode')=='none' and host.get('ReadonlyRootfs') is True and host.get('Privileged') is False,'network/root/privilege policy')
    m.require(host.get('CapDrop')==['ALL'] and not host.get('CapAdd') and host.get('SecurityOpt')==['no-new-privileges'],'capability/security policy')
    m.require(host.get('Tmpfs')=={'/tmp':tmpfs},'tmpfs policy')
    m.require(host.get('LogConfig')=={'Type':'none','Config':{}},'daemon logging policy')
    for key in ('Binds','VolumesFrom','Devices','DeviceRequests','DeviceCgroupRules','PortBindings','ExtraHosts','GroupAdd'):
        m.require(not host.get(key),'unexpected host access: '+key)
    m.require(host.get('PidMode')=='' and host.get('IpcMode')=='private' and host.get('UTSMode')=='','namespace policy')
    m.require(host.get('PublishAllPorts') is False,'published ports')
    ulimits=host.get('Ulimits');m.require(type(ulimits) is list and len(ulimits)==2,'ulimit entries')
    limits={}
    for row in ulimits:
        k.obj(row,'Name Soft Hard');m.require(row['Name'] not in limits,'duplicate ulimit')
        integer(row['Soft']);integer(row['Hard']);limits[row['Name']]=(row['Soft'],row['Hard'])
    m.require(limits=={'core':(0,0),'fsize':(fsize,fsize)},'ulimit profile')
    m.require(host.get('Mounts')==[{'ReadOnly':True,'Source':old_root,'Target':'/src','Type':'bind'}] and host['Mounts'][0]['ReadOnly'] is True,'configured mounts')
    m.require(type(mounts) is list and len(mounts)==1,'observed mounts')
    m.require(all(mounts[0].get(key)==value for key,value in {'Type':'bind','Source':old_root,'Destination':'/src','Propagation':'rprivate'}.items()) and mounts[0].get('RW') is False,'observed read-only mount')


def verified(bundle, anchor):
    k.digest(anchor)
    raw=bounded_read(bundle,'manifest.json',MAX_METADATA)
    m.require(m.sha(raw)==anchor,'manifest anchor mismatch')
    manifest=m.load(raw);k.obj(manifest,'schema files')
    m.require(manifest['schema']=='geek-work-manuscript-compile-manifest-1' and type(manifest['files']) is dict,'manifest schema')
    hashes=manifest['files'];m.require(3<=len(hashes)<=40,'manifest file count')
    for name,h in hashes.items():
        k.digest(h)
        m.require(name in ROOT_FILES or name.startswith('sources/'),'unexpected manifest path')
        if name.startswith('sources/'):k.path_name(name[len('sources/'):])
    file_set(bundle,hashes)
    data,total={},0
    for name,h in hashes.items():
        limit=c.MAX_FILE if name.startswith('sources/') else c.MAX_PDF if name in {'document.pdf','compiler.stdout','compiler.log'} else MAX_METADATA
        blob=bounded_read(bundle,name,limit);total+=len(blob);m.require(total<=MAX_BUNDLE,'bundle byte limit')
        m.require(m.sha(blob)==h,'artifact hash mismatch: '+name);data[name]=blob
    m.require({'request.json','receipt.json'}<=set(data),'missing request or receipt')
    spec=c.request(m.load(data['request.json']))
    expected={'sources/'+row['path'] for row in spec['files']}
    m.require({n for n in data if n.startswith('sources/')}==expected,'selected source set mismatch')
    source_total=sum(len(data[n]) for n in expected);m.require(source_total<=c.MAX_TOTAL,'source byte limit')
    for row in spec['files']:
        if row['path'].endswith('.typ'):m.source(data['sources/'+row['path']])
    source_matches=all(m.sha(data['sources/'+row['path']])==row['sha256'] for row in spec['files'])
    receipt=m.load(data['receipt.json'])
    m.require(type(receipt) is dict and BASE_FIELDS<=set(receipt)<=BASE_FIELDS|OPTIONAL_FIELDS,'receipt fields')
    m.require(receipt['schema']=='geek-work-manuscript-compile-receipt-1','receipt schema')
    m.require(type(receipt['status']) is str and receipt['status'] in FAILURES|{'compiled'},'receipt status')
    m.require(type(receipt['container_name']) is str and re.fullmatch('geek-work-typeset-[0-9a-f]{32}',receipt['container_name']),'container name')
    m.require(receipt['request_sha256']==m.sha(data['request.json']),'request/receipt mismatch')
    for key in ('scientific_verification','semantic_claim_check','pdf_visual_review'):m.require(receipt[key] is False,'unsupported verification promotion')
    for key in ('timed_out','container_removed','snapshot_unchanged_at_final_check'):m.require(type(receipt[key]) is bool,'boolean receipt field')
    m.require(receipt['oom_killed'] is None or type(receipt['oom_killed']) is bool,'OOM field')
    for key in ('exit_code','client_exit_code'):
        if receipt.get(key) is not None:integer(receipt[key])
    integer(receipt['wall_time_ms']);m.require(receipt['wall_time_ms']>=0,'elapsed time');k.text(receipt['limits'])
    m.require(receipt['image']==c.IMAGE and receipt['image_id']==c.IMAGE_ID,'receipt image pin')
    for key in ('error','cleanup_error'):
        if key in receipt:m.require(type(receipt[key]) is str and len(receipt[key])<=4000,'error metadata')
    if 'prior_status' in receipt:m.require(type(receipt['prior_status']) is str and receipt['prior_status'] in FAILURES|{'compiled'},'prior status')
    if 'pdf_sha256' in receipt:k.digest(receipt['pdf_sha256'])
    compiled=receipt['status']=='compiled'
    if compiled:
        m.require(source_matches,'compiled source/request mismatch')
        compiled_profile(data,spec,receipt)
    result=dict(schema='geek-work-compile-archive-check-1',
                status='compiled_bundle_consistent' if compiled else 'failure_archive_intact',
                manifest_sha256=anchor, recorded_status=receipt['status'], files=len(data),
                snapshot_matches_request=source_matches, compiled_profile_checked=compiled,
                cleanup_reported=receipt['container_removed'], live_cleanup_checked=False,
                compilation_replayed=False, artifact_authenticity_verified=False,
                pdf_conformance_verified=False, pdf_visual_review=False, scientific_verification=False,
                limits='Anchored bytes and recorded success-profile consistency only. Failure archives receive integrity/schema checks, not execution-state qualification. No Docker calls, original-root access, compilation, signature verification or independent proof of historical execution/cleanup.')

    return result,{**data,'manifest.json':raw}


def verify(bundle,anchor):
    result,_=verified(bundle,anchor)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--sha256',required=True)
    a=p.parse_args();result=verify(a.bundle,a.sha256);print(m.encoded(result).decode(),end='')
    if result['status']!='compiled_bundle_consistent':raise SystemExit(2)


if __name__=='__main__':main()
