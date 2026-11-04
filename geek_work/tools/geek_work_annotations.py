#!/usr/bin/env python3
"""Check declared review metadata and exact citations; prepare a sealed corpus, not verified knowledge."""
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import sys

import geek_work_memory as memory
import geek_work_structured as structured
import knowledge as k

FILES={'packet.json','review.json','policy.json','assessment.json','corpus.json'}
LIMITS=dict(output_tokens=512,total_tokens_per_call=8000,wall_ms_per_call=45000,estimated_usd_per_call='0.10')


def pins():
    return {Path(m.__file__).name:k.digest(Path(m.__file__).read_bytes()) for m in
            (sys.modules[__name__],k,memory,structured)}


def packet_cases(packet):
    k.obj(packet,{'schema','state','author_id','graph_sha256','graph_source_commit','graph_path','cases'})
    k.require(packet['schema']=='geek-work-memory-annotation-packet-1' and
              packet['state']=='awaiting_independent_review','invalid_input:packet_schema')
    k.require(type(packet['author_id']) is str and packet['author_id'].strip(),'invalid_input:author')
    memory.sha(packet['graph_sha256'])
    k.require(type(packet['graph_source_commit']) is str and re.fullmatch('[0-9a-f]{40}',packet['graph_source_commit']),
              'invalid_input:source_commit')
    k.require(type(packet['graph_path']) is str and packet['graph_path'],'invalid_input:graph_path')
    path=PurePosixPath(packet['graph_path'])
    k.require(not path.is_absolute() and '..' not in path.parts,'invalid_input:graph_path')
    k.require(type(packet['cases']) is list and 0<len(packet['cases'])<=16,'resource_limit:cases')
    cases={}
    for row in packet['cases']:
        k.obj(row,{'id','split','card_id','revision','candidate'})
        k.require(type(row['id']) is str and row['id'] and row['id'] not in cases,'invalid_input:case_id')
        k.require(type(row['split']) is str and row['split'] in ('calibration','holdout'),'invalid_input:split')
        k.require(type(row['card_id']) is str and row['card_id'] and
                  type(row['revision']) is int and row['revision']>0 and
                  type(row['candidate']) is str and row['candidate'].strip(),'invalid_input:case')
        cases[row['id']]=row
    return cases


def template(packet):
    cases=packet_cases(packet)
    return dict(schema='geek-work-memory-annotation-review-2',packet_sha256=k.digest(k.canonical(packet)),
                reviewer=dict(id=None,kind=None,expected_profile=None,observed_profile=None,independence_note=None),
                decisions=[dict(case_id=cid,expected_with_memory=None,rationale=None,citations=[]) for cid in cases])


def assess(packet,review,graph,root,policy=None):
    cases=packet_cases(packet);k.validate(graph)
    k.require(packet['graph_sha256']==k.digest(k.canonical(graph)),'invalid_witness:graph_changed')
    k.obj(review,{'schema','packet_sha256','reviewer','decisions'})
    k.require(review['schema']=='geek-work-memory-annotation-review-2','invalid_input:review_schema')
    k.require(review['packet_sha256']==k.digest(k.canonical(packet)),'invalid_witness:packet_changed')
    who=review['reviewer'];k.obj(who,{'id','kind','expected_profile','observed_profile','independence_note'})
    for name in ('id','independence_note'):
        k.require(who[name] is None or type(who[name]) is str,'invalid_input:reviewer_text')
    k.require(who['kind'] is None or (type(who['kind']) is str and who['kind'] in ('human','model')),
              'invalid_input:reviewer_kind')
    for name in ('expected_profile','observed_profile'):
        if who[name] is not None:memory.profile_id(who[name])
    if policy is not None:memory.validate_policy(policy)
    issues=[];gate=None
    if not who['id'] or not who['id'].strip():issues.append('reviewer_missing')
    elif who['id'].strip().casefold()==packet['author_id'].strip().casefold():issues.append('reviewer_is_author')
    if not who['independence_note'] or not who['independence_note'].strip():issues.append('independence_note_missing')
    if who['kind'] is None:issues.append('reviewer_kind_missing')
    elif who['kind']=='human':
        k.require(who['expected_profile'] is None and who['observed_profile'] is None,
                  'invalid_input:human_with_model_profile')
    else:
        if policy is None:issues.append('model_policy_missing')
        else:
            gate=memory.qualify(policy,dict(schema='geek-work-review-attempt-1',policy_sha256=k.digest(k.canonical(policy)),
                task_class='corpus_annotation',kind='model_review',expected_profile=who['expected_profile'],
                observed_profile=who['observed_profile'],artifact_sha256=k.digest(k.canonical(review)),verifier_receipt=None),root)
            if gate['disposition']!='eligible_for_review':issues.extend(gate['issues'])
    k.require(type(review['decisions']) is list and len(review['decisions'])<=16,'resource_limit:decisions')
    decisions={}
    for d in review['decisions']:
        k.obj(d,{'case_id','expected_with_memory','rationale','citations'})
        cid=d['case_id'];k.require(type(cid) is str and cid in cases and cid not in decisions,'invalid_input:decision_id')
        k.require(d['expected_with_memory'] is None or type(d['expected_with_memory']) is bool,'invalid_input:label')
        k.require(d['rationale'] is None or type(d['rationale']) is str,'invalid_input:rationale')
        k.require(type(d['citations']) is list and len(d['citations'])<=6,'invalid_input:citations')
        decisions[cid]=d
    rows=[]
    for cid,row in cases.items():
        context=memory.retrieve(graph,root,dict(schema='geek-work-memory-request-1',
            expected_graph_sha256=packet['graph_sha256'],cards=[dict(id=row['card_id'],revision=row['revision'])]))
        pending=[];d=decisions.get(cid)
        if context['disposition']!='context_ready':pending.extend(context['issues'])
        if d is None:pending.append('decision_missing')
        else:
            if d['expected_with_memory'] is None:pending.append('label_missing')
            if not d['rationale'] or not d['rationale'].strip():pending.append('rationale_missing')
            if not d['citations']:pending.append('citation_missing')
            else:
                # This constant is a shape-check label only, never a substituted reviewer rationale.
                response=dict(accept=False,failure_classes=['missing_premise'],reason='Citation validation only',evidence=d['citations'])
                errors=structured.check_request(dict(structured_response=response),dict(input=dict(source=dict(memory=context))))
                k.require(not errors,'invalid_witness:citations:'+cid)
        rows.append(dict(case_id=cid,issues=sorted(set(pending)),context_sha256=k.digest(k.canonical(context))))
    ready=not issues and all(not row['issues'] for row in rows)
    return dict(schema='geek-work-annotation-assessment-1',status='ready_for_sealing' if ready else 'needs_review',
        packet_sha256=k.digest(k.canonical(packet)),review_sha256=k.digest(k.canonical(review)),
        reviewer_issues=sorted(set(issues)),cases=rows,model_gate=gate,
        independence_verified=False,semantic_correctness_verified=False,accepted_into_knowledge_graph=False)


def build_corpus(packet,review):
    decisions={d['case_id']:d for d in review['decisions']}
    return dict(schema='geek-work-memory-corpus-1',graph_sha256=packet['graph_sha256'],limits=LIMITS.copy(),
                cases=[dict(**row,expected_with_memory=decisions[row['id']]['expected_with_memory'],
                            rationale=decisions[row['id']]['rationale']) for row in packet['cases']])


def seal(packet,review,graph,root,output,policy=None):
    assessment=assess(packet,review,graph,root,policy)
    k.require(assessment['status']=='ready_for_sealing','invalid_witness:review_incomplete')
    contents={'packet.json':packet,'review.json':review,'policy.json':policy,
              'assessment.json':assessment,'corpus.json':build_corpus(packet,review)}
    encoded={name:k.canonical(value)+b'\n' for name,value in contents.items()}
    k.require(sum(map(len,encoded.values()))<=k.MAX_BYTES,'resource_limit:bundle')
    output.mkdir(parents=True,exist_ok=False)
    for name,raw in encoded.items():k.write_new(output/name,raw)
    marker=dict(schema='geek-work-annotation-seal-1',files={name:k.digest(raw) for name,raw in encoded.items()},
                tool_pins=pins(),independence_verified=False,accepted_into_knowledge_graph=False)
    # Last-file completion marker; partial directories are retained but are not sealed bundles.
    k.write_new(output/'seal.json',k.canonical(marker)+b'\n')
    return marker


def verify(output,graph,root):
    k.require(not output.is_symlink(),'invalid_input:bundle_symlink')
    k.require({p.name for p in output.iterdir()}==FILES|{'seal.json'},'invalid_input:bundle_file_set')
    marker=k.load(output/'seal.json')
    k.obj(marker,{'schema','files','tool_pins','independence_verified','accepted_into_knowledge_graph'})
    k.require(marker['schema']=='geek-work-annotation-seal-1' and marker['tool_pins']==pins(),'invalid_witness:seal_tools')
    k.require(marker['independence_verified'] is False and marker['accepted_into_knowledge_graph'] is False,
              'invalid_input:seal_claims')
    k.require(type(marker['files']) is dict and set(marker['files'])==FILES,'invalid_input:sealed_files')
    values={};total=0
    for name,sha in marker['files'].items():
        memory.sha(sha);raw=k.bounded(output/name);total+=len(raw)
        k.require(total<=k.MAX_BYTES,'resource_limit:bundle')
        k.require(k.digest(raw)==sha,'invalid_witness:sealed_hash:'+name);values[name]=k.strict_json(raw)
    assessment=assess(values['packet.json'],values['review.json'],graph,root,values['policy.json'])
    k.require(assessment['status']=='ready_for_sealing' and assessment==values['assessment.json'],
              'invalid_witness:assessment_changed')
    k.require(build_corpus(values['packet.json'],values['review.json'])==values['corpus.json'],
              'invalid_witness:corpus_changed')
    return dict(schema='geek-work-annotation-bundle-check-1',status='verified_structure',
                cases=len(assessment['cases']),independence_verified=False,semantic_correctness_verified=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);subs=parser.add_subparsers(dest='command',required=True)
    t=subs.add_parser('template');t.add_argument('packet',type=Path);t.add_argument('--output',type=Path,required=True)
    for name in ('check','seal'):
        p=subs.add_parser(name);p.add_argument('packet',type=Path);p.add_argument('review',type=Path)
        p.add_argument('--graph',type=Path,required=True);p.add_argument('--root',type=Path,required=True)
        p.add_argument('--policy',type=Path);p.add_argument('--output',type=Path,required=True)
    v=subs.add_parser('verify');v.add_argument('bundle',type=Path);v.add_argument('--graph',type=Path,required=True)
    v.add_argument('--root',type=Path,required=True);v.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.command=='template':result=template(k.load(args.packet))
        elif args.command=='verify':result=verify(args.bundle,k.load(args.graph),args.root)
        else:
            packet=k.load(args.packet);review=k.load(args.review);graph=k.load(args.graph)
            policy=k.load(args.policy) if args.policy else None
            if args.command=='seal':seal(packet,review,graph,args.root,args.output,policy);return 0
            result=assess(packet,review,graph,args.root,policy)
        k.write_new(args.output,k.canonical(result)+b'\n')
        return 2 if result.get('status')=='needs_review' else 0
    except (k.Refusal,OSError,UnicodeError,ValueError) as exc:
        print(json.dumps(dict(status='rejected',reason=str(exc))),file=sys.stderr);return 2


if __name__=='__main__':sys.exit(main())
