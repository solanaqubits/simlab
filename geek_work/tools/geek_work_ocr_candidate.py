#!/usr/bin/env python3
"""Capture untrusted OCR candidates bound to an existing verified page packet."""
import argparse
from pathlib import Path
import re
import geek_work_pdf_pages as pages

m=pages.m;k=pages.k;tree=pages.tree
FIELDS='schema model_id model_revision runtime_id prompt_sha256 finish_reason input_tokens output_tokens cost_usd postprocess_id postprocess_revision'
STATUS='ocr_candidate_review_required'


def template():return dict(schema='geek-work-ocr-provenance-1',**{name:None for name in FIELDS.split()[1:]})


def provenance(value):
    k.obj(value,FIELDS);m.require(value['schema']=='geek-work-ocr-provenance-1','OCR provenance schema')
    for key in ('model_id','runtime_id','finish_reason','postprocess_id'):
        if value[key] is not None:k.text(value[key])
    for key in ('model_revision','postprocess_revision'):
        if value[key] is not None:m.require(type(value[key]) is str and bool(re.fullmatch('[0-9a-f]{40}',value[key])),'revision syntax only: '+key)
    if value['prompt_sha256'] is not None:k.digest(value['prompt_sha256'])
    for key in ('input_tokens','output_tokens'):
        m.require(value[key] is None or type(value[key]) is int and 0<=value[key]<=10**12,'declared token count or null: '+key)
    cost=value['cost_usd'];m.require(cost is None or type(cost) is str and len(cost)<=50 and bool(re.fullmatch(r'(0|[1-9][0-9]*)(\.[0-9]+)?',cost)),'declared decimal cost or null')
    return value


def artifacts(packet,anchor,page,raw,meta_raw,processed=None):
    m.require(type(page) is int and 1<=page<=packet['page_count'],'selected page number');m.source(raw)
    if processed is not None:m.source(processed)
    meta=provenance(m.load(meta_raw));flags=['untrusted_model_output','transcription_not_verified','reading_order_not_verified','formula_numeric_fidelity_not_verified','table_structure_not_verified']
    if not raw:flags.append('empty_raw_output')
    reason=meta['finish_reason']
    if reason is None:flags.append('finish_reason_unknown')
    elif reason in {'length','max_tokens','max_output_tokens'}:flags.append('reported_truncation')
    elif reason=='error':flags.append('reported_generation_error')
    elif reason!='stop':flags.append('unrecognized_finish_reason')
    for key in ('model_id','model_revision','runtime_id','prompt_sha256'):
        if meta[key] is None:flags.append(key+'_unknown')
    if processed is not None:
        if processed!=raw:flags.append('postprocessing_changed_bytes')
        if meta['postprocess_id'] is None:flags.append('postprocessing_identity_unknown')
    elif meta['postprocess_id'] is not None:flags.append('postprocessed_output_not_supplied')
    if packet['renderer_diagnostics_present'] or packet['diagnostics_review_required']:flags.append('source_page_diagnostics_require_review')
    result=dict(schema='geek-work-ocr-candidate-report-1',status=STATUS,source_packet_sha256=anchor,page=page,pdf=packet['pdf'],page_png=packet['pages'][f'{page:04}.png'],raw_sha256=m.sha(raw),raw_bytes=len(raw),postprocessed_sha256=None if processed is None else m.sha(processed),postprocessed_bytes=None if processed is None else len(processed),raw_equals_postprocessed=None if processed is None else raw==processed,provenance_sha256=m.sha(meta_raw),declared_provenance=meta,review_flags=flags,model_called_here=False,model_revision_exists_verified=False,provenance_authenticated=False,token_cost_telemetry_verified=False,source_pixels_decoded_here=False,model_input_preprocessing_verified=False,content_verified=False,completeness_verified=False,scientific_verification=False,publication_authorized=False,
                limits='Exact untrusted OCR bytes, not accepted knowledge. No inference/server/network, prompt execution, HTML rendering or cleanup. Declared model/revision/usage/cost are self-reported; unknown metrics stay null. stop does not prove completeness; revision hex does not prove existence. Parent packet is required separately for full verification, avoiding duplicate source archives. Whole-page candidates only; raw-chat PDF bridge and region/crop provenance remain separate stages.')

    if packet.get('source_kind')=='original_pdf_bytes':
        result.update(source_packet_kind='original_pdf_bytes',source_pdf_page=packet['source_pdf_pages'][page-1],source_full_document_coverage=packet['full_document_coverage'],compile_binding_verified=False)
        result['review_flags'].append('source_pdf_no_compile_binding')
        result['limits']=result['limits'].replace('raw-chat PDF bridge and region/crop provenance remain separate stages.','source PDF page selection is explicit; region/crop provenance remains a separate stage.')
    return result


def source(packet,anchor,page):
    raw=m.read(packet/'manifest.json');k.digest(anchor);m.require(m.sha(raw)==anchor,'page packet anchor mismatch')
    if m.load(raw).get('schema')=='geek-work-raw-pdf-selection-manifest-1':
        import geek_work_raw_pdf_selection as selection
        report,archive=selection.verified(packet,anchor,require_pages=True)
    elif m.load(raw).get('schema')=='geek-work-raw-pdf-container-manifest-1':
        import geek_work_raw_pdf_container as raw_container
        report,archive=raw_container.verified(packet,anchor,require_pages=True)
    elif m.load(raw).get('schema')=='geek-work-raw-pdf-pages-manifest-1':
        import geek_work_raw_pdf_pages as raw_pdf
        report,archive=raw_pdf.verified(packet,anchor)
    else:report,archive=pages.verified(packet,anchor)
    m.require(type(page) is int and 1<=page<=report['page_count'],'selected page number')
    return report,archive[f'pages/{page:04}.png']


def capture(packet,anchor,page,raw_path,raw_anchor,meta_path,meta_anchor,output,processed_path=None,processed_anchor=None):
    pages.b.release.g.pre.ops.outside(output,packet,raw_path,meta_path,*([processed_path] if processed_path is not None else []));m.require(not output.exists() and not output.is_symlink(),'new OCR candidate required')
    m.require((processed_path is None)==(processed_anchor is None),'postprocessed path/SHA pair required');k.digest(raw_anchor);k.digest(meta_anchor)
    raw=m.read(raw_path);meta=m.read(meta_path);m.require(m.sha(raw)==raw_anchor and m.sha(meta)==meta_anchor,'OCR input anchor mismatch');processed=None
    if processed_path is not None:k.digest(processed_anchor);processed=m.read(processed_path);m.require(m.sha(processed)==processed_anchor,'postprocessed anchor mismatch')
    parent,png=source(packet,anchor,page);report=artifacts(parent,anchor,page,raw,meta,processed)
    files={'raw.txt':raw,'provenance.json':meta,'page.png':png,'report.json':m.encoded(report)}
    if processed is not None:files['postprocessed.txt']=processed
    m.require(len(files['report.json'])<=m.MAX_ARTIFACT,'OCR report limit')
    manifest=m.encoded(dict(schema='geek-work-ocr-candidate-manifest-1',source_packet_sha256=anchor,page=page,postprocessed_present=processed is not None,files={name:m.sha(data) for name,data in files.items()}));tree.write_tree(output,{**files,'manifest.json':manifest})
    return dict(status=STATUS,manifest_sha256=m.sha(manifest),review_flags=report['review_flags'],model_called_here=False)


def verify(packet,packet_anchor,bundle,anchor):
    k.digest(anchor);raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'OCR candidate anchor mismatch');manifest=m.load(raw);k.obj(manifest,'schema source_packet_sha256 page postprocessed_present files');m.require(manifest['schema']=='geek-work-ocr-candidate-manifest-1' and manifest['source_packet_sha256']==packet_anchor,'OCR source packet binding');m.require(type(manifest['postprocessed_present']) is bool,'postprocessed presence flag')
    parent,png=source(packet,packet_anchor,manifest['page']);text=m.read(bundle/'raw.txt');meta=m.read(bundle/'provenance.json');processed=m.read(bundle/'postprocessed.txt') if manifest['postprocessed_present'] else None
    report=artifacts(parent,packet_anchor,manifest['page'],text,meta,processed);files={'raw.txt':text,'provenance.json':meta,'page.png':png,'report.json':m.encoded(report)}
    if processed is not None:files['postprocessed.txt']=processed
    m.require(len(files['report.json'])<=m.MAX_ARTIFACT,'OCR report limit');tree.exact_tree(bundle,set(files)|{'manifest.json'});m.require(manifest['files']=={name:m.sha(data) for name,data in files.items()},'OCR candidate hashes')
    for name,data in files.items():m.require(m.read(bundle/name,max(len(data),1))==data,'OCR candidate reproduction mismatch')
    return dict(status=STATUS,manifest_sha256=anchor,review_flags=report['review_flags'],model_called_here=False,integrity_reproduced=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True);q=sub.add_parser('provenance-template');q.add_argument('--output',type=Path,required=True)
    for action in ('capture','verify'):
        q=sub.add_parser(action);q.add_argument('--packet',type=Path,required=True);q.add_argument('--packet-sha256',required=True)
        if action=='capture':
            q.add_argument('--page',type=int,required=True)
            for name in ('raw','provenance','output'):q.add_argument('--'+name,type=Path,required=True)
            for name in ('raw-sha256','provenance-sha256'):q.add_argument('--'+name,required=True)
            q.add_argument('--postprocessed',type=Path);q.add_argument('--postprocessed-sha256')
        else:q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True)
    args=parser.parse_args()
    if args.action=='provenance-template':
        raw=m.encoded(template())
        with args.output.open('xb') as f:f.write(raw)
        result=dict(status='provenance_template_created',sha256=m.sha(raw),model_called_here=False)
    elif args.action=='capture':result=capture(args.packet,args.packet_sha256,args.page,args.raw,args.raw_sha256,args.provenance,args.provenance_sha256,args.output,args.postprocessed,args.postprocessed_sha256)
    else:result=verify(args.packet,args.packet_sha256,args.bundle,args.sha256)
    print(m.encoded(result).decode(),end='')
    if result['status']==STATUS:raise SystemExit(2)


if __name__=='__main__':main()
