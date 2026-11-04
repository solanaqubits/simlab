#!/usr/bin/env python3
"""Measure a verified science selection and refuse excess bytes; no model or token estimate."""
import argparse
from pathlib import Path

import geek_work_science as science
import geek_work_context_profile as context
import geek_work_manuscript as m
import geek_work_manuscript_claims as k
import knowledge

MAX_CONTEXT = 16 * 1024 * 1024


def profile(bundle, anchor):
    science.verify(bundle, anchor)
    catalog = knowledge.strict_json(k.read_source(bundle, 'catalog.json'))
    plan = knowledge.strict_json(k.read_source(bundle, 'plan.json'))
    selected, fit, _ = science.selection(catalog, plan)
    # Compare the same JSON shape and order, excluding unavailable/domain-ineligible entries.
    baseline = [row for row in catalog['capabilities']
                if row['availability'] == 'offline_adapter' and plan['domain'] in row['domains']]
    chosen = {row['id'] for row in selected}
    ordered = [row for row in baseline if row['id'] in chosen]
    def payload(rows): return dict(capabilities=rows, task_fit=fit, budget=plan['budget'])
    full, subset = context.measure(payload(baseline)), context.measure(payload(ordered))
    capsule = k.read_source(bundle, 'capsule.md')
    return dict(schema='geek-work-science-context-profile-1',selection_manifest_sha256=anchor,
        tool_pins={Path(p).name:m.sha(Path(p).read_bytes()) for p in (__file__,science.__file__,context.__file__)},
        comparison=dict(format='canonical JSON; identical task_fit and budget',
            baseline=dict(**full,capability_ids=[r['id'] for r in baseline]),
            selected=dict(**subset,capability_ids=[r['id'] for r in ordered]),
            omitted_eligible_ids=[r['id'] for r in baseline if r['id'] not in chosen],
            excluded_ineligible_ids=[r['id'] for r in catalog['capabilities'] if r not in baseline],
            utf8_bytes_reduced=full['utf8_bytes']-subset['utf8_bytes']),
        actual_capsule=dict(sha256=m.sha(capsule),utf8_bytes=len(capsule),unicode_codepoints=len(capsule.decode('utf-8'))),
        token_usage=None,monetary_cost=None,answer_quality=None,model_calls=0,
        scientific_verification=False,execution_authorized=False,
        limits='Same-format capability metadata only; source contents, tool definitions and provider framing are excluded. '
               'Only selected material hashes were replayed. Baseline task_fit keeps the same selected IDs; '
               'this is a payload comparison, not a different executable plan or an ablation. '
               'Bytes/codepoints do not measure tokens, cost, quality or semantic completeness.')


def verify(report_raw, report_anchor, bundle, bundle_anchor):
    k.digest(report_anchor)
    m.require(m.sha(report_raw) == report_anchor, 'context report anchor mismatch')
    expected = profile(bundle, bundle_anchor)
    m.require(report_raw == m.encoded(expected), 'context report reproduction mismatch')
    return expected


def preflight(report_raw, report_anchor, bundle, bundle_anchor, max_bytes, additional_bytes):
    for value in (max_bytes, additional_bytes):
        m.require(type(value) is int and 0 <= value <= MAX_CONTEXT, 'bounded integer context bytes')
    m.require(max_bytes > 0, 'positive context byte budget')
    report = verify(report_raw, report_anchor, bundle, bundle_anchor)
    capsule_bytes = report['actual_capsule']['utf8_bytes']; total = capsule_bytes + additional_bytes
    return dict(schema='geek-work-science-context-preflight-1',
        status='within_byte_budget' if total <= max_bytes else 'refused',
        reasons=[] if total <= max_bytes else ['context_byte_budget_exceeded'],
        report_sha256=report_anchor,selection_manifest_sha256=bundle_anchor,
        capsule_bytes=capsule_bytes,additional_context_bytes_declared=additional_bytes,
        accounted_bytes=total,max_context_bytes=max_bytes,remaining_bytes=max(0,max_bytes-total),
        truncated=False,model_calls=0,token_usage=None,monetary_cost=None,
        additional_context_verified=False,token_window_verified=False,execution_authorized=False,
        limits='Pure preflight only; a caller must honor refusal. Additional prompt/material/framing bytes are '
               'caller-declared, not inspected. No truncation, model request, token-window guarantee or authorization.')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['profile','verify','preflight'])
    p.add_argument('--bundle',type=Path,required=True);p.add_argument('--bundle-sha256',required=True)
    p.add_argument('--report',type=Path);p.add_argument('--report-sha256');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--max-context-bytes',type=int);p.add_argument('--additional-context-bytes',type=int)
    a=p.parse_args()
    try:
        science.ops.outside(a.output, a.bundle, *([a.report] if a.report is not None else []))
        m.require(a.action=='preflight' or (a.max_context_bytes is None and a.additional_context_bytes is None),'unexpected budget arguments')
        if a.action=='profile':
            m.require(a.report is None and a.report_sha256 is None,'unexpected report arguments')
            result=profile(a.bundle,a.bundle_sha256)
        else:
            m.require(a.report is not None and a.report_sha256 is not None,'report and anchor required')
            raw=m.read(a.report)
            if a.action=='verify':
                verify(raw,a.report_sha256,a.bundle,a.bundle_sha256)
                result=dict(status='context_profile_reproduced',report_sha256=a.report_sha256,scientific_verification=False)
            else:result=preflight(raw,a.report_sha256,a.bundle,a.bundle_sha256,a.max_context_bytes,a.additional_context_bytes)
        raw=m.encoded(result);knowledge.write_new(a.output,raw)
        print(m.encoded(dict(status=result.get('status','profiled'),output_sha256=m.sha(raw))).decode(),end='')
        return 2 if result.get('status')=='refused' else 0
    except (ValueError,OSError,TypeError,KeyError,knowledge.Refusal,RecursionError) as error:
        print(m.encoded(dict(status='rejected',reason=str(error))).decode(),end='');return 2


if __name__=='__main__':raise SystemExit(main())
