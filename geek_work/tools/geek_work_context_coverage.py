#!/usr/bin/env python3
"""Measure annotated-span presence in native document selections, not answer quality."""
import argparse
from pathlib import Path

import geek_work_document_index as index
import geek_work_manuscript as m
import geek_work_manuscript_claims as k
import geek_work_batch_hunks as archive
import geek_work_file_operations as ops
import knowledge

SCHEMA='geek-work-context-coverage-archive-1'
MAX_TOTAL=32*1024*1024


def union(ranges):
    result=[]
    for start,end in sorted(ranges):
        if start==end:continue
        if result and start<=result[-1][1]:result[-1][1]=max(result[-1][1],end)
        else:result.append([start,end])
    return result


def coverage(required,visible):
    count=sum(max(0,min(required['end'],b)-max(required['start'],a)) for a,b in union(visible))
    length=required['end']-required['start']
    return dict(id=required['id'],role=required['role'],status='covered' if count==length else 'missing' if count==0 else 'partial',
                covered_codepoints=count,required_codepoints=length)


def validate(raw,outline,parent):
    spec=knowledge.strict_json(raw);k.obj(spec,'schema index_sha256 annotation variants cases')
    m.require(spec['schema']=='geek-work-context-coverage-corpus-1','coverage corpus schema');k.digest(spec['index_sha256'])
    m.require(spec['index_sha256']==m.sha(parent['manifest.json']),'corpus index anchor mismatch')
    k.obj(spec['annotation'],'author note independence_verified accepted_as_gold')
    k.text(spec['annotation']['author']);k.text(spec['annotation']['note'])
    m.require(spec['annotation']['independence_verified'] is False and spec['annotation']['accepted_as_gold'] is False,'no independent/gold promotion')
    variants=[]
    for v in k.rows(spec['variants'],4,1):
        k.obj(v,'id description');k.ident(v['id']);k.text(v['description'])
        m.require(v['id'] not in variants,'duplicate variant');variants.append(v['id'])
    ids=set();nodes={n['id'] for n in outline['nodes']};text=k.utf8(parent['source.md'])
    for case in k.rows(spec['cases'],16,1):
        k.obj(case,'id question required selections');k.ident(case['id']);k.text(case['question'])
        m.require(case['id'] not in ids,'duplicate case');ids.add(case['id']);ref_ids=set();spans=set()
        for r in k.rows(case['required'],16,1):
            k.obj(r,'id role start end quote');k.ident(r['id']);k.text(r['quote'])
            m.require(r['id'] not in ref_ids,'duplicate requirement');ref_ids.add(r['id'])
            m.require(r['role'] in ('answer','premise','limit'),'requirement role')
            start,end=r['start'],r['end'];m.require(type(start) is int and type(end) is int and 0<=start<end<=len(text),'requirement offsets')
            m.require(text[start:end]==r['quote'],'requirement quote mismatch')
            m.require((start,end) not in spans,'duplicate requirement span');spans.add((start,end))
        m.require(type(case['selections']) is dict and set(case['selections'])==set(variants),'complete variant coverage')
        for s in case['selections'].values():
            k.obj(s,'node_ids max_context_bytes');ns=k.rows(s['node_ids'],16,1)
            m.require(all(type(n) is str and n in nodes for n in ns) and len(set(ns))==len(ns),'known unique nodes')
            m.require(type(s['max_context_bytes']) is int and 1<=s['max_context_bytes']<=k.MAX_FILE,'context budget')
    return spec


def derive(raw,outline,parent):
    spec=validate(raw,outline,parent);files={**{'index/'+n:b for n,b in parent.items()},'corpus.json':raw};rows=[]
    for case in spec['cases']:
        for variant in spec['variants']:
            vid=variant['id'];selection=dict(schema='geek-work-document-selection-1',index_sha256=spec['index_sha256'],**case['selections'][vid])
            row=dict(case_id=case['id'],variant_id=vid,required_count=len(case['required']),max_context_bytes=selection['max_context_bytes'])
            try:
                native_report,native=index.selected_files(outline,parent,selection)
            except ValueError as error:
                if str(error)!='context byte budget exceeded; no truncation':raise
                rows.append(dict(**row,status='budget_rejected',context_bytes=None,requirements=None,covered_count=None,all_required_covered=None));continue
            context=knowledge.strict_json(native['context.json'])
            # Count every source-addressed text interval actually exposed in the payload,
            # including ancestor headings. Parent prose is not reconstructed from headings.
            visible=union([(r['start'],r['end']) for r in context['fragments']]+[(h['start'],h['heading_end']) for h in context['ancestor_headings']])
            checks=[coverage(r,visible) for r in case['required']];covered=sum(r['status']=='covered' for r in checks)
            rows.append(dict(**row,status='measured',context_bytes=native_report['context_bytes'],context_sha256=native_report['context_sha256'],
                visible_source_ranges=visible,visible_source_codepoints=sum(b-a for a,b in visible),
                requirements=checks,covered_count=covered,all_required_covered=covered==len(checks)))
            for name in ('selection.json','context.json','report.json'):files[f'selections/{case["id"]}/{vid}/{name}']=native[name]
    summaries=[]
    for variant in spec['variants']:
        selected=[r for r in rows if r['variant_id']==variant['id']];completed=[r for r in selected if r['status']=='measured']
        summaries.append(dict(variant_id=variant['id'],cases=len(selected),completed=len(completed),budget_rejected=len(selected)-len(completed),
            cases_with_all_required_spans=sum(r['all_required_covered'] for r in completed),
            required_span_count_on_completed=sum(r['required_count'] for r in completed),
            covered_span_count_on_completed=sum(r['covered_count'] for r in completed),
            serialized_context_bytes_on_completed=sum(r['context_bytes'] for r in completed) if completed else None))
    report=dict(schema='geek-work-context-coverage-report-1',status='coverage_measured_review_required',annotation=spec['annotation'],rows=rows,summary=summaries,
        coverage_definition='Union of source-addressed fragments and ancestor headings covers each complete annotated interval. No string search across other occurrences or semantic equivalence.',
        denominator_scope='Completed selections only; budget refusals are counted separately, never assigned zero coverage or silently removed.',
        semantic_completeness_verified=False,answer_quality_evaluated=False,automatic_retrieval_evaluated=False,
        annotation_completeness_verified=False,independence_verified=False,accepted_as_gold=False,
        token_usage=None,monetary_cost=None,model_called_here=False,scientific_verification=False,publication_authorized=False)
    files['report.json']=m.encoded(report)
    m.require(all(len(b)<=k.MAX_FILE for b in files.values()) and sum(map(len,files.values()))<=MAX_TOTAL,'coverage archive bounds')
    return files,report


def manifest(files):return m.encoded(dict(schema=SCHEMA,files={n:m.sha(b) for n,b in files.items()}))


def build(bundle,anchor,corpus,corpus_sha,output):
    ops.outside(output,bundle,corpus);k.digest(corpus_sha)
    raw=m.read(corpus,k.MAX_FILE);m.require(m.sha(raw)==corpus_sha,'corpus anchor mismatch')
    outline,parent=index.verified(bundle,anchor);files,report=derive(raw,outline,parent);meta=manifest(files)
    archive.write_tree(output,{**files,'manifest.json':meta})
    return dict(status=report['status'],manifest_sha256=m.sha(meta),summary=report['summary'])


def verify(bundle,anchor):
    k.digest(anchor);meta=m.read(bundle/'manifest.json',k.MAX_FILE);m.require(m.sha(meta)==anchor,'coverage anchor mismatch')
    raw=k.read_source(bundle,'corpus.json');spec=knowledge.strict_json(raw)
    k.obj(spec,'schema index_sha256 annotation variants cases')
    outline,parent=index.verified(bundle/'index',spec['index_sha256']);files,report=derive(raw,outline,parent)
    m.require(meta==manifest(files),'coverage manifest reproduction mismatch');archive.exact_tree(bundle,set(files)|{'manifest.json'})
    for name,data in files.items():m.require(k.read_source(bundle,name)==data,'coverage artifact reproduction mismatch')
    return dict(status=report['status'],integrity_reproduced=True,manifest_sha256=anchor,summary=report['summary'])


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    for action in ('build','verify'):
        q=sub.add_parser(action);q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True)
        if action=='build':
            q.add_argument('--corpus',type=Path,required=True);q.add_argument('--corpus-sha256',required=True);q.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        r=build(a.bundle,a.sha256,a.corpus,a.corpus_sha256,a.output) if a.action=='build' else verify(a.bundle,a.sha256)
        print(m.encoded(r).decode(),end='');return 0
    except (ValueError,OSError,TypeError,KeyError,RecursionError) as exc:
        print(m.encoded(dict(status='rejected',reason=str(exc))).decode(),end='');return 2


if __name__=='__main__':raise SystemExit(main())
