#!/usr/bin/env python3
"""Offline literal HTTP(S) reference queue; source text is never fetched or executed."""
import argparse
from collections import Counter
import ipaddress
from pathlib import Path
import re
from urllib.parse import urlsplit
import knowledge as k
import geek_work_fields as fields
import geek_work_memory as memory

MAX_REFERENCES=256
MAX_TEXT_BYTES=4*1024*1024
TOKEN=re.compile(r'https?://[^\s<>"\x27`]+')


def pins():
    return {Path(p).name:k.digest(Path(p).read_bytes()) for p in
            (__file__,fields.__file__,memory.__file__,k.__file__)}


def field_value(card,pointer):
    value=card
    for part in pointer.split('/')[1:]:
        key=part.replace('~1','/').replace('~0','~')
        value=value[int(key)] if type(value) is list else value[key]
    return value


def flags(url):
    result=[]
    if url[-1:] in '.,;!?)]}':result.append('ambiguous_trailing_punctuation')
    try:
        parsed=urlsplit(url);host=parsed.hostname
        if not host:return sorted(set(result+['malformed_url']))
        if parsed.username is not None or parsed.password is not None:result.append('credentials_present')
        try:private=not ipaddress.ip_address(host).is_global
        except ValueError:private=host=='localhost' or host.endswith(('.localhost','.local','.internal'))
        if private:result.append('private_or_local_literal')
        if parsed.scheme=='http':result.append('unencrypted_http')
        if host=='github.com':
            match=re.match(r'^/[^/]+/[^/]+/(?:blob|tree)/([^/]+)(?:/|$)',parsed.path)
            if match:
                result.append('pinned_git_syntax' if re.fullmatch('[0-9a-f]{40}',match[1]) else 'mutable_git_reference')
        if host=='hexagonmath.org' and re.fullmatch(r'/\d{4}\.\d{5}v[1-9]\d*',parsed.path):
            result.append('versioned_identifier_syntax')
    except ValueError:result.append('malformed_url')
    return sorted(set(result))


def build(graph,root,request):
    context=memory.retrieve(graph,root,request)
    k.require(context['graph_sha256']==request['expected_graph_sha256'],'graph_changed')
    k.require(all('revision_changed' not in row['issues'] for row in context['cards']),'revision_changed')
    refs=[];field_count=0;size=0
    for row in context['cards']:
        card=row['card'];card_sha=k.digest(k.canonical(card));paths=fields.string_fields(card);field_count+=len(paths)
        k.require(field_count<=fields.MAX_FIELDS,'reference_field_limit')
        for pointer in paths:
            value=field_value(card,pointer);raw=value.encode();size+=len(raw)
            k.require(size<=MAX_TEXT_BYTES,'reference_text_limit')
            field_sha=k.digest(raw)
            for match in TOKEN.finditer(value):
                literal=match.group()
                refs.append(dict(card_id=card['id'],revision=card['revision'],card_sha256=card_sha,
                                 field=pointer,field_sha256=field_sha,start=match.start(),end=match.end(),
                                 literal=literal,flags=flags(literal),source_issues=row['issues'],
                                 availability='not_checked',content_verification='not_checked'))
                k.require(len(refs)<=MAX_REFERENCES,'reference_count_limit')
    return dict(schema='geek-work-reference-queue-1',graph_sha256=context['graph_sha256'],
                context_sha256=k.digest(k.canonical(context)),
                request_sha256=k.digest(k.canonical(request)),tool_pins=pins(),references=refs,
                cards=len(context['cards']),fields_scanned=field_count,text_utf8_bytes=size,
                unique_literals=len({r['literal'] for r in refs}),context_issues=context['issues'],
                network_requests=0,model_calls=0,truth_status_changed=False,
                limits='Case-sensitive lexical HTTP(S) tokens in selected card string fields only; '
                       'not all document/PDF links or relative references. Raw punctuation is retained. '
                       'Flags describe syntax, not existence, immutability, safety, source authority or scientific validity. '
                       'No DNS, requests, redirects or URL repair. Offsets are Unicode codepoints.')


def verify(report,anchor,graph,root,request):
    memory.sha(anchor)
    k.require(k.digest(k.canonical(report))==anchor,'reference_anchor')
    k.require(k.canonical(report)==k.canonical(build(graph,root,request)),'reference_report_changed')
    return dict(status='verified_reference_queue',network_requests=0,scientific_verification=False)


def summarize(report,anchor,graph,root,request):
    """Replay first; expose aggregate counts only, never source text or identifiers."""
    verify(report,anchor,graph,root,request)
    rows=report['references']
    counts=Counter(flag for row in rows for flag in row['flags'])
    return dict(schema='geek-work-reference-summary-1',
                status='verified_reference_summary',
                cards=report['cards'],references=len(rows),
                unique_literals=report['unique_literals'],
                repeated_occurrences=len(rows)-report['unique_literals'],
                flag_occurrences=dict(sorted(counts.items())),
                occurrences_with_source_issues=sum(bool(row['source_issues']) for row in rows),
                availability_checked=0,content_verified=0,
                network_requests=0,model_calls=0,truth_status_changed=False,
                limits='Aggregate metadata only; counts may still be private. '
                       'No URLs, card IDs, field paths, source paths or source hashes. '
                       'Replay verifies provenance, not availability or scientific truth.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['scan','verify','summarize']);p.add_argument('--graph',type=Path,required=True)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--request',type=Path,required=True)
    p.add_argument('--output',type=Path);p.add_argument('--report',type=Path);p.add_argument('--anchor')
    a=p.parse_args()
    try:
        graph=k.load(a.graph);request=k.load(a.request)
        if a.action=='scan':
            k.require(a.output is not None,'scan_output_required')
            report=build(graph,a.root,request);k.write_new(a.output,k.canonical(report)+b'\n')
            result=dict(status='reference_queue_created',references=len(report['references']),
                        report_sha256=k.digest(k.canonical(report)),network_requests=0)
        else:
            k.require(a.report is not None and a.anchor is not None,'verify_arguments')
            operation=summarize if a.action=='summarize' else verify
            result=operation(k.load(a.report),a.anchor,graph,a.root,request)
            if a.output:k.write_new(a.output,k.canonical(result)+b'\n')
        print(k.canonical(result).decode())
    except (k.Refusal,OSError,ValueError,TypeError,KeyError) as error:
        print(k.canonical(dict(status='refused',reason=str(error))).decode());return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
