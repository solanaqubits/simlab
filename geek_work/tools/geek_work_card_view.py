#!/usr/bin/env python3
"""Portable read-only cards over existing memory retrieval; no evidence promotion."""
import argparse
import html
from pathlib import Path
from urllib.parse import quote

import knowledge as k
import geek_work_memory as memory
import geek_work_manuscript as m
import geek_work_manuscript_claims as claims
import geek_work_batch_hunks as tree
import geek_work_file_operations as ops

SCHEMA = 'geek-work-card-view-1'
MAX_SOURCES = 64
MAX_SOURCE_TOTAL = 16 * 1024 * 1024
FLAGS = dict(semantic_support_verified=False, independent_review_verified=False,
             scientific_verification=False, publication_authorized=False, live_graph_modified=False)


def select(graph_raw, request_raw, root):
    graph=k.strict_json(graph_raw);request=k.strict_json(request_raw)
    context=memory.retrieve(graph,root,request)
    selected={row['card']['id'] for row in context['cards']}
    boundary=[edge for edge in graph['links'] if (edge['from'] in selected)!=(edge['to'] in selected)]
    return dict(schema=SCHEMA,graph_file_sha256=m.sha(graph_raw),request_file_sha256=m.sha(request_raw),
                context=context,boundary_links=boundary,omitted_card_count=len(graph['cards'])-len(selected),
                full_graph_archived=True,unselected_sources_checked=False,**FLAGS)


def sources(report, root):
    refs={}
    for row in report['context']['cards']:
        for source in row['source_checks']:
            claims.path_name(source['ref'])
            previous=refs.setdefault(source['ref'],source)
            # Different expected hashes can legitimately produce different per-card warnings;
            # the observed byte state for a single path must nevertheless agree.
            m.require(previous['actual_sha256']==source['actual_sha256'],'source changed during retrieval')
    m.require(len(refs)<=MAX_SOURCES,'selected source count limit')
    files={};total=0
    for ref,source in sorted(refs.items()):
        if source['state']=='missing':
            m.require(not (root/ref).exists(),'source appeared during capture')
            continue
        raw=claims.read_source(root,ref)
        m.require(m.sha(raw)==source['actual_sha256'],'source changed during capture')
        total+=len(raw);m.require(total<=MAX_SOURCE_TOTAL,'aggregate selected source byte limit')
        files['sources/'+ref]=raw
    return files


def render(report):
    esc=lambda value:html.escape(str(value),quote=True)
    context=report['context'];rows=context['cards']
    anchors={row['card']['id']:'card-'+str(i) for i,row in enumerate(rows)}
    def pre(value):return '<pre>'+esc(value if isinstance(value,str) else m.encoded(value).decode())+'</pre>'
    def link(cid):
        return '<a href="#'+anchors[cid]+'">'+esc(cid)+'</a>' if cid in anchors else esc(cid)+' (outside selection)'
    page=['''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Knowledge cards — pinned review</title>
<style>body{font:17px/1.55 system-ui;max-width:1080px;padding:1rem;margin:1rem auto;color:#173248;background:#fafcfe;overflow-wrap:anywhere}article{border:1px solid #bdcbd8;background:white;border-radius:10px;padding:1rem;margin:1.5rem 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;background:#f1f5f8;padding:.8rem}a{color:#145b87}details{border-top:1px solid #cbd6df;padding:.7rem 0}summary{font-weight:bold;cursor:pointer}summary:focus-visible,a:focus-visible{outline:3px solid #287abb;outline-offset:3px}.notice{padding:1rem;border-left:5px solid #aa6a16;background:#fff3df}.axes{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:.7rem}.axis{border:1px solid #cbd6df;padding:.7rem}h2,h3{line-height:1.3}</style>
<h1>Knowledge cards — pinned review</h1>
<p class="notice">Recorded claims and evidence are shown unchanged. Hash matches verify material bytes, not truth, authorship or support. Effective review state concerns this saved graph, not current project state. No semantic approval is issued.</p>''',
        '<p>Retrieval disposition: <strong>'+esc(context['disposition'])+'</strong></p>',
        '<p>Private archive includes the full graph and selected material files. Unselected sources are not checked.</p>',
        '<details><summary>Snapshot identity and retrieval issues</summary>'+pre({key:context[key] for key in ('graph_sha256','expected_graph_sha256','issues')})+'</details>',
        '<nav aria-label="Selected cards"><ul>']
    for row in rows:page.append('<li>'+link(row['card']['id'])+' — '+esc(row['card']['title'])+'</li>')
    page.append('</ul></nav>')
    for row in rows:
        c=row['card'];page.extend(['<article id="'+anchors[c['id']]+'"><h2>'+esc(c['title'])+'</h2>',
            '<p>'+esc(c['id'])+' · revision '+str(c['revision'])+' · '+esc(c['kind'])+' · '+('requested' if row['requested'] else 'dependency / objection closure')+'</p>',
            '<p>Recorded claim status: <strong>'+esc(c['status'])+'</strong><br>Recorded review: '+esc(c['review']['state'])+' · Effective review: <strong>'+esc(row['effective_review'])+'</strong></p>',
            '<p class="notice">Review issues: '+esc(', '.join(row['issues']) or 'none detected by structural retrieval; not semantic approval')+'</p>',
            '<h3>Statement</h3>'+pre(c['text']),'<h3>Scope</h3>'+pre(c['scope']),'<h3>Assumptions</h3>'])
        page.append('<ul>'+''.join('<li>'+esc(a)+'</li>' for a in c['assumptions'])+'</ul>' if c['assumptions'] else '<p>No assumptions listed; completeness has not been verified.</p>')
        page.append('<h3>Recorded evidence axes</h3><div class="axes">')
        for axis,value in c['evidence'].items():page.append('<section class="axis"><h4>'+esc(axis)+' · '+esc(value['state'])+'</h4>'+pre(value)+'</section>')
        page.append('</div><details open><summary>Details, boundaries and proof outline (as recorded)</summary>'+pre(c['detail'])+'</details>')
        page.append('<details><summary>Review date, applicability and dependency revisions</summary>'+pre(c['review'])+'</details>')
        page.append('<details><summary>Classification</summary>'+pre({key:c[key] for key in ('domains','directions','tags','categories','projects')})+'</details>')
        page.append('<h3>Materials and byte checks</h3>')
        for source in row['source_checks']:
            href='sources/'+quote(source['ref'],safe='/')
            label=esc(source['ref']) if source['state']=='missing' else '<a href="'+esc(href)+'">'+esc(source['ref'])+'</a>'
            page.append('<p>'+label+' · <strong>'+esc(source['state'])+'</strong></p>'+pre(source))
        page.append('<details><summary>Complete unchanged card JSON</summary>'+pre(c)+'</details></article>')
    page.append('<h2>Recorded relations and selection boundary</h2><p>Editorial graph relations are not a kernel-derived proof DAG. Links to omitted cards are explicitly marked.</p>')
    for edge in context['links']+report['boundary_links']:
        page.append('<p>'+link(edge['from'])+' → '+esc(edge['relation'])+' → '+link(edge['to'])+'</p>'+pre(edge['scope']))
    page.append('<p>Cards outside the displayed selection: '+str(report['omitted_card_count'])+'</p></html>\n')
    raw=''.join(page).encode();m.require(len(raw)<=k.MAX_BYTES,'card HTML byte limit');return raw


def payload(graph_raw,request_raw,root):
    report=select(graph_raw,request_raw,root);files=sources(report,root)
    encoded=m.encoded(report);m.require(len(encoded)<=k.MAX_BYTES,'card report byte limit')
    return {**files,'graph.json':graph_raw,'request.json':request_raw,'report.json':encoded,'index.html':render(report)}


def manifest(files):return m.encoded(dict(schema=SCHEMA,files={n:m.sha(b) for n,b in files.items()},**FLAGS))


def build(graph,anchor,request,root,output):
    graph,request,root,output=map(Path,(graph,request,root,output))
    claims.digest(anchor);ops.outside(output,graph,request,root)
    raw=m.read(graph,k.MAX_BYTES);m.require(m.sha(raw)==anchor,'graph file anchor mismatch')
    files=payload(raw,m.read(request,k.MAX_BYTES),root);meta=manifest(files)
    tree.write_tree(output,{**files,'manifest.json':meta})
    return dict(status='card_view_ready',manifest_sha256=m.sha(meta),**FLAGS)


def verify(bundle,anchor):
    bundle=Path(bundle);claims.digest(anchor)
    meta=m.read(bundle/'manifest.json',k.MAX_BYTES);m.require(m.sha(meta)==anchor,'view manifest anchor mismatch')
    files=payload(m.read(bundle/'graph.json',k.MAX_BYTES),m.read(bundle/'request.json',k.MAX_BYTES),bundle/'sources')
    tree.exact_tree(bundle,set(files)|{'manifest.json'})
    m.require(meta==manifest(files),'view manifest reproduction mismatch')
    for name,raw in files.items():m.require(m.read(bundle/name,k.MAX_BYTES)==raw,'view artifact reproduction mismatch')
    return dict(status='card_view_reproduced',manifest_sha256=anchor,**FLAGS)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['build','verify'])
    p.add_argument('--graph',type=Path);p.add_argument('--request',type=Path);p.add_argument('--root',type=Path)
    p.add_argument('--output',type=Path);p.add_argument('--bundle',type=Path);p.add_argument('--sha256',required=True)
    a=p.parse_args()
    try:
        if a.action=='build':
            m.require(a.bundle is None and all(x is not None for x in (a.graph,a.request,a.root,a.output)),'build requires graph/request/root/output')
            result=build(a.graph,a.sha256,a.request,a.root,a.output)
        else:
            m.require(a.bundle is not None and all(x is None for x in (a.graph,a.request,a.root,a.output)),'verify requires only bundle/sha256')
            result=verify(a.bundle,a.sha256)
        print(m.encoded(result).decode(),end='');return 0
    except (ValueError,OSError,UnicodeError) as error:
        print(m.encoded(dict(status='refused',reason=str(error))).decode(),end='');return 2


if __name__=='__main__':raise SystemExit(main())
