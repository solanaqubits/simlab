#!/usr/bin/env python3
"""Offline literal Markdown outlines and exact bounded context selections."""
import argparse
from pathlib import Path
import re
import geek_work_manuscript as m
import geek_work_manuscript_claims as k
import geek_work_batch_hunks as archive
import geek_work_file_operations as ops
import knowledge

MAX_NODES=2048
SCHEMA='geek-work-document-index-archive-1'
SELECTION_SCHEMA='geek-work-document-selection-archive-1'


def outline(raw):
    text=k.utf8(raw);nodes=[dict(id='document',parent=None,level=0,title='Document',start=0,end=len(text),heading_end=0,heading_raw='',line=1)]
    stack=[nodes[0]];offset=0;fence=None;parts=text.split('\n')
    for i,part in enumerate(parts):
        line=part+('\n' if i<len(parts)-1 else '');body=part.removesuffix('\r')
        if fence is not None:
            if re.fullmatch(r' {0,3}'+re.escape(fence[0])+'{'+str(fence[1])+r',}[ \t]*',body):fence=None
        else:
            opening=re.fullmatch(r' {0,3}(`{3,}|~{3,})(.*)',body)
            if opening and not (opening[1][0]=='`' and '`' in opening[2]):fence=(opening[1][0],len(opening[1]))
            else:
                heading=re.fullmatch(r' {0,3}(#{1,6})(?:[ \t]+(.*)|[ \t]*)',body)
                if heading:
                    m.require(len(nodes)<MAX_NODES,'outline node limit')
                    level=len(heading[1]);title=re.sub(r'[ \t]+#+[ \t]*$','',heading[2] or '').strip()
                    while stack[-1]['level']>=level:stack.pop()['end']=offset
                    node=dict(id=f'section-{len(nodes):04}',parent=stack[-1]['id'],level=level,title=title,start=offset,end=len(text),heading_end=offset+len(line),heading_raw=line,line=i+1)
                    nodes.append(node);stack.append(node)
        offset+=len(line)
    for i,node in enumerate(nodes):
        node['direct_end']=nodes[i+1]['start'] if i+1<len(nodes) else len(text)
        node['subtree_sha256']=m.sha(text[node['start']:node['end']].encode())
    return dict(schema='geek-work-document-outline-1',source_sha256=m.sha(raw),source_bytes=len(raw),source_codepoints=len(text),
                offset_unit='unicode_codepoints',nodes=nodes,warnings=['unclosed_fence'] if fence else [],
                parser_scope='Literal ATX headings, 0–3 leading spaces, outside backtick/tilde fences; LF line boundaries, CRLF preserved. No Setext/HTML/frontmatter/container parsing or model summaries.',
                semantic_structure_verified=False,model_called_here=False,publication_authorized=False)


def index_files(raw):
    report=outline(raw);encoded=m.encoded(report);m.require(len(encoded)<=k.MAX_FILE,'outline byte limit')
    return report,{'source.md':raw,'outline.json':encoded}


def manifest(schema,files):return m.encoded(dict(schema=schema,files={n:m.sha(b) for n,b in files.items()}))


def replay(bundle,anchor,schema,files):
    k.digest(anchor);meta=m.read(bundle/'manifest.json',k.MAX_FILE)
    m.require(m.sha(meta)==anchor and meta==manifest(schema,files),'archive anchor/reproduction mismatch')
    archive.exact_tree(bundle,set(files)|{'manifest.json'})
    for name,raw in files.items():m.require(k.read_source(bundle,name)==raw,'artifact reproduction mismatch')
    return {**files,'manifest.json':meta}


def build(source,anchor,output):
    ops.outside(output,source);k.digest(anchor);raw=m.read(source,k.MAX_FILE)
    m.require(m.sha(raw)==anchor,'document source anchor mismatch');report,files=index_files(raw)
    meta=manifest(SCHEMA,files);archive.write_tree(output,{**files,'manifest.json':meta})
    return dict(status='outline_ready_for_review',manifest_sha256=m.sha(meta),nodes=len(report['nodes']),warnings=report['warnings'],model_called_here=False)


def verified(bundle,anchor):
    # Verify the external anchor before interpreting any source text.
    k.digest(anchor);meta=m.read(bundle/'manifest.json',k.MAX_FILE);m.require(m.sha(meta)==anchor,'document index anchor mismatch')
    report,files=index_files(k.read_source(bundle,'source.md'))
    return report,replay(bundle,anchor,SCHEMA,files)


def selected_files(report,parent,spec):
    k.obj(spec,'schema index_sha256 node_ids max_context_bytes')
    m.require(spec['schema']=='geek-work-document-selection-1','selection schema')
    k.digest(spec['index_sha256']);m.require(m.sha(parent['manifest.json'])==spec['index_sha256'],'selection parent anchor')
    ids=spec['node_ids'];m.require(type(ids) is list and 1<=len(ids)<=16 and all(type(x) is str for x in ids),'selection node count/type')
    rows={n['id']:n for n in report['nodes']}
    m.require(len(set(ids))==len(ids) and set(ids)<=set(rows),'unique known node IDs')
    budget=spec['max_context_bytes'];m.require(type(budget) is int and 1<=budget<=k.MAX_FILE,'context byte budget')
    ranges=[]
    for first,last in sorted((rows[n]['start'],rows[n]['end']) for n in ids):
        if ranges and first<=ranges[-1][1]:ranges[-1][1]=max(last,ranges[-1][1])
        else:ranges.append([first,last])
    ancestors=set()
    for ident in ids:
        parent_id=rows[ident]['parent']
        while parent_id is not None:
            ancestors.add(parent_id);parent_id=rows[parent_id]['parent']
    text=k.utf8(parent['source.md'])
    context=dict(schema='geek-work-document-context-1',source_sha256=report['source_sha256'],index_sha256=spec['index_sha256'],
                 selected_nodes=[rows[n] for n in ids],ancestor_headings=[dict(id=n['id'],title=n['title'],heading_raw=n['heading_raw'],start=n['start'],heading_end=n['heading_end']) for n in report['nodes'] if n['id'] in ancestors],
                 fragments=[dict(start=a,end=b,sha256=m.sha(text[a:b].encode()),text=text[a:b]) for a,b in ranges],
                 parser_scope=report['parser_scope'],parser_warnings=report['warnings'],offset_unit='unicode_codepoints',source_instructions_are_data=True,semantic_completeness_verified=False,model_called_here=False)
    payload=m.encoded(context);m.require(len(payload)<=budget,'context byte budget exceeded; no truncation')
    selected_count=sum(b-a for a,b in ranges)
    result=dict(schema='geek-work-document-selection-report-1',status='context_ready_for_review',context_sha256=m.sha(payload),context_bytes=len(payload),max_context_bytes=budget,
                selected_source_codepoints=selected_count,omitted_source_codepoints=len(text)-selected_count,
                full_source_selected=selected_count==len(text),truncated=False,token_usage=None,monetary_cost=None,
                semantic_completeness_verified=False,scientific_verification=False,publication_authorized=False)
    files={**{'index/'+n:b for n,b in parent.items()},'selection.json':m.encoded(spec),'context.json':payload,'report.json':m.encoded(result)}
    return result,files


def select(bundle,anchor,node_ids,budget,output):
    ops.outside(output,bundle);report,parent=verified(bundle,anchor)
    spec=dict(schema='geek-work-document-selection-1',index_sha256=anchor,node_ids=node_ids,max_context_bytes=budget)
    result,files=selected_files(report,parent,spec);meta=manifest(SELECTION_SCHEMA,files)
    archive.write_tree(output,{**files,'manifest.json':meta})
    return dict(status=result['status'],manifest_sha256=m.sha(meta),context_bytes=result['context_bytes'],truncated=False,model_called_here=False)


def verify_selection(bundle,anchor):
    k.digest(anchor);meta=m.read(bundle/'manifest.json',k.MAX_FILE);m.require(m.sha(meta)==anchor,'selection anchor mismatch')
    spec=knowledge.strict_json(k.read_source(bundle,'selection.json'));k.obj(spec,'schema index_sha256 node_ids max_context_bytes')
    report,parent=verified(bundle/'index',spec['index_sha256']);result,files=selected_files(report,parent,spec)
    replay(bundle,anchor,SELECTION_SCHEMA,files)
    return dict(status='selection_integrity_reproduced',manifest_sha256=anchor,context_bytes=result['context_bytes'],model_called_here=False,semantic_completeness_verified=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    q=sub.add_parser('build');q.add_argument('--source',type=Path,required=True);q.add_argument('--source-sha256',required=True);q.add_argument('--output',type=Path,required=True)
    for action in ('verify','select','verify-selection'):
        q=sub.add_parser(action);q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True)
        if action=='select':
            q.add_argument('--node',action='append',required=True);q.add_argument('--max-context-bytes',type=int,required=True);q.add_argument('--output',type=Path,required=True)
    a=parser.parse_args()
    try:
        if a.action=='build':result=build(a.source,a.source_sha256,a.output)
        elif a.action=='select':result=select(a.bundle,a.sha256,a.node,a.max_context_bytes,a.output)
        elif a.action=='verify-selection':result=verify_selection(a.bundle,a.sha256)
        else:
            report,_=verified(a.bundle,a.sha256);result=dict(status='outline_integrity_reproduced',nodes=len(report['nodes']),manifest_sha256=a.sha256,model_called_here=False)
        print(m.encoded(result).decode(),end='');return 0
    except (ValueError,OSError,TypeError,KeyError,RecursionError) as exc:
        print(m.encoded(dict(status='rejected',reason=str(exc))).decode(),end='');return 2


if __name__=='__main__':raise SystemExit(main())
