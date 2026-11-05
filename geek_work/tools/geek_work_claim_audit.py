#!/usr/bin/env python3
"""Offline audit matrix over native manuscript claim bundles; judgments remain reported."""
import argparse
from collections import Counter
import html
import json
from pathlib import Path

import geek_work_manuscript as m
import geek_work_manuscript_claims as k
import geek_work_batch_hunks as archive
import geek_work_file_operations as ops
import knowledge

SCHEMA = 'geek-work-claim-audit-archive-1'
MAX_BUNDLE = k.MAX_TOTAL + 4*k.MAX_FILE
CONCLUSIONS = ('not_checked', 'supports', 'contradicts', 'not_established', 'mixed')
ROLES = ('reference', 'code', 'data', 'check_result')


def parent_bytes(bundle, anchor):
    k.verify(bundle, anchor)
    meta = m.read(bundle/'manifest.json')
    # Recheck the external anchor on the snapshot used below, not only the first read.
    m.require(m.sha(meta) == anchor, 'parent anchor changed')
    manifest = knowledge.strict_json(meta)
    flat = {name:m.read(bundle/name, k.MAX_TOTAL) for name in manifest['files']}
    m.require(all(m.sha(raw) == manifest['files'][name] for name,raw in flat.items()), 'parent changed during read')
    mapping = knowledge.strict_json(flat['map.json'])
    generated = k.derive(mapping, {name:flat[name] for name in k.catalog(mapping)})
    m.require(all(flat[name] == raw for name,raw in generated.items()), 'parent reconstruction mismatch')
    return mapping, {**flat, 'manifest.json':meta}


def template(mapping, anchor, reviewer):
    k.text(reviewer); k.digest(anchor)
    return dict(schema='geek-work-claim-audit-review-1', claim_bundle_sha256=anchor,
                reviewer=dict(id=reviewer, prior_exposure='Not recorded; fill before assessment.', independence_verified=False),
                claims=[dict(claim_id=c['id'], conclusion='not_checked', rationale=None, comparisons=[]) for c in mapping['claims']])


def derive(raw, mapping, parent):
    review = knowledge.strict_json(raw)
    k.obj(review, 'schema claim_bundle_sha256 reviewer claims')
    m.require(review['schema'] == 'geek-work-claim-audit-review-1', 'audit review schema')
    k.digest(review['claim_bundle_sha256'])
    m.require(review['claim_bundle_sha256'] == m.sha(parent['manifest.json']), 'review parent mismatch')
    k.obj(review['reviewer'], 'id prior_exposure independence_verified')
    k.text(review['reviewer']['id']); k.text(review['reviewer']['prior_exposure'])
    m.require(review['reviewer']['independence_verified'] is False, 'independence cannot be established here')
    claims = {c['id']:c for c in mapping['claims']}
    materials = {r['id']:r for r in mapping['materials']}
    texts = {mid:k.utf8(parent['material-'+mid+'.txt']) for mid in materials}
    seen = set(); ordered = {}; citation_count = 0
    for row in k.rows(review['claims'], 64, 1):
        k.obj(row, 'claim_id conclusion rationale comparisons'); k.ident(row['claim_id'])
        m.require(row['claim_id'] in claims and row['claim_id'] not in seen, 'unknown/duplicate audit claim')
        seen.add(row['claim_id']); ordered[row['claim_id']] = row
        conclusion = row['conclusion']
        m.require(type(conclusion) is str and conclusion in CONCLUSIONS, 'reported conclusion')
        if conclusion == 'not_checked':
            m.require(row['rationale'] is None, 'not_checked rationale must be null')
        else:
            k.text(row['rationale'])
        comparisons = k.rows(row['comparisons'], 16)
        m.require(conclusion == 'not_checked' or bool(comparisons), 'assessed claim requires cited comparison')
        unique = set()
        for comparison in comparisons:
            k.obj(comparison, 'role citation observation')
            m.require(type(comparison['role']) is str and comparison['role'] in ROLES, 'comparison role')
            k.span(comparison['citation'], texts, 'material'); k.text(comparison['observation'])
            c = comparison['citation']; key = (comparison['role'], c['material'], c['start'], c['end'])
            m.require(key not in unique, 'duplicate comparison'); unique.add(key); citation_count += 1
    m.require(seen == set(claims), 'every mapped claim must have an explicit review row')
    matrix = []
    for cid, claim in claims.items():
        row = ordered[cid]
        enriched = [dict(**c, material_metadata=materials[c['citation']['material']]) for c in row['comparisons']]
        matrix.append(dict(**row, statement=claim['statement'], reported_evidence_state=claim['reported_evidence_state'],
                           scope=claim['scope'], assumptions=claim['assumptions'], non_claims=claim['non_claims'],
                           open_obligations=claim['open_obligations'], original_evidence=claim['evidence'],
                           comparisons_with_provenance=enriched,
                           roles_without_citations=[r for r in ROLES if not any(c['role']==r for c in row['comparisons'])]))
    report = dict(schema='geek-work-claim-audit-report-1', status='audit_bindings_reproduced', claims=len(claims),
                  citation_count=citation_count, reported_conclusions=dict(sorted(Counter(r['conclusion'] for r in matrix).items())),
                  reviewer=review['reviewer'], judgments_are_reported=True, semantic_correspondence_verified=False,
                  material_roles_verified=False, scientific_verification=False, independence_verified=False,
                  kernel_replayed=False, code_executed=False, origin_commits_verified=False, all_document_claims_covered=False,
                  publication_authorized=False, accepted_as_gold=False,
                  limits='Exact bytes, citations and complete coverage of the supplied map only. Roles, observations and conclusions are reviewer assertions. Citation presence does not establish support, contradiction, execution, independence, authenticity or complete manuscript coverage.')
    payload = dict(schema='geek-work-claim-audit-matrix-1', claim_bundle_sha256=review['claim_bundle_sha256'],
                   documents=mapping['documents'], materials=mapping['materials'], rows=matrix, report=report)
    files = {'review.json':raw, 'matrix.json':m.encoded(payload), 'report.json':m.encoded(report), 'index.html':render(payload)}
    m.require(all(len(b) <= k.MAX_FILE for b in files.values()), 'audit artifact byte limit')
    return files


def render(matrix):
    esc = lambda v: html.escape(str(v), quote=True)
    pre = lambda v: '<pre>'+esc(json.dumps(v, ensure_ascii=False, indent=2))+'</pre>'
    parts = ['''<!doctype html><html lang="en"><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Claim audit matrix</title>
<style>body{font:16px/1.6 system-ui;max-width:1100px;margin:2rem auto;padding:1rem;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%}th,td{border:1px solid #aab;padding:.6rem;text-align:left;vertical-align:top}details{border:1px solid #aab;padding:1rem;margin:1rem 0}summary{cursor:pointer;font-weight:bold}a{color:#164e8a}a:focus-visible,summary:focus-visible{outline:3px solid #287abb}</style>
<h1>Claim → materials → code/data → reported checks</h1>
<p>Only bytes and citations were checked here. Conclusions and material roles are reported reviewer judgments, not scientific acceptance. “not_checked” is not falsehood; absent citations are not evidence of absence.</p>
<p>A check_result citation is text from a supplied report: no code, verifier or Lean kernel was run by this tool.</p>
<table><caption>All claims in the supplied map (not necessarily all manuscript claims)</caption><thead><tr><th scope="col">Claim</th><th scope="col">Reported conclusion</th><th scope="col">Roles without citations</th></tr></thead><tbody>''']
    for row in matrix['rows']:
        parts.append('<tr><th scope="row"><a href="#claim-'+esc(row['claim_id'])+'">'+esc(row['claim_id'])+'</a></th><td>'+esc(row['conclusion'])+'</td><td>'+esc(', '.join(row['roles_without_citations']) or 'none')+'</td></tr>')
    parts.append('</tbody></table>')
    for row in matrix['rows']:
        parts.append('<section id="claim-'+esc(row['claim_id'])+'"><h2>'+esc(row['claim_id'])+'</h2><blockquote><pre>'+esc(row['statement']['quote'])+'</pre></blockquote><p>Reported conclusion: '+esc(row['conclusion'])+'</p>')
        parts.append('<h3>Reviewer rationale</h3>'+pre(row['rationale']))
        for c in row['comparisons_with_provenance']:
            parts.append('<details open><summary>'+esc(c['role'])+' · '+esc(c['citation']['material'])+'</summary><blockquote><pre>'+esc(c['citation']['quote'])+'</pre></blockquote><p>'+esc(c['observation'])+'</p>'+pre(dict(citation=c['citation'],material=c['material_metadata']))+'</details>')
        parts.append('<details><summary>Original claim scope, assumptions, evidence and open obligations</summary>'+pre({k:v for k,v in row.items() if k not in {'comparisons','comparisons_with_provenance'}})+'</details></section>')
    parts.append('<h2>Source identities and review limits</h2>'+pre({k:v for k,v in matrix.items() if k!='rows'})+'</html>\n')
    return ''.join(parts).encode()


def manifest(files):
    return m.encoded(dict(schema=SCHEMA, files={n:m.sha(b) for n,b in files.items()}))


def build(bundle, anchor, review_path, review_sha, output):
    ops.outside(output, bundle, review_path); k.digest(review_sha)
    raw = m.read(review_path, k.MAX_FILE); m.require(m.sha(raw)==review_sha, 'review anchor mismatch')
    mapping, parent = parent_bytes(bundle, anchor)
    files = {**{'claims/'+n:b for n,b in parent.items()}, **derive(raw, mapping, parent)}
    m.require(sum(map(len, files.values())) <= MAX_BUNDLE, 'audit bundle byte limit')
    meta = manifest(files); archive.write_tree(output, {**files, 'manifest.json':meta})
    return dict(status='audit_ready_for_review', manifest_sha256=m.sha(meta), scientific_verification=False)


def verify(bundle, anchor):
    k.digest(anchor); meta = m.read(bundle/'manifest.json', k.MAX_FILE)
    m.require(m.sha(meta)==anchor, 'audit archive anchor mismatch')
    raw = k.read_source(bundle, 'review.json'); review = knowledge.strict_json(raw)
    k.obj(review, 'schema claim_bundle_sha256 reviewer claims')
    mapping, parent = parent_bytes(bundle/'claims', review['claim_bundle_sha256'])
    files = {**{'claims/'+n:b for n,b in parent.items()}, **derive(raw, mapping, parent)}
    m.require(sum(map(len, files.values())) <= MAX_BUNDLE, 'audit bundle byte limit')
    m.require(meta==manifest(files), 'audit manifest reproduction mismatch')
    archive.exact_tree(bundle, set(files)|{'manifest.json'})
    # Parent artifacts have already passed the native claim-bundle verifier.
    for name in ('review.json','matrix.json','report.json','index.html'):
        m.require(k.read_source(bundle,name)==files[name], 'audit artifact reproduction mismatch')
    return dict(status='audit_integrity_reproduced', manifest_sha256=anchor, scientific_verification=False, accepted_as_gold=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest='action',required=True)
    for action in ('template','build','verify'):
        p=sub.add_parser(action); p.add_argument('--bundle',type=Path,required=True); p.add_argument('--sha256',required=True)
        if action!='verify':p.add_argument('--output',type=Path,required=True)
        if action=='template':p.add_argument('--reviewer',required=True)
        if action=='build':p.add_argument('--review',type=Path,required=True); p.add_argument('--review-sha256',required=True)
    a=parser.parse_args()
    try:
        if a.action=='template':
            ops.outside(a.output,a.bundle); mapping,_=parent_bytes(a.bundle,a.sha256)
            raw=m.encoded(template(mapping,a.sha256,a.reviewer)); archive.write_tree(a.output,{'review.template.json':raw})
            result=dict(status='unassessed_template_ready',review_sha256=m.sha(raw))
        elif a.action=='build':result=build(a.bundle,a.sha256,a.review,a.review_sha256,a.output)
        else:result=verify(a.bundle,a.sha256)
        print(m.encoded(result).decode(),end='');return 0
    except (ValueError,OSError,TypeError,KeyError,RecursionError) as exc:
        print(m.encoded(dict(status='rejected',reason=str(exc))).decode(),end='');return 2


if __name__=='__main__':raise SystemExit(main())
