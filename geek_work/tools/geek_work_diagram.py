#!/usr/bin/env python3
"""Render a bounded, source-bound diagram; citations certify bytes, not meaning."""
import argparse
import html
import json
from pathlib import Path
import textwrap

import geek_work_manuscript as m
import geek_work_manuscript_claims as k
import geek_work_batch_hunks as archive
import geek_work_file_operations as ops
import knowledge

MAX_TOTAL = 8 * 1024 * 1024
NODE_STATES = {'formal_reported', 'empirical_reported', 'reference_only', 'hypothesis', 'open'}
RELATIONS = {'formal_dependency', 'editorial_link', 'application_hypothesis'}
EDGE_STATES = {'reported', 'proposed'}


def label(value):
    k.text(value)
    m.require(len(value) <= 90 and all(ord(c) >= 32 for c in value), 'single-line label, at most 90 characters')


def catalog(spec):
    k.obj(spec, 'schema id title sources nodes edges omissions merges')
    m.require(spec['schema'] == 'geek-work-diagram-1', 'diagram schema')
    k.ident(spec['id']); label(spec['title'])
    sources = {}; paths = set()
    for row in k.rows(spec['sources'], 8, 1):
        k.obj(row, 'id path sha256'); k.ident(row['id']); k.path_name(row['path']); k.digest(row['sha256'])
        m.require(row['id'] not in sources and row['path'].casefold() not in paths, 'duplicate source ID/path')
        sources[row['id']] = row; paths.add(row['path'].casefold())
    for key in ('omissions', 'merges'):
        k.strings(spec[key])
    return sources


def derive(spec, blobs):
    sources = catalog(spec)
    m.require(set(blobs) == set(sources) and sum(map(len, blobs.values())) <= MAX_TOTAL, 'source snapshot set/size')
    texts = {}
    for sid, row in sources.items():
        m.require(m.sha(blobs[sid]) == row['sha256'], 'source hash mismatch')
        texts[sid] = k.utf8(blobs[sid])
    used = set(); node_ids = set(); edge_ids = set(); pairs = set()
    def citations(item):
        for citation in k.rows(item['citations'], 16, 1):
            k.span(citation, texts, 'source'); used.add(citation['source'])
    for node in k.rows(spec['nodes'], 16, 1):
        k.obj(node, 'id label state citations'); k.ident(node['id']); label(node['label'])
        m.require(node['id'] not in node_ids, 'duplicate node ID'); node_ids.add(node['id'])
        m.require(type(node['state']) is str and node['state'] in NODE_STATES, 'node reported state')
        citations(node)
    for edge in k.rows(spec['edges'], 32):
        k.obj(edge, 'id from to relation state label citations'); k.ident(edge['id']); label(edge['label'])
        m.require(edge['id'] not in edge_ids, 'duplicate edge ID'); edge_ids.add(edge['id'])
        for key in ('from', 'to'):
            m.require(type(edge[key]) is str and edge[key] in node_ids, 'unknown edge endpoint')
        m.require(edge['from'] != edge['to'], 'self-edge not supported')
        m.require(type(edge['relation']) is str and edge['relation'] in RELATIONS, 'relation type')
        m.require(type(edge['state']) is str and edge['state'] in EDGE_STATES, 'edge reported state')
        pair = (edge['from'], edge['to'], edge['relation'])
        m.require(pair not in pairs, 'duplicate directed relation'); pairs.add(pair)
        citations(edge)
    return dict(schema='geek-work-diagram-report-1', status='byte_bindings_verified',
                node_ids=[n['id'] for n in spec['nodes']], edge_ids=[e['id'] for e in spec['edges']],
                unused_sources=sorted(set(sources)-used), omissions_declared=spec['omissions'], merges_declared=spec['merges'],
                semantic_correspondence_verified=False, formal_dependencies_verified=False,
                graph_completeness_verified=False, kernel_replayed=False, scientific_verification=False,
                publication_authorized=False)


def svg(spec):
    esc = lambda x: html.escape(str(x), quote=True)
    width = 640 + 24 * len(spec['edges']); height = 120 + 170 * len(spec['nodes'])
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="diagram-title diagram-desc">',
           '<title id="diagram-title">'+esc(spec['title'])+'</title>',
           '<desc id="diagram-desc">Source-bound editorial diagram. Relations and states are reported, not verified. Edge labels and citations are in the accompanying HTML.</desc>',
           '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#526578"/></marker></defs>',
           f'<rect width="{width}" height="{height}" fill="#f5f7fa"/>',
           '<text x="32" y="35" font-family="system-ui,sans-serif" font-size="22" fill="#172c40">Source-bound diagram</text>',
           '<text x="32" y="65" font-family="system-ui,sans-serif" font-size="14" fill="#526578">Reported states / declared links — not a verified proof DAG</text>']
    positions = {n['id']: 100 + 170*i for i,n in enumerate(spec['nodes'])}
    colors = {'formal_reported':'#196f69', 'empirical_reported':'#2c648f', 'reference_only':'#526578', 'hypothesis':'#8557a1', 'open':'#915b17'}
    for node in spec['nodes']:
        y = positions[node['id']]; color = colors[node['state']]
        out += [f'<g data-node-id="{esc(node["id"])}"><title>{esc(node["id"])}</title>',
                f'<rect x="32" y="{y}" width="540" height="130" rx="10" fill="white" stroke="{color}" stroke-width="2"/>',
                f'<text x="48" y="{y+23}" font-family="monospace" font-size="12" fill="{color}">{esc(node["id"])}</text>',
                f'<text x="48" y="{y+42}" font-family="monospace" font-size="12" fill="{color}">{esc(node["state"])}</text>']
        for i,line in enumerate(textwrap.wrap(node['label'], width=38)):
            out.append(f'<text x="48" y="{y+66+i*23}" font-family="system-ui,sans-serif" font-size="18" fill="#172c40">{esc(line)}</text>')
        out.append('</g>')
    patterns = {'formal_dependency':'', 'editorial_link':'8 5', 'application_hypothesis':'2 5'}
    for i,edge in enumerate(spec['edges']):
        y1 = positions[edge['from']]+65; y2 = positions[edge['to']]+65; x = 604+24*i
        out += [f'<g data-edge-id="{esc(edge["id"])}"><title>{esc(edge["id"])}: {esc(edge["from"])} → {esc(edge["to"])}; {esc(edge["relation"])}; {esc(edge["state"])}; {esc(edge["label"])}</title>',
                f'<path d="M 574 {y1} H {x} V {y2} H 574" fill="none" stroke="#526578" stroke-width="2" stroke-dasharray="{patterns[edge["relation"]]}" marker-end="url(#arrow)"/>',
                f'<text x="{x+3}" y="{(y1+y2)//2}" font-family="monospace" font-size="12" fill="#172c40">{i+1}</text></g>']
    return (''.join(out)+'</svg>\n').encode()


def page(spec, report, image):
    esc = lambda x: html.escape(str(x), quote=True)
    out = ['''<!doctype html><html lang="en"><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Source-bound diagram</title>
<style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:1rem;color:#172c40}svg{display:block;width:100%;min-width:680px}.diagram{overflow-x:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f7fa;padding:1rem}article{border-top:1px solid #bbc8d4;padding:1rem 0}li{margin:.5rem 0}</style>
<h1>Source-bound diagram</h1><p>Exact citations bind bytes, not meaning. No Lean replay, dependency extraction, completeness or publication approval.</p><div class="diagram">''', image.decode(), '</div>',
           '<h2>Directed relations</h2><p>Solid: formal_dependency (reported only). Dashed: editorial_link. Dotted: application_hypothesis.</p><ol>']
    for edge in spec['edges']:
        out.append('<li>'+esc(edge['id'])+': '+esc(edge['from'])+' → '+esc(edge['to'])+' — '+esc(edge['label'])+' ['+esc(edge['relation'])+'; '+esc(edge['state'])+']</li>')
    out.append('</ol><h2>Exact citations</h2>')
    for item in spec['nodes'] + spec['edges']:
        out.append('<article><h3>'+esc(item['id'])+' — '+esc(item['label'])+'</h3>')
        for c in item['citations']:
            out.append('<p>'+esc(c['source'])+' codepoints ['+str(c['start'])+', '+str(c['end'])+')</p><pre>'+esc(c['quote'])+'</pre>')
        out.append('</article>')
    for title,value in [('Pinned materials',spec['sources']),('Declared omissions',spec['omissions']),('Declared merges',spec['merges']),('Structural report and limits',report)]:
        out.append('<h2>'+title+'</h2><pre>'+esc(json.dumps(value,ensure_ascii=False,indent=2))+'</pre>')
    raw=(''.join(out).replace('<h1>Source-bound diagram</h1>', '<h1>'+esc(spec['title'])+'</h1>', 1)+'</html>\n').encode(); m.require(len(raw)<=m.MAX_ARTIFACT,'HTML byte bound'); return raw


def content(raw, blobs):
    spec = knowledge.strict_json(raw); report = derive(spec, blobs); image = svg(spec)
    return {'spec.json':raw, **{'sources/'+sid+'.txt':data for sid,data in blobs.items()},
            'report.json':m.encoded(report), 'diagram.svg':image, 'index.html':page(spec,report,image)}


def manifest(files):
    return m.encoded(dict(schema='geek-work-diagram-archive-1',files={name:m.sha(raw) for name,raw in files.items()}))


def build(spec_path, anchor, root, output):
    k.digest(anchor); ops.outside(output,root,spec_path)
    raw = m.read(spec_path); m.require(m.sha(raw)==anchor,'spec anchor mismatch')
    spec = knowledge.strict_json(raw); refs = catalog(spec)
    files = content(raw,{sid:k.read_source(root,row['path']) for sid,row in refs.items()})
    meta = manifest(files); archive.write_tree(output,{**files,'manifest.json':meta})
    return dict(status='diagram_built',manifest_sha256=m.sha(meta),scientific_verification=False)


def verify(bundle, anchor):
    k.digest(anchor); m.require(bundle.is_dir() and not bundle.is_symlink(),'regular archive directory')
    meta = m.read(bundle/'manifest.json'); m.require(m.sha(meta)==anchor,'archive anchor mismatch')
    raw = m.read(bundle/'spec.json'); refs = catalog(knowledge.strict_json(raw))
    blobs = {sid:k.read_source(bundle,'sources/'+sid+'.txt') for sid in refs}
    files = content(raw,blobs)
    m.require(meta==manifest(files),'manifest reproduction mismatch')
    archive.exact_tree(bundle,set(files)|{'manifest.json'})
    for name,data in files.items():
        m.require(m.read(bundle/name,max(len(data),1))==data,'artifact reproduction mismatch')
    return dict(status='diagram_integrity_reproduced',manifest_sha256=anchor,scientific_verification=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    b=sub.add_parser('build');b.add_argument('--spec',type=Path,required=True);b.add_argument('--sha256',required=True);b.add_argument('--root',type=Path,required=True);b.add_argument('--output',type=Path,required=True)
    v=sub.add_parser('verify');v.add_argument('--bundle',type=Path,required=True);v.add_argument('--sha256',required=True);a=p.parse_args()
    try:
        result=build(a.spec,a.sha256,a.root,a.output) if a.action=='build' else verify(a.bundle,a.sha256)
        print(json.dumps(result));return 0
    except (ValueError,OSError,KeyError,TypeError,RecursionError) as error:
        print(json.dumps(dict(status='rejected',reason=str(error))));return 2


if __name__=='__main__':raise SystemExit(main())
