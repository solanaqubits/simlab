#!/usr/bin/env python3
"""Read-only diagnostics for verified container page/failure archives."""
import argparse
from pathlib import Path
import re
import geek_work_pdf_container as c
import geek_work_raw_pdf_container as raw_container
import geek_work_raw_pdf_selection as selection

m=c.m;k=c.k


def operation(row,archive,*,runtime=None):
    selected=runtime;runtime=c.runtime_profile(runtime)
    folder=row['folder'];name=row['name'];receipt=m.load(archive[folder+'/receipt.json']);events=[];classes=[]
    def add(kind,phase,detail):
        if kind not in classes:classes.append(kind)
        events.append(dict(failure_class=kind,phase=phase,detail=detail))
    missing=[];evidence={};created=None;stderr_bytes=0
    if folder+'/interrupted.json' in archive:add('operator_interruption',None,'Recorded operation interruption marker')
    for phase in c.PHASES:
        prefix=folder+'/'+phase;evidence[phase]=[prefix+suffix for suffix in ('.json','.stdout','.stderr') if prefix+suffix in archive]
        stderr_bytes+=len(archive.get(prefix+'.stderr',b''))
        if prefix+'.json' not in archive:missing.append(phase);continue
        meta=m.load(archive[prefix+'.json']);code=meta['returncode'];error=meta['error_class']
        if phase=='create' and re.fullmatch(b'[0-9a-f]{64}\n',archive.get(prefix+'.stdout',b'')):created=archive[prefix+'.stdout'].strip().decode()
        if (code is not None and type(code) is not int) or type(meta['capture_overflow']) is not bool or (error is not None and type(error) is not str):
            add('capture_metadata_rejected',phase,'Recorded return/error/overflow field types are invalid');continue
        if prefix+'.stdout' not in archive or prefix+'.stderr' not in archive:
            add('incomplete_phase_capture',phase,'Recorded phase has no complete stdout/stderr pair');continue
        if meta['capture_overflow']:add('capture_overflow',phase,'Recorded bounded capture overflow')
        if error=='InterruptedError':add('operator_interruption',phase,'Recorded interrupted client call')
        elif error=='TimeoutExpired':add('client_timeout',phase,'Recorded client timeout; side effects are not inferred')
        elif error is not None:add('client_launch_or_transport_error',phase,str(error))
        if type(code) is int and code!=0:add('client_nonzero_exit',phase,'Recorded client return code '+str(code))
        if code!=0 or error is not None or meta['capture_overflow']:continue
        raw=archive.get(prefix+'.stdout',b'')
        try:
            if phase=='image':
                value=m.load(raw);m.require(len(value)==1 and value[0]['Id']==runtime['image_id'] and value[0]['Os']=='linux' and value[0]['Architecture']=='amd64','image/profile observation mismatch')
            elif phase=='create':
                m.require(bool(re.fullmatch(b'[0-9a-f]{64}\n',raw)),'create ID is not full hex');created=raw.strip().decode()
            elif phase in ('before','after'):
                value=m.load(raw);m.require(len(value)==1,'single container observation required');c.inspect_config(value[0],name,runtime=selected)
                m.require(created is None or value[0]['Id']==created,'container ID does not match recorded create')
                if phase=='after':
                    state=value[0]['State'];m.require(state['Running'] is False and type(state['ExitCode']) is int and state['ExitCode']==0 and state.get('OOMKilled') is False,'recorded container exit/OOM state rejected')
            elif phase=='start' and row['mode']=='profile':m.require(m.encoded(m.load(raw))==m.encoded(runtime['worker_observation']),'worker observation does not match reviewed profile')
            elif phase=='remove':m.require(raw.strip().decode()==name,'removal response does not match operation name')
            elif phase=='absence':m.require(not raw.strip(),'absence query returned a container ID')
        except (ValueError,KeyError,TypeError,UnicodeError) as exc:
            kind='runtime_image_rejected' if phase=='image' else 'create_identity_rejected' if phase=='create' else 'container_configuration_or_state_rejected' if phase in ('before','after') else 'worker_profile_rejected' if phase=='start' else 'cleanup_observation_rejected'
            add(kind,phase,str(exc)[:500])
    if not receipt['container_removed']:add('cleanup_unconfirmed','absence','Recorded removal was not confirmed; current live state is not checked')
    if receipt['status']!='completed' and not classes:add('incomplete_operation_journal',missing[0] if missing else None,'No stronger recorded cause; missing phases are listed separately')
    first=next((event['phase'] for event in events if event['phase'] is not None),None)
    return dict(folder=folder,container_name=name,recorded_create_id=created,mode=row['mode'],page=row['page'],recorded_status=receipt['status'],recorded_error_class=receipt['error_class'],recorded_cleanup='removed' if receipt['container_removed'] else 'unconfirmed',live_container_state='not_checked',first_problem_phase=first,failure_classes=classes,events=events,missing_phases=missing,evidence_paths=evidence,recorded_stderr_bytes=stderr_bytes)


def format_findings(descriptors,archive,source_pages=None):
    # This helper reports only deterministic checks over already verified captures.
    # It never interprets a matching PNG/container as visual or scientific validity.
    if len(descriptors)<2:return [dict(failure_class='incomplete_pipeline',detail='No complete profile/info prefix recorded')]
    try:
        stderr=b''
        for row in descriptors:
            err=b''.join(archive[row['folder']+'/'+phase+'.stderr'] for phase in c.PHASES)
            m.require(len(err)<=65536,'per-operation diagnostic aggregate limit')
            if row['mode'] in ('profile','info'):stderr+=err
        m.require(len(stderr)<=65536,'profile/info diagnostic aggregate limit')
        info=archive[descriptors[1]['folder']+'/start.stdout']
        if source_pages is None:count=c.p.page_count(info)
        else:
            total=raw_container.raw.total_pages(info);raw_container.raw.selection(source_pages[0],source_pages[-1],total);count=len(source_pages)
        m.require(len(descriptors)==count+2,'page operation coverage incomplete')
        total=0
        for row in descriptors[2:]:
            raw=archive[row['folder']+'/start.stdout'];c.p.png(raw);total+=len(raw)
        m.require(total<=c.p.MAX_IMAGES,'aggregate page image byte limit')
    except (ValueError,KeyError) as exc:return [dict(failure_class='format_bounds_or_coverage_rejected',detail=str(exc)[:500])]
    return []


def raw_format_findings(descriptors,archive):
    if len(descriptors)<2:return format_findings(descriptors,archive)
    info_path=descriptors[1]['folder']+'/start.stdout'
    try:
        count=raw_container.raw.total_pages(archive[info_path])
    except (ValueError,KeyError) as exc:
        return [dict(failure_class='raw_pdf_info_rejected',detail=str(exc)[:500],evidence_path=info_path)]
    limit=c.profile()['max_pages']
    if count>limit:
        return [dict(failure_class='document_exceeds_container_page_limit',
                     detail='Recorded complete-document page count exceeds the pinned runtime limit; no truncation or fallback was performed',
                     recorded_pdf_page_count=count,max_pages=limit,evidence_path=info_path)]
    return format_findings(descriptors,archive)


def assess(bundle,anchor):
    # Dispatch only after checking the caller's exact manifest anchor. Each branch
    # still performs its native archive verification before diagnostics are derived.
    k.digest(anchor);meta=m.read(bundle/'manifest.json');m.require(m.sha(meta)==anchor,'diagnostic source anchor mismatch')
    decoded=m.load(meta);m.require(type(decoded) is dict,'diagnostic manifest object required')
    schema=decoded.get('schema');selected_input=schema==selection.SCHEMA;raw_input=selected_input or schema==raw_container.SCHEMA
    m.require(raw_input or schema==c.SCHEMA,'unsupported diagnostic source schema')
    report,archive=(selection.verified(bundle,anchor) if selected_input else raw_container.verified(bundle,anchor) if raw_input else c.verified(bundle,anchor))
    ready_status=raw_container.raw.STATUS if raw_input else 'pages_ready_for_review'
    manifest=m.load(archive['manifest.json']);rows=[operation(row,archive,runtime=c.selection_profile() if selected_input else None) for row in manifest['operations']]
    pipeline=[]
    if report['status']!=ready_status and all(row['recorded_status']=='completed' for row in rows):pipeline=(format_findings(manifest['operations'],archive,list(range(manifest['first_page'],manifest['last_page']+1))) if selected_input else (raw_format_findings if raw_input else format_findings)(manifest['operations'],archive))
    classes=[]
    for kind in [kind for row in rows for kind in row['failure_classes']]+[row['failure_class'] for row in pipeline]:
        if kind not in classes:classes.append(kind)
    cleanup=all(row['recorded_cleanup']=='removed' for row in rows) if rows else None
    unconfirmed=any(row['recorded_cleanup']=='unconfirmed' for row in rows)
    warnings=any(row['recorded_stderr_bytes'] for row in rows) or bool(report.get('diagnostics_review_required'))
    attention=report['status']!=ready_status or warnings
    action='inspect_recorded_container_on_trusted_host' if unconfirmed else 'review_interruption_before_retry' if 'operator_interruption' in classes else 'inspect_recorded_failure_evidence' if report['status']!=ready_status else 'review_recorded_diagnostics' if warnings else 'no_recorded_failure'
    result=dict(schema='geek-work-pdf-container-diagnostics-1',status='diagnostics_require_attention' if attention else 'diagnostics_recorded',source_archive_sha256=anchor,source_archive_status=report['status'],pdf=report['pdf'],operations=rows,pipeline_findings=pipeline,failure_classes=classes,all_recorded_removals_confirmed=cleanup,cleanup_observation_count=len(rows),live_container_state='not_checked',recorded_container_stderr_present=any(row['recorded_stderr_bytes'] for row in rows),source_compile_diagnostics_review_required=report.get('diagnostics_review_required'),next_action=action,renderer_execution_independently_verified=False,pdf_conformance_verified=False,scientific_verification=False,publication_authorized=False,
                limits='Derived only from verified recorded bytes. No Docker command, current image/container query, cleanup or retry. A recorded timeout does not establish whether creation happened; recorded removal is not current live absence. Parent archive/status is unchanged. A clean diagnostic report is not visual/scientific/publication qualification.')

    if raw_input:
        result.update(schema='geek-work-raw-pdf-container-diagnostics-1',
                      source_archive_kind='original_pdf_bytes',compile_binding_verified=False,
                      source_pdf_pages=report.get('source_pdf_pages'),
                      full_document_coverage=report.get('full_document_coverage'))
        if selected_input:
            result['schema']='geek-work-raw-pdf-selection-diagnostics-1'
            result['requested_source_pages']=list(range(manifest['first_page'],manifest['last_page']+1))
        result['raw_renderer_diagnostics_review_required']=result.pop('source_compile_diagnostics_review_required')
        if not unconfirmed and 'document_exceeds_container_page_limit' in classes:
            result['next_action']='review_document_page_limit_before_new_render'
        result['limits']+=' Original PDF archive: no manuscript compile binding. Page-count findings are recorded pdfinfo observations, not an independent PDF parser. No renderer selection, split or native fallback is performed.'
    return result


def check(bundle,anchor,output):
    c.p.b.release.g.pre.ops.outside(output,bundle);report=assess(bundle,anchor);raw=m.encoded(report);m.require(len(raw)<=m.MAX_ARTIFACT,'diagnostic report limit')
    with output.open('xb') as f:f.write(raw)
    return dict(status=report['status'],report_sha256=m.sha(raw),source_archive_status=report['source_archive_status'],failure_classes=report['failure_classes'],next_action=report['next_action'],live_container_state='not_checked')


def verify_report(bundle,anchor,report_path,report_anchor):
    k.digest(report_anchor);raw=m.read(report_path);m.require(m.sha(raw)==report_anchor,'diagnostic report anchor mismatch');report=assess(bundle,anchor);m.require(raw==m.encoded(report),'diagnostic report reproduction mismatch')
    return dict(status=report['status'],report_sha256=report_anchor,source_archive_status=report['source_archive_status'],failure_classes=report['failure_classes'],next_action=report['next_action'],live_container_state='not_checked',reproduced=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    for action in ('check','verify-report'):
        q=sub.add_parser(action);q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True)
        if action=='check':q.add_argument('--output',type=Path,required=True)
        else:q.add_argument('--report',type=Path,required=True);q.add_argument('--report-sha256',required=True)
    args=parser.parse_args();result=check(args.bundle,args.sha256,args.output) if args.action=='check' else verify_report(args.bundle,args.sha256,args.report,args.report_sha256)
    print(m.encoded(result).decode(),end='')
    if result['status']=='diagnostics_require_attention':raise SystemExit(2)


if __name__=='__main__':main()
