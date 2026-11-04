#!/usr/bin/env python3
"""Route changed manuscript blocks to explicit excerpt guards; never accept semantics."""
import argparse
import html
import json
from pathlib import Path

import geek_work_manuscript as m
import geek_work_manuscript_hunks as h
import geek_work_manuscript_claims as k
import geek_work_batch_hunks as archive
import geek_work_file_operations as ops
import knowledge

KINDS = {'premise', 'negation', 'quantifier', 'uncertainty', 'non_claim',
         'formula', 'code', 'number', 'unit', 'citation', 'other'}


def overlap(start, end, row):
    left, right = row['before_start'], row['before_end']
    # Pure insertions at either boundary are deliberately included for review.
    return start <= left <= end if left == right else start < right and left < end



MAX_OCCURRENCES = 16


def context_occurrences(text, quote, surrounding_lines, selected_start=None):
    """Every overlapping literal match, in Unicode offsets; no inferred identity."""
    k.text(quote)
    m.require(type(surrounding_lines) is int and 1 <= surrounding_lines <= 3, 'context_lines must be 1..3')
    result = []; cursor = 0
    while True:
        start = text.find(quote, cursor)
        if start < 0:
            return result
        m.require(len(result) < MAX_OCCURRENCES, 'quote occurrence limit; select a longer excerpt')
        end = start + len(quote); left = text.rfind('\n', 0, start) + 1
        # Include the entire touched line(s) plus the requested surrounding LF lines.
        right = text.find('\n', end - 1)
        right = len(text) if right < 0 else right + 1
        for _ in range(surrounding_lines):
            if left > 0:
                left = text.rfind('\n', 0, left - 1) + 1
            if right < len(text):
                next_lf = text.find('\n', right)
                right = len(text) if next_lf < 0 else next_lf + 1
        result.append(dict(start=start, end=end, context_start=left, context_end=right,
                           context=text[left:right], selected_baseline_occurrence=(start == selected_start)))
        cursor = start + 1


def guard_spec(spec):
    m.require(type(spec) is dict, 'guard object required')
    version = spec.get('schema')
    m.require(version in ('geek-work-editorial-guards-1', 'geek-work-editorial-guards-2'), 'guard schema')
    k.obj(spec, 'schema proposal_sha256 base_sha256 guards' + (' context_lines' if version.endswith('-2') else ''))
    if version.endswith('-2'):
        m.require(type(spec['context_lines']) is int and 1 <= spec['context_lines'] <= 3, 'context_lines must be 1..3')
    return version.endswith('-2')


def derive(spec, proposal_anchor, before, after, rows):
    with_context = guard_spec(spec)
    k.digest(spec['proposal_sha256']); k.digest(spec['base_sha256'])
    m.require(spec['proposal_sha256'] == proposal_anchor, 'proposal pin mismatch')
    m.require(spec['base_sha256'] == m.sha(before), 'base pin mismatch')
    text = m.source(before); guards = []; seen = set()
    for guard in k.rows(spec['guards'], 64):
        k.obj(guard, 'id kind rationale span'); k.ident(guard['id']); k.text(guard['rationale'])
        m.require(guard['id'] not in seen, 'duplicate guard ID'); seen.add(guard['id'])
        m.require(type(guard['kind']) is str and guard['kind'] in KINDS, 'guard kind')
        k.span(guard['span'], {'before':text}, 'source')
        s = guard['span']; start = len(text[:s['start']].encode()); end = len(text[:s['end']].encode())
        affected = [r['id'] for r in rows if overlap(start,end,r)]
        guards.append(dict(id=guard['id'],kind=guard['kind'],rationale=guard['rationale'],span=s,
                           before_byte_start=start,before_byte_end=end,affected_hunks=affected,
                           status='changed_block_overlap' if affected else 'no_changed_block_overlap'))
    if with_context:
        candidate_text = m.source(after)
        for guard in guards:
            span = guard['span']
            guard['literal_context'] = dict(
                before=context_occurrences(text, span['quote'], spec['context_lines'], span['start']),
                after=context_occurrences(candidate_text, span['quote'], spec['context_lines']),
                occurrence_mapping_verified=False, semantic_preservation_verified=False)
    changes = [dict(**row,guard_ids=[g['id'] for g in guards if row['id'] in g['affected_hunks']],
                    review_required=True) for row in rows]
    report = dict(schema='geek-work-editorial-guard-report-1',status='review_required',
                proposal_sha256=proposal_anchor,base_sha256=m.sha(before),candidate_sha256=m.sha(after),
                algorithm='lf-sequence-matcher-v1 + selected-UTF8-span-overlap-v1',
                guards=guards,changes=changes,
                unguarded_hunks=[r['id'] for r in changes if not r['guard_ids']],
                changed_guard_count=sum(bool(g['affected_hunks']) for g in guards),
                selected_guard_coverage_complete=False,semantic_preservation_verified=False,
                independent_review_verified=False,scientific_verification=False,
                live_document_modified=False,publication_authorized=False)
    if with_context:
        report.update(schema='geek-work-editorial-guard-report-2', context_lines=spec['context_lines'],
                      context_algorithm='all-overlapping-literal-Unicode-matches-with-LF-context-v1',
                      context_coverage_complete=False)
    return report


def render(report):
    esc=lambda value:html.escape(str(value),quote=True)
    page='''<!doctype html><html lang="en"><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Editorial guard review</title>
<style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:1rem;color:#193044}article{border:1px solid #bdcad5;padding:1rem;margin:1rem 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:1rem}.notice{border-left:5px solid #a36113;padding:1rem;background:#fff4e3}</style>
<h1>Every changed block requires review</h1><p class="notice">A guard overlap is a review signal, not proof of a defect. No overlap is not semantic approval. Selected excerpts can miss context, new claims and interactions between blocks.</p>
<p><a href="proposal/hunk-review.html">Existing per-hunk review</a> · <a href="proposal/review.html">Full before/after proposal</a></p>'''
    page+='<h2>Selected excerpts</h2>'
    for guard in report['guards']:
        page+='<article><h3>'+esc(guard['id'])+' ['+esc(guard['kind'])+']</h3><p>'+esc(guard['status'])+'; blocks: '+esc(', '.join(guard['affected_hunks']) or 'none')+'</p><p>'+esc(guard['rationale'])+'</p><pre>'+esc(guard['span']['quote'])+'</pre></article>'
    if report['schema'] == 'geek-work-editorial-guard-report-2':
        page+='<h2>Literal occurrences and surrounding context</h2><p class="notice">All exact matches are shown, including overlaps. Equal text does not identify the same occurrence or preserve its meaning. Candidate matches are not automatically paired with baseline matches. Missing text is not a semantic verdict. Context windows are bounded; inspect the full proposal.</p>'
        for guard in report['guards']:
            page+='<article><h3>'+esc(guard['id'])+'</h3>'
            for side in ('before','after'):
                matches=guard['literal_context'][side]
                page+='<h4>'+esc(side)+' — '+str(len(matches))+' exact matches</h4>'
                if not matches: page+='<p>No exact occurrence; full candidate review is required.</p>'
                for match in matches:
                    page+='<p>Unicode ['+str(match['start'])+', '+str(match['end'])+'); '+('selected baseline excerpt' if match['selected_baseline_occurrence'] else 'unpaired occurrence')+'</p><pre>'+esc(match['context'])+'</pre>'
            page+='</article>'
    page+='<h2>All changed blocks</h2>'
    for row in report['changes']:
        page+='<article><h3>'+esc(row['id'])+' — '+esc(row['kind'])+'</h3><p>Guards: '+esc(', '.join(row['guard_ids']) or 'none selected — review still required')+'</p><h4>Before</h4><pre>'+esc(row['before_text'])+'</pre><h4>After</h4><pre>'+esc(row['after_text'])+'</pre></article>'
    page+='<h2>Scope and reproducible report</h2><pre>'+esc(json.dumps(report,ensure_ascii=False,indent=2))+'</pre></html>\n'
    raw=page.encode();m.require(len(raw)<=m.MAX_ARTIFACT,'HTML byte bound');return raw


def payload(guard_raw, proposal, anchor):
    meta,data,rows,manifest_raw=h.verified(proposal,anchor)
    spec=knowledge.strict_json(guard_raw)
    report=derive(spec,anchor,data['before.txt'],data['after.txt'],rows)
    report_raw=m.encoded(report);m.require(len(report_raw)<=m.MAX_ARTIFACT,'report byte bound')
    return {'guards.json':guard_raw,'report.json':report_raw,'index.html':render(report),
            **{'proposal/'+n:raw for n,raw in data.items()},'proposal/manifest.json':manifest_raw}


def manifest(files):
    return m.encoded(dict(schema='geek-work-editorial-guard-archive-1',files={n:m.sha(raw) for n,raw in files.items()}))


def prepare(proposal,proposal_anchor,guards,guards_anchor,output):
    k.digest(proposal_anchor);k.digest(guards_anchor);ops.outside(output,proposal,guards)
    raw=m.read(guards);m.require(m.sha(raw)==guards_anchor,'guard spec anchor mismatch')
    files=payload(raw,proposal,proposal_anchor);meta=manifest(files)
    archive.write_tree(output,{**files,'manifest.json':meta})
    return dict(status='review_required',manifest_sha256=m.sha(meta),semantic_preservation_verified=False)


def verify(bundle,anchor):
    k.digest(anchor);m.require(bundle.is_dir() and not bundle.is_symlink(),'regular review archive')
    meta=m.read(bundle/'manifest.json');m.require(m.sha(meta)==anchor,'review anchor mismatch')
    raw=m.read(bundle/'guards.json');spec=knowledge.strict_json(raw)
    guard_spec(spec);k.digest(spec['proposal_sha256'])
    files=payload(raw,bundle/'proposal',spec['proposal_sha256'])
    m.require(meta==manifest(files),'review manifest reproduction mismatch')
    archive.exact_tree(bundle,set(files)|{'manifest.json'})
    for name,data in files.items():m.require(m.read(bundle/name,max(len(data),1))==data,'review artifact mismatch')
    return dict(status='review_integrity_reproduced',review_disposition='review_required',
                manifest_sha256=anchor,semantic_preservation_verified=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    q=sub.add_parser('prepare')
    for n in ('proposal','guards','output'):q.add_argument('--'+n,type=Path,required=True)
    for n in ('proposal-sha256','guards-sha256'):q.add_argument('--'+n,required=True)
    q=sub.add_parser('verify');q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True)
    a=p.parse_args()
    try:
        result=prepare(a.proposal,a.proposal_sha256,a.guards,a.guards_sha256,a.output) if a.action=='prepare' else verify(a.bundle,a.sha256)
        print(json.dumps(result));return 0
    except (ValueError,OSError,KeyError,TypeError,RecursionError) as error:
        print(json.dumps(dict(status='rejected',reason=str(error))));return 2


if __name__=='__main__':raise SystemExit(main())
