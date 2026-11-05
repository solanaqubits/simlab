#!/usr/bin/env python3
"""Bounded alphaXiv discovery intake, including failed responses and offline replay."""
import argparse
from datetime import date, datetime, timezone
import http.client
import json
from pathlib import Path
import re
import socket
from urllib.parse import urlencode, quote

import knowledge as k
import geek_work_manuscript as m
import geek_work_batch_hunks as tree
import geek_work_hexagon as hexagon

HOST = 'api.alphaxiv.org'
MAX_BYTES = 1024 * 1024
MAX_RECORDS = 100
FILES = {'request.json', 'response.raw', 'capture.json', 'records.json'}
ERRORS = (None, 'timeout', 'connection_error', 'incomplete_body', 'response_limit', 'invalid_headers')


def text(value, limit, empty=False):
    m.require(type(value) is str and len(value.encode('utf-8')) <= limit and
              (empty or bool(value.strip())), 'bounded UTF-8 text required')
    return value


def request_spec(strategy, query, prioritize='default', after=None, before=None, max_records=100):
    spec = dict(schema='geek-work-alphaxiv-request-1', strategy=strategy, query=query,
                prioritize=prioritize, published_after=after, published_before=before,
                max_records=max_records)
    validate_request(spec)
    return spec


def validate_request(spec):
    k.obj(spec, {'schema','strategy','query','prioritize','published_after','published_before','max_records'})
    m.require(spec['schema'] == 'geek-work-alphaxiv-request-1', 'request schema')
    m.require(spec['strategy'] in ('keyword', 'embedding'), 'discovery strategy')
    text(spec['query'], 256)
    m.require(not any(ord(c) < 32 or ord(c) == 127 for c in spec['query']), 'query controls forbidden')
    m.require(spec['prioritize'] in ('default','recency','historical','popular'), 'ranking mode')
    for name in ('published_after','published_before'):
        value = spec[name]
        if value is not None:
            m.require(type(value) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value), 'ISO date required')
            date.fromisoformat(value)
    m.require(not (spec['published_after'] and spec['published_before']) or
              spec['published_after'] <= spec['published_before'], 'date window order')
    m.require(type(spec['max_records']) is int and 1 <= spec['max_records'] <= MAX_RECORDS, 'local record bound')
    return spec


def request_url(spec):
    validate_request(spec)
    params = {'q':spec['query'], 'prioritize':spec['prioritize']}
    for field, name in [('published_after','publishedAfter'),('published_before','publishedBefore')]:
        if spec[field] is not None: params[name] = spec[field]
    # max_records is a local refusal bound, NOT an undocumented server limit.
    return 'https://' + HOST + '/search/v2/paper/discover/' + spec['strategy'] + '?' + urlencode(params)


def identity(ident):
    text(ident, 256)
    m.require(not any(ord(c) < 32 or ord(c) == 127 for c in ident), 'identifier controls')
    found = re.fullmatch(r'(\d{4}\.\d{4,5}|[a-z][a-z0-9.-]+/\d{7})(?:v([1-9]\d{0,5}))?', ident)
    return dict(work_id=found[1] if found else None,
                version=int(found[2]) if found and found[2] else None,
                version_state='explicit_in_id' if found and found[2] else 'unknown',
                identity_kind='arxiv_syntax_only' if found else 'opaque_alphaxiv_id')


def parse(raw, spec):
    data = k.strict_json(raw)
    m.require(type(data) is list and len(data) <= spec['max_records'], 'response array/record bound')
    rows = []; groups = {}
    for index, item in enumerate(data):
        m.require(type(item) is dict, 'paper object')
        ident = item.get('paperId'); ids = identity(ident)
        title = text(item.get('title'), 4000)
        abstract = item.get('abstract')
        if abstract is not None: text(abstract, 64000, True)
        published = item.get('publicationDate')
        if published is not None: text(published, 100)
        votes = item.get('votes')
        m.require(votes is None or type(votes) is int and abs(votes) <= 10**12, 'reported votes')
        snippets = item.get('snippets', [])
        m.require(type(snippets) is list and len(snippets) <= 32, 'snippet bound')
        excerpts = []
        for j, snippet in enumerate(snippets):
            m.require(type(snippet) is dict, 'snippet object')
            value = text(snippet.get('snippet'), 32000, True); page = snippet.get('pageNumber')
            m.require(page is None or type(page) is int and 0 <= page <= 100000, 'reported page number')
            excerpts.append(dict(text=value, text_sha256=m.sha(value.encode()),
                source_json_pointer=f'/{index}/snippets/{j}/snippet',
                codepoint_range=dict(start=0,end=len(value)), reported_page_number=page,
                page_number_base='not_established', verified_against_full_text=False))
        rows.append(dict(response_index=index, paper_id=ident, **ids,
            record_url='https://www.alphaxiv.org/abs/'+quote(ident,safe=''), title=title,
            abstract=abstract, reported_publication_date=published, reported_votes=votes,
            snippets=excerpts, source_json_pointer=f'/{index}',
            canonical_record_sha256=m.sha(m.encoded(item)), verification_status='unreviewed',
            full_text_captured=False, peer_review_verified=False, accepted_into_knowledge_graph=False))
        groups.setdefault(ident, []).append(index)
    return rows, [dict(paper_id=i,response_indices=v) for i,v in sorted(groups.items()) if len(v)>1]


def capture_metadata(spec, method, observed_at, status, content_type, encoding, complete, error, content_length=None):
    m.require(method in ('local-snapshot','https-get'), 'capture method')
    hexagon.utc_stamp(observed_at)
    m.require(status is None or type(status) is int and 100 <= status <= 599, 'HTTP status')
    for value in (content_type, encoding):
        if value is not None: text(value, 256, True)
    m.require(content_length is None or type(content_length) is int and 0 <= content_length <= 10**12, 'reported content length')
    m.require(type(complete) is bool and error in ERRORS, 'transport fields')
    m.require((error is None) == complete, 'transport completeness/error mismatch')
    m.require(not complete or status is not None, 'complete HTTP response requires status')
    return dict(schema='geek-work-alphaxiv-capture-1', url=request_url(spec), method=method,
                observed_at=observed_at, http_status=status, content_type=content_type,
                content_encoding=encoding, response_complete=complete, transport_error=error, reported_content_length=content_length,
                origin_authenticated_by_replay=False, trusted_timestamp=False)


def project(raw, spec, capture):
    status = 'records_captured'; reason = None; rows = []; duplicates = []
    if not capture['response_complete']: status = 'transport_failure'; reason = capture['transport_error']
    elif capture['reported_content_length'] is not None and capture['reported_content_length'] != len(raw):
        status = 'transport_failure'; reason = 'content_length_mismatch'
    elif capture['http_status'] != 200: status = 'http_failure'; reason = 'http_status:'+str(capture['http_status'])
    elif (capture['content_type'] or '').split(';')[0].strip().lower() != 'application/json':
        status = 'unsupported_response'; reason = 'content_type'
    elif capture['content_encoding'] not in (None,'identity'):
        status = 'unsupported_response'; reason = 'content_encoding'
    else:
        try:
            m.require(len(raw) <= MAX_BYTES, 'response byte bound')
            rows, duplicates = parse(raw, spec)
        except (ValueError, UnicodeError, RecursionError):
            status = 'invalid_response'; reason = 'response_contract_failed'
    return dict(schema='geek-work-alphaxiv-records-1', status=status, reason=reason,
                response_sha256=m.sha(raw), records=rows, duplicate_id_groups=duplicates,
                complete_catalog=False, empty_result_means_no_literature=False,
                accepted_into_knowledge_graph=False, scientific_verification=False)


def save(request_raw, raw, capture, output):
    spec = validate_request(k.strict_json(request_raw)); output = Path(output)
    m.require(not output.exists() and not output.is_symlink(), 'new snapshot directory required')
    m.require(type(raw) is bytes and len(raw) <= MAX_BYTES+1, 'bounded raw response')
    metadata = capture_metadata(spec, *[capture[key] for key in
        ('method','observed_at','http_status','content_type','content_encoding','response_complete','transport_error','reported_content_length')])
    m.require(capture == metadata, 'capture metadata mismatch')
    report = project(raw, spec, metadata)
    files = {'request.json':request_raw,'response.raw':raw,'capture.json':m.encoded(metadata),
             'records.json':m.encoded(report)}
    m.require(len(files['records.json']) <= 4 * MAX_BYTES, 'projection byte bound')
    manifest = m.encoded(dict(schema='geek-work-alphaxiv-archive-1',files={n:m.sha(b) for n,b in files.items()}))
    tree.write_tree(output, {**files,'manifest.json':manifest})
    return dict(status=report['status'], manifest_sha256=m.sha(manifest), records=len(report['records']))


def verify(bundle, anchor):
    m.require(type(anchor) is str and re.fullmatch('[0-9a-f]{64}',anchor), 'full manifest SHA')
    bundle = Path(bundle); tree.exact_tree(bundle,FILES|{'manifest.json'})
    encoded = m.read(bundle/'manifest.json',16384);m.require(m.sha(encoded)==anchor,'manifest anchor mismatch')
    manifest = k.strict_json(encoded)
    files = {name:m.read(bundle/name,4*MAX_BYTES if name=='records.json' else MAX_BYTES+1) for name in FILES}
    expected = dict(schema='geek-work-alphaxiv-archive-1',files={n:m.sha(b) for n,b in files.items()})
    m.require(encoded == m.encoded(expected),'manifest reproduction mismatch')
    spec = validate_request(k.strict_json(files['request.json'])); capture=k.strict_json(files['capture.json'])
    m.require(type(capture) is dict,'capture object')
    metadata=capture_metadata(spec,*[capture.get(key) for key in
        ('method','observed_at','http_status','content_type','content_encoding','response_complete','transport_error','reported_content_length')])
    m.require(files['capture.json']==m.encoded(metadata),'capture reproduction mismatch')
    report=project(files['response.raw'],spec,metadata)
    m.require(files['records.json']==m.encoded(report),'records reproduction mismatch')
    return dict(status=report['status'],manifest_sha256=anchor,integrity_reproduced=True,records=len(report['records']),origin_authenticated=False)



def compare(previous, previous_anchor, bundle, anchor):
    for path, expected in ((previous, previous_anchor), (bundle, anchor)):
        result = verify(path, expected)
        m.require(result['status'] == 'records_captured', 'comparison requires two successful captures')
    def grouped(path):
        report = k.strict_json(m.read(Path(path)/'records.json', 4*MAX_BYTES))
        groups = {}
        for row in report['records']:
            groups.setdefault(row['paper_id'], []).append(row['canonical_record_sha256'])
        return {key:sorted(value) for key,value in groups.items()}
    old, new = grouped(previous), grouped(bundle)
    return dict(schema='geek-work-alphaxiv-diff-1', status='snapshots_compared',
                previous_manifest_sha256=previous_anchor, manifest_sha256=anchor,
                added_identifiers=sorted(new.keys()-old.keys()),
                absent_from_new_snapshot=sorted(old.keys()-new.keys()),
                changed_same_identifier=sorted(key for key in old.keys() & new.keys() if old[key]!=new[key]),
                absence_means_withdrawal=False, comparison_proves_revision_order=False,
                accepted_into_knowledge_graph=False)


def fetch(spec):
    url=request_url(spec); body=bytearray(); status=ctype=encoding=length=None; error=None
    connection=http.client.HTTPSConnection(HOST,timeout=20)
    try:
        connection.request('GET',url.split(HOST,1)[1],headers={
            'User-Agent':'GeekWork-LiteratureIntake/1','Accept':'application/json','Accept-Encoding':'identity'})
        response=connection.getresponse();status=response.status
        ctype=response.getheader('Content-Type');encoding=response.getheader('Content-Encoding')
        declared=response.getheader('Content-Length')
        if declared is not None:
            if re.fullmatch(r'[0-9]{1,12}',declared):length=int(declared)
            else:error='invalid_headers'
        if (ctype is not None and len(ctype.encode())>256) or (encoding is not None and len(encoding.encode())>256):
            ctype=(ctype or '')[:128];encoding=(encoding or '')[:128];error='invalid_headers'
        while len(body)<=MAX_BYTES:
            part=response.read(min(65536,MAX_BYTES+1-len(body)))
            if not part:break
            body.extend(part)
        if len(body)>MAX_BYTES:error='response_limit'
        elif error is None and length is not None and length != len(body):error='incomplete_body'
    except (TimeoutError,socket.timeout):error='timeout'
    except http.client.IncompleteRead as exc:
        body.extend(exc.partial[:MAX_BYTES+1-len(body)]);error='incomplete_body'
    except (OSError,http.client.HTTPException):error='connection_error'
    finally:connection.close()
    metadata=capture_metadata(spec,'https-get',datetime.now(timezone.utc).isoformat(),status,ctype,encoding,error is None,error,length)
    return bytes(body),metadata


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    q=sub.add_parser('query');q.add_argument('--strategy',choices=['keyword','embedding'],required=True)
    q.add_argument('--query',required=True);q.add_argument('--prioritize',default='default',choices=['default','recency','historical','popular'])
    q.add_argument('--published-after');q.add_argument('--published-before');q.add_argument('--max-records',type=int,default=100);q.add_argument('--output',type=Path,required=True)
    for action in ('fetch','import'):
        s=sub.add_parser(action);s.add_argument('--request',type=Path,required=True);s.add_argument('--sha256',required=True);s.add_argument('--output',type=Path,required=True)
        if action=='import':
            s.add_argument('--input',type=Path,required=True);s.add_argument('--response-sha256',required=True)
            s.add_argument('--observed-at',required=True);s.add_argument('--http-status',type=int,required=True)
            s.add_argument('--content-type',default='application/json');s.add_argument('--content-encoding',default='identity')
    v=sub.add_parser('verify');v.add_argument('--bundle',type=Path,required=True);v.add_argument('--sha256',required=True)
    d=sub.add_parser('diff');d.add_argument('--previous',type=Path,required=True);d.add_argument('--previous-sha256',required=True)
    d.add_argument('--bundle',type=Path,required=True);d.add_argument('--sha256',required=True);d.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        if a.action=='query':
            spec=request_spec(a.strategy,a.query,a.prioritize,a.published_after,a.published_before,a.max_records)
            raw=m.encoded(spec)
            with a.output.open('xb') as f:f.write(raw)
            result=dict(status='request_prepared',request_sha256=m.sha(raw),url=request_url(spec))
        elif a.action=='verify': result=verify(a.bundle,a.sha256)
        elif a.action=='diff':
            m.require(not any(a.output.resolve().is_relative_to(p.resolve()) for p in (a.bundle,a.previous)), 'diff output outside snapshots required')
            result=compare(a.previous,a.previous_sha256,a.bundle,a.sha256)
            with a.output.open('xb') as f:f.write(m.encoded(result))
        else:
            m.require(not a.output.exists() and not a.output.is_symlink(),'new output required before network/input read')
            request_raw=m.read(a.request,16384);m.require(m.sha(request_raw)==a.sha256,'request anchor mismatch')
            spec=validate_request(k.strict_json(request_raw))
            if a.action=='fetch':raw,meta=fetch(spec)
            else:
                raw=m.read(a.input,MAX_BYTES);m.require(m.sha(raw)==a.response_sha256,'response anchor mismatch')
                meta=capture_metadata(spec,'local-snapshot',a.observed_at,a.http_status,a.content_type,a.content_encoding,True,None)
            result=save(request_raw,raw,meta,a.output)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True))
        return 0 if result['status'] in ('request_prepared','records_captured','snapshots_compared') else 2
    except (ValueError,OSError,RecursionError) as error:
        print(json.dumps(dict(status='rejected',reason=str(error)),ensure_ascii=True));return 2


if __name__=='__main__':raise SystemExit(main())
