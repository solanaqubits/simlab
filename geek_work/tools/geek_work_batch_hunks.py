#!/usr/bin/env python3
"""Per-file hunk choices over an anchored manuscript batch; staged output only."""
import argparse
import html
import json
from pathlib import Path, PurePosixPath
import geek_work_manuscript as m
import geek_work_manuscript_batch as b
import geek_work_manuscript_hunks as h
import geek_work_manuscript_claims as k

MAX_HUNKS=256
PLAN_FILES={'hunks.json','review.html','decisions.template.json'}


def write_tree(output,files):
    output.mkdir(parents=True,exist_ok=False)
    for name,raw in files.items():
        p=output/name;p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('xb') as f:f.write(raw)


def exact_tree(root,names):
    dirs={'.':set()}
    for name in names:
        p=PurePosixPath(name)
        for parent in p.parents:dirs.setdefault(str(parent),set())
        for part in [p,*list(p.parents)[:-1]]:dirs[str(part.parent)].add(part.name)
    for folder,children in sorted(dirs.items()):b.directory(root/folder,children)


def batch_bytes(bundle,anchor):
    b.directory(bundle,{'files','review.html','manifest.json'})
    raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'batch anchor mismatch')
    spec,data=b.verified(bundle,anchor)
    flat={'manifest.json':raw,'review.html':b.index(spec['entries'])}
    for i,blobs in enumerate(data):flat.update({f'files/{i:04d}/'+n:x for n,x in blobs.items()})
    return spec,data,flat


def plan_artifacts(spec,data):
    rows=[dict(document=r['document'],changed=r['changed'],hunks=h.hunks(d['before.txt'],d['after.txt']) if r['changed'] else []) for r,d in zip(spec['entries'],data)]
    m.require(sum(len(r['hunks']) for r in rows)<=MAX_HUNKS,'batch hunk count limit')
    template=dict(schema='geek-work-batch-hunk-selection-1',plan_sha256=None,reviewer=None,
        files=[dict(document=r['document'],decisions=[dict(hunk_id=x['id'],decision=None,reason=None) for x in r['hunks']]) for r in rows])
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Batch hunk review</title><style>body{font:16px system-ui;max-width:1000px;margin:2em auto;padding:1em}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>
<h1>Review every selected file and hunk</h1><p>Hunk IDs are local to each file. Unchanged files are baseline guards and must have an explicit empty decision list. Text choices do not establish cross-file consistency. Byte offsets are zero-based and end-exclusive; JSON escapes preserve visible line endings.</p>'''
    for i,r in enumerate(rows):
        page+='<h2>'+html.escape(r['document'])+'</h2><p><a href="batch/files/'+f'{i:04d}'+'/review.html">Full source preview</a></p><pre>'+html.escape(json.dumps(r,ensure_ascii=False,indent=2))+'</pre>'
    files={'hunks.json':m.encoded(dict(schema='geek-work-batch-hunks-1',files=rows)),
        'decisions.template.json':m.encoded(template),'review.html':(page+'</html>\n').encode()}
    m.require(all(len(x)<=m.MAX_ARTIFACT for x in files.values()),'plan artifact byte limit')
    return files,rows


def prepare(bundle,anchor,output):
    k.digest(anchor);spec,data,flat=batch_bytes(bundle,anchor);files,rows=plan_artifacts(spec,data)
    manifest=m.encoded(dict(schema='geek-work-batch-hunk-plan-1',batch_sha256=anchor,files={n:m.sha(x) for n,x in files.items()}))
    write_tree(output,{**files,**{'batch/'+n:x for n,x in flat.items()},'manifest.json':manifest})
    return dict(status='batch_hunk_plan_ready',manifest_sha256=m.sha(manifest),files=len(rows),hunks=sum(len(r['hunks']) for r in rows),live_document_modified=False)


def verified_plan(bundle,anchor):
    k.digest(anchor);b.directory(bundle,PLAN_FILES|{'batch','manifest.json'})
    raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'plan anchor mismatch');plan=m.load(raw)
    k.obj(plan,'schema batch_sha256 files');m.require(plan['schema']=='geek-work-batch-hunk-plan-1','plan schema');k.digest(plan['batch_sha256'])
    m.require(type(plan['files']) is dict and set(plan['files'])==PLAN_FILES,'plan file set')
    files={n:m.read(bundle/n) for n in PLAN_FILES};m.require(all(m.sha(x)==plan['files'][n] for n,x in files.items()),'plan artifact hash mismatch')
    spec,data,flat=batch_bytes(bundle/'batch',plan['batch_sha256']);expected,rows=plan_artifacts(spec,data)
    m.require(files==expected,'plan reproduction mismatch')
    return spec,data,rows,{**files,**{'batch/'+n:x for n,x in flat.items()},'manifest.json':raw}


def selected(raw,anchor,rows):
    spec=m.load(raw);k.obj(spec,'schema plan_sha256 reviewer files')
    m.require(spec['schema']=='geek-work-batch-hunk-selection-1' and spec['plan_sha256']==anchor,'selection/plan mismatch');k.text(spec['reviewer'])
    by_name={}
    for row in k.rows(spec['files'],b.MAX_FILES,1):
        k.obj(row,'document decisions');m.document(row['document']);m.require(row['document'] not in by_name,'duplicate file decision');by_name[row['document']]=row
    m.require(set(by_name)=={r['document'] for r in rows},'every selected file requires a decision row')
    choices=[]
    for row in rows:
        decisions=by_name[row['document']]['decisions']
        if row['changed']:
            _,normalized=h.selection(m.encoded(dict(schema='geek-work-hunk-selection-1',proposal_sha256=anchor,reviewer=spec['reviewer'],decisions=decisions)),anchor,row['hunks'])
        else:
            m.require(type(decisions) is list and not decisions,'unchanged guard requires empty decisions');normalized=[]
        choices.append(normalized)
    return spec['reviewer'],choices


def results(data,rows,anchor,raw):
    reviewer,choices=selected(raw,anchor,rows);payload={};entries=[]
    for blobs,row,choice in zip(data,rows,choices):
        result=h.assemble(blobs['before.txt'],row['hunks'],choice)
        payload['result/'+row['document']]=result
        entries.append(dict(document=row['document'],unchanged_guard=not row['changed'],decisions=choice,
            observed_base_sha256=m.sha(blobs['before.txt']),result_sha256=m.sha(result),accepted=sum(c['decision']=='accept' for c in choice),rejected=sum(c['decision']=='reject' for c in choice)))
    receipt=dict(schema='geek-work-batch-hunk-decision-1',plan_sha256=anchor,selection_sha256=m.sha(raw),reviewer=reviewer,files=entries,
        live_document_modified=False,scientific_verification=False,reference_consistency_checked=False,compilation_checked=False,reviewer_identity_verified=False,
        limits='All selected baselines checked before staging, including unchanged guards; per-file point-in-time observations, not an atomic project snapshot or live write-back. Review/preflight/compile the assembled selected subset separately.')
    payload.update({'decisions.json':raw,'receipt.json':m.encoded(receipt)})
    m.require(len(payload['receipt.json'])<=m.MAX_ARTIFACT,'receipt byte limit')
    return payload,receipt


def decide(bundle,anchor,current,decisions,decisions_sha256,output):
    _,data,rows,plan=verified_plan(bundle,anchor);k.digest(decisions_sha256)
    raw=m.read(decisions);m.require(m.sha(raw)==decisions_sha256,'selection SHA mismatch');payload,receipt=results(data,rows,anchor,raw)
    for row,blobs in zip(rows,data):
        m.require(b.project_file(current,row['document'])==blobs['before.txt'],'STALE_BASE_REJECTED: '+row['document'])
    manifest=m.encoded(dict(schema='geek-work-batch-hunk-decision-bundle-1',plan_sha256=anchor,files={n:m.sha(x) for n,x in payload.items()}))
    write_tree(output,{**payload,**{'plan/'+n:x for n,x in plan.items()},'manifest.json':manifest})
    return dict(status='batch_hunk_decision_staged',manifest_sha256=m.sha(manifest),**receipt)


def verify_decision(bundle,anchor):
    k.digest(anchor);m.require(bundle.is_dir() and not bundle.is_symlink(),'regular decision directory')
    raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'decision anchor mismatch');manifest=m.load(raw)
    k.obj(manifest,'schema plan_sha256 files');m.require(manifest['schema']=='geek-work-batch-hunk-decision-bundle-1','decision schema')
    _,data,rows,plan=verified_plan(bundle/'plan',manifest['plan_sha256'])
    names={'decisions.json','receipt.json'}|{'result/'+r['document'] for r in rows}
    m.require(type(manifest['files']) is dict and set(manifest['files'])==names,'decision file set')
    exact_tree(bundle,names|{'plan/'+n for n in plan}|{'manifest.json'})
    payload={n:m.read(bundle/n,m.MAX_SOURCE if n.startswith('result/') else m.MAX_ARTIFACT) for n in names}
    m.require(all(m.sha(x)==manifest['files'][n] for n,x in payload.items()),'decision artifact hash mismatch')
    expected,receipt=results(data,rows,manifest['plan_sha256'],payload['decisions.json']);m.require(payload==expected,'decision reproduction mismatch')
    return dict(status='batch_hunk_decision_consistent',manifest_sha256=anchor,files=len(rows),
        accepted=sum(r['accepted'] for r in receipt['files']),rejected=sum(r['rejected'] for r in receipt['files']),
        unchanged_guards=sum(not r['changed'] for r in rows),live_document_checked=False,historical_baseline_check_verified=False,
        reviewer_identity_verified=False,scientific_verification=False,
        limits='Anchored byte/decision reproduction only; not authentication, historical current-file attestation or cross-file semantic validation.')


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    for action in ('prepare','decide','verify-decision'):
        q=sub.add_parser(action);q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True)
        if action!='verify-decision':q.add_argument('--output',type=Path,required=True)
        if action=='decide':
            q.add_argument('--current-root',type=Path,required=True);q.add_argument('--decisions',type=Path,required=True);q.add_argument('--decisions-sha256',required=True)
    a=p.parse_args()
    if a.action=='prepare':r=prepare(a.bundle,a.sha256,a.output)
    elif a.action=='decide':r=decide(a.bundle,a.sha256,a.current_root,a.decisions,a.decisions_sha256,a.output)
    else:r=verify_decision(a.bundle,a.sha256)
    print(m.encoded(r).decode(),end='')


if __name__=='__main__':main()
