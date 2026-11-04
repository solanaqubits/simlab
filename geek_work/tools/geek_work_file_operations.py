#!/usr/bin/env python3
"""Review explicit file lifecycle operations; stage bytes and removal intents only."""
import argparse
import html
import json
import os
from pathlib import Path
import stat
import geek_work_manuscript as m
import geek_work_manuscript_batch as b
import geek_work_manuscript_claims as k
import geek_work_batch_hunks as tree

MAX_FILES=16
MAX_FILE=8*1024*1024
MAX_SNAPSHOTS=16*1024*1024
OPS={'create','delete','rename','replace','guard'}


def outside(output,*roots):
    target=output.resolve()
    for root in roots:
        path=root.resolve()
        m.require(not target.is_relative_to(path) and not path.is_relative_to(target),'output must be disjoint from input roots')


def operations(raw):
    spec=m.load(raw);k.obj(spec,'schema operations');m.require(spec['schema']=='geek-work-file-operations-1','operations schema')
    rows=k.rows(spec['operations'],MAX_FILES,1);ids=set();paths=[]
    for row in rows:
        k.obj(row,'id op kind source target');k.ident(row['id']);m.require(row['id'] not in ids,'duplicate operation ID');ids.add(row['id'])
        m.require(type(row['op']) is str and row['op'] in OPS,'operation');m.require(type(row['kind']) is str and row['kind'] in {'text','binary'},'content kind')
        src,dst=row['source'],row['target'];op=row['op']
        m.require((src is None)==(op=='create') and (dst is None)==(op=='delete'),'operation endpoints')
        for path in (src,dst):
            if path is not None:k.path_name(path)
        if op in {'replace','guard'}:m.require(src==dst,'same-path operation')
        if op=='rename':m.require(src!=dst,'rename requires distinct paths')
        paths.extend(dict.fromkeys(p for p in (src,dst) if p is not None))
    m.require(len({p.casefold() for p in paths})==len(paths),'shared/case-colliding operation paths')
    for a in paths:
        for bpath in paths:m.require(a==bpath or not bpath.casefold().startswith(a.casefold()+'/'),'file/directory path collision')
    m.require(any(r['op']!='guard' for r in rows),'no file operations')
    return rows


def content(raw,kind):
    m.require(len(raw)<=MAX_FILE,'file byte limit')
    if kind=='text':m.source(raw)
    return raw


def observe(root,name,kind):
    parts=k.path_name(name).parts;fd=None
    try:
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            for part in parts[:-1]:
                child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=child
            leaf=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        except FileNotFoundError:return None
        with os.fdopen(leaf,'rb') as f:
            m.require(stat.S_ISREG(os.fstat(f.fileno()).st_mode),'regular operation input required')
            return content(f.read(MAX_FILE+1),kind)
    except OSError as error:raise ValueError('unsafe or unavailable project path: '+name) from error
    finally:
        if fd is not None:os.close(fd)


def states(row,before,after):
    op,src,dst=row['op'],row['source'],row['target']
    m.require((before is None)==(op=='create') and (after is None)==(op=='delete'),'missing operation content')
    for raw in (before,after):
        if raw is not None:content(raw,row['kind'])
    if op in {'rename','guard'}:m.require(before==after,'rename/guard must preserve bytes')
    if op=='replace':m.require(before!=after,'no replacement change')
    if op=='create':return {dst:None},{dst:after}
    if op=='delete':return {src:before},{src:None}
    if op=='rename':return {src:before,dst:None},{src:None,dst:after}
    return {src:before},{dst:after}


def artifacts(raw,rows,pairs,author,reason):
    k.text(author);k.text(reason);files={'operations.json':raw};total=0
    preview='''<!doctype html><html lang="en"><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>File operation review</title><style>body{font:16px system-ui;max-width:1000px;margin:2em auto;padding:1em}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>File operation review</h1><p>Staged bytes and removal intents only. No live changes. Binary files are not rendered or decoded. Absent and empty files are distinct.</p>'''
    for label,value in [('Reported author',author),('Reason',reason)]:preview+='<h2>'+label+'</h2><pre>'+html.escape(value)+'</pre>'
    for i,(row,(before,after)) in enumerate(zip(rows,pairs)):
        states(row,before,after);preview+='<h2>'+html.escape(row['id'])+'</h2><pre>'+html.escape(json.dumps(row,ensure_ascii=False,indent=2))+'</pre>'
        for side,blob in [('before',before),('after',after)]:
            details={'state':'absent'}
            if blob is not None:
                total+=len(blob);m.require(total<=MAX_SNAPSHOTS,'snapshot byte limit');files[f'{i:04d}-{side}.bin']=blob
                details=dict(state='present',sha256=m.sha(blob),bytes=len(blob))
                if row['kind']=='text':details['text']=blob.decode('utf-8')
            preview+='<h3>'+side+'</h3><pre>'+html.escape(json.dumps(details,ensure_ascii=False,indent=2))+'</pre>'
    files['review.html']=(preview+'</html>\n').encode();m.require(len(files['review.html'])<=m.MAX_ARTIFACT,'preview byte limit')
    files['decisions.template.json']=m.encoded(dict(schema='geek-work-file-operation-selection-1',proposal_sha256=None,reviewer=None,
        decisions=[dict(operation_id=r['id'],decision=None,reason=None) for r in rows]))
    return files


def propose(base,candidate,operations_path,operations_sha256,author,reason,output):
    outside(output,base,candidate)
    k.digest(operations_sha256);raw=m.read(operations_path);m.require(m.sha(raw)==operations_sha256,'operations SHA mismatch');rows=operations(raw);pairs=[];total=0
    for row in rows:
        paths=dict.fromkeys(p for p in (row['source'],row['target']) if p is not None)
        old={p:observe(base,p,row['kind']) for p in paths};new={p:observe(candidate,p,row['kind']) for p in paths}
        before=old.get(row['source']);after=new.get(row['target']);a,z=states(row,before,after)
        m.require(old==a and new==z,'operation state mismatch: '+row['id'])
        total+=sum(len(x) for x in (before,after) if x is not None);m.require(total<=MAX_SNAPSHOTS,'snapshot byte limit');pairs.append((before,after))
    data=artifacts(raw,rows,pairs,author,reason)
    manifest=m.encoded(dict(schema='geek-work-file-operation-proposal-1',author=author,reason=reason,files={n:m.sha(x) for n,x in data.items()}))
    tree.write_tree(output,{**data,'manifest.json':manifest})
    return dict(status='file_operation_proposal_ready',manifest_sha256=m.sha(manifest),operations=len(rows),live_project_modified=False)


def verified(bundle,anchor):
    k.digest(anchor);m.require(bundle.is_dir() and not bundle.is_symlink(),'regular proposal directory')
    raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'proposal anchor mismatch');spec=m.load(raw)
    k.obj(spec,'schema author reason files');m.require(spec['schema']=='geek-work-file-operation-proposal-1','proposal schema')
    opraw=m.read(bundle/'operations.json');rows=operations(opraw);names={'operations.json','review.html','decisions.template.json'}
    for i,row in enumerate(rows):
        if row['op']!='create':names.add(f'{i:04d}-before.bin')
        if row['op']!='delete':names.add(f'{i:04d}-after.bin')
    m.require(type(spec['files']) is dict and set(spec['files'])==names,'proposal file set');b.directory(bundle,names|{'manifest.json'})
    data={};total=0
    for name in names:
        blob=m.read(bundle/name,MAX_FILE if name.endswith('.bin') else m.MAX_ARTIFACT)
        if name.endswith('.bin'):total+=len(blob);m.require(total<=MAX_SNAPSHOTS,'snapshot byte limit')
        m.require(m.sha(blob)==spec['files'][name],'proposal artifact hash mismatch');data[name]=blob
    pairs=[(data.get(f'{i:04d}-before.bin'),data.get(f'{i:04d}-after.bin')) for i in range(len(rows))]
    m.require(data==artifacts(opraw,rows,pairs,spec['author'],spec['reason']),'proposal reproduction mismatch')
    return rows,pairs,{**data,'manifest.json':raw}


def projection(rows,pairs,anchor,raw):
    selection=m.load(raw);k.obj(selection,'schema proposal_sha256 reviewer decisions')
    m.require(selection['schema']=='geek-work-file-operation-selection-1' and selection['proposal_sha256']==anchor,'selection/proposal mismatch');k.text(selection['reviewer']);choices={}
    for d in k.rows(selection['decisions'],MAX_FILES,1):
        k.obj(d,'operation_id decision reason');k.ident(d['operation_id']);k.text(d['reason'])
        m.require(d['operation_id'] not in choices,'duplicate operation decision');choices[d['operation_id']]=d
    m.require(set(choices)=={r['id'] for r in rows},'every operation requires one decision')
    writes={};removals=[];records=[]
    for row,(before,after) in zip(rows,pairs):
        d=choices[row['id']];m.require(type(d['decision']) is str and d['decision'] in ({'confirm'} if row['op']=='guard' else {'accept','reject'}),'explicit operation decision')
        old,new=states(row,before,after);chosen=new if d['decision']=='accept' else old
        for path,blob in chosen.items():
            if blob is not None:writes['result/'+path]=blob
            elif old[path] is not None:removals.append(dict(path=path,expected_sha256=m.sha(old[path])))
        records.append(dict(operation=row,decision=d,baseline={p:None if x is None else m.sha(x) for p,x in old.items()},result={p:None if x is None else m.sha(x) for p,x in chosen.items()}))
    removals.sort(key=lambda r:r['path'])
    receipt=dict(schema='geek-work-file-operation-decision-1',proposal_sha256=anchor,selection_sha256=m.sha(raw),reviewer=selection['reviewer'],operations=records,
        writes={n[len('result/'):]:m.sha(x) for n,x in writes.items()},removals=removals,live_project_modified=False,
        scientific_verification=False,reference_consistency_checked=False,binary_content_validated=False,reviewer_identity_verified=False,
        limits='Selected path observations only, including required absence. Staged files/removal intents are not an executable patch, atomic live update, complete project snapshot or publication approval.')
    writes.update({'decisions.json':raw,'removals.json':m.encoded(removals),'receipt.json':m.encoded(receipt)})
    m.require(len(writes['receipt.json'])<=m.MAX_ARTIFACT,'receipt byte limit');return writes,receipt


def decide(bundle,anchor,current,decisions,decisions_sha256,output):
    outside(output,bundle,current)
    rows,pairs,proposal=verified(bundle,anchor);k.digest(decisions_sha256);raw=m.read(decisions);m.require(m.sha(raw)==decisions_sha256,'selection SHA mismatch');payload,receipt=projection(rows,pairs,anchor,raw)
    for row,(before,after) in zip(rows,pairs):
        old,_=states(row,before,after)
        for path,expected in old.items():m.require(observe(current,path,row['kind'])==expected,'STALE_BASE_REJECTED: '+path)
    manifest=m.encoded(dict(schema='geek-work-file-operation-decision-bundle-1',proposal_sha256=anchor,files={n:m.sha(x) for n,x in payload.items()}))
    tree.write_tree(output,{**payload,**{'proposal/'+n:x for n,x in proposal.items()},'manifest.json':manifest})
    return dict(status='file_operation_decision_staged',manifest_sha256=m.sha(manifest),**receipt)


def verified_decision(bundle,anchor):
    k.digest(anchor);m.require(bundle.is_dir() and not bundle.is_symlink(),'regular decision directory');raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'decision anchor mismatch')
    spec=m.load(raw);k.obj(spec,'schema proposal_sha256 files');m.require(spec['schema']=='geek-work-file-operation-decision-bundle-1','decision schema')
    rows,pairs,proposal=verified(bundle/'proposal',spec['proposal_sha256']);selection=m.read(bundle/'decisions.json');expected,receipt=projection(rows,pairs,spec['proposal_sha256'],selection)
    m.require(type(spec['files']) is dict and set(spec['files'])==set(expected),'decision file set')
    tree.exact_tree(bundle,set(expected)|{'proposal/'+n for n in proposal}|{'manifest.json'})
    for name,wanted in expected.items():
        actual=m.read(bundle/name,MAX_FILE if name.startswith('result/') else m.MAX_ARTIFACT)
        m.require(m.sha(actual)==spec['files'][name] and actual==wanted,'decision reproduction mismatch')
    return expected,receipt,{**expected,**{'proposal/'+n:x for n,x in proposal.items()},'manifest.json':raw}


def verify_decision(bundle,anchor):
    _,receipt,_=verified_decision(bundle,anchor)
    return dict(status='file_operation_decision_consistent',manifest_sha256=anchor,staged_files=len(receipt['writes']),removal_intents=len(receipt['removals']),
        live_project_checked=False,historical_baseline_check_verified=False,reviewer_identity_verified=False,binary_content_validated=False,scientific_verification=False,
        limits='Anchored byte/decision consistency only; no live mutation, actual deletion, semantic validation or independent authentication of historical observations.')


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    q=sub.add_parser('propose')
    for n in ('base-root','candidate-root','operations','output'):q.add_argument('--'+n,type=Path,required=True)
    for n in ('operations-sha256','author','reason'):q.add_argument('--'+n,required=True)
    q=sub.add_parser('decide')
    for n in ('bundle','current-root','decisions','output'):q.add_argument('--'+n,type=Path,required=True)
    for n in ('sha256','decisions-sha256'):q.add_argument('--'+n,required=True)
    q=sub.add_parser('verify-decision');q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True)
    a=p.parse_args()
    if a.action=='propose':r=propose(a.base_root,a.candidate_root,a.operations,a.operations_sha256,a.author,a.reason,a.output)
    elif a.action=='decide':r=decide(a.bundle,a.sha256,a.current_root,a.decisions,a.decisions_sha256,a.output)
    else:r=verify_decision(a.bundle,a.sha256)
    print(m.encoded(r).decode(),end='')


if __name__=='__main__':main()
