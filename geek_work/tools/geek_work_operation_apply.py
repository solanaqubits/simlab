#!/usr/bin/env python3
"""Prepare, apply and recover bounded manuscript worktree edits; leave Git index/refs unchanged."""
import argparse
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path, PurePosixPath
import re
import stat
import uuid
import geek_work_operation_git as g

m=g.m
MAX_INDEX=16*1024*1024
STATES={'prepared','applying','applied','rolling_back','rolled_back','recovery_required'}


def checkpoint(name):
    """Fault-injection boundary for tests; not controlled by source text or CLI."""


def sync_dir(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


@contextmanager
def parent(root,name):
    parts=g.pre.k.path_name(name).parts;fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=child
        yield fd,parts[-1]
    finally:os.close(fd)


def observe(root,name):
    try:
        with parent(root,name) as (fd,leaf):
            f=os.open(leaf,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
            with os.fdopen(f,'rb') as source:
                st=os.fstat(source.fileno())
                m.require(stat.S_ISREG(st.st_mode) and st.st_nlink==1 and st.st_uid==os.geteuid() and st.st_gid==os.getegid(),'owned regular single-link file required')
                m.require(not st.st_mode&0o7000 and not os.listxattr(source.fileno()),'special modes or extended attributes unsupported')
                raw=source.read(g.pre.ops.MAX_FILE+1);m.require(len(raw)<=g.pre.ops.MAX_FILE,'file byte limit')
                return raw,stat.S_IMODE(st.st_mode)
    except FileNotFoundError:return None


def directory(root,name):
    try:
        with parent(root,name) as (fd,leaf):
            child=os.open(leaf,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(child);return True
    except FileNotFoundError:return False


def metadata(repo):
    env=g.git_environment();repo=repo.resolve()
    top=g.git(['rev-parse','--show-toplevel'],env,repo).decode().strip();m.require(Path(top)==repo,'repository root required')
    gitdir=Path(g.git(['rev-parse','--absolute-git-dir'],env,repo).decode().strip())
    head=g.git(['rev-parse','HEAD'],env,repo).decode().strip();index=m.read(gitdir/'index',MAX_INDEX)
    return dict(root=str(repo),git_dir=str(gitdir),head=head,index_sha256=m.sha(index))


def clean_index(repo,commit):
    env=g.git_environment();index=g.git(['ls-files','--stage','-z'],env,repo,limit=MAX_INDEX);tree=g.git(['ls-tree','-r','-z',commit],env,repo,limit=MAX_INDEX)
    a={};b={}
    for row in index.split(b'\0'):
        if row:
            meta,name=row.split(b'\t',1);mode,oid,stage=meta.split();m.require(stage==b'0','unmerged index');a[name]=(mode,oid)
    for row in tree.split(b'\0'):
        if row:
            meta,name=row.split(b'\t',1);mode,_,oid=meta.split();b[name]=(mode,oid)
    m.require(a==b,'staged changes rejected')


def material(result,archive,modes):
    report=m.load(archive['preflight/report.json']);receipt=m.load(archive['preflight/decision/receipt.json'])
    m.require(type(modes) is dict and set(modes)==set(report['baseline']),'mode observation set');before={}
    for name,desc in report['baseline'].items():
        mode=modes[name]
        if desc is None:m.require(mode is None,'absent mode');before[name]=None
        else:
            m.require(type(mode) is int and 0<=mode<=0o777 and bool(mode&0o111)==(result['baseline_modes'][name]=='100755'),'baseline mode mismatch')
            before[name]=(archive['preflight/baseline/'+name],mode)
    after=before.copy()
    for r in receipt['removals']:after[r['path']]=None
    for name in receipt['writes']:
        mode=modes[name]
        if mode is None:mode=next((modes[r['operation']['source']] for r in receipt['operations'] if r['operation']['op']=='rename' and r['operation']['target']==name),0o644)
        after[name]=(archive['preflight/decision/result/'+name],mode)
    return before,after


def ancestors(names):
    return sorted({str(p) for n in names for p in PurePosixPath(n).parents if str(p)!='.'},key=lambda n:(len(PurePosixPath(n).parts),n))


def save_state(txn,anchor,status,error=None):
    m.require(status in STATES,'state');raw=m.encoded(dict(schema='geek-work-operation-apply-state-1',transaction_sha256=anchor,status=status,error=error))
    path=txn/'state.next'
    try:path.unlink()
    except FileNotFoundError:pass
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(path,txn/'state.json');sync_dir(txn)


def prepare(bundle,anchor,repo,output):
    repo=repo.resolve();g.pre.ops.outside(output,bundle,repo)
    m.require(output.parent.is_dir() and output.parent.stat().st_dev==repo.stat().st_dev,'transaction and project must share a filesystem')
    result,archive=g.verified(bundle,anchor,repo);meta=metadata(repo)
    m.require(meta['head']==result['base_commit'],'HEAD differs from reviewed commit');clean_index(repo,meta['head'])
    report=m.load(archive['preflight/report.json']);observed={n:observe(repo,n) for n in report['baseline']}
    modes={n:None if x is None else x[1] for n,x in observed.items()};before,after=material(result,archive,modes)
    m.require(observed==before,'STALE_WORKTREE_REJECTED')
    dirs={n:directory(repo,n) for n in ancestors(before)}
    plan=dict(schema='geek-work-operation-apply-plan-1',**meta,git_bundle_sha256=anchor,modes=modes,directories=dirs,token=uuid.uuid4().hex)
    files={'plan.json':m.encoded(plan),'scratch/keep':b'',**{'git-bundle/'+n:x for n,x in archive.items()}}
    manifest=m.encoded(dict(schema='geek-work-operation-apply-bundle-1',files={n:m.sha(x) for n,x in files.items()}));pin=m.sha(manifest)
    state=m.encoded(dict(schema='geek-work-operation-apply-state-1',transaction_sha256=pin,status='prepared',error=None))
    g.pre.tree.write_tree(output,{**files,'state.json':state,'manifest.json':manifest})
    m.require(output.stat().st_dev==repo.stat().st_dev,'transaction and project must share a filesystem')
    for n in [*files,'state.json','manifest.json']:
        with open(output/n,'rb') as f:os.fsync(f.fileno())
    for p in sorted((p for p in output.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):sync_dir(p)
    sync_dir(output);sync_dir(output.parent)
    return dict(status='prepared',manifest_sha256=pin,backup_location=str(output.resolve()),live_project_modified=False)


def load(txn,anchor,repo):
    g.pre.k.digest(anchor);raw=m.read(txn/'manifest.json');m.require(m.sha(raw)==anchor,'transaction anchor mismatch');manifest=m.load(raw)
    g.pre.k.obj(manifest,'schema files');m.require(manifest['schema']=='geek-work-operation-apply-bundle-1','transaction schema')
    plan=m.load(m.read(txn/'plan.json'));g.pre.k.obj(plan,'schema root git_dir head index_sha256 git_bundle_sha256 modes directories token')
    m.require(plan['schema']=='geek-work-operation-apply-plan-1' and type(plan['token']) is str and re.fullmatch('[0-9a-f]{32}',plan['token']),'plan schema/token')
    m.require(plan['root']==str(repo.resolve()),'transaction repository mismatch')
    result,archive=g.verified(txn/'git-bundle',plan['git_bundle_sha256'],repo)
    m.require(plan['head']==result['base_commit'],'plan commit mismatch');g.pre.k.digest(plan['index_sha256'])
    files={'plan.json':m.encoded(plan),'scratch/keep':b'',**{'git-bundle/'+n:x for n,x in archive.items()}}
    m.require(manifest['files']=={n:m.sha(x) for n,x in files.items()},'transaction file hashes')
    m.require(m.read(txn/'plan.json')==files['plan.json'] and m.read(txn/'scratch/keep')==b'','transaction bytes')
    before,after=material(result,archive,plan['modes']);m.require(set(plan['directories'])==set(ancestors(before)) and all(type(x) is bool for x in plan['directories'].values()),'directory observations')
    extras=set()
    for p in (txn/'scratch').iterdir():
        if p.name!='keep':
            m.require(re.fullmatch('[0-9]{3}\\.tmp',p.name) and int(p.name[:3])<len(before),'unknown scratch file')
            m.read(p,g.pre.ops.MAX_FILE);extras.add('scratch/'+p.name)
    if (txn/'state.next').exists():m.read(txn/'state.next');extras.add('state.next')
    g.pre.tree.exact_tree(txn,set(files)|extras|{'manifest.json','state.json'})
    state=m.load(m.read(txn/'state.json'));g.pre.k.obj(state,'schema transaction_sha256 status error')
    m.require(state['schema']=='geek-work-operation-apply-state-1' and state['transaction_sha256']==anchor and state['status'] in STATES,'journal state')
    return plan,before,after,state['status']


def identity(repo,plan):
    m.require(metadata(repo)=={k:plan[k] for k in ('root','git_dir','head','index_sha256')},'HEAD/index identity changed')


@contextmanager
def locks(plan,anchor):
    gitdir=Path(plan['git_dir']);fd=os.open(gitdir/'geek-work-apply.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);path=gitdir/'index.lock'
        if path.exists() or path.is_symlink():
            old=m.load(m.read(path,4096));m.require(type(old) is dict and old.get('transaction_sha256')==anchor and type(old.get('pid')) is int and old['pid']>0,'foreign index lock')
            try:os.kill(old['pid'],0)
            except ProcessLookupError:path.unlink();sync_dir(gitdir)
            else:raise ValueError('index lock owner still alive')
        indexfd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            os.write(indexfd,m.encoded(dict(transaction_sha256=anchor,pid=os.getpid())));os.fsync(indexfd);sync_dir(gitdir)
            yield
        finally:
            owned=os.fstat(indexfd);os.close(indexfd)
            if path.exists():
                current=path.lstat();m.require((current.st_dev,current.st_ino)==(owned.st_dev,owned.st_ino),'index lock replaced')
                path.unlink();sync_dir(gitdir)
    finally:os.close(fd)


def write_file(repo,name,value,txn,index):
    with parent(repo,name) as (fd,leaf):
        if value is None:os.unlink(leaf,dir_fd=fd);os.fsync(fd);return
        data,mode=value;tmp=txn/'scratch'/f'{index:03}.tmp'
        f=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(f,'wb') as out:
            out.write(data);out.flush();os.fchown(out.fileno(),-1,os.getegid());os.fchmod(out.fileno(),mode);os.fsync(out.fileno())
        sync_dir(tmp.parent);os.replace(tmp,leaf,dst_dir_fd=fd);os.fsync(fd);sync_dir(tmp.parent)


def rollback_core(txn,anchor,repo,plan,before,after):
    identity(repo,plan);current={n:observe(repo,n) for n in before}
    m.require(all(current[n] in (before[n],after[n]) for n in before),'INTERVENING_EDIT: rollback refused')
    for n,existed in plan['directories'].items():
        actual=directory(repo,n);m.require(actual or not existed,'baseline directory missing')
    save_state(txn,anchor,'rolling_back')
    for p in (txn/'scratch').glob('*.tmp'):p.unlink()
    sync_dir(txn/'scratch')
    for i,n in enumerate(sorted(before)):
        identity(repo,plan);value=observe(repo,n);m.require(value in (before[n],after[n]),'INTERVENING_EDIT during rollback')
        if value!=before[n]:write_file(repo,n,before[n],txn,i);checkpoint('restored:'+n)
    needed=set(ancestors(n for n,value in after.items() if value is not None))
    for n,existed in sorted(plan['directories'].items(),key=lambda x:len(PurePosixPath(x[0]).parts),reverse=True):
        if not existed and n in needed and directory(repo,n):
            with parent(repo,n) as (fd,leaf):os.rmdir(leaf,dir_fd=fd);os.fsync(fd)
    identity(repo,plan);m.require({n:observe(repo,n) for n in before}==before,'rollback verification')
    save_state(txn,anchor,'rolled_back')


def execute(txn,anchor,repo,action,quiescent=False):
    m.require(quiescent,'quiescent workspace acknowledgment required');repo=repo.resolve()
    plan,before,after,state=load(txn,anchor,repo);m.require(Path(plan['git_dir'])==Path(metadata(repo)['git_dir']),'Git directory mismatch')
    g.pre.ops.outside(txn,repo);m.require(txn.stat().st_dev==repo.stat().st_dev,'same filesystem required')
    with locks(plan,anchor):
        # Re-read under the cooperative lock, including any recovery state.
        plan,before,after,state=load(txn,anchor,repo);identity(repo,plan)
        if action=='rollback':
            try:rollback_core(txn,anchor,repo,plan,before,after)
            except Exception as error:save_state(txn,anchor,'recovery_required',str(error)[:1024]);raise
            return dict(status='rolled_back',manifest_sha256=anchor,index_and_refs_unchanged=True,backup_location=str(txn.resolve()))
        m.require(action=='apply','action')
        if state=='applied':
            m.require({n:observe(repo,n) for n in after}==after,'INTERVENING_EDIT after apply')
            return dict(status='applied',idempotent=True,manifest_sha256=anchor,index_and_refs_unchanged=True,backup_location=str(txn.resolve()))
        m.require(state=='prepared','explicit rollback/recovery required')
        m.require({n:observe(repo,n) for n in before}==before,'STALE_WORKTREE_REJECTED')
        m.require(all(directory(repo,n)==existed for n,existed in plan['directories'].items()),'directory baseline changed')
        m.require(not list((txn/'scratch').glob('*.tmp')),'unexpected prepared scratch')
        save_state(txn,anchor,'applying')
        try:
            checkpoint('started');needed=set(ancestors(n for n,value in after.items() if value is not None))
            for n,existed in sorted(plan['directories'].items(),key=lambda x:len(PurePosixPath(x[0]).parts)):
                if not existed and n in needed:
                    with parent(repo,n) as (fd,leaf):os.mkdir(leaf,0o755,dir_fd=fd);os.fsync(fd)
            for i,n in enumerate(sorted(before)):
                identity(repo,plan);m.require(observe(repo,n)==before[n],'INTERVENING_EDIT during apply')
                if before[n]!=after[n]:write_file(repo,n,after[n],txn,i);checkpoint('written:'+n)
            identity(repo,plan);m.require({n:observe(repo,n) for n in after}==after,'post-apply verification')
            save_state(txn,anchor,'applied')
        except Exception as error:
            try:
                rollback_core(txn,anchor,repo,plan,before,after);save_state(txn,anchor,'rolled_back',str(error)[:1024])
            except Exception as recovery:save_state(txn,anchor,'recovery_required',str(recovery)[:1024])
            raise error
    return dict(status='applied',idempotent=False,manifest_sha256=anchor,index_and_refs_unchanged=True,backup_location=str(txn.resolve()))


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    q=sub.add_parser('prepare')
    for n in ('bundle','repo','output'):q.add_argument('--'+n,type=Path,required=True)
    q.add_argument('--sha256',required=True)
    for action in ('apply','rollback'):
        q=sub.add_parser(action)
        for n in ('transaction','repo'):q.add_argument('--'+n,type=Path,required=True)
        q.add_argument('--sha256',required=True);q.add_argument('--quiescent',action='store_true',required=True)
    a=parser.parse_args();result=prepare(a.bundle,a.sha256,a.repo,a.output) if a.action=='prepare' else execute(a.transaction,a.sha256,a.repo,a.action,a.quiescent)
    print(m.encoded(result).decode(),end='')


if __name__=='__main__':main()
