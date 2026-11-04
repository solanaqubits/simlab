#!/usr/bin/env python3
"""Build an offline read-only experiment tree from pinned plans and reported ledgers."""
import argparse
import copy
import html
import json
from pathlib import Path

import geek_work_experiment as experiment
import geek_work_ledger as ledger
import geek_work_manuscript as m
import geek_work_manuscript_claims as k
import geek_work_batch_hunks as tree
import geek_work_file_operations as ops
import knowledge

MAX_NODES = 32
MAX_TOTAL = 64 * 1024 * 1024
MAX_FILES = 4096


def reference(ref):
    k.obj(ref, 'path sha256');k.path_name(ref['path']);k.digest(ref['sha256'])


def validate(spec):
    k.obj(spec, 'schema id title nodes');m.require(spec['schema']=='geek-work-experiment-tree-1','tree schema')
    k.ident(spec['id']);k.text(spec['title']);nodes=k.rows(spec['nodes'],MAX_NODES,1);by_id={};refs={};selectors=set()
    def register(ref,kind):
        reference(ref);key=ref['path'];value=(kind,ref['sha256'])
        m.require(key not in refs or refs[key]==value,'conflicting input reference');refs[key]=value
    for node in nodes:
        k.obj(node,'id parent builds_on plan ledger claim_maps');k.ident(node['id'])
        m.require(node['id'] not in by_id,'duplicate node ID');by_id[node['id']]=node
        if node['parent'] is None:m.require(node['builds_on'] is None,'root has no inherited result')
        else:k.ident(node['parent']);k.text(node['builds_on'])
        register(node['plan'],'plan')
        if node['ledger'] is not None:
            row=node['ledger'];k.obj(row,'path sha256 task_id');k.text(row['task_id'])
            register(dict(path=row['path'],sha256=row['sha256']),'ledger')
            selector=(row['sha256'],row['task_id']);m.require(selector not in selectors,'task counted twice');selectors.add(selector)
        for ref in k.rows(node['claim_maps'],2):register(ref,'claims')
        m.require(len({ref['path'] for ref in node['claim_maps']})==len(node['claim_maps']),'duplicate claim map')
    roots=[n['id'] for n in nodes if n['parent'] is None];m.require(len(roots)==1,'exactly one baseline root required')
    depths={}
    for node in nodes:
        current=node['id'];seen=set()
        while current is not None:
            m.require(current in by_id and current not in seen,'missing parent or cyclic tree')
            seen.add(current);current=by_id[current]['parent']
        depths[node['id']]=len(seen)-1
    names=list(refs)
    for i,name in enumerate(names):
        for other in names[i+1:]:
            a,b=name.casefold(),other.casefold()
            m.require(a!=b and not a.startswith(b+'/') and not b.startswith(a+'/'),'overlapping/case-colliding inputs')
    m.require(len(refs)<=96,'input count bound')
    return sorted(nodes,key=lambda n:(depths[n['id']],n['id'])),refs,depths


def archive_directory(root,name):
    path=Path(root);m.require(path.is_dir() and not path.is_symlink(),'regular input root')
    for part in k.path_name(name).parts:
        path=path/part;m.require(path.is_dir() and not path.is_symlink(),'regular archive path')
    return path


def snapshot(root,refs):
    files={};loaded={};total=0
    def add(name,raw):
        nonlocal total
        total+=len(raw);m.require(total<=MAX_TOTAL and len(files)<MAX_FILES,'tree snapshot bound')
        files['inputs/'+name]=raw
    for name,(kind,anchor) in sorted(refs.items()):
        if kind=='ledger':
            raw=k.read_source(root,name);m.require(m.sha(raw)==anchor,'ledger anchor mismatch')
            doc=knowledge.strict_json(raw)
            m.require(type(doc) is dict and type(doc.get('tasks')) is list and len(doc['tasks'])<=128,'ledger task bound')
            for task in doc['tasks']:
                m.require(type(task) is dict and type(task.get('attempts')) is list and len(task['attempts'])<=128,'ledger attempt bound')
            try:ledger.validate(doc)
            except (KeyError,TypeError,AttributeError) as error:raise ValueError('malformed ledger') from error
            loaded[name]=doc;add(name,raw)
        else:
            folder=archive_directory(root,name);experiment.verify(folder,anchor)
            manifest=m.load(m.read(folder/'manifest.json'))
            m.require(manifest['kind']==kind,'wrong archive kind for tree reference')
            for file in sorted(set(manifest['files'])|{'manifest.json'}):
                k.path_name(file);add(name+'/'+file,m.read(folder/file))
            loaded[name]=dict(spec=m.load(files['inputs/'+name+'/spec.json']),report=m.load(files['inputs/'+name+'/report.json']))
    return files,loaded


def derive(spec,loaded,depths):
    nodes=sorted(spec['nodes'],key=lambda n:(depths[n['id']],n['id']));by_id={n['id']:n for n in nodes}
    result=[];documents=[];task_ids=set()
    for node in nodes:
        plan=loaded[node['plan']['path']]['spec'];attempts=[];outcome=None;selected=None
        if node['ledger'] is not None:
            binding=node['ledger'];doc=loaded[binding['path']]
            matches=[t for t in doc['tasks'] if t['task_id']==binding['task_id']]
            m.require(len(matches)==1,'selected ledger task missing');task=matches[0]
            m.require(task['task_id'] not in task_ids,'duplicate task ID across selected ledgers');task_ids.add(task['task_id'])
            selected=dict(schema=doc['schema'],currency=doc['currency'],cost_scope=doc['cost_scope'],tasks=[copy.deepcopy(task)])
            documents.append(selected);attempts=copy.deepcopy(task['attempts']);outcome=task['outcome']
        changes=[]
        if node['parent'] is not None:
            parent=loaded[by_id[node['parent']]['plan']['path']]['spec']
            changes=[key for key in ('domain','hypothesis','sources','parameters','seeds','budget','controls','criteria','holdout','analysis_change_policy') if m.encoded(plan[key])!=m.encoded(parent[key])]
        maps=[dict(manifest_sha256=ref['sha256'],path=ref['path'],report=loaded[ref['path']]['report']) for ref in node['claim_maps']]
        result.append(dict(id=node['id'],parent=node['parent'],depth=depths[node['id']],builds_on_declared=node['builds_on'],
            state='attempts_reported' if selected else 'plan_only',plan_manifest_sha256=node['plan']['sha256'],
            plan_id=plan['id'],title=plan['title'],hypothesis=plan['hypothesis'],parameters=plan['parameters'],
            pinned_sources=plan['sources'],seeds=plan['seeds'],declared_budget=plan['budget'],holdout=plan['holdout'],
            changed_plan_fields=changes,reported_task_outcome=outcome,reported_attempts=attempts,
            reported_attempts_exceed_declared_limit=len(attempts)>plan['budget']['max_attempts'],claim_maps=maps,
            execution_verified=False,acceptance_evidence_verified=False,map_plan_conformance_verified=False,
            ledger_plan_conformance_verified=False,
            inheritance_verified=False,comparability_verified=False,scientific_verification=False))
    summary=ledger.summarize(documents)
    summary['scope']='Reported selected ledger tasks only; not proof of execution, commitment or scientific acceptance'
    return dict(schema='geek-work-experiment-tree-report-1',id=spec['id'],title=spec['title'],nodes=result,
        reported_ledger_summary=summary,all_attempts_complete_verified=False,budget_enforced=False,
        chronology_verified=False,holdout_blinding_verified=False,scientific_verification=False,publication_authorized=False)


def render(report):
    esc=lambda x:html.escape(str(x),quote=True)
    output=['''<!doctype html><html lang="en"><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Experiment tree</title>
<style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:1rem;color:#17212b;background:#fafafa}article{border:1px solid #b8c6cc;margin:1rem 0;padding:1rem;background:white}pre{white-space:pre-wrap;overflow-wrap:anywhere}a{color:#125b7a}small{color:#45545e}li{margin:.4rem 0}</style>''',
        '<h1>'+esc(report['title'])+'</h1>',
        '<p>Read-only metadata. Parent links and attempts are reported; no scientific result or execution is certified. Budgets are declarations.</p>']
    nodes=report['nodes']
    def branch(parent):
        children=[n for n in nodes if n['parent']==parent]
        if not children:return ''
        return '<ul>'+''.join('<li><a href="#'+esc(n['id'])+'">'+esc(n['id'])+'</a> — '+esc(n['title'])+' <small>['+esc(n['state'])+']</small>'+branch(n['id'])+'</li>' for n in children)+'</ul>'
    output.append('<nav aria-label="Experiment hierarchy">'+branch(None)+'</nav>')
    for node in nodes:
        output.append('<article id="'+esc(node['id'])+'"><h2>'+esc(node['id'])+': '+esc(node['title'])+'</h2>')
        output.append('<p>'+esc(node['hypothesis'])+'</p><p>State: '+esc(node['state'])+'; reported ledger outcome: '+esc(node['reported_task_outcome'])+'</p>')
        if node['parent'] is not None:output.append('<p>Parent: <a href="#'+esc(node['parent'])+'">'+esc(node['parent'])+'</a>; declared basis: '+esc(node['builds_on_declared'])+'</p>')
        output.append('<p>Reported attempts: '+str(len(node['reported_attempts']))+'; beyond declared attempt limit: '+str(node['reported_attempts_exceed_declared_limit'])+'</p>')
        output.append('<p>Numeric maps: '+esc(', '.join(x['report']['status'] for x in node['claim_maps']) or 'none attached')+'</p>')
        output.append('<details><summary>Pinned plan, every reported attempt and numeric maps</summary><pre>'+esc(json.dumps(node,ensure_ascii=False,indent=2))+'</pre></details></article>')
    output.append('<h2>Reported cost ledger</h2><p>Ledger acceptance is not scientific acceptance. Unknown costs remain null. No currencies are converted.</p><pre>'+esc(json.dumps(report['reported_ledger_summary'],ensure_ascii=False,indent=2))+'</pre></html>\n')
    raw=''.join(output).encode();m.require(len(raw)<=8*1024*1024,'HTML byte bound');return raw


def content(spec_raw,root):
    spec=knowledge.strict_json(spec_raw);_,refs,depths=validate(spec);files,loaded=snapshot(root,refs)
    report=derive(spec,loaded,depths);report_raw=m.encoded(report);m.require(len(report_raw)<=8*1024*1024,'report byte bound')
    return {'spec.json':spec_raw,**files,'report.json':report_raw,'index.html':render(report)}


def build(spec_path,anchor,root,output):
    k.digest(anchor);ops.outside(output,root,spec_path)
    raw=m.read(spec_path);m.require(m.sha(raw)==anchor,'tree spec anchor mismatch')
    m.require(not output.exists() and not output.is_symlink(),'new tree output required')
    files=content(raw,root)
    manifest=m.encoded(dict(schema='geek-work-experiment-tree-archive-1',files={n:m.sha(b) for n,b in files.items()}))
    tree.write_tree(output,{**files,'manifest.json':manifest})
    return dict(status='tree_built',manifest_sha256=m.sha(manifest),scientific_verification=False)


def verify(bundle,anchor):
    k.digest(anchor);m.require(bundle.is_dir() and not bundle.is_symlink(),'regular tree archive')
    raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'tree anchor mismatch')
    files=content(m.read(bundle/'spec.json'),bundle/'inputs')
    expected=m.encoded(dict(schema='geek-work-experiment-tree-archive-1',files={n:m.sha(b) for n,b in files.items()}))
    m.require(raw==expected,'tree manifest reproduction mismatch');tree.exact_tree(bundle,set(files)|{'manifest.json'})
    for name,data in files.items():m.require(m.read(bundle/name,max(len(data),1))==data,'tree reproduction mismatch')
    return dict(status='tree_integrity_reproduced',manifest_sha256=anchor,scientific_verification=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    b=sub.add_parser('build');b.add_argument('--spec',type=Path,required=True);b.add_argument('--sha256',required=True);b.add_argument('--root',type=Path,required=True);b.add_argument('--output',type=Path,required=True)
    v=sub.add_parser('verify');v.add_argument('--bundle',type=Path,required=True);v.add_argument('--sha256',required=True);a=p.parse_args()
    try:
        result=build(a.spec,a.sha256,a.root,a.output) if a.action=='build' else verify(a.bundle,a.sha256)
        print(json.dumps(result,ensure_ascii=True));return 0
    except (ValueError,OSError,KeyError,TypeError,RecursionError) as error:
        print(json.dumps(dict(status='rejected',reason=str(error)),ensure_ascii=True));return 2


if __name__=='__main__':raise SystemExit(main())
