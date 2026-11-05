#!/usr/bin/env python3
"""Portable, offline replay of the bounded typed ALCC pilot. Does not run archived code."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys

import geek_work_alcc_tasks as tasks

SOURCE_COMMIT='5ac42501622b66a69d2598d27c0a26b66ce31d95'
PREFIX='digital-brain/evaluation/alcc-full-task/'
LAUNCHER="import resource,os; resource.setrlimit(resource.RLIMIT_AS,(4294967296,4294967296)); os.execv('/app/bench',['/app/bench'])"
LIMITS={'Memory':1073741824,'MemorySwap':1073741824,'NanoCpus':1000000000,
        'Privileged':False,'PublishAllPorts':False,'PidMode':'','IpcMode':'private',
        'Tmpfs':{'/tmp':'rw,noexec,nosuid,size=16777216'},'Binds':None,'Devices':[],'DeviceRequests':None,
        'PidsLimit':64,'NetworkMode':'none','ReadonlyRootfs':True,
        'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges'],
        'Ulimits':[{'Name':'cpu','Hard':120,'Soft':120}]}
RUN_FILES=('stdout.jsonl','stderr.txt','transport.json','inspect-before.json',
           'inspect-after.json','cleanup.json','result.json')
ROOT_FILES={'plan.json','build.json','binary','original-oracle.py','corpus.json',
            'adapter.lean','contract.md','origin.json','current-oracle.py',
            'generated.c','link-input-hashes.json','kernel.lean','cached.lean','lean-toolchain','lake-manifest.json'}
FILES=ROOT_FILES|{f'run-{i:03}/{name}' for i in (1,2) for name in RUN_FILES}
MAX_BYTES=512*1024**2


def require(ok,reason):
    if not ok:raise ValueError(reason)


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def json_load(path):
    p=Path(path);require(p.stat().st_size<=8*1024**2,'resource_limit:json')
    def unique(pairs):
        d={}
        for k,v in pairs:
            require(k not in d,'duplicate_key');d[k]=v
        return d
    return json.loads(p.read_text(),object_pairs_hook=unique,
                      parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite')))


def relative(name):
    require(type(name) is str and name and '\\' not in name and
            not PurePosixPath(name).is_absolute() and
            all(x not in ('','.','..') for x in name.split('/')),'unsafe_path')
    return name


def file_at(root,name):
    name=relative(name);p=root
    for part in name.split('/'):
        p=p/part;require(not p.is_symlink(),'symlink')
    require(p.is_file(),'missing_file:'+name)
    return p


def check_files(root, expected):
    require(type(expected) is dict and 0<len(expected)<=256,'file_count')
    total=0
    for name,h in expected.items():
        require(type(h) is str and re.fullmatch('[0-9a-f]{64}',h),'invalid_sha')
        p=file_at(root,name);total+=p.stat().st_size
        require(total<=MAX_BYTES,'resource_limit:total')
        require(sha(p)==h,'hash_mismatch:'+name)


def seal(root):
    manifest={'schema':'geek-work-alcc-replay-bundle-1',
              'files':{name:sha(file_at(root,name)) for name in sorted(FILES)}}
    p=root/'manifest.json'
    with p.open('xb') as f:f.write(tasks.canonical(manifest)+b'\n')
    return sha(p)


def verify(root, expected_manifest_sha):
    root=Path(root);require(not root.is_symlink(),'symlink_root')
    manifest=file_at(root,'manifest.json')
    require(sha(manifest)==expected_manifest_sha,'external_anchor_mismatch')
    m=json_load(manifest)
    require(set(m)=={'schema','files'} and m['schema']=='geek-work-alcc-replay-bundle-1','manifest_schema')
    require(set(m['files'])==FILES,'manifest_files')
    actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() or p.is_symlink()}
    require(actual==FILES|{'manifest.json'},'unexpected_files')
    check_files(root,m['files'])
    require(sha(root/'current-oracle.py')==sha(tasks.__file__),'oracle_version_mismatch')
    plan=json_load(root/'plan.json');require(set(plan)=={'pins','image','repeats'},'plan_schema')
    require(type(plan['repeats']) is int and plan['repeats']==2,'repeats')
    mapping={'.local/quantum-alcc-evidence/alcc-full-task':'binary',
             'digital-brain/tools/geek_work_alcc_tasks.py':'original-oracle.py',
             PREFIX+'corpus.json':'corpus.json',PREFIX+'AlccFullTaskBench.lean':'adapter.lean',
             PREFIX+'CONTRACT.ru.md':'contract.md'}
    require(set(plan['pins'])==set(mapping),'plan_pins')
    for old,new in mapping.items():require(plan['pins'][old]==sha(root/new),'plan_binding:'+new)
    build=json_load(root/'build.json')
    require(build['binary_sha256']==sha(root/'binary') and build['source_sha256']==sha(root/'adapter.lean'),'build_binding')
    origin=json_load(root/'origin.json')
    require(origin['source_commit']==SOURCE_COMMIT,'source_commit')
    require(type(origin['archive_manifest_sha256']) is str and re.fullmatch('[0-9a-f]{64}',origin['archive_manifest_sha256']),'archive_sha')
    c=json_load(root/'corpus.json');require(c==tasks.corpus(),'corpus_contract')
    results=[];names=set()
    for i in (1,2):
        run=root/f'run-{i:03}'
        transport=json_load(run/'transport.json')
        require(transport.get('issue') is None and type(transport.get('exit_code')) is int and transport['exit_code']==0,'transport_failure')
        require(type(transport.get('wall_time_ms')) is int and 0<=transport['wall_time_ms']<=180000,'wall_limit')
        require((run/'stdout.jsonl').stat().st_size+(run/'stderr.txt').stat().st_size<=1048576,'output_limit')
        before=json_load(run/'inspect-before.json');after=json_load(run/'inspect-after.json')
        require(before['Id']==after['Id'] and before['Name']==after['Name'],'container_identity')
        require(before['Id'] not in names,'container_reused');names.add(before['Id'])
        for info in (before,after):
            require(info['Image']==plan['image'],'image_mismatch')
            h=info['HostConfig']
            require(all(tasks.canonical(h.get(k))==tasks.canonical(v) for k,v in LIMITS.items()),'container_limits')
            mounts=h.get('Mounts');require(type(mounts) is list and len(mounts)==1,'mount_count')
            mount=mounts[0]
            require(mount.get('Type')=='bind' and mount.get('Target')=='/app/bench' and mount.get('ReadOnly') is True,'writable_mount')
            cfg=info['Config'];require(cfg['User']=='65534:65534','user')
            require(cfg['Entrypoint']==['/usr/local/bin/python3'] and cfg['Cmd']==['-I','-c',LAUNCHER],'launcher')
            require([v for v in cfg['Env'] if v.startswith('LEAN_')]==['LEAN_NUM_THREADS=0','LEAN_STACK_SIZE_KB=8192'],'lean_environment')
        # Docker28 reports OomKillDisable false before start and null after exit.
        # Both mean no enabled disable flag; true remains forbidden.
        for info in (before,after):require(info['HostConfig'].get('OomKillDisable') is None or info['HostConfig'].get('OomKillDisable') is False,'oom_kill_disabled')
        bhost={k:v for k,v in before['HostConfig'].items() if k!='OomKillDisable'}
        ahost={k:v for k,v in after['HostConfig'].items() if k!='OomKillDisable'}
        require(bhost==ahost and before['Config']==after['Config'],'config_changed')
        require(before['State']['Status']=='created' and before['State']['Running'] is False,'initial_state')
        state=after['State'];require(state['Status']=='exited' and state['Running'] is False and state['OOMKilled'] is False and type(state['ExitCode']) is int and state['ExitCode']==0,'final_state')
        cleanup=json_load(run/'cleanup.json')
        require(cleanup=={'name':before['Name'].lstrip('/'),'removed':True},'cleanup')
        result=tasks.validate(c,(run/'stdout.jsonl').read_text())
        require(result==json_load(run/'result.json'),'saved_result_mismatch')
        results.append(result)
    return dict(schema='geek-work-alcc-replay-report-1',status='ARCHIVE_REPLAY_MATCH',
                manifest_sha256=expected_manifest_sha,recorded_runs=2,
                full_outputs_checked=sum(r['full_outputs_checked'] for r in results),
                recorded_timed_samples=288,verifier_sha256=sha(__file__),oracle_sha256=sha(tasks.__file__),
                native_executions=0,new_model_calls=0,lean_builds=0,
                performance_qualified=False,independent_audit_completed=False,
                scope='Checks preserved bytes, recorded configuration and exact residuals. Not authenticated OS evidence, new timing, source-to-binary proof, or independent scientific review.')


def pack(archive, archive_sha, repo, output):
    archive=Path(archive);output=Path(output)
    require(not output.exists(),'output_exists')
    require(not archive.is_symlink(),'symlink_root')
    manifest=file_at(archive,'MANIFEST.sha256')
    require(sha(manifest)==archive_sha,'archive_anchor_mismatch')
    require(manifest.stat().st_size<=1024*1024,'resource_limit:manifest')
    entries={}
    for line in manifest.read_text().splitlines():
        h,name=line.split('  ',1);require(name not in entries,'duplicate_path');entries[name]=h
    check_files(archive,entries)
    # Inputs are a specific historical archive and exact Git blobs, never supplied labels.
    selected={'frozen-run-plan.json':'plan.json','build.json':'build.json',
              'alcc-full-task':'binary','oracle-at-native-run.py':'original-oracle.py',
              'adapter.c':'generated.c','link-input-hashes.json':'link-input-hashes.json',
              'import-snapshot/AlgebraicCertificateKernel.lean':'kernel.lean',
              'import-snapshot/AlgebraicCertificateNormalizeCached.lean':'cached.lean',
              'import-snapshot/lean-toolchain':'lean-toolchain','import-snapshot/lake-manifest.json':'lake-manifest.json'}
    selected.update({f'run-{i:03}/{n}':f'run-{i:03}/{n}' for i in (1,2) for n in RUN_FILES})
    require(set(selected)<=set(entries),'missing_archived_input')
    sources={}
    for old,new in [('corpus.json','corpus.json'),('AlccFullTaskBench.lean','adapter.lean'),('CONTRACT.ru.md','contract.md')]:
        sources[new]=subprocess.check_output(['git','-C',str(repo),'show',SOURCE_COMMIT+':'+PREFIX+old],timeout=15)
    output.mkdir(parents=True,exist_ok=False)
    for old,new in selected.items():
        p=output/new;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(file_at(archive,old),p)
    for new,b in sources.items():(output/new).write_bytes(b)
    shutil.copyfile(tasks.__file__,output/'current-oracle.py')
    (output/'origin.json').write_bytes(tasks.canonical(dict(source_commit=SOURCE_COMMIT,archive_manifest_sha256=archive_sha))+b'\n')
    h=seal(output)
    return verify(output,h)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='cmd',required=True)
    v=sub.add_parser('verify');v.add_argument('bundle',type=Path);v.add_argument('--expected-manifest-sha256',required=True)
    x=sub.add_parser('pack');x.add_argument('archive',type=Path);x.add_argument('--archive-manifest-sha256',required=True);x.add_argument('--repo',required=True,type=Path);x.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    try:
        r=verify(a.bundle,a.expected_manifest_sha256) if a.cmd=='verify' else pack(a.archive,a.archive_manifest_sha256,a.repo,a.output)
        print(json.dumps(r,indent=2));return 0
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as e:
        print(json.dumps(dict(status='REJECTED',reason=str(e))));return 2


if __name__=='__main__':sys.exit(main())
