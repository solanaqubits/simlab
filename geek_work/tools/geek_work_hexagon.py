#!/usr/bin/env python3
"""Bounded read-only Hexagon metadata snapshots. No submission, crawling or graph promotion."""
import argparse
from datetime import datetime, timezone
import http.client
from pathlib import Path
import re
from urllib.parse import urlsplit, parse_qsl
import xml.etree.ElementTree as ET

import knowledge as k

HOST = 'hexagonmath.org'
MAX_BYTES = 1024 * 1024
MAX_RECORDS = 50
FILES = {'response.raw', 'source.json', 'records.json'}
VERSION = re.compile(r'(\d{4}\.\d{5})v([1-9]\d{0,5})')


def source_url(url):
    k.require(type(url) is str and len(url) <= 1000, 'source_url')
    u = urlsplit(url)
    k.require(u.scheme == 'https' and u.netloc == HOST and not u.fragment, 'source_origin')
    if u.path == '/api/v1/works':
        pairs = parse_qsl(u.query, keep_blank_values=True, strict_parsing=True)
        q = dict(pairs)
        k.require(len(q) == len(pairs) and set(q) <= {'limit', 'subject', 'q'}, 'query_parameters')
        k.require('limit' in q and re.fullmatch(r'[1-9]\d?', q['limit']) and int(q['limit']) <= MAX_RECORDS, 'explicit_limit')
        if 'subject' in q: k.require(re.fullmatch(r'(?:math|cs|stat)\.[A-Z]{2}|math-ph|quant-ph', q['subject']), 'subject')
        if 'q' in q: k.require(0 < len(q['q'].encode()) <= 48 and not any(ord(c) < 32 for c in q['q']), 'query_length')
        return 'json', int(q['limit'])
    k.require(not u.query and re.fullmatch(r'/rss/(?:all|math|cs|stat|physics|(?:math|cs|stat)\.[A-Z]{2}|math-ph|quant-ph)', u.path), 'endpoint_not_allowed')
    return 'rss', MAX_RECORDS


def string(value, name, limit=16000, optional=False):
    if optional and value is None: return None
    k.require(type(value) is str and 0 < len(value) <= limit, name)
    return value


def versioned(value):
    string(value, 'identifier', 100)
    m = VERSION.fullmatch(value.removeprefix('hexagon:'))
    k.require(m is not None, 'explicit_version_required')
    return m.group(1), int(m.group(2))


def base_record(ident, title, abstract, authors, subjects, license, status, declarations, published, fingerprint, markup):
    base, version = versioned(ident)
    string(title, 'title', 1000)
    k.require(abstract is None or type(abstract) is str and len(abstract) <= 64000, 'abstract')
    k.require(type(authors) is list and len(authors) <= 100, 'authors')
    for author in authors: string(author, 'author', 1000)
    k.require(type(subjects) is list and len(subjects) <= 100, 'subjects')
    for subject in subjects: string(subject, 'subject', 100)
    string(license, 'license', 200, optional=True)
    string(status, 'reported_status', 100, optional=True)
    string(published, 'publication_date', 100, optional=True)
    return dict(id=f'hexagon:{base}v{version}', work_id=base, version=version,
        record_url=f'https://{HOST}/abs/{base}v{version}', title=title, abstract=abstract,
        abstract_format=markup, authors=authors, subjects=subjects, license=license,
        reported_status=status, author_declarations=declarations, published_at=published,
        source_record_sha256=fingerprint, verification_status='unreviewed',
        peer_review_verified=False, accepted_into_knowledge_graph=False)


def parse(raw, url):
    kind, limit = source_url(url)
    k.require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, 'response_byte_limit')
    rows = []; pagination = None
    if kind == 'json':
        data = k.strict_json(raw)
        k.require(type(data) is dict and type(data.get('works')) is list and type(data.get('page')) is dict, 'api_shape')
        works = data['works']; pagination = data['page']
        k.require(len(works) <= limit, 'record_limit')
        for w in works:
            k.require(type(w) is dict, 'work_shape')
            base, version = versioned(w.get('id'))
            k.require(w.get('identifier') == base and type(w.get('versionNumber')) is int and w['versionNumber'] == version, 'version_mismatch')
            authors = w.get('authors'); k.require(type(authors) is list and all(type(a) is dict for a in authors), 'authors')
            cross = w.get('crossListSubjects', []); k.require(type(cross) is list, 'subjects')
            declarations = {key: w.get(key) for key in ('authorshipMode', 'humanUnderstanding')}
            for value in declarations.values(): string(value, 'declaration', 100, optional=True)
            rows.append(base_record(w['id'], w.get('title'), w.get('abstract'), [a.get('name') for a in authors],
                [w.get('subject')] + cross, w.get('license'), w.get('status'), declarations,
                w.get('publishedAt'), k.digest(k.canonical(w)), 'plain_text'))
    else:
        text = raw.decode('utf-8')
        k.require('\x00' not in text and not re.search(r'<!\s*(?:DOCTYPE|ENTITY)', text, re.I), 'xml_declarations_forbidden')
        root = ET.fromstring(text)
        k.require(root.tag == 'rss' and root.attrib.get('version') == '2.0', 'rss_shape')
        channels = root.findall('channel'); k.require(len(channels) == 1, 'rss_channel')
        stack = [(root, 0)]; count = 0
        while stack:
            element, depth = stack.pop(); count += 1
            k.require(depth <= 16 and count <= 5000, 'xml_structure_limit')
            stack.extend((x, depth+1) for x in element)
        items = channels[0].findall('item'); k.require(len(items) <= limit, 'record_limit')
        for item in items:
            def one(name, required=True):
                found = item.findall(name)
                k.require(len(found) == 1 if required else len(found) <= 1, 'rss_field:'+name)
                return found[0].text if found else None
            link = urlsplit(string(one('link'), 'record_link', 1000))
            k.require(link.scheme == 'https' and link.netloc == HOST and not link.query and not link.fragment, 'record_origin')
            ident = link.path.removeprefix('/abs/').removeprefix('/')
            rows.append(base_record(ident, one('title'), one('description', False),
                [x.text for x in item.findall('{http://purl.org/dc/elements/1.1/}creator')],
                [x.text for x in item.findall('category')], None, None,
                dict(authorshipMode=None, humanUnderstanding=None), one('pubDate', False),
                k.digest(ET.tostring(item, encoding='utf-8')), 'untrusted_html_text'))
    ids = [r['id'] for r in rows]
    k.require(len(ids) == len(set(ids)), 'duplicate_version')
    return dict(schema='geek-work-hexagon-records-1', source_url=url,
                response_sha256=k.digest(raw), records=rows, pagination=pagination,
                complete_catalog=False, accepted_into_knowledge_graph=False)


def tools_pin():
    return {Path(p).name:k.digest(Path(p).read_bytes()) for p in (__file__, k.__file__)}


def utc_stamp(value):
    string(value, 'observed_at', 100)
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    k.require(stamp.tzinfo is not None and stamp.utcoffset().total_seconds() == 0, 'utc_timestamp_required')


def snapshot(raw, url, observed_at, method, output):
    kind, _ = source_url(url)
    k.require(method in ('local-snapshot', 'https-get'), 'capture_method')
    utc_stamp(observed_at)
    records = parse(raw, url)
    source = dict(schema='geek-work-hexagon-source-1', url=url, format=kind,
                  observed_at=observed_at, capture_method=method, response_sha256=k.digest(raw))
    content = {'response.raw':raw, 'source.json':k.canonical(source)+b'\n', 'records.json':k.canonical(records)+b'\n'}
    output.mkdir(parents=True, exist_ok=False)
    for name, value in content.items(): k.write_new(output/name, value)
    seal = dict(schema='geek-work-hexagon-seal-1', files={name:k.digest(value) for name,value in content.items()}, tool_pins=tools_pin())
    k.write_new(output/'seal.json', k.canonical(seal)+b'\n')
    return dict(seal_sha256=k.digest(k.canonical(seal)), records=len(records['records']))


def verify(output, anchor):
    k.require(not output.is_symlink() and output.is_dir(), 'bundle_directory')
    k.require({p.name for p in output.iterdir()} == FILES|{'seal.json'}, 'bundle_file_set')
    seal = k.load(output/'seal.json')
    k.require(k.digest(k.canonical(seal)) == anchor, 'seal_anchor')
    k.obj(seal, {'schema', 'files', 'tool_pins'})
    k.require(seal['schema'] == 'geek-work-hexagon-seal-1' and seal['tool_pins'] == tools_pin(), 'seal_tools')
    k.require(type(seal['files']) is dict and set(seal['files']) == FILES, 'seal_files')
    data = {name:k.bounded(output/name) for name in FILES}
    for name, raw in data.items(): k.require(k.digest(raw) == seal['files'][name], 'file_hash:'+name)
    source = k.strict_json(data['source.json'])
    k.obj(source, {'schema','url','format','observed_at','capture_method','response_sha256'})
    k.require(source['schema'] == 'geek-work-hexagon-source-1' and source['capture_method'] in ('local-snapshot','https-get'), 'source_schema')
    k.require(source['format'] == source_url(source['url'])[0] and source['response_sha256'] == k.digest(data['response.raw']), 'source_binding')
    utc_stamp(source['observed_at'])
    records = parse(data['response.raw'], source['url'])
    k.require(records == k.strict_json(data['records.json']), 'projection_changed')
    return records


def diff(before, after):
    old = {r['id']:r for r in before['records']}; new = {r['id']:r for r in after['records']}
    return dict(schema='geek-work-hexagon-diff-1',
        added_versions=sorted(new.keys()-old.keys()),
        absent_from_new_snapshot=sorted(old.keys()-new.keys()),
        changed_same_version=sorted(key for key in old.keys() & new.keys() if old[key]['source_record_sha256'] != new[key]['source_record_sha256']),
        absence_means_withdrawal=False, accepted_into_knowledge_graph=False)


def fetch(url):
    kind, _ = source_url(url); u = urlsplit(url)
    connection = http.client.HTTPSConnection(HOST, timeout=20)
    try:
        connection.request('GET', u.path+('?' + u.query if u.query else ''), headers={
            'User-Agent':'GeekWork-HexagonMetadata/1', 'Accept':'application/json' if kind == 'json' else 'application/rss+xml',
            'Accept-Encoding':'identity'})
        response = connection.getresponse()
        k.require(response.status == 200, 'http_status:'+str(response.status))
        k.require(response.getheader('Content-Encoding', 'identity') == 'identity', 'content_encoding')
        allowed = {'application/json'} if kind == 'json' else {'application/rss+xml','application/xml','text/xml'}
        k.require(response.getheader('Content-Type','').split(';')[0].strip() in allowed, 'content_type')
        raw = response.read(MAX_BYTES+1); k.require(len(raw) <= MAX_BYTES, 'response_byte_limit')
        return raw
    finally: connection.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['fetch','import','verify','diff'])
    p.add_argument('--url'); p.add_argument('--input', type=Path); p.add_argument('--output', type=Path)
    p.add_argument('--observed-at'); p.add_argument('--bundle', type=Path); p.add_argument('--anchor')
    p.add_argument('--previous', type=Path); p.add_argument('--previous-anchor')
    a = p.parse_args()
    try:
        if a.action in ('fetch','import'):
            k.require(a.output is not None and a.url is not None, 'arguments')
            if a.action == 'fetch': raw=fetch(a.url); stamp=datetime.now(timezone.utc).isoformat()
            else:
                k.require(a.input is not None and a.observed_at is not None, 'import_arguments')
                raw=k.bounded(a.input);stamp=a.observed_at
            result=snapshot(raw,a.url,stamp,'https-get' if a.action=='fetch' else 'local-snapshot',a.output)
        else:
            k.require(a.bundle is not None and a.anchor is not None, 'verify_arguments')
            records=verify(a.bundle,a.anchor)
            if a.action=='verify': result=dict(status='verified_structure',records=len(records['records']))
            else:
                k.require(a.previous is not None and a.previous_anchor is not None and a.output is not None,'diff_arguments')
                result=diff(verify(a.previous,a.previous_anchor),records)
                k.write_new(a.output,k.canonical(result)+b'\n')
        print(k.canonical(result).decode())
    except (k.Refusal, OSError, ValueError, TypeError, KeyError, ET.ParseError, http.client.HTTPException) as e:
        print(k.canonical(dict(status='refused',reason=str(e))).decode());return 1
    return 0


if __name__ == '__main__': raise SystemExit(main())
