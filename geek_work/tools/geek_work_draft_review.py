#!/usr/bin/env python3
"""Offline intake of provisional document reviews; never creates gold labels."""
import argparse
from pathlib import Path
import re
import knowledge as k


def assess(packet_raw,review,anchor):
    k.require(type(anchor) is str and re.fullmatch('[0-9a-f]{64}',anchor),'packet_anchor_format')
    k.require(k.digest(packet_raw)==anchor,'packet_anchor')
    packet=k.strict_json(packet_raw)
    k.require(packet['schema']=='geek-work-review-draft-1' and packet['state']=='awaiting_independent_annotation','packet_schema')
    response_schema=packet.get('response_schema','geek-work-review-draft-response-1')
    k.require(response_schema in ('geek-work-review-draft-response-1','geek-work-review-draft-response-2'),'packet_response_schema')
    v2=response_schema.endswith('-2')
    taxonomy=packet.get('failure_taxonomy')
    if v2:
        k.require(type(taxonomy) is dict and 1<=len(taxonomy)<=16,'failure_taxonomy')
        k.require(all(type(code) is str and 0<len(code)<=128 and type(description) is str and 0<len(description)<=2048 for code,description in taxonomy.items()),'failure_taxonomy')
    k.require(type(packet['sources']) is list and 1<=len(packet['sources'])<=16,'source_limit')
    sources={}
    for row in packet['sources']:
        k.require(type(row['id']) is str and row['id'] not in sources,'source_id')
        k.require(type(row['text']) is str and k.digest(row['text'].encode())==row['sha256'],'source_hash')
        sources[row['id']]=row['text']
    k.require(type(packet['cases']) is list and 1<=len(packet['cases'])<=32,'case_limit')
    cases={}
    for row in packet['cases']:
        k.require(type(row['id']) is str and row['id'] not in cases and row['source_id'] in sources,'packet_case')
        k.require(type(row['candidate']) is str and bool(row['candidate'].strip()),'candidate')
        cases[row['id']]=row
    k.obj(review,{'schema','packet_file_sha256','reviewer','decisions','accepted_as_gold'})
    k.require(review['schema']==response_schema and review['packet_file_sha256']==anchor,'review_packet')
    k.require(review['accepted_as_gold'] is False,'gold_claim')
    who=review['reviewer'];k.obj(who,{'id','kind','prior_exposure','relationship_to_author'})
    issues=[]
    for key in ('id','prior_exposure','relationship_to_author'):
        value=who[key];k.require(value is None or type(value) is str and len(value)<=2048,'reviewer_field')
        if not value or not value.strip():issues.append('reviewer_'+key+'_missing')
    k.require(who['kind'] in (None,'human','model'),'reviewer_kind')
    if who['kind'] is None:issues.append('reviewer_kind_missing')
    rows=review['decisions'];k.require(type(rows) is list and len(rows)<=len(cases),'decision_limit')
    seen=set();results=[]
    for row in rows:
        required={'case_id','supported','failure_classes','rationale','citations'}
        if v2:required.add('relation_to_source')
        k.obj(row,required)
        cid=row['case_id'];k.require(type(cid) is str and cid in cases and cid not in seen,'decision_id');seen.add(cid)
        label=row['supported'];k.require(label is None or type(label) is bool,'label_type')
        reason=row['rationale'];k.require(reason is None or type(reason) is str and len(reason)<=4096,'rationale')
        classes=row['failure_classes'];k.require(classes is None or type(classes) is list and len(classes)<=16 and all(type(x) is str and 0<len(x)<=128 for x in classes) and len(set(classes))==len(classes),'failure_classes')
        if v2:
            k.require(classes is None or all(code in taxonomy for code in classes),'unknown_failure_class')
            relation=row['relation_to_source']
            k.require(relation in (None,'entails','contradicts','not_established','ambiguous','insufficient_information'),'relation_to_source')
        cites=row['citations'];k.require(type(cites) is list and len(cites)<=8,'citation_limit')
        for cite in cites:
            k.obj(cite,{'source_id','start','end','quote'})
            k.require(cite['source_id']==cases[cid]['source_id'],'citation_source')
            text=sources[cite['source_id']];a=cite['start'];b=cite['end']
            k.require(type(a) is int and type(b) is int and 0<=a<b<=len(text),'citation_span')
            k.require(type(cite['quote']) is str and text[a:b]==cite['quote'],'citation_text')
        missing=[]
        if v2:
            allowed={True:('entails',),False:('contradicts','not_established'),None:('ambiguous','insufficient_information')}
            if relation is None:missing.append('relation_missing')
            elif relation not in allowed[label]:missing.append('label_relation_conflict')
        if label is None:missing.append('abstained')
        if not reason or not reason.strip():missing.append('rationale_missing')
        if not cites:missing.append('citations_missing')
        if classes is None:missing.append('failure_classes_missing')
        if label is True and classes:missing.append('supported_with_failures')
        if label is False and classes==[]:missing.append('unsupported_without_class')
        results.append(dict(case_id=cid,issues=missing))
    missing_ids=sorted(set(cases)-seen)
    complete=not issues and not missing_ids and all(not r['issues'] for r in results)
    return dict(schema='geek-work-review-draft-check-1',status='structurally_complete' if complete else 'needs_review',
                packet_file_sha256=anchor,review_sha256=k.digest(k.canonical(review)),
                tool_sha256=k.digest(Path(__file__).read_bytes()),knowledge_tool_sha256=k.digest(Path(k.__file__).read_bytes()),
                reviewer_issues=issues,missing_case_ids=missing_ids,cases=results,
                independence_verified=False,semantic_correctness_verified=False,accepted_as_gold=False,
                model_calls=0,limits='Exact embedded text and structural checks only; no Git origin attestation or semantic review. No benchmark or graph promotion.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--packet',type=Path,required=True);p.add_argument('--review',type=Path,required=True)
    p.add_argument('--expected-packet-sha256',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        result=assess(k.bounded(a.packet),k.load(a.review),a.expected_packet_sha256)
        k.write_new(a.output,k.canonical(result)+b'\n');print(k.canonical(result).decode())
        return 0 if result['status']=='structurally_complete' else 2
    except (k.Refusal,OSError,ValueError,TypeError,KeyError) as err:
        print(k.canonical(dict(status='refused',reason=str(err))).decode());return 1


if __name__=='__main__':raise SystemExit(main())
