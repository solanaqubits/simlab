#!/usr/bin/env python3
"""Offline payload sizing; no model, tokenizer, billing or quality estimate."""
import argparse
from pathlib import Path
import knowledge as k
import geek_work_memory as memory


def measure(value):
    raw = k.canonical(value)
    return dict(sha256=k.digest(raw), utf8_bytes=len(raw), unicode_codepoints=len(raw.decode('utf-8')))


def profile(graph, root, request):
    selected = memory.retrieve(graph, root, request)
    k.require(selected['graph_sha256'] == request['expected_graph_sha256'], 'graph_changed')
    k.require(not any('revision_changed' in row['issues'] for row in selected['cards']), 'revision_changed')
    ids = {row['card']['id'] for row in selected['cards']}
    # Same payload schema on both sides; source diagnostics are reported separately.
    full = dict(cards=graph['cards'], links=graph['links'])
    subset = dict(cards=[c for c in graph['cards'] if c['id'] in ids], links=selected['links'])
    boundary = [e for e in graph['links'] if (e['from'] in ids) != (e['to'] in ids)]
    return dict(schema='geek-work-context-profile-1', graph_sha256=selected['graph_sha256'],
                request_sha256=k.digest(k.canonical(request)),
                tool_pins={Path(p).name:k.digest(Path(p).read_bytes()) for p in (__file__, memory.__file__, k.__file__)},
                full=dict(**measure(full), cards=len(full['cards']), links=len(full['links']), source_checks='not_run'),
                selected=dict(**measure(subset), cards=len(subset['cards']), links=len(subset['links']),
                              requested_ids=sorted(row['card']['id'] for row in selected['cards'] if row['requested']),
                              closure_ids=sorted(row['card']['id'] for row in selected['cards'] if not row['requested']),
                              issues=selected['issues'], source_checks='selected_provenance_checked'),
                retrieval_envelope=measure(selected), boundary_links=boundary,
                omitted_ids=sorted(c['id'] for c in graph['cards'] if c['id'] not in ids),
                token_usage=None, monetary_cost=None, answer_quality=None, model_calls=0,
                limits='Canonical JSON cards+links only; no prompts, events, source bytes or provider framing. '
                       'Closure covers recorded depends_on/contradicts/corrects, not semantic completeness. '
                       'Character and byte sizes are not token usage, cost or evidence of quality.')


def verify(report, anchor, graph, root, request):
    memory.sha(anchor)
    k.require(k.digest(k.canonical(report)) == anchor, 'report_anchor')
    expected = profile(graph, root, request)
    k.require(k.canonical(report) == k.canonical(expected), 'report_not_reproducible')
    return dict(status='verified_profile', report_sha256=anchor,
                graph_sha256=expected['graph_sha256'], model_calls=0,
                scientific_verification=False, quality_comparison=False)


def preflight(report, anchor, graph, root, request, max_bytes):
    k.require(type(max_bytes) is int and 0 < max_bytes <= 16 * 1024 * 1024, 'byte_budget_range')
    verify(report, anchor, graph, root, request)
    size = report['retrieval_envelope']['utf8_bytes']
    reasons = []
    if size > max_bytes: reasons.append('context_byte_budget_exceeded')
    if report['selected']['issues']: reasons.append('context_requires_review')
    return dict(schema='geek-work-context-preflight-1',
                status='refused' if reasons else 'within_context_budget', reasons=reasons,
                report_sha256=anchor, max_context_bytes=max_bytes, context_bytes=size,
                remaining_context_bytes=max(0,max_bytes-size),
                source_issues=report['selected']['issues'], truncated=False,
                model_calls=0, execution_authorized=False,
                limits='Budget covers canonical retrieval envelope only. Caller must separately '
                       'budget prompts, tool definitions, framing and output. Not a token/context-window '
                       'guarantee, semantic approval or authorization to transmit private data.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--graph',type=Path,required=True);p.add_argument('--root',type=Path,required=True)
    p.add_argument('action',nargs='?',choices=['profile','verify','preflight'],default='profile')
    p.add_argument('--request',type=Path,required=True);p.add_argument('--output',type=Path)
    p.add_argument('--report',type=Path);p.add_argument('--anchor')
    p.add_argument('--max-context-bytes',type=int)
    a=p.parse_args()
    try:
        k.require(a.action=='preflight' or a.max_context_bytes is None,'unexpected_byte_budget')
        graph=k.load(a.graph);request=k.load(a.request)
        if a.action=='profile':
            k.require(a.output is not None and a.report is None and a.anchor is None,'profile_arguments')
            report=profile(graph,a.root,request)
            k.write_new(a.output,k.canonical(report)+b'\n')
            result=dict(status='profiled',report_sha256=k.digest(k.canonical(report)))
        else:
            k.require(a.report is not None and a.anchor is not None,'verify_arguments')
            report=k.load(a.report)
            result=(preflight(report,a.anchor,graph,a.root,request,a.max_context_bytes)
                    if a.action=='preflight' else verify(report,a.anchor,graph,a.root,request))
            if a.output:k.write_new(a.output,k.canonical(result)+b'\n')
        print(k.canonical(result).decode())
        if result['status']=='refused':return 1
    except (k.Refusal,OSError,ValueError,KeyError,TypeError) as e:
        print(k.canonical(dict(status='refused',reason=str(e))).decode());return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
