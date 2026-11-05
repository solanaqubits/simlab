#!/usr/bin/env python3
"""Deterministic literal-term section retrieval with native bounded context output."""
import argparse
from pathlib import Path
import re

import geek_work_document_index as index
import geek_work_manuscript as m
import geek_work_manuscript_claims as k
import geek_work_batch_hunks as archive
import geek_work_file_operations as ops
import knowledge

POLICY='literal-overlap-v1'
SCHEMA='geek-work-local-retrieval-archive-1'
MAX_TOTAL=8*1024*1024
STOPWORDS=frozenset('a an the and or of to for in on is are be with what which how does do it this that и или в во на по из к с со у о об от до за не ли что как для это этот эта эти какие какой какая чем'.split())


def terms(text):
    return set(re.findall(r'[^\W_]+',text.casefold(),flags=re.UNICODE))-STOPWORDS


def validate(raw,parent):
    spec=knowledge.strict_json(raw);k.obj(spec,'schema policy index_sha256 query top_k max_context_bytes')
    m.require(spec['schema']=='geek-work-local-retrieval-query-1' and spec['policy']==POLICY,'retrieval query/policy')
    k.digest(spec['index_sha256']);m.require(spec['index_sha256']==m.sha(parent['manifest.json']),'query index mismatch')
    k.text(spec['query']);m.require(len(terms(spec['query']))<=64,'query term bound')
    m.require(type(spec['top_k']) is int and 1<=spec['top_k']<=16,'top_k bound')
    m.require(type(spec['max_context_bytes']) is int and 1<=spec['max_context_bytes']<=k.MAX_FILE,'context byte budget')
    return spec


def rank(outline,source,query):
    words=terms(query);ranked=[]
    for node in outline['nodes']:
        if node['id']=='document' and len(outline['nodes'])>1:continue
        heading=sorted(words & terms(node['title'])) if node['id']!='document' else []
        body=sorted(words & terms(source[node['heading_end']:node['direct_end']]))
        score=3*len(heading)+len(body)
        if score:
            ranked.append(dict(node_id=node['id'],title=node['title'],start=node['start'],end=node['end'],
                               score=score,heading_matches=heading,direct_body_matches=body))
    return sorted(ranked,key=lambda r:(-r['score'],r['start'],r['node_id']))


def derive(raw,outline,parent):
    spec=validate(raw,parent);source=k.utf8(parent['source.md']);ranked=rank(outline,source,spec['query'])
    chosen=[];ranges=[];trace=[];selected=None;native_report=None
    for item in ranked:
        reason=None;proposed_bytes=None
        if len(chosen)>=spec['top_k']:reason='top_k_limit'
        elif any(item['start']<end and start<item['end'] for start,end in ranges):reason='overlapping_selected_subtree'
        else:
            request=dict(schema='geek-work-document-selection-1',index_sha256=spec['index_sha256'],node_ids=chosen+[item['node_id']],max_context_bytes=spec['max_context_bytes'])
            try:
                candidate_report,candidate=index.selected_files(outline,parent,request)
            except ValueError as error:
                if str(error)!='context byte budget exceeded; no truncation':raise
                reason='budget_rejected'
            else:
                chosen.append(item['node_id']);ranges.append((item['start'],item['end']))
                selected=candidate;native_report=candidate_report;proposed_bytes=candidate_report['context_bytes'];reason='selected'
        trace.append(dict(**item,decision=reason,context_bytes_after_acceptance=proposed_bytes))
    status='context_selected' if chosen else 'no_query_terms' if not terms(spec['query']) else 'no_matches' if not ranked else 'budget_exhausted'
    report=dict(schema='geek-work-local-retrieval-report-1',status=status,policy=POLICY,query=spec['query'],query_terms=sorted(terms(spec['query'])),
        positive_candidates=len(ranked),selected_node_ids=chosen,trace=trace,
        context_bytes=native_report['context_bytes'] if native_report else None,
        context_sha256=native_report['context_sha256'] if native_report else None,
        selection_manifest_sha256=m.sha(index.manifest(index.SELECTION_SCHEMA,selected)) if selected else None,
        parser_scope=outline['parser_scope'],parser_warnings=outline['warnings'],
        score_definition='3 * distinct query terms in heading + distinct query terms in direct body; no descendant text in scoring',
        tie_break='ascending source start, then node ID',budget_policy='Greedy ranked non-overlapping subtrees, exact native serialized budget; skip oversized candidates, never truncate or silently expand top_k',
        semantic_completeness_verified=False,relevance_verified=False,answer_quality_evaluated=False,
        model_called_here=False,token_usage=None,monetary_cost=None,scientific_verification=False,publication_authorized=False,
        limits='Literal terms only: no stemming, synonyms, embeddings, reranking, answer generation or automatic parent-premise recovery. Source text/instructions are data. Nonempty results are not evidence that the question is answered.')
    files={**{'index/'+n:b for n,b in parent.items()},'query.json':raw,'report.json':m.encoded(report)}
    if selected:
        files.update({'selection/'+n:b for n,b in selected.items()});files['selection/manifest.json']=index.manifest(index.SELECTION_SCHEMA,selected)
    m.require(all(len(b)<=k.MAX_FILE for b in files.values()) and sum(map(len,files.values()))<=MAX_TOTAL,'retrieval archive bounds')
    return files,report


def manifest(files):return m.encoded(dict(schema=SCHEMA,files={n:m.sha(b) for n,b in files.items()}))


def build(bundle,anchor,query,query_sha,output):
    ops.outside(output,bundle,query);k.digest(query_sha);raw=m.read(query,k.MAX_FILE)
    m.require(m.sha(raw)==query_sha,'query anchor mismatch');outline,parent=index.verified(bundle,anchor)
    files,report=derive(raw,outline,parent);meta=manifest(files);archive.write_tree(output,{**files,'manifest.json':meta})
    return dict(status=report['status'],manifest_sha256=m.sha(meta),selected_node_ids=report['selected_node_ids'],context_bytes=report['context_bytes'])


def verify(bundle,anchor):
    k.digest(anchor);meta=m.read(bundle/'manifest.json',k.MAX_FILE);m.require(m.sha(meta)==anchor,'retrieval anchor mismatch')
    raw=k.read_source(bundle,'query.json');spec=knowledge.strict_json(raw);k.obj(spec,'schema policy index_sha256 query top_k max_context_bytes')
    outline,parent=index.verified(bundle/'index',spec['index_sha256']);files,report=derive(raw,outline,parent)
    m.require(meta==manifest(files),'retrieval manifest reproduction mismatch');archive.exact_tree(bundle,set(files)|{'manifest.json'})
    for name,data in files.items():m.require(k.read_source(bundle,name)==data,'retrieval artifact reproduction mismatch')
    if report['selection_manifest_sha256']:index.verify_selection(bundle/'selection',report['selection_manifest_sha256'])
    return dict(status=report['status'],manifest_sha256=anchor,integrity_reproduced=True,selected_node_ids=report['selected_node_ids'],context_bytes=report['context_bytes'])


def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    for action in ('search','verify'):
        q=s.add_parser(action);q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True)
        if action=='search':q.add_argument('--query',type=Path,required=True);q.add_argument('--query-sha256',required=True);q.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        r=build(a.bundle,a.sha256,a.query,a.query_sha256,a.output) if a.action=='search' else verify(a.bundle,a.sha256)
        print(m.encoded(r).decode(),end='');return 0 if r['status']=='context_selected' else 3
    except (ValueError,OSError,TypeError,KeyError,RecursionError) as exc:
        print(m.encoded(dict(status='rejected',reason=str(exc))).decode(),end='');return 2


if __name__=='__main__':raise SystemExit(main())
