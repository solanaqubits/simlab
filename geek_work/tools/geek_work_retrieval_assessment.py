#!/usr/bin/env python3
"""Assess frozen literal retrieval against provisional annotations, retaining misses."""
import argparse
from pathlib import Path

import geek_work_retrieval_review as review
import geek_work_local_retrieval as search
import geek_work_context_coverage as coverage
import geek_work_document_index as index
import geek_work_manuscript as m
import geek_work_manuscript_claims as k
import geek_work_batch_hunks as archive
import geek_work_file_operations as ops
import knowledge

SCHEMA='geek-work-retrieval-assessment-archive-1'
MAX_TOTAL=32*1024*1024


def validate(raw):
    spec=knowledge.strict_json(raw)
    m.require(type(spec) is dict,'assessment plan object')
    version=spec.get('schema');m.require(version in ('geek-work-retrieval-assessment-plan-1','geek-work-retrieval-assessment-plan-2'),'assessment plan schema')
    k.obj(spec,'schema review_sha256 retriever_source_sha256 policy top_k max_context_bytes'+(' query_transforms_sha256' if version.endswith('-2') else ''))
    if version.endswith('-2'):k.digest(spec['query_transforms_sha256'])
    k.digest(spec['review_sha256']);k.digest(spec['retriever_source_sha256'])
    m.require(spec['retriever_source_sha256']==m.sha(m.read(Path(search.__file__),k.MAX_FILE)),'frozen retriever source mismatch')
    m.require(spec['policy']==search.POLICY,'assessment policy')
    m.require(type(spec['top_k']) is int and 1<=spec['top_k']<=16,'assessment top_k')
    m.require(type(spec['max_context_bytes']) is int and 1<=spec['max_context_bytes']<=k.MAX_FILE,'assessment byte budget')
    return spec


def validate_transforms(raw,spec,response):
    m.require(raw is not None,'query transformations required for plan v2')
    m.require(m.sha(raw)==spec['query_transforms_sha256'],'query transformations anchor mismatch')
    data=knowledge.strict_json(raw)
    k.obj(data,'schema review_sha256 method source_language target_language translator semantic_equivalence_verified independence_verified cases')
    m.require(data['schema']=='geek-work-query-transforms-1' and data['method']=='supplied_translation','query transformation schema/method')
    k.digest(data['review_sha256']);m.require(data['review_sha256']==spec['review_sha256'],'transformation review mismatch')
    for name in ('source_language','target_language'):k.ident(data[name])
    k.obj(data['translator'],'id model_profile prior_exposure')
    k.text(data['translator']['id']);k.text(data['translator']['prior_exposure'])
    if data['translator']['model_profile'] is not None:k.text(data['translator']['model_profile'])
    m.require(data['semantic_equivalence_verified'] is False and data['independence_verified'] is False,'no translation equivalence/independence promotion')
    cases={c['id']:c for c in response['cases']};seen=set()
    for row in k.rows(data['cases'],16,1):
        k.obj(row,'id original_question original_sha256 derived_query derived_sha256 rationale')
        k.ident(row['id']);m.require(row['id'] in cases and row['id'] not in seen,'unique known transformation case');seen.add(row['id'])
        for name in ('original_question','derived_query','rationale'):k.text(row[name])
        m.require(row['original_question']==cases[row['id']]['question'],'original question mismatch')
        for name,field in [('original_sha256','original_question'),('derived_sha256','derived_query')]:
            k.digest(row[name]);m.require(row[name]==m.sha(row[field].encode()),'query text hash mismatch')
    m.require(seen==set(cases),'complete query transformation coverage')
    return data


def collect(bundle,anchor):
    review.verify_review(bundle,anchor)
    meta=knowledge.strict_json(m.read(bundle/'manifest.json',k.MAX_FILE))
    names=set(meta['files'])|{'manifest.json'};m.require(len(names)<=32,'review file count')
    saved={name:k.read_source(bundle,name) for name in sorted(names)}
    packet=knowledge.strict_json(saved['packet/packet.json'])
    outline,parent=index.verified(bundle/'packet/index',packet['index_sha256'])
    return knowledge.strict_json(saved['response.json']),outline,parent,saved


def measured(case,variant,status,context_raw):
    context=knowledge.strict_json(context_raw) if context_raw is not None else None
    visible=[] if context is None else coverage.union([(f['start'],f['end']) for f in context['fragments']]+[(h['start'],h['heading_end']) for h in context['ancestor_headings']])
    eligible=case['answerability']=='answerable'
    checks=[coverage.coverage(ref,visible) for ref in case['required']] if eligible else None
    return dict(case_id=case['id'],variant_id=variant,reported_answerability=case['answerability'],
        coverage_eligible=eligible,retrieval_status=status,context_obtained=context is not None,
        context_bytes=len(context_raw) if context_raw is not None else None,context_sha256=m.sha(context_raw) if context_raw is not None else None,
        visible_source_ranges=visible,required_count=len(checks) if eligible else None,requirements=checks,
        covered_count=sum(c['status']=='covered' for c in checks) if eligible else None,
        all_required_covered=all(c['status']=='covered' for c in checks) if eligible else None)


def summarize(rows,variant):
    rows=[r for r in rows if r['variant_id']==variant];eligible=[r for r in rows if r['coverage_eligible']]
    contexts=[r for r in rows if r['context_obtained']];eligible_contexts=[r for r in eligible if r['context_obtained']]
    states={}
    for r in rows:states[r['retrieval_status']]=states.get(r['retrieval_status'],0)+1
    result=dict(variant_id=variant,total_cases=len(rows),retrieval_status_counts=states,contexts_produced=len(contexts),
        eligible_cases=len(eligible),eligible_cases_with_context=len(eligible_contexts),eligible_cases_without_context=len(eligible)-len(eligible_contexts),
        required_span_count=sum(r['required_count'] for r in eligible),covered_span_count=sum(r['covered_count'] for r in eligible),
        cases_with_all_required_spans=sum(r['all_required_covered'] for r in eligible),
        context_bytes_on_produced=sum(r['context_bytes'] for r in contexts) if contexts else None,
        eligible_context_bytes_on_produced=sum(r['context_bytes'] for r in eligible_contexts) if eligible_contexts else None)
    for state in ('not_answerable','uncertain'):
        subset=[r for r in rows if r['reported_answerability']==state]
        result['reported_'+state]=dict(cases=len(subset),with_context=sum(r['context_obtained'] for r in subset),without_context=sum(not r['context_obtained'] for r in subset))
    return result


def derive(raw,bundle,transform_raw=None):
    spec=validate(raw);response,outline,parent,saved=collect(bundle,spec['review_sha256'])
    transformed=spec['schema']=='geek-work-retrieval-assessment-plan-2'
    if transformed:transforms=validate_transforms(transform_raw,spec,response)
    else:m.require(transform_raw is None,'query transformations not allowed for plan v1');transforms=None
    queries={r['id']:r['derived_query'] for r in transforms['cases']} if transforms else {}
    files={'plan.json':raw,**{'review/'+n:b for n,b in saved.items()}};rows=[]
    if transformed:files['query-transforms.json']=transform_raw
    baseline=dict(schema='geek-work-document-selection-1',index_sha256=m.sha(parent['manifest.json']),node_ids=['document'],max_context_bytes=spec['max_context_bytes'])
    files['baseline/request.json']=m.encoded(baseline);full=None;full_status='context_selected'
    try:
        _,full=index.selected_files(outline,parent,baseline)
    except ValueError as error:
        if str(error)!='context byte budget exceeded; no truncation':raise
        full_status='budget_rejected'
    if full:
        for name in ('selection.json','context.json','report.json'):files['baseline/'+name]=full[name]
    for case in response['cases']:
        # Only the exact question and fixed settings enter retrieval, never labels/spans.
        query=dict(schema='geek-work-local-retrieval-query-1',index_sha256=baseline['index_sha256'],query=case['question'],
                   policy=spec['policy'],top_k=spec['top_k'],max_context_bytes=spec['max_context_bytes'])
        selected,report=search.derive(m.encoded(query),outline,parent)
        for name in ('query.json','report.json','selection/selection.json','selection/context.json','selection/report.json'):
            if name in selected:files[f'searches/{case["id"]}/{name}']=selected[name]
        rows.append(measured(case,'lexical',report['status'],selected.get('selection/context.json')))
        if transformed:
            transformed_query={**query,'query':queries[case['id']]}
            derived,derived_report=search.derive(m.encoded(transformed_query),outline,parent)
            for name in ('query.json','report.json','selection/selection.json','selection/context.json','selection/report.json'):
                if name in derived:files[f'transformed-searches/{case["id"]}/{name}']=derived[name]
            rows.append(measured(case,'transformed',derived_report['status'],derived.get('selection/context.json')))
        rows.append(measured(case,'full',full_status,full['context.json'] if full else None))
    report=dict(schema='geek-work-retrieval-assessment-report-1',status='retrieval_measured_review_required',
        source_sha256=outline['source_sha256'],review_sha256=spec['review_sha256'],reviewer=response['reviewer'],
        rows=rows,summary=[summarize(rows,v) for v in (('lexical','transformed','full') if transformed else ('lexical','full'))],
        coverage_definition='Exact annotated intervals covered by union of native context fragments and visible ancestor headings.',
        denominator_scope='All reported-answerable cases including no-context/budget failures; no context contributes zero covered spans and null bytes. Other reported states retain null coverage and separate counts.',
        payload_scope='Serialized native context JSON only, not question/prompt, verification archive, tokens or monetary cost.',
        independence_verified=False,held_out_verified=False,accepted_as_gold=False,annotation_sufficiency_verified=False,
        answerability_verified=False,answer_quality_evaluated=False,semantic_abstention_evaluated=False,
        model_called_here=False,token_usage=None,monetary_cost=None,scientific_verification=False,publication_authorized=False,
        limits='Literal retrieval, no translation or synonym expansion. A match is not an answer; no match is not semantic abstention. Reviewer judgments/exposure are reported. Frozen source hash does not pin the full runtime or prove preregistration.')
    if transformed:
        report.update(schema='geek-work-retrieval-assessment-report-2',query_transforms_sha256=spec['query_transforms_sha256'],
            transformation_provenance={name:transforms[name] for name in ('method','source_language','target_language','translator')},
            semantic_equivalence_verified=False,translator_identity_verified=False,language_labels_verified=False,
            limits='Literal retrieval on original and separately supplied translated questions, identical policy/budget. Translation identity, language and fidelity are reported, not verified; semantic drift remains possible. No automatic translation/provider call. A match is not an answer and no match is not semantic abstention. Frozen retriever source does not pin the full runtime or prove preregistration.')
    files['report.json']=m.encoded(report)
    m.require(all(len(b)<=k.MAX_FILE for b in files.values()) and sum(map(len,files.values()))<=MAX_TOTAL,'assessment archive bounds')
    return files,report


def manifest(files):
    version=knowledge.strict_json(files['plan.json'])['schema']
    schema='geek-work-retrieval-assessment-archive-2' if version=='geek-work-retrieval-assessment-plan-2' else SCHEMA
    return m.encoded(dict(schema=schema,files={n:m.sha(b) for n,b in files.items()}))


def build(bundle,anchor,plan,plan_sha,output,query_transforms=None):
    ops.outside(output,bundle,plan);k.digest(anchor);k.digest(plan_sha);raw=m.read(plan,k.MAX_FILE)
    m.require(m.sha(raw)==plan_sha,'assessment plan anchor mismatch');spec=validate(raw)
    m.require(spec['review_sha256']==anchor,'assessment review anchor mismatch')
    if query_transforms is not None:ops.outside(output,query_transforms)
    transform_raw=m.read(query_transforms,k.MAX_FILE) if query_transforms is not None else None
    files,report=derive(raw,bundle,transform_raw)
    meta=manifest(files);archive.write_tree(output,{**files,'manifest.json':meta})
    return dict(status=report['status'],manifest_sha256=m.sha(meta),summary=report['summary'])


def verify(bundle,anchor):
    k.digest(anchor);meta=m.read(bundle/'manifest.json',k.MAX_FILE);m.require(m.sha(meta)==anchor,'assessment anchor mismatch')
    raw=k.read_source(bundle,'plan.json');spec=validate(raw)
    transforms=k.read_source(bundle,'query-transforms.json') if spec['schema']=='geek-work-retrieval-assessment-plan-2' else None
    files,report=derive(raw,bundle/'review',transforms)
    m.require(meta==manifest(files),'assessment manifest reproduction mismatch');archive.exact_tree(bundle,set(files)|{'manifest.json'})
    for name,raw in files.items():m.require(k.read_source(bundle,name)==raw,'assessment artifact reproduction mismatch')
    return dict(status=report['status'],manifest_sha256=anchor,integrity_reproduced=True,summary=report['summary'])


def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    for action in ('build','verify'):
        q=s.add_parser(action);q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True)
        if action=='build':q.add_argument('--plan',type=Path,required=True);q.add_argument('--plan-sha256',required=True);q.add_argument('--output',type=Path,required=True);q.add_argument('--query-transforms',type=Path)
    a=p.parse_args()
    try:
        result=build(a.bundle,a.sha256,a.plan,a.plan_sha256,a.output,a.query_transforms) if a.action=='build' else verify(a.bundle,a.sha256)
        print(m.encoded(result).decode(),end='');return 0
    except (ValueError,OSError,TypeError,KeyError,RecursionError) as error:
        print(m.encoded(dict(status='rejected',reason=str(error))).decode(),end='');return 2


if __name__=='__main__':raise SystemExit(main())
