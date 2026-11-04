#!/usr/bin/env python3
"""Compose pinned manuscript proposals, guard reviews and declared diagram links."""
import argparse
import html
import json
from pathlib import Path

import geek_work_manuscript as m
import geek_work_manuscript_hunks as h
import geek_work_manuscript_claims as k
import geek_work_manuscript_status as status
import geek_work_editorial_guards as guards
import geek_work_diagram as diagram
import geek_work_batch_hunks as archive
import geek_work_file_operations as ops
import knowledge

MAX_BYTES = 64 * 1024 * 1024
MAX_FILES = 128


def plan(raw):
    spec=knowledge.strict_json(raw);k.obj(spec,'schema title proposal guards diagrams')
    m.require(spec['schema']=='geek-work-document-review-1','document review schema');k.text(spec['title'])
    paths=[];ids=set()
    def reference(ref):
        k.obj(ref,'path sha256');k.path_name(ref['path']);k.digest(ref['sha256']);paths.append(ref['path'].casefold())
    reference(spec['proposal'])
    if spec['guards'] is not None:reference(spec['guards'])
    for row in k.rows(spec['diagrams'],4):
        k.obj(row,'id archive selected_node_ids context rationale');k.ident(row['id']);k.text(row['rationale'])
        m.require(row['id'] not in ids,'duplicate diagram ID');ids.add(row['id']);reference(row['archive'])
        for nid in k.rows(row['selected_node_ids'],16,1):k.ident(nid)
        m.require(len(set(row['selected_node_ids']))==len(row['selected_node_ids']),'duplicate selected node')
    for i,path in enumerate(paths):
        for other in paths[i+1:]:
            m.require(path!=other and not path.startswith(other+'/') and not other.startswith(path+'/'),'overlapping/case-colliding input archives')
    return spec


def read_member(root,name):
    parts=k.path_name(name).parts
    parent=root if len(parts)==1 else status.folder(root,'/'.join(parts[:-1]))
    return m.read(parent/parts[-1])


def collect(raw,root,replay=False):
    spec=plan(raw);files={};total=0
    def take(ref,destination,verifier):
        nonlocal total
        folder=status.folder(root,destination if replay else ref['path'])
        verifier(folder,ref['sha256'])
        meta=m.read(folder/'manifest.json');manifest=knowledge.strict_json(meta)
        m.require(type(manifest.get('files')) is dict and len(manifest['files'])<=MAX_FILES,'nested file count')
        names=set(manifest['files'])|{'manifest.json'}
        for name in sorted(names):
            data=read_member(folder,name);total+=len(data)
            m.require(total<=MAX_BYTES and len(files)<MAX_FILES,'composite snapshot bound')
            files[destination+'/'+name]=data
        return folder
    p=take(spec['proposal'],'inputs/proposal',h.verified)
    proposal,data,rows,_=h.verified(p,spec['proposal']['sha256'])
    guard_report=None
    if spec['guards'] is not None:
        folder=take(spec['guards'],'inputs/guards',guards.verify)
        guard_report=knowledge.strict_json(m.read(folder/'report.json'))
        m.require(guard_report['proposal_sha256']==spec['proposal']['sha256'],'CHAIN_MISMATCH: guard/proposal')
        m.require(guard_report['base_sha256']==m.sha(data['before.txt']) and guard_report['candidate_sha256']==m.sha(data['after.txt']),'CHAIN_MISMATCH: guard/document')
    texts={'before':data['before.txt'].decode(),'after':data['after.txt'].decode()};links=[]
    for link in spec['diagrams']:
        folder=take(link['archive'],'inputs/diagrams/'+link['id'],diagram.verify)
        view=knowledge.strict_json(m.read(folder/'report.json'));dspec=knowledge.strict_json(m.read(folder/'spec.json'))
        m.require(set(link['selected_node_ids'])<=set(view['node_ids']),'selected diagram node missing')
        k.span(link['context'],texts,'source')
        links.append(dict(id=link['id'],manifest_sha256=link['archive']['sha256'],title=dspec['title'],
                          selected_node_ids=link['selected_node_ids'],context=link['context'],rationale=link['rationale'],
                          node_count=len(view['node_ids']),edge_count=len(view['edge_ids']),
                          relationship_verified=False,graph_completeness_verified=False))
    report=dict(schema='geek-work-document-review-report-1',status='review_required',title=spec['title'],
        document=proposal['document'],proposal_sha256=spec['proposal']['sha256'],base_sha256=m.sha(data['before.txt']),
        candidate_sha256=m.sha(data['after.txt']),hunk_ids=[r['id'] for r in rows],
        guard_review=None if guard_report is None else dict(manifest_sha256=spec['guards']['sha256'],
             status=guard_report['status'],selected_guards=len(guard_report['guards']),
             changed_guard_count=guard_report['changed_guard_count'],unguarded_hunks=guard_report['unguarded_hunks']),
        diagrams=links,missing_optional_views=(['guard_review'] if guard_report is None else [])+(['diagram'] if not links else []),
        proposal_guard_chain_consistent=guard_report is not None,
        semantic_preservation_verified=False,independent_review_verified=False,scientific_verification=False,
        live_document_checked=False,live_document_modified=False,publication_authorized=False)
    return files,report,data,rows


def render(report,data,rows):
    esc=lambda value:html.escape(str(value),quote=True)
    out=['''<!doctype html><html lang="en"><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Manuscript review desk</title>
<style>body{font:16px system-ui;max-width:1120px;margin:2rem auto;padding:1rem;color:#173248}nav{display:flex;gap:1rem;flex-wrap:wrap}article{border:1px solid #c1ccd5;padding:1rem;margin:1rem 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:1rem}.notice{background:#fff3df;border-left:5px solid #9b6218;padding:1rem}a{color:#175d8b}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1rem}h2{margin-top:2rem}.diagram{display:block;max-width:100%;max-height:560px;margin:1rem 0;object-fit:contain;object-position:left}</style>''',
         '<h1>'+esc(report['title'])+'</h1>',
         '<p class="notice">Review required. This desk checks archive integrity and declared links, not preserved meaning or scientific correctness. No live document is checked or changed.</p>',
         '<nav><a href="#changes">All changes</a><a href="#guards">Guards</a><a href="#diagrams">Diagrams</a><a href="#identity">Pinned versions</a><a href="inputs/proposal/review.html">Full before/after</a><a href="inputs/proposal/hunk-review.html">Existing hunk review</a></nav>',
         '<h2 id="identity">Pinned document versions</h2><pre>'+esc(json.dumps({k:report[k] for k in ('document','proposal_sha256','base_sha256','candidate_sha256')},indent=2,ensure_ascii=False))+'</pre>',
         '<h2 id="guards">Guard review</h2>']
    if report['guard_review'] is None:
        out.append('<p class="notice">No guard archive attached. Every changed block still requires review.</p>')
    else:
        g=report['guard_review'];out.append('<p><a href="inputs/guards/index.html">Open source-bound guard report</a></p><p>'+str(g['selected_guards'])+' selected guards; '+str(g['changed_guard_count'])+' overlap changed blocks; '+str(len(g['unguarded_hunks']))+' unguarded blocks. No overlap is not semantic approval.</p>')
    out.append('<h2 id="diagrams">Declared diagram associations</h2>')
    if not report['diagrams']:out.append('<p>No diagram selected. This is not a statement that no diagram exists.</p>')
    for link in report['diagrams']:
        out.append('<article><h3>'+esc(link['title'])+'</h3><p><a href="inputs/diagrams/'+esc(link['id'])+'/index.html">Open diagram and exact material citations</a></p><p>Selected nodes: '+esc(', '.join(link['selected_node_ids']))+'</p><p>'+esc(link['rationale'])+'</p><p>Context in '+esc(link['context']['source'])+'; association supplied by the author, not semantically verified:</p><pre>'+esc(link['context']['quote'])+'</pre><img class="diagram" src="inputs/diagrams/'+esc(link['id'])+'/diagram.svg" alt="'+esc(link['title'])+'"></article>')
    out.append('<h2 id="changes">Every changed block</h2>')
    for row in rows:
        out.append('<article><h3>'+esc(row['id'])+' — '+esc(row['kind'])+'</h3><div class="grid"><section><h4>Before</h4><pre>'+esc(row['before_text'])+'</pre></section><section><h4>Candidate</h4><pre>'+esc(row['after_text'])+'</pre></section></div></article>')
    out.append('<h2>Boundaries</h2><p>Use the existing hunk decision protocol separately after reviewing the assembled candidate. This page does not collect decisions, prove reviewer independence, grant publication permission or replace the compile/PDF status chain.</p><details><summary>Reproducible report</summary><pre>'+esc(json.dumps(report,ensure_ascii=False,indent=2))+'</pre></details></html>\n')
    raw=''.join(out).encode();m.require(len(raw)<=m.MAX_ARTIFACT,'review page byte bound');return raw


def content(raw,root,replay=False):
    files,report,data,rows=collect(raw,root,replay)
    report_raw=m.encoded(report);m.require(len(report_raw)<=m.MAX_ARTIFACT,'report byte bound')
    return {'spec.json':raw,**files,'report.json':report_raw,'index.html':render(report,data,rows)}


def manifest(files):
    return m.encoded(dict(schema='geek-work-document-review-archive-1',files={n:m.sha(raw) for n,raw in files.items()}))


def build(spec_path,anchor,root,output):
    k.digest(anchor);ops.outside(output,root,spec_path);raw=m.read(spec_path);m.require(m.sha(raw)==anchor,'spec SHA mismatch')
    files=content(raw,root);meta=manifest(files);archive.write_tree(output,{**files,'manifest.json':meta})
    return dict(status='review_required',manifest_sha256=m.sha(meta),scientific_verification=False)


def verify(bundle,anchor):
    k.digest(anchor);m.require(bundle.is_dir() and not bundle.is_symlink(),'regular review archive')
    meta=m.read(bundle/'manifest.json');m.require(m.sha(meta)==anchor,'review SHA mismatch')
    files=content(m.read(bundle/'spec.json'),bundle,True)
    m.require(meta==manifest(files),'manifest reproduction mismatch');archive.exact_tree(bundle,set(files)|{'manifest.json'})
    for name,data in files.items():m.require(m.read(bundle/name,max(len(data),1))==data,'review reproduction mismatch')
    return dict(status='document_review_integrity_reproduced',review_disposition='review_required',manifest_sha256=anchor,scientific_verification=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    q=sub.add_parser('build')
    for n in ('spec','root','output'):q.add_argument('--'+n,type=Path,required=True)
    q.add_argument('--sha256',required=True)
    q=sub.add_parser('verify');q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True);a=p.parse_args()
    try:
        result=build(a.spec,a.sha256,a.root,a.output) if a.action=='build' else verify(a.bundle,a.sha256)
        print(json.dumps(result));return 0
    except (ValueError,OSError,KeyError,TypeError,RecursionError) as error:
        print(json.dumps(dict(status='rejected',reason=str(error))));return 2


if __name__=='__main__':raise SystemExit(main())
