#!/usr/bin/env python3
"""Export a preflight-bound Git patch using disposable objects and index only."""
import argparse
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import geek_work_operation_preflight as pre

m=pre.m
MAX_PATCH=32*1024*1024


def git_environment():
    env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,GIT_NO_REPLACE_OBJECTS='1',GIT_TERMINAL_PROMPT='0',GIT_NO_LAZY_FETCH='1',LC_ALL='C')
    return env


def git(args,env,cwd=None,data=None,limit=m.MAX_ARTIFACT):
    executable=shutil.which('git');m.require(executable is not None,'Git executable required')
    with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err:
        r=subprocess.run([executable,'--literal-pathspecs','-c','core.fsmonitor=false','-c','core.hooksPath=/dev/null',*args],input=data,stdout=out,stderr=err,cwd=cwd,env=env,timeout=30)
        out.seek(0);raw=out.read(limit+1);err.seek(0);error=err.read(4096)
    m.require(r.returncode==0,'Git command failed: '+error.decode('utf-8','replace'))
    m.require(len(raw)<=limit,'Git output byte limit');return raw


def construct(repo,commit,report,payload,receipt):
    m.require(type(commit) is str and re.fullmatch('[0-9a-f]{40}',commit),'full SHA-1 base commit required')
    env=git_environment();repo=repo.resolve()
    m.require(git(['rev-parse','--show-object-format'],env,repo).strip()==b'sha1','only SHA-1 Git repositories supported')
    objects=git(['rev-parse','--path-format=absolute','--git-path','objects'],env,repo).decode().strip()
    m.require(not any(c in objects for c in ':\n\r'),'unsupported object directory path')
    with tempfile.TemporaryDirectory(prefix='geek-work-git-') as tmp:
        tmp=Path(tmp);store=tmp/'repo.git';work=tmp/'work';work.mkdir()
        git(['init','--bare','--template=','--object-format=sha1',str(store)],env)
        env.update(GIT_DIR=str(store),GIT_WORK_TREE=str(work),GIT_INDEX_FILE=str(tmp/'index'),GIT_ALTERNATE_OBJECT_DIRECTORIES=objects)
        m.require(git(['cat-file','-t',commit],env).strip()==b'commit','base object must be a commit')
        base_tree=git(['rev-parse',commit+'^{tree}'],env).decode().strip();modes={}
        for name,expected in report['baseline'].items():
            pre.k.path_name(name)
            for ancestor in PurePosixPath(name).parents:
                if str(ancestor)=='.':continue
                row=git(['ls-tree','-z',commit,'--',str(ancestor)],env)
                m.require(not row or row.startswith(b'040000 tree '),'baseline parent is not a Git directory')
            row=git(['ls-tree','-z',commit,'--',name],env)
            if expected is None:
                m.require(not row,'GIT_BASE_MISMATCH: expected absence: '+name);modes[name]=None;continue
            m.require(row and row.endswith(b'\0') and row.count(b'\0')==1,'GIT_BASE_MISMATCH: missing file: '+name)
            meta,path=row[:-1].split(b'\t',1);mode,kind,oid=meta.decode().split()
            m.require(path.decode()==name and mode in {'100644','100755'} and kind=='blob','regular Git blob required: '+name)
            size=int(git(['cat-file','-s',oid],env));m.require(size<=pre.ops.MAX_FILE,'Git blob byte limit')
            blob=git(['cat-file','blob',oid],env,limit=pre.ops.MAX_FILE)
            m.require(m.sha(blob)==expected['sha256'] and len(blob)==expected['bytes'],'GIT_BASE_MISMATCH: '+name);modes[name]=mode
        git(['read-tree',commit],env)
        changes=[]
        for removed in receipt['removals']:changes.append(b'0 '+b'0'*40+b'\t'+removed['path'].encode()+b'\0')
        for name in sorted(receipt['writes']):
            mode=modes.get(name)
            if mode is None:
                # Renames preserve the source executable bit; creates are non-executable.
                mode=next((modes[r['operation']['source']] for r in receipt['operations'] if r['operation']['op']=='rename' and r['operation']['target']==name),'100644')
            oid=git(['hash-object','-w','--no-filters','--stdin'],env,data=payload['result/'+name]).strip()
            changes.append(mode.encode()+b' '+oid+b'\t'+name.encode()+b'\0')
        if changes:git(['update-index','-z','--index-info'],env,data=b''.join(changes))
        result_tree=git(['write-tree'],env).decode().strip()
        patch=git(['diff-tree','-p','--binary','--full-index','--no-renames','--no-ext-diff','--no-textconv','--src-prefix=a/','--dst-prefix=b/',base_tree,result_tree,'--'],env,limit=MAX_PATCH)
        git(['read-tree',commit],env)
        if patch:
            git(['apply','--cached','--binary','--whitespace=nowarn','--check','-'],env,data=patch)
            git(['apply','--cached','--binary','--whitespace=nowarn','-'],env,data=patch)
        m.require(git(['write-tree'],env).decode().strip()==result_tree,'patch replay tree mismatch')
        result=dict(schema='geek-work-operation-git-receipt-1',status='patch_ready' if patch else 'no_changes',base_commit=commit,base_tree=base_tree,result_tree=result_tree,
            git_version=git(['--version'],env).decode().strip(),git_object_format='sha1',baseline_modes=modes,patch_sha256=m.sha(patch),patch_bytes=len(patch),
            isolated_index_replay=True,live_project_modified=False,source_index_modified=False,source_objects_written=False,refs_updated=False,
            compilation_verified=False,scientific_verification=False,
            limits='Pinned commit tree, not live worktree state. Temporary index/object store; no commit, live apply or publication. Literal preflight only. Git executable, host and local object database trusted; no independent historical execution attestation.')
    return patch,result


def inputs(bundle,anchor):
    report,archive=pre.verified(bundle,anchor)
    m.require(report['status']=='no_findings_in_supported_subset','preflight review required')
    payload,receipt,_=pre.ops.verified_decision(bundle/'decision',report['decision_sha256'])
    return report,archive,payload,receipt


def stage(bundle,anchor,repo,commit,output):
    pre.ops.outside(output,bundle,repo)
    report,archive,payload,receipt=inputs(bundle,anchor)
    patch,result=construct(repo,commit,report,payload,receipt);result['preflight_sha256']=anchor
    files={'patch.diff':patch,'receipt.json':m.encoded(result),**{'preflight/'+n:x for n,x in archive.items()}}
    manifest=m.encoded(dict(schema='geek-work-operation-git-bundle-1',preflight_sha256=anchor,files={n:m.sha(x) for n,x in files.items()}))
    pre.tree.write_tree(output,{**files,'manifest.json':manifest})
    return dict(status=result['status'],manifest_sha256=m.sha(manifest),base_commit=commit,result_tree=result['result_tree'],live_project_modified=False)


def verified(bundle,anchor,repo):
    pre.k.digest(anchor);m.require(bundle.is_dir() and not bundle.is_symlink(),'regular Git bundle directory')
    raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'manifest anchor mismatch');manifest=m.load(raw)
    pre.k.obj(manifest,'schema preflight_sha256 files');m.require(manifest['schema']=='geek-work-operation-git-bundle-1','Git bundle schema')
    report,archive,payload,receipt=inputs(bundle/'preflight',manifest['preflight_sha256'])
    files={'preflight/'+n:x for n,x in archive.items()}
    files.update({'patch.diff':m.read(bundle/'patch.diff',MAX_PATCH),'receipt.json':m.read(bundle/'receipt.json')})
    pre.tree.exact_tree(bundle,set(files)|{'manifest.json'})
    m.require(manifest['files']=={n:m.sha(x) for n,x in files.items()},'Git bundle file hashes')
    stored=m.load(files['receipt.json']);m.require(type(stored) is dict and 'base_commit' in stored,'receipt shape')
    patch,result=construct(repo,stored['base_commit'],report,payload,receipt);result['preflight_sha256']=manifest['preflight_sha256']
    m.require(files['patch.diff']==patch and files['receipt.json']==m.encoded(result),'Git reproduction mismatch')
    return result,{**files,'manifest.json':raw}


def verify(bundle,anchor,repo):
    result,_=verified(bundle,anchor,repo)
    return dict(status=result['status'],manifest_sha256=anchor,result_tree=result['result_tree'],reproduced=True,live_project_modified=False,historical_execution_verified=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    q=sub.add_parser('stage')
    for name in ('preflight','repo','output'):q.add_argument('--'+name,type=Path,required=True)
    for name in ('preflight-sha256','base-commit'):q.add_argument('--'+name,required=True)
    q=sub.add_parser('verify')
    for name in ('bundle','repo'):q.add_argument('--'+name,type=Path,required=True)
    q.add_argument('--sha256',required=True);a=parser.parse_args()
    result=stage(a.preflight,a.preflight_sha256,a.repo,a.base_commit,a.output) if a.action=='stage' else verify(a.bundle,a.sha256,a.repo)
    print(m.encoded(result).decode(),end='')


if __name__=='__main__':main()
