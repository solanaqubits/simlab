#!/usr/bin/env python3
"""Record evidence-bound dispositions of EVM findings without certifying them."""
import argparse
from collections import Counter
import re
from pathlib import Path
import json

import geek_work_evm_audit as audit

STATES=('open','needs_reproduction','disputed','fix_proposed','resolved_claimed')
TOTAL_EVIDENCE_BYTES=16*1024*1024


def anchored(path, expected):
    audit.require(type(expected) is str and bool(re.fullmatch('[0-9a-f]{64}',expected)), 'full SHA-256 required')
    raw=audit.read_regular(path)
    audit.require(audit.sha(raw)==expected,'input anchor mismatch')
    return raw


def validate_decisions(packet, response, packet_sha, response_sha, decisions, evidence_dir):
    audit.fields(decisions,'schema packet_sha256 response_sha256 adjudicator decisions','decisions')
    audit.require(decisions['schema']=='geek-work-evm-decisions-1','decisions schema')
    audit.require(decisions['packet_sha256']==packet_sha and decisions['response_sha256']==response_sha,
                  'decisions refer to another packet or response')
    audit.fields(decisions['adjudicator'],'id prior_participation','adjudicator')
    for key in ('id','prior_participation'):audit.text(decisions['adjudicator'][key],key)
    rows=decisions['decisions']
    audit.require(type(rows) is list and len(rows)<=256,'decision list limit')
    findings={f['id']:f for f in response['findings']}
    seen=set();artifacts={};pins={};total=0
    audit.require(evidence_dir.is_dir() and not evidence_dir.is_symlink(),'regular evidence directory required')
    for row in rows:
        audit.fields(row,'finding_id state rationale fix_commit evidence','decision')
        ident=row['finding_id']
        audit.require(type(ident) is str and ident in findings and ident not in seen,'unknown or duplicate finding')
        seen.add(ident)
        audit.require(row['state'] in STATES,'decision state')
        audit.text(row['rationale'],'decision rationale')
        commit=row['fix_commit']
        audit.require(commit is None or (type(commit) is str and bool(re.fullmatch('[0-9a-f]{40}',commit))), 'fix commit syntax')
        refs=row['evidence']
        audit.require(type(refs) is list and len(refs)<=16,'evidence list limit')
        if row['state'] in ('disputed','fix_proposed','resolved_claimed'):
            audit.require(bool(refs),'disposition requires supporting material')
        if row['state']=='fix_proposed' or (row['state']=='resolved_claimed' and findings[ident]['kind']=='defect'):
            audit.require(commit is not None,'defect fix requires commit reference')
        used=set()
        for ref in refs:
            audit.fields(ref,'file sha256 purpose','evidence reference')
            name=ref['file'];pin=ref['sha256']
            audit.require(type(name) is str and bool(re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',name)), 'flat evidence filename required')
            audit.require(name not in used,'duplicate evidence reference');used.add(name)
            audit.text(ref['purpose'],'evidence purpose')
            audit.require(type(pin) is str and bool(re.fullmatch('[0-9a-f]{64}',pin)), 'evidence hash syntax')
            if name in pins:
                audit.require(pins[name]==pin,'conflicting evidence pin')
            else:
                raw=anchored(evidence_dir/name,pin)
                total+=len(raw)
                audit.require(total<=TOTAL_EVIDENCE_BYTES,'total evidence byte limit')
                pins[name]=pin;artifacts[name]=raw
    audit.require(seen==set(findings),'every finding requires an explicit disposition')
    return artifacts


def record(packet_dir, manifest_sha, response_path, response_sha, decision_path, decision_sha, evidence_dir, output):
    files,packet=audit.verified_snapshot(packet_dir,manifest_sha)
    raw_response=anchored(response_path,response_sha);response=audit.strict_json(raw_response)
    packet_sha=audit.sha(files['packet.json'])
    review_counts=audit.validate_response(packet,packet_sha,response)
    raw_decisions=anchored(decision_path,decision_sha);decisions=audit.strict_json(raw_decisions)
    artifacts=validate_decisions(packet,response,packet_sha,response_sha,decisions,evidence_dir)
    counts=Counter(row['state'] for row in decisions['decisions'])
    receipt=dict(schema='geek-work-evm-decision-record-1',status='dispositions_recorded',
                 manifest_sha256=manifest_sha,packet_sha256=packet_sha,response_sha256=response_sha,
                 decisions_sha256=decision_sha,source_commit=packet['commit'],
                 states={state:counts[state] for state in STATES},findings=review_counts['findings'],
                 open_questions=len(response['open_questions']),
                 reported_failed_checks=review_counts['reported_failed_checks'],
                 reported_unchecked_checks=review_counts['reported_unchecked_checks'],
                 assessment_present=review_counts['assessment_present'],
                 evidence={name:audit.sha(raw) for name,raw in artifacts.items()},
                 findings_verified=False,resolutions_verified=False,fix_commits_checked=False,
                 adjudicator_identity_verified=False,independence_verified=False,
                 independent_audit_completed=False,production_ready=False,
                 limits='Recorded dispositions and evidence bytes only; no code execution, commit lookup or semantic adjudication.')
    output.mkdir(parents=True,exist_ok=False);(output/'evidence').mkdir()
    for name,raw in artifacts.items():
        with (output/'evidence'/name).open('xb') as f:f.write(raw)
    for name,raw in [('response.json',raw_response),('decisions.json',raw_decisions)]:
        with (output/name).open('xb') as f:f.write(raw)
    # Last file is the completion marker. Partial output is not a completed record.
    with (output/'receipt.json').open('xb') as f:f.write(audit.encode(receipt))
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--packet',type=Path,required=True);p.add_argument('--manifest-sha256',required=True)
    p.add_argument('--response',type=Path,required=True);p.add_argument('--response-sha256',required=True)
    p.add_argument('--decisions',type=Path,required=True);p.add_argument('--decisions-sha256',required=True)
    p.add_argument('--evidence-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    result=record(a.packet,a.manifest_sha256,a.response,a.response_sha256,a.decisions,a.decisions_sha256,a.evidence_dir,a.output)
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
