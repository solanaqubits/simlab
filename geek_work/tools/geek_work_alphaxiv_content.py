#!/usr/bin/env python3
"""Offline saved alphaXiv content bindings, with explicit reported representation."""
import argparse
from pathlib import Path
import re
from urllib.parse import urlsplit

import geek_work_alphaxiv as discovery
import geek_work_hexagon as hexagon
import geek_work_manuscript as m
import geek_work_manuscript_claims as k
import geek_work_batch_hunks as archive
import geek_work_file_operations as ops
import knowledge

SCHEMA='geek-work-alphaxiv-content-archive-1'
FILES={'spec.json','response.raw','content.json'}
REPRESENTATIONS=('ai_report','extracted_text','unknown')


def requested_identity(url):
    k.text(url);parts=urlsplit(url)
    m.require(parts.scheme=='https' and parts.netloc in ('arxiv.org','www.alphaxiv.org') and not parts.query and not parts.fragment,'canonical paper URL')
    prefix='/pdf/' if parts.netloc=='arxiv.org' and parts.path.startswith('/pdf/') else '/abs/'
    m.require(parts.path.startswith(prefix),'paper URL path')
    ident=parts.path[len(prefix):]
    if prefix=='/pdf/' and ident.endswith('.pdf'):ident=ident[:-4]
    value=discovery.identity(ident)
    m.require(value['identity_kind']=='arxiv_syntax_only' and value['version'] is not None,'explicit versioned arXiv ID required')
    return dict(paper_id=ident,**value)


def validate(spec):
    k.obj(spec,'schema request response annotation excerpts')
    m.require(spec['schema']=='geek-work-alphaxiv-content-import-1','content spec schema')
    k.obj(spec['request'],'tool url fullText')
    m.require(spec['request']['tool']=='get_paper_content' and type(spec['request']['fullText']) is bool,'explicit get_paper_content request')
    requested_identity(spec['request']['url'])
    k.obj(spec['response'],'format state')
    m.require(spec['response']['format'] in ('text','json') and spec['response']['state'] in ('complete','partial','error','unknown'),'response format/state')
    a=spec['annotation'];k.obj(a,'representation paper_id observed_at note')
    m.require(a['representation'] in REPRESENTATIONS,'reported representation');k.text(a['note']);hexagon.utc_stamp(a['observed_at'])
    if a['paper_id'] is not None:discovery.identity(a['paper_id'])
    ids=set()
    for e in k.rows(spec['excerpts'],32):
        k.obj(e,'id text_pointer start end quote reported_page')
        k.ident(e['id']);m.require(e['id'] not in ids,'duplicate excerpt ID');ids.add(e['id'])
        ptr=e['text_pointer'];m.require(type(ptr) is str and len(ptr)<=512 and (ptr=='' or ptr.startswith('/')) and not re.search(r'~(?![01])',ptr),'RFC6901 pointer')
        m.require(spec['response']['format']=='json' or ptr=='','text response requires root pointer')
        k.text(e['quote']);m.require(type(e['start']) is int and type(e['end']) is int and 0<=e['start']<e['end'],'codepoint offsets')
        page=e['reported_page'];m.require(page is None or type(page) is int and 1<=page<=100000,'reported one-based page or null')
    return spec


def pointer(data,path):
    for segment in path[1:].split('/') if path else []:
        key=segment.replace('~1','/').replace('~0','~')
        if type(data) is list:
            m.require(re.fullmatch(r'0|[1-9][0-9]*',key) is not None and len(key)<=6,'canonical bounded array index')
            index=int(key);m.require(index<len(data),'array index missing');data=data[index]
        else:
            m.require(type(data) is dict and key in data,'JSON pointer missing');data=data[key]
    m.require(type(data) is str,'selected response value must be text')
    return data


def derive(spec_raw,raw):
    spec=validate(knowledge.strict_json(spec_raw));m.require(len(raw)<=k.MAX_FILE,'response byte limit')
    requested=requested_identity(spec['request']['url']);a=spec['annotation'];issues=[]
    if not spec['excerpts']:issues.append('no_excerpts_selected')
    if spec['response']['state']!='complete':issues.append('response_'+spec['response']['state'])
    if a['representation']=='unknown':issues.append('representation_unknown')
    elif spec['request']['fullText'] and a['representation']!='extracted_text':issues.append('requested_full_text_but_reported_ai_report')
    reported=discovery.identity(a['paper_id']) if a['paper_id'] is not None else None
    if reported is None or reported['version'] is None:issues.append('returned_version_unconfirmed')
    elif (reported['work_id'],reported['version'])!=(requested['work_id'],requested['version']):issues.append('reported_paper_or_version_mismatch')
    rows=[];parse_error=None
    try:
        data=k.utf8(raw) if spec['response']['format']=='text' else knowledge.strict_json(raw)
        # JSON framing is chosen explicitly, never guessed from body text.
        for e in spec['excerpts']:
            text=pointer(data,e['text_pointer'])
            m.require(e['end']<=len(text) and text[e['start']:e['end']]==e['quote'],'quote mismatch')
            rows.append(dict(**e,selected_text_sha256=m.sha(text.encode()),quote_sha256=m.sha(e['quote'].encode()),
                response_sha256=m.sha(raw),reported_representation=a['representation'],
                reported_paper_id=a['paper_id'],requested_paper_id=requested['paper_id'],
                offset_unit='unicode_codepoints',reported_page_base='one_based' if e['reported_page'] is not None else 'unknown',
                exact_response_quote_verified=True,pdf_page_verified=False,original_paper_quote_verified=False))
    except (ValueError,UnicodeError,RecursionError) as error:
        # Retain invalid/partial/error payload bytes, but never emit partial citation success.
        rows=[];parse_error=str(error);issues.append('response_or_citation_invalid')
    report=dict(schema='geek-work-alphaxiv-content-1',status='content_bound_review_required' if not issues else 'content_requires_resolution',
        request=spec['request'],requested_identity=requested,reported_identity=reported,
        requested_representation='extracted_text' if spec['request']['fullText'] else 'prefer_ai_report_with_text_fallback',
        reported_representation=a['representation'],annotation=a,annotation_basis='operator_declaration_not_authenticated',
        response_format=spec['response']['format'],reported_response_state=spec['response']['state'],response_sha256=m.sha(raw),
        issues=issues,parse_or_citation_error=parse_error,excerpts=rows,
        excerpts_requested=len(spec['excerpts']),excerpts_bound=len(rows),
        representation_verified=False,paper_identity_verified=False,transport_completeness_verified=False,
        full_paper_coverage_verified=False,origin_authenticated=False,trusted_timestamp=False,
        scientific_verification=False,accepted_into_knowledge_graph=False,publication_authorized=False,network_called_here=False,
        limits='Exact selected response strings only. Format/state, representation, returned ID, page numbers and time are operator annotations. A request parameter, matching identifier or SHA does not prove that text is the original paper or that its extraction is complete. No MCP connection, HTML/XML interpretation or source instruction execution.')
    encoded=m.encoded(report);m.require(len(encoded)<=k.MAX_FILE,'content projection byte limit')
    return {'spec.json':spec_raw,'response.raw':raw,'content.json':encoded},report


def manifest(files):return m.encoded(dict(schema=SCHEMA,files={n:m.sha(b) for n,b in files.items()}))


def capture(spec_path,spec_sha,response_path,response_sha,output):
    ops.outside(output,spec_path,response_path);k.digest(spec_sha);k.digest(response_sha)
    spec_raw=m.read(spec_path,k.MAX_FILE);raw=m.read(response_path,k.MAX_FILE)
    m.require(m.sha(spec_raw)==spec_sha and m.sha(raw)==response_sha,'input anchor mismatch')
    files,report=derive(spec_raw,raw);meta=manifest(files);archive.write_tree(output,{**files,'manifest.json':meta})
    return dict(status=report['status'],manifest_sha256=m.sha(meta),excerpts_bound=report['excerpts_bound'],issues=report['issues'])


def verify(bundle,anchor):
    k.digest(anchor);archive.exact_tree(bundle,FILES|{'manifest.json'})
    meta=m.read(bundle/'manifest.json',k.MAX_FILE);m.require(m.sha(meta)==anchor,'archive anchor mismatch')
    files,report=derive(k.read_source(bundle,'spec.json'),m.read(bundle/'response.raw',k.MAX_FILE))
    m.require(meta==manifest(files),'content manifest reproduction mismatch')
    m.require(k.read_source(bundle,'content.json')==files['content.json'],'content projection mismatch')
    return dict(status=report['status'],manifest_sha256=anchor,integrity_reproduced=True,excerpts_bound=report['excerpts_bound'],issues=report['issues'])


def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    c=s.add_parser('import');c.add_argument('--spec',type=Path,required=True);c.add_argument('--sha256',required=True)
    c.add_argument('--response',type=Path,required=True);c.add_argument('--response-sha256',required=True);c.add_argument('--output',type=Path,required=True)
    v=s.add_parser('verify');v.add_argument('--bundle',type=Path,required=True);v.add_argument('--sha256',required=True)
    a=p.parse_args()
    try:
        r=capture(a.spec,a.sha256,a.response,a.response_sha256,a.output) if a.action=='import' else verify(a.bundle,a.sha256)
        print(m.encoded(r).decode(),end='');return 0 if r['status']=='content_bound_review_required' else 2
    except (ValueError,OSError,TypeError,KeyError,RecursionError) as exc:
        print(m.encoded(dict(status='rejected',reason=str(exc))).decode(),end='');return 2


if __name__=='__main__':raise SystemExit(main())
