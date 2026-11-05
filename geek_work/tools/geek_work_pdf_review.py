#!/usr/bin/env python3
"""Record explicit page-by-page visual judgments against pinned PDF/PNG bytes."""
import argparse
import html
from pathlib import Path
import geek_work_pdf_pages as p

m=p.m;k=p.k;tree=p.tree
CHECKS=('legibility','clipping','formulas','tables_figures','references','page_order')
OPTIONAL={'formulas','tables_figures','references'}
CLEAN='visual_review_reported'


def template(anchor,packet):
    return dict(schema='geek-work-pdf-visual-review-1',page_packet_sha256=anchor,pdf_sha256=packet['pdf']['sha256'],
        reviewer=dict(id=None,role=None,prior_exposure=None),diagnostics=dict(status=None,note=None),
        pages=[dict(page=i,png_sha256=packet['pages'][f'{i:04}.png']['sha256'],checks={name:dict(status=None,note=None) for name in CHECKS}) for i in range(1,packet['page_count']+1)])


def assess(raw,anchor,packet):
    spec=m.load(raw);k.obj(spec,'schema page_packet_sha256 pdf_sha256 reviewer diagnostics pages')
    m.require(spec['schema']=='geek-work-pdf-visual-review-1' and spec['page_packet_sha256']==anchor and spec['pdf_sha256']==packet['pdf']['sha256'],'review PDF/packet binding')
    who=spec['reviewer'];k.obj(who,'id role prior_exposure');k.text(who['id']);k.text(who['prior_exposure'])
    m.require(type(who['role']) is str and who['role'] in {'implementer','external_reviewer'},'declared reviewer role')
    diag=spec['diagnostics'];k.obj(diag,'status note');k.text(diag['note']);m.require(diag['status'] in ('reviewed','unresolved'),'diagnostic review status')
    m.require(type(spec['pages']) is list and len(spec['pages'])==packet['page_count'],'complete page coverage required')
    seen=set();counts={x:0 for x in ('pass','fail','unknown','not_applicable')}
    for row in spec['pages']:
        k.obj(row,'page png_sha256 checks');number=row['page']
        m.require(type(number) is int and 1<=number<=packet['page_count'] and number not in seen,'unique page number');seen.add(number)
        m.require(row['png_sha256']==packet['pages'][f'{number:04}.png']['sha256'],'page PNG binding')
        k.obj(row['checks'],' '.join(CHECKS))
        for name,check in row['checks'].items():
            k.obj(check,'status note');status=check['status'];m.require(type(status) is str and status in counts,'explicit check outcome required');k.text(check['note'])
            m.require(status!='not_applicable' or name in OPTIONAL,'required check cannot be not_applicable');counts[status]+=1
    diagnostics_present=packet['diagnostics_review_required'] or packet['renderer_diagnostics_present']
    status='changes_requested' if counts['fail'] else 'visual_review_incomplete' if counts['unknown'] or diag['status']=='unresolved' else 'visual_review_reported_with_diagnostics' if diagnostics_present else CLEAN
    return dict(schema='geek-work-pdf-visual-review-report-1',status=status,page_packet_sha256=anchor,pdf_sha256=packet['pdf']['sha256'],review_sha256=m.sha(raw),
        reviewer=who,page_count=packet['page_count'],check_counts=counts,source_binding_status=packet['source_binding_status'],diagnostics_present=diagnostics_present,
        diagnostics_disposition=diag,pdf_visual_review_reported=True,pdf_visual_review_verified=False,independence_verified=False,reviewer_identity_verified=False,
        renderer_execution_independently_verified=False,pdf_conformance_verified=False,scientific_verification=False,publication_authorized=False,accepted_as_gold=False,
        limits='Recorded judgments on pinned page/PDF bytes. Reviewer role and prior exposure are self-reported. No proof that pages were inspected, no authenticated identity/independence, no science/conformance/privacy/publication approval. Diagnostic flags cannot be cleared by review text.')


def preview(spec,report):
    esc=lambda x:html.escape(str(x),quote=True)
    out='<!doctype html><html lang="en"><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src \'self\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">\n<title>PDF visual review record</title><style>body{font:16px system-ui;max-width:1000px;margin:2em auto;padding:1em}img{max-width:100%;height:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>PDF visual review record</h1>'
    out+='<p>'+esc(report['status'])+'</p><pre>'+esc(m.encoded(report).decode())+'</pre>'
    for row in sorted(spec['pages'],key=lambda x:x['page']):
        out+=f'<h2>Page {row["page"]}</h2><img alt="Recorded page image" src="page-packet/pages/{row["page"]:04}.png"><pre>'+esc(m.encoded(row['checks']).decode())+'</pre>'
    return (out+'</html>\n').encode()


def make_template(packet,anchor,output):
    p.b.release.g.pre.ops.outside(output,packet);report,_=p.verified(packet,anchor);raw=m.encoded(template(anchor,report))
    with output.open('xb') as f:f.write(raw)
    return dict(status='review_template_prepared',review_template_sha256=m.sha(raw),page_count=report['page_count'],decisions_defaulted=False)


def artifacts(raw,anchor,packet,archive):
    report=assess(raw,anchor,packet);files={'review.json':raw,'report.json':m.encoded(report),'review.html':preview(m.load(raw),report),**{'page-packet/'+n:x for n,x in archive.items()}}
    m.require(len(files['review.html'])<=m.MAX_ARTIFACT,'review preview limit');return report,files


def accept(packet,anchor,review,review_anchor,output):
    p.b.release.g.pre.ops.outside(output,packet,review);packet_report,archive=p.verified(packet,anchor);k.digest(review_anchor)
    raw=m.read(review);m.require(m.sha(raw)==review_anchor,'review SHA mismatch');report,files=artifacts(raw,anchor,packet_report,archive)
    manifest=m.encoded(dict(schema='geek-work-pdf-visual-review-manifest-1',page_packet_sha256=anchor,files={n:m.sha(x) for n,x in files.items()}))
    tree.write_tree(output,{**files,'manifest.json':manifest});return summary(report,m.sha(manifest))


def summary(report,anchor):
    return dict(status=report['status'],manifest_sha256=anchor,page_count=report['page_count'],check_counts=report['check_counts'],pdf_visual_review_reported=True,
        pdf_visual_review_verified=False,independence_verified=False,publication_authorized=False,accepted_as_gold=False)


def verified(bundle,anchor):
    k.digest(anchor);raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'review archive anchor mismatch');manifest=m.load(raw)
    k.obj(manifest,'schema page_packet_sha256 files');m.require(manifest['schema']=='geek-work-pdf-visual-review-manifest-1','review archive schema')
    packet,archive=p.verified(bundle/'page-packet',manifest['page_packet_sha256']);report,files=artifacts(m.read(bundle/'review.json'),manifest['page_packet_sha256'],packet,archive)
    tree.exact_tree(bundle,set(files)|{'manifest.json'});m.require(manifest['files']=={n:m.sha(x) for n,x in files.items()},'review archive hashes')
    for n,x in files.items():m.require(m.read(bundle/n,max(len(x),1))==x,'review reproduction mismatch')
    return report,{**files,'manifest.json':raw}


def verify(bundle,anchor):
    report,_=verified(bundle,anchor)
    return dict(**summary(report,anchor),reproduced=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    q=sub.add_parser('template');q.add_argument('--packet',type=Path,required=True);q.add_argument('--sha256',required=True);q.add_argument('--output',type=Path,required=True)
    q=sub.add_parser('accept')
    for n in ('packet','review','output'):q.add_argument('--'+n,type=Path,required=True)
    for n in ('sha256','review-sha256'):q.add_argument('--'+n,required=True)
    q=sub.add_parser('verify');q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True);a=parser.parse_args()
    if a.action=='template':result=make_template(a.packet,a.sha256,a.output)
    elif a.action=='accept':result=accept(a.packet,a.sha256,a.review,a.review_sha256,a.output)
    else:result=verify(a.bundle,a.sha256)
    print(m.encoded(result).decode(),end='')
    if result['status'] not in {CLEAN,'review_template_prepared'}:raise SystemExit(2)


if __name__=='__main__':main()
