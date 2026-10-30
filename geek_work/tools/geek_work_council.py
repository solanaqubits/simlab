#!/usr/bin/env python3
"""Compare bounded offline reviews; agreement is never a correctness verdict."""
import argparse
import base64
from pathlib import Path
import geek_work_draft_review as review
import knowledge as k

MAX_TOTAL_BYTES=2*1024*1024


def compare(packet_raw,raw_reviews,packet_anchor):
    k.require(type(raw_reviews) is list and 2<=len(raw_reviews)<=4,'participant_limit')
    k.require(len(packet_raw)+sum(len(x) for x in raw_reviews)<=MAX_TOTAL_BYTES,'council_byte_limit')
    # Validate the packet independently of whether any participant supplied valid JSON.
    packet=k.strict_json(packet_raw)
    empty=dict(schema=packet.get('response_schema','geek-work-review-draft-response-1'),packet_file_sha256=packet_anchor,
               reviewer=dict(id=None,kind=None,prior_exposure=None,relationship_to_author=None),
               decisions=[],accepted_as_gold=False)
    review.assess(packet_raw,empty,packet_anchor)
    hashes=[k.digest(x) for x in raw_reviews]
    k.require(len(set(hashes))==len(hashes),'duplicate_response_bytes')
    participants=[];identities=set()
    for index,raw in enumerate(raw_reviews,1):
        row=dict(participant='P'+str(index),raw_sha256=k.digest(raw),raw_base64=base64.b64encode(raw).decode(),
                 token_usage=None,monetary_cost=None)
        try:
            value=k.strict_json(raw);assessment=review.assess(packet_raw,value,packet_anchor)
        except (ValueError,TypeError,KeyError) as err:
            row.update(status='invalid_response',reason=str(err),assessment=None,review=None)
        else:
            identity=value['reviewer']['id']
            if identity and identity.strip():
                k.require(identity not in identities,'duplicate_declared_reviewer');identities.add(identity)
            row.update(status=assessment['status'],assessment=assessment,review=value)
        participants.append(row)
    cases=[]
    for case in packet['cases']:
        observations=[];labels=[];relations=[];mechanisms=[]
        for row in participants:
            entry=dict(participant=row['participant'],state='invalid_response',supported=None)
            if row['assessment'] is not None:
                assessment=row['assessment'];value=row['review']
                decision=next((x for x in value['decisions'] if x['case_id']==case['id']),None)
                if decision is None:entry['state']='missing'
                else:
                    issues=next(x['issues'] for x in assessment['cases'] if x['case_id']==case['id'])
                    entry.update(supported=decision['supported'],decision=decision,issues=issues)
                    if assessment['reviewer_issues']:entry['state']='reviewer_incomplete'
                    elif any(x!='abstained' for x in issues):entry['state']='incomplete_decision'
                    elif decision['supported'] is None:entry['state']='abstained'
                    else:
                        entry['state']='valid_decision';labels.append(decision['supported'])
                        mechanisms.append(tuple(sorted(decision['failure_classes'])))
                        if 'relation_to_source' in decision:relations.append(decision['relation_to_source'])
            observations.append(entry)
        state='insufficient_valid_reviews' if len(labels)<2 else 'agreement' if len(set(labels))==1 else 'disagreement'
        mechanism_state='insufficient_valid_reviews' if len(mechanisms)<2 else 'agreement' if len(set(mechanisms))==1 else 'disagreement'
        relation_state='not_available' if packet.get('response_schema')!='geek-work-review-draft-response-2' else 'insufficient_valid_reviews' if len(relations)<2 else 'agreement' if len(set(relations))==1 else 'disagreement'
        cases.append(dict(case_id=case['id'],state=state,valid_decisions=len(labels),
                          mechanism_state=mechanism_state,relation_state=relation_state,observations=observations))
    complete=all(p['status']=='structurally_complete' for p in participants)
    return dict(schema='geek-work-council-comparison-1',status='comparison_ready' if complete else 'needs_review',
                packet_file_sha256=packet_anchor,participants=participants,cases=cases,
                tool_pins={Path(p).name:k.digest(Path(p).read_bytes()) for p in (__file__,review.__file__,k.__file__)},
                disagreement_cases=[x['case_id'] for x in cases if x['state']=='disagreement'],
                mechanism_disagreement_cases=[x['case_id'] for x in cases if x['mechanism_state']=='disagreement'],
                relation_disagreement_cases=[x['case_id'] for x in cases if x['relation_state']=='disagreement'],
                independence_verified=False,semantic_correctness_verified=False,accepted_as_gold=False,
                model_calls=0,limits='Offline comparison of supplied artifacts only; participant labels preserve input order, not anonymity. Declared identities are not attested. No voting, arbitration, graph promotion or verified cost.')


def verify(report,anchor,packet_raw,raw_reviews,packet_anchor):
    k.require(k.digest(k.canonical(report))==anchor,'council_report_anchor')
    k.require(k.canonical(report)==k.canonical(compare(packet_raw,raw_reviews,packet_anchor)),'council_report_changed')
    return dict(status='verified_council_comparison',accepted_as_gold=False,model_calls=0)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['compare','verify']);p.add_argument('--packet',type=Path,required=True)
    p.add_argument('--review',type=Path,action='append',required=True);p.add_argument('--packet-anchor',required=True)
    p.add_argument('--output',type=Path);p.add_argument('--report',type=Path);p.add_argument('--report-anchor')
    a=p.parse_args()
    try:
        k.require(2<=len(a.review)<=4,'participant_limit')
        packet=k.bounded(a.packet);raw=[k.bounded(x) for x in a.review]
        if a.action=='compare':
            k.require(a.output is not None,'output_required');report=compare(packet,raw,a.packet_anchor)
            encoded=k.canonical(report);k.require(len(encoded)<=k.MAX_BYTES,'report_byte_limit')
            k.write_new(a.output,encoded+b'\n');result=dict(status=report['status'],report_sha256=k.digest(encoded),disagreement_cases=report['disagreement_cases'])
        else:
            k.require(a.report is not None and a.report_anchor is not None,'verify_arguments')
            result=verify(k.load(a.report),a.report_anchor,packet,raw,a.packet_anchor)
            if a.output:k.write_new(a.output,k.canonical(result)+b'\n')
        print(k.canonical(result).decode());return 0
    except (ValueError,TypeError,KeyError,OSError) as err:
        print(k.canonical(dict(status='refused',reason=str(err))).decode());return 1


if __name__=='__main__':raise SystemExit(main())
