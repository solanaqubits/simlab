#!/usr/bin/env python3
"""Fixed sum-of-squares control pilot; exact finite checks, not a universal proof."""
import argparse
from fractions import Fraction
from pathlib import Path
import platform
import re
import tempfile

import geek_work_polynomial_candidate as generator
import geek_work_manuscript as m
import geek_work_manuscript_claims as k
import geek_work_batch_hunks as archive
import geek_work_file_operations as ops
import geek_work_experiment as experiment
import geek_work_ledger as ledger
import knowledge

SCHEMA='geek-work-exact-pilot-archive-1'
PROFILE='sum-squares-controls-v1'
IDS=['null','sign-error','training-only','interpolated']
TRAINING={'samples':[{'n':n,'sum_squares':v} for n,v in enumerate([0,1,5,14])]}
HOLDOUT={'points':[4,5,7,11]}
BUDGET=dict(max_attempts=4,wall_time_seconds=30,memory_bytes=268435456,token_limit=None,cost_usd=None)
PARAMETERS=dict(profile=PROFILE,coefficient_order='ascending',max_degree=8,max_coefficient_bits=128,
                arithmetic='Fraction',attempt_order=IDS,holdout_blinded=False)


def implementation():
    return {'checker.py':Path(__file__).read_bytes(),'generator.py':Path(generator.__file__).read_bytes()}


def freeze(output):
    # Native passport captures inert source bytes; nothing from this archive is executed.
    files={**implementation(),'training.json':m.encoded(TRAINING),'holdout.json':m.encoded(HOLDOUT)}
    spec=experiment.plan_template('exact-arithmetic');spec.update(id=PROFILE,title='Finite sum-of-squares candidate/checker controls',
        hypothesis='Interpolation matches direct sums on fixed assessment points while deliberately wrong controls fail.',
        readiness='ready_for_protocol_review',parameters=PARAMETERS,budget=BUDGET,
        sources=[dict(id=name.split('.')[0],path=name,sha256=m.sha(raw),role='code' if name.endswith('.py') else 'holdout' if name=='holdout.json' else 'data') for name,raw in files.items()],
        holdout=dict(source_ids=['holdout'],exposure='previously_inspected',note='Fixed public fixture known to the author; generator function receives training only. This is not a blinded experiment.'),
        controls=[dict(kind='positive',description='Interpolated candidate',expected='Matches training and assessment points'),
                  dict(kind='null',description='Zero polynomial',expected='Fails nonzero training and assessment points'),
                  dict(kind='injection',description='Sign flip and training-vanishing overfit term',expected='Sign flip fails; overfit matches training but fails assessment')],
        criteria=dict(recovered='All four declared control patterns occur on this finite fixture',inconsistent='A valid candidate result disagrees with its fixed expected control pattern',excluded='Malformed, oversized or wrong-profile input: reject without a mathematical verdict',insufficient_data='Missing source or assessment points: reject, never substitute success'),
        non_claims=['No novelty, universal polynomial theorem, formal proof, scientific discovery or performance improvement.',
                    'Same author, Python/Fraction and archiving helpers; implementation diversity does not establish independence.',
                    'Finite input bounds are checked; wall/memory budgets need an external supervisor. No model or paid service is called.'])
    with tempfile.TemporaryDirectory(prefix='geek-exact-plan-') as temp:
        root=Path(temp)
        for name,raw in files.items():(root/name).write_bytes(raw)
        p=root/'plan.json';p.write_bytes(m.encoded(spec))
        return experiment.capture('plan',p,m.sha(p.read_bytes()),root,output)


def plan_bytes(bundle,anchor):
    experiment.verify(bundle,anchor)
    meta=m.read(bundle/'manifest.json');m.require(m.sha(meta)==anchor,'plan anchor changed')
    manifest=knowledge.strict_json(meta);m.require(manifest['kind']=='plan','frozen plan required')
    files={name:m.read(bundle/name,k.MAX_TOTAL) for name in manifest['files']}
    m.require(all(m.sha(raw)==manifest['files'][name] for name,raw in files.items()),'plan changed during read')
    spec=knowledge.strict_json(files['spec.json'])
    m.require(spec['id']==PROFILE and spec['parameters']==PARAMETERS and spec['budget']==BUDGET,'fixed pilot profile/budget required')
    m.require(spec['holdout']['exposure']=='previously_inspected','no blinded holdout claim')
    expected={**implementation(),'training.json':m.encoded(TRAINING),'holdout.json':m.encoded(HOLDOUT)}
    m.require({r['path'] for r in spec['sources']}==set(expected),'fixed pilot source set')
    for name,raw in expected.items():m.require(files['sources/'+name]==raw,'pinned source/runtime mismatch: '+name)
    return {**files,'manifest.json':meta}


def rational(value):
    m.require(type(value) is str and len(value)<=82 and re.fullmatch(r'-?(0|[1-9][0-9]*)(/[1-9][0-9]*)?',value),'bounded rational text')
    q=Fraction(value);m.require(max(q.numerator.bit_length(),q.denominator.bit_length())<=128,'coefficient bit limit')
    m.require(str(q)==value,'canonical rational text');return q


def check(candidates):
    k.rows(candidates,4,4);m.require([c.get('id') for c in candidates if type(c) is dict]==IDS,'fixed candidate order/set')
    rows=[]
    for c in candidates:
        k.obj(c,'id coefficients');coefficients=[rational(x) for x in k.rows(c['coefficients'],9,1)]
        checks={}
        for name,points in [('training',[0,1,2,3]),('assessment',HOLDOUT['points'])]:
            values=[]
            for n in points:
                value=Fraction(0)
                for coefficient in reversed(coefficients):value=value*n+coefficient
                # Integer direct summation, not interpolation or the closed-form polynomial.
                expected=sum(i*i for i in range(1,n+1))
                values.append(dict(n=n,expected=str(expected),actual=str(value),matches=value==expected))
            checks[name]=dict(matches=all(x['matches'] for x in values),points=values)
        rows.append(dict(id=c['id'],**checks))
    patterns={r['id']:(r['training']['matches'],r['assessment']['matches']) for r in rows}
    ok=patterns=={'null':(False,False),'sign-error':(False,False),'training-only':(True,False),'interpolated':(True,True)}
    return dict(schema='geek-work-exact-pilot-report-1',status='controls_observed' if ok else 'control_pattern_mismatch',
                control_suite_passed=ok,rows=rows,candidate_count=4,point_evaluations=32,
                training_only_false_acceptance_ids=[r['id'] for r in rows if r['training']['matches'] and not r['assessment']['matches']],
                holdout_blinding_verified=False,independence_verified=False,universal_identity_proved=False,
                scientific_verification=False,publication_authorized=False,model_called_here=False,
                os_resource_limits_enforced_here=False,token_usage=None,monetary_cost=None,
                limits='Exact finite evaluation only. Public assessment fixture, same author and Python/Fraction runtime. A match is not a universal proof; a mismatch is a counterexample at the recorded n. Control success is not discovery or a quality benchmark.')


def reported_ledger(report):
    # The task is the control suite; attempts are its four planned checks, not an optimization trajectory.
    raw=m.encoded(report)
    attempts=[dict(attempt_id=i+1,model_profile=None,model_transition='initial' if i==0 else 'unknown',token_usage=None,
                   monetary_cost=None,verification_wall_time_ms=None,human_interventions=None,
                   failure_classes=[] if r['assessment']['matches'] else ['finite_value_mismatch']) for i,r in enumerate(report['rows'])]
    doc=dict(schema='geek-work-ledger-1',currency='USD',cost_scope='attempt_including_verification',tasks=[dict(task_id=PROFILE,
        outcome='accepted' if report['control_suite_passed'] else 'rejected',attempts_count=4,attempts=attempts,
        acceptance=dict(kind='machine_check',evidence=[dict(path='report.json',sha256=m.sha(raw))]) if report['control_suite_passed'] else None)])
    ledger.validate(doc);return doc


def artifacts(parent,candidates):
    report=check(candidates);doc=reported_ledger(report)
    files={**{'plan/'+n:b for n,b in parent.items()},'candidates.json':m.encoded(candidates),'report.json':m.encoded(report),
           'ledger.json':m.encoded(doc),'cost-summary.json':m.encoded(ledger.summarize([doc]))}
    m.require(sum(map(len,files.values()))<=k.MAX_TOTAL,'pilot archive limit');return files,report


def manifest(files):return m.encoded(dict(schema=SCHEMA,files={n:m.sha(b) for n,b in files.items()}))


def run(plan,anchor,output):
    ops.outside(output,plan);parent=plan_bytes(plan,anchor)
    samples=knowledge.strict_json(parent['sources/training.json'])['samples']
    # No holdout object is passed to the generator; this is an interface boundary, not a sandbox.
    files,report=artifacts(parent,generator.candidates(samples));meta=manifest(files)
    archive.write_tree(output,{**files,'manifest.json':meta})
    return dict(status=report['status'],manifest_sha256=m.sha(meta),control_suite_passed=report['control_suite_passed'])


def verify(bundle,anchor):
    k.digest(anchor);meta=m.read(bundle/'manifest.json');m.require(m.sha(meta)==anchor,'pilot anchor mismatch')
    plan_meta=k.read_source(bundle,'plan/manifest.json');parent=plan_bytes(bundle/'plan',m.sha(plan_meta))
    # Replay the checker on saved candidates, never regenerate them or execute archived code.
    candidates=knowledge.strict_json(k.read_source(bundle,'candidates.json'));files,report=artifacts(parent,candidates)
    m.require(meta==manifest(files),'pilot reproduction mismatch');archive.exact_tree(bundle,set(files)|{'manifest.json'})
    for name,data in files.items():m.require(k.read_source(bundle,name)==data,'pilot artifact mismatch')
    return dict(status=report['status'],integrity_reproduced=True,generator_rerun=False,control_suite_passed=report['control_suite_passed'])


def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    q=s.add_parser('freeze');q.add_argument('--output',type=Path,required=True)
    for action in ('run','verify'):
        q=s.add_parser(action);q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True)
        if action=='run':q.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        if a.action=='freeze':r=freeze(a.output)
        elif a.action=='run':r=run(a.bundle,a.sha256,a.output)
        else:r=verify(a.bundle,a.sha256)
        print(m.encoded(r).decode(),end='');return 3 if r.get('control_suite_passed') is False else 0
    except (ValueError,OSError,TypeError,KeyError,RecursionError) as exc:
        print(m.encoded(dict(status='rejected',reason=str(exc))).decode(),end='');return 2


if __name__=='__main__':raise SystemExit(main())
