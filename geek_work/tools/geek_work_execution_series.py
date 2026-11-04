#!/usr/bin/env python3
"""Selected fixed-profile executions: failure-inclusive accounting, not global completeness."""
import argparse
from collections import Counter
from pathlib import Path

import geek_work_exact_runner as runner
import geek_work_manuscript as m
import geek_work_manuscript_claims as k
import geek_work_batch_hunks as archive
import geek_work_file_operations as ops
import knowledge

SCHEMA='geek-work-execution-series-1'
MAX_ATTEMPTS=16
MAX_TOTAL=64*1024*1024


def capture(bundle,anchor,budget=None):
    budget=MAX_TOTAL if budget is None else budget
    m.require(type(budget) is int and 0<budget<=MAX_TOTAL,'remaining series byte budget')
    # Native verification is separately bounded; the following copy uses only the
    # remaining series allowance, including this attempt's root manifest bytes.
    runner.verify(bundle,anchor)
    meta=m.read(bundle/'manifest.json',min(m.MAX_ARTIFACT,budget))
    m.require(m.sha(meta)==anchor,'attempt changed during capture')
    files={'manifest.json':meta};total=len(meta)
    names,_=runner.scan_layout(bundle)
    for name in names:
        raw=m.read(bundle/name,min(k.MAX_TOTAL,budget-total));total+=len(raw)
        m.require(total<=budget,'series capture byte limit');files[name]=raw
    manifest=knowledge.strict_json(meta)
    m.require({n:m.sha(b) for n,b in files.items() if n!='manifest.json'}==manifest['files'],'attempt changed during capture')
    return files


def summarize(attempts):
    rows=[];groups={};seen=set()
    for anchor,files in attempts:
        req=knowledge.strict_json(files['request.json']);rec=knowledge.strict_json(files['receipt.json'])
        identity=req['attempt_id'];m.require(identity not in seen,'duplicate execution attempt');seen.add(identity)
        binding=dict(plan_sha256=req['plan_sha256'],runtime=req['runtime'],limits=req['limits'])
        key=m.sha(m.encoded(binding))
        row=dict(attempt_id=identity,manifest_sha256=anchor,binding_group=key,
                 status=rec['result']['status'],wall_time_ms=rec['process']['wall_time_ms'])
        rows.append(row);groups.setdefault(key,dict(binding=binding,rows=[]))['rows'].append(row)
    summaries=[]
    for key,group in sorted(groups.items()):
        selected=group['rows'];counts=dict(sorted(Counter(r['status'] for r in selected).items()))
        accepted=counts.get('controls_observed',0);total=sum(r['wall_time_ms'] for r in selected)
        summaries.append(dict(binding_group=key,bindings=group['binding'],attempts_count=len(selected),
            outcome_counts=counts,control_suite_successes=accepted,total_process_wall_time_ms=total,
            process_wall_ms_per_control_suite_success=dict(numerator=total,denominator=accepted) if accepted else None,
            monetary_cost_per_control_suite_success=None,token_usage=None))
    return dict(schema=SCHEMA,attempts=rows,groups=summaries,attempts_count=len(rows),
        exact_bindings_match=len(groups)==1,global_attempt_completeness_verified=False,
        scientific_comparability_verified=False,execution_independently_verified=False,
        limits='Only explicitly selected completed receipts. Equal fingerprints do not establish equal hardware/load, independence, scientific comparability or chronology. Time includes failed selected executions, excludes preflight/replay and is not full pipeline cost. Four internal controls are not four execution attempts.')


def contents(attempts):
    k.rows(attempts,MAX_ATTEMPTS,1)
    report=summarize(attempts)
    files={'selection.json':m.encoded(dict(schema=SCHEMA,anchors=[h for h,_ in attempts])),
           'report.json':m.encoded(report)}
    m.require(all(len(b)<=k.MAX_FILE for b in files.values()),'series generated metadata byte limit')
    for i,(_,blobs) in enumerate(attempts):files.update({f'attempts/{i:04d}/'+n:b for n,b in blobs.items()})
    m.require(sum(map(len,files.values()))<=MAX_TOTAL,'series byte limit')
    return files,report


def manifest(files):
    raw=m.encoded(dict(schema=SCHEMA,files={n:m.sha(b) for n,b in files.items()}))
    m.require(len(raw)<=m.MAX_ARTIFACT,'series manifest byte limit');return raw


def build(bundles,anchors,output):
    m.require(1<=len(bundles)<=MAX_ATTEMPTS and len(bundles)==len(anchors),'one anchor per attempt; 1–16 attempts')
    ops.outside(output,*bundles)
    attempts=[];total=0
    for bundle,anchor in zip(bundles,anchors):
        blobs=capture(bundle,anchor,MAX_TOTAL-total);total+=sum(map(len,blobs.values()));m.require(total<=MAX_TOTAL,'series byte limit')
        attempts.append((anchor,blobs))
    files,report=contents(attempts);meta=manifest(files)
    archive.write_tree(output,{**files,'manifest.json':meta})
    # Preserve empty partial-run directories included in nested receipts.
    for i,(_,blobs) in enumerate(attempts):
        for d in knowledge.strict_json(blobs['manifest.json'])['directories']:(output/f'attempts/{i:04d}'/d).mkdir(parents=True,exist_ok=True)
    return dict(status='recorded',manifest_sha256=m.sha(meta),attempts_count=report['attempts_count'],exact_bindings_match=report['exact_bindings_match'])


def verify(bundle,anchor):
    k.digest(anchor);meta=m.read(bundle/'manifest.json');m.require(m.sha(meta)==anchor,'series anchor mismatch')
    selection=knowledge.strict_json(k.read_source(bundle,'selection.json'));k.obj(selection,'schema anchors')
    m.require(selection['schema']==SCHEMA,'selection schema');k.rows(selection['anchors'],MAX_ATTEMPTS,1)
    attempts=[];total=0
    for i,h in enumerate(selection['anchors']):
        blobs=capture(bundle/f'attempts/{i:04d}',h,MAX_TOTAL-total);total+=sum(map(len,blobs.values()));m.require(total<=MAX_TOTAL,'series byte limit')
        attempts.append((h,blobs))
    files,report=contents(attempts);m.require(meta==manifest(files),'series reproduction mismatch')
    # Nested runners validate their own full directory trees, including empty dirs.
    archive.b.directory(bundle,{'attempts','manifest.json','selection.json','report.json'})
    archive.b.directory(bundle/'attempts',{f'{i:04d}' for i in range(len(attempts))})
    for name in ('selection.json','report.json'):m.require(k.read_source(bundle,name)==files[name],'series report mismatch')
    return dict(status='reproduced',attempts_count=report['attempts_count'],exact_bindings_match=report['exact_bindings_match'],subprocess_rerun=False,global_attempt_completeness_verified=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    q=s.add_parser('build');q.add_argument('--attempt',type=Path,action='append',required=True);q.add_argument('--sha256',action='append',required=True);q.add_argument('--output',type=Path,required=True)
    q=s.add_parser('verify');q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True)
    a=p.parse_args()
    try:
        r=build(a.attempt,a.sha256,a.output) if a.action=='build' else verify(a.bundle,a.sha256)
        print(m.encoded(r).decode(),end='');return 0
    except (ValueError,OSError,TypeError,KeyError,RecursionError) as exc:
        print(m.encoded(dict(status='rejected',reason=str(exc))).decode(),end='');return 2


if __name__=='__main__':raise SystemExit(main())
