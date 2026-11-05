#!/usr/bin/env python3
"""Check a pinned LaTeX compile archive offline; never replay its compiler."""
import argparse
from pathlib import Path, PurePosixPath
import re
import geek_work_manuscript as m
import geek_work_manuscript_claims as k
import geek_work_latex_compile as c
import geek_work_compile_verify as v

MAX_BUNDLE = 128 * 1024 * 1024
ROOT_FILES = {'request.json','runtime.json','receipt.json','image.json','command.json',
              'container.json','worker.stdout','worker.stderr'}
ARTIFACTS = c.OUTPUTS | {'pass-1.log','pass-2.log'}
FAILURES = v.FAILURES | {'worker_failed'}
COMPILED = {'compiled','compiled_with_warnings'}
BASE_FIELDS = set('schema request_sha256 status image_id container_name container_removed timed_out oom_killed worker_exit_code wall_time_ms snapshot_unchanged_at_final_check compile_timeout_seconds shell_escape_enabled scientific_verification pdf_visual_review limits'.split())
OPTIONAL_FIELDS = set('client_exit_code error cleanup_error prior_status engine_exit_codes diagnostics_review_required pdf_sha256'.split())
SUCCESS_FIELDS = BASE_FIELDS | set('client_exit_code engine_exit_codes diagnostics_review_required pdf_sha256'.split())
ENV = {'PYTHONDONTWRITEBYTECODE':'1',
       'PATH':'/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
       'LANG':'C.UTF-8','GPG_KEY':'7169605F62C751356D054A26A821E680E5FA6305',
       'PYTHON_VERSION':'3.12.16',
       'PYTHON_SHA256':'b5796915dc45ff745cfb4e990a7e7c93d6f546328a102ce31448d69ebc37575c'}


def receipt_check(receipt,request_raw,runtime):
    m.require(type(receipt) is dict and BASE_FIELDS<=set(receipt)<=BASE_FIELDS|OPTIONAL_FIELDS,'receipt fields')
    m.require(receipt['schema']=='geek-work-latex-compile-receipt-1','receipt schema')
    m.require(type(receipt['status']) is str and receipt['status'] in FAILURES|COMPILED,'receipt status')
    m.require(receipt['request_sha256']==m.sha(request_raw),'request/receipt mismatch')
    m.require(receipt['image_id']==runtime['image_id'],'receipt image pin')
    m.require(type(receipt['container_name']) is str and re.fullmatch('geek-work-latex-[0-9a-f]{32}',receipt['container_name']),'container name')
    for key in ('shell_escape_enabled','scientific_verification','pdf_visual_review'):
        m.require(receipt[key] is False,'unsupported verification or shell promotion')
    for key in ('timed_out','container_removed','snapshot_unchanged_at_final_check'):
        m.require(type(receipt[key]) is bool,'boolean receipt field')
    m.require(receipt['oom_killed'] is None or type(receipt['oom_killed']) is bool,'OOM field')
    for key in ('worker_exit_code','client_exit_code'):
        if receipt.get(key) is not None:v.integer(receipt[key])
    v.integer(receipt['compile_timeout_seconds'],c.TIMEOUT)
    v.integer(receipt['wall_time_ms']);m.require(receipt['wall_time_ms']>=0,'elapsed time');k.text(receipt['limits'])
    for key in ('error','cleanup_error'):
        if key in receipt:m.require(type(receipt[key]) is str and len(receipt[key])<=4000,'error metadata')
    if 'prior_status' in receipt:m.require(type(receipt['prior_status']) is str and receipt['prior_status'] in FAILURES|COMPILED,'prior status')
    if 'pdf_sha256' in receipt:k.digest(receipt['pdf_sha256'])
    if 'diagnostics_review_required' in receipt:m.require(type(receipt['diagnostics_review_required']) is bool,'diagnostic flag')
    if 'engine_exit_codes' in receipt:
        for code in k.rows(receipt['engine_exit_codes'],2,1):v.integer(code)


def compiled_profile(data,spec,receipt,runtime):
    m.require(set(receipt)==SUCCESS_FIELDS,'compiled receipt fields')
    m.require(ROOT_FILES<=set(data),'missing compiled evidence')
    for key in ('worker_exit_code','client_exit_code'):v.integer(receipt[key],0)
    for key in ('timed_out','oom_killed'):m.require(receipt[key] is False,'compiled failure flag')
    for key in ('container_removed','snapshot_unchanged_at_final_check'):m.require(receipt[key] is True,'compiled completion flag')
    m.require(len(data['worker.stderr'])<c.CAPTURE,'compiled capture limit')
    decoded,artifacts=c.decode_envelope(data['worker.stdout'])
    for key in ('status','engine_exit_codes','diagnostics_review_required','pdf_sha256'):
        m.require(decoded.get(key)==receipt[key],'worker/receipt mismatch: '+key)
    expected_artifacts={'artifacts/'+n:b for n,b in artifacts.items()}
    m.require({n:b for n,b in data.items() if n.startswith('artifacts/')}==expected_artifacts,'worker/artifact binding mismatch')
    image=m.load(data['image.json'])
    m.require(type(image) is list and len(image)==1 and type(image[0]) is dict,'image observation')
    image_id=runtime['image_id']
    m.require(image[0].get('Id')==image_id and image[0].get('Os')=='linux' and image[0].get('Architecture')=='amd64','observed image identity')
    command=m.load(data['command.json'])
    m.require(type(command) is list and all(type(x) is str for x in command) and command.count('--mount')==1,'command shape')
    i=command.index('--mount');m.require(i+1<len(command),'mount argument')
    mount=command[i+1];prefix='type=bind,src=';suffix=',dst=/src,readonly'
    m.require(mount.startswith(prefix) and mount.endswith(suffix),'read-only snapshot mount')
    old_root=mount[len(prefix):-len(suffix)];path=PurePosixPath(old_root)
    m.require(path.is_absolute() and path.as_posix()==old_root and '..' not in path.parts and path.name=='sources','historical snapshot path')
    # old_root is compared as inert text; never resolve, stat or open it.
    expected=c.command_for_path(receipt['container_name'],old_root,spec['entry'],image_id)
    m.require(command==expected,'compile command/profile mismatch')
    container=m.load(data['container.json']);m.require(type(container) is dict,'container observation')
    m.require(container.get('Name')=='/'+receipt['container_name'] and container.get('Image')==image_id,'container identity')
    state=container.get('State');cfg=container.get('Config');host=container.get('HostConfig')
    m.require(all(type(x) is dict for x in (state,cfg,host)),'container sections')
    for key in ('Running','OOMKilled','Paused','Restarting','Dead'):m.require(state.get(key) is False,'container not cleanly exited')
    v.integer(state.get('ExitCode'),0)
    m.require(state.get('Status')=='exited' and state.get('Error')=='','container exit state')
    args=['-B','/opt/worker.py',spec['entry']]
    m.require(cfg.get('Image')==image_id and cfg.get('Entrypoint')==['/usr/local/bin/python'] and cfg.get('Cmd')==args,'container worker invocation')
    m.require(container.get('Path')=='/usr/local/bin/python' and container.get('Args')==args,'observed process invocation')
    m.require(cfg.get('User')=='1000:1000' and cfg.get('WorkingDir')=='/src' and cfg.get('Tty') is False and not cfg.get('Volumes'),'container execution config')
    m.require(v.environment(cfg.get('Env'))==ENV,'container environment mismatch')
    v.container_security(host,container.get('Mounts'),old_root,'rw,noexec,nosuid,nodev,size=96m,mode=1777',8388608)


def verified(bundle,anchor):
    k.digest(anchor);raw=v.bounded_read(bundle,'manifest.json',v.MAX_METADATA)
    m.require(m.sha(raw)==anchor,'manifest anchor mismatch')
    manifest=m.load(raw);k.obj(manifest,'schema files')
    m.require(manifest['schema']=='geek-work-latex-compile-manifest-1' and type(manifest['files']) is dict,'manifest schema')
    hashes=manifest['files'];m.require(4<=len(hashes)<=46,'manifest file count')
    for name,h in hashes.items():
        k.digest(h)
        m.require(name in ROOT_FILES or name in {'artifacts/'+n for n in ARTIFACTS} or name.startswith('sources/'),'unexpected manifest path')
        if name.startswith('sources/'):k.path_name(name[len('sources/'):])
    v.file_set(bundle,hashes);data={};total=0
    for name,h in hashes.items():
        limit=c.common.MAX_FILE if name.startswith('sources/') else c.MAX_OUTPUT if name.startswith('artifacts/') else c.CAPTURE if name in {'worker.stdout','worker.stderr'} else v.MAX_METADATA
        blob=v.bounded_read(bundle,name,limit);total+=len(blob);m.require(total<=MAX_BUNDLE,'bundle byte limit')
        m.require(m.sha(blob)==h,'artifact hash mismatch: '+name);data[name]=blob
    m.require({'request.json','runtime.json','receipt.json'}<=set(data),'missing request/runtime/receipt')
    runtime=c.profile();m.require(m.load(data['runtime.json'])==runtime,'unsupported runtime profile')
    spec=c.request(m.load(data['request.json']));selected={'sources/'+r['path'] for r in spec['files']}
    m.require({n for n in data if n.startswith('sources/')}==selected,'selected source set mismatch')
    m.require(sum(len(data[n]) for n in selected)<=c.common.MAX_TOTAL,'source byte limit')
    for row in spec['files']:
        if Path(row['path']).suffix in {'.tex','.bib','.sty','.cls'}:m.source(data['sources/'+row['path']])
    matches=all(m.sha(data['sources/'+r['path']])==r['sha256'] for r in spec['files'])
    receipt=m.load(data['receipt.json']);receipt_check(receipt,data['request.json'],runtime)
    compiled=receipt['status'] in COMPILED
    if compiled:
        m.require(matches,'compiled source/request mismatch');compiled_profile(data,spec,receipt,runtime)
    status={'compiled':'compiled_bundle_consistent','compiled_with_warnings':'warning_bundle_consistent'}.get(receipt['status'],'failure_archive_intact')
    result=dict(schema='geek-work-latex-archive-check-1',status=status,manifest_sha256=anchor,
                recorded_status=receipt['status'],files=len(data),snapshot_matches_request=matches,
                compiled_profile_checked=compiled,diagnostics_review_required=receipt.get('diagnostics_review_required'),
                cleanup_reported=receipt['container_removed'],live_cleanup_checked=False,
                compilation_replayed=False,artifact_authenticity_verified=False,pdf_conformance_verified=False,
                pdf_visual_review=False,scientific_verification=False,
                limits='Anchored bytes and recorded profile consistency only. Warning archives require review; failure archives receive integrity/schema checks only. No Docker, original-root access, compiler replay, signature verification or independent attestation of execution/cleanup.')

    return result,{**data,'manifest.json':raw}


def verify(bundle,anchor):
    result,_=verified(bundle,anchor)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--sha256',required=True)
    a=p.parse_args();r=verify(a.bundle,a.sha256);print(m.encoded(r).decode(),end='')
    if r['status']!='compiled_bundle_consistent':raise SystemExit(2)


if __name__=='__main__':main()
