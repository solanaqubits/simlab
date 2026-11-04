#!/usr/bin/env python3
"""Check an explicitly pinned manuscript chain and report its next unresolved step."""
import argparse
import os
from pathlib import Path
import geek_work_manuscript_release as source
import geek_work_release_compile as compile_stage
import geek_work_pdf_pages as pages
import geek_work_pdf_review as review
import geek_work_typst_preflight as typst_preflight
import geek_work_typst_gate as typst_gate

m=source.m;k=source.k
STAGES=('source','compile_binding','page_packet','visual_review')
CLEAR='local_chain_consistent_review_reported'


def plan(raw):
    spec=m.load(raw);m.require(type(spec) is dict,'status plan object');v2=spec.get('schema')=='geek-work-manuscript-status-plan-2'
    k.obj(spec,'schema '+' '.join(STAGES)+(' engine' if v2 else ''));m.require(spec['schema'] in {'geek-work-manuscript-status-plan-1','geek-work-manuscript-status-plan-2'},'status plan schema')
    if v2:m.require(spec['engine'] in ('latex','typst'),'explicit supported engine')
    for name in STAGES:
        ref=spec[name]
        if ref is None:m.require(name!='source','source package required');continue
        k.obj(ref,'path sha256');k.path_name(ref['path']);k.digest(ref['sha256'])
    m.require(spec['page_packet'] is None or spec['compile_binding'] is not None,'page packet requires compile binding')
    m.require(spec['visual_review'] is None or spec['page_packet'] is not None,'visual review requires page packet')
    return spec


def folder(root,name):
    parts=k.path_name(name).parts;fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in parts:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=child
    except OSError as error:raise ValueError('regular stage directory required: '+name) from error
    finally:os.close(fd)
    return root.joinpath(*parts)


def assess(root,raw):
    spec=plan(raw);reports={};paths={};typst=spec.get('engine','latex')=='typst'
    functions={'source':source.verify_public,'compile_binding':lambda *a:compile_stage.verified_binding(*a)[0],
               'page_packet':lambda *a:pages.verified(*a)[0],'visual_review':lambda *a:review.verified(*a)[0]}
    if typst:
        functions.update(source=lambda *a:typst_preflight.verified(*a)[0],compile_binding=lambda *a:typst_gate.verified(*a)[0])
    for name in STAGES:
        ref=spec[name]
        if ref is not None:
            paths[name]=folder(root,ref['path']);reports[name]=functions[name](paths[name],ref['sha256'])
    c=reports.get('compile_binding');p=reports.get('page_packet');r=reports.get('visual_review')
    if c:m.require(c['preflight_sha256' if typst else 'source_package_sha256']==spec['source']['sha256'],'CHAIN_MISMATCH: compile/source')
    if p:
        m.require(p['binding_sha256']==spec['compile_binding']['sha256'],'CHAIN_MISMATCH: page/compile')
        m.require(p['pdf']==c['pdf'],'CHAIN_MISMATCH: page/PDF')
    if r:
        m.require(r['page_packet_sha256']==spec['page_packet']['sha256'],'CHAIN_MISMATCH: review/page')
        m.require(r['pdf_sha256']==p['pdf']['sha256'],'CHAIN_MISMATCH: review/PDF')
    blockers=[]
    if typst and reports['source']['status']=='review_required':blockers.append('source_preflight_findings')
    if c is None:blockers.append('missing_compile_binding')
    elif c['status'] in {'source_bound_failure_archive','preflight_bound_typst_failure_archive'}:blockers.append('compile_failure')
    elif c['status'] in {'source_bound_compile_needs_review','preflight_bound_typst_compile_needs_review'}:blockers.append('compile_diagnostics')
    if p is None:blockers.append('missing_page_packet')
    elif p['renderer_diagnostics_present']:blockers.append('renderer_diagnostics')
    if r is None:blockers.append('missing_visual_review')
    elif r['status']=='changes_requested':blockers.append('visual_changes_requested')
    elif r['status']=='visual_review_incomplete':blockers.append('visual_review_incomplete')
    elif r['status']=='visual_review_reported_with_diagnostics':blockers.append('review_diagnostics')
    if 'source_preflight_findings' in blockers:action='address_preflight_findings'
    elif c is None:action='run_typst_preflight_gate' if typst else 'prepare_compile_request_and_bind_result'
    elif c['status'] in {'source_bound_failure_archive','preflight_bound_typst_failure_archive'}:action='address_compile_failure'
    elif r and r['status']=='changes_requested':action='address_visual_changes'
    elif r and r['status']=='visual_review_incomplete':action='complete_visual_review'
    elif c['status'] in {'source_bound_compile_needs_review','preflight_bound_typst_compile_needs_review'}:action='resolve_compile_diagnostics'
    elif p is None:action='render_page_packet'
    elif r is None:action='record_visual_review'
    elif blockers:action='resolve_recorded_diagnostics'
    else:action='obtain_independent_visual_privacy_rights_review'
    stage_results={name:None if spec[name] is None else dict(**spec[name],status=reports[name]['status']) for name in STAGES}
    result=dict(schema='geek-work-manuscript-status-report-1',status=CLEAR if not blockers else 'needs_work',plan_sha256=m.sha(raw),
        stages=stage_results,all_stages_present=len(reports)==len(STAGES),chain_links_consistent=True,blockers=blockers,next_action=action,
        source_files=len(reports['source']['files']) if typst else reports['source']['files'],pdf=None if c is None else c['pdf'],
        review_check_counts=None if r is None else r['check_counts'],
        external_obligations=['independent_visual_review','substantive_privacy_review','rights_review','pdf_conformance_and_safety','scientific_correspondence','explicit_publication_decision'],
        independence_verified=False,privacy_verified=False,pdf_conformance_verified=False,scientific_verification=False,publication_authorized=False,
        limits='Explicit anchored stages and their relationships checked here. No stage discovery or execution, no atomic observation of concurrent writers, no authenticated reviewer or historical execution. A clear local reported-review chain is not publication approval.')
    if spec['schema']=='geek-work-manuscript-status-plan-2':result.update(schema='geek-work-manuscript-status-report-2',engine=spec['engine'],source_kind='typst_preflight' if typst else 'public_source_package')
    return result,paths


def check(root,plan_path,anchor,output):
    k.digest(anchor);raw=m.read(plan_path);m.require(m.sha(raw)==anchor,'plan SHA mismatch');result,paths=assess(root,raw)
    source.g.pre.ops.outside(output,plan_path,*paths.values());data=m.encoded(result)
    with output.open('xb') as f:f.write(data)
    return dict(status=result['status'],report_sha256=m.sha(data),next_action=result['next_action'],blockers=result['blockers'],publication_authorized=False)


def verify_report(root,plan_path,plan_anchor,report_path,report_anchor):
    k.digest(plan_anchor);k.digest(report_anchor);raw=m.read(plan_path);m.require(m.sha(raw)==plan_anchor,'plan SHA mismatch')
    recorded=m.read(report_path);m.require(m.sha(recorded)==report_anchor,'report SHA mismatch');result,_=assess(root,raw)
    m.require(recorded==m.encoded(result),'status report reproduction mismatch')
    return dict(status=result['status'],report_sha256=report_anchor,next_action=result['next_action'],reproduced=True,publication_authorized=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    for action in ('check','verify-report'):
        q=sub.add_parser(action)
        for n in ('root','plan'):q.add_argument('--'+n,type=Path,required=True)
        q.add_argument('--plan-sha256',required=True)
        if action=='check':q.add_argument('--output',type=Path,required=True)
        else:q.add_argument('--report',type=Path,required=True);q.add_argument('--report-sha256',required=True)
    a=parser.parse_args()
    result=check(a.root,a.plan,a.plan_sha256,a.output) if a.action=='check' else verify_report(a.root,a.plan,a.plan_sha256,a.report,a.report_sha256)
    print(m.encoded(result).decode(),end='')
    if result['status']!=CLEAR:raise SystemExit(2)


if __name__=='__main__':main()
